# IDEX Calibration Operator Manual

This printer has one prescribed route from a roughly aligned machine to a
printable coordinate system. It is automatic: do not copy measurements into
`calib.yaml`, paste a mesh, run an applier, or restart Klipper by hand.

## Before starting

Check that:

- both tools and XYZ can home safely;
- the multi-head-zero ball and NC switch are rigid and electrically healthy;
- both clean nozzles can reach the ball envelope around `(75,-9)`;
- the bed is clean and empty;
- T0's Eddy sensor and Tap threshold are working; and
- no print is running.

Open `http://menderpi.local/calibration/`, then run from the repository root:

```bash
scripts/run_idex_calibration.sh
```

## What the command does

1. It validates local and live configuration parity and homes XYZ only when
   needed. Immediately after homing, it requires the physically clear
   multi-head-zero switch to report `RELEASED`; otherwise it reports a fault and
   stops before further motion. It then performs one final slow X-only latch
   pass so both chapters use the same settled carriage datum.
2. T0 and T1 each make 26 guarded ball contacts. Their logical X/Y frames are
   independently rebased so the measured ball centre is exactly `(75,-9)`.
   T0 remains the Z anchor and T1 Z is aligned to T0's direct centre contact.
3. Both tools make nine fixed-target verification contacts. The centre contact
   supplies Z; the 1.5 mm crown-adjacent octagonal ring verifies X/Y. Failure
   stops here.
4. T0 makes three Eddy Tap contacts at `(150,150)` with the mesh cleared. The
   median is used to add the same Z delta to both tool endstops, preserving
   their relative Z exactly.
5. After deployment and homing, three new reference taps must read within
   0.030 mm of logical Z=0.
6. T0 measures the 7×7 native Tap mesh. The profile is zero-referenced at
   `(150,150)`, written atomically to `calib.yaml`, regenerated, deployed, and
   loaded as `default`.
7. Five physical mesh-aware Tap checks must all place contact within 0.040 mm
   of commanded Z=0. Only then does the dashboard say **READY TO PRINT**.

The printer console mirrors the major state changes and per-contact progress.
The dashboard retains the complete two-chapter story, including full-size plots
and exact failure reasons.

## Independent maintenance

Rerun only tool alignment and fixed-target verification:

```bash
scripts/run_multi_head_zero_contact_map.sh
```

Preserve relative tool alignment while replacing the absolute bed Z datum and
mesh:

```bash
scripts/run_eddy_tap_bed_calibration.sh
```

These are complete workflows, not preparation for manual edits.

## Acceptance criteria

Tool verification requires both recovered centres to be within 0.05 mm of
`(75,-9)`, paired X/Y within 0.05 mm, and direct centre T1−T0 Z within 0.02 mm.
Bed reference requires a repeatable pre-rebase series and a post-deployment
median within 0.030 mm of zero. The stored mesh must exactly equal the accepted
live matrix, be active, and pass the mesh-aware contact checks.

If any step fails, leave the printer alone and inspect `/calibration/` and the
batch directory printed by the script. A failed candidate deployment is rolled
back automatically. A physical verification failure is preserved and never
causes a second speculative correction.

## Files and evidence

- `calib.yaml`: flat measured values only.
- `calib_config.yaml`: fixed machine/procedure configuration.
- `vision_config.yaml`: legacy diagnostic camera configuration.
- `printer.cfg.template` and generated `printer.cfg`: active Klipper truth.
- `runs/idex_calibration/<batch-id>/`: immutable local evidence.
- `/home/pi/printer_data/calibration/data/current.json`: live dashboard state.
- `/home/pi/printer_data/calibration/data/last_successful.json`: last printable
  full run.

The architecture and ownership rationale are in
`CONCEPT_IDEX_CALIBRATION_V2.md`.
