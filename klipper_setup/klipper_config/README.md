# Klipper Config Truth

This directory has one active printer configuration:

- `printer.cfg` is THE config for the active printer.
- `printer.cfg.template` plus `calib.yaml` generate `printer.cfg`.
- `wiring/` is THE active wiring source for the custom Pico/TMC wiring.
- `../klipper_host/` is THE active Klipper host-extra source and contains the
  managed heater baseline plus the Tap-aware `bed_mesh.py` override. The
  override uses nozzle coordinates for `METHOD=tap` and retains Eddy offsets
  for Eddy methods.
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
remote `~/printer_data/config/printer.cfg`, the managed remote
`/opt/klipper/klippy/extras/heaters.py` and `bed_mesh.py`, the deployed
resonance helper, and the config Klippy has loaded via Moonraker without
uploading files or restarting Klipper.

`update_menderpi.sh` copies local `printer.cfg` to
`~/printer_data/config/printer.cfg` on `pi@menderpi.local`, backs up the
previous remote file with a timestamp, installs the managed Klipper core
overrides and custom extras,
restarts Klipper, verifies the Moonraker/Klippy state, then runs
`deploy_vision_code.sh` to synchronize all tracked top-level vision Python,
JSON, and PNG assets plus `priors.yaml`, restart the four vision services, and
rebuild the static vision catalog.

## Resonance measurements

The live resonance helpers are in the repository-level `scripts/` directory.
Run the default X-axis measurement from the repository root with:

```bash
scripts/run_resonance_plot.sh
```

This homes all axes first, then uses the left toolhead accelerometer and
measures at Z=20 mm. Each run is stored in its own timestamped directory under
`runs/klipper_resonance/`. To choose another measurement height, pass the
explicit option; X is assumed when no axis is supplied:

```bash
scripts/run_resonance_plot.sh X --measure-at-z=150
```

For a Y-axis measurement, the X coordinate can be selected explicitly:

```bash
scripts/run_resonance_plot.sh Y --measure-at-x=150 --measure-at-z=150
```

The wrapper copies the complete Pi-side run directory locally, including the
raw resonance CSV, calibration CSV, plot, summary, and latest aliases.

## Vision Code Development, Deployment, and Artifact Download

The commands in this section assume the current directory is already the
repository root:

```text
/Users/mege/git/mege-ender-3v3ke-idex
```

### Edit the tracked source

The source deployed to the printer is under:

```text
klipper_setup/image_build/overlays/stage2/99-klipperpi/files/
```

The main files are:

| Change | Tracked source |
| --- | --- |
| Job names, capture grids, G-code, analyzer selection, and analyzer parameters | `vision_job_types.json` |
| Job preparation, acquisition, analysis dispatch, publication, and static UI generation | `vision_calibration.py` |
| Job graph, manifests, dependencies, and validation | `vision_calibration_graph.py` |
| Eddy fiducial X/Z circle analysis | `vision_eddy_fiducial_xz.py` |
| Shared nozzle-tip localization | `vision_nozzle_tip_localization.py` |
| Fixed-Z tool-XY measurement and candidate calculation | `vision_tool_xy_calibration.py` |
| Combined post-XY nozzle X/Z sweep report | `vision_tool_xz_sweep.py` |
| Camera capture daemon | `vision_capture.py` |
| Capture service definition | `vision-capture-nozzle-cam.service` |

For example, from the repository root:

```bash
${EDITOR:-vi} klipper_setup/image_build/overlays/stage2/99-klipperpi/files/vision_job_types.json
```

If a new Python module is added, also add it to the required-file, `scp`, and
`install` lists in
`klipper_setup/klipper_config/deploy_webcam_vision.sh`.

### Apply the latest vision tool-XY candidate locally

After successful `idex_tool_xy_measure_t0` and `idex_tool_xy_measure_t1` jobs,
deploy the current vision code and run:

```bash
klipper_setup/klipper_config/fetch_apply_vision_tool_xy_candidate.sh
```

The script runs the compute-only `idex_tool_xy_candidate` job against the two
latest published datum facts, fetches its hashed candidate, verifies that the
local versioned `calib.yaml` still contains the acquisition-time T0/T1 X/Y
endstops, updates only `tools.t1.{x,y}_endstop`, and regenerates the versioned
`printer.cfg`. It does not deploy or restart the printer. Review the diff, then
use `update_menderpi.sh` to deploy the generated Klipper config and
`deploy_webcam_vision.sh` to synchronize the DAO copy of `calib.yaml`.

After deployment, a changed tool endstop invalidates the old XY image prior.
Refresh both priors and verify their provenance with:

```bash
/usr/local/bin/vision_calibration.py post-endstop-xy-check \
  --name post_endstop_xy_check
```

This runs the existing T0 and T1 XY measurement jobs, publishes fresh
commanded-X image-line models, and verifies that both were captured with the
currently active XY endstops. The X/Z sweep refuses to prepare until these
source endstops match its active calibration snapshot.

### Deploy and start the complete vision stack

The normal deployment command is:

```bash
klipper_setup/klipper_config/deploy_webcam_vision.sh
```

