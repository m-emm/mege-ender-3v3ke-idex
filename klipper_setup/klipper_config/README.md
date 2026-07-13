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

## Nozzle Camera Bed Y Sweep

`nozzle_cam_bed_y_sweep` is a report-only first-stage vision job. It moves the
printer Y axis away from the endstop and measures how fixed bed/fixture features
move in nozzle-camera image space. It does not update `calib.yaml` and it does
not solve nozzle Z height.

Run the default tested pose from SSH with:

```bash
ssh pi@menderpi.local '/usr/local/bin/vision_nozzle_align.py --run-bed-y-job --name bed_y --x -80.4 --y -14.8 --z 293.75 --y-offsets 0,5,10,15,20'
```

Or queue the same job from Mainsail/Klipper with:

```gcode
IDEX_BED_Y_VISION_SWEEP NAME=bed_y X=-80.4 Y=-14.8 Z=293.75 Y_OFFSETS=0,5,10,15,20
```

Use the browser index for progress and history:

- Browser index: `http://menderpi.local/vision/`
- Per-job page: `http://menderpi.local/vision/nozzle_cam/jobs/<job_id>/`
- Live progress: `state.json`, `events.jsonl`, and the frame count on the job
  page.
- Results: `analysis/facts.json`, `analysis/result.json`,
  `analysis/raw_contact_sheet.jpg`, and `analysis/overlay_contact_sheet.jpg`.

The stable fact names are:

- `bed_y_axis_vector_px_per_mm`: image-space movement for +1 mm printer Y.
  Image +Y is downward; negative image Y means the feature moves upward in the
  camera image as printer Y increases.
- `bed_y_scale_px_per_mm` and `bed_y_mm_per_px`: local bed-feature image scale.
- `bed_y_axis_angle_deg`: direction in image coordinates.
- `bed_y_cross_axis_px_per_mm`: X drift component during commanded Y motion.
- `bed_y_fit_residual_rms_px`, `bed_y_correlation_min`, and
  `bed_y_correlation_median`: template-match quality.
- `bed_y_parallax_spread`: variation between accepted bed-feature ROIs. This is
  local perspective variation, not a full Z-height solve.

## Nozzle Camera Z Calibration Sweep

`nozzle_cam_nozzle_z_sweep` is a report-only one-run calibration job. It first
captures the bed-feature Y sweep for local scale, then captures T0 and T1 nozzle
frames at multiple X offsets and Z samples in the same acquisition G-code file.
No older job is used as input, and the measurement job does not edit
`calib.yaml`.

Run the default one-run acquisition and analysis from SSH with:

```bash
ssh pi@menderpi.local '/usr/local/bin/vision_nozzle_align.py --run-nozzle-z-job --name nozzle_z --bed-y-x -80.4 --bed-y-y -14.8 --bed-y-z 293.75 --tool-x 195 --tool-y -14.8 --travel-z 20 --y-offsets 0,5,10,15,20 --x-offsets 0,3,6,9,12 --z-values 1,2,4,8 --bed-feature-z-mm -0.1'
```

Or queue it from Mainsail/Klipper with:

```gcode
IDEX_NOZZLE_Z_VISION_SWEEP NAME=nozzle_z BED_Y_X=-80.4 BED_Y_Y=-14.8 BED_Y_Z=293.75 TOOL_X=195 TOOL_Y=-14.8 TRAVEL_Z=20 Y_OFFSETS=0,5,10,15,20 X_OFFSETS=0,3,6,9,12 Z_VALUES=1,2,4,8 BED_FEATURE_Z=-0.1
```

The generated `acquisition.gcode` explicitly switches lighting by phase:

- `bed_y_sweep`: `NOZZLE_CAM_Y_FEATURE_LIGHT`
- `tool_xz_sweep`: `NOZZLE_CAM_ANALYSIS_LIGHT`

Use the same browser locations for progress and results:

- Browser index: `http://menderpi.local/vision/`
- Per-job page: `http://menderpi.local/vision/nozzle_cam/jobs/<job_id>/`
- Live progress: `state.json`, `events.jsonl`, and frame count by phase on the
  job page.
- Results: `analysis/facts.json`, `analysis/result.json`,
  `analysis/raw_contact_sheet.jpg`, and `analysis/overlay_contact_sheet.jpg`.

Stable Z-calibration fact names include:

- `measurement: "nozzle_cam_nozzle_z_offsets"`
- `bed_feature_z_mm`: configured feature plane relative to print-surface `Z=0`.
- `bed_y_axis_vector_px_per_mm` and `bed_y_scale_px_per_mm`: bed-feature image
  scale from the first phase.
- `tool_zero_error_mm.T0` and `tool_zero_error_mm.T1`: per-tool commanded
  `Z=0` error relative to the print surface.
- `tool_z_to_bed_feature_at_command_0_mm`: per-tool distance to the configured
  bed feature plane at commanded `Z=0`.
- `tool_delta_t1_minus_t0_z_mm`: T1 zero error minus T0 zero error.
- `suggested_calib_yaml.tools.t0.z_endstop` and
  `suggested_calib_yaml.tools.t1.z_endstop`: report-only values that can be
  applied later.
- `suggested_runtime_t1_z_offset`: generated as
  `t0.z_endstop - t1.z_endstop`.
- `lighting.bed_y_sweep.macro` and `lighting.tool_xz_sweep.macro`: phase
  lighting used for the run.

Apply accepted Z facts only as an explicit follow-up:

```bash
python apply_nozzle_vision_calibration.py --dry-run --update-z /path/to/facts.json
python apply_nozzle_vision_calibration.py --update-z /path/to/facts.json
```

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
