# Klipper XYZ Contact Probing — v0 Design Note

## Purpose

Provide a slow, repeatable 3D contact-measurement move for a Klipper-based printer. A contact switch (for example, a ball probe) stops an arbitrary XYZ trajectory and reports the corresponding Cartesian contact point. This is a concept note only; the mechanical probe, calibration, and user-facing commands remain to be designed.

## Brief architecture sketch

```text
planned XYZ move
        |
        v
custom contact-probe object ----> MCU contact input
        |                                  |
        | registers X, Y, Z… steppers       | trigger timestamp
        v                                  v
Klipper HomingMove / probing_move ----> Cartesian XYZ trigger position
```

The custom probe object is an MCU endstop/contact input attached to every stepper that contributes to the measurement move. On contact, all participating axes stop and Klipper reconstructs the XYZ position at the trigger time.

## Reusing Klipper’s probing infrastructure

Use Klipper’s existing `PrinterHoming.probing_move()` / `HomingMove` path rather than building a parallel motion-and-timestamp system.

- `probing_move()` accepts an MCU probe/endstop and a target XYZ position; it is not intrinsically Z-only.
- `HomingMove` records the participating steppers’ motion and obtains each stepper’s position at the switch trigger timestamp.
- With `probe_pos=True`, Klipper runs those trigger-time stepper positions through the kinematics to reconstruct the Cartesian XYZ contact position.

The standard `[probe]` object is deliberately Z-oriented, so it is not the right object by itself for arbitrary-direction 3D contact measurement.

## Custom contact-probe object

Implement a small custom probe/endstop object around the contact switch. During MCU identification/setup, add every relevant kinematic stepper to its MCU endstop:

```python
for stepper in toolhead.get_kinematics().get_steppers():
    mcu_endstop.add_stepper(stepper)
```

In the final implementation, “relevant” should mean every stepper that may move during the probing trajectory. This lets the existing homing machinery stop and timestamp X, Y, and all Z steppers as one measurement event.

## Multi-MCU considerations

Klipper supports probing/homing where the contact input and moved steppers live on different MCUs. The motion controller accounts for the trigger timestamp when reporting the contact position.

- It is acceptable for X to be on one MCU and Y/Z on another, with the contact input on either of those or a third MCU.
- All steppers of one multi-stepper axis must remain on the same MCU for multi-MCU homing/probing. For example, do not split `Z` and `Z1` across MCUs.
- There can be a small physical stop delay while the trigger is relayed to other MCUs. The mechanism must safely tolerate that extra travel.

## Motion details

Call the probing move with `check_movement=False`. A general 3D contact move should be permitted even when it has no Z component or moves in a direction that ordinary probing validation would reject; safety still comes from explicit travel limits, a conservative target, and a sound mechanical design.

Keep the two reported concepts separate:

- **Trigger position:** the kinematically reconstructed XYZ position at the switch’s trigger timestamp. This is the measurement result.
- **Halt position:** where the machine physically came to rest after deceleration and, in a multi-MCU setup, any relay delay. This matters for clearance and mechanics, not for the measured coordinate.

Probe slowly—roughly 1–3 mm/s for the final approach is a sensible initial range. At 2 mm/s, a 25 ms worst-case inter-MCU stop delay corresponds to about 0.05 mm of additional physical travel.

## First implementation: raw T0/T1 contact-height map

The first useful implementation is deliberately a data-collection tool, not a
calibration feature. It should make repeated vertical contact moves over the
multi-head-zero area, save every raw trigger coordinate, and render those
measurements. It must not fit a plane or surface, calculate tool offsets,
write calibration values, or alter normal homing/probing behavior.

### Initial measurement envelope

The measured contact area begins at the known front-edge location:

```text
reference contact area: X=77 mm, Y=-14 mm, expected Z contact near 0 mm
```

`Y=-14` is close to the configured front soft limit, so the initial grid must
extend only toward positive Y. The default first-pass raster is a 5 × 5 grid:

```text
X coordinates: 73, 75, 77, 79, 81 mm
Y coordinates: -14, -12, -10, -8, -6 mm
```

This covers X=77 ±4 mm and the first 8 mm behind the front edge without
commanding travel beyond the front boundary. The grid dimensions, spacing, and
repeat count should be explicit command parameters when this is implemented;
the values above are the initial safe default, not calibration data.

Run the full grid independently for T0 and T1. Each commanded coordinate is an
absolute machine coordinate after selecting the respective tool. Do not derive
one tool's result from the other tool's offset or assume their contact maps are
identical.

