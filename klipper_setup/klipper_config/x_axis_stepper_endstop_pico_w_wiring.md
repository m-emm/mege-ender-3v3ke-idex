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
| X-left endstop | `GP4` | `^gpio4` NC switch wiring |
| X-right STEP | `GP7` | Commented `[dual_carriage]` template |
| X-right DIR | `GP6` | Inverted in template |
| X-right EN | `GP8` | Active low |
| X-right UART | `GP5` | Single-wire UART |
| X-right endstop | `GP22` | `^gpio22` NC switch template |
| Left SFS V2.0 switch | `GP0` | Runout switch output |
| Left SFS V2.0 motion | `GP1` | Encoder/motion output |
| Right SFS V2.0 switch | `GP2` | Runout switch output |
| Right SFS V2.0 motion | `GP3` | Encoder/motion output |
| CR Touch control | `GP13` | Wiring retained; not configured in Klipper |
| CR Touch Z signal | `GP14` | Wiring retained; not configured in Klipper |

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

The X endstops use normally-closed switch wiring: switch `COM` goes to common
ground and switch `NC` goes to the Pico input. Klipper enables the Pico internal
pull-up with `^`, so a pressed switch or broken wire reads as triggered. Do not
route `3V3` through the bare switch contact.

## Connectors

### X-left motor and endstop

| Connector pin | Connect to |
|---|---|
| `X_LEFT_MOTOR_A_PLUS` | TMC1 `A1` |
| `X_LEFT_MOTOR_A_MINUS` | TMC1 `A2` |
| `X_LEFT_MOTOR_B_PLUS` | TMC1 `B1` |
| `X_LEFT_MOTOR_B_MINUS` | TMC1 `B2` |
| `X_LEFT_ENDSTOP_NC` | Pico `GP4` |
| `X_LEFT_ENDSTOP_GND` | Common ground / switch `COM` |
| `X_LEFT_ENDSTOP_VCC` | Unused for a bare NC microswitch |

### X-right motor and endstop

| Connector pin | Connect to |
|---|---|
| `X_RIGHT_MOTOR_A_PLUS` | TMC2 `A1` |
| `X_RIGHT_MOTOR_A_MINUS` | TMC2 `A2` |
| `X_RIGHT_MOTOR_B_PLUS` | TMC2 `B1` |
| `X_RIGHT_MOTOR_B_MINUS` | TMC2 `B2` |
| `X_RIGHT_ENDSTOP_NC` | Pico `GP22` |
| `X_RIGHT_ENDSTOP_GND` | Common ground / switch `COM` |
| `X_RIGHT_ENDSTOP_VCC` | Unused for a bare NC microswitch |

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

## CR Touch Wiring

The physical CR Touch wiring is retained for now, but the current Klipper
configuration intentionally provides no probe, button, or output-pin section for
it:

| CR Touch signal | Connect to |
|---|---|
| `GND` | Common ground |
| `5V` | Pico `VBUS` or a regulated 5V rail |
| `CONTROL` | Pico `GP13` |
| `Z_GND` | Common ground |
| `Z_SIGNAL` | Pico `GP14` directly, using the internal pull-up |

The CR Touch still needs 5V power, but its signal line is open-drain and should
remain Pico-safe when pulled to 3.3V. This wiring is documentation only; do not
expect CR Touch commands, status buttons, homing, or automatic probing in the
current printer config.

## Config Notes

- The live bring-up config maps X-left to `[stepper_x]` and X-right to
  `[dual_carriage]`.
- BTT TMC2226 V1.0 is configured through the `tmc2209` section used by this repo.
- The SFS snippets are intentionally commented so this include can be used for
  motor bring-up without requiring unfinished extruder setup.
