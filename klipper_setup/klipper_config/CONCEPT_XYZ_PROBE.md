# Klipper XYZ Contact Probing — Two-stage Tool Calibration

## Purpose

The multi-head-zero normally-closed contact switch provides repeatable 3D
contact measurements for both IDEX tools. It is deliberately not an endstop.
Klipper's `HomingMove`/`probing_move()` path records the Cartesian trigger
position of every moved stepper; the trigger position is the measurement and
the subsequent halt position is only a mechanical-clearance concern.

Each guarded contact starts at logical `START_Z=4 mm`, approaches at 1 mm/s,
and retracts to that same logical height after either a trigger or an allowed
seed-grid no-contact result. The primitive first lifts upward to machine Z=10
for safe preparation, then selects the requested tool and moves XY once. The
standard `[probe]` remains Z-only and is not involved.

## Commands and artifacts

Use the prescribed local workflow:

```text
scripts/run_multi_head_zero_contact_map.sh
```

It performs the full T0 calibration, T1 calibration, absolute T0/T1 X/Y
rebase plus T1-only Z correction,
deployment/parity check, and nine-contact T0/T1 verification. The only
diagnostic form is `scripts/run_multi_head_zero_contact_map.sh --tool T0` or
`--tool T1`; it collects that single 18-contact calibration and makes no
configuration change. There are no bounds, homing, reference, workflow, or
output-path options.

For a direct console repeatability check, use only:

```gcode
MULTI_HEAD_ZERO_CONTACT TOOL=1 COUNT=10
```

It selects the requested tool, clears an active mesh, uses the configured
logical ball target, and leaves the nozzle at `START_Z` after the final tap.
It requires XYZ to have been homed already. If mechanics may have raised the
ball, raise the guarded-start height without exposing the lower probe limit:

```gcode
MULTI_HEAD_ZERO_CONTACT TOOL=1 COUNT=1 START_Z=20
```

`START_Z` may only increase the configured 4 mm default. It is the caller's
declared safe height above the ball; the fixed logical target remains `Z=-1`.
Optional X/Y are logical diagnostic coordinates. The calibration helper alone
uses its internal no-contact mode for coarse seed points.

Every batch creates a root `batch_manifest.json`, immutable per-tool schema-v4
`manifest.json`/`records.csv` artifacts, and tool-named plots. The prescribed
logical targets are transformed into the active tool's physical machine frame
before each contact. CSV and manifest records retain both logical
`commanded_*`/`trigger_*` values used for fitting and comparison, and the
corresponding `machine_commanded_*`/`machine_trigger_*` values used by the
contact primitive. Every contact also records the active G-code origin,
generated-config fingerprint, zero manual-Z adjustment, physical tool state,
and inactive runtime-mesh state. This makes IDEX offsets explicit instead of
smuggling them into the measurement math.

During a live batch, Klipper's console receives concise `MHZ calibration:`
events for preparation, every tap, tool transitions, centres, deployment, and
the final verification result. The compact live view at
`http://menderpi.local/calibration/` polls an atomically updated status snapshot
once per second. It uses a fixed isometric logical XYZ view: each contact's
vertical stalk starts at that run's lowest completed contact, so the ball shape
is readable without hiding absolute result cards. Completed PNG plots open in a
fullscreen modal. Chapter 1 retains the T0/T1 18-contact calibration plots and
calculations; chapter 2 appends the T0/T1 nine-contact verification and paired
result. The result card presents source, applied, and change values for
`T1−T0` endstop offsets rather than raw T1 endstops. It is a status view only;
immutable run artifacts remain authoritative.

## Ball and IDEX coordinate priors

`calib.yaml` is the single source for the 10 mm ball, its 1 mm front-bed gap,
the convention that Y=0 is 3 mm behind the bed front edge, nominal ball target
`(X=75, Y=-9)`, and the generated calibration seed `X=72…78`, `Y=-12…-6`.
The deployed runner consumes those generated values directly; there is no
command-line override.

The same file records the measured rigid parked-tool clearance: with T0 at
`X=-85.4`, T1 first just clears it at `X=16.0`, so the required nozzle
separation is exactly **101.4 mm**. The derived static limits preserve that
separation without an additional margin. They govern normal single-active-tool
operation, where the other toolhead is parked at its own X endstop.

`[dual_carriage] safe_distance: 10` remains unchanged. It belongs to Klipper's
simultaneous-carriage modes and is not the physical parked-tool clearance
authority for this workflow.

## Calibration: 18 contacts per tool

Calibration is the only workflow that can produce input for an endstop update.
It uses a known 5 mm ball and a 2.8 mm refinement ring. This leaves margin to
the printer's hard front-Y travel limit around the installed ball position.

### Phase 1 — rough summit (10 contacts)

1. Require Klipper-ready XYZ homing. If XYZ is not homed, home exactly once;
   otherwise start immediately. Clear the bed mesh once and require the
   normally-closed switch to be released. Before the workflow and
   before every contact, the runner and Klipper extra both require the manual
   tool state, `_IDEX_TOOL_STATE`, active extruder, and dual-carriage modes to
   agree (`T0`: carriage 0 primary; `T1`: carriage 1 primary). Each contact
   record retains that physical-selection evidence.