It deploys the tracked Python, JSON, web-server, and systemd files; restarts
Moonraker, nginx, both framebuffer services, and both capture services;
rebuilds the static `/vision/` catalog; and checks both cameras. Existing jobs
and analysis results are retained because `VISION_CLEAN_SLATE` defaults to
`0`.

Do not set `VISION_CLEAN_SLATE=1` for an ordinary code deployment. That option
permanently removes the existing printer-side vision jobs and generated
G-code after first checking that Klipper is ready and idle.

For a quick Python/JSON-only tuning cycle, use:

```bash
klipper_setup/klipper_config/deploy_vision_code.sh
```

The helper deploys every top-level `*.py` and `*.json` file from the tracked
vision source directory, installs Python under `/usr/local/bin` and JSON under
`/usr/local/share/vision`, restarts the four vision framebuffer/capture
services, rebuilds the static catalog, and confirms that all four services are
active. It deliberately does not install packages or webcam configuration and
does not restart Klipper, Moonraker, or nginx. It also leaves all acquired jobs
and analysis results untouched.

Set `MENDERPI_HOST` only when deploying to a host other than the default
`pi@menderpi.local`.

Follow nozzle-camera capture logs in a separate shell with:

```bash
ssh pi@menderpi.local 'journalctl -u vision-capture-nozzle-cam.service -f'
```

### Acquire and analyze a job

Vision motion jobs begin with `G28`, like normal print jobs. The current print
state can be checked without changing anything:

```bash
ssh pi@menderpi.local \
  'curl -fsS "http://127.0.0.1:7125/printer/objects/query?print_stats=state"'
```

Starting a new acquisition replaces any stale acquisition lock left by an
aborted job. The displaced job is recorded as failed and its partial frames
remain available for diagnosis; it cannot block the requested job.

Run acquisition and analysis together with `run`. The post-XY combined nozzle
X/Z sweep is:

```bash
ssh pi@menderpi.local \
  '/usr/local/bin/vision_calibration.py run idex_tool_xz_sweep_report --name tool_xz_sweep --timeout 1200'
```

Re-run analysis without moving the printer or capturing new images by using
the job ID printed by `run`/`acquire` and shown in the `/vision/` UI:

```bash
VISION_JOB_ID=20260731T102429.673230Z-stage5_z0p5_to25_t1
ssh pi@menderpi.local \
  "/usr/local/bin/vision_calibration.py analyze ${VISION_JOB_ID}"
```

Each analysis creates a new timestamped directory. Older analyses remain
available for comparison. Rebuild the overview after manual changes with:

```bash
ssh pi@menderpi.local \
  '/usr/local/bin/vision_calibration.py rebuild-catalog'
```

The rebuild output includes a `warnings` list. If a publication still points
to a fact set removed by manual cleanup, rebuilding continues with the newest
surviving fact for that name and reports the deleted job, affected fact, chosen
fallback, and recovery action. A job only needs to be rerun when its warning
has no fallback or when you want to replace the deleted newer measurement.
If a later publication superseded that fallback directly, rebuilding repairs
the publication lineage in chronological order and reports the repair instead
of blocking calibration jobs.
The same warnings appear at the top of the `/vision/` overview.

Inspect jobs and analysis pages at:

```text
http://menderpi.local/vision/
```

### Download frames, results, and overlays

List recent job IDs first:

```bash
ssh pi@menderpi.local \
  'find /home/pi/printer_data/vision/calibration/jobs -mindepth 1 -maxdepth 1 -type d -printf "%f\n" | sort | tail -n 20'
```

Download one complete job into a new timestamped local directory:

```bash
VISION_JOB_ID=20260731T102429.673230Z-stage5_z0p5_to25_t1
VISION_DOWNLOAD_DIR="output/vision_downloads/$(date -u +%Y%m%dT%H%M%SZ)-${VISION_JOB_ID}"
mkdir -p "${VISION_DOWNLOAD_DIR}"
scp -r \
  "pi@menderpi.local:/home/pi/printer_data/vision/calibration/jobs/${VISION_JOB_ID}/." \
  "${VISION_DOWNLOAD_DIR}/"
printf 'Downloaded vision job to:\n%s\n' "${VISION_DOWNLOAD_DIR}"
find "${VISION_DOWNLOAD_DIR}" -maxdepth 4 -type f | sort
```

The downloaded job contains:

- `manifest.json`, `state.json`, `events.jsonl`, and `acquisition.gcode` at the
  job root;
- raw images and per-frame metadata under `frames/`;
- one directory per analysis run under `analysis/`;
- `result.json` and `report.md` in each analysis directory; and
- the full-resolution generated overlays and model plots under
  `analysis/<analysis_run_id>/artifacts/`.

Opening the downloaded `index.html` directly is useful for file discovery,
but the printer-hosted UI remains the authoritative rendered view because its
links use the `/vision/` URL prefix.

## Vision Calibration Framework

