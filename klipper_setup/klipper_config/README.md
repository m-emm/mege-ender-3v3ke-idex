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

The clean chain starts with seed facts for the 8 mm square fiducial patch, its
printer-Z plane (`-0.6 mm`), and the bed-tab corner (`[173, -18, 0] mm`).
First select reproducible, low-glare fiducial lighting:

```gcode
IDEX_BED_FIDUCIAL_LIGHTING_CALIBRATE NAME=bed_fiducial_lighting
```

Then capture the six-frame `0, 10, 20, 20, 10, 0 mm` printer-Y sweep and
recover the local fiducial metric:

```gcode
IDEX_BED_FIDUCIAL_METRIC_CALIBRATE NAME=bed_fiducial_metric
```

Observe the bed-tab corner relative to that metric:

```gcode
IDEX_BED_TAB_CORNER_CALIBRATE NAME=bed_tab_corner
```

The coarse red-marker sweep establishes image X and both tool relations:

```gcode
IDEX_RED_MARKER_X_SWEEP_CALIBRATE NAME=red_marker_x_sweep
```

Accepted red-marker jobs publish their three coordinate facts immediately. They
do not modify `calib.yaml` or activate either tool's X endstop.

Calculate both tool X endstops independently from the fixed bed prior:

```bash
/usr/local/bin/vision_calibration.py calculate-rough-x
```

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

Stage 5 is split into independent T0 and T1 jobs. Each job captures a
28-frame nozzle grid: seven evenly spaced X columns at bed-tab offsets
`10, 12.5, 15, 17.5, 20, 22.5, 25 mm` on four complete Z rows spanning
Z 1 through 9 mm. The outer circular ring is a coarse locator. Only a small
ROI centered on the actual metallic nozzle tip contributes registration
measurements:

```gcode
IDEX_NOZZLE_FINE_XZ_CALIBRATE_T0 NAME=fine_nozzle_xz_t0
IDEX_NOZZLE_FINE_XZ_CALIBRATE_T1 NAME=fine_nozzle_xz_t1
```

Each job publishes only its own tool's nozzle-tip projection and registration
model. It deliberately does not publish absolute nozzle XYZ or infer Z by
forcing the nozzle X vector to equal the bed X vector; that solve is a
separate per-tool follow-up operation.

Stage 5.1 performs that gated calculation:

```bash
/usr/local/bin/vision_calibration.py calculate-fine-tool-xyz --tool T0
/usr/local/bin/vision_calibration.py calculate-fine-tool-xyz --tool T1
```

Each accepted calculation writes a complete `calib_candidate.yaml`, changing
only the selected tool's persisted XYZ datum, and publishes that tool's
absolute nozzle-coordinate facts plus its per-tool candidate fact. A rejected
calculation remains visible under `/vision/`, publishes nothing, and must not
be deployed. A per-tool candidate is based on the active source calibration;
after applying one candidate, recapture and recalculate the other tool rather
than applying a candidate computed against the previous source file. After
deploying an accepted candidate, verify the generated mappings by recording
the active snapshot:

```bash
/usr/local/bin/vision_calibration.py record-fine-tool-xyz-activation \
  <calculation-id> --expected-fingerprint=<active-config-fingerprint>
```

The calculation is the Stage 5.1 deployment gate. Do not deploy a rejected
candidate. The independent post-activation XYZ verification described in the
calibration concept is deliberately not exposed until its full X/Y dither and
three-row Z-scale contract is implemented; there is no legacy X/Y-only alias.

The corresponding host job types, in dependency order, are:

```text
nozzle_cam_bed_fiducial_lighting_sweep
nozzle_cam_bed_fiducial_y_metric
nozzle_cam_bed_tab_corner
idex_tool_red_marker_x_sweep
idex_rough_tool_x_verify
idex_nozzle_fine_xz_grid_t0
idex_nozzle_fine_xz_grid_t1
```

The seed values live in
`/usr/local/share/vision/vision_calibration_priors.json`. Publishing changed
prior values supersedes the old seed facts and makes downstream corner facts
stale.

Watch progress and artifacts at `http://menderpi.local/vision/`. Accepted
results publish immediately; rejected analyses publish nothing. Fiducial and
feature pixel positions are observed, never configured.

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
