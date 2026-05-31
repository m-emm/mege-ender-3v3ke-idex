# Klipper Configuration Bring-Up

This directory holds the temporary and production-facing Klipper configuration
pieces for the Ender 3V3 KE IDEX conversion. During bring-up, the files here are
treated as the source of truth and are transported to the Raspberry Pi through
git.

## Source Flow

The wiring starts in YAML:

- `pico_w_btt_tmc2226_x.yaml` describes the X-axis Pico W, TMC2226 drivers,
  endstops, Smart Filament Sensors, and CR Touch pins.
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
- `pico_w_btt_tmc2226_y_z_bringup.cfg` is the current temporary real-kinematics
  right-X + Y + dual-Z `printer.cfg`.
- `toolhead_nitehawk_and_x_axis.cfg` is the fuller printer config kept for
  later integration.
- `snippets/x_axis_stepper_endstop_pico_w.cfg` and
  `snippets/y_z_dual_endstop_heatbed_pico_w.cfg` are include-style snippets, not
  the current live bring-up config.

The right-X + Y + dual-Z config uses normal `cartesian` kinematics so Mainsail
and KlipperScreen can use standard `G28` homing and GUI jogging. The right IDEX
carriage is temporarily exposed as `stepper_x` with travel `X40..X340` and the
right endstop at `X340`. The left IDEX carriage remains a manual stepper until
its endstop mechanics are fixed; full Klipper `dual_carriage` mode is deferred
until both carriages can home safely.

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

## Right-X + Y + Dual-Z Homing

Run these from the Mainsail/Klipper console:

```gcode
QUERY_ENDSTOPS
YZ_QUERY_ENDSTOPS
X_QUERY_ENDSTOPS
X_WAIT_LEFT_ENDSTOP
X_WAIT_RIGHT_ENDSTOP
X_WAIT_BOTH_ENDSTOPS
X_CANCEL_ENDSTOP_WAIT
CR_TOUCH_QUERY
CR_TOUCH_DEPLOY
CR_TOUCH_DEPLOY_650
CR_TOUCH_DEPLOY_750
CR_TOUCH_DEPLOY_900
CR_TOUCH_DEPLOY_1000
CR_TOUCH_TOUCH_MODE
CR_TOUCH_STOW
CR_TOUCH_RESET
CR_TOUCH_SELF_TEST
CR_TOUCH_WAIT_TRIGGER
CR_TOUCH_CANCEL_WAIT

G28 Y
G28 Z
G28

Y_TEST_TRAVEL_100
Y_TEST_TRAVEL_100_AUDACIOUS
MOTORS_OFF
```

`G28 X` homes the real right IDEX carriage to the right-mounted endstop, sets X
to `340`, and uses a temporary safe range of `40..340`. Stay above `X40` until
the current left-carriage collision risk is mechanically fixed. `G28 Y` homes
the real Y axis to the back-mounted min-Y endstop, sets Y to `0`, and uses a
configured Y travel range of `0..310`. `G28 Z` homes both Z motors upward to
their top-mounted independent left/right endstops and sets Z to `295`. `G28` or
"home all" homes right-X first, then Y and Z.

The X endstop macros remain bring-up buttons for the separate X Pico. The left
switch uses `x_pico:gpio4` and remains registered as `manual_stepper x_left`.
The right switch uses `x_pico:gpio22` and is now registered as `stepper_x`.
Both are NC-to-ground contacts with internal pull-ups. `X_WAIT_LEFT_ENDSTOP`,
`X_WAIT_RIGHT_ENDSTOP`, and `X_WAIT_BOTH_ENDSTOPS` poll `QUERY_ENDSTOPS` until
the requested switch or switches report triggered, then show the result with
`RESPOND` and `M117`. Use `X_CANCEL_ENDSTOP_WAIT` to stop an active wait.

The CR Touch is in temporary raw-pulse bring-up mode on the X Pico:
`CONTROL=x_pico:gpio13`, `Z_SIGNAL=^x_pico:gpio14`. It is not used by Z
homing, bed mesh, safe-Z-home, or any automatic movement. The built-in
`[bltouch]` `pin_down` path alarmed the probe during bring-up, while a raw
650us PWM deploy pulse worked. The raw test buttons send 20 ms servo pulses
directly so deploy behavior can be tested without using the probe for motion:
`CR_TOUCH_DEPLOY_650`, `CR_TOUCH_DEPLOY_750`, `CR_TOUCH_DEPLOY_900`, and
`CR_TOUCH_DEPLOY_1000`. `CR_TOUCH_STOW`, `CR_TOUCH_RESET`,
`CR_TOUCH_SELF_TEST`, `CR_TOUCH_TOUCH_MODE`, and `CR_TOUCH_QUERY` use the same
raw-control path. Once the normal BLTouch path is understood, switch this back
to `[bltouch]` before using the probe for actual probing.

### CR Touch Bring-Up Log, 2026-05-31

Known wiring during the test:

- CR Touch control/servo wire: `x_pico:gpio13`
- CR Touch Z signal wire: `^x_pico:gpio14`
- CR Touch powered from 5V, with signal/common ground tied to the Pico/common
  printer ground
- Klipper query object in raw mode: `gcode_button cr_touch_signal`

Observed behavior:

- `CR_TOUCH_QUERY` reported `open` when the probe was stowed and calm.
- Klipper's built-in `[bltouch]` `BLTOUCH_DEBUG COMMAND=pin_down` repeatedly
  put the probe into red error mode instead of reliably deploying it.
- Increasing the BLTouch `pin_move_time` did not fix that built-in `pin_down`
  failure.
- `BLTOUCH_DEBUG COMMAND=self_test` did move the pin during one test, and
  `reset` plus `stow` could recover the probe to an open signal state.
- Raw PWM control proved the control pin is alive: a 650us pulse at 20ms servo
  period deployed the pin once, with the probe LED changing to blue.
- A clean raw deploy-only test showed the signal transition from `RELEASED` to
  `PRESSED`, then a reset+stow command returned Klipper's signal query to
  `RELEASED/open`.
- The first implementation of `CR_TOUCH_WAIT_TRIGGER` was too eager because it
  called `CR_TOUCH_TOUCH_MODE` immediately after deploy. That made the wait
  report `TRIGGERED` instantly, so the source config now polls the raw signal
  directly after deploy instead.
- End-of-session physical state: after another manual test, the user observed
  the probe in error mode again and shut the printer down. Do not assume the
  probe recovered physically just because the last successful Klipper query from
  earlier had shown `open`.

Resume checklist:

1. Power the printer back on and do not run any deploy command first.
2. Run `CR_TOUCH_RESET`, then `CR_TOUCH_STOW`, then `CR_TOUCH_QUERY`.
3. Confirm physically that the probe is stowed and not blinking red.
4. Redeploy this local source config before using `CR_TOUCH_WAIT_TRIGGER`; the
   live printer may still have the older wait macro that used touch-mode.
5. For the next controlled test, prefer `CR_TOUCH_DEPLOY_650`, visually confirm
   the pin deployed, then manually query or poll `cr_touch_signal` before
   touching the pin.
6. Keep the CR Touch disconnected from all homing/probing features until the
   deploy, trigger, reset, and stow sequence is repeatable.

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
