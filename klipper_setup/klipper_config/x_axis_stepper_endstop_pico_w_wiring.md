# Raspberry Pi Pico W <-> BTT TMC2226 Driver Wiring (X Axis, Minimal)

This wiring matches `x_axis_stepper_endstop_pico_w.cfg`.

## 1) Signal wiring (Pico -> driver)

| Pico pin | Driver pin | Notes |
|---|---|---|
| `GP11` | `STEP` | X step pulse |
| `GP10` | `DIR` | X direction |
| `GP12` | `EN` | Driver enable (active low in config) |
| `GP9` | `UART` / `PDN_UART` | Single-wire UART control from Klipper |
| `GND` | `GND` | Common logic ground |
| `3V3(OUT)` | `VIO` | Driver logic voltage reference |

## 2) Motor and power wiring (driver side)

| Driver pin | Connect to |
|---|---|
| `A1`, `A2`, `B1`, `B2` | X motor coils |
| `VM` | Motor power supply `+` (typically 12V/24V) |
| `GND` (power side) | Motor power supply `-` |

Important: Pico ground and motor PSU ground must be common.

## 3) X endstop wiring (mechanical switch)

Use a 2-wire NO switch:
- Switch `COM` -> Pico `GND`
- Switch `NO`  -> Pico `GP4`

The config uses `endstop_pin: ^!gpio4` (pull-up + inverted) for this wiring.
If your logic is reversed, remove `!` or move to `NC`.

## 4) Klipper driver section for TMC2226

- For **TMC2226**, use `[tmc2208 stepper_x]` in Klipper.
- TMC2226 uses the same UART-style configuration family as TMC2208 in Klipper.

If you ever swap to a true TMC2209 board, switch the section to `[tmc2209 stepper_x]`.

## 5) Optional split RX/TX UART (not required for one driver)

For single-driver bring-up, one-wire `GP9 <-> UART` is simplest.
If you intentionally split RX/TX (per specific board mod docs), set:
- `uart_pin` = RX pin
- `tx_pin` = TX pin
