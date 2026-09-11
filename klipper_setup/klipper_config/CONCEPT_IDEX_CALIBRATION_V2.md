# IDEX Calibration V2 — One Automatic Path to a Printable Machine

Status: authoritative workflow definition. The local scripts and dashboard now
follow the reconciled sequence; live deployment and physical acceptance remain
separate verification activities.

## Purpose

The printer needs two independent calibrations that compose into one useful
coordinate system:

1. **Toolhead alignment** makes T0 and T1 reach the same physical point when
   commanded to the same logical X/Y/Z coordinate. The multi-head-zero ball is
   the shared tool datum. Its prescribed logical centre is exactly
   `X=75.000, Y=-9.000`.
2. **Bed reference and surface calibration** makes T0 touch the bed at logical
   `Z=0` at `X=150.000, Y=150.000`, then measures the bed surface so commanded
   `Z=0` follows the bed everywhere covered by the mesh.

T0 is the absolute Z anchor. Multi-head-zero aligns T1 to T0. Eddy Tap then
shifts both tool Z endstops by the same amount to establish the bed's absolute
Z datum, preserving the T0/T1 relationship. The mesh adds only an X/Y-dependent
surface correction.

When both chapters pass, the following statements hold:

```text
T0 ball centre XY = (75.000, -9.000)
T1 ball centre XY = (75.000, -9.000)
T0 ball contact Z = T1 ball contact Z

T0 bed contact Z at (150.000, 150.000) = 0.000
T1 bed contact Z at (150.000, 150.000) = 0.000
commanded Z=0 follows the measured bed surface for both tools
```

The last line follows because the mesh is measured with T0, tool changes use
the same physical-bed mesh, and multi-head-zero has already made T1's logical
coordinate frame coincide with T0's.

## Design principles

- There is one prescribed full workflow and one public command for it.
- The user never copies measurements into YAML and never runs an applier by
  hand.
- Calibration writers update only the fields they own.
- Every write is atomic, provenance-checked, regenerated, deployed, and checked
  against the configuration Klipper actually loaded.
- Measurement values live in `calib.yaml`. Fixed geometry and procedure
  configuration do not.
- Status, methods, timestamps, fingerprints, candidates, and acceptance evidence
  live in run artifacts and dashboard state, not in `calib.yaml`.
- Vision is not part of the authoritative print-calibration chain.
- The printer console and `/calibration/` tell the same story while the machine
  moves. A shell running on another computer must not be the only place where
  progress is visible.
- A failed measurement never produces a partial calibration update. A failed
  deployment is rolled back automatically. A failed physical verification is
  retained as evidence and leaves the machine clearly marked not ready.

## Calibration model and invariants

### Toolhead alignment owns relative tool coordinates

The multi-head-zero workflow may change:

- T0 X endstop;
- T0 Y endstop;
- T1 X endstop;
- T1 Y endstop; and
- T1 Z endstop.

It must not change T0 Z or the bed mesh. X/Y corrections are absolute: each
tool's measured phase-3 ball centre is independently moved to `(75,-9)`. T1 Z
is adjusted from the final five-tap centre-median difference to T0. The rough
summit remains available for the sphere fit, but it is not the authoritative Z
measurement. Ring contacts support XY fitting only.

After either X endstop changes, the two parked-tool limits are derived from the
fixed physical nozzle separation of exactly `101.4 mm`:

```text
T0 position_max = T1 x_endstop - 101.4
T1 position_min = T0 x_endstop + 101.4
```

Klipper's `safe_distance: 10` is unrelated to this parked-tool clearance and
remains unchanged.

### Bed reference calibration owns absolute Z

With T0 selected, no mesh active, and no manual G-code offset, Eddy Tap measures
the physical bed at `(150,150)`. For the accepted centre-contact result
`z_reference`, the common correction is:

