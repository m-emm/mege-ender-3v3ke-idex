# Klipper Config Truth

This directory has one active printer configuration:

- `printer.cfg` is THE config for the active printer.
- `update_menderpi.sh` is THE script for copying it to `pi@menderpi.local`.
- `archive/` is historical/reference material only. Do not edit files there to
  change the active printer.

Verify local and remote config hashes with:

```bash
shasum -a 256 klipper_setup/klipper_config/printer.cfg
ssh pi@menderpi.local 'sha256sum ~/printer_data/config/printer.cfg'
```

## Daily Workflow

Edit `printer.cfg`, then deploy it:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex/klipper_setup/klipper_config
./update_menderpi.sh
```

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
