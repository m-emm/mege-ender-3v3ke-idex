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
- `pico_w_btt_tmc2226_y_z_bringup.cfg` is the current Y + dual-Z temporary
  `printer.cfg`.
- `toolhead_nitehawk_and_x_axis.cfg` is the fuller printer config kept for
  later integration.
- `y_z_dual_endstop_heatbed_pico_w.cfg` is a future include-style snippet, not
  the current live bring-up config.

The Y + dual-Z bring-up config intentionally does not home Z. It only enables
small synchronized Z moves and lets the Z endstops be tested by hand.

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

## Y + Dual-Z Debug Commands

Run these from the Mainsail/Klipper console:

```gcode
Y_TEST_ENABLE
Y_TEST_BUZZ
Y_TEST_HOME
Y_TEST_DISABLE

Z_TEST_QUERY_ENDSTOPS
Z_TEST_WAIT_ENDSTOP SIDE=LEFT
Z_TEST_WAIT_ENDSTOP SIDE=RIGHT
Z_TEST_WAIT_ENDSTOP SIDE=BOTH

Z_TEST_ENABLE
Z_TEST_MOVE DIST=1
Z_TEST_BUZZ
Z_TEST_MOVE DIST=0
Z_TEST_DISABLE
```

`Z_TEST_MOVE` rejects any absolute `DIST` over `3` mm. Both Z motors are always
commanded together: the left move is queued with `SYNC=0`, then the right move
is queued and waited on, causing both sides to move at the same time.

If either Z motor moves opposite the other, stop testing and invert that side's
`dir_pin` in `pico_w_btt_tmc2226_y_z_bringup.cfg` before redeploying.
