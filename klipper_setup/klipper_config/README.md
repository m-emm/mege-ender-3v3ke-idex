# Klipper Config Truth

This directory has one active printer configuration:

- `printer.cfg` is THE config for the active printer.
- `update_menderpi.sh` is THE script for copying it to `pi@menderpi.local`.
- `archive/` is historical/reference material only. Do not edit files there to
  change the active printer.

Check whether the generated local config is live on the printer with:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex/klipper_setup/klipper_config
./update_menderpi.sh --check
```

## Daily Workflow

Edit `calib.yaml` or `printer.cfg.template`, check the live printer config, then
deploy when needed:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex/klipper_setup/klipper_config
./update_menderpi.sh --check
./update_menderpi.sh
```

`update_menderpi.sh --check` verifies the generated local `printer.cfg`, the
remote `~/printer_data/config/printer.cfg`, and the config Klippy has loaded via
Moonraker without uploading files or restarting Klipper.

`update_menderpi.sh` copies local `printer.cfg` to
`~/printer_data/config/printer.cfg` on `pi@menderpi.local`, backs up the
previous remote file with a timestamp, restarts Klipper, and reports the
Moonraker/Klippy state.

No other root script or config is part of the active deployment path.

## Archive

The archive contains old bring-up configs, retired install scripts, snippets,
wiring notes/diagrams, and resonance plotting helpers. Keep them for reference,
but treat them as inactive unless they are deliberately restored into the root
workflow.

## Useful Console Commands

Run these from Mainsail/Klipper while working with the active config:

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

If either Z motor moves opposite the other, stop testing and fix that side's
`dir_pin` in `printer.cfg` before redeploying.