```text
common_z_delta = 0.000 - z_reference
new T0 Z endstop = old T0 Z endstop + common_z_delta
new T1 Z endstop = old T1 Z endstop + common_z_delta
```

The workflow checks, before writing and after deployment, that:

```text
new T1 Z endstop - new T0 Z endstop
    = old T1 Z endstop - old T0 Z endstop
```

This common rebase cannot disturb the T0/T1 Z alignment established by the
ball. After restart and homing, a fresh physical T0 centre tap must occur at
approximately logical `Z=0` before mesh acquisition is allowed.

### The mesh owns bed shape, not absolute tool offset

The mesh is measured only after the common Z rebase passes. The generated
`[bed_mesh]` configuration uses:

```ini
zero_reference_position: 150,150
```

This anchors the native mesh correction to zero at the same physical reference
used for the absolute Eddy Tap datum. Mesh values are deviations from that
reference and therefore normally contain both positive and negative values
when the bed has high and low regions around it.

Raw contact Z away from the reference is not expected to read zero with the
mesh cleared: it is the measured bed shape. With the mesh active, the useful
invariant is that commanded logical `Z=0` maps to physical bed contact. Final
verification must evaluate that mesh-aware residual rather than demand that an
untransformed raw tap reports zero at every point.

## What the user does

### Starting condition

The machine only needs to be roughly calibrated:

- all axes can home safely;
- both toolheads can reach the multi-head-zero seed envelope around the ball;
- the ball switch is mechanically secure and electrically healthy;
- T0's Eddy sensor has a valid frequency/height curve and Tap threshold;
- the nozzle and bed are clean; and
- no print is running.

The rough endstops may be inaccurate. That is the point of the workflow.

### Normal full calibration

From the repository root, the user runs one command:

```bash
scripts/run_idex_calibration.sh
```

The command performs the following seven-step sequence without asking the user
to edit a file, copy a number, restart Klipper, load a mesh, or run a verifier
manually.

1. Find rough T0 bed Z at `(150,150)` with banded Eddy descent.
2. Apply the common T0/T1 Z correction, deploy, and re-home.
3. Verify five fixed-window T0 taps at logical `Z=0`; no banded descent is
   allowed here because the bed height is already known.
4. Align and verify T0/T1 X, Y, and relative Z against the ball.
5. Measure the native Tap mesh and persist the accepted matrix to `calib.yaml`.
6. Regenerate, deploy, reload, and verify the persisted active mesh.
7. Publish `READY TO PRINT` only when the compatible accepted bed, tool, and
   mesh chapters are all deployed and verified. The accepted calibration chain
   may compose chapters from different immutable attempts.

The dashboard is opened separately at:

```text
http://menderpi.local/calibration/
```

The page needs no manual refresh. The printer console also reports every major
phase and every contact's progress.

### Independent maintenance workflows

The two systems remain independently runnable without exposing low-level
applier commands:

```bash
scripts/run_idex_bed_reference.sh          # steps 1–3
scripts/run_multi_head_zero_contact_map.sh # step 4
scripts/refresh_idex_bed_mesh.sh           # steps 5–6
```

Each route creates an immutable attempt. A shared acceptance ledger on the Pi
retains a chapter only when its semantic invariants and fixed inputs remain
compatible, then composes those accepted chapters into readiness. A failed
rerun is rolled back to the last accepted `calib.yaml` checkpoint; diagnostics
remain visible without replacing accepted evidence.

Developer-only helpers may still support replay, calculation, and diagnostics,
but they are not steps in the user manual and cannot be required to reach a
printable state.

## Prescribed automatic sequence

### 0. Preflight and transaction start

The coordinator:

1. validates `calib.yaml`, `calib_config.yaml`, and `printer.cfg.template`;
2. regenerates `printer.cfg` and checks that no generated diff is being hidden;
3. confirms local, remote-file, and live-Klipper fingerprints agree;
4. requires Klipper ready and the printer idle;
5. records heaters, homed axes, active tool, manual offsets, mesh state, switch
   state, and source endstops;
