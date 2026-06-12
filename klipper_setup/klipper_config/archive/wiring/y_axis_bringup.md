# Y-Axis Pico Bring-Up

This is a temporary, non-printing Klipper configuration for testing the rewired
Pico W controller as a Y-axis controller. It enables only the Y driver and Y
endstop from `pico_w_btt_tmc2226_y_z.yaml`.

The previous full config, `toolhead_nitehawk_and_x_axis.cfg`, remains untouched
in git for later use. The installer also backs up the live Raspberry Pi
`printer.cfg` before replacing it.

## Files

- `pico_w_btt_tmc2226_y_axis_bringup.cfg` - deploys as `printer.cfg` for Y-only testing.
- `install_y_axis_bringup_cfg.sh` - copies the bring-up config into `~/printer_data/config/printer.cfg`.
- `pico_w_btt_tmc2226_y_z.yaml` - wiring source of truth for the Y, future Z, and future bed pins.

## Before Fetching on the Pi

Only committed and pushed changes can be fetched by the Raspberry Pi. From the
local development machine:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex
git status --short
git add klipper_setup/klipper_config/pico_w_btt_tmc2226_y_axis_bringup.cfg \
        klipper_setup/klipper_config/install_y_axis_bringup_cfg.sh \
        klipper_setup/klipper_config/y_axis_bringup.md
git commit -m "Add Y-axis Pico bring-up config"
git push origin main
```

## Fetch and Deploy on the Raspberry Pi

If the repository already exists on the Klipper Raspberry Pi:

```bash
ssh pi@menderpi.local
cd ~/mege-ender-3v3ke-idex
git fetch origin
git switch main
git pull --ff-only origin main
./klipper_setup/klipper_config/install_y_axis_bringup_cfg.sh
sudo systemctl restart klipper
tail -f ~/printer_data/logs/klippy.log
```

If the repository is not on the Pi yet, clone it first:

```bash
ssh pi@menderpi.local
git clone git@github.com:m-emm/mege-ender-3v3ke-idex.git ~/mege-ender-3v3ke-idex
# Or, if SSH keys are not configured:
# git clone https://github.com/m-emm/mege-ender-3v3ke-idex.git ~/mege-ender-3v3ke-idex
cd ~/mege-ender-3v3ke-idex
./klipper_setup/klipper_config/install_y_axis_bringup_cfg.sh
sudo systemctl restart klipper
```

## Test Procedure

Run these commands from the Mainsail/Klipper console:

```gcode
Y_TEST_ENABLE
Y_TEST_BUZZ
Y_TEST_HOME
Y_TEST_DISABLE
```

`Y_TEST_BUZZ` moves the motor a short distance out and back. `Y_TEST_HOME`
moves toward the Y endstop. Stop immediately if it moves away from the endstop;
then invert the direction in `dir_pin` and redeploy before trying again.

## Active Pins

| Function | Pico GPIO |
|---|---|
| Y STEP | `gpio11` |
| Y DIR | `gpio10` |
| Y EN | `gpio12` |
| Y UART | `gpio9` |
| Y endstop | `gpio4` |

Future wiring from `pico_w_btt_tmc2226_y_z.yaml` is documented in the config but
left inactive until the hardware is connected.
