# Fluke 45 Dual Display Multimeter — Computer Interface Command Set

## Overview

The Fluke 45 supports both **RS-232** and **IEEE-488** computer interfaces. Commands are identical across both interfaces except where noted. Parameters supplied by the user or strings returned by the meter are enclosed in angle brackets (e.g., `<value>`).

---

## IEEE-488 Interface Capabilities

| Subset | Description |
|--------|-------------|
| SH1 | Source Handshake |
| AH1 | Acceptor Handshake |
| T5 | Talker |
| L4 | Listener |
| SRI | Service Request |
| RL1 | Remote/Local |
| DC1 | Device Clear (`^C` is the RS-232 equivalent) |
| DT1 | Device Trigger |
| E1 | Electrical Interface |

> **Note:** `^C` (CTRL+C) is the RS-232 equivalent of DC1; it causes `<CR><LF>` and a new prompt to be output.

---

## IEEE-488 Common Commands

| Command | Name | Description |
|---------|------|-------------|
| `*CLS` | Clear Status | Clears all event registers summarized in the status byte, except "Message Available" (cleared only if `*CLS` is the first message in the command line). |
| `*ESE <value>` | Event Status Enable | Sets the Event Status Enable Register to `<value>` (integer 0–255). Binary equivalent of `<value>` maps to register bit states. Generates Execution Error if out of range. Example: decimal 16 = binary `00010000`, sets bit 4 (EXE). |
| `*ESE?` | Event Status Enable Query | Returns the `<value>` of the Event Status Enable Register set by `*ESE`. |
| `*ESR?` | Event Status Register Query | Returns the `<value>` of the Event Status Register and then clears it. |
| `*IDN` | Identification Query | Returns four comma-separated fields: manufacturer (`FLUKE`), model (`45`), seven-digit serial number, main software version, display software version. |
| `*OPC` | Operation Complete Command | Sets the Operation Complete bit in the Standard Event Status Register when parsed. |
| `*OPC?` | Operation Complete Query | Places an ASCII `"1"` in the output queue when parsed. |
| `*RST` | Reset | Performs power-up reset except IEEE-488 interface state is unchanged (instrument address, Status Byte, and Event Status Register are preserved). |
| `*SRE <value>` | Service Request Enable | Sets the Service Request Enable Register to `<value>` (integer 0–255). Bit 6 is ignored. Generates Execution Error if out of range. |
| `*SRE?` | Service Request Enable Query | Returns `<value>` of the Service Request Enable Register (bit 6 always zero). |
| `*STB?` | Read Status Byte | Returns `<value>` of the Status Byte with bit 6 as the "Master Summary" bit. |
| `*TRG` | Trigger | Causes the meter to trigger a measurement when parsed. |
| `*TST` | Self-Test Query | Runs internal self-test (~15 seconds; all display segments lit). Returns a numeric result (see table below). Meter reverts to power-up configuration after test. |
| `*WAI` | Wait-to-Continue | Required by IEEE-488.2 standard. Non-operational on the Fluke 45; accepted but has no effect. |

### Self-Test Result Codes (`*TST`)

| Number | State |
|--------|-------|
| 0 | Passes |
| 1 | A/D self-test failed |
| 2 | A/D dead |
| 4 | EEPROM instrument configuration bad |
| 8 | EEPROM calibration data bad |
| 16 | Display dead |
| 32 | Display self-test failed |
| 64 | ROM test failed |
| 128 | External RAM test failed |
| 256 | Internal RAM test failed |

> **Example:** Decimal 9 (8 + 1) = binary `000001001` → A/D self-test failed **and** EEPROM calibration data bad.

---

## Function Commands and Queries

Commands under *Primary Display* operate on the primary display; *Secondary Display* commands operate on the secondary display.

| Primary Display | Secondary Display | Function |
|-----------------|-------------------|----------|
| `AAC` | `AAC2` | AC current |
| `AACDC` | *(not available)* | AC + DC rms current (primary only) |
| `ADC` | `ADC2` | DC current |
| — | `CLR2` | Clears measurement from secondary display |
| `CONT` | — | Continuity test (primary only) |
| `DIODE` | `DIODE2` | Diode test |
| `FREQ` | `FREQ2` | Frequency |
| `FUNC1?` | — | Returns function selected for primary display as command mnemonic. Example: `"FREQ"` |
| — | `FUNC2?` | Returns function selected for secondary display as command mnemonic. Generates Execution Error if secondary display is inactive. |
| `OHMS` | `OHMS2` | Resistance |
| `VAC` | `VAC2` | AC volts |
| `VACDC` | *(not available)* | AC + DC rms volts (primary only) |
| `VDC` | `VDC2` | DC volts |

> **Note:** If `AACDC` or `VACDC` is selected on the primary display, no other function can be selected for the secondary display; an Execution Error is generated if attempted.

---

## Function Modifier Commands and Queries

Function modifiers alter normal measurement operation on the **primary display only**.