6. creates an immutable batch directory containing the source files and hashes;
7. clears manual offsets and the active mesh;
8. homes XYZ once only if it is not already homed;
9. immediately issues `QUERY_MULTI_HEAD_ZERO` to sample the physical pin and
   requires the result to be `RELEASED` while the axes are at home. The explicit
   query is necessary because a newly restarted Klipper instance has no cached
   switch state. A `TRIGGERED` or unavailable result at this physically clear
   position is an electrical/mechanical fault, is reported in the printer
   console and dashboard, and aborts before the X latch, tool selection, or any
   calibration motion; and
10. performs one final X-only latch pass at 1 mm/s. Live ball measurements found
   the first X home after restart could differ by up to 0.25 mm, while the
   settled pass is the repeatable datum needed by both calibration and
   post-deployment verification.

Every later candidate names this source fingerprint. A stale result cannot be
applied to a changed `calib.yaml` or a different live configuration.

### 1. Eddy Tap absolute bed reference (steps 1–3)

The first physical datum is always the T0 Eddy Tap centre at exactly
`(150,150)` with the mesh cleared. Discovery is deliberately staged from high
to low in overlapping 2 mm guarded bands, advancing by 1 mm:

```text
10→8, 9→7, 8→6, 7→5, 6→4, 5→3, 4→2, 3→1,
2→0, 1→-1, 0→-2.2 mm
```

Each no-trigger band is recorded and continues from its lower endpoint plus
the 1 mm overlap. A contact on an endpoint is therefore covered by the
neighbouring window as well. The first accepted deformation fit establishes a
physical contact height. A trigger whose pullback fit is rejected exactly at a
lower window endpoint is treated as an ambiguous boundary and retried in the
next overlapping window. A rejected fit in the interior, or in the final
window, remains a safety fault: retract, report the diagnostics, and stop
rather than probing farther on an unproven signal.

After discovery, five narrow-range centre taps start 2 mm above that contact
and stop 1 mm below it. The probe retracts 4 mm after each trigger so the
deformation fit has enough samples. Only their median establishes the absolute bed-Z datum;
the common correction is applied to both Z endstops, preserving the
T1-minus-T0 Z difference. The candidate is deployed and the post-rebase check
repeats only the fixed window `START_Z=2` to target `Z=-1` for five taps. It
must return within the absolute-Z tolerance before the ball workflow starts.
No second banded discovery, ball motion, or mesh motion is attempted until this
stage passes.

This ordering is deliberate: the ball's measured summit is then expressed in
the final bed-referenced logical Z frame, while the ball remains the authority
for relative T0/T1 Z alignment.

### 2. Multi-head-zero calibration (step 4)

For T0, then T1, the runner performs the fixed 31-contact sequence:

1. nine serpentine seed contacts over the configured safe envelope;
2. one mandatory direct contact at the fitted rough summit;
3. one mandatory eight-point `2.8 mm` ring around that summit;
4. one mandatory eight-point `2.8 mm` ring around the first refined centre; and
5. five final-centre contacts at the refined XY position.

The `2.8 mm` ring retains enough sphere slope for the harmonic XY fit while
keeping contacts close to vertical. Ring Z values are consumed only by that
fit and are not exposed as an operator-facing Z diagnostic.

The second ring's harmonic centre is the final X/Y measurement. The median of
the five final-centre contacts is the authoritative Z measurement. Each series
must contain exactly five completed contacts and have population standard
deviation `σ ≤ 15 µm`; an incomplete or noisy series fails before any
correction is applied. T0 completes all 31 contacts, Z lifts to the safe switch
height, and the workflow selects T1 exactly once. Active carriage, extruder,
logical origin, mesh state, and manual adjustment are verified for every
contact.

The coordinator calculates and stages:

