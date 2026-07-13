# IDEX Nozzle Y/Z Vision Measurement Concept

This document describes a new nozzle-camera measurement job for deriving the
relative Z height of the T0 and T1 nozzle tips, and their height relative to the
visible print-bed feature plane. It is intended to build on the current
`idex_nozzle_sweep` framework rather than replacing it.

The existing implementation already has the important infrastructure:

- `vision-framebuffer` owns `nozzle_cam` and keeps fresh RAM-backed frames.
- `vision-capture` persists frames and now exposes synchronous job primitives
  through `visiond`.
- Klipper's `[vision]` extra exposes `VISION_JOB_BEGIN`, `VISION_PROFILE`,
  `VISION_CAPTURE_SYNC`, and `VISION_JOB_END`.
- `vision_nozzle_align.py` can prepare immutable manifests, generate hashed
  virtual-SD acquisition G-code, start the job through Moonraker, verify
  acquired frames, analyze them, write `analysis/result.json` and
  `analysis/facts.json`, and refresh the static vision UI.
- The current T0/T1 nozzle sweep measures image-space X motion and derives the
  T1-minus-T0 nozzle offset in the X/perpendicular directions.

The new measurement should be a sibling job kind, not a one-off macro or a
pose-by-pose Moonraker script.

## Goal

Add a job kind named something like `idex_nozzle_yz_sweep` that captures two
sets of images:

1. A bed-feature Y sweep: 3-5 frames with the Y axis moving away from the
   endstop by up to about 20 mm.
2. A tool X/Z sweep: with Y back at the endstop, capture both T0 and T1 at
   3-5 X positions and 3-5 Z positions, with default Z samples
   `1,2,5,8`.

The analysis should fit a small local camera/parallax model:

- The Y sweep estimates how visible bed-plane features move when the physical
  Y axis moves. This gives the image Y-axis vector, scale, and local
  perspective/parallax at the height of the bed features.
- The X/Z sweep estimates the image X-axis vector and the image-space parallax
  caused by commanded Z motion of the nozzle tips.
- Combining both fits yields the Z height of T0 and T1 relative to each other
  and relative to the bed-feature plane.

The result remains report-only. Applying a new T1 Z offset or changing
`calib.yaml` should be a separate explicit action, following the existing
`apply_nozzle_vision_calibration.py` pattern.

## Files To Extend

Primary implementation surface:

- `klipper_setup/image_build/overlays/stage2/99-klipperpi/files/vision_nozzle_align.py`

The current file is already more than a nozzle aligner: it owns job preparation,
virtual-SD staging, monitoring, analysis reporting, and UI refresh. The first
implementation can add the new job kind there to reuse the deployed plumbing.
After the second job is working, the generic job helpers can be extracted into a
shared module, but that extraction should not block the measurement.

Shared capture/runtime surfaces that should not need a new protocol:

- `klipper_setup/image_build/overlays/stage2/99-klipperpi/files/vision_capture.py`
- `klipper_setup/klipper_host/klippy/extras/vision.py`
- `klipper_setup/klipper_config/printer.cfg.template`

`VISION_CAPTURE_SYNC` already carries `tool`, `toolhead_position`,
`gcode_position`, and `homed_axes` into the frame sidecar. The new job only
needs a richer manifest and new analysis code. No new Klipper synchronous
command is required.

Optional user-facing convenience:

- Add a thin macro such as `IDEX_NOZZLE_YZ_VISION_SWEEP` only if console
  launch from Klipper/Mainsail is useful. The preferred path should stay the
  existing job orchestrator/UI flow: prepare manifest, generate G-code, start
  virtual-SD job, then analyze after acquisition.

## Manifest Shape

Keep the existing immutable manifest/state/event layout:

```text
/home/pi/printer_data/vision/nozzle_cam/jobs/<job_id>/
  manifest.json
  state.json
  events.jsonl
  acquisition.gcode
  frames/
  analysis/
```

Use the same `schema_version`, hash fields, and state machine. Add a new
`kind`:

```json
{
  "kind": "idex_nozzle_yz_sweep",
  "camera": "nozzle_cam",
  "profile": "analysis",
  "preconditions": {
    "required_homed_axes": "xyz",
    "require_idle": true
  },
  "measurement_parameters": {
    "base_x": 195.0,
    "base_y": -14.8,
    "travel_z": 20.0,
    "y_offsets": [0.0, 5.0, 10.0, 15.0, 20.0],
    "x_offsets": [0.0, 3.0, 6.0, 9.0, 12.0],
    "z_values": [1.0, 2.0, 5.0, 8.0]
  }
}
```

