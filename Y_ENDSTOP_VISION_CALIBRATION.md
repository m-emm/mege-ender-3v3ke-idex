# Y Endstop and Vision Calibration Investigation

Status: discussion draft
Date: 2026-08-02

## Purpose

This paper derives one Y diagnostic that answers the practical question:

> If T0 and T1 print the same logical Y coordinate, will the deposited material
> align in Y?

The diagnostic must remain valid when T0 and T1 cannot acquire images at the
same commanded Y. It must use each job's actual commanded acquisition Y, the
bed-fiducial observation, and the nozzle-tip observation. It must also say how
to correct the T1 Y endstop when the diagnostic is nonzero.

The primary evidence is in `resources/calibration_y_shift_data.txt`, together
with the immutable manifests, frame sidecars, and analysis results for the four
printer jobs named below.

This remains a discussion paper. It does not authorize a calibration edit,
deployment, or printer motion.

## Executive Summary

For each tool, define:

```text
tool_y_datum = commanded_acquisition_y + fiducials_to_tip_y
```

Then define the effective T1-to-T0 print-alignment error:

```text
y_alignment_error = t1_tool_y_datum - t0_tool_y_datum
```

Expanded:

```text
y_alignment_error =
    (t1_commanded_y + t1_fiducials_to_tip_y)
  - (t0_commanded_y + t0_fiducials_to_tip_y)
```

This is the requested single Y number.

- `y_alignment_error = 0` means the configured T1 Y compensation matches the
  observed physical T1-to-T0 nozzle separation. The tools should print aligned
  in Y, subject to the validity of the image projection.
- The tools do not need to acquire at the same commanded Y. A change in
  acquisition Y produces the opposite change in the observed
  fiducials-to-tip Y distance, so it cancels in the sum.
- A negative error means the T1 Y endstop must be made less negative by the
  magnitude of the error. A positive error means it must be made more negative.

With T0 fixed, the correction is:

```text
t1_y_endstop_new = t1_y_endstop_current - y_alignment_error
```

Using the two X positions accepted in all four Z=0.5 runs:

| Configuration | Mean Y alignment error | T1 endstop used | Implied corrected T1 endstop |
|---|---:|---:|---:|
| Before | -0.051 mm | -13.800 mm | -13.749 mm |
| After | -1.046 mm | -14.800 mm | -13.754 mm |

The two independent estimates agree at approximately `-13.75 mm`. More
importantly, changing the T1 endstop by `-1.000 mm` changed the measured
alignment error by `-0.995 mm`. This is the expected one-for-one response and
dismisses the earlier suspicion that the T1 endstop change also moved T0.

The current image-to-XY calculation still has a Z limitation. The final
diagnostic should evaluate both tools at a common physical reference Z through
an XYZ-aware projection. The acquisition Y cancellation itself is valid and is
already strongly demonstrated by the supplied data.

## Coordinate Model

### Configured tool offset

The generated printer config uses T0 as the shared Y-axis anchor:

```text
t0_gcode_y_offset = 0
t1_gcode_y_offset = t0_y_endstop - t1_y_endstop
```

For an acquisition command `C_t` and active G-code offset `O_t`, the sidecars
show the internal toolhead Y coordinate as:

```text
A_t = C_t + O_t
```

For example, in the first T1 run:

```text
C_1 = -13.0
O_1 = -1.0
A_1 = -14.0
```

After changing the T1 endstop so that `O_1 = 0`, the unchanged acquisition
command produced `A_1 = -13.0`.

### Image-derived fiducial-to-tip distance

Let `D_t` be the image-derived Y component currently displayed as the second
component of `fiducials_to_tip_mm`.

When the bed moves by `+1 mm` in physical Y while the nozzle remains fixed in
the camera view, the bed fiducials move by one image-Y vector and `D_t` changes
by approximately `-1 mm`. The supplied T1 data demonstrates this directly:

| T1 run | Internal toolhead Y `A_1` | `D_1` at X=193, Z=0.5 |
|---|---:|---:|
| Before | -14.0 | -1.780 mm |
| After | -13.0 | -2.873 mm |

The toolhead coordinate changed by `+1.000 mm`; the observed distance changed
by `-1.093 mm`. The remaining 0.093 mm is an image/model residual, while the
dominant response is the expected opposite sign.

### Why the current `fiducials seen at` formula does not cancel acquisition Y

The current overlay reports:

```text
current_fiducials_seen_y = C_t - D_t
```

If acquisition Y changes by `+delta`, then `D_t` changes by approximately
`-delta`. The current result therefore changes by approximately `+2 * delta`:

```text
(C_t + delta) - (D_t - delta) = C_t - D_t + 2 * delta
```

It amplifies the acquisition-position difference instead of cancelling it.
That is why the current per-tool values cannot answer whether the two tools
will print aligned when their safe acquisition Ys differ.

The required sign is addition:

```text
tool_y_datum = C_t + D_t
```

Then the acquisition command cancels the equal and opposite observation
change.

### Acquisition-invariant physical datum

The combination

```text
M_t = A_t + D_t
```

is invariant to acquisition Y for a fixed physical tool and image model:

```text
A_t changes by +delta
D_t changes by -delta
M_t does not change
```

`M_t` represents the observed physical nozzle Y datum relative to the common
bed-fiducial reference, expressed in the underlying machine coordinate.

The physical relative nozzle separation inferred by vision is:

```text
required_relative_offset = M_1 - M_0
```

The compensation currently supplied by Klipper is:

```text
configured_relative_offset = O_1 - O_0
```

The effective print-alignment error is the difference:

```text
E_y = (M_1 - M_0) - (O_1 - O_0)
```

Substitute `M_t = A_t + D_t` and `A_t = C_t + O_t`:

```text
E_y = [(C_1 + O_1 + D_1) - (C_0 + O_0 + D_0)] - (O_1 - O_0)

E_y = (C_1 + D_1) - (C_0 + D_0)
```

The configured offsets cancel. This is why the diagnostic neither requires
the same acquisition Y nor needs the active G-code offsets as an input.

The active calibration values must still be recorded for provenance and for
calculating the correction, but they are not needed to calculate the error.

## Why Zero Means Printed Y Alignment

When both tools later print the same logical Y coordinate, Klipper applies the
configured relative offset. Vision independently measures the relative nozzle
datum against the same bed fiducials.

If:

```text
required_relative_offset = configured_relative_offset
```

then:

```text
E_y = 0
```

The configured coordinate compensation exactly accounts for the physical
T1-to-T0 nozzle separation. Both tools address the same physical bed Y for the
same logical print Y.

If `E_y` is nonzero, it is the residual effective T1-to-T0 print offset after
the current configuration has been applied.

This is a relative tool-alignment diagnostic. It does not require an absolute
fiducial Y prior because the common fiducial reference cancels between T0 and
T1. An absolute fiducial prior may still be useful for independently placing
both tools in the printer's global bed coordinate system, but it is not needed
to make dual-tool printing align.

## Endstop Correction Rule

With T0 held fixed:

```text
O_0 = 0
O_1 = t0_y_endstop - t1_y_endstop
```

Changing the T1 endstop by `delta` changes its G-code offset by `-delta`.
Therefore it changes the effective alignment error by `+delta`:

```text
E_y_new = E_y_current + delta
```

Set `E_y_new` to zero:

```text
delta = -E_y_current
```

Therefore:

```text
t1_y_endstop_new = t1_y_endstop_current - E_y_current
```

Sign examples:

- If `E_y = -1.000 mm`, add `+1.000 mm` to the T1 endstop; for example,
  `-14.800` becomes `-13.800`.
- If `E_y = +0.250 mm`, subtract `0.250 mm` from the T1 endstop; for example,
  `-13.800` becomes `-14.050`.

This rule assumes T0 is the fixed machine anchor. If both tools are later
calibrated independently to an absolute physical prior, the residual may be
distributed differently, but the relative error definition remains the same.

## Four-Run Evidence

### Comparable observations

`X=193.0` and `X=198.0` at `Z=0.5` were accepted in all four runs.