```text
T0 X/Y delta = configured ball target - measured T0 centre
T1 X/Y delta = configured ball target - measured T1 centre
T1 Z delta   = correction that makes the T1 centre median equal the T0 centre median
T0 Z delta   = 0
```

It updates all owned endstops in one candidate `calib.yaml`, derives the parked
X limits, generates a candidate `printer.cfg`, deploys it, checks file and live
fingerprints, re-homes once if the restart invalidated homing, and repeats the
same final X-only latch pass before verification.

### 3. Fixed-target tool verification (step 4)

T0 and T1 each perform thirteen mandatory contacts in their logical frames:

1. five contacts are exactly `(75.000,-9.000)` and publish centre-Z statistics;
2. the remaining eight contacts are E, NE, N, NW, W, SW, S, and SE on the
   fixed `2.8 mm` ring around exactly `(75,-9)`.

The ring recovers X/Y. The centre median supplies Z. Verification passes only
when each tool is within the configured target tolerance, the two recovered
centres agree, the paired centre-median Z difference is within the Z tolerance,
and both five-tap series satisfy `σ ≤ 15 µm`. Every check records its measured
value, limit, pass/fail result, and a human-readable reason. A failed gate stops
the workflow before mesh acquisition.

Verification never performs a second correction. Failure marks tool alignment
failed and stops the full workflow before bed calibration.

### 4. Eddy Tap mesh acquisition and persistence (steps 5–6)

With the absolute reference verified before ball alignment, the coordinator:

1. runs the source-configured native `BED_MESH_CALIBRATE` Tap sequence;
2. publishes progress after every mesh point;
3. requires the configured dimensions and a complete finite matrix;
4. confirms the mesh's zero reference is `(150,150)`;
5. activates the candidate profile in the current session;
6. performs mesh-aware checks at the reference and representative bed points;
7. writes only `bed_mesh_points` to the staged flat `calib.yaml`;
8. regenerates and deploys the persistent profile;
9. verifies the deployed points exactly match the accepted live candidate; and
10. loads the configured default profile.

No one copies the matrix from a console. A failed scan or verification retains
the previous stored mesh.

### 5. Final readiness decision (step 7)

The final report is printable only if all of these are true under the same
deployed target fingerprint:

- multi-head-zero calibration completed for both tools;
- fixed-target thirteen-contact verification passed, including both centre
  repeatability gates;
- the post-rebase T0 bed-reference tap passed near `Z=0`;
- the persistent mesh equals the accepted measured matrix;
- the default mesh is active;
- mesh-aware physical checks passed;
- no manual XYZ offset is active; and
- Klipper is ready with local/remote/live configuration parity.

Anything else is prominently `NOT READY TO PRINT`; a sea of green unit tests
does not get a veto over physics.

## Implementation status and known boundaries

The current implementation now follows the reference-first ordering in the
full coordinator. The post-rebase reference check is a fixed five-tap window;
banded descent is reserved for initial discovery. The mesh runner already
performs acquisition, persistence, regeneration, deployment, profile reload,
matrix parity, and mesh-aware physical checks; it is exposed through the
single `scripts/refresh_idex_bed_mesh.sh` maintenance command.

The dashboard uses schema-v4 acceptance state rather than attempt-only
readiness. It shows accepted provenance (attempt, time, compatibility, and
artifact) alongside any active or failed attempt. A T0 X/Y/Z frame change in a
tool rerun immediately marks the accepted mesh stale; steps 5–6 must then be
refreshed. Non-owned changes do not invalidate it. The last successful full
composition is retained as history and is never silently mixed into the active
attempt.

The older
`klipper_setup/klipper_config/calibrate_idex_bed_surface_eddy_tap.py` I1
iteration remains in the repository for diagnostics and historical replay. Its
workflow and transient-mesh behavior are not authoritative and must not be
used as the operator path; the coordinator and the two maintenance commands
above are the supported interface.

