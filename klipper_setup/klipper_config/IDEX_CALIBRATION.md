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

The preflight gate validates local/live parity, performs only the required
homing and final slow X latch, and confirms the ball switch is physically
`RELEASED`. The numbered workflow then runs as follows:

1. **Chapter 1 — Bed Z reference:** find rough T0 bed Z at `(150,150)` using
   overlapping guarded Eddy bands.
2. Apply the common correction to both T0/T1 Z endstops and deploy it.
3. Verify five fixed-window T0 taps from `START_Z=2` toward `Z=-1`; banded
   discovery is not repeated.
4. **Chapter 2 — Toolhead alignment:** align T0/T1 X, Y, and relative Z with
   the 26-contact ball calibration and nine-contact fixed-target verification.
5. **Chapter 3 — Mesh and readiness:** acquire the native 7×7 Tap mesh and
   write the accepted matrix atomically to `calib.yaml`.
6. Regenerate, deploy, reload, and verify the persisted active mesh, including
   the five mesh-aware physical checks.
7. Publish **READY TO PRINT** only when all evidence belongs to this successful
   full batch. A standalone mesh refresh proves steps 5–6 but remains
   **NOT READY TO PRINT**.

The printer console mirrors the major state changes and per-contact progress.
The dashboard retains the complete three-chapter story, including full-size plots
and exact failure reasons.

## Independent maintenance

Rerun only tool alignment and fixed-target verification:

```bash
scripts/run_multi_head_zero_contact_map.sh
```

Run only the Eddy centre reference/rebase and its post-deploy check:

```bash
IDEX_EDDY_PHASE=reference scripts/run_eddy_tap_bed_calibration.sh
```

Run steps 5–6 as one repeatable acquisition/persistence/deployment operation:

```bash
scripts/refresh_idex_bed_mesh.sh
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

## Implementation boundary

The supported operator paths are `scripts/run_idex_calibration.sh`,
`scripts/run_multi_head_zero_contact_map.sh`, and
`scripts/refresh_idex_bed_mesh.sh`. The older
`klipper_setup/klipper_config/calibrate_idex_bed_surface_eddy_tap.py` I1
iteration is retained for diagnostics and historical replay only; it is not
part of this sequence and must not be used to establish print readiness.

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