Each frame record should include explicit phase and sweep coordinates:

```json
{
  "seq": 0,
  "frame": "bed_y_0p0",
  "phase": "bed_y_sweep",
  "target": "bed_features",
  "tool": "T0",
  "y_offset": 0.0,
  "x_offset": null,
  "z_sample": null,
  "pose": {"x": 195.0, "y": -14.8, "z": 20.0},
  "lighting": "NOZZLE_CAM_ANALYSIS_LIGHT",
  "camera": "nozzle_cam",
  "profile": "analysis",
  "capture_command": "VISION_CAPTURE_SYNC"
}
```

Tool frames use the same record shape:

```json
{
  "seq": 17,
  "frame": "t0_x6p0_z5p0",
  "phase": "tool_xz_sweep",
  "target": "nozzle_tip",
  "tool": "T0",
  "y_offset": 0.0,
  "x_offset": 6.0,
  "z_sample": 5.0,
  "pose": {"x": 201.0, "y": -14.8, "z": 5.0}
}
```

This is intentionally more general than the current `dx`-only frame structure.
The existing `VisionJobFrame` can either gain optional fields or a sibling
dataclass can be introduced for Y/Z frames.

## Acquisition G-Code

The generated G-code remains the source of truth for the physical timeline.
It should not home, restore, park, or analyze.

Default acquisition order:

1. `G90`
2. `VISION_JOB_BEGIN ...`
3. `VISION_PROFILE CAMERA=nozzle_cam PROFILE=analysis`
4. `NOZZLE_CAM_ANALYSIS_LIGHT`
5. Select a known tool, normally `T0`.
6. Move to `travel_z`, then the base X/Y.
7. Capture the bed-feature Y sweep.
8. Return Y to the endstop/base Y.
9. For each tool, for each X position:
   - select tool if needed
   - lift to `travel_z`
   - move X/Y at safe height
   - capture Z values from high to low, for example `8,5,2,1`
   - lift to `travel_z` before the next X move
10. `VISION_JOB_END ...`

Example skeleton:

```gcode
; generated vision job: idex_nozzle_yz_sweep_...
; kind: idex_nozzle_yz_sweep

G90
VISION_JOB_BEGIN JOB=... MANIFEST_HASH=sha256:... GCODE_HASH=sha256:...
VISION_PROFILE CAMERA=nozzle_cam PROFILE=analysis
NOZZLE_CAM_ANALYSIS_LIGHT

T0
G1 Z20.000 F3600
G1 X195.000 Y-14.800 F3600

G1 Y-14.800 F3600
M400
G4 P750
VISION_CAPTURE_SYNC JOB=... SEQ=0 FRAME=bed_y_0p0 CAMERA=nozzle_cam PROFILE=analysis TOOL=T0

G1 Y-9.800 F3600
M400
G4 P750
VISION_CAPTURE_SYNC JOB=... SEQ=1 FRAME=bed_y_5p0 CAMERA=nozzle_cam PROFILE=analysis TOOL=T0

; ...

G1 Y-14.800 F3600

T0
G1 Z20.000 F3600
G1 X195.000 Y-14.800 F3600
G1 Z8.000 F1200
M400
G4 P750
VISION_CAPTURE_SYNC JOB=... SEQ=5 FRAME=t0_x0p0_z8p0 CAMERA=nozzle_cam PROFILE=analysis TOOL=T0
G1 Z5.000 F1200
M400
G4 P750
VISION_CAPTURE_SYNC JOB=... SEQ=6 FRAME=t0_x0p0_z5p0 CAMERA=nozzle_cam PROFILE=analysis TOOL=T0

; ...

VISION_JOB_END JOB=... EXPECTED_FRAMES=45
```

With the default `5 y_offsets`, `5 x_offsets`, `4 z_values`, and `2 tools`,
the job captures `5 + 2 * 5 * 4 = 45` frames. A smaller first bring-up can use
`3 y_offsets`, `3 x_offsets`, and `4 z_values` for `27` frames.

Motion rules:

- Resolve the default base Y from live Klipper limits when possible. On the
  current machine the Y minimum/endstop is `-14.8`, so a 20 mm sweep ends near
  `5.2`.
- Keep XY travel at `travel_z`; only descend for the fixed-position Z stack.
- Capture Z stacks from high to low, then lift before moving X.
- Use conservative Z feedrates near the bed.
- Validate every planned pose against Moonraker `axis_minimum`/`axis_maximum`
  before staging the virtual-SD file.
- Do not silently add `G28`. If an axis is not homed, fail preflight.

## Analysis Strategy

Implement the analysis as a new function, for example:

```python
analyze_yz_sweep_frames(frames, run_dir, overlay_dir=None)
```

Reuse the existing image helpers where possible:

- `normalized_registration_feature`
- `match_registration_features`
- contact-sheet and overlay writers
- atomic result/facts writing
- UI artifact discovery

Add specialized helpers for this job:

- `load_yz_job_frames_for_analysis(manifest_path)`
- `fit_bed_y_motion(frames)`
- `detect_or_match_bed_features(frames)`
- `detect_nozzle_tip_for_yz(frame)`
- `fit_tool_xz_motion(frames, bed_fit)`
- `solve_tool_heights(bed_fit, tool_fit)`
- `write_yz_contact_sheet(...)`

### A. Fit Bed-Plane Y Motion

Use only `phase == "bed_y_sweep"` frames.

The simplest robust approach is pairwise template registration over one or more
bed-feature ROIs:

1. Pick stable bed/fixture texture regions that are visible in every Y-sweep
   frame. Avoid the nozzle itself and avoid saturated ring-light reflections.
2. For each ROI, compute normalized gray and gradient features.
3. Match every Y-sweep frame against the Y=0 reference frame.
4. Fit image displacement as a function of commanded `y_offset`.

Output:

```json
{
  "bed_y_fit": {
    "accepted": true,
    "axis_vector_px_per_mm": [0.42, 7.51],
    "axis_px_per_mm": 7.52,
    "axis_angle_deg": 86.8,
    "residual_rms_px": 0.9,
    "usable_pair_count": 12,
    "rois": [[...]]
  }
}
```

This fit represents the image scale and direction of physical Y motion at the
height of the bed features. If several ROIs are used, also record whether the
Y vector changes across the image; that local variation is the useful
perspective/parallax signal for the bed plane.

### B. Fit Tool X Motion And Z Parallax

Use `phase == "tool_xz_sweep"` frames.

For each tool and Z sample:

1. Detect the nozzle tip center. Start from the existing nozzle candidate
   detector and global ROI cross-match. The current red-marker-derived ROI is
   useful, but this job should also support a manually configured or learned
   global nozzle ROI because low-Z images may crop differently.
2. Register the visible bed features in the same frame back to the Y=0 bed
   reference. This separates bed/camera registration from nozzle-tip motion.
3. Fit nozzle image position against commanded X and Z.

The core model can start as a local affine/parallax fit:

```text
nozzle_px(tool, x, z) =
    reference_px
  + x_axis_vector_px_per_mm * x_offset
  + z_parallax_vector_px_per_mm * z_sample
  + tool_xy_offset_px(tool)
  + tool_z_height_mm(tool) * z_parallax_vector_px_per_mm
  + residual
```

In practice the fit should be implemented as a weighted least-squares solve
with robust rejection:

- same-tool/same-Z X pairs constrain `x_axis_vector_px_per_mm`
- same-tool/same-X Z pairs constrain `z_parallax_vector_px_per_mm`
- cross-tool pairs at the same commanded X/Z constrain relative T1-minus-T0
  displacement
- the bed Y fit constrains the bed-plane basis and helps separate XY
  displacement from Z-parallax displacement

Record both direct nozzle-center detections and template-match registrations.
The current X/Y implementation became reliable when it moved from single
candidate selection to global ROI cross-match; this measurement should follow
that lesson and prefer a global fit over per-frame winner-picking.

### C. Solve Tool Heights

The height solve should produce:

- `t0_z_to_bed_features_mm`
- `t1_z_to_bed_features_mm`
- `t1_minus_t0_z_mm`
- quality metrics and residuals

The important interpretation is:

```text
tool_z_height_mm(tool) =
    fitted physical Z of the nozzle tip relative to the visible bed-feature
    plane, after accounting for commanded Z motion and the fitted image-space
    Z parallax vector.
```

The first version should report this as an observed measurement, not as an
automatic correction. It can also emit a suggested T1 Z offset adjustment:

```text
suggested_t1_z_offset_delta_mm = -t1_minus_t0_z_mm
```

but applying it must remain explicit.

### Ambiguity And Acceptance Criteria

This job fits a perspective/parallax model from image observations. It should
refuse to produce accepted calibration facts when the geometry is underconstrained.

Reject the result if any of these happen:

- fewer than 3 usable Y-sweep frames
- fewer than 2 usable Z levels per tool
- fewer than 3 usable X positions per tool
- bed feature registration fails or has high residual
- nozzle detection/cross-match fails for too many frames
- the fitted X and Y image axes are nearly colinear
- the Z parallax vector is too small or inconsistent across tools
- pairwise residuals exceed the configured threshold
- T0/T1 relative height changes materially across X positions