| Command | Description |
|---------|-------------|
| `DB` | Enters decibels modifier; primary display reads in dB. Execution Error if not in a volts AC/DC function. |
| `DBCLR` | Exits decibels modifier; restores normal units. Also clears dB Power, REL, and MN MX modifiers. |
| `DBPOWER` | Enters dB Power modifier (reads in Watts). Requires reference impedance of 2, 4, 8, or 16 Ω and a voltage function; otherwise Execution Error. |
| `DBREF <value>` | Sets dB reference impedance. See Reference Impedance table below. Execution Error if `<value>` is invalid. |
| `DBREF?` | Returns current dB reference impedance `<value>`. |
| `HOLD` | Enters Touch Hold modifier. If already in Touch Hold, forces and displays a reading. |
| `HOLDCLR` | Exits Touch Hold; restores normal display. |
| `HOLDTHRESH <threshold>` | Sets Touch Hold threshold: `1` = very stable, `2` = stable, `3` = noisy. Execution Error for any other value. |
| `HOLDTHRESH?` | Returns current Touch Hold threshold (`1`, `2`, or `3`). |
| `MAX` | Enters MN MX modifier using the present reading as the maximum. If already in MN MX, displays maximum value. Autoranging disabled. |
| `MAXSET <numeric value>` | Enters MN MX modifier with `<numeric value>` as the maximum. Accepts signed integer, signed real, or scientific notation. Execution Error if value exceeds range. |
| `MIN` | Enters MN MX modifier using the present reading as the minimum. If already in MN MX, displays minimum value. Autoranging disabled. |
| `MINSET <numeric value>` | Enters MN MX modifier with `<numeric value>` as the minimum. Accepts signed integer, signed real, or scientific notation. Execution Error if value exceeds range. |
| `MMCLR` | Exits MN MX modifier; stored min/max values are lost. Returns to ranging mode/range from before MN MX was selected. |
| `MOD?` | Returns a numeric value indicating active modifiers: `1`=MN, `2`=MX, `4`=HOLD, `8`=dB, `16`=dB Power, `32`=REL, `64`=COMP. Multiple modifiers return the sum (e.g., dB + REL = `40`). |
| `REL` | Enters relative (REL) modifier using the primary display value as the relative base. Autoranging disabled. |
| `RELCLR` | Exits REL modifier; returns to ranging mode/range from before REL was selected. |
| `RELSET <relative base>` | Enters REL modifier using `<relative base>` as the offset. Accepts signed integer, signed real, or scientific notation. Execution Error if value exceeds range. |
| `RELSET?` | Returns current `<relative base>`. Execution Error if REL modifier is not active. |

### dB Reference Impedance Values (`DBREF`)

| Value | Ref Impedance (Ω) | Value | Ref Impedance (Ω) |
|-------|-------------------|-------|-------------------|
| 1 | 2 | 12 | 150 |
| 2 | 4 | 13 | 250 |
| 3 | 8 | 14 | 300 |
| 4 | 16 | 15 | 500 |
| 5 | 50 | 16 | 600 |
| 6 | 75 | 17 | 800 |
| 7 | 93 | 18 | 900 |
| 8 | 110 | 19 | 1000 |
| 9 | 124 | 20 | 1200 |
| 10 | 125 | 21 | 8000 |
| 11 | 135 | | |

---

## Range and Measurement Rate Commands and Queries

| Command | Description |
|---------|-------------|
| `AUTO` | Enters autoranging mode on primary display. Execution Error if autorange cannot be selected (e.g., REL, dB, MN MX, or diode/continuity test active). |
| `AUTO?` | Returns `1` if in autorange, `0` if not. |
| `FIXED` | Exits autoranging on primary display; enters manual ranging at the current range. |
| `RANGE <range>` | Sets primary display to the range designated by `<range>` (integer 1–7). See range tables below. |
| `RANGE1?` | Returns the range currently selected on the primary display. |
| `RANGE2?` | Returns the range currently selected on the secondary display. Execution Error if secondary display is inactive. |
| `RATE <speed>` | Sets measurement rate: `S` = slow (2.5 readings/sec), `M` = medium (5 readings/sec), `F` = fast (20 readings/sec). Case-insensitive. Execution Error for any other value. |
| `RATE?` | Returns current measurement rate as `S`, `M`, or `F`. |

### Range Values — Fast & Medium Measurement Rate

| Range | Voltage | Resistance | Current | Frequency |
|-------|---------|------------|---------|-----------|
| 1 | 300 mV | 300 Ω | 30 mA | 1000 Hz |
| 2 | 3 V | 3 kΩ | 100 mA | 10 kHz |
| 3 | 30 V | 30 kΩ | 10 A | 100 kHz |
| 4 | 300 V | 300 kΩ | ERROR | 1000 kHz |
| 5 | 1000 V dc* | 3 MΩ | ERROR | 1 MHz |
| 6 | ERROR | 30 MΩ | ERROR | ERROR |
| 7 | ERROR | 300 MΩ | ERROR | ERROR |

### Range Values — Slow Measurement Rate