## Configuration ownership

### `calib.yaml`: measured values only

`calib.yaml` is intentionally flat. A field belongs here only when a measurement
workflow can reasonably produce a new value for it without redesigning or
disassembling the machine.

The V2 schema contains these keys, in this stable order:

```text
t0_x_endstop
t0_y_endstop
t0_z_endstop
t1_x_endstop
t1_y_endstop
t1_z_endstop

input_shaper_t0_x_type
input_shaper_t0_x_frequency_hz
input_shaper_t1_x_type
input_shaper_t1_x_frequency_hz
input_shaper_y_type
input_shaper_y_frequency_hz

eddy_nozzle_to_coil_x_mm
eddy_nozzle_to_coil_y_mm
eddy_nozzle_to_coil_z_mm
eddy_temperature_calibration_c
eddy_reg_drive_current
eddy_tap_threshold
eddy_height_calibration

bed_mesh_points
```

`eddy_height_calibration` remains a block scalar because it is one measured
Klipper curve. `bed_mesh_points` remains a two-dimensional list because a
matrix is intrinsically structured. Everything else is a simple scalar.

The file contains no:

- schema/status/method/cold-only fields;
- timestamps, acceptance state, or provenance;
- ball dimensions or target coordinates;
- contact counts, ring radii, tolerances, or search bounds;
- bed mesh dimensions or algorithm settings;
- parked-tool model names or safety policy;
- camera, lighting, capture-pose, or image-analysis configuration; or
- derived `position_min`/`position_max` values.

Derived values are recalculated by the generator. Evidence belongs to the run
manifest. Comments in `calib.yaml` explain ownership, not machine history.

### `calib_config.yaml`: fixed print-calibration configuration

This file contains values that change only when the printer design or the
prescribed calibration procedure changes. It is also flat. Its intended groups
are:

```text
# Coordinate datums and fixed reach
multi_head_zero_target_x_mm
multi_head_zero_target_y_mm
eddy_bed_reference_x_mm
eddy_bed_reference_y_mm
parked_tool_clearance_mm

# Safe acquisition envelope
multi_head_zero_seed_min_x_mm
multi_head_zero_seed_max_x_mm
multi_head_zero_seed_min_y_mm
multi_head_zero_seed_max_y_mm

# Persistent mesh layout
bed_mesh_profile
bed_mesh_min_x_mm
bed_mesh_max_x_mm
bed_mesh_min_y_mm
bed_mesh_max_y_mm
bed_mesh_x_count
bed_mesh_y_count
bed_mesh_x_pps
bed_mesh_y_pps
bed_mesh_algorithm
bed_mesh_tension
bed_mesh_horizontal_move_z_mm
```

Algorithm constants that have only one supported value are code constants, not
configuration: the 5 mm ball radius, 2.8 mm ring, 31-contact calibration
layout, 13-contact verification layout, five-tap centre gate, safe switch lift,
contact order, correction formulae, and acceptance logic. If an implementation genuinely needs an
operator-tunable physical limit, it may be added to `calib_config.yaml`; it may
not be smuggled back into measured `calib.yaml`.

The generator hashes `calib.yaml`, `calib_config.yaml`, and
`printer.cfg.template` together. The resulting fingerprint is embedded in
`printer.cfg` and every measurement artifact.

### `vision_config.yaml`: isolated vision configuration

All camera-specific configuration moves here, including:

- image dimensions and profiles;
- capture poses;
- camera controls;
- lighting patterns;
- fiducial and image-analysis priors; and
- any vision-only acceptance thresholds.

Vision run results remain in immutable vision job artifacts. Vision does not
write tool endstops, bed Z, or mesh values in `calib.yaml`, and vision files do
not participate in the print-calibration fingerprint.

