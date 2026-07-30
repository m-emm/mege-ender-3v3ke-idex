# Klipper Config Truth

This directory has one active printer configuration:

- `printer.cfg` is THE config for the active printer.
- `printer.cfg.template` plus `calib.yaml` generate `printer.cfg`.
- `wiring/` is THE active wiring source for the custom Pico/TMC wiring.
- `../klipper_host/` is THE active custom Klipper host patch source.
- `update_menderpi.sh` is THE script for copying it to `pi@menderpi.local`.
- `archive/` is historical/reference material only. Do not edit files there to
  change the active printer.

Check whether the generated local config is live on the printer with:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex/klipper_setup/klipper_config
./update_menderpi.sh --check
```

## Daily Workflow

Edit `calib.yaml`, `printer.cfg.template`, or active wiring YAMLs, check the
generated config and wiring consistency, then deploy when needed:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex/klipper_setup/klipper_config
python generate_printer_cfg.py --check
wiring/generate_wiring_svgs.sh --check
python wiring/validate_wiring.py
./update_menderpi.sh --check
./update_menderpi.sh
```

`update_menderpi.sh --check` verifies the generated local `printer.cfg`, the
remote `~/printer_data/config/printer.cfg`, the patched remote
`/opt/klipper/klippy/extras/heaters.py`, and the config Klippy has loaded via
Moonraker without uploading files or restarting Klipper.

`update_menderpi.sh` copies local `printer.cfg` to
`~/printer_data/config/printer.cfg` on `pi@menderpi.local`, backs up the
previous remote file with a timestamp, installs the custom Klipper host patch,
restarts Klipper, and reports the Moonraker/Klippy state.

## Vision Calibration Framework

The clean framework starts with the relative bed-tab Y/parallax job. It
resolves T0 X park, Y minimum, and Z maximum from active Klipper, then captures
six frames at Y offsets 0, 10, 20, 20, 10, and 0 mm: three forward and three
reverse.

Run it from Mainsail:

```gcode
IDEX_BED_TAB_Y_SCALE_CALIBRATE NAME=bed_tab_y_scale
```

Or from the printer:

```bash
/usr/local/bin/vision_calibration.py run nozzle_cam_bed_tab_y_scale --name bed_tab_y_scale
```

The next dependency-bound stage uses the current Y-parallax fact plus the
versioned bed-tab XYZ and tab-plane Z seed facts:

```gcode
IDEX_BED_TAB_CORNER_CALIBRATE NAME=bed_tab_corner
```

or:

```bash
/usr/local/bin/vision_calibration.py run nozzle_cam_bed_tab_corner --name bed_tab_corner
```

Run the dependency-bound coarse T0/T1 red-marker X sweep:

```gcode
IDEX_RED_MARKER_X_SWEEP_CALIBRATE NAME=red_marker_x_sweep
```

or directly on the printer host:

```bash
/usr/local/bin/vision_calibration.py run idex_tool_red_marker_x_sweep --name red_marker_x_sweep
```

Accepted red-marker jobs publish their four coordinate facts immediately. They
do not modify `calib.yaml` or activate either tool's X endstop.

The rough-X calibration sequence synchronizes the current priors, asks the
dependency graph which inputs are missing or stale, reruns only those
acquisition and analysis jobs in dependency order, publishes their accepted
facts, and calculates both tool endstops independently:

```bash
/usr/local/bin/vision_calibration.py calibrate-rough-x \
  --name rough_x_calibration
```

Pass `--force` when every acquisition stage should be repeated even if its
current facts are fresh. The sequence stores an immutable operation result with
the exact input fact bindings and candidate. It never modifies configuration.

After copying the accepted candidates into `calib.yaml`, regenerating and
deploying `printer.cfg`, record the active snapshot with the pre-calibration
values used by the candidate:

```bash
/usr/local/bin/vision_calibration.py record-rough-x-activation \
  --old-t0=-80.400 --old-t1=357.532 \
  --expected-fingerprint=<active-config-fingerprint>
```

Finally, home the printer and capture exactly one image from each tool at
X=183:

```gcode
IDEX_ROUGH_X_VERIFY NAME=rough_x_activation_verify
```

The verification expects each red marker to project 10 mm along the measured
image-X axis from the fixed bed-tab corner and expects the two marker image-X
positions to agree. It is report-only and does not change configuration.

The seed values live in
`/usr/local/share/vision/vision_calibration_priors.json`. Publishing changed
prior values supersedes the old seed facts and makes downstream corner facts
stale.

Watch preparation, frame progress, analysis, and artifacts at
`http://menderpi.local/vision/`. An accepted result creates and immediately
publishes the current `camera.nozzle_cam.bed_tab.y_parallax_model` fact.
Rejected analyses publish nothing. No pixel position or ROI is configured: the
v4 analysis discovers horizontal features in both zero-offset frames and
requires the bed-tab geometry—a horizontal top with a steep side descending to
its right. It then tracks all semantic candidates, rejects stationary enclosure
features and lower frame reflections, and selects the best moving tab top from
fit quality.

The job page makes the discovered-edge overlay and the six-frame measured-versus-
fitted overlay prominent. Yellow marks the measured seam and strip, cyan marks
the fitted model, and green/magenta distinguish forward and reverse passes. The
page also includes the raw contact sheet, displacement plot, and direction
comparison. Small fit and direction inconsistencies are warnings; a repeated
position discrepancy above 1.5 mm remains a rejection.

The `/vision/` overview shows only fields explicitly declared as
coordinate-system defining. The full current-facts report keeps diagnostic
fields such as fit quality, capture details, provenance, and artifact hashes.

Publication updates only the fact catalog. It does not edit `calib.yaml`,
restart Klipper, or activate a printer calibration.


## Boosted Heatbed

The active bed remains `[heater_bed]` for normal Klipper and UI compatibility.
The patched Klipper host code adds `boost_pin`, `primary_heater_power`, and
`boost_heater_power` support:

- `heater_pin: gpio21` drives the original 24V 240W bed MOSFET.
- `boost_pin: gpio20` drives the 230V 500W SSR boost bed.
- `pwm_cycle_time: 2.0` uses long software PWM for both outputs.

The template stays in calibration-ready `watermark` mode until measured PID
constants exist. To tune and deploy the final PID bed config while physically
supervising the printer:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex/klipper_setup/klipper_config
./calibrate_boosted_bed_pid.sh --target 80
```

No other root script or config is part of the active deployment path. The
Raspberry Pi image build also contains a minimal `files/printer.cfg` boot stub;
that file is only for first boot and is not the active printer config.

## Wiring

Active wiring lives in `wiring/`:

- `wiring/pico_w_btt_tmc2226_x.yaml`
- `wiring/pico_w_btt_tmc2226_y_z.yaml`
- `wiring/diagrams/*.svg`

The YAML files are the source for physical wiring and the SVGs are generated
review artifacts. The `klipper:` tags in the YAML are checked against
`printer.cfg.template` by `wiring/validate_wiring.py`.

## Archive

The archive contains unrelated historical/reference helpers such as resonance
plotting. Active-looking legacy wiring files, install scripts, snippets, and
bring-up configs were removed to avoid mistaken deployment paths.

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

TEST_X_TRAVEL
TEST_X_TRAVEL_ACCEL_FOURK
TEST_X_TRAVEL_ACCEL_SIXK
TEST_X_TRAVEL_ACCEL_EIGHTK
X_MOTORS_OFF
MOTORS_OFF
```

If either Z motor moves opposite the other, stop testing and fix that side's
`dir_pin` in `printer.cfg` before redeploying.