| Run | Job | Tool | Commanded XYZ | Internal toolhead XYZ |
|---|---|---|---|---|
| Before T0 | `20260802T102805.939979Z-idex_nozzle_fine_xz_grid_t0` | T0 | 193, -14, 0.5 | 193, -14, 0.5 |
| Before T1 | `20260802T103043.637672Z-idex_nozzle_fine_xz_grid_t1` | T1 | 193, -13, 0.5 | 193, -14, 0.6 |
| After T0 | `20260802T103522.226760Z-idex_nozzle_fine_xz_grid_t0` | T0 | 193, -14, 0.5 | 193, -14, 0.5 |
| After T1 | `20260802T103757.906809Z-idex_nozzle_fine_xz_grid_t1` | T1 | 193, -13, 0.5 | 193, -13, 0.6 |

The T1 internal Z is 0.6 because the configured T1 Z offset is 0.1 mm. The Y
diagnostic ultimately needs an XYZ-aware projection so that differing physical
Z does not leak into the Y result.

### X=193 derivation

| Configuration | Tool | Commanded Y `C_t` | Fiducials-to-tip Y `D_t` | Tool datum `C_t + D_t` |
|---|---|---:|---:|---:|
| Before | T0 | -14.000 | -0.722 | -14.722 |
| Before | T1 | -13.000 | -1.780 | -14.780 |
| After | T0 | -14.000 | -0.798 | -14.798 |
| After | T1 | -13.000 | -2.873 | -15.873 |

Therefore:

```text
before E_y = -14.780 - (-14.722) = -0.058 mm
after  E_y = -15.873 - (-14.798) = -1.075 mm
```

### X=198 confirmation

Using the rounded values in the source log:

```text
before E_y = [-13.000 + (-1.761)] - [-14.000 + (-0.717)]
           = -0.044 mm

after  E_y = [-13.000 + (-2.853)] - [-14.000 + (-0.836)]
           = -1.017 mm
```

### Combined result

| Configuration | X=193 error | X=198 error | Mean error |
|---|---:|---:|---:|
| Before | -0.058 | -0.044 | -0.051 mm |
| After | -1.075 | -1.017 | -1.046 mm |

The observed change in alignment error is:

```text
-1.046 - (-0.051) = -0.995 mm
```

The T1 endstop change was:

```text
-14.800 - (-13.800) = -1.000 mm
```

The diagnostic follows the endstop change one-for-one to within 0.005 mm in
the two-point mean. This is exactly the predicted sign and magnitude.

The implied corrected endstops are:

```text
from before: -13.800 - (-0.051) = -13.749 mm
from after:  -14.800 - (-1.046) = -13.754 mm
```

The agreement between these estimates is strong evidence that the formula and
correction sign are correct. It also shows that the initial `-13.800 mm` T1
endstop was already close, whereas changing it to `-14.800 mm` introduced
approximately 1 mm of effective Y misalignment.

No value is applied by this paper. The provisional estimate should be checked
with synchronized deployment and an XYZ-aware or tightly controlled low-Z
analysis before activation.

## Acquisition Y Does Not Need to Match

The supplied data already contains different commanded acquisition Ys:

```text
T0 C_0 = -14
T1 C_1 = -13
```

The raw `fiducials_to_tip_y` values cannot be compared directly because the bed
was acquired at different positions. Adding each command back to its observed
distance normalizes both measurements to a common tool datum.

This is important near travel limits. A tool may be unable to reach the same
logical acquisition Y as the other tool after its offset is applied. The
calibration job may choose any safe, visible, reachable Y for each tool, as long
as all of the following are true:

- the exact commanded Y is recorded;
- the image-Y metric is valid at that acquisition pose;
- both observations refer to the same physical fiducial reference;
- Z is either common in physical space or corrected by the projection model;
- the nozzle tip and fiducials are both reliably localized; and
- no unrecorded coordinate offset is introduced between command and capture.

A useful falsification experiment is to acquire the same tool at two
substantially different reachable Ys. Its raw `D_t` should change by the
negative of the command change, while `C_t + D_t` remains stable. This directly
tests the cancellation without requiring T0 and T1 to share a reachable pose.

## Dismissed T1-to-T0 Coupling Suspicion