| Range | Voltage | Resistance | Current | Frequency |
|-------|---------|------------|---------|-----------|
| 1 | 100 mV | 100 Ω | 10 mA | 1000 Hz |
| 2 | 1000 mV | 1000 Ω | 100 mA | 10 kHz |
| 3 | 10 V | 10 kΩ | 10 A | 100 kHz |
| 4 | 100 V | 100 kΩ | ERROR | 1000 kHz |
| 5 | 1000 V dc* | 1000 kΩ | ERROR | 1 MHz |
| 6 | ERROR | 10 MΩ | ERROR | ERROR |
| 7 | ERROR | 100 MΩ | ERROR | ERROR |

*\* 1000 V dc / 750 V ac*

---

## Measurement Queries

| Command | Description |
|---------|-------------|
| `MEAS1?` | Returns the value on the primary display after the next triggered measurement. |
| `MEAS2?` | Returns the value on the secondary display after the next triggered measurement. Execution Error if secondary display is off. |
| `MEAS?` | Returns values from both displays after the next triggered measurement (if both are on), separated per the active FORMAT. If secondary display is off, equivalent to `MEAS1?`. **Do not use with external trigger types (TRIGGER 2–5).** |
| `VAL1?` | Returns the value currently shown on the primary display. If blank, returns the next triggered measurement. |
| `VAL2?` | Returns the value currently shown on the secondary display. Execution Error if secondary display is off. If blank, returns the next triggered measurement. |
| `VAL?` | Returns values from both displays in the active FORMAT. If secondary is off, equivalent to `VAL1?`. If a display is blank, the next triggered measurement is returned for that display. |

### Output Format Examples

| Format | Example Output |
|--------|----------------|
| Format 1 | `+1.2345E+0,+6.7890E+3<CR><LF>` |
| Format 2 | `+1.2345E+0 VDC, +6.7890E+3 ADC<CR><LF>` |

---

## Compare Commands and Queries

| Command | Description |
|---------|-------------|
| `COMP` | Enters compare (COMP) function. Touch Hold is automatically enabled. |
| `COMP?` | Returns: `HI` (above range), `LO` (below range), `PASS` (within range), or `—` (measurement not yet complete). |
| `COMPCLR` | Exits compare function (and Touch Hold if active); restores normal display. |
| `COMPHI <high value>` | Sets the HI compare value. Accepts signed integer, signed real, or scientific notation. |
| `COMPLO <low value>` | Sets the LO compare value. Accepts signed integer, signed real, or scientific notation. |
| `HOLDCLR` | Exits Touch Hold without exiting the compare function. |

---

## Trigger Configuration Commands

| Command | Description |
|---------|-------------|
| `TRIGGER <type>` | Sets trigger configuration to `<type>` (integer 1–5). Execution Error for invalid values. |
| `TRIGGER?` | Returns the current trigger `<type>`. |

### Trigger Types

| Type | Trigger Source | Rear Trigger | Settling Delay |
|------|----------------|--------------|----------------|
| 1 | Internal | Disabled | Off |
| 2 | External | Disabled | Off |
| 3 | External | Disabled | On |
| 4 | External | Enabled | Off |
| 5 | External | Enabled | On |

> **Tip:** Use trigger types 3 or 5 (settling delay enabled) when the input signal is not stable before a measurement is triggered.

---

## Miscellaneous Commands and Queries

| Command | Description |
|---------|-------------|
| `^C` (CTRL+C) | RS-232 equivalent of IEEE-488 DCL. Outputs `<CR><LF>` and `=><CR><LF>`. |
| `FORMAT <frmt>` | Sets output format to `1` or `2`. Format 1 (IEEE-488.2 compatible): values without units. Format 2: values with measurement unit strings (primarily for RS-232 print-only mode). |
| `FORMAT?` | Returns current format as `1` or `2`. |
| `SERIAL?` | Returns the meter's serial number. |

### Format 2 Measurement Unit Strings

| Measurement Function | Units Output |
|----------------------|--------------|
| Volts DC | `VDC` |
| Volts AC | `VAC` |
| Amps DC | `ADC` |
| Amps AC | `AAC` |
| Resistance | `OHMS` |
| Frequency | `HZ` |
| Diode/Continuity Test | `VDC` |

---

## RS-232 Remote/Local Configuration Commands

These commands are valid **only when the RS-232 interface is enabled**.

| Command | Description |
|---------|-------------|
| `REMS` | Puts meter into IEEE-488 REMS state (remote, no front-panel lockout). Display shows `REMOTE`. Pressing LOCAL returns to local control; all other front-panel buttons disabled. |
| `RWLS` | Puts meter into IEEE-488 RWLS state (remote, front-panel locked out). Display shows `REMOTE`. All front-panel buttons disabled. |
| `LOCS` | Puts meter into IEEE-488 LOCS state (local, no lockout). All front-panel buttons enabled. |
| `LWLS` | Puts meter into IEEE-488 LWLS state (local, locked out). All front-panel buttons disabled. |

---

## Service Request Enable Register (SRE)

The SRE register controls which status conditions generate a Service Request. Use `*SRE <value>` to set it and `*SRE?` to read it.

- `<value>` is an integer 0–255 whose binary equivalent maps to register bit states.
- Bit 6 is always zero (unused by the SRE register).

**Example:**

```
*SRE?   → Returns "32"
32 decimal = 00100000 binary → Bit 5 is set.
```