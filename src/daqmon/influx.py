"""InfluxDB writer for acquired data points."""

from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger(__name__)


class InfluxWriter:
    """Writes measurement data to InfluxDB v2.x.

    Writes are enqueued and processed by a background thread, so the caller
    is never blocked by network latency or a temporarily unreachable InfluxDB.
    Failed writes are retried with exponential backoff. On close(), the queue
    is fully drained before returning.
    """

    def __init__(
        self,
        url: str = "http://localhost:8086",
        token: str = "",
        org: str = "",
        bucket: str = "daqmon",
        measurement: str = "hp34970a",
        enabled: bool = True,
        queue_maxsize: int = 1000,
        retry_max_delay: float = 60.0,
    ):
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.measurement = measurement
        self.enabled = enabled
        self.retry_max_delay = retry_max_delay
        self._client: Optional[InfluxDBClient] = None
        self._write_api = None
        self._queue: queue.Queue[Optional[list[dict[str, Any]]]] = queue.Queue(maxsize=queue_maxsize)
        self._worker: Optional[threading.Thread] = None

    def open(self) -> None:
        if not self.enabled:
            logger.info("InfluxDB output disabled")
            return
        logger.info("Connecting to InfluxDB at %s, bucket=%s", self.url, self.bucket)
        self._client = InfluxDBClient(
            url=self.url, token=self.token, org=self.org
        )
        self._ensure_bucket()
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        self._worker = threading.Thread(
            target=self._writer_loop, name="influx-writer", daemon=False
        )
        self._worker.start()

    def _ensure_bucket(self) -> None:
        """Create the bucket if it does not already exist."""
        buckets_api = self._client.buckets_api()
        if buckets_api.find_bucket_by_name(self.bucket) is None:
            buckets_api.create_bucket(bucket_name=self.bucket, org=self.org)
            logger.info("Created InfluxDB bucket: %s", self.bucket)
        else:
            logger.debug("InfluxDB bucket already exists: %s", self.bucket)

    def close(self) -> None:
        if self._worker is not None:
            logger.info("Flushing InfluxDB write queue (%d items)...", self._queue.qsize())
            self._queue.put(None)  # poison pill
            self._worker.join()
            self._worker = None
        if self._client:
            logger.info("Closing InfluxDB connection")
            self._client.close()
            self._client = None
            self._write_api = None

    def write_readings(self, readings: list[dict[str, Any]]) -> None:
        """Enqueue a batch of readings for async writing. Returns immediately."""
        if not self.enabled or self._worker is None:
            return
        try:
            self._queue.put_nowait(readings)
        except queue.Full:
            logger.warning(
                "InfluxDB write queue full – dropping sweep of %d readings",
                len(readings),
            )

    def _writer_loop(self) -> None:
        """Background thread: drain queue, retry on failure with exponential backoff."""
        retry_delay = 1.0
        while True:
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is None:  # poison pill: drain then exit
                self._drain_remaining()
                break

            while True:
                try:
                    self._do_write(item)
                    retry_delay = 1.0
                    self._queue.task_done()
                    break
                except Exception:
                    logger.warning(
                        "InfluxDB write failed; retrying in %.1fs (%d items queued)",
                        retry_delay,
                        self._queue.qsize(),
                    )
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, self.retry_max_delay)

    def _drain_remaining(self) -> None:
        """Flush all queued items after receiving shutdown signal."""
        retry_delay = 1.0
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                break
            while True:
                try:
                    self._do_write(item)
                    self._queue.task_done()
                    retry_delay = 1.0
                    break
                except Exception:
                    logger.warning(
                        "InfluxDB flush failed during shutdown; retrying in %.1fs (%d remaining)",
                        retry_delay,
                        self._queue.qsize(),
                    )
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, self.retry_max_delay)

    def _do_write(self, readings: list[dict[str, Any]]) -> None:
        """Build Point objects and write to InfluxDB. Raises on failure."""
        points: list[Point] = []
        for r in readings:
            p = (
                Point(self.measurement)
                .tag("channel", str(r["channel"]))
                .tag("name", r["name"])
                .field("value", float(r["value"]))
                .time(r.get("timestamp", datetime.now(timezone.utc)), WritePrecision.MS)
            )
            if r.get("unit"):
                p = p.tag("unit", r["unit"])
            points.append(p)

        self._write_api.write(bucket=self.bucket, record=points)
        logger.debug("Wrote %d points to InfluxDB", len(points))
