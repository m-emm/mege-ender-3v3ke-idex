# Klipper Configuration Bring-Up

This directory holds the temporary and production-facing Klipper configuration
pieces for the Ender 3V3 KE IDEX conversion. During bring-up, the files here are
treated as the source of truth and are transported to the Raspberry Pi through
git.

## Source Flow

The wiring starts in YAML:

- `pico_w_btt_tmc2226_x.yaml` describes the X-axis Pico W, TMC2226 drivers,
  endstops, Smart Filament Sensor pins, and retained auxiliary wiring.
- `pico_w_btt_tmc2226_y_z.yaml` describes Pico W, TMC2226 driver, motor,
  endstop, heatbed, and thermistor pins.
- `generate_wiring_svgs.sh` renders the X and Y/Z YAML files into top and
  bottom wiring SVGs under `wiring_diagrams/`.
- The generated `*_wiring.md` notes summarize the human-readable wiring plan.
- Include-style snippets live under `snippets/`; deployable bring-up and full
  Klipper `.cfg` files stay in this directory.

Regenerate the wiring diagrams after changing YAML pin assignments:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex
./klipper_setup/klipper_config/generate_wiring_svgs.sh
```

## Bring-Up Configs

- `pico_w_btt_tmc2226_y_axis_bringup.cfg` is the older Y-only temporary
  `printer.cfg`.
- `pico_w_btt_tmc2226_y_z_bringup.cfg` is the current conservative IDEX
  motion-first `printer.cfg`: X-left is `[stepper_x]`, X-right is
  `[dual_carriage]`, Y plus independent dual-Z are real Klipper axes, and the
  heatbed is enabled through the Y/Z Pico MOSFET on `gpio21` with a 100k B3950
  NTC on `gpio26` / ADC0. It also brings up the left Nitehawk toolhead board
  with the calibrated left hotend/extruder.
- `toolhead_nitehawk_and_x_axis.cfg` is the fuller printer config kept for
  later integration.
- `snippets/x_axis_stepper_endstop_pico_w.cfg` and
  `snippets/y_z_dual_endstop_heatbed_pico_w.cfg` are include-style snippets, not
  the current live bring-up config.

The IDEX motion config uses normal `cartesian` kinematics with Klipper
`[dual_carriage]` support so Mainsail and KlipperScreen can use standard `G28`
homing and GUI jogging. X-left is carriage 0 with provisional travel `X0..X300`;
X-right is carriage 1 with provisional travel `X15..X340`; Klipper enforces a
temporary `10` mm safe distance between them. Toolchanging, copy mode, mirror
mode, and the second extruder remain deferred. The heatbed uses Klipper
`sensor_type: Generic 3950` for the known 100k B3950 NTC. The left toolhead
uses the Nitehawk by-id path `usb-Klipper_rp2040_30333938340637C1-if00` and
the Micro Swiss calibrated thermistor values from
`toolhead_nitehawk_and_x_axis.cfg`.

## Local Git Workflow

Only committed and pushed changes can be pulled by the Raspberry Pi:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex
git status --short
git add klipper_setup/klipper_config
git commit -m "Configure motion-first IDEX Klipper bring-up"
git push origin main
```

## Raspberry Pi Deployment

The printer host is reachable as:

```bash
ssh pi@menderpi.local
```

One-time clone, if the repo is not already present on the Pi:

```bash
ssh pi@menderpi.local
git clone git@github.com:m-emm/mege-ender-3v3ke-idex.git ~/mege-ender-3v3ke-idex
# If SSH keys are not configured on the Pi:
# git clone https://github.com/m-emm/mege-ender-3v3ke-idex.git ~/mege-ender-3v3ke-idex
```

Normal update and install flow:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex/klipper_setup/klipper_config
./update_menderpi.sh
```

`update_menderpi.sh` copies the current local
`pico_w_btt_tmc2226_y_z_bringup.cfg` to `pi@menderpi.local`, backs up the live
`~/printer_data/config/printer.cfg`, installs the new config, restarts Klipper,
and reports the Klippy state through Moonraker. This is the fastest bring-up
path while the Raspberry Pi does not have a local checkout of this repository.

If the repository is later cloned on the Pi, the equivalent Git-based flow is:

```bash
ssh pi@menderpi.local
cd ~/mege-ender-3v3ke-idex
git fetch origin
git switch main
git pull --ff-only origin main
./klipper_setup/klipper_config/install_y_z_bringup_cfg.sh
sudo systemctl restart klipper
tail -f ~/printer_data/logs/klippy.log
```

## IDEX Motion Homing

Run these from the Mainsail/Klipper console:

```gcode
QUERY_ENDSTOPS
YZ_QUERY_ENDSTOPS
X_QUERY_ENDSTOPS
X_WAIT_LEFT_ENDSTOP
X_WAIT_RIGHT_ENDSTOP
X_WAIT_BOTH_ENDSTOPS
X_CANCEL_ENDSTOP_WAIT
IDEX_HOME_X
IDEX_SELECT_LEFT
IDEX_SELECT_RIGHT

G28 X
G28 Y
G28 Z
G28

Y_TEST_TRAVEL_100
X_MOTORS_OFF
MOTORS_OFF
```

`G28 X` homes both IDEX carriages: X-left homes to the left-mounted endstop at
`X0`, and X-right homes to the right-mounted endstop at `X340`. `IDEX_HOME_X`
runs `G28 X`, parks X-right, and leaves X-left active. `IDEX_SELECT_LEFT` parks
X-right and activates X-left; `IDEX_SELECT_RIGHT` parks X-left and activates
X-right. Both selection macros require X to be homed first.

`G28 Y` homes the real Y axis to the back-mounted min-Y endstop, sets Y to `0`,
and uses a configured Y travel range of `0..310`. `G28 Z` homes both Z motors
upward to their top-mounted independent left/right endstops and sets Z to
`295`. `G28` or "home all" homes both X carriages first, then Y and Z.

The X endstop macros remain bring-up buttons for the separate X Pico. The left
switch uses `x_pico:gpio4` and is registered as `stepper_x`. The right switch
uses `x_pico:gpio22` and is registered as `dual_carriage`. Both are
NC-to-ground contacts with internal pull-ups. `X_WAIT_LEFT_ENDSTOP`,
`X_WAIT_RIGHT_ENDSTOP`, and `X_WAIT_BOTH_ENDSTOPS` poll `QUERY_ENDSTOPS` until
the requested switch or switches report triggered, then show the result with
`RESPOND` and `M117`. Use `X_CANCEL_ENDSTOP_WAIT` to stop an active wait.

`Y_TEST_TRAVEL_100` requires Y to be homed. It picks a safe 100 mm direction
from the current Y position, temporarily sets `550` mm/s velocity, `4500`
mm/s^2 acceleration, and `11` mm/s square-corner velocity, then runs three
out-and-back cycles. It then moves to the farther test position and performs a
slow `G28 Y` verification pass, so the hardware Y endstop stops the final move
back to the rear. Klipper macros can safely use that homing stop and will error
if the endstop is not found, but they do not expose enough trigger-distance data
to automatically flag an early trigger as lost steps.

If either Z motor moves opposite the other, stop testing and invert that side's
`dir_pin` in `pico_w_btt_tmc2226_y_z_bringup.cfg` before redeploying.