The result JSON should make rejection useful by keeping all diagnostic overlays,
candidate detections, fit residuals, and contact sheets.

## Result And Facts

Write job-local artifacts under `analysis/`, consistent with existing jobs:

```text
analysis/result.json
analysis/facts.json
analysis/raw_contact_sheet.jpg
analysis/overlay_contact_sheet.jpg
analysis/overlays/<frame>_overlay.jpg
```

`facts.json` should be small and stable:

```json
{
  "schema_version": 1,
  "accepted": true,
  "measurement": "idex_nozzle_yz_height",
  "job_id": "idex_nozzle_yz_sweep_...",
  "kind": "idex_nozzle_yz_sweep",
  "camera": "nozzle_cam",
  "profile": "analysis",
  "manifest_hash": "sha256:...",
  "gcode_hash": "sha256:...",
  "bed_y_axis": {
    "axis_vector_px_per_mm": [0.42, 7.51],
    "axis_px_per_mm": 7.52,
    "residual_rms_px": 0.9
  },
  "tool_xz_fit": {
    "x_axis_vector_px_per_mm": [7.78, -0.02],
    "z_parallax_vector_px_per_mm": [-0.35, 4.80],
    "residual_rms_px": 1.4
  },
  "tool_heights": {
    "T0": {"z_to_bed_features_mm": 0.03},
    "T1": {"z_to_bed_features_mm": -0.08}
  },
  "tool_delta_t1_minus_t0": {
    "z_mm": -0.11
  },
  "suggested_offsets": {
    "t1_z_offset_delta_mm": 0.11
  }
}
```

`result.json` can be larger and include:

- every frame record after analysis
- bed feature matches
- nozzle candidates
- pairwise match matrices
- fit residual tables
- accepted/rejected reason
- links to overlays/contact sheets

## UI Changes

The static vision UI already discovers jobs from `manifest.json` and
`state.json`. Extend the rendering to understand the new `kind`:

- show job kind as `IDEX nozzle Y/Z sweep`
- show frame count split by phase
- show bed Y fit summary
- show T0/T1 heights and T1-minus-T0 Z delta when accepted
- show rejection reason and contact sheets when rejected

The UI should not present an "apply" button in the first version. A later apply
workflow can call a dedicated script once the measurement has been validated.

## Tests

Add focused pytest coverage without asserting tuned calibration literals:

- job generation:
  - manifest `kind == "idex_nozzle_yz_sweep"`
  - frame sequences are contiguous and unique
  - frame count follows `len(y_offsets) + 2 * len(x_offsets) * len(z_values)`
  - generated G-code contains exactly one `VISION_JOB_BEGIN` and
    `VISION_JOB_END`
  - generated G-code uses `VISION_CAPTURE_SYNC`
  - no hidden `G28`, `VISION_CAPTURE`, restore, or park commands
  - XY moves between X samples happen at `travel_z`
- preflight:
  - all planned poses are checked against Klipper limits
  - missing homed axes fail before staging virtual-SD G-code
- analysis:
  - synthetic Y-sweep images recover the expected Y vector within tolerance
  - synthetic X/Z tool frames recover the expected Z delta within tolerance
  - rejected fits still write `result.json`, `facts.json`, and overlays
  - existing `idex_nozzle_sweep` tests continue to pass
- UI:
  - `refresh-ui` lists the new job kind and links its artifacts

Use invariants and relationships in tests. Do not assert production calibration
defaults or visually tuned threshold values as brittle literals.

## Bring-Up Plan

1. Add the new manifest/frame builder and `--prepare-yz-job` CLI path. Verify
   generated manifests and G-code locally without moving the printer.
2. Add `--run-yz-acquisition-job` using the existing virtual-SD staging and
   monitor path.
3. Run one reduced acquisition job, for example 3 Y frames, 3 X positions, and
   Z values `8,5,2`. Inspect raw frames and overlays before enabling `Z=1`.
4. Implement bed-feature Y registration and write diagnostic overlays.
5. Implement nozzle X/Z fitting and report rejected diagnostics first.
6. Add acceptance thresholds and stable `facts.json`.
7. Add UI rendering for the new job.
8. Only after repeated accepted measurements, add a separate apply script for
   the T1 Z offset recommendation.

## Notes From Current Machine State

The live printer reports Klipper ready, idle, and homed. Current limits include
Y minimum `-14.8`, Y maximum `296.0`, Z minimum `-1.0`, and Z maximum `293.75`.
Those values should not be hard-coded; the job preflight should read live
Moonraker limits and validate the generated frame poses before starting.
