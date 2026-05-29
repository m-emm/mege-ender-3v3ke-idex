# Klipper Configuration Bring-Up

This directory holds the temporary and production-facing Klipper configuration
pieces for the Ender 3V3 KE IDEX conversion. During bring-up, the files here are
treated as the source of truth and are transported to the Raspberry Pi through
git.

## Source Flow

The wiring starts in YAML:

- `pico_w_btt_tmc2226_y_z.yaml` describes Pico W, TMC2226 driver, motor,
  endstop, heatbed, and thermistor pins.
- `generate_wiring_svgs.sh` renders the YAML into top and bottom wiring SVGs.
- The generated `*_wiring.md` notes summarize the human-readable wiring plan.
- The Klipper `.cfg` files map those same GPIO choices into stepper, TMC, and
  debug macro sections.

Regenerate the wiring diagrams after changing YAML pin assignments:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex
./klipper_setup/klipper_config/generate_wiring_svgs.sh \
  klipper_setup/klipper_config/pico_w_btt_tmc2226_y_z.yaml
```

## Bring-Up Configs

- `pico_w_btt_tmc2226_y_axis_bringup.cfg` is the older Y-only temporary
  `printer.cfg`.
- `pico_w_btt_tmc2226_y_z_bringup.cfg` is the current temporary real-kinematics
  Y + dual-Z `printer.cfg`.
- `toolhead_nitehawk_and_x_axis.cfg` is the fuller printer config kept for
  later integration.
- `y_z_dual_endstop_heatbed_pico_w.cfg` is a future include-style snippet, not
  the current live bring-up config.

The Y + dual-Z config uses normal `cartesian` kinematics so Mainsail and
KlipperScreen can use standard `G28` homing. There is no physical X axis during
this stage, so `stepper_x` is a placeholder on unused Pico pins and the homing
override marks X homed without movement.

## Local Git Workflow

Only committed and pushed changes can be pulled by the Raspberry Pi:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex
git status --short
git add klipper_setup/klipper_config
git commit -m "Add Y dual-Z Pico bring-up config"
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

## Y + Dual-Z Homing

Run these from the Mainsail/Klipper console:

```gcode
QUERY_ENDSTOPS
YZ_QUERY_ENDSTOPS

G28 Y
G28 Z
G28

Y_TEST_TRAVEL_100
Y_TEST_TRAVEL_100_AUDACIOUS
MOTORS_OFF
```

`G28 Y` homes the real Y axis to the back-mounted min-Y endstop, sets Y to
`0`, and uses a configured Y travel range of `0..310`. `G28 Z` homes both Z
motors upward to their top-mounted independent left/right endstops and sets Z
to `290`. `G28` or "home all" marks the placeholder X as homed, then homes Y
and Z. `G28 X` only marks the placeholder X homed and does not command physical
motion.

`Y_TEST_TRAVEL_100` requires Y to be homed. It picks a safe 100 mm direction
from the current Y position, temporarily sets `550` mm/s velocity, `8000`
mm/s^2 acceleration, and `11` mm/s square-corner velocity, then runs three
out-and-back cycles. It then moves to the farther test position and performs a
slow `G28 Y` verification pass, so the hardware Y endstop stops the final move
back to the rear. Klipper macros can safely use that homing stop and will error
if the endstop is not found, but they do not expose enough trigger-distance data
to automatically flag an early trigger as lost steps.

`Y_TEST_TRAVEL_100_AUDACIOUS` uses the same path and verification pass, but
raises the acceleration to `9500` mm/s^2. Both Y travel-test macros use the
configured Y driver current of `1.7` A.

If either Z motor moves opposite the other, stop testing and invert that side's
`dir_pin` in `pico_w_btt_tmc2226_y_z_bringup.cfg` before redeploying.
