# Raspberry Pi Pico W <-> BTT TMC2226 Wiring (X Axis MCU)

This wiring matches `pico_w_btt_tmc2226_x.yaml`, the generated SVGs under
`wiring_diagrams/`, and `snippets/x_axis_stepper_endstop_pico_w.cfg`.

## GPIO Map

| Function | Pico GPIO | Notes |
|---|---:|---|
| X-left STEP | `GP11` | Active `stepper_x` driver |
| X-left DIR | `GP10` | Inverted in config |
| X-left EN | `GP12` | Active low |
| X-left UART | `GP9` | Single-wire UART |
| X-left endstop | `GP4` | `^!gpio4` NO switch wiring |
| X-right STEP | `GP7` | Commented `[dual_carriage]` template |
| X-right DIR | `GP6` | Inverted in template |
| X-right EN | `GP8` | Active low |
| X-right UART | `GP5` | Single-wire UART |
| X-right endstop | `GP22` | `^!gpio22` template |
| Left SFS V2.0 switch | `GP0` | Runout switch output |
| Left SFS V2.0 motion | `GP1` | Encoder/motion output |
| Right SFS V2.0 switch | `GP2` | Runout switch output |
| Right SFS V2.0 motion | `GP3` | Encoder/motion output |
| CR Touch control | `GP13` | BLTouch-compatible servo/control pin |
| CR Touch Z signal | `GP14` | Open-drain output; `^gpio14` enables the Pico pull-up |

## Driver Wiring

Each BTT TMC2226 V1.0 driver is wired the same way:

| Driver pin | Connect to |
|---|---|
| `VM` | Motor PSU positive, typically 24V |
| `GND` motor side | Motor PSU ground |
| `VIO` | Pico `3V3(OUT)` |
| `GND` logic side | Pico/common ground |
| `EN` | Driver enable GPIO, plus 10K pull-up to `VIO` |
| `STEP` | Driver STEP GPIO |
| `DIR` | Driver DIR GPIO |
| `UART` / `PDN_UART` | Driver UART GPIO |
| `A1`, `A2`, `B1`, `B2` | Matching X motor coils |

Important: Pico ground, driver logic ground, motor PSU ground, endstop ground,
SFS ground, and CR Touch ground must be common.

## Connectors

### X-left motor and endstop

| Connector pin | Connect to |
|---|---|
| `X_LEFT_MOTOR_A_PLUS` | TMC1 `A1` |
| `X_LEFT_MOTOR_A_MINUS` | TMC1 `A2` |
| `X_LEFT_MOTOR_B_PLUS` | TMC1 `B1` |
| `X_LEFT_MOTOR_B_MINUS` | TMC1 `B2` |
| `X_LEFT_ENDSTOP_NO` | Pico `GP4` |
| `X_LEFT_ENDSTOP_GND` | Common ground |
| `X_LEFT_ENDSTOP_VCC` | Pico `3V3(OUT)` if using a 3-wire endstop board |

### X-right motor and endstop

| Connector pin | Connect to |
|---|---|
| `X_RIGHT_MOTOR_A_PLUS` | TMC2 `A1` |
| `X_RIGHT_MOTOR_A_MINUS` | TMC2 `A2` |
| `X_RIGHT_MOTOR_B_PLUS` | TMC2 `B1` |
| `X_RIGHT_MOTOR_B_MINUS` | TMC2 `B2` |
| `X_RIGHT_ENDSTOP_NO` | Pico `GP22` |
| `X_RIGHT_ENDSTOP_GND` | Common ground |
| `X_RIGHT_ENDSTOP_VCC` | Pico `3V3(OUT)` if using a 3-wire endstop board |

## BTT Smart Filament Sensor V2.0

Power both sensors from Pico `3V3(OUT)` and common ground. The SFS V2.0 supports
3.3V to 5V operation, and using 3.3V keeps both outputs Pico-safe.

| Sensor pin | Connect to |
|---|---|
| Left `SWITCH` | Pico `GP0` |
| Left `MOTION` | Pico `GP1` |
| Left `VCC` | Pico `3V3(OUT)` |
| Left `GND` | Common ground |
| Right `SWITCH` | Pico `GP2` |
| Right `MOTION` | Pico `GP3` |
| Right `VCC` | Pico `3V3(OUT)` |
| Right `GND` | Common ground |

The config file includes commented templates for both Klipper sensor types:
`[filament_switch_sensor]` for runout and `[filament_motion_sensor]` for encoder
movement. Enable them only after the matching extruder names are final.

## CR Touch

Treat the CR Touch as BLTouch-compatible in Klipper:

| CR Touch signal | Connect to |
|---|---|
| `GND` | Common ground |
| `5V` | Pico `VBUS` or a regulated 5V rail |
| `CONTROL` | Pico `GP13` |
| `Z_GND` | Common ground |
| `Z_SIGNAL` | Pico `GP14` directly, using the internal pull-up |

The CR Touch still needs 5V power, but its Z signal is an open-drain output and is
safe for the Pico when pulled up to 3.3V. Use `sensor_pin: ^gpio14` so Klipper
enables the RP2040 internal pull-up. No external pull-up should be needed for
first bring-up; add one to 3.3V only if the signal is noisy or unreliable.

The `[bltouch]` template in `snippets/x_axis_stepper_endstop_pico_w.cfg` is
commented until the probe is physically moved to this MCU and its offsets are
measured.

## Config Notes

- The active X-left driver remains `[stepper_x]` plus `[tmc2209 stepper_x]`.
- BTT TMC2226 V1.0 is configured through the `tmc2209` section used by this repo.
- X-right wiring is present in the SVG and config template as `[dual_carriage]`,
  but should stay commented until the IDEX limits and kinematics are finished.
- The SFS and CR Touch snippets are intentionally commented so this include can be
  used for motor bring-up without requiring unfinished extruder/probe setup.
