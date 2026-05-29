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
ssh pi@menderpi.local
cd ~/mege-ender-3v3ke-idex
git fetch origin
git switch main
git pull --ff-only origin main
./klipper_setup/klipper_config/install_y_z_bringup_cfg.sh
sudo systemctl restart klipper
tail -f ~/printer_data/logs/klippy.log
```

The installer backs up the current live `~/printer_data/config/printer.cfg`
before replacing it.

## Y + Dual-Z Homing

Run these from the Mainsail/Klipper console:

```gcode
QUERY_ENDSTOPS
YZ_QUERY_ENDSTOPS

G28 Y
G28 Z
G28

MOTORS_OFF
```

`G28 Y` homes the real Y axis. `G28 Z` homes both Z motors upward to their
top-mounted independent left/right endstops and sets Z to `250`. `G28` or
"home all" marks the placeholder X as homed, then homes Y and Z. `G28 X` only
marks the placeholder X homed and does not command physical motion.

If either Z motor moves opposite the other, stop testing and invert that side's
`dir_pin` in `pico_w_btt_tmc2226_y_z_bringup.cfg` before redeploying.
