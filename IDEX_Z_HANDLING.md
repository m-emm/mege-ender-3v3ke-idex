# IDEX Z Handling: Coordinate Model, Eddy Interaction, and Proposed Architecture

## Status

This is an architecture and investigation document. It describes the current
printer behavior, the relevant Klipper internals, a proposed future design, and
the tests required before that design may control printer motion.

Nothing described as **proposed** below is implemented by this document. In
particular, this document does not change:

- `calib.yaml` or either Z endstop value;
- `printer.cfg.template` or generated `printer.cfg`;
- the `idex_manual_tuning` Klipper extra;
- T0/T1 macros, Eddy calibration, or bed-mesh behavior;
- the live printer.

The active printer may therefore continue to exhibit the problems described
here until a separate implementation and validation task is completed.

## Executive summary

The current implementation combines two conceptually different quantities in
Klipper's `SET_GCODE_OFFSET` state:

1. the calibrated, tool-specific T0/T1 Y and Z geometry; and
2. the temporary adjustment made by an operator in KlipperScreen.

Klipper reports the resulting value as `gcode_move.homing_origin`.
KlipperScreen reasonably presents that as the user's G-code offset. A tool
change therefore changes the displayed offset even when the operator has not
changed anything. Recovering a manual Z adjustment then requires subtracting a
tool offset from a combined value, which is fragile when another macro or
component changes the same Klipper state.

The preferred future architecture is a chained Klipper move transform:

```text
G-code
  -> gcode_move (including the real, user-visible manual offset)
  -> hidden IDEX tool transform
  -> bed_mesh
  -> toolhead and Cartesian/IDEX kinematics
  -> steppers
```

The hidden transform would own only calibrated tool geometry. KlipperScreen's
G-code offset would then start at zero, remain zero across T0/T1 changes, and
show only a real operator adjustment. This is a proposal, not yet a proven
implementation.

Implementation is deliberately divided into two iterations. Iteration 1 first
creates a source-controlled physical and sensor baseline: it uses T0 Eddy tap
at `X=150,Y=150` to establish native Z=0, transfers the same common correction
to T1 while preserving the vision-derived relative alignment, recalibrates
Eddy, and verifies a full mesh against tap. Iteration 2 then addresses hidden
tool geometry, KlipperScreen manual offsets, M220/M221, and print lifecycle
state. Iteration 2 must not begin until Iteration 1 passes.

The Eddy Duo tap mode adds an important physical reference that was not part of
the original analysis. A T0 `PROBE METHOD=tap` does not infer bed height from
the normal frequency-to-distance calibration. It makes nozzle contact, analyzes
the frequency response while pulling away, and reports the contact coordinate
in Klipper's current kinematic frame. Once the known-good tap threshold, tap bias, mechanics,
and repeatability are validated, repeated T0 taps can be the primary absolute
contact reference. The non-contact Eddy calibration and scanned mesh can then
be aligned to that reference instead of being asked to establish absolute
nozzle contact by themselves.

The controlled follow-up now compares both methods at the same physical bed
point near `(92.606,130.997)`. Two regular samples average `+1.1317055 mm`; two
successful taps average `-0.0383835 mm`. The resulting regular-minus-tap datum
mismatch is approximately `+1.170089 mm`. Tap measurements at the original
nozzle point indicate only about `0.041584 mm` of local bed-height difference,
so bed shape cannot explain the large mismatch. The regular Eddy vertical
calibration frame is the leading issue, but no correction should be applied
until the configured threshold and multi-point/temperature behavior are validated.


## Goals and non-goals

The future design is intended to provide these invariants:

- T0/T1 calibrated geometry is invisible in KlipperScreen's G-code-offset UI.
- With no operator adjustment, the displayed X/Y/Z G-code offset is zero for
  both tools.
- A manual Z adjustment has one shared value for the current print and survives
  any number of T0/T1 changes.
- M220 speed and M221 flow overrides survive extruder activation and tool
  changes.
- T0 and T1 use the same physical bed mesh at the corresponding nozzle
  coordinate.
- A new virtual-SD print starts with manual Z at zero and speed/flow at 100%,
  without discarding calibrated tool geometry.
- Logical G-code position does not jump merely because the active tool changes.

This documentation task does **not** itself:

- write or activate a new absolute nozzle-to-bed Z datum on the printer;
- run the planned Eddy drive-current, frequency/height, or mesh
  calibrations;
- replace Klipper's Cartesian or dual-carriage kinematics;
- prove that the endstop experiment was cancelled by bed mesh;
- calibrate T0/T1 relative geometry automatically.

Instead, Iteration 1 below specifies how a future automatic script will measure
the absolute datum from T0 tap, preserve the independently measured T1/T0
relationship, regenerate Eddy calibration in the new frame, and validate bed
mesh. No measured calibration value is selected or applied by this document.

## Current repository state

The source of truth for the active configuration is
[`printer.cfg.template`](klipper_setup/klipper_config/printer.cfg.template) plus
[`calib.yaml`](klipper_setup/klipper_config/calib.yaml), rendered into
[`printer.cfg`](klipper_setup/klipper_config/printer.cfg).

The current custom extra is
[`idex_manual_tuning.py`](klipper_setup/klipper_host/klippy/extras/idex_manual_tuning.py).
Its current behavior is:

- `_capture_current_state()` reads `gcode_move.homing_origin` and calculates
  `manual_z_adjust = homing_origin.z - active_tool_z_offset`;
- `_apply()` writes the sum of static tool Z and manual Z with
  `SET_GCODE_OFFSET`, together with the static Y offset;
- `_apply()` also restores M220 and M221;
- `_reset()` leaves the active static tool Z in `SET_GCODE_OFFSET` while
  clearing only the extension's notion of manual Z.

