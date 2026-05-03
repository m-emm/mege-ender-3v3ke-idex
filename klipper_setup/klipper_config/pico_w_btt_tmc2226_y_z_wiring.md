# Raspberry Pi Pico W <-> BTT TMC2226 Driver Wiring (Y + Dual Z)

This wiring note describes a Pico W carrier that drives:

- one Y-axis motor
- one left Z motor
- one right Z motor

The pin choices stay close to the existing X-axis bring-up wiring so the harness is easy to reason about and the remaining Pico GPIOs stay available for other printer functions.

## GPIO grouping

The three drivers use three simple 4-signal groups:

| Function | Driver | STEP | DIR | EN | UART |
|---|---|---|---|---|---|
| Y axis | Driver 1 | `GP11` | `GP10` | `GP12` | `GP9` |
| Z left | Driver 2 | `GP7` | `GP6` | `GP8` | `GP5` |
| Z right | Driver 3 | `GP14` | `GP15` | `GP16` | `GP13` |

Why this layout:

- Driver 1 reuses the proven X-axis pin block from the current repo wiring.
- Driver 2 reuses the second already-established 4-pin block.
- Driver 3 uses the next free GPIO block without touching ADC pins, `RUN`, USB power pins, or the higher GPIOs that are often useful later for heaters, fans, probes, or other IO.

## Endstop and signal plan

Suggested auxiliary signal pins:

| Signal | Pico pin | Intended use |
|---|---|---|
| Y endstop | `GP4` | Mechanical Y endstop input |
| Z left endstop | `GP22` | Left Z endstop input |
| Z right endstop | `GP17` | Right Z endstop input |

## Shared power and logic wiring

For each TMC2226 module:

- `VIO` -> Pico `3V3(OUT)`
- `GND_LOGIC` -> Pico ground
- `VM` -> motor supply positive (typically 24V)
- `GND_MOTOR` -> motor supply ground
- `EN` also gets a `10k` pull-up to `VIO`

Important:

- Pico ground and the motor PSU ground must be common.
- Each motor keeps its own four coil wires on its own driver output.
- The two Z motors are electrically independent because they use two drivers, which keeps them compatible with dual-Z stepper configuration in Klipper.
- The two Z endstops are also electrically independent, with one signal line per side.

## Klipper mapping summary

Expected stepper sections from this wiring:

| Axis | STEP | DIR | EN | UART |
|---|---|---|---|---|
| `stepper_y` | `gpio11` | `gpio10` | `gpio12` | `gpio9` |
| `stepper_z` | `gpio7` | `gpio6` | `gpio8` | `gpio5` |
| `stepper_z1` | `gpio14` | `gpio15` | `gpio16` | `gpio13` |

Use inverted `dir_pin` or `enable_pin` in Klipper only if the final hardware motion direction requires it.