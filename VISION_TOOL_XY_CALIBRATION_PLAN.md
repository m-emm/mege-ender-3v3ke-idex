# Minimal Vision Tool XY Calibration Plan

Status: implementation plan
Date: 2026-08-02

## Goal

Add one small vision workflow that answers only this question:

> What T1 X and Y endstop values make T0 and T1 address the same physical XY
> point when they receive the same logical print coordinate?

The coordinate derivation and four-run evidence remain in
[`Y_ENDSTOP_VISION_CALIBRATION.md`](Y_ENDSTOP_VISION_CALIBRATION.md). This plan
deliberately excludes Z calibration, the old fine-XZ projection model, and the
discarded coupling and repeatability hypotheses.

## Measurement Contract

For every accepted frame, let:

- `C_x`, `C_y` be the commanded acquisition coordinates recorded in the
  immutable frame manifest;
- `D_x`, `D_y` be the detected fiducial-center-to-nozzle-tip vector converted
  from pixels to printer millimetres; and
- `i` be the selected tool, `T0` or `T1`.

Calculate the tool datum as:

```text
x_datum(i) = C_x(i) - D_x(i)
y_datum(i) = C_y(i) + D_y(i)
```

The signs differ because an X command moves the selected nozzle in the camera
image, while a Y command moves the bed and therefore the fiducials in the
opposite image direction. Both formulas cancel the acquisition position, so
T0 and T1 do not need the same reachable X or Y command.

Each tool's published result is the median datum across its accepted frames.
The analysis must require at least three accepted frames spanning at least
8 mm in commanded X. Counts, spreads, per-frame values, rejection reasons, and
overlays remain analysis diagnostics rather than graph facts.

Every acquisition uses commanded `Z=0.5 mm`. The workflow intentionally treats
the tools as if they have no relative Z offset and produces no Z measurement
or correction.

## Job 1: Measure One Tool

Create one implementation in a new deployed module:

```text
vision_tool_xy_calibration.py
```

Register two job types backed by that same module:

```text
idex_tool_xy_measure_t0
idex_tool_xy_measure_t1
```

Their registry definitions differ only in genuinely tool-specific inputs such
as the selected tool and nozzle-marker reference. They must not contain a
manually selected `capture_y_mm`.

Instead, the common job definition has one human-readable setting:

```yaml
capture_endstop_gap_mm: 0.5
```

Preparation derives each tool's commanded capture Y from the synchronized
endstop active for that acquisition:

```text
capture_y(Ti) = y_endstop(Ti) + capture_endstop_gap
```

This also gives the intended physical clearance from the shared bed-axis
endstop. With Klipper's tool offset:

```text
offset_y(Ti) = y_endstop(T0) - y_endstop(Ti)

internal_capture_y(Ti)
    = capture_y(Ti) + offset_y(Ti)
    = y_endstop(T0) + capture_endstop_gap
```

The code must require a positive gap, verify the derived command against the
loaded motion limits before generating G-code, and record the derived command,
source endstops, and gap in the immutable acquisition manifest. This removes a
configuration value that would otherwise need manual recalculation whenever
an endstop changes.

The jobs use a short, single-Z sweep over the existing bed-tab-relative X
positions and standard analysis lighting.

The new module owns all job-specific behavior:

- preparation and validation of the selected tool and required coordinate
  references;
- acquisition frame definitions and G-code, including `G28`, tool selection,
  safe movement, `Z=0.5`, lighting, and capture commands;
- four-fiducial and physical-nozzle-tip localization using the existing shared
  detector primitives;
- pixel-to-printer-XY conversion and the datum formulas above;
- acceptance gates and compact diagnostic artifacts; and
- construction of the published fact.

The generic calibration framework continues to own job IDs, storage,
dependency resolution, capture transport, fact publication, and catalog
updates. `vision_calibration.py` should only dispatch the two job types to the
new module; it must contain no new tool-XY analysis branches or formulas.

The two measurement facts are:

```text
tool.t0.vision_xy_datum
tool.t1.vision_xy_datum
```

Each fact contains only:

```yaml
x_datum_mm: 0.0
y_datum_mm: 0.0
acquisition_endstop_xy_mm: [0.0, 0.0]
commanded_z_mm: 0.5
```

The tool identity is carried by the fact name. The fact-set provenance carries
the acquisition manifest, active Klipper fingerprint, calibration hash, input
fact hashes, and analysis artifacts; those values are not duplicated in the
fact payload.

The measurement jobs require only the existing facts actually needed to find
the nozzle tip and convert the shared fiducials-to-tip pixel vector to printer
XY. They must not depend on either fine-XZ projection fact, the XYZ-offset fact,
or any Z-calibration result.

## Job 2: Calculate the T1 Candidate

Add one compute-only job type backed by the same module:

```text
idex_tool_xy_candidate
```

It requires the current T0 and T1 measurement facts and calculates:

```text
x_alignment_error = x_datum(T1) - x_datum(T0)
y_alignment_error = y_datum(T1) - y_datum(T0)

t1_x_endstop_new = t1_x_endstop_at_acquire - x_alignment_error
t1_y_endstop_new = t1_y_endstop_at_acquire - y_alignment_error
```

T0 remains the fixed machine anchor. T0 X/Y and both tools' Z endstops remain
unchanged.

Before calculating a candidate, reject the inputs with an actionable message
unless:

- both measurements used commanded `Z=0.5`;
- both were produced from the same coordinate-reference fact versions;
- their acquisition fingerprints identify the currently loaded Klipper
  configuration; and
- the active T0/T1 X/Y endstops match the values recorded at acquisition.

The job writes `calib_candidate.yaml` through `CalibDAO`, preserving every
unrelated calibration field. It does not overwrite canonical `calib.yaml` or
reload the printer automatically.

Publish one compact candidate fact containing the two alignment errors, the
old and suggested T1 X/Y endstops, and the candidate YAML hash. Source fact
hashes and the source calibration hash remain normal fact-set provenance.

## Consistency Cleanup

Use the simpler deployment policy: `deploy_vision_code.sh` checks consistency;
it does not regenerate or install `printer.cfg`.

Before it changes the remote vision code, it must:

1. run `generate_printer_cfg.py --check` locally;
2. compare the deployed DAO `calib.yaml` with canonical repository
   `calib.yaml`;
3. reuse the existing generated-config fingerprint check to verify that the
   remote `printer.cfg` and the configuration loaded by Klipper were generated
   from that same `calib.yaml` and template; and
4. report the differing files, hashes, and T0/T1 X/Y values when any view is
   inconsistent.

On failure, print the exact existing full/config deployment command that
reconciles those files, then exit before installing vision code. The preflight
must not mutate printer configuration and must not prevent catalog rebuilding
or reading historical publications.

For the new workflow, remove misleading output names such as `fiducials seen
at`. Use only `x_datum`, `y_datum`, `x_alignment_error`, and
`y_alignment_error`. Keep the old fine-XZ and XYZ jobs readable for historical
results and future Z work, but do not make them dependencies of the new XY
chain.

## Tests

Add focused tests for:

- X and Y command cancellation, including different acquisition coordinates
  for T0 and T1;
- capture-Y derivation for unequal T0/T1 endstops, proving that both tools end
  at the configured physical endstop gap without a per-tool capture-Y setting;
- rejection of zero or negative capture gaps and derived commands outside the
  loaded motion limits;
- both endstop-correction signs and a known zero-alignment case;
- per-frame rejection, median aggregation, minimum accepted count, and minimum
  X span;
- a compact checked-in real-image set containing at least three accepted
  `Z=0.5` frames for each tool, with their original sidecars and hashes;
- the two registry variants delegating preparation, acquisition, and analysis
  to the new module;
- the compute job requiring exactly the two datum facts and preserving all
  unrelated `calib.yaml` content;
- rejection of stale or mixed acquisition/configuration snapshots; and
- deployment preflight success and informative mismatch failures.

Run only the relevant validation:

```text
python -m pytest -q tests/vision
python -m pytest -q tests/test_klipper_idex_config.py
python -m py_compile <touched runtime modules>
bash -n klipper_setup/klipper_config/deploy_vision_code.sh
python klipper_setup/klipper_config/generate_printer_cfg.py --check
git diff --check
```

No printer deployment, calibration motion, automatic candidate activation, or
Z calibration is part of this implementation.