The implementation marks the former vision-based IDEX calibration documents as
**legacy** and links them to this document and the new operator manual. Vision
may remain useful for diagnostics and experiments, but it is no longer an
authoritative route to a printable coordinate frame. The current
`CONCEPT_XYZ_PROBE.md` becomes historical detail for the ball algorithm where
it does not conflict with V2; this document owns the end-to-end sequence.

### Generated and deployed files

`printer.cfg.template` contains structure and macros. The generator combines it
with the two print-calibration YAML files to produce `printer.cfg`.

```text
calib.yaml + calib_config.yaml + printer.cfg.template
    -> generate_printer_cfg.py
    -> printer.cfg
    -> update_menderpi.sh
    -> remote printer.cfg
    -> live Klipper configuration
```

Neither `printer.cfg` nor a remote `SAVE_CONFIG` block is edited by a calibration
workflow. Deployment succeeds only when generated local, remote file, and live
Klipper fingerprints agree.

## Atomic calibration updates

All calibration writers use one shared calibration-data access layer. It:

1. reads and validates the flat measured schema;
2. checks the expected source hash;
3. restricts the caller to its owned keys;
4. writes a complete candidate beside the run artifacts;
5. validates and generates a candidate `printer.cfg`;
6. atomically replaces the canonical files only after candidate validation;
7. deploys through the normal update path;
8. verifies remote and live parity; and
9. automatically restores and redeploys the source files if deployment or
   parity fails.

The multi-head-zero writer owns five endstop fields. The Eddy reference writer
owns the two Z endstop fields but is constrained to the same delta. The mesh
writer owns only `bed_mesh_points`. Input-shaper and low-level Eddy calibration
tools own only their respective measured fields.

Physical verification failure is different from deployment failure: it is
published as a failed calibration result and stops the sequence. Measurements
and both source/target configurations remain available for diagnosis; no
follow-up correction is silently invented.

## Run artifacts and live files

### Immutable local batch

Each full run is copied to:

```text
runs/idex_calibration/<batch-id>/
  batch_manifest.json
  source/
    calib.yaml
    calib_config.yaml
    printer.cfg
  tool_alignment/
    calibration_result.json
    T0/manifest.json
    T0/records.csv
    T0/calibration_T0.png
    T1/manifest.json
    T1/records.csv
    T1/calibration_T1.png
    verification/
      T0/manifest.json
      T0/records.csv
      T0/verification_T0.png
      T1/manifest.json
      T1/records.csv
      T1/verification_T1.png
      verification_report.json
      verification_report.csv
  bed_calibration/
    reference_before.json
    reference_after.json
    z_rebase_result.json
    mesh_points.csv
    mesh_result.json
    mesh.png
    mesh_verification.json
  final_report.json
```

Manifests contain timestamps, logical and machine coordinates, active origins,
tool state, mesh state, manual offsets, source and target endstops, configuration
fingerprints, calculations, tolerances, and termination reason. None of this
metadata is copied into `calib.yaml`.

### Remote dashboard state

Calibration live data is no longer stored under a vision-named directory. The
canonical remote root becomes:

```text
/home/pi/printer_data/calibration/
  data/accepted.json
  data/current.json
  data/activity.json
  data/last_successful.json
  runs/<batch-id>/...
  artifacts/<content-addressed-or-batch-named-files>
```

Nginx continues to expose this root at `/calibration/`.

`accepted.json` is the durable acceptance ledger. `current.json` is its
atomically replaced compact dashboard projection; it is mutable by design and
contains links or summaries, not the sole copy of evidence. `activity.json` is
the separately locked volatile heartbeat/activity record. It may inform the UI
that a transaction is busy, delayed, or stale, but cannot alter acceptance or
print readiness.
`last_successful.json` points to the last full batch that reached printable
state. Starting or failing a new run does not erase that history.

The V2 dashboard snapshot has this top-level shape:

```json
{
  "schema_version": 4,
  "kind": "idex_calibration_dashboard",
  "batch_id": "...",
  "run_scope": "full|tool_alignment|bed_reference|mesh_refresh",
  "status": "running|completed|failed",
  "stage": "tool_alignment.calibration.t0",
  "updated_at": "...",
  "source_config_fingerprint": "...",
  "target_config_fingerprint": "...",
  "attempt": {},
  "accepted": {},
  "accepted_sources": {},
  "events": [],
  "chapters": {
    "tool_alignment": {
      "calibration": {},
      "verification": {}
    },
    "bed_calibration": {
      "reference": {},
      "mesh": {}
    }
  },
  "readiness": {
    "printable": false,
    "checks": [],
    "reasons": []
  },
  "last_successful_batch_id": "..."
}
```

The publisher updates it after every multi-head-zero contact, every Eddy
reference contact, every mesh point, every calculation, every deployment state
change, and every abort. Writes use temporary-file-plus-rename so the one-second
browser poll never observes partial JSON.

### Local dashboard simulator

Dashboard behavior must be exercised without waiting for a physical calibration
or moving the printer. `scripts/run_idex_calibration_dashboard_simulator.sh`
starts a localhost-only server at
`http://127.0.0.1:8787/calibration/`. It serves the exact production static
dashboard assets, injecting controls only into that local response, and mocks
the calibration projections, activity record, Moonraker object query, G-code
store, webcam still, artifacts, and plots.

`scripts/idex_calibration_simulate.sh` is the deterministic event interface
for reset, scenarios, starts, explicit steps, contact progress, heartbeats,
chapter completion, failures, restarts, heartbeat age, and printer state.
It uses the real acceptance-ledger module to compose its projections. Its
fixtures are captured by the read-only
`scripts/capture_idex_calibration_dashboard_simulator_fixtures.sh`, which keeps
a small provenance-manifested subset of real evidence in
`tests/fixtures/idex_calibration_dashboard/`. The simulator binds only to
`127.0.0.1` and never contacts Moonraker, SSH, or motion workflows.

## Calibration dashboard

The page title becomes **IDEX calibration**. It presents the entire causal story
without replacing earlier results when a later phase starts.

### Header and readiness

The fixed header shows:

- current state and phase;
- source and deployed configuration fingerprints in shortened form;
- last update time;
- a large `CALIBRATING`, `READY TO PRINT`, or `NOT READY TO PRINT` badge; and
- live printer state, coordinates, camera, and running console output; and
- the last fully verified batch when the current run is partial or failed.

The dashboard deliberately avoids ambiguous “before” and “after” labels. The
operator-facing names are **Initial discovery** (the banded rough-height
measurement) and **Post-correction verification** (the five fixed-window taps
at logical `Z=0`). The JSON compatibility keys `before_rebase` and
`after_rebase` remain internal implementation names only. Coordinates,
absolute Z, and the common Z correction are shown in millimetres; alignment
corrections, errors, spans, and repeatability are shown in micrometres.

### Chapter 1 — Bed Z reference (steps 1–3)

This chapter shows:

- the fixed `(150,150)` reference and target `Z=0`;
- initial banded discovery progress and diagnostics;
- the five post-correction fixed-window taps, explicitly marked as no-discovery;
- source/target T0/T1 Z endstops, common correction, and the preserved relative Z check;
- zero residual and acceptance evidence.

### Chapter 2 — Toolhead alignment (step 4)

This chapter keeps both 31-contact calibration cards and both fixed-target
13-contact verification cards visible together. It shows:

- current tool and `n/31` or `n/13` progress;
- the live isometric contact plots;
- clickable fullscreen completed PNG plots;
- rough summit, phase-2 centre, and final phase-3 centre;
- the prescribed `(75,-9)` target;
- each tool's target error in micrometres;
- each tool's five-tap centre median, centre σ, and their difference in
  micrometres;
- source/applied/change values for the human-meaningful `T1-T0` endstop
  offsets; and
