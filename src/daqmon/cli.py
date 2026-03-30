"""CLI entry point for daqmon."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
from pathlib import Path

from . import __version__
from .backup import download_config
from .config import ScanConfig
from .csv_writer import CsvWriter
from .influx import InfluxWriter
from .instrument import HP34970A
from .scanner import run_scan

logger = logging.getLogger("daqmon")

DEFAULT_CONFIG = "config.json"


def load_app_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        logger.error("Config file not found: %s", p)
        sys.exit(1)
    with p.open() as f:
        return json.load(f)


def make_instrument(cfg: dict) -> HP34970A:
    ser = cfg.get("serial", {})
    return HP34970A(
        port=ser.get("port", "/dev/ttyUSB0"),
        baudrate=ser.get("baudrate", 9600),
        timeout=ser.get("timeout", 10.0),
    )


def make_influx(cfg: dict) -> InfluxWriter:
    db = cfg.get("influxdb", {})
    return InfluxWriter(
        url=db.get("url", "http://localhost:8086"),
        token=db.get("token", ""),
        org=db.get("org", ""),
        bucket=db.get("bucket", "daqmon"),
        measurement=db.get("measurement", "hp34970a"),
        enabled=db.get("enabled", True),
        queue_maxsize=db.get("queue_maxsize", 1000),
        retry_max_delay=db.get("retry_max_delay", 60.0),
    )


def setup_logging(level: str = "INFO") -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    fmt = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
    logging.basicConfig(level=numeric, format=fmt, stream=sys.stdout)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="daqmon",
        description="HP 34970A Data Acquisition Manager",
    )
    p.add_argument(
        "--version", action="version", version=f"daqmon {__version__}"
    )
    p.add_argument(
        "-c", "--config",
        default=DEFAULT_CONFIG,
        help="Path to application config JSON (serial + influxdb). Default: %(default)s",
    )
    p.add_argument(
        "--bucket",
        default=None,
        help="Override the InfluxDB bucket from the config file.",
    )
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG logging",
    )

    sub = p.add_subparsers(dest="command", help="Available commands")

    scan_p = sub.add_parser("scan", help="Upload a scan config and start scanning")
    scan_p.add_argument("scan_file", help="Path to scan definition JSON (e.g. myscan.json)")
    scan_p.add_argument(
        "--poll-interval", type=float, default=2.0,
        help="Instrument poll interval in seconds. Default: %(default)s",
    )

    backup_p = sub.add_parser("backup", help="Download current instrument config to JSON")
    backup_p.add_argument(
        "-o", "--output", default="backup.json",
        help="Output file path. Default: %(default)s",
    )

    sub.add_parser("identify", help="Query instrument *IDN? and print it")

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging("DEBUG" if args.verbose else "INFO")

    if not args.command:
        parser.print_help()
        sys.exit(0)

    app_cfg = load_app_config(args.config)

    if args.bucket is not None:
        logger.debug("Overriding influxdb.bucket with CLI value: %s", args.bucket)
        app_cfg.setdefault("influxdb", {})["bucket"] = args.bucket

    inst = make_instrument(app_cfg)
    influx = make_influx(app_cfg)

    stop_event = threading.Event()

    def _sigint_handler(sig, frame):
        logger.info("SIGINT received – shutting down …")
        stop_event.set()

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        inst.open()

        if args.command == "identify":
            idn = inst.idn()
            print(f"Instrument: {idn}")

        elif args.command == "backup":
            download_config(inst, output_path=args.output)
            print(f"Configuration saved to {args.output}")

        elif args.command == "scan":
            scan_cfg = ScanConfig.load(args.scan_file)
            logger.info(
                "Loaded scan config: %s (%d channels, interval=%.1fs)",
                args.scan_file,
                len(scan_cfg.channels),
                scan_cfg.scan_interval,
            )

            influx.open()

            bucket = app_cfg.get("influxdb", {}).get("bucket", "daqmon")
            csv_writer = CsvWriter(bucket=bucket)
            csv_writer.open()

            try:
                run_scan(
                    inst=inst,
                    scan_cfg=scan_cfg,
                    influx=influx,
                    csv_writer=csv_writer,
                    poll_interval=args.poll_interval,
                    stop_event=stop_event,
                )
            finally:
                csv_writer.close()

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt – shutting down")
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)
    finally:
        influx.close()
        inst.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()