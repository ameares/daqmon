# daqmon – HP 34970A Data Acquisition Monitor

A Python CLI tool for configuring, scanning, and logging data from the
HP/Agilent 34970A Data Acquisition / Switch Unit via serial (RS-232).
Readings are logged to the console and written to InfluxDB v2.

## Installation

**pip:**
```bash
pip install daqmon
```

**uv** (installs into the current project or virtual environment):
```bash
uv add daqmon
```

**uvx** (run without installing — useful for one-off use):
```bash
uvx daqmon identify
```

## Quick start

```bash
# Create the default config file at ~/.config/daqmon/config.json
daqmon init

# Edit the config to set your serial port and InfluxDB connection
nano ~/.config/daqmon/config.json

# Scaffold a scan definition at ./scan.json
daqmon init-scan

# Identify the instrument
daqmon identify

# Run a scan (Ctrl-C to stop)
daqmon scan myscan.json

# Download the current instrument configuration
daqmon backup -o backup.json
```

## Development

```bash
# Clone and install in editable mode with dev dependencies
git clone https://github.com/YOUR_USERNAME/daqmon
cd daqmon
uv sync

# Run the CLI from source
uv run daqmon identify

# Lint, format, type-check, test
uv run ruff check src/
uv run ruff format src/
uv run mypy src/
uv run pytest tests/
```

## Files

| File | Purpose |
|------|---------|
| `config.json` | Serial port and InfluxDB connection settings |
| `myscan.json` | Scan definition (channels, types, interval) |
| `backup.json` | Downloaded instrument configuration (same format as `myscan.json`) |

## config.json

```jsonc
{
  "serial": {
    "port": "/dev/ttyUSB0",   // Serial port path
    "baudrate": 9600,          // 9600 default for 34970A
    "timeout": 10.0            // Read timeout in seconds
  },
  "influxdb": {
    "enabled": true,
    "url": "http://localhost:8086",
    "token": "my-token",
    "org": "my-org",
    "bucket": "daqmon",
    "measurement": "hp34970a"
  }
}
```

## Scan definition (myscan.json / backup.json)

### Top-level fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | string | `""` | Human-readable label for this scan |
| `scan_interval` | float | `10.0` | Seconds between sweeps |
| `scan_count` | int | `0` | Number of sweeps to run; `0` = infinite (Ctrl-C to stop) |
| `ambient_correction` | bool | `false` | If `true`, adds a `_rise` reading for each temperature channel (value minus ambient) |
| `ambient_channel` | int | — | Channel number to use as the ambient reference (required when `ambient_correction` is `true`) |
| `channels` | array | — | List of channel definitions (see below) |

### Channel fields

| Field | Type | Default | Applies to | Description |
|-------|------|---------|------------|-------------|
| `channel` | int | **required** | all | Channel number: slot × 100 + line (101–120, 201–220, 301–320) |
| `name` | string | **required** | all | Friendly name written as an InfluxDB tag |
| `function` | string | `"dc_voltage"` | all | Measurement function (see table below) |
| `range` | string | `"auto"` | dc_voltage, ac_voltage, dc_current, ac_current, resistance_2w, resistance_4w, frequency, period | Measurement range or `"auto"` |
| `nplc` | float | `1.0` | dc_voltage, dc_current, resistance_2w, resistance_4w, temperature | Integration time in power-line cycles (0.02–100) |
| `tc_type` | string | `"K"` | temperature, thermocouple | Thermocouple type: `J`, `K`, `T`, `E`, `R`, `S`, `B`, `N` |
| `ref_junction` | string | `"internal"` | temperature, thermocouple | Reference junction: `internal`, `fixed`, or `external` |
| `ref_fixed_temp` | float | — | temperature, thermocouple | Fixed reference junction temperature in °C (only when `ref_junction` is `"fixed"`) |
| `ref_channel` | int | — | temperature, thermocouple | Channel number of external reference junction (only when `ref_junction` is `"external"`) |
| `ac_bandwidth` | float | — | ac_voltage, ac_current | AC bandwidth filter in Hz: `3`, `20`, or `200` |
| `unit` | string | `""` | all | Unit label written to InfluxDB |
| `gain` | float | `1.0` | all | Multiplier applied to raw reading: `result = raw × gain + offset` |
| `offset` | float | `0.0` | all | Offset added after gain: `result = raw × gain + offset` |
| `delay` | float | — | all | Relay settling time in seconds inserted after this channel is configured |

### Supported measurement functions

| Key | SCPI function | range | nplc | ac_bandwidth |
|-----|---------------|:-----:|:----:|:------------:|
| `dc_voltage` | VOLT:DC | ✓ | ✓ | |
| `ac_voltage` | VOLT:AC | ✓ | | ✓ |
| `dc_current` | CURR:DC | ✓ | ✓ | |
| `ac_current` | CURR:AC | ✓ | | ✓ |
| `resistance_2w` | RES (2-wire) | ✓ | ✓ | |
| `resistance_4w` | FRES (4-wire) | ✓ | ✓ | |
| `frequency` | FREQ | ✓ | | |
| `period` | PER | ✓ | | |
| `temperature` | TEMP (thermocouple) | | ✓ | |
| `thermocouple` | TEMP (alias) | | ✓ | |
| `digital_input` | DIG | | | |
| `totalize` | TOT | | | |

