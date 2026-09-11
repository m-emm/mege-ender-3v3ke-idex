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
   the 31-contact ball calibration and 13-contact fixed-target verification.
5. **Chapter 3 — Mesh and readiness:** acquire the native 7×7 Tap mesh and
   write the accepted matrix atomically to `calib.yaml`.
6. Regenerate, deploy, reload, and verify the persisted active mesh, including
   the five mesh-aware physical checks.
7. Publish **READY TO PRINT** only when the compatible accepted bed, tool, and
   mesh chapters are all deployed and verified. The accepted chain may combine
   chapters from different attempts; a standalone mesh refresh proves steps 5–6
   but cannot make the chain printable by itself.

The printer console mirrors the major state changes and per-contact progress.
The dashboard retains the complete three-chapter story, including full-size plots
and exact failure reasons.

## Independent maintenance

Rerun only tool alignment and fixed-target verification:

```bash
scripts/run_multi_head_zero_contact_map.sh
```

Run only the Eddy centre reference and its post-correction verification:

```bash
scripts/run_idex_bed_reference.sh
```

Run steps 5–6 as one repeatable acquisition/persistence/deployment operation:

```bash
scripts/refresh_idex_bed_mesh.sh
```

These are complete workflows, not preparation for manual edits.

## Acceptance criteria

The dashboard presents the bed point once as `(150,150)`. The internal JSON
keys `before_rebase` and `after_rebase` remain for compatibility, but the
operator-facing phases are the Bed Center Z=0 measurement, calibration update,
and verification. Tool verification requires each recovered centre to be
within 0.06 mm of `(75,-9)`, paired X/Y within 0.05 mm, paired centre-median
T1−T0 Z within 0.02 mm, and population σ no greater than 15 µm for each
five-tap centre series. The 31-contact calibration and 13-contact verification
must be complete; a noisy or incomplete centre series blocks correction or
mesh progression. The stored mesh must exactly equal the accepted live matrix,
be active, and pass the mesh-aware contact checks.

If any step fails, leave the printer alone and inspect `/calibration/` and the
batch directory printed by the script. A failed candidate deployment is rolled
back automatically. A physical verification failure is preserved and never
causes a second speculative correction.

## Implementation boundary

The supported operator paths are `scripts/run_idex_calibration.sh`,
`scripts/run_idex_bed_reference.sh`,
`scripts/run_multi_head_zero_contact_map.sh`, and
`scripts/refresh_idex_bed_mesh.sh`. Each chapter is an immutable attempt; the
dashboard composes compatible accepted results and automatically rolls back a
failed rerun to the last accepted checkpoint. The older
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

## Local dashboard simulator (development and UI testing only)

Do not use the printer to test dashboard states. The localhost-only simulator
serves the production dashboard unchanged at `http://127.0.0.1:8787/calibration/`
against captured, read-only representative data. It never opens an SSH or
Moonraker connection and cannot send G-code.

```bash
scripts/run_idex_calibration_dashboard_simulator.sh
scripts/idex_calibration_simulate.sh scenario active-step-4
scripts/idex_calibration_simulate.sh fail-step 4 "paired X/Y limit exceeded"
```

The injected local control panel exposes the same presets and shows its
consistency checks. `scripts/idex_calibration_simulate.sh --help` lists the
deterministic event commands for scripted tests. Refresh representative fixture
data only with the explicitly read-only capture command:

```bash
scripts/capture_idex_calibration_dashboard_simulator_fixtures.sh
```