The clean chain starts with the flat values in `priors.yaml` for the 8 mm
square fiducial patch, its printer-Z plane (`-0.6 mm`), and the master fiducial-centre datum
(`[166.709424, -24.839235, -0.6] mm`). Vision runtime code reads these through `CalibDAO`; they
are configuration, not published graph facts.
Capture the six-frame `0, 10, 20, 20, 10, 0 mm` printer-Y sweep under the
standard nozzle-camera lighting and recover the local fiducial metric:

```gcode
IDEX_BED_FIDUCIAL_METRIC_CALIBRATE NAME=bed_fiducial_metric
```

The coarse red-marker sweep establishes image X and both tool relations:

```gcode
IDEX_RED_MARKER_X_SWEEP_CALIBRATE NAME=red_marker_x_sweep
```

Accepted red-marker jobs publish their three coordinate facts immediately. They
do not modify `calib.yaml` or activate either tool's X endstop.

Calculate both tool X endstops independently from the fixed fiducial datum:

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

The verification expects each red marker to project 16.290576 mm along the measured
image-X axis from the fixed fiducial-centre datum and expects the two marker image-X
positions to agree. It is report-only and does not change configuration.

The independent Eddy diagnostic commands T0 through four X positions from
`230` to `244 mm` and four Z positions from `0.5` to `9 mm`, producing 16
captures at `Y=-14 mm`. It uses the existing nozzle analysis profile and light
macro, detects the strongest circular Eddy fiducial, and publishes only the raw
commanded X/Z and image X/Y records:

```gcode
IDEX_EDDY_FIDUCIAL_XZ_ACQUIRE NAME=eddy_fiducial_xz
```

The combined report uses the ArUco-located ROI and bright-circle nozzle
detector, then fits the T0/T1 X/Z trajectories and shared Z offset. It is
diagnostic-only; an unavailable or bound-saturated shared fit must not be
applied.

After the post-endstop XY check succeeds, start the combined report-only nozzle
X/Z sweep with:

```gcode
IDEX_TOOL_XZ_SWEEP_REPORT NAME=tool_xz_sweep_report
```

The job captures both T0 and T1 at the configured XY sweep columns and Z rows.
It records commanded X/Y/Z, raw nozzle image `(u, v)`, and all four fiducial
positions for every frame, then writes one combined `u(x)` plot. Overlay
generation is currently disabled behind a module guard. This step is
diagnostic-only and does not calculate or apply a calibration correction. It
also fits a robust Theil-Sen
`u = intercept + slope * X` model independently for each toolhead and Z height,
records the slope and fit quality, and writes a slope-versus-Z plot. Correlated
rows are then fitted to a shared robust quadratic slope-versus-physical-Z curve
with a bounded T1 Z shift. Poor-correlation rows and MAD-detected curve outliers
are excluded and documented; the resulting T1 Z delta remains diagnostic only.

After reviewing an accepted shared-curve result, fetch and apply its local T1
Z-endstop candidate with:

```bash
./fetch_apply_vision_tool_z_offset_candidate.sh
```

The helper verifies that local T0/T1 Z endstops still match the sweep's
acquisition snapshot, then applies `new T1 z_endstop = old z_endstop + fitted
T1 Z delta` and regenerates `printer.cfg`. Because Z homes at the top, a
negative fitted delta reduces `z_endstop` and raises the T1 nozzle. The helper
only edits the local source-of-truth files; deployment remains explicit.

> Calibration boundary (2026-08-23): the accepted T0/T1 XY state is the end
> calibration state for the IDEX tools. The XZ sweep implementation is retained
> for historical and diagnostic use, but is no longer a calibration authority.
> T0 Z calibration is maintained by the Eddy sensor, Tap, and the active bed
> mesh; the accepted T0/T1 relative offset remains unchanged.

The corresponding host job types, in dependency order, are:

```text
nozzle_cam_bed_fiducial_y_metric
idex_tool_red_marker_x_sweep
idex_rough_tool_x_verify
idex_eddy_fiducial_xz_grid
idex_tool_xz_sweep_report
```

The prior values live in `/usr/local/share/vision/priors.yaml`, deployed from
the canonical `klipper_setup/klipper_config/priors.yaml`. Changes apply to new
preparations and analyses; deliberately rerun the affected calibration chain
when an existing published result should be replaced.

Watch progress and artifacts at `http://menderpi.local/vision/`. Accepted
results publish immediately; rejected analyses publish nothing. Fiducial and
feature pixel positions are observed, never configured.

The `/vision/` overview shows only fields explicitly declared as
coordinate-system defining. The full current-facts report keeps diagnostic
fields such as fit quality, capture details, provenance, and artifact hashes.

Publication updates only the fact catalog. It does not edit `calib.yaml`,
restart Klipper, or activate a printer calibration.


## Heatbed

The active bed remains `[heater_bed]` for normal Klipper and UI compatibility.
`heater_pin: gpio20` drives the SSR for the single 220V 750W bed, and
`pwm_cycle_time: 2.0` provides appropriately long software PWM for the SSR.

The template stays in calibration-ready `watermark` mode until measured PID
constants exist. To tune and deploy the final PID bed config while physically
supervising the printer:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex/klipper_setup/klipper_config
./calibrate_bed_pid.sh --target 80
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