### Range values

| Function | Valid range strings |
|----------|---------------------|
| `dc_voltage` | `"auto"`, `"0.1"`, `"1"`, `"10"`, `"100"`, `"300"` |
| `ac_voltage` | `"auto"`, `"0.1"`, `"1"`, `"10"`, `"100"`, `"300"` |
| `dc_current` | `"auto"`, `"0.01"`, `"0.1"`, `"1"` |
| `ac_current` | `"auto"`, `"0.01"`, `"0.1"`, `"1"` |
| `resistance_2w` / `resistance_4w` | `"auto"`, `"100"`, `"1000"`, `"10000"`, `"100000"`, `"1000000"`, `"10000000"`, `"100000000"` |
| `frequency` / `period` | `"auto"`, `"0.1"`, `"1"`, `"10"`, `"100"`, `"300"` (input voltage range) |

### Example: full-featured scan

```jsonc
{
  "description": "Thermal test – oven channels + power supply",
  "scan_interval": 5.0,          // Sweep every 5 seconds
  "scan_count": 0,               // Run until Ctrl-C
  "ambient_correction": true,    // Add _rise readings for temperature channels
  "ambient_channel": 110,        // Channel 110 is the ambient reference
  "channels": [
    {
      // Thermocouple – internal cold junction reference
      "channel": 101,
      "name": "oven_top",
      "function": "temperature",
      "tc_type": "K",
      "ref_junction": "internal",
      "nplc": 5.0,
      "unit": "degC"
    },
    {
      // Thermocouple – fixed cold junction reference
      "channel": 102,
      "name": "oven_bottom",
      "function": "temperature",
      "tc_type": "K",
      "ref_junction": "fixed",
      "ref_fixed_temp": 23.5,    // Reference junction is 23.5 °C
      "unit": "degC"
    },
    {
      // Thermocouple – external cold junction on another channel
      "channel": 103,
      "name": "sample",
      "function": "temperature",
      "tc_type": "T",
      "ref_junction": "external",
      "ref_channel": 110,        // Cold junction measured on channel 110
      "unit": "degC"
    },
    {
      // Ambient reference channel (used for _rise correction above)
      "channel": 110,
      "name": "ambient",
      "function": "temperature",
      "tc_type": "K",
      "ref_junction": "internal",
      "unit": "degC"
    },
    {
      // DC voltage with explicit range and high integration time
      "channel": 201,
      "name": "psu_output",
      "function": "dc_voltage",
      "range": "10",             // 10 V range
      "nplc": 10.0,              // Slow, high-accuracy
      "unit": "V"
    },
    {
      // DC current with gain/offset scaling
      "channel": 202,
      "name": "load_current",
      "function": "dc_current",
      "range": "auto",
      "nplc": 1.0,
      "gain": 1000.0,            // Convert A → mA
      "offset": 0.0,
      "unit": "mA"
    },
    {
      // AC voltage with bandwidth filter
      "channel": 203,
      "name": "mains_voltage",
      "function": "ac_voltage",
      "range": "300",
      "ac_bandwidth": 20,        // 20 Hz bandwidth filter
      "unit": "Vrms"
    },
    {
      // 4-wire resistance
      "channel": 204,
      "name": "heater_resistance",
      "function": "resistance_4w",
      "range": "auto",
      "nplc": 2.0,
      "unit": "ohm",
      "delay": 0.05              // 50 ms relay settling delay
    },
    {
      // Frequency measurement
      "channel": 205,
      "name": "fan_speed_freq",
      "function": "frequency",
      "range": "auto",
      "unit": "Hz"
    },
    {
      // Digital input (returns integer bitmask)
      "channel": 301,
      "name": "door_switch",
      "function": "digital_input"
    }
  ]
}
```

## CLI reference

```
daqmon [-c CONFIG] [-v] {scan,backup,identify}

  -c, --config   Path to config.json (default: config.json)
  -v, --verbose  Enable DEBUG logging

  scan SCAN_FILE         Upload config and start scanning
       --poll-interval   Polling rate in seconds (default: 2.0)

  backup [-o OUTPUT]     Download instrument config to JSON (default: backup.json)

  identify               Print *IDN? response
```

## Architecture

```
cli.py          argparse entry point, signal handling, orchestration
instrument.py   HP34970A SCPI driver over pyserial
config.py       ScanConfig / ChannelConfig dataclasses + JSON I/O
scanner.py      Channel configuration, scan loop, data parsing
influx.py       InfluxDB v2 writer
backup.py       Download instrument config to JSON
```