The relevant code is in
[`IDEXManualTuning._capture_current_state()` and `_apply()`](klipper_setup/klipper_host/klippy/extras/idex_manual_tuning.py#L46-L65).

The generated macro `_IDEX_APPLY_TOOL_OFFSET` delegates static Y/Z to that
extra and then selects a `BED_MESH_OFFSET`. See
[`_IDEX_APPLY_TOOL_OFFSET`](klipper_setup/klipper_config/printer.cfg.template#L895-L917).
The T0 and T1 macros capture state, call `ACTIVATE_EXTRUDER`, select the
carriage, and apply the combined offset. See
[`T0`](klipper_setup/klipper_config/printer.cfg.template#L1055-L1091) and
[`T1`](klipper_setup/klipper_config/printer.cfg.template#L1093-L1129).

The checked-in Eddy section provides the frequency/height calibration,
`descend_z: 0.5`, X/Y offsets, and the known-good `tap_threshold: 5000` with
`tap_z_offset: 0.000`. Iteration 1 treats that source-controlled threshold as
canonical and uses it for every tap. Threshold discovery is not part of this
workflow.

### Why the GUI changes on a tool change

Klipper stores a G-code offset in `GCodeMove.homing_position`. Its status API
returns that array as `homing_origin`. The implementation is visible in
[`GCodeMove.get_status()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/gcode_move.py#L102-L114).

`SET_GCODE_OFFSET` updates both `base_position` and `homing_position`:

```python
delta = offset - self.homing_position[pos]
self.base_position[pos] += delta
self.homing_position[pos] = offset
```

See
[`GCodeMove.cmd_SET_GCODE_OFFSET()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/gcode_move.py#L207-L226)
or the
[same code at the pinned upstream revision](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/gcode_move.py#L207-L226).

The UI is not misinterpreting a private IDEX field. It is displaying the value
Klipper explicitly labels as the G-code homing origin. The architectural error
is putting calibrated tool geometry in that field.

### Why the current manual-Z recovery is fragile

The current extension assumes:

```text
homing_origin.z = active static tool Z + shared manual Z
```

It can recover `manual Z` only while that equation is the complete history of
the field. It becomes ambiguous if any of the following writes, restores, or
consumes that G-code-offset state:

- KlipperScreen baby-stepping;
- a start, layer, or tool-change macro;
- slicer G-code;
- `Z_OFFSET_APPLY_PROBE`;
- a saved/restored G-code state;
- another custom extension.

The live observation of a combined offset that did not equal only the expected
static tool value plus the extension's remembered manual value is evidence that
this ambiguity is not merely theoretical.

### Speed and flow are related but separate

M220 and M221 are not geometric transforms. They are nevertheless affected by
the T0/T1 sequence because Klipper resets the active extruder's extrusion factor
when `ACTIVATE_EXTRUDER` emits `extruder:activate_extruder`.

In
[`GCodeMove._handle_activate_extruder()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/gcode_move.py#L75-L78),
Klipper resets `extrude_factor` to `1.0`. The future implementation must still
capture M220/M221 before activation and restore them afterwards. That state does
not belong in the geometric transform itself, but it can remain managed by the
same `idex_manual_tuning` extra.

## Coordinate layers

The word "position" is overloaded. A useful investigation must identify the
coordinate layer being observed or changed.

| Layer | Meaning | Typical source |
|---|---|---|
| MCU steps | Integer step count known by an MCU for each stepper | `GET_POSITION` `mcu:` |
| Stepper position | MCU count converted through rotation distance, microsteps, direction, and commanded-position state | `GET_POSITION` `stepper:` |
| Kinematic position | Cartesian position calculated from the active rails | `GET_POSITION` `kinematic:` |
| Toolhead position | Position at the bottom of the move-transform chain | `GET_POSITION` `toolhead:` |
| Transform input/output | Logical position before and corrected position after each move transform | `gcode_move`, future IDEX transform, `bed_mesh` |
| G-code internal position | `GCodeMove.last_position` | `GET_POSITION` `gcode:` / status `position` |
| G-code base | Coordinate-system origin used to derive reported G-code coordinates | `GET_POSITION` `gcode base:` |
| G-code homing origin | User-visible offset maintained by `SET_GCODE_OFFSET` | `GET_POSITION` `gcode homing:` / status `homing_origin` |
| Reported G-code position | `last_position - base_position` | M114 / status `gcode_position` |
| Eddy sensor height | Coil-to-bed distance inferred from measured frequency | `probe_eddy_current` |
| Probe result | Kinematic toolhead position combined with sensor and configured X/Y offsets | probing API |
| Mesh correction | Interpolated Z value at a mesh lookup coordinate | `bed_mesh.ZMesh.calc_z()` |

### Interpreting the captured `GET_POSITION`

The supplied example was:

```text
mcu: stepper_x:-8654 stepper_y:-3392 stepper_z:-68561 stepper_z1:-70175 dual_carriage:-2
stepper: stepper_x:149.997500 stepper_y:148.812500 stepper_z:2.950000 stepper_z1:2.950000 dual_carriage:353.087000
kinematic: X:149.997500 Y:148.812500 Z:2.950000
toolhead: X:150.000000 Y:148.815000 Z:2.950599 E:684.467700
gcode: X:150.000000 Y:148.815000 Z:2.924000 E:684.467700
gcode base: X:0.000000 Y:-1.185000 Z:0.924000 E:542.357820
gcode homing: X:0.000000 Y:-1.185000 Z:0.924000
```

This output supports several observations, but not every possible conclusion:

- The two Z steppers report the same converted position even though their raw
  MCU counts differ. Each stepper has its own count-to-commanded-position
  relationship and homing history.
- `kinematic.z` is the Cartesian Z obtained from the configured Z rail.
- `toolhead.z` differs slightly because it is the physical toolhead position
  after downstream movement processing.
- `gcode.z` is the internal transform-side position, not the final user-facing
  G-code coordinate.
- `gcode base.z` and `gcode homing.z` contain the combined offset state. In this
  example, `2.924 - 0.924 = 2.000`, so the reported G-code Z is 2 mm.
- The Y base/homing value of `-1.185` is tool geometry exposed through the same
  mechanism that the UI uses for manual tuning.

### What raw MCU counts can prove

If the physical endstops do not move, the motors do not lose steps, and no new
homing operation redefines the commanded-position mapping, returning to the
same raw MCU counts means returning to the same motor positions. This is useful
for verifying a reversible T0 -> T1 -> T0 compensation sequence.

Raw counts must be treated as **session-relative evidence**, not a portable
absolute coordinate:

- homing re-establishes commanded positions at physical switch locations;
- firmware restart or MCU reset can reset counters and clock relationships;
- Klipper converts historic MCU positions using each stepper's configured and
  homed state;
- Z and Z1 may have different absolute raw counts while representing the same
  gantry coordinate;
- skipped steps or mechanical movement with motors disabled break the physical
  correspondence.

The correct protocol is therefore:

1. home once;
2. record a post-home `GET_POSITION` baseline;
3. perform the operation under test without rehoming or disabling motors;
4. return to the same logical test point;
5. compare raw-count **deltas** and converted positions to that baseline.

## Eddy Duo and bed mesh

### What Eddy measures

Eddy calibration stores frequency/height pairs. At runtime Klipper adjusts the
measured frequency for thermal drift, locates the surrounding calibration
samples, and interpolates a sensor height. See
[`EddyCalibration.apply_calibration()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L61-L83)
and the
[pinned upstream implementation](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/probe_eddy_current.py#L61-L83).

The result is a distance inferred from frequency. Eddy does not directly
observe the mechanical top Z endstop or a nozzle touching the bed. Klipper
combines the inferred sensor height with the kinematic toolhead position and
configured probe offsets to create a probe result in
[`probe_results_from_avg()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L538-L551).

During `METHOD=scan`, Klipper obtains the kinematic position corresponding to
the sample time from past MCU stepper positions, then combines it with the
frequency-derived sensor height. See
[`EddyScanningProbe._lookup_toolhead_pos()` and `_analyze_scan()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L951-L961).

This confirms the important part of the working model: an Eddy scan is not an
independent absolute measurement of where the top endstop "really" is. It
combines a relative sensor distance with Klipper's current kinematic coordinate
model.

### What Eddy tap measures

Tap uses a different path from regular and scan probing. The toolhead descends
until the Eddy signal's derivative crosses the configured `tap_threshold`, then
lifts away. Klipper correlates frequency samples with historic kinematic Z
positions, fits the free-air and bed-depression portions of that pullback, and
estimates the Z position where the nozzle broke contact with the bed. See
[`EddyTap`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L649-L932),
especially
[`EddyTap._analyze_pullback()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L862-L900),
or the
[pinned upstream implementation](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/probe_eddy_current.py#L862-L900).

The reported value is:

```text
reported_tap_z = fitted_contact_z - tap_z_offset
```

`tap_z_offset` is intended for a repeatable tap bias such as backlash, thermal
expansion, or systemic contact-detection bias. It must not silently absorb T1
relative geometry, a bed mesh, or an operator baby-step. See the
[`tap_z_offset` configuration reference](klipper_setup/rp2040_firmware/klipper/docs/Config_Reference.md#L2358-L2371).

For tap requests Klipper reports zero probe XYZ offsets, so the result is at
the current nozzle XY rather than at the offset Eddy coil XY. That dispatch is
implemented in
[`PrinterEddyProbe.get_offsets()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L1074-L1092).

Tap is consequently a substantially better T0 absolute-contact observation
than a non-contact scan:

- it includes the current T0 nozzle geometry;
- it detects physical nozzle/bed contact rather than extrapolating from a
  coil-to-bed distance;
- it does not use the main frequency-to-height calibration and therefore does
  not inherit that calibration's thermal drift;
- it still depends on clean contact surfaces, Z mechanics, threshold quality,
  contact/depression behavior, and the configured `tap_z_offset`.

Klipper's Eddy guide describes the same distinction and warns that the nozzle
should begin roughly 3-20 mm above the bed, both nozzle and sensor must remain
over the bed, and the nozzle/bed must be clean. See
[`Eddy_Probe.md` tap method](klipper_setup/rp2040_firmware/klipper/docs/Eddy_Probe.md#L149-L209)
or the
[pinned upstream guide](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/docs/Eddy_Probe.md#L149-L209).

### Interpreting the observed tap/probe pair

The observed results were:

```text
Result: at 92.606,130.997 estimate contact at z=1.097861
PROBE METHOD=probe
Result: at 149.997,149.994 estimate contact at z=-0.098499
```

Their reported Z difference is:

```text
1.097861 - (-0.098499) = 1.196360 mm
```

It is not yet valid to call that `1.196360 mm` a tap-versus-probe calibration
error. The XY difference exactly matches the configured T0 nozzle-to-coil
offset:

```text
149.997 - 92.606 = 57.391 mm
149.994 - 130.997 = 18.997 mm

configured x_offset = -57.391 mm
configured y_offset = -18.997 mm
```

This is strong evidence that the two commands were executed at one toolhead
pose, but reported two different physical bed locations:

- tap reported contact under the nozzle at approximately
  `(149.997, 149.994)`;
- regular Eddy probing reported the estimated bed contact under the coil at
  approximately `(92.606, 130.997)`.

The output is therefore consistent with Klipper's probe-result model:
`create_probe_result()` adds the configured X/Y probe offsets to the test
position, while tap bypasses them. See
[`manual_probe.create_probe_result()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/manual_probe.py#L8-L22).

`METHOD=probe` is also not a special Eddy method in this pinned Klipper version.
Only `scan`, `rapid_scan`, and `tap` receive special Eddy parameter handling.
Any other method string falls back to the regular descend probe path. See
[`EddyParameterHelper.get_probe_params()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L1011-L1034)
and
[`PrinterEddyProbe._start_descend_wrapper()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L1082-L1092).
The regular path descends until the frequency corresponding to `descend_z` and
then estimates the bed-contact coordinate using the frequency-to-height table.
It is not a second physical nozzle-contact method.

### Same-physical-point comparison

Tap and regular Eddy results must be compared at one **bed coordinate**, not at
one toolhead coordinate.

Let the desired physical bed comparison point be `P = (Px, Py)`, and let the
configured regular probe offsets be `(ox, oy)`. Then:

```text
tap nozzle/toolhead XY = (Px, Py)
regular-probe nozzle/toolhead XY = (Px - ox, Py - oy)
```

For the current offsets `(-57.391, -18.997)`, a comparison at bed point
`(150, 150)` requires:

```text
tap toolhead XY = (150.000, 150.000)
regular-probe toolhead XY = (207.391, 168.997)
```

Both poses must first be checked against carriage limits and bed coverage. The
comparison point should be chosen so the nozzle and Eddy sensor are safely over
the bed in both poses.

The comparison must also hold constant:

- T0 as the active tool;
- one Z homing session and enabled motors;
- zero visible G-code offset;
- hidden tool state;
- mesh inactive, unless a later test explicitly accounts for it;
- bed, nozzle, and Eddy temperatures;
- nozzle cleanliness and bed cleanliness;
- approach direction, probe speed, sample count, and tap threshold.

Only then is this residual meaningful:

```text
delta_eddy_to_tap(P) = regular_probe_z(P) - tap_z(P)
```

Repeat at the same point first, then at several points. A constant residual
suggests a vertical calibration translation. A residual varying with XY points
to mesh shape, gantry twist, bed deflection, coil/nozzle XY calibration, or
mechanical repeatability instead. A residual varying with temperature points to
Eddy drift or thermal mechanics.

### Controlled follow-up measurements

The follow-up console sequence performs the missing same-physical-point test.
It uses two bed points:

```text
P1 = approximately (92.606, 130.997)
P2 = approximately (149.997, 149.994)
```

At toolhead XY near `(149.997,149.994)`, regular probing reports P1 because the
Eddy coil is offset by `(-57.391,-18.997)`. Moving the toolhead/nozzle to P1 and
then tapping measures that same P1 with physical nozzle contact.

The results group as follows:

| Physical bed point | Method | Contact Z results (mm) | Mean (mm) | Span (mm) |
|---|---|---:|---:|---:|
| P1 `(92.606,130.997)` | regular frequency probe | `1.141738`, `1.121673` | `1.1317055` | `0.020065` |
| P1 `(92.606,130.997)` | nozzle tap | `-0.038148`, `-0.038619` | `-0.0383835` | `0.000471` |
| P2 `(149.997,149.994)` | nozzle tap | `-0.072990`, `-0.086945` | `-0.0799675` | `0.013955` |

The paired P1 regular-minus-tap residuals are:

```text
1.141738 - (-0.038148) = 1.179886 mm
1.121673 - (-0.038619) = 1.160292 mm

mean delta_eddy_to_tap(P1) = 1.170089 mm
pair-to-pair range          = 0.019594 mm
```

The tap-observed local bed difference is much smaller:

```text
tap_mean(P2) - tap_mean(P1)
    = -0.0799675 - (-0.0383835)
    = -0.041584 mm
```

These data support the following conclusions:

1. The original approximately 1.2 mm disagreement is not primarily the bed
   height difference between the nozzle and coil locations. Tap sees only about
   0.042 mm difference between P1 and P2 in this sample.
2. At P1, tap is extremely repeatable across the two successful samples
   (`0.000471 mm` span), while regular Eddy varies by about `0.020 mm`.
3. The approximately `1.170 mm` P1 residual is dominated by a vertical datum
   mismatch between the regular frequency/height calibration and physical tap
   contact.
4. The current evidence does not yet prove that the residual is globally
   constant. There are only two regular samples at one same-point location.
5. P2 tap repeatability is worse than P1, and one P2 attempt failed validation.
   Tap threshold, contact mechanics, and sample procedure therefore still need
   characterization before tap can automatically set a datum.

The failed tap reported:

```text
Unable to detect tap: invalid depress distance
(0.026808 vs 0.030000:0.250000)
```

Klipper requires the fitted contact position to be between 0.030 and 0.250 mm
above the lowest depression position. This attempt missed the lower bound by
`0.003192 mm`. The rejection is a valuable safety result: Klipper did not
silently accept a contact fit outside its validity range. It may indicate early
triggering, insufficient/variable bed depression, contact mechanics, noise, or
the configured threshold or contact mechanics. It is not evidence that lowering the configured
minimum would be safe.

The known-good `TAP_THRESHOLD=5000` is canonical in `calib.yaml`. Iteration 1
does not rediscover or mutate it; threshold changes are an out-of-band
maintenance decision, not a phase of this workflow. The configuration
reference notes that increasing the threshold reduces early noise triggers but
increases the risk of failing to stop promptly at contact, so it should not be
adjusted casually to eliminate one rejected sample.

### What the measured residual means

At P1, tap says physical T0 contact occurs near kinematic Z `-0.0384`. Regular
Eddy says the bed contact estimate is near `+1.1317`. For the regular result to
match tap at that point, the regular frequency/height mapping would need to
report approximately `1.1701 mm` more sensor/nozzle gap at the measured
frequency, which lowers the resulting bed-contact estimate by the same amount.

In the calibration-translation notation used later in this document:

```text
delta_eddy_to_tap = regular_probe_z - tap_z
                  = +1.170089 mm

h = tap_z - regular_probe_z
  = -1.170089 mm

calibrated_height_new = calibrated_height_old - h
                      = calibrated_height_old + 1.170089 mm
```

This is an explanation of the current data, not a value to apply. Directly
adding `1.170089 mm` to the checked-in calibration would be premature because:

- the regular-probe residual has not been mapped at multiple XY points and
  temperatures;
- the existing frequency/height calibration may have been generated under the
  combined static/manual G-code-offset architecture;
- the known-good `tap_threshold: 5000` is not evidence that the regular-probe
  residual is spatially or thermally constant;
- a full Eddy recalibration may be more correct than translating a calibration
  whose provenance is uncertain.

### Reconciliation decision tree

Use this order to remove the discrepancy without hiding its cause:

1. **Verify the current canonical baseline.** Require matching
   source/generated/live configuration, zero visible offsets, T0 active, mesh
   clear, and valid vision-relative T1/T0 provenance.
2. **Bootstrap tap at center.** Use the known-good threshold from `calib.yaml`
   to obtain a repeatable T0 contact estimate at `(150,150)`.
3. **Establish native Z=0.** Apply the measured common endstop delta to both
   tools, preserving the vision-derived relative alignment, then verify center
   tap after restart.
4. **Recalibrate Eddy in the new frame.** Calibrate and deploy drive current,
   restart, prove the center tap invariant with three taps and a full
   `GET_POSITION` snapshot, and only then run
   `PROBE_EDDY_CURRENT_CALIBRATE` using native center Z=0 as the contact
   reference. Repeat the same three-tap and full-position evidence after the
   new frequency curve is deployed, then require a regular Eddy `PROBE` at the
   same reference point to report approximately Z=0 as well. The regular-probe
   result uses the same ±0.020 mm center-reference gate and is recorded before
   I1.5 can be committed.
5. **Re-anchor and compare methods.** Recheck center tap with the configured
   threshold and compare tap/regular Eddy at identical physical points. A full
   recalibration is preferred over translating an uncertain old curve.
6. **Generate the mesh.** Scan the full configured domain with `(150,150)` as
   its zero reference and keep the result active only in Klipper memory.
7. **Verify through the inverse mesh.** At every safe Tap point, require
   `raw_tap_z - mesh_correction_z` to be near zero.

This sequence treats the approximately `1.170 mm` value as a diagnostic of the
current calibration frame, not as another invisible print offset.

### What `METHOD=scan` is intended to do

Klipper documents scan probing as keeping Z fixed while measuring coil-to-bed
distance at each XY location. It explicitly calls out relative measurements
with `zero_reference_position` as a useful application. See the repository's
[`Eddy_Probe.md`](klipper_setup/rp2040_firmware/klipper/docs/Eddy_Probe.md#L65-L111)
or the
[pinned upstream document](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/docs/Eddy_Probe.md#L65-L111).

Temperature matters: the bed, coil, electronics, and nearby metal can shift the
measurement. Calibration and comparison scans should therefore be performed at
controlled, recorded temperatures.

### How bed mesh transforms moves

`BedMesh` registers itself as the initial G-code move transform by calling
`gcode_move.set_move_transform(self)`. See
[`BedMesh.__init__()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/bed_mesh.py#L86-L133)
and the
[pinned upstream source](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/bed_mesh.py#L86-L133).

Its two sides are intentionally inverse operations:

- `BedMesh.move()` accepts a pre-mesh position, calculates or interpolates the
  required Z adjustment, and forwards corrected moves to `toolhead.move()`;
- `BedMesh.get_position()` starts with physical toolhead position and subtracts
  the active mesh adjustment to recover the pre-mesh position.

See
[`BedMesh.get_position()` and `move()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/bed_mesh.py#L181-L220).

### Mesh lookup offsets

`BED_MESH_OFFSET X=<x> Y=<y>` changes where an XY position looks into the same
mesh. The actual lookup uses:

```text
mesh_x = input_x + mesh_offset_x
mesh_y = input_y + mesh_offset_y
```

See
[`ZMesh.calc_z()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/bed_mesh.py#L1427-L1437).

`BED_MESH_OFFSET ZFADE=<z>` is separate. It adjusts the Z value used to
calculate mesh fade and does not add a constant value to the mesh matrix. See
[`BedMesh.cmd_BED_MESH_OFFSET()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/bed_mesh.py#L277-L288).

For the future hidden IDEX transform, a target tool's mesh offset must be
selected **before** making the physical tool-compensation move. Otherwise that
move would be evaluated using the previous tool's mesh lookup coordinates.

### Zero-reference normalization

For an in-mesh zero reference, Klipper evaluates the mesh at the configured
reference coordinate and subtracts that value from every probed and
interpolated matrix entry:

```python
offset = self.calc_z(xpos, ypos)
for matrix in [self.probed_matrix, self.mesh_matrix]:
    for every entry:
        entry -= offset
```

See
[`ZMesh.set_zero_reference()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/bed_mesh.py#L1409-L1418)
and the
[pinned upstream source](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/bed_mesh.py#L1409-L1418).

This makes the mesh correction zero at the reference point and preserves
surface variation relative to that point. A uniform shift in all raw mesh
values is removed from the stored mesh shape.

That source behavior does **not**, by itself, establish that changing
`position_endstop` must have no physical effect at logical Z=0. At the mesh zero
reference, the mesh correction is zero; the physical meaning of commanded Z=0
still depends on homing, endstop coordinates, transform state, and any G-code
offsets. The printer observation and the source-derived expectation therefore
do not yet agree. The discrepancy must be measured rather than resolved by
assumption.

### The unresolved endstop experiment

The trial changed both Z calibration values by +0.05 mm:

```text
T0 293.500 -> 293.550
T1 292.226 -> 292.276
```

The relative T1/T0 difference remained 1.274 mm. The intended result was to
lower both physical nozzles by 0.05 mm at a given logical Z. The expected
improvement was not observed.

Possible explanations include, but are not limited to:

- another G-code offset changed at the same time;
- a mesh profile, zero-reference operation, or start macro changed between
  comparisons;
- the compared points were not the same physical XY point;
- a tool-specific offset or mesh lookup offset masked the comparison;
- the physical difference was smaller than the test method could resolve;
- homing repeatability, Z backlash, stiction, or thermal conditions dominated;
- the generated or live configuration did not match the assumed source at one
  of the observations.

## Implementation roadmap

The Z correction is split into two deliberately ordered iterations.

### Iteration 1: automatic physical and sensor baseline

Iteration 1 establishes a clean physical coordinate system before changing
operator, slicer, layer-change, or tool-change offset handling. Its output is a
source-controlled printer configuration in which:

- validated T0 Eddy tap contact at bed center `X=150`, `Y=150` is native Z=0;
- T1 preserves the existing vision-determined relative Z alignment to T0;
- Eddy drive current and frequency/height calibration are regenerated in that
  coordinate frame;
- the bed mesh uses `(150,150)` as its zero-reference point;
- a fresh full scan is active in memory for verification and is neither saved
  to configuration nor checked into the repository;
- tap contact, converted through the mesh inverse, is near logical Z=0 across
  the tap-safe validation region.

Iteration 1 does not fix KlipperScreen offset display, T0/T1 hidden-transform
handling, M220/M221 persistence, or slicer interactions. Those belong to
Iteration 2.

### Iteration 2: operator, G-code, and printing behavior

Iteration 2 implements the hidden IDEX transform described later in this
document. It starts only after Iteration 1 has produced a passing physical
baseline. This ordering prevents UI/G-code offset logic from masking a sensor
or native-coordinate error.

## Iteration 1 automatic calibration script

### Execution model

Add a repository-side Python orchestrator:

```text
klipper_setup/klipper_config/calibrate_idex_bed_surface_eddy_tap.py
```

It runs from the canonical repository checkout on the Mac because it must
atomically update `calib.yaml`, regenerate `printer.cfg`, and invoke
`update_menderpi.sh`. Printer operations are sent through Moonraker on
`menderpi`; the implementation may use SSH to call Moonraker at
`http://127.0.0.1:7125`, matching existing repository calibration scripts.

One explicit physical-safety confirmation arms the run. After confirmation,
the workflow is automatic across its planned Klipper restarts. It may pause
only on a failed safety/acceptance gate; it must never ask an operator to choose
a calibration value during the run.

Command-line API:

```text
cd /Users/mege/git/mege-ender-3v3ke-idex
python3 klipper_setup/klipper_config/calibrate_idex_bed_surface_eddy_tap.py \
  --step tap-baseline \
  --run-dir runs/idex_z_iteration_1/my-run \
  --host pi@menderpi.local \
  --yes
```

Every workflow operation is available as a single `--step` invocation. The
same `--run-dir` is reused for related commands; it contains the immutable
pre-run snapshots, `state.json`, and phase evidence. A run directory can be
named explicitly as above, or omitted for `--step run` to create a timestamped
directory under `runs/idex_z_iteration_1/`.

The supported steps are:

| Step | Operation |
| --- | --- |
| `preflight` | Validate source, generated configuration, deployment checks, and live idle state |
| `bootstrap-tap` | Home and acquire the guarded seven-tap center baseline |
| `update-endstops` | Apply the saved bootstrap median to both native endstops and deploy |
| `center-verify` | Verify five center taps at native Z=0 |
| `tap-baseline` | Run `bootstrap-tap`, `update-endstops`, and `center-verify` in sequence |
| `drive-current` | Run the Eddy drive-current calibration and deploy its result |
| `eddy-frequency` | Run the guarded Eddy height/frequency calibration, including pre/post three-tap references and a post-calibration regular Eddy `PROBE` Z=0 check |
| `reanchor` | Repeat the post-Eddy center verification |
| `mesh` | Scan, activate, and validate the transient default mesh |
| `run` | Execute the complete fresh Iteration 1 workflow |
| `resume` | Continue from the last committed phase in `state.json` |

For example, the normal operator-controlled sequence can be run as individual
one-liners:

```text
(cd /Users/mege/git/mege-ender-3v3ke-idex && python3 klipper_setup/klipper_config/calibrate_idex_bed_surface_eddy_tap.py --step tap-baseline --run-dir runs/idex_z_iteration_1/my-run --host pi@menderpi.local)
(cd /Users/mege/git/mege-ender-3v3ke-idex && python3 klipper_setup/klipper_config/calibrate_idex_bed_surface_eddy_tap.py --step drive-current --run-dir runs/idex_z_iteration_1/my-run --host pi@menderpi.local)
(cd /Users/mege/git/mege-ender-3v3ke-idex && python3 klipper_setup/klipper_config/calibrate_idex_bed_surface_eddy_tap.py --step eddy-frequency --run-dir runs/idex_z_iteration_1/my-run --host pi@menderpi.local)
(cd /Users/mege/git/mege-ender-3v3ke-idex && python3 klipper_setup/klipper_config/calibrate_idex_bed_surface_eddy_tap.py --step reanchor --run-dir runs/idex_z_iteration_1/my-run --host pi@menderpi.local)
(cd /Users/mege/git/mege-ender-3v3ke-idex && python3 klipper_setup/klipper_config/calibrate_idex_bed_surface_eddy_tap.py --step mesh --run-dir runs/idex_z_iteration_1/my-run --host pi@menderpi.local)
```

Use `--yes` on a supervised run to bypass only the arming prompt. The existing
`--resume <run-directory>` and `--rollback <run-directory>` forms remain
available for compatibility.

Additional interfaces:

- `--dry-run`: run all source/live/preflight and pose calculations without
  heating, moving, probing, writing, deploying, or restarting;
- `--resume <run-directory>`: continue from the last committed phase boundary
  after revalidating source hashes and live state;
- `--rollback <run-directory>`: restore the pre-run canonical files and deploy
  them through the normal updater;
- `--yes`: bypass only the typed confirmation for an already supervised run;
  it does not bypass any machine safety gate;
- `MENDERPI_HOST`: retains the repository's existing host override convention.

The center is not a casual CLI tuning option. Iteration 1 defines the canonical
absolute reference as:

```text
T0 nozzle reference X = 150.000 mm
T0 nozzle reference Y = 150.000 mm
desired tap contact Z = 0.000 mm
```

For an interactive printer-side measurement at that reference, the generated
configuration provides:

```text
EDDY_TAP_MEASURE
EDDY_TAP_MEASURE THRESHOLD=5100
EDDY_TAP_MEASURE COUNT=3 THRESHOLD=5100
```

The default is seven taps and the threshold defaults to the canonical value in
`calib.yaml`. The extra moves to the generated reference point, requires XYZ
homing, and reports each contact result plus mean, median, minimum, maximum,
span, and population standard deviation in the Klipper console. It reports the
post-retract toolhead Z separately for diagnostic comparison; statistics use
the tap contact result.

After the tap series, it reads the configured regular Eddy X/Y offsets and
places the coil over the same physical bed point. For example, with the
current offsets `(-57.391,-18.997)`, a tap at `(150,150)` requires the nozzle
at `(207.391,168.997)` for the comparison probe. The extra reports the regular
probe result beside the tap median and includes their signed difference. If
that derived nozzle pose is outside the current homed motion limits, the tap
statistics remain valid and the regular comparison is skipped with a warning.
The macro does not clear mesh or visible offsets; it measures the current
coordinate state.

### Canonical calibration data

Extend `calib.yaml` and the generator so Iteration 1 data has one authoritative
home. The design should represent, at minimum:

```yaml
bed_z_reference:
  x: 150.000
  y: 150.000

eddy_relative_calibration:
  klipper:
    reg_drive_current: <measured integer>
    calibrate: <measured height:frequency table>
    tap_threshold: 5000
    tap_z_offset: 0.000

```

The generator uses `bed_z_reference` for the configured
`zero_reference_position`. Mesh bounds, probe count, interpolation, and scan
motion settings remain normal source-controlled configuration. Measured mesh
points are runtime data: no `[bed_mesh default]` section, point matrix, or
measured profile is added to `calib.yaml`, the template, or generated
`printer.cfg`.

`tap_z_offset` remains zero in Iteration 1. The native endstop is intentionally
calibrated to the contact definition produced by the final verified tap
algorithm. A later physical-bias study may justify a nonzero `tap_z_offset`, but
it must not be introduced during this baseline workflow.

The template's current literal `zero_reference_position: 170,170` is replaced
by the generated `(150,150)` reference. No second center constant may remain in
the script or template.

Print startup treats bed shape as ephemeral sensor data. It clears any prior
mesh, runs a fresh full Eddy scan, verifies that the resulting mesh is active,
and then starts printing with that in-memory mesh. It must not load a saved
profile, issue `BED_MESH_PROFILE SAVE`, call `SAVE_CONFIG`, or source measured
mesh points from the repository. A scan failure aborts print startup rather
than falling back to an older mesh.

### Source-control and `SAVE_CONFIG` policy

The script must not call `SAVE_CONFIG`. Klipper calibration commands expose
proposed values through `configfile.save_config_pending_items`; the orchestrator
must read and validate those values, write them into canonical `calib.yaml`,
regenerate `printer.cfg`, and deploy with `update_menderpi.sh`.

This policy applies to:

- `reg_drive_current`;
- the Eddy `calibrate` frequency/height table;
- the known-good `tap_threshold` read from `calib.yaml` (not generated by this
  workflow).

Klipper's `BED_MESH_CALIBRATE` automatically makes the new mesh active, stores
a session-local profile, and stages `[bed_mesh default]` in
`configfile.save_config_pending_items`. The script must classify that mesh
entry as transient runtime state: record it as run evidence, never copy it into
canonical files, and never invoke `SAVE_CONFIG`. Before scanning, pending
configuration must still be empty. After scanning, the only permitted pending
item is the just-generated bed mesh; any Eddy, endstop, or unrelated pending
item is an abort condition. Restarting Klipper discards the transient mesh and
its pending save state.

Every actual deployment is followed by `update_menderpi.sh --check`. A
calibration phase is not committed until source, generated config, deployed
hashes, active fingerprint, pinned Klipper commit, Klippy readiness, and
absence of pending `SAVE_CONFIG` items all agree. The scan/verification phases
make no deployment and use the explicit transient-mesh exception above.

### Durable run state and evidence

Each run writes an ignored artifact directory:

```text
runs/idex_z_iteration_1/<UTC-run-id>/
```

It contains:

- an atomic `state.json` state-machine checkpoint;
- pre-run and per-phase copies/hashes of `calib.yaml` and `printer.cfg`;
- Moonraker status snapshots before and after every command;
- every G-code command and result with monotonic and wall-clock timestamps;
- all tap successes and failures, including fitted-depression diagnostics;
- drive-current and frequency-height pending values;
- mesh matrices and mesh configuration;
- raw and mesh-corrected tap verification tables;
- temperatures and stability windows;
- final Markdown and JSON reports.

An automatic resume is allowed only at a committed phase boundary. If a run was
interrupted while a probe, calibration, movement, or deployment was in
progress, resume first aborts any manual probe, raises Z if safe, rehomes, and
repeats that phase from its beginning.

### Preflight and safety contract

Before motion, the script verifies:

- local working tree changes are either only its own run artifacts or explicitly
  accepted; it refuses overlapping edits to calibration/config/deployment files;
- generated config passes `generate_printer_cfg.py --check`;
- `update_menderpi.sh --check` proves source/live parity;
- Klipper is ready, idle, not paused, and not printing from virtual SD;
- no manual probe or `SAVE_CONFIG` change is pending;
- T0 is available and all required macros/commands are registered;
- physical Z endstops remain authoritative;
- X/Y/Z limits permit every calculated nozzle and coil pose;
- the bed is clear and the operator has typed the exact arming phrase;
- nozzles and bed are clean;
- the cold-baseline limits are satisfied: heater targets are zero, bed is at or
  below 40 C, nozzles are at or below 50 C, and Eddy temperature is stable to a
  maximum 0.25 C range over 120 seconds;
- `position_min` allows the guarded tap descent;
- the active tool is T0, the mesh is clear, and visible G-code X/Y/Z offsets
  are exactly zero.

All tap phases start with the nozzle 5 mm above the expected bed. A concurrent
watchdog monitors Klipper state, Z motion, command timeout, and shutdown events.
It sends `M112` if Z passes the configured emergency floor, Klipper leaves
ready state unexpectedly, or a tap fails to stop within its bounded time.

The threshold is the known-good positive integer read from `calib.yaml`. It is
used for every tap and is never discovered or overwritten by Iteration 1.

### Iteration 1 state machine

#### I1.0: snapshot and dry preflight

Capture canonical files, hashes, current vision-relative T1/T0 Z relationship,
active endstops, probe offsets, current Eddy calibration, mesh state, and all
printer safety/status objects.

The script resolves these required poses before arming:

```text
tap center nozzle pose:
  X=150.000, Y=150.000

coil-over-center pose:
  nozzle_x = 150.000 - probe_x_offset
  nozzle_y = 150.000 - probe_y_offset

with current offsets (-57.391,-18.997):
  nozzle X=207.391, Y=168.997
```

To place the coil approximately 20 mm above the tapped bed reference, use the
checked-in nozzle-to-coil Z vector when its provenance is valid:

```text
drive-current nozzle Z = 20.000 - nozzle_to_coil_z
```

With the current `+1.399 mm` vector this is `18.601 mm`. The report records both
nozzle and estimated coil heights. If the Z vector is missing, stale, or would
place either component outside safe limits, the workflow aborts instead of
assuming a pose.

#### I1.1: bootstrap T0 center tap

Home all axes, select T0, clear bed mesh and visible offsets, move to
`(150,150,5)`, and collect seven successful taps using the configured
known-good threshold from `calib.yaml`. A maximum of ten attempts is allowed; rejected attempts remain in
the report.

The phase passes only if:

- seven successful samples are obtained;
- no more than three attempts are rejected;
- successful span is at most 0.030 mm;
- successful standard deviation is at most 0.010 mm;
- no safety watchdog event occurs.

Use the median successful `z_tap_center` as the robust contact estimate.

#### I1.2: calculate and deploy native endstops

Let active, source-matched endstops be `E0_old` and `E1_old`. Compute:

```text
delta_endstop = -median(z_tap_center)
E0_new = E0_old + delta_endstop
E1_new = E1_old + delta_endstop
```

This is equivalent to `E0_new = E0_old - z_tap_center`. Applying the same delta
to both endstops preserves the vision-determined relative alignment exactly:

```text
E0_new - E1_new = E0_old - E1_old
```

Before writing, require the current relative difference and acquisition
provenance to match the latest accepted vision T1 Z fact within its declared
tolerance. If provenance is stale or contradictory, abort; do not infer a new
T1 relationship from tap because Iteration 1 taps only T0.

Atomically update both Z endstops and the `(150,150)` mesh zero reference in
`calib.yaml`, regenerate, run focused checks, deploy, restart, and verify parity.

#### I1.3: verify native center Z=0

Rehome after deployment and repeat five center taps. Pass criteria:

- mean contact Z magnitude at most 0.010 mm;
- span at most 0.020 mm;
- no rejected taps;
- visible G-code offset remains zero;
- T0/T1 configured Z difference is unchanged.

If the mean is outside tolerance but all samples are stable, allow one bounded
endstop convergence update using the same formula. A second miss aborts and
rolls back; the script must not iterate indefinitely.

#### I1.4: calibrate and deploy Eddy drive current

With the new native datum active, home, select T0, clear mesh/offsets, and move
the coil-over-center pose to the calculated approximately 20 mm coil height.
Run:

```text
LDC_CALIBRATE_DRIVE_CURRENT CHIP=btt_eddy
```

Read `reg_drive_current` from `configfile.save_config_pending_items`, validate
the integer range `0..31`, write it to `calib.yaml`, regenerate, deploy, and
restart before frequency/height calibration. Klipper's drive-current command
proposes a config value but does not update the active configured current for
subsequent calibration, so this restart is mandatory. This follows
[`DriveCurrentCalibrate.cmd_LDC_CALIBRATE()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/ldc1612.py#L50-L73),
which writes the proposed setting through `configfile.set()` while the
configured `drive_cur` field remains the value loaded at startup.

#### I1.5: guarded Eddy frequency/height calibration

This phase starts after the drive-current phase has deployed its value and
restarted Klipper. The preceding endstop phase is authoritative: I1.5 must
not silently apply another endstop or tap offset. It must prove that the tap
datum is still valid before allowing the frequency curve to change.

At both the start and the end of the phase, run this reference sequence at
`(150,150)` with the known-good threshold from `calib.yaml`:

1. Home with mesh and visible offsets cleared. Immediately issue `GET_POSITION`
   and retain the complete response. The `mcu:` line is the raw integer step
   count, including `stepper_z` and `stepper_z1`; also retain the converted
   `stepper:`, `kinematic:`, `toolhead:`, `gcode:`, `gcode base:`, and
   `gcode homing:` lines.
2. Move to the reference point and perform exactly three successful
   `PROBE METHOD=tap TAP_THRESHOLD=<calib.yaml value>` samples. Read contact
   Z from `probe.last_probe_position[2]`, not the post-retract toolhead Z.
3. Require all three samples to succeed, have no rejected attempts, have a
   mean within `+/-0.020 mm` of zero, and have a span no greater than
   `0.030 mm`. These are deliberately looser than the final center datum
   limits, but still bound the reference before changing the frequency curve.
   If any condition fails, refuse to continue and do not start or accept the
   Eddy frequency calibration.
4. Move to the median of those three tap contact heights with an explicit
   `G1 ... Z=<median>` and immediately retain another complete `GET_POSITION`
   snapshot. This records the exact logical and raw-step position used as the
   calibration reference.

At the start sequence, then raise to `Z=5` and run:

```text
PROBE_EDDY_CURRENT_CALIBRATE CHIP=btt_eddy
```

Poll `manual_probe.is_active`. Instead of a paper test, use the already verified
native contact coordinate:

1. read `manual_probe.z_position`;
2. send one bounded `TESTZ Z=<delta>` that targets exactly kinematic Z=0;
3. verify the reported manual-probe Z is zero within one Z step;
4. send `ACCEPT`;
5. wait for the automatic coil sweep to finish;
6. collect the proposed `calibrate` table from pending config state.

This retains Klipper's intended same-point geometry. The accepted manual-probe
position is the T0 nozzle touching `(150,150)`, already proven by the three-tap
gate. Klipper then raises 5 mm, subtracts the configured probe X/Y offsets
from the carriage position so the Eddy coil is over `(150,150)`, descends to
0.050 mm above the accepted contact plane, and performs the frequency sweep.
See
[`EddyCalibrationTool.post_manual_probe()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L260-L294).
The automation replaces only the paper judgement with the already verified
native Z=0; it does not replace Klipper's sweep or coordinate translation.

Validate that the table is finite, ordered, monotonic in the expected
direction, has at least nine usable pairs, spans the required height range, and
passes the repository generator's calibration parser. Store the complete table
in `calib.yaml`, deploy, and restart. Do not commit I1.5 yet.

After that restart, repeat the complete reference sequence: home and capture
`GET_POSITION`, take the three center taps, require the same zero and
repeatability limits, move to their median tap height, and capture
   `GET_POSITION` again. Apply the same `+/-0.020 mm` mean and `0.030 mm` span
   gate, then compare the pre/post raw MCU step counts and converted positions
   alongside the two tap summaries. A post-calibration tap shift is
   evidence, not something to hide with an endstop or `tap_z_offset` update.
2. Place the nozzle at `P - probe_offset_xy`, where `P=(150,150)` is the tap
   point, and take five regular `PROBE METHOD=probe` samples. Require the
   reported physical probe XY to be within `0.020 mm` of `P`, the regular
   median and mean to be within `+/-0.020 mm`, the regular span to be no more
   than `0.030 mm`, and the regular-minus-tap median residual to be within
   `+/-0.020 mm`.
3. If this regular-probe gate fails, record regular probes at 1, 2, and
   5 mm/s and stationary `METHOD=scan` samples at commanded Z values 3, 2, 1,
   and 0.5 mm over the same physical point. Interpret constant residuals as a
   possible datum translation, speed-dependent residuals as a descent-path
   issue, height-dependent residuals as a curve-shape issue, temperature
   dependence as a thermal-drift issue, and XY dependence as an offset,
   geometry, or interference issue.

The newly captured curve is provisional until all post-calibration gates pass.
The runner snapshots the pre-candidate calibration and restores it if the tap
or same-point Eddy gate fails. Failed candidates and diagnostic evidence remain
in the run directory, but the failed curve is not left active.

Only after the post sequence passes may the runner commit I1.5. Raise to
`Z=5` after the evidence is captured; the runtime mesh remains clear.

Any movement below the known contact coordinate, unexpected manual-probe state,
or inability to land at Z=0 within step resolution aborts before `ACCEPT`.

#### I1.6: final center re-anchor and clean-frame Eddy verification

The runner does not discover or change `tap_threshold`. It reads the known-good
positive integer from `calib.yaml` and uses it for the final center tap set.
If center mean is
outside 0.010 mm, apply one final common endstop delta to T0 and T1, deploy, and
repeat the five-tap center verification.

Then perform same-physical-point tap and regular-Eddy measurements at center
and at two additional safe points. For every physical point `P`, tap with the
T0 nozzle at `P`, then place the nozzle at `P - probe_offset_xy` for the regular
probe so the displaced coil measures `P`. If the regular-minus-tap residual is
not within 0.030 mm at every point, rerun the frequency/height calibration once
in the final endstop frame and repeat verification. A remaining spatial or
thermal dependency aborts Iteration 1; the script must not hide it in an
offset.

The final mesh verification is a complete survey, not a fail-fast loop. Every
derived safe-grid point is attempted even when all taps fail at an earlier
point or a point has excessive tap span. The run records each point's attempts,
successful samples, mesh correction, and error in `mesh-verification.json`,
then fails the workflow after the full grid has been surveyed. A failed survey
therefore leaves the transient mesh and a location-specific report available
for diagnosis.

#### I1.7: full bed scan

With center tap verified at native Z=0 and regular Eddy aligned to tap:

1. run one full 11x11 scan over the configured domain with
   `BED_MESH_CALIBRATE METHOD=scan PROFILE=default HORIZONTAL_MOVE_Z=1`;
2. reject invalid samples, out-of-range sensor values, or mesh range exceeding
   the configured safe limit;
3. verify the generated mesh evaluates to zero at `(150,150)` within 0.005 mm;
4. retain the matrix, mesh parameters, temperatures, and command transcript in
   the run artifact directory as evidence only;
5. verify that the new mesh is active in memory and that the only
   `save_config_pending_items` entry is the transient `[bed_mesh default]` data
   created by Klipper;
6. verify that `calib.yaml`, `printer.cfg.template`, and generated `printer.cfg`
   contain no measured mesh profile or point matrix.

The full scan covers the configured bed-mesh domain. Tap verification cannot
cover every scanned point because tap requires both nozzle and offset coil to
remain over the bed. No deployment or restart occurs between this scan and
I1.8; verification must use this exact in-memory mesh.

#### I1.8: verify mesh against tap

Derive a 3x3 validation grid inside the intersection of:

- configured nozzle travel limits;
- the bed-mesh domain;
- positions where the T0 nozzle is over the bed;
- positions where `nozzle_xy + probe_offset_xy` keeps the Eddy coil over the
  bed;
- a conservative edge margin.

At each point, with the freshly scanned in-memory mesh still active, collect
three successful T0 taps from safe Z. Klipper tap reports raw low-level
kinematic contact, not the logical position above the bed-mesh transform.
Therefore the verification quantity is:

```text
mesh_corrected_contact_z(x,y)
    = raw_tap_contact_z(x,y) - active_mesh_correction_z(x,y)
```

Equivalently, this is the contact position obtained by applying the bed-mesh
inverse. Expecting the raw `PROBE METHOD=tap` console value itself to be zero
away from center would be incorrect.

Iteration 1 passes when:

- center raw tap mean is within +/-0.010 mm of zero;
- every point's mesh-corrected mean is within +/-0.030 mm of zero;
- mesh-corrected RMS over all validation points is at most 0.015 mm;
- each point's successful tap span is at most 0.020 mm;
- no tap is rejected during final verification;
- the in-memory mesh uses the configured zero reference and scan parameters;
- no measured mesh points appear in canonical or generated configuration;
- the vision-derived T0/T1 Z difference is unchanged.

Points outside the safe tap-overlap region are validated by scan quality,
continuity, sensor range, and mesh bounds, not by unsafe tap attempts. The final
report must say "verified across the tap-safe region", not claim literal tap
coverage of every bed coordinate.

#### I1.9: finish or rollback

On success:

- leave T0 selected at safe Z;
- leave heaters off;
- leave the fresh in-memory mesh active for inspection until the next restart
  or print-start scan replaces it;
- write final JSON/Markdown reports and exact source/live hashes;
- do not commit or push automatically;
- mark Iteration 1 complete and Iteration 2 eligible.

On failure before any canonical deployment, leave source/live unchanged. On
failure after deployment, restore the last known-good snapshot, regenerate,
deploy, restart, and verify parity if the printer remains safely controllable.
After `M112`, MCU shutdown, ambiguous physical movement, or possible step loss,
do not attempt automatic recovery motion; require inspection and rehoming.

### Iteration 1 implementation tests

Before live use, add tests for:

- state-machine phase transitions, checkpoint/resume, and phase idempotency;
- center-endstop math and exact preservation of T0/T1 relative Z;
- acquisition-provenance mismatch rejection;
- robust tap statistics, rejected-attempt accounting, and convergence limits;
- coil/nozzle pose calculation from X/Y/Z offsets and bounds checking;
- Moonraker command serialization, timeout handling, and watchdog M112 path;
- pending-config extraction for drive current, calibration table, and bed mesh;
- automatic manual-probe targeting of Z=0 without paper intervention;
- calibration-table and transient in-memory mesh validation;
- rejection of any attempt to copy mesh points into canonical or generated
  configuration;
- atomic YAML update, generator invocation, deployment verification, and
  rollback restoration;
- raw tap versus mesh-corrected logical contact calculations;
- derivation of a safe 3x3 tap validation grid;
- dry-run behavior proving zero writes, motion, heating, deployment, or restart;
- a full fake-Moonraker simulation covering success and every phase failure.

Tests use explicit local fixtures and relationships. They must not pin the
eventual measured endstops, drive current, frequency table, threshold, or mesh
matrix to repository literals.

## Alternatives considered

### Continue using `SET_GCODE_OFFSET`

This is rejected for static tool geometry.

It is appropriate for the operator's temporary tuning precisely because it
updates `homing_position` and is exposed through Klipper's status API. Those
same properties make it the wrong storage location for invisible tool
calibration.

Static and manual values can be algebraically combined, but once combined they
lose provenance. Every writer must know the active tool and preserve every
other contribution. The current failure demonstrates that this is not a robust
ownership model.

### Use `G92` in T0/T1

`G92` does not update `homing_position`, so it initially appears capable of
hiding tool geometry from KlipperScreen. However, Klipper implements it by
rewriting `base_position`:

```python
self.base_position[i] = self.last_position[i] - requested_position
```

See
[`GCodeMove.cmd_G92()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/gcode_move.py#L181-L190)
or the
[pinned upstream source](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/gcode_move.py#L181-L190).

Changing the mapping while preserving both physical position and reported
logical position would require a coupled physical compensation move and a
carefully calculated `G92`. That state would then coexist with:

- homing, which updates axis base positions;
- `SAVE_GCODE_STATE` and `RESTORE_GCODE_STATE`, which save and restore
  `base_position` and `homing_position`;
- slicer use of `G92 E...`;
- the coordinates entering bed mesh.

The save/restore behavior is visible in
[`GCodeMove.cmd_SAVE_GCODE_STATE()` and `cmd_RESTORE_GCODE_STATE()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/gcode_move.py#L227-L260).

`G92` would hide state, but not isolate it. It is rejected.

### Implement custom kinematics

Tool-relative nozzle geometry is kinematic in a broad physical sense, but a
custom Klipper kinematics implementation is disproportionate here.

Klipper's Cartesian implementation owns rail creation, position calculation,
homing, limits, and Z speed/acceleration checks. See
[`CartKinematics`](klipper_setup/rp2040_firmware/klipper/klippy/kinematics/cartesian.py#L10-L125)
and the
[pinned upstream source](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/kinematics/cartesian.py#L10-L125).

IDEX mode handling additionally owns active rail changes, copy/mirror modes,
safe distance, homing order, and limit updates. See
[`DualCarriages`](klipper_setup/rp2040_firmware/klipper/klippy/kinematics/idex_modes.py#L15-L135)
and the
[pinned upstream source](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/kinematics/idex_modes.py#L15-L135).

Forking that machinery would enlarge the safety and upstream-maintenance
surface without being necessary to hide a reversible per-tool translation.
Custom kinematics should be reconsidered only if a future requirement cannot be
expressed as a reversible transform, such as non-Cartesian coupling or a
different physical rail model.

## Iteration 2: proposed hidden IDEX move transform

### Why a move transform fits

Klipper explicitly supports a transform object with two operations:

```python
transform.move(newpos, speed)
transform.get_position()
```

`GCodeMove.set_move_transform()` installs that pair and returns the previously
installed transform so it can be chained. See
[`GCodeMove.set_move_transform()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/gcode_move.py#L83-L93)
and the
[pinned upstream implementation](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/gcode_move.py#L83-L93).

Klipper's skew correction is the reference pattern. On connect it installs
itself with `force=True`, stores the previous transform as `next_transform`,
applies its correction in `move()`, and applies the inverse in
`get_position()`. See
[`PrinterSkew._handle_connect()`, `move()`, and `get_position()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/skew_correction.py#L43-L72)
or the
[pinned upstream source](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/skew_correction.py#L43-L72).

The IDEX extra can follow the same pattern and wrap the already-registered
`bed_mesh` transform.

### Transform ordering

The required order is:

```text
GCodeMove.last_position
    |
    | includes normal G-code coordinates and real SET_GCODE_OFFSET tuning
    v
IDEX hidden transform
    |
    | adds active tool's calibrated Y/Z translation
    v
BedMesh transform
    |
    | looks up mesh at the selected tool's physical bed coordinate
    | and adds interpolated Z correction
    v
Toolhead / Cartesian + DualCarriages
    v
MCU step generation
```

This ordering leaves operator tuning above the hidden transform and allows the
existing `BED_MESH_OFFSET` behavior to remain immediately downstream.

### Forward and inverse equations

Let:

- `p = [x, y, z, e]` be the position received from `gcode_move`;
- `o_t = [0, y_t, z_t, 0]` be the hidden offset for active tool `t`;
- `B()` be the downstream bed-mesh transform;
- `B^-1()` represent `bed_mesh.get_position()`.

The forward move is:

```text
IDEX.move(p) = B.move(p + o_t)
```

The inverse position query is:

```text
IDEX.get_position() = B.get_position() - o_t
```

Therefore, ignoring floating-point tolerance:

```text
IDEX.get_position(IDEX.move(p)) = p
```

The transform does not write `GCodeMove.base_position` or
`GCodeMove.homing_position`. Static tool geometry consequently remains absent
from `homing_origin`.

### Absolute T0 datum from tap

The complete Z model needs four quantities with separate ownership:

```text
machine_z       coordinate established by the physical Z endstop
absolute_datum  common T0 nozzle-contact reference, measured by tap
tool_z[t]       relative T0/T1 nozzle geometry
manual_z        operator adjustment visible in KlipperScreen
mesh_z(x,y)     relative bed-surface correction
```

They must not be collapsed into one `SET_GCODE_OFFSET` value.

There are two viable ways to use a repeatable T0 tap result. They serve
different operating policies.

#### Static, source-controlled datum

The preferred first absolute calibration is to keep runtime transformation
simple and calibrate the physical Z endstop coordinate from repeated T0 tap
measurements.

With all other Z offsets neutral and mesh inactive, let `z_tap` be the mean T0
tap contact coordinate at the chosen anchor. To make that same physical contact
be native kinematic Z=0:

```text
new_t0_position_endstop = old_t0_position_endstop - z_tap
new_t1_z_endstop = new_t0_position_endstop - calibrated_t1_relative_z
```

The sign follows directly from the top-endstop frame: subtracting a positive
reported contact coordinate shifts every native Z coordinate down by that
amount. This formula must be verified first with a deliberately small,
guarded, non-persistent test because current combined offsets make historical
observations difficult to interpret.

The measured proposal should be written to `calib.yaml`, reviewed, generated,
and deployed through the normal source-controlled path. `SAVE_CONFIG` output
must not become an undocumented second source of truth.

This approach has useful properties:

- T0 physical contact is native kinematic Z=0;
- no common runtime Z transform is required;
- T1 inherits the same absolute datum through its separately calibrated
  relative Z difference;
- raw stepper, kinematic, and logical coordinates are easier to interpret;
- a firmware restart reconstructs the same datum from checked-in config.

It also means nozzle replacement, mechanical changes, or significant thermal
geometry changes require a new measured calibration.

#### Optional per-print runtime datum

A later design may tap T0 after homing and establish a per-print datum without
rewriting the checked-in endstop. In that design the hidden transform has two
explicit components:

```text
d = [0, 0, common_runtime_z_datum, 0]
o_t = [0, tool_y[t], tool_z[t], 0]

IDEX.move(p) = B.move(p + d + o_t)
IDEX.get_position() = B.get_position() - d - o_t
```

For T0 with `tool_z[0] = 0`, a tap reporting physical kinematic contact at
`z_tap` implies `common_runtime_z_datum = z_tap` if logical Z=0 is intended to
map to that physical contact coordinate.

Changing `common_runtime_z_datum` is a coordinate rebase, not an ordinary
move. A future command must:

1. require T0, homed Z, zero manual offset, mesh inactive, and a fresh valid tap
   result;
2. validate tap age, tool identity, XY anchor, temperatures, repeatability, and
   bounds;
3. update the common datum without physically moving;
4. call the appropriate G-code position resynchronization so the logical
   position reflects the new frame;
5. expose the datum prominently in status and clear it on rehome, restart, or
   failed validation;
6. establish the datum before scanning or loading a mesh for the print.

Klipper's Eddy guide mentions using tap results with
`SET_KINEMATIC_POSITION` before bed-mesh calibration. That command directly
forces low-level kinematic position and is documented as a diagnostic/debugging
interface that can create invalid internal state if used incorrectly. See
[`SET_KINEMATIC_POSITION`](klipper_setup/rp2040_firmware/klipper/docs/G-Codes.md#L597-L638)
and
[`ForceMove.cmd_SET_KINEMATIC_POSITION()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/force_move.py#L117-L137).

It remains a possible implementation mechanism, but it should not be hidden in
a macro without tests and state guards. A deliberately owned common transform
datum is easier to report and clear, while static endstop calibration remains
the least stateful first implementation.

No common datum is introduced by the current documentation task. The future
Iteration 1 workflow applies the tap-derived common correction only after its
preflight has verified canonical source/generated/live parity.

### Calibration hierarchy: making tap and regular Eddy agree

"Getting rid of the difference" should not mean forcing two arbitrary numbers
to match. The methods need a declared hierarchy:

1. **Mechanical/manual verification** validates that a successful tap really
   represents clean nozzle/bed contact without excessive depression.
2. **T0 tap** becomes the primary contact observation after threshold and
   repeatability validation.
3. **Regular and scan Eddy calibration** is the secondary non-contact surface
   measurement and is translated to agree with tap at the same physical point.
4. **Bed mesh** stores relative surface shape around the chosen zero-reference
   anchor.
5. **Vision T0/T1 calibration** transfers the T0 absolute datum to T1 through a
   relative tool Z offset.
6. **Manual Z** remains a final per-print operator adjustment and is never fed
   back implicitly into calibrated geometry.

The reconciliation sequence is:

1. Read and verify the canonical positive `tap_threshold` from `calib.yaml`.
   Do not rediscover or overwrite it in the Iteration 1 workflow.
2. Establish `tap_z_offset` only for measured, repeatable tap bias. Do not use
   it merely to make a one-off regular-probe result match.
3. At one safe bed point, run repeated tap and regular probes using the two
   different toolhead XY poses required to measure that same physical point.
4. Compute `delta_eddy_to_tap = regular_probe_z - tap_z` for paired samples.
5. Repeat at multiple points and controlled temperatures.
6. If the residual is constant within tolerance, translate the regular Eddy
   height calibration without changing its curve shape.
7. If the residual varies with XY or temperature, fix that dependency instead
   of applying one global correction.
8. Re-run the paired measurements after calibration, then scan a mesh whose
   `zero_reference_position` is the tap anchor.

Klipper can translate the regular calibration through
`Z_OFFSET_APPLY_PROBE`: it reads `homing_origin.z` and subtracts that value from
every calibration height. For tap, `Z_OFFSET_APPLY_PROBE METHOD=tap` changes
`tap_z_offset` instead. See
[`EddyCalibrationTool.cmd_Z_OFFSET_APPLY_PROBE()`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L301-L329)
and the
[pinned command reference](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/docs/G-Codes.md#L1257-L1263).

Because a regular probe result is `toolhead_z - calibrated_sensor_height`,
subtracting a value `h` from every calibrated sensor height raises the reported
regular-probe contact result by `h`. Therefore, after a valid same-point
comparison:

```text
delta_eddy_to_tap = regular_probe_z - tap_z
required_regular_calibration_translation h = tap_z - regular_probe_z
                                          = -delta_eddy_to_tap
```

That equation is only a proposed **vertical translation**. It is invalid if the
residual depends materially on XY, temperature, approach, or sample order.

The current architecture contaminates `homing_origin` with static tool Z, so
that command is not safe as an automated calibration step today. After hidden
tool geometry is implemented, a future report-only helper should calculate the
proposed translation, print the old/new calibration summary, and require the
result to be checked into `calib.yaml`. It should not silently invoke
`SAVE_CONFIG` or infer calibration intent from an arbitrary GUI offset.

### Tool switching

For a homed, movable T0 -> T1 switch, the future sequence should be:

1. Read and retain current M220 and M221.
2. Call `ACTIVATE_EXTRUDER` for T1.
3. Select/park the correct dual carriage.
4. Select T1's target `BED_MESH_OFFSET`.
5. Obtain the current logical transform input while T0's hidden offset is still
   active.
6. Change the transform's active hidden offset from `o_0` to `o_1`.
7. Forward the unchanged logical position through the new transform at the
   configured compensation speed.
8. Restore M220 and M221.
9. Update macro/reporting state only after successful activation.

The physical compensation is:

```text
delta_physical = o_1 - o_0
```

The logical position and visible manual offset remain unchanged.

The reverse T1 -> T0 transition performs the inverse physical delta. A complete
T0 -> T1 -> T0 cycle should return both Z steppers to their starting raw-count
deltas within step quantization, provided no other moves occurred.

### Edge and failure behavior

The implementation must make an explicit distinction between:

- unhomed selection, where tool state may be selected but no compensating
  physical move is allowed;
- a normal homed switch where the target physical Y/Z is within limits;
- a homed switch at an axis edge where compensation would exceed limits.

For the last case, silently changing the transform and waiting for a later move
would create a discontinuity. The safer future policy is to reject the tool
switch with a clear error before changing active transform or macro state. Any
different policy must be justified and separately tested.

If a downstream transform move fails, active-tool state, mesh offset, and
reported macro state must not claim a successful switch. The implementation
needs either prevalidation or a defined rollback sequence.

### Bed mesh during a switch

Because `BED_MESH_OFFSET` changes the coordinate used by `ZMesh.calc_z()`, the
target mesh offset must be active before the target transform performs its
compensation move. The composition test must verify this order explicitly.

The existing T1 mesh-Y offset is intended to make a mesh measured with one
physical Eddy/nozzle relationship usable at the corresponding T1 nozzle
location. The current `ZFADE` adjustment concerns fade calculations, not an
absolute Z datum. Neither should be repurposed for manual baby-stepping.

### Manual Z

KlipperScreen should continue to issue `SET_GCODE_OFFSET Z_ADJUST=... MOVE=1`
or its equivalent. That value remains in `homing_origin.z` and is shared by both
tools because the hidden transform sits below `gcode_move`.

No capture/subtraction/reconstruction of manual Z is required during a tool
switch. The active visible value simply remains untouched.

At virtual-SD file reset, the future extension may explicitly return the
operator offset to neutral with `SET_GCODE_OFFSET X=0 Y=0 Z=0 MOVE=0`. That
reset changes only per-print user state. It must not alter the hidden calibrated
offsets.

### M220 and M221

The future extension should retain the existing command ordering for speed and
flow:

1. before `ACTIVATE_EXTRUDER`, read `gcode_move.speed_factor` and
   `gcode_move.extrude_factor`;
2. convert the speed ratio to the percentage accepted by M220;
3. after activation and successful geometric switch, issue M220 and M221 with
   the captured values.

Slicer-issued M220/M221 values become the current intended per-print values and
must be carried over the next switch. Virtual-SD reset returns both to 100%.

### Proposed future command contract

The existing `[idex_manual_tuning]` section and command names can be retained to
limit deployment churn, but their semantics should change:

- `IDEX_MANUAL_TUNING_CAPTURE`
  - captures M220 and M221 only;
  - does not calculate or store a manual Z value.
- `IDEX_MANUAL_TUNING_APPLY TOOL=<0|1> TOOL_Z=<mm> Y=<mm> MOVE=<0|1> MOVE_SPEED=<mm/s>`
  - selects hidden tool geometry;
  - performs compensation through the chained transform when `MOVE=1`;
  - restores captured speed and flow;
  - never writes static geometry with `SET_GCODE_OFFSET`.
- `IDEX_MANUAL_TUNING_STATUS`
  - reports active tool and hidden Y/Z separately;
  - reports current UI-visible `homing_origin` separately;
  - reports M220/M221 percentages;
  - does not call their sum a single "effective G-code offset".
- `IDEX_MANUAL_TUNING_RESET`
  - resets visible manual offsets and M220/M221;
  - leaves hidden tool geometry and active calibration unchanged.

The temporary `IDEX_SET_TOOL_OFFSET` macro may continue to modify runtime
hidden geometry for testing. Proven values remain sourced from `calib.yaml` and
the generated configuration.

## State-transition examples

### Firmware restart

Expected future state:

```text
active hidden tool: T0
hidden T0 Y/Z: configured calibration
visible manual X/Y/Z: 0/0/0
speed/flow: 100%/100%
mesh: none until the next fresh print-start scan
```

No tuning or measured mesh survives a firmware restart. A print must run a
fresh Eddy scan before printing; startup must not load a saved mesh profile.

### Home

Homing establishes the physical rail coordinate through the endstop values.
The hidden transform remains a separate reversible mapping. Homing must not
copy a tool offset into `homing_origin`.

After homing, record a new raw-step baseline before interpreting MCU counts.

### T0 tap datum and mesh startup

The eventual startup order for a tap-anchored print should be:

1. home from the physical endstops;
2. select T0 and confirm hidden relative tool state;
3. clean the T0 nozzle and chosen bed anchor;
4. clear visible manual Z and disable any stale mesh;
5. perform repeated validated T0 taps at the fixed anchor;
6. either verify the static source-controlled datum or establish the optional
   per-print common runtime datum;
7. run `BED_MESH_CALIBRATE METHOD=scan` under controlled conditions, using that
   anchor as `zero_reference_position`;
8. permit T0/T1 printing only after datum, mesh, and relative-tool status agree.

Tap defines contact at one point; scan supplies the relative bed shape away
from that point. Vision-derived relative T0/T1 geometry then transfers the T0
datum to T1. None of these layers should modify the manual-offset UI.

### T0 -> T1 with no manual tuning

Before and after:

```text
visible manual Z: 0
reported logical XYZ: unchanged
hidden tool offset: changes T0 -> T1
physical Y/Z: changes by calibrated tool delta
```

KlipperScreen must continue to show zero G-code offset.

### Manual Z followed by T0 -> T1 -> T0

If the operator applies `-0.060 mm`:

```text
visible manual Z: -0.060 before T1
visible manual Z: -0.060 on T1
visible manual Z: -0.060 after returning to T0
```

The hidden static T1 Z is never added to that displayed value.

### Mesh inactive

The IDEX transform forwards to a bed-mesh object that in turn forwards directly
to the toolhead when no mesh is active. Forward/inverse tool geometry must still
work.

### Mesh active

The target tool's mesh lookup offset is selected first. The hidden tool
translation is then applied, and bed mesh adds the correction for the intended
physical bed location. Returning to the original tool and logical position must
restore the original physical position within motion quantization.

### New or reset virtual-SD file

Expected future per-print state:

```text
visible manual X/Y/Z: 0/0/0
speed: 100%
flow: 100%
hidden calibrated tool geometry: unchanged
```

## Iteration 2 integration and live test plan

Iteration 1's own unit, simulation, deployment, and live-motion sequence is
specified in I1.0-I1.9 above and must pass first. The phases below cover
Iteration 2 and end-to-end regression after the hidden transform is added.
They proceed from pure logic tests to guarded live motion; a later phase must
not begin until the previous phase has passed and its evidence has been
retained. Phases 8-10 revalidate the already accepted Iteration 1 datum and
mesh through the newly introduced transform—they do not establish the datum
for the first time.

### Phase 0: accepted Iteration 1 source and deployment baseline

Actions:

- verify the working tree and record the implementation commit;
- require a passing Iteration 1 report and record its artifact hashes;
- run `generate_printer_cfg.py --check` before changing Iteration 2 code;
- run `update_menderpi.sh --check` and record the remote Klipper commit,
  generated-config fingerprint, custom-extra hashes, and Klippy readiness;
- record the current T0/T1 calibration and derived relative offsets;
- save current `BED_MESH_OUTPUT`, active runtime mesh state, temperatures, active
  tool, `IDEX_MANUAL_TUNING_STATUS`, and `GET_POSITION`.

Expected result:

- repository, generated config, deployed config, and deployed extra are
  demonstrably aligned.

Abort conditions:

- dirty or unexplained overlapping configuration changes;
- remote commit differs from pinned
  `ca8230d505b7ba7fd225bfa6ed9655bc4520e805`;
- Klippy is not ready or the printer is not idle;
- source/generated/deployed fingerprints differ.

Evidence:

- command output captured in the implementation report;
- pre-change configuration and extra hashes.

Rollback:

- none; this phase is read-only.

### Phase 1: unit tests for the transform

Use fake `gcode_move`, downstream transform, G-code, reactor, and printer
objects. Test at least:

1. Forward T0 mapping adds exactly T0 hidden Y/Z.
2. Forward T1 mapping adds exactly T1 hidden Y/Z.
3. `get_position()` subtracts the active hidden offset.
4. Forward/inverse symmetry holds for multiple XYZ/E points.
5. Changing T0 -> T1 with compensation forwards the same logical position
   through the new offset.
6. T0 -> T1 -> T0 returns to the original downstream target.
7. G-code `homing_origin` is never changed by hidden tool application.
8. A pre-existing manual Z remains unchanged across switches.
9. M220 and M221 are captured before simulated extruder activation.
10. Simulated M221 reset to 100% is restored after activation.
11. Virtual-SD reset clears visible tuning and speed/flow while leaving hidden
    tool geometry intact.
12. Unhomed `MOVE=0` selection does not schedule physical motion.
13. An out-of-range compensated target fails before state is committed.
14. Downstream movement failure does not leave active-tool state inconsistent.

Expected result:

- exact assertions pass within a small floating-point tolerance;
- no test expects configurable production calibration to equal a hard-coded
  repository value; test-local fixtures provide example offsets.

Abort conditions:

- any failure in inverse symmetry, state rollback, manual-offset isolation, or
  limit handling.

Evidence:

- focused pytest output and coverage of both tools and failure paths.

Rollback:

- revert only the unvalidated implementation changes; no live deployment has
  occurred.

### Phase 2: transform composition with fake bed mesh

Build a fake downstream transform that:

- records every input position;
- adds a deterministic mesh correction based on X and Y;
- supports a configurable mesh lookup offset;
- implements an inverse `get_position()`.

Test:

1. transform order is IDEX then mesh;
2. target `BED_MESH_OFFSET` is selected before compensation;
3. T0 and T1 resolve to the intended logical nozzle point in one physical mesh;
4. mesh inactive and active behavior are both reversible;
5. a zero-reference location produces zero mesh correction;
6. adding a uniform constant to all pre-normalized mesh samples and then
   zero-referencing does not alter mesh shape;
7. changing hidden tool Z does not appear in `homing_origin`;
8. `ZFADE` changes fade coordinates only and is not treated as a manual or
   absolute offset.

Expected result:

- one logical point produces the expected physical tool point and mesh lookup
  for each tool;
- inverse position reporting returns the original logical point.

Abort conditions:

- compensation is evaluated with the old tool's mesh offset;
- forward/inverse composition is not symmetric;
- tool changes alter visible manual state.

Evidence:

- focused tests that assert the complete ordered call trace.

Rollback:

- same as Phase 1.

### Phase 3: generator and packaging checks

Actions:

- update generator tests to verify delegation to hidden tool handling and
  unchanged mesh-offset relationships;
- verify source and image-overlay copies of the extra are byte-identical;
- verify updater hash and install checks cover the changed extra;
- generate `printer.cfg` and compare it to the checked-in output;
- run `git diff --check` and focused Klipper/config tests.

Expected result:

- generated configuration matches its template and calibration inputs;
- deployment parity tests pass;
- tests verify relationships, structure, and parity rather than pinning
  tunable calibration literals.

Abort conditions:

- unrelated generated changes;
- image/update source divergence;
- any config parser, generator, or focused test failure.

Evidence:

- generator check, pytest output, diff summary, and hashes.

Rollback:

- restore the previous extra/template/generator artifacts as one coherent set.

### Phase 4: read-only live baseline after deployment

Actions:

- deploy only after Phases 1-3 pass;
- run `update_menderpi.sh --check`;
- without moving, record active tool, mesh status, temperatures, G-code move
  status, manual-tuning status, and `GET_POSITION`;
- confirm KlipperScreen displays zero G-code offset before any manual change.

Expected result:

- Klippy is ready, all hashes match, and hidden tool state is reported
  separately from `homing_origin`.

Abort conditions:

- any source/live mismatch;
- nonzero unexplained UI offset;
- printer not idle or any axis state is unexpected.

Evidence:

- screenshots/status output and deployment-check output.

Rollback:

- restore the updater's pre-deployment backup of the config and previous extra,
  restart Klipper, and verify readiness before continuing printer use.

### Phase 5: elevated no-mesh tool switching

Preconditions:

- printer idle;
- bed and nozzle temperatures safe and recorded;
- build plate clear;
- mesh cleared;
- all axes homed once;
- nozzle raised to a conservative Z clearance;
- both compensation targets within axis limits.

Actions:

1. Move to a central XY position at safe Z.
2. Record a post-home `GET_POSITION` baseline and UI offset.
3. Run T1 and record `GET_POSITION` and status.
4. Run T0 and record the same data.
5. Repeat several reversible cycles without rehoming.

Expected result:

- UI G-code offset stays exactly zero;
- reported logical XYZ does not jump during a tool change;
- physical raw-step deltas match the expected tool compensation;
- returning to T0 returns raw Z/Z1 deltas and logical position to baseline
  within step/motion quantization;
- carriage selection and limits remain correct.

Abort conditions:

- unexpected Z direction or magnitude;
- either carriage approaches an unsafe boundary;
- logical position or UI offset changes;
- Z and Z1 show inconsistent, non-reversible movement;
- Klipper reports a movement or shutdown error.

Evidence:

- complete console transcript with each sample labelled by tool and cycle.

Rollback:

- stop motion, keep the nozzle elevated, disable the implementation by
  restoring the previous config/extra, restart, and rehome before further use.

### Phase 6: manual Z, speed, and flow persistence

Preconditions:

- Phase 5 passes;
- remain at safe clearance with mesh inactive.

Actions:

1. Apply a small, clearly visible but safe KlipperScreen Z adjustment.
2. Set non-default M220 and M221 values.
3. Record UI and status values.
4. Run T1, then T0, for multiple cycles.
5. Trigger a virtual-SD file reset when no print is running.

Expected result:

- the displayed manual Z remains exactly the operator value across every tool
  switch;
- hidden static Z never appears in the GUI value;
- speed and flow remain at their requested values across activation;
- virtual-SD reset returns manual offsets to zero and M220/M221 to 100%;
- hidden calibrated geometry remains available after reset.

Abort conditions:

- manual Z changes, doubles, or incorporates static tool Z;
- flow returns to 100% during a switch instead of being restored;
- reset changes hidden geometry.

Evidence:

- before/after screenshots plus command status output.

Rollback:

- manually return tuning to neutral, restore prior software, and restart.

### Phase 7: active-mesh switching at safe height

Preconditions:

- Phases 5 and 6 pass;
- a known mesh is loaded or a controlled-temperature scan has completed;
- mesh output and zero-reference position are recorded;
- nozzle remains at safe clearance.

Actions:

1. Run the normal fresh print-start scan, then record `BED_MESH_OUTPUT`, runtime
   mesh state, and current mesh offsets on T0.
2. At several central XY points, record logical position and `GET_POSITION`.
3. Switch to T1 and verify the target mesh offset is active.
4. Return to T0 and verify reversibility.
5. Repeat at more than one XY point to expose lookup-sign errors.

Expected result:

- tool switching remains logically and visibly invariant;
- each tool selects its intended mesh lookup offset;
- T0 -> T1 -> T0 is reversible;
- no discontinuous Z correction appears from applying the mesh offset in the
  wrong order.

Abort conditions:

- mesh offset changes after rather than before compensation;
- unexpected Z jump correlated with local mesh slope;
- logical position or UI offset changes;
- mesh becomes unloaded or corrupted.

Evidence:

- mesh output, per-point status, and ordered macro/extension messages.

Rollback:

- raise Z, clear the mesh, restore previous software, restart, and rehome.

### Phase 8: tap and same-point reconciliation regression

This phase proves that the Iteration 2 transform has not changed the accepted
tap/Eddy relationship or moved the Iteration 1 coordinate datum.

Preconditions:

- all earlier phases pass;
- clean T0 nozzle and bed;
- conservative nozzle/bed temperatures;
- T0 selected, mesh inactive, and visible G-code offset zero;
- one homing session and recorded raw-step baseline;
- a safe bed point for which both the tap-nozzle pose and offset-coil pose are
  inside carriage and bed limits;
- exact tap threshold, `tap_z_offset`, speeds, and sample settings recorded.

Actions:

1. Read the canonical threshold and calibration hashes from `calib.yaml` and
   verify they match the accepted Iteration 1 report; do not change them in
   this regression phase.
2. At bed point `P`, run repeated `PROBE METHOD=tap` samples with the nozzle at
   `P`.
3. Move the nozzle to `(Px - x_offset, Py - y_offset)` and run repeated regular
   probes so the Eddy coil measures the same point `P`.
4. Pair samples and calculate tap mean/spread, regular-probe mean/spread, and
   `delta_eddy_to_tap`.
5. Collect at least five successful samples per method at each point and retain
   every rejected tap as evidence rather than rerunning it silently.
6. Repeat at at least three safe points and at the intended calibration/print
   temperatures.
7. Record `GET_POSITION`, probe result bed/test coordinates, temperatures, and
   active offset/mesh state for every group.
8. Compare the new statistics to the passing Iteration 1 same-point table and
   tolerances. Retain the old approximately `+1.170089 mm` mismatch only as a
   historical failure signature that must not reappear.

Expected result:

- tap succeeds without excessive depression and has acceptable repeatability;
- repeated output coordinates prove both methods measured the same physical
  bed point;
- the regular-minus-tap residual remains within the accepted Iteration 1
  tolerance at every same-point location;
- the historical approximately 1.170 mm mismatch does not reappear;
- no calibration value changes during this read-only regression.

Abort conditions:

- tap reports insufficient slope, invalid free-air slope, invalid depression,
  or inconsistent contact;
- nozzle or sensor is not safely above the bed;
- sample coordinates do not resolve to the same bed point;
- temperature, homing, mesh, manual-offset, or tool state changes between pairs;
- tap spread or mechanics no longer support the accepted absolute datum.

Evidence:

- paired measurement table including `bed_x/y/z`, `test_x/y/z`, raw-step
  baseline/deltas, temperatures, method, threshold, and statistics;
- tap calibration diagnostics and exact commands.

Rollback:

- raise Z and stop; no persistent datum or calibration translation is allowed
  in this phase.

### Phase 9: zero-reference investigation

This phase checks that the accepted Iteration 1 endstop/Eddy/mesh relationship
survives Iteration 2; it does not retune absolute Z.

Preconditions:

- all earlier phases pass;
- controlled bed, sensor, and tool temperatures;
- mesh freshly scanned or explicitly loaded and documented;
- physical clearance verified before every low-Z move.

Actions:

1. Home once and record post-home raw-step baseline.
2. At the configured zero-reference bed point, perform the validated same-point
   T0 tap and regular-Eddy comparison from Phase 8.
3. Scan with `BED_MESH_CALIBRATE METHOD=scan` under recorded conditions.
4. Record `BED_MESH_OUTPUT` and verify the configured zero-reference correction
   is zero within interpolation tolerance.
5. Move T0 to the zero-reference nozzle coordinate at a conservative Z.
6. Record all `GET_POSITION` layers, tap result, and Eddy diagnostic output.
7. Repeat the approach from the same direction to quantify repeatability,
   backlash, and stiction.
8. Repeat with mesh inactive at the same logical and physical comparison point,
   without changing endstop calibration during the session.

Expected result:

- a reproducible account of which coordinate layer changes between mesh-active
  and mesh-inactive conditions;
- a direct link between the physical tap anchor and the mesh's normalized zero
  reference;
- repeatability and coordinate-layer results consistent with the accepted
  Iteration 1 report.

Abort conditions:

- nozzle clearance cannot be guaranteed;
- temperature drifts outside the chosen tolerance;
- homing or motor disable invalidates the raw-step baseline;
- repeated approaches are not mechanically repeatable.

Evidence:

- raw console data, temperatures, mesh matrix, approach direction, and any
  physical gauge measurement.

Rollback:

- raise Z and stop. This phase makes no persistent calibration change.

### Phase 10: guarded physical nozzle-gap test

This is the first Iteration 2 phase allowed to approach a physically meaningful
small gap. It does not authorize retuning the accepted absolute Z calibration.

Preconditions:

- every previous phase passes;
- user is present at the printer with immediate emergency-stop access;
- clean nozzles and bed;
- a defined non-damaging feeler/paper method;
- low movement speed and conservative incremental approach;
- no unattended macro may command Z=0 directly.

Actions:

1. Approach the mesh zero-reference point with T0 in small guarded increments.
2. Record commanded position, all `GET_POSITION` layers, raw-step delta, Eddy
   reading, and physical gauge result.
3. Withdraw before switching tools.
4. Repeat for T1 only after T0 behavior is understood and safe.
5. Compare the T0 gap to the Iteration 1 absolute target and the T1 gap to the
   vision-derived relative alignment.

Expected result:

- repeatable measurements that separate relative tool alignment from absolute
  bed datum.

Abort conditions:

- any unexpected contact, scraping, step loss, asymmetric Z movement, or
  disagreement between repeated approaches;
- tool switch changes GUI offset or logical position;
- the required correction cannot be explained by one identified coordinate
  layer.

Evidence:

- full measurement table and operator notes.

Rollback:

- immediately raise Z, stop heaters if appropriate, inspect the bed/nozzles,
  and do not proceed to calibration changes.

## Acceptance criteria

### Iteration 1

Iteration 1 is acceptable only when all of the following are demonstrated in
one retained run report:

- final T0 tap contact at `(150,150)` is native Z=0 within the specified center
  mean and repeatability tolerances, with visible G-code offsets neutral;
- I1.5 retains complete pre/post `GET_POSITION` snapshots, including raw MCU
  step counts, and three-tap center summaries around the frequency sweep;
- a failed pre/post three-tap gate refuses to accept the Eddy curve and stops
  before mesh or re-anchor phases;
- exactly the same tap-derived endstop delta was applied to T0 and T1, leaving
  the vision-derived relative Z alignment unchanged;
- final `reg_drive_current` and frequency/height table originate from the
  recorded run; the known-good tap threshold and zero `tap_z_offset` agree in
  `calib.yaml`, generated config, and the active printer;
- the verification mesh originates from a fresh scan in that run, remains
  runtime-only, and has no measured points in canonical or generated config;
- regular Eddy and tap agree at identical physical bed coordinates within the
  I1.6 tolerance after calibration;
- the loaded mesh evaluates to zero at `(150,150)` within tolerance;
- at each safe verification point, `raw_tap_z - mesh_correction_z` is near
  zero within the I1.8 per-point and RMS limits;
- no raw Tap value away from center is misreported as a logical mesh-corrected
  coordinate;
- every rejected sample, restart, deployment, and safety decision is retained;
- any failed phase rolls back to a verified canonical snapshot or stops for
  inspection when automatic recovery is unsafe.

### Iteration 2

The hidden-transform implementation is acceptable only after Iteration 1 has
passed and all of the following are demonstrated:

- static T0/T1 Y/Z never appears in `gcode_move.homing_origin`;
- KlipperScreen shows zero offset on either tool until the operator changes it;
- the same manual Z value survives repeated tool switches;
- logical XYZ remains unchanged through a compensated tool switch;
- physical motion equals the calibrated relative tool delta and is reversible;
- M220 and M221 survive `ACTIVATE_EXTRUDER`;
- virtual-SD reset clears only per-print manual tuning;
- mesh lookup selection precedes compensation and works at multiple XY points;
- mesh-disabled and mesh-enabled behavior both pass;
- out-of-range and failed movements cannot commit contradictory tool state;
- generator, image overlay, updater, and live deployment all match;
- Iteration 1's absolute datum, Eddy agreement, and mesh verification remain
  unchanged through the new transform;
- status reports absolute datum, hidden tool-relative geometry, and visible
  manual Z as separate state.

## Future implementation checklist

This checklist identifies expected future work. Checking an item requires a
separate implementation task; this document checks none of them.

**Iteration 1: automatic physical and sensor baseline**

- [ ] Add `calibrate_idex_bed_surface_eddy_tap.py` with dry-run,
      checkpoint/resume,
      guarded execution, report generation, and rollback modes.
- [ ] Extend `calib.yaml` and `generate_printer_cfg.py` for the canonical bed
      reference, Eddy current/table/tap values, and run provenance, without
      adding measured mesh data or pinning measured values in tests.
- [ ] Automate repeated center tap, robust statistics, the common endstop-delta
      calculation, and exact preservation of the vision T1/T0 relationship.
- [ ] Automate drive-current calibration, canonical capture, deployment, and
      mandatory restart before frequency/height calibration.
- [ ] Automate `PROBE_EDDY_CURRENT_CALIBRATE` behind pre/post three-tap center
      gates, full `GET_POSITION` snapshots including raw MCU step counts, and
      capture/deploy the table only after the post gate passes.
- [ ] Use the known-good tap threshold from `calib.yaml` for every tap, keeping
      `tap_z_offset: 0.000` for this baseline.
- [ ] Re-anchor center contact with the configured threshold and require same-point
      regular-Eddy/tap agreement.
- [ ] Run a fresh full scan with `(150,150)` as zero reference and keep it
      active only in memory for verification.
- [ ] Verify Tap against the active mesh using
      `raw_tap_z - mesh_correction_z`, not raw console Z alone.
- [ ] Add state-machine, safety, fake-Moonraker, calibration parser, generator,
      deployment-parity, resume, and rollback tests.
- [ ] Run I1.0-I1.9 under supervision and retain the complete passing report.

**Iteration 2: operator, G-code, and printing behavior**

- [ ] Refactor `klipper_setup/klipper_host/klippy/extras/idex_manual_tuning.py`
      to chain a hidden move transform above `bed_mesh`.
- [ ] Apply forward offsets in `move()` and exact inverse offsets in
      `get_position()`.
- [ ] Remove static tool geometry from every `SET_GCODE_OFFSET` call.
- [ ] Reduce manual-tuning capture to M220/M221 state.
- [ ] Make tool-switch state changes transactional or prevalidated.
- [ ] Select target `BED_MESH_OFFSET` before compensation.
- [ ] Keep operator `SET_GCODE_OFFSET` untouched during T0/T1.
- [ ] Reset visible manual tuning and M220/M221 on virtual-SD reset.
- [ ] Update status output to separate hidden geometry from visible tuning.
- [ ] Update T0/T1 and `_IDEX_APPLY_TOOL_OFFSET` in
      `printer.cfg.template`.
- [ ] Preserve source/image-overlay extra parity.
- [ ] Preserve updater hash and pinned-Klipper checks.
- [ ] Add transform, composition, config, packaging, and failure-path tests.
- [ ] Complete Iteration 2 live test Phases 0-10 with retained evidence.
- [ ] Treat an optional per-print runtime datum as a later, separate design;
      do not mix it into either initial iteration.

## Pinned Klipper reference index

This project currently pins Klipper commit
`ca8230d505b7ba7fd225bfa6ed9655bc4520e805`. Symbol names are listed with line
links so the references remain searchable if a future Klipper update moves the
code.

| Concern | Repository source | Pinned upstream source |
|---|---|---|
| Extruder activation resets flow | [`GCodeMove._handle_activate_extruder`](klipper_setup/rp2040_firmware/klipper/klippy/extras/gcode_move.py#L75-L78) | [`gcode_move.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/gcode_move.py#L75-L78) |
| Transform installation | [`GCodeMove.set_move_transform`](klipper_setup/rp2040_firmware/klipper/klippy/extras/gcode_move.py#L83-L93) | [`gcode_move.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/gcode_move.py#L83-L93) |
| UI/status coordinate fields | [`GCodeMove.get_status`](klipper_setup/rp2040_firmware/klipper/klippy/extras/gcode_move.py#L102-L117) | [`gcode_move.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/gcode_move.py#L102-L117) |
| G92 base-position behavior | [`GCodeMove.cmd_G92`](klipper_setup/rp2040_firmware/klipper/klippy/extras/gcode_move.py#L181-L190) | [`gcode_move.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/gcode_move.py#L181-L190) |
| M220/M221 | [`GCodeMove.cmd_M220` / `cmd_M221`](klipper_setup/rp2040_firmware/klipper/klippy/extras/gcode_move.py#L195-L206) | [`gcode_move.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/gcode_move.py#L195-L206) |
| User-visible G-code offsets | [`GCodeMove.cmd_SET_GCODE_OFFSET`](klipper_setup/rp2040_firmware/klipper/klippy/extras/gcode_move.py#L207-L226) | [`gcode_move.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/gcode_move.py#L207-L226) |
| Saved coordinate state | [`SAVE_GCODE_STATE` / `RESTORE_GCODE_STATE`](klipper_setup/rp2040_firmware/klipper/klippy/extras/gcode_move.py#L227-L260) | [`gcode_move.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/gcode_move.py#L227-L260) |
| Bed mesh transform registration | [`BedMesh.__init__`](klipper_setup/rp2040_firmware/klipper/klippy/extras/bed_mesh.py#L86-L133) | [`bed_mesh.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/bed_mesh.py#L86-L133) |
| Bed mesh inverse/forward transform | [`BedMesh.get_position` / `move`](klipper_setup/rp2040_firmware/klipper/klippy/extras/bed_mesh.py#L181-L220) | [`bed_mesh.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/bed_mesh.py#L181-L220) |
| Mesh offsets and fade tool offset | [`BedMesh.cmd_BED_MESH_OFFSET`](klipper_setup/rp2040_firmware/klipper/klippy/extras/bed_mesh.py#L277-L288) | [`bed_mesh.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/bed_mesh.py#L277-L288) |
| Zero-reference normalization | [`ZMesh.set_zero_reference`](klipper_setup/rp2040_firmware/klipper/klippy/extras/bed_mesh.py#L1409-L1418) | [`bed_mesh.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/bed_mesh.py#L1409-L1418) |
| Mesh lookup offset sign | [`ZMesh.calc_z`](klipper_setup/rp2040_firmware/klipper/klippy/extras/bed_mesh.py#L1427-L1437) | [`bed_mesh.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/bed_mesh.py#L1427-L1437) |
| Chained-transform pattern | [`PrinterSkew`](klipper_setup/rp2040_firmware/klipper/klippy/extras/skew_correction.py#L43-L72) | [`skew_correction.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/skew_correction.py#L43-L72) |
| Eddy frequency-to-height conversion | [`EddyCalibration.apply_calibration`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L61-L83) | [`probe_eddy_current.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/probe_eddy_current.py#L61-L83) |
| LDC drive-current calibration and pending value | [`DriveCurrentCalibrate`](klipper_setup/rp2040_firmware/klipper/klippy/extras/ldc1612.py#L34-L73) | [`ldc1612.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/ldc1612.py#L34-L73) |
| Main Eddy calibration same-point translation and sweep | [`EddyCalibrationTool.post_manual_probe`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L260-L294) | [`probe_eddy_current.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/probe_eddy_current.py#L260-L294) |
| Eddy probe result construction | [`probe_results_from_avg`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L538-L551) | [`probe_eddy_current.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/probe_eddy_current.py#L538-L551) |
| Probe result bed/test coordinates | [`manual_probe.create_probe_result`](klipper_setup/rp2040_firmware/klipper/klippy/extras/manual_probe.py#L8-L22) | [`manual_probe.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/manual_probe.py#L8-L22) |
| Manual-probe state, relative `TESTZ`, and `ACCEPT` | [`ManualProbeHelper`](klipper_setup/rp2040_firmware/klipper/klippy/extras/manual_probe.py#L163-L294) | [`manual_probe.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/manual_probe.py#L163-L294) |
| Pending `SAVE_CONFIG` status exposed to Moonraker | [`PrinterConfig.get_status` / `set`](klipper_setup/rp2040_firmware/klipper/klippy/configfile.py#L308-L324) | [`configfile.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/configfile.py#L308-L324) |
| Tap contact fitting and bias | [`EddyTap._analyze_pullback`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L862-L900) | [`probe_eddy_current.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/probe_eddy_current.py#L862-L900) |
| Eddy method dispatch and offsets | [`PrinterEddyProbe`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L1003-L1092) | [`probe_eddy_current.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/probe_eddy_current.py#L1003-L1092) |
| Eddy/tap offset application | [`EddyCalibrationTool.cmd_Z_OFFSET_APPLY_PROBE`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L301-L329) | [`probe_eddy_current.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/probe_eddy_current.py#L301-L329) |
| Eddy scan position reconstruction | [`EddyScanningProbe`](klipper_setup/rp2040_firmware/klipper/klippy/extras/probe_eddy_current.py#L935-L995) | [`probe_eddy_current.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/probe_eddy_current.py#L935-L995) |
| Forced kinematic rebase | [`ForceMove.cmd_SET_KINEMATIC_POSITION`](klipper_setup/rp2040_firmware/klipper/klippy/extras/force_move.py#L117-L137) | [`force_move.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/extras/force_move.py#L117-L137) |
| Cartesian homing and limits | [`CartKinematics`](klipper_setup/rp2040_firmware/klipper/klippy/kinematics/cartesian.py#L10-L125) | [`cartesian.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/kinematics/cartesian.py#L10-L125) |
| Dual-carriage activation and homing | [`DualCarriages`](klipper_setup/rp2040_firmware/klipper/klippy/kinematics/idex_modes.py#L15-L135) | [`idex_modes.py`](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/klippy/kinematics/idex_modes.py#L15-L135) |

Additional pinned Klipper documentation:

- [Eddy current probe behavior](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/docs/Eddy_Probe.md)
- [Bed mesh behavior](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/docs/Bed_Mesh.md)
- [G-code command reference](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/docs/G-Codes.md)
- [Configuration reference](https://github.com/Klipper3d/klipper/blob/ca8230d505b7ba7fd225bfa6ed9655bc4520e805/docs/Config_Reference.md)