- all verification limits and pass/fail components.

The centre series is authoritative only when all five taps are complete and
within the `σ ≤ 15 µm` gate; the ring need not finish before the user can
inspect the in-progress XY fit.

### Chapter 3 — Mesh and readiness (steps 5–7)

This chapter shows:

- live mesh-point progress and latest contact;
- a readable bed heatmap/3D surface with zero emphasized;
- mesh minimum, maximum, peak-to-peak range, and reference interpolation;
- source, candidate, and deployed mesh hashes;
- mesh-aware verification residuals; and
- whether the default profile is currently loaded; and
- the final accepted calibration-chain readiness decision.

All three chapters remain visible after completion. A failed current run remains
visible with its precise stopping condition, while the header can still link to
the last successful full calibration.

### Live printer context and console

The top of the page mirrors the useful parts of Mainsail without leaving the
calibration workflow: printer state and homed coordinates, the main printer
camera, and the live Moonraker G-code console. Human-readable `RESPOND`
messages remain visible there alongside motion commands and Eddy diagnostics:

```text
IDEX calibration: batch started; preflight passed
IDEX calibration: T0 ball calibration started
IDEX calibration: T0 ball tap 12/31 ...
IDEX calibration: T0 final centre X=... Y=...
IDEX calibration: lifting to Z=10 and switching T0 -> T1
IDEX calibration: tool alignment deployed; parity passed
IDEX calibration: T0 verification centre Z=...
IDEX calibration: tool verification PASSED
IDEX calibration: Eddy bed reference taps started at X=150 Y=150
IDEX calibration: common Z delta=...; T1-T0 preserved
IDEX calibration: post-deploy bed reference Z=...
IDEX calibration: mesh point 23/49 ...
IDEX calibration: persistent mesh deployed and active
IDEX calibration: READY TO PRINT
```

Low-level contact messages remain available, but they are not the workflow UI.

## Operator manual to be written during implementation

`IDEX_CALIBRATION.md` will be the short operational manual. It will contain:

1. the physical prerequisites and safety inspection;
2. the single normal command;
3. the exact automatic sequence and expected duration;
4. what the console and dashboard should show;
5. the objective pass criteria;
6. the two independent maintenance commands;
7. recovery from a failed contact, failed deployment, or failed verification;
8. where immutable artifacts are stored; and
9. how to confirm the machine is ready before printing.

It will not instruct the user to edit `calib.yaml`, paste a mesh, invoke an
applier, restart Klipper, or load a profile manually.

## Legacy vision calibration separation

The implementation adds a prominent legacy banner to the former vision-based
IDEX calibration concepts and README instructions. Those documents will state:

- vision calibration is no longer in the authoritative print workflow;
- its existing jobs and evidence are retained for diagnostics;
- camera configuration lives in `vision_config.yaml`;
- vision code cannot update print-calibration fields; and
- this V2 concept plus `IDEX_CALIBRATION.md` are the current sources for making
  the printer printable.

The vision web application remains at `/vision/`; the print calibration
dashboard remains at `/calibration/`. Their configuration, fingerprints, live
state, and artifact roots are deliberately separate.

## Implementation order

The implementation should proceed in reviewable stages:

1. finish and validate the three-file configuration split without changing
   measured values;
2. migrate every consumer to the flat measured schema and combined generator
   fingerprint;
3. add the transactional calibration writer;
4. implement the automatic Eddy reference rebase before mesh persistence;
5. add the no-option full coordinator with the reference-first order;
6. migrate dashboard storage and render both chapters;
7. mark vision calibration legacy and write `IDEX_CALIBRATION.md`;
8. run local syntax/generation/parity checks;
9. deploy the code without changing calibration values; and
10. run one complete physical calibration, accepting only the live verification
    and final readiness report as proof.

Until all stages are implemented and physically accepted, the current scripts
remain operational truth and this file remains a design specification.