2. Contact the generated `X=72…78`, `Y=-12…-6` 3×3 seed pattern. Only these nine
   attempts may yield `no_contact`; retained no-contact records are excluded
   from fitting.
3. Fit completed seed samples to the normalized six-term paraboloid. Require
   at least six completed samples, rank six, acceptable conditioning,
   negative-definite curvature, and a vertex strictly inside the safe envelope.
4. Contact that fitted X/Y vertex. This tenth contact must trigger. Its direct
   logical-frame Z is the calibration `z_max`; the broad paraboloid's fitted Z
   is never used.

The seed is serpentine: `(72,-12) → (75,-12) → (78,-12) → (78,-9) → …`.
It reduces seed travel to 24.000 mm per tool from 31.416 mm while leaving the
measurements and fit unchanged. Contacts never home or select a tool. After
T0's eighteenth contact retracts, the batch lifts to `Z=10.000`, switches once
from T0 to T1, then completes T1's eighteen contacts.

### Phase 2 — ring refinement (8 contacts)

Starting at phase 1's rough `(x_rough, y_rough)`, contact eight equally spaced
points at radius `r=2.8 mm`, angles `0, 45, …, 315°`. All eight contacts must
trigger.

For measured ring heights `z_i`, calculate the first harmonic:

```text
A = (2 / 8) * sum(z_i * cos(theta_i))
B = (2 / 8) * sum(z_i * sin(theta_i))
scale = sqrt(5^2 - 2.8^2) / 2.8

x_refined = x_rough + A * scale
y_refined = y_rough + B * scale
```

The calibration result stores refined X/Y, direct phase-1 summit Z, harmonic
coefficients, and fixed-sphere residuals for all ring measurements. It does
not fit a sphere, alter the known radius, or fall back to another search.

## Applying calibration

After successful T0 and T1 18-contact runs made from the same source config,
run:

```text
scripts/apply_multi_head_zero_maximum_calibration.py \
  --t0-run <t0-calibration-run> \
  --t1-run <t1-calibration-run> \
  --result <calibration_result.json>
```

The helper rejects mismatched provenance and uses the configured ball target
`(75,-9)` as the absolute X/Y datum:

- add `target − measured centre` independently to T0 and T1 X/Y endstops;
- subtract `T1−T0` direct logical-frame summit Z from the T1 Z endstop. T1's
  logical trigger Z is machine Z minus its active origin
  (`T0_z_endstop − T1_z_endstop`), so increasing the T1 endstop would make a
  positive T1−T0 Z residual worse;
- preserve T0 Z, derive the two parked-tool X limits from the corrected
  endstops and the exact 101.4 mm clearance, regenerate `printer.cfg`, and
  write a calibration-result JSON.

That result records the configured target centre, pre-correction centres and
target errors, applied endstop deltas, and target endstops.
The prescribed workflow deploys it and requires parity automatically. The
Klipper restart may invalidate homing, so verification checks XYZ and homes
once only if needed before its own T0-to-T1 batch.

## Verification: nine contacts per tool

Verification is evidence only. It never edits, calculates, or deploys another
calibration.

The runner reads the configured target directly from the generated runtime
priors and runs the same nine-point pattern for each tool under the deployed
configuration:

1. one centre contact exactly at logical `X=75, Y=-9`; and
2. eight mandatory ring contacts at 2.8 mm around exactly that point: east, north-east, north,
   north-west, west, south-west, south, and south-east.

The octagonal ring heights recover each tool's local X/Y centre using the same
eight-point first-harmonic calculation as calibration. The centre contact
supplies the only authoritative logical-frame Z. The raw mean and spread of the
eight peripheral heights remain visible as shape/repeatability diagnostics, but
they are never converted into an inferred summit: the nozzle tip has non-zero
physical dimensions, so the point-probe sphere model is not valid for that
purpose. Pair the resulting T0/T1 manifests with:

```text
scripts/verify_multi_head_zero_alignment.py \
  --t0-run <t0-verification-run> \
  --t1-run <t1-verification-run> \
  --calibration-result <calibration_result.json> \
  --output-dir <verification-report-dir>
```

The report refuses stale configuration provenance, writes JSON/CSV/plot output,
and passes only when all limits hold:

```text
abs(T0 X − 75) <= 0.05 mm
abs(T0 Y + 9) <= 0.05 mm
abs(T1 X − 75) <= 0.05 mm
abs(T1 Y + 9) <= 0.05 mm
abs(T1−T0 X) <= 0.05 mm
abs(T1−T0 Y) <= 0.05 mm
abs(T1−T0 Z) <= 0.02 mm
```

It also reports radial XY error for inspection.

For a repeatability audit, run multiple paired nine-contact batches without
changing configuration or homing between them. Compare the physical centre-Z
contacts in both logical and machine frames. A separate deliberately re-homed
pair distinguishes contact/tool-switch repeatability from homing repeatability;
the peripheral ring is still used only for X/Y and descriptive diagnostics.