The earlier suspicion that changing the T1 Y endstop also moved T0 is dismissed
for these runs.

The evidence is more simply and quantitatively explained by the intended T1
coordinate transform:

- T0 used the same command and reported internal toolhead position in both
  runs.
- Within each tool, before/after manifests used identical frames, fine
  references, facts, and analysis geometry.
- The effective alignment diagnostic changed by `-0.995 mm` in response to a
  T1 endstop change of `-1.000 mm`.
- The T1 sidecars and roughly 10 px fiducial motion directly record the
  corresponding one-millimetre T1 acquisition shift.

There is no need to retain a T1-to-T0 coupling hypothesis or design further
experiments around it based on this dataset.

## Deployment Finding

The four-run experiment also exposed three inconsistent deployed views:

| Consumer | T1 Y endstop or offset | T1 acquisition Y | T1 X endstop |
|---|---:|---:|---:|
| Loaded `printer.cfg` after the change | endstop -14.800, offset 0.000 | n/a | 351.739 |
| DAO `/usr/local/share/vision/calib.yaml` | endstop -15.820 | n/a | 350.516 |
| Deployed `vision_job_types.json` | n/a | -13.000 | n/a |
| Worktree at inspection time | endstop -14.800 | -14.000 | 351.739 |

The overlay's acquisition snapshot came from the stale DAO YAML, not from the
values loaded by Klipper. The intended acquisition-Y change was also not
deployed.

This split did not prevent calculation of `E_y`, because the configured offset
cancels from the formula and the actual command is in the manifest. It does
make provenance misleading and would make an automatic endstop correction
unsafe: the correction must be applied to the endstop actually loaded by
Klipper, not an unrelated stale DAO value.

Before any automated correction, one deployment audit must show agreement
among:

- canonical repository `calib.yaml`;
- generated and loaded `printer.cfg`;
- live Klipper tool-offset macro values;
- deployed DAO `calib.yaml`;
- deployed vision job definition; and
- the acquisition manifest snapshot.

## Remaining Z Limitation

The Y cancellation derivation assumes `D_t` is a valid physical Y distance.
The current implementation obtains it by solving the nozzle-to-fiducial image
delta against an XY basis. It does not explicitly model the Z separation
between nozzle tip and bed fiducials.

Existing data shows that the current derived coordinate changes with Z. At T0
X=193 in the first run:

| Commanded Z | Current `fiducials seen at` X | Current `fiducials seen at` Y |
|---:|---:|---:|
| 0.5 | 166.436 | -13.278 |
| 4.0 | 166.886 | -13.299 |
| 16.0 | 168.663 | -13.400 |

The large X drift proves that the current result is not a general absolute
fiducial coordinate. The differential Y error cancels common geometry much
better, but it still changes somewhat with Z. At X=193, the before-configuration
Y error progresses approximately from `-0.058` at Z=0.5 to `+0.021` at Z=4 and
`+0.125` at Z=16.

The production diagnostic should therefore be defined at a canonical physical
reference Z relevant to printing. There are two implementation approaches to
evaluate:

1. Use only observations near the print plane, with both tools interpreted at
   the same physical nozzle Z.
2. Fit an XYZ-aware projection and evaluate each tool's datum at a declared
   common reference Z, regardless of the Z used for acquisition.

The second is more general. Whichever approach is selected, acquisition Y
normalization remains `C_t + D_t`.

## Hypotheses and Falsification Tests

### H1: `C_t + D_t` is independent of acquisition Y

Evidence: strongly supported by the algebra and by the opposite T1 changes in
internal toolhead Y and observed `D_t`.

Falsification test:

- Hold tool, active calibration, X, physical Z, camera settings, and fiducial
  reference fixed.
- Acquire at two or more different reachable commanded Ys.
- The command-normalized datum `C_t + D_t` must remain constant within the
  internal spread of accepted observations.
- A systematic dependence on acquisition Y would show that the image-Y model
  is pose-dependent or incomplete and must be extended before calibration.

### H2: The endstop correction changes alignment error one-for-one

Evidence: the observed `-1.000 mm` endstop change produced a `-0.995 mm` change
in the two-point mean error.

Falsification test:

- Coherently deploy a reviewed T1 endstop adjustment while holding T0 and the
  analysis model fixed.
- Acquire at any safe recorded Ys and recalculate `E_y`.
- The change in `E_y` must equal the T1 endstop change in sign and magnitude.
- Applying `t1_endstop_new = t1_endstop_current - E_y` must bring the next
  result to zero without changing T0.

### H3: A common physical reference Z removes the remaining Y bias

Evidence: open. The current differential is close at low Z but drifts with Z.

Falsification test:

- Evaluate both tools through a candidate XYZ-aware model at several acquired
  Z positions but one common physical reference Z.
- The resulting `E_y` must not depend systematically on acquisition Z.
- If it still does, inspect tool-specific nozzle-tip projection, camera
  distortion, or the conversion from pixels to printer axes.

### H4: Zero relative error predicts aligned dual-tool printing

Evidence: follows from the coordinate model but should ultimately be validated
against deposited material.

Falsification test:

- After a reviewed vision calibration yields `E_y` near zero, print a simple
  alternating T0/T1 Y-alignment artifact.
- Measure the deposited T0-to-T1 Y displacement independently of vision.
- A significant residual print displacement would identify an unmodelled
  difference between the visible nozzle-tip datum and the extrusion datum.

## Suggested Course of Action

### 1. Add the command-normalized diagnostic

For every accepted observation, record:

```text
commanded_y_mm
fiducials_to_tip_y_mm
tool_y_datum_mm = commanded_y_mm + fiducials_to_tip_y_mm
reference_z_mm
```

For a compatible T0/T1 pair or fitted reference-Z result, publish:

```text
y_alignment_error_mm = t1_tool_y_datum_mm - t0_tool_y_datum_mm
suggested_t1_y_endstop_mm = active_t1_y_endstop_mm - y_alignment_error_mm
```

The result must include the exact active endstop to which the suggestion
applies. A stale DAO value must never be used as that base.

### 2. Make deployment provenance coherent

- Deploy canonical `calib.yaml`, generated `printer.cfg`, and the DAO copy as
  one calibration transaction.
- Record both intended and live Klipper values in the acquisition manifest.
- Resolve acquisition poses from synchronized job definitions.
- Refuse automatic correction when the base endstop in the result differs from
  the value currently loaded by Klipper.

### 3. Make the Y result independent of both acquisition Y and Z

- Keep the proven `commanded_y + fiducials_to_tip_y` normalization.
- Replace the current raw XY-only conversion with an XYZ-aware projection, or
  constrain the first version to a declared near-print-plane physical Z.
- Combine multiple accepted X observations at that reference Z and report
  their individual errors and aggregate, without pinning tunable calibration
  values in tests.

### 4. Keep relative and absolute calibration separate

The relative diagnostic needs no absolute fiducial Y prior. It answers whether
T0 and T1 print aligned with each other.

An absolute fiducial prior is a separate concern: it answers whether the common
T0/T1 coordinate is correctly placed in the printer's global bed coordinate
system. The two should be separate outputs so an absolute-reference problem
cannot be mistaken for inter-tool misalignment.

### 5. Do not apply the provisional value yet

The present low-Z data consistently suggests a T1 Y endstop near `-13.75 mm`,
but the value should remain a documented estimate until:

- deployment inputs are coherent;
- the exact loaded endstop is captured as provenance;
- acquisition-Y cancellation is deliberately verified at two reachable Ys;
- the reference-Z policy is settled; and
- the result is reviewed before activation.

## Discussion Questions

1. Should the first implementation constrain the diagnostic to a low physical
   reference Z, or should it immediately build the full XYZ-aware projection?
2. Should the calibration result only suggest a T1 endstop, or should a
   separately confirmed operation be allowed to write a candidate
   `calib.yaml`?
3. Which printed artifact should independently validate that vision error zero
   corresponds to deposited-material Y alignment?

The central conclusion is no longer tentative:

```text
y_alignment_error =
    (t1_commanded_y + t1_fiducials_to_tip_y)
  - (t0_commanded_y + t0_fiducials_to_tip_y)
```

This is the acquisition-Y-independent number that should be driven to zero.