### Per-point contact sequence

For each tool and grid point:

1. Require an idle, fully homed printer and select the requested tool.
2. Move to a conservative clearance height, initially Z=5 mm, before every XY
   travel move.
3. Move to the grid X/Y coordinate, then descend to a fixed approach height,
   initially Z=3 mm.
4. Make a vertical contact move toward a conservative lower bound below the
   expected Z=0 contact plane, initially Z=-1 mm, at 1–2 mm/s.
5. On the multi-head-zero trigger, record Klipper's reconstructed trigger XYZ
   coordinate as the raw measurement, retract to clearance, and repeat at the
   same point.

Use three repeats per grid point initially: 25 points × 3 samples = 75 raw
samples per tool, 150 samples for one T0/T1 run. Traverse each Y row in
alternating X direction (serpentine order) to reduce non-measurement travel;
the saved coordinates, rather than traversal order, define the map.

Before a full raster, require a guarded single-point trial at X=77, Y=-14 to
confirm that the ball triggers near the expected Z range and has enough safe
mechanical overtravel. A missing trigger, unexpected trigger, loss of homing,
or motion-limit violation must abort the run immediately and retain the failed
event in the run record; it must never silently continue with a fabricated
height.

### Raw data contract

Store one immutable record per contact attempt in a run directory, with a
machine-readable CSV plus a JSON run manifest. Each raw record should include:

- run ID, timestamp, tool (`T0` or `T1`), sample index, grid row/column, and
  commanded X/Y;
- approach start Z, lower target Z, requested approach speed, and the raw
  trigger X/Y/Z returned by Klipper;
- whether the contact completed, failed, or was aborted, together with the
  reason and the active configuration/source fingerprint.

The source data remains append-only for the run. Do not average repeated
measurements, apply offsets, subtract T0 from T1, remove outliers, or convert
the values into fitted coefficients in this iteration.

### First plots

Generate plots directly from the raw records after a completed or aborted run:

- a per-tool XY scatter plot, with each raw sample coloured by its raw trigger
  Z;
- for a complete rectangular grid, a raw trigger-Z contour and X/Z
  cross-sections, one labelled line per Y coordinate.

The acquisition-order trace is intentionally omitted: it does not help locate
the ball. Grid contours are visual interpolations of explicitly labelled raw
points only; neither mode may fit a surface or produce a T0-to-T1 correction
map.

### Adaptive maximum-search alternative

Before taking a dense contour map, locate the highest directly observed contact
point for each tool independently. This is a bounded coordinate hill-climb, not
a ball fit and not a calibration operation.

The initial safe envelope is deliberately wider than the first observed grid:

```text
X: 72 to 79 mm
Y: -14.8 to -9 mm
```

For each tool, the search must:

1. Measure a 3 × 3 seed grid spanning the full envelope.
2. Select the seed point with the highest raw trigger Z.
3. Measure unvisited X-/X+/Y-/Y+ neighbours at a 1.0 mm step. Advance as soon
   as one improves the raw trigger Z by more than the small repeatability
   threshold; otherwise reduce the step.
4. When no neighbour improves, halve the step to 0.5 mm and then 0.2 mm.
   Stop at 0.2 mm, after 30 contact attempts, or when the observed maximum is
   at an envelope edge.

The search records every attempt. A point that reaches the conservative lower
target without triggering is a `no_contact` record, retracts to clearance, and
does not participate in the maximum comparison. A switch, motion, homing, or
configuration fault still aborts immediately.

Write the observed maximum's machine `X`, `Y`, and raw trigger `Z` to the JSON
manifest and console output. Generate a single maximum-search plot showing the
raw contact locations, no-contact locations, the measured-contact path, and
the marked winner. Do not generate a contour from these sparse adaptive points.

Once a search terminates without being boundary-limited, use its reported X/Y
as the centre for a separate 5 × 5 contour grid for that same tool. The grid is
a later collection operation; the maximum search does not launch it itself.

## Next steps

1. Define the ball/switch mechanics, allowable overtravel, and retraction strategy.
2. Prototype the custom contact-probe object and a guarded single-point contact
   command at X=77, Y=-14.
3. Use the adaptive maximum search for T0 and T1, then centre a separate 5 × 5
   grid on each observed maximum.
4. Inspect repeatability, trigger-position versus halt-position behavior, and
   the raw T0/T1 maps before deciding whether any fitting or calibration is
   justified.
