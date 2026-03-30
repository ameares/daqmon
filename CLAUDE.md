# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run the CLI
uv run daqmon -c config.json identify
uv run daqmon -c config.json scan myscan.json
uv run daqmon -c config.json backup -o backup.json

# Lint and format
ruff check src/
ruff format src/

# Type check
mypy src/

# Run tests
pytest tests/
pytest --cov=daqmon tests/
```

## Architecture

daqmon is a CLI tool for controlling and reading data from the HP/Agilent 34970A Data Acquisition unit over RS-232 (SCPI protocol), logging readings to CSV files and InfluxDB v2.

**Layered structure:**

```
cli.py           → Argument parsing, command dispatch, factory functions
scanner.py       → Scan loop: configure instrument, poll readings, distribute to writers
instrument.py    → SCPI driver (HP34970A class): all serial communication
config.py        → ScanConfig / ChannelConfig dataclasses; JSON serialization
influx.py        → InfluxWriter: queue-based async writes with exponential backoff retry
csv_writer.py    → CsvWriter: timestamped CSV logs in logs/
backup.py        → download_config(): read full instrument state to JSON
```

**Key data flow:**
1. `cli.py` loads `config.json` (serial port + InfluxDB settings), instantiates `HP34970A` and `InfluxWriter`
2. `scanner.py:configure_scan()` applies each `ChannelConfig` to the instrument via SCPI commands
3. `scanner.py:run_scan()` polls the instrument on a configurable interval, parses raw readings, applies per-channel gain/offset/ambient corrections, then pushes to both `InfluxWriter` and `CsvWriter`
4. `InfluxWriter` runs a background thread draining a queue with retry logic; graceful shutdown drains the queue on SIGINT

**Config files (not source code):**
- `config.json` — serial port and InfluxDB connection settings (see `src/daqmon/config_example.json`)
- `myscan.json` — scan definition (array of `ChannelConfig` objects); can be generated via `backup` command

**Measurement functions** (11 supported): DC/AC voltage, DC/AC current, 2-wire/4-wire resistance, frequency, period, thermocouple temperature, digital input, totalizer. Each function maps to a specific SCPI subsystem in `instrument.py`.
