# Vision Calibration Job Runtime

This document describes the clean-slate runtime implemented by
`vision_calibration.py`. It has no reader, migration, alias, or UI path for the
previous vision-job format.

## Job lifecycle

Every calibration job has three separate operations:

1. `prepare` resolves active printer limits and configuration, writes an
   immutable acquisition manifest, and generates the virtual-SD G-code.
2. `run` executes that G-code and then invokes an immutable analysis run.
3. `publish` explicitly advances accepted facts in the dependency catalog.

The first registered job type is:

```text
nozzle_cam_bed_tab_y_scale
```

The public command surface is:

```text
vision_calibration.py prepare nozzle_cam_bed_tab_y_scale
vision_calibration.py run nozzle_cam_bed_tab_y_scale
vision_calibration.py analyze <job_id>
vision_calibration.py publish <job_id> <analysis_run_id>
vision_calibration.py rebuild-catalog
```

Klipper exposes the equivalent acquisition-and-analysis entry point as:

```text
IDEX_BED_TAB_Y_SCALE_CALIBRATE NAME=...
```

## Storage

```text
/home/pi/printer_data/vision/
  index.html
  calibration/
    catalog.json
    publications/
      <publication_id>.json
    jobs/
      <job_id>/
        manifest.json
        acquisition.gcode
        state.json
        events.jsonl
        frames/
          <frame>.jpg
          <frame>.json
        analysis/
          <analysis_run_id>/
            result.json
            report.md
            fact_set.json       # accepted analyses only
            artifacts/
```

Acquisition manifests, analysis results, fact sets, and publications all start
at schema version 1. Analysis directories and publication records are
immutable. `catalog.json` and generated HTML are rebuildable indexes.

## Acquisition contract

The low-level Klipper commands are intentionally small:

- `VISION_JOB_BEGIN`
- `VISION_PROFILE`
- `VISION_CAPTURE_SYNC`
- `VISION_JOB_END`

`VISION_CAPTURE_SYNC` waits for queued motion, requests a framebuffer sequence
newer than the sequence visible at the start of the request, verifies the fixed
camera profile, validates and decodes the complete JPEG, and atomically commits
the image and sidecar. Sidecars include commanded and actual position,
framebuffer sequence, image hash and dimensions, profile, temperatures, and
timestamps.

The manifest and generated G-code bind each other by canonical hashes. A
mismatched schema, job type, job ID, sequence, frame name, tool, camera,
profile, manifest hash, or G-code hash fails the acquisition.

## Analysis and facts

An accepted analysis is publication-eligible but not current. A rejected
analysis stores diagnostics and artifacts, writes no fact set, changes no
current head, and invalidates nothing.

Fact dependencies bind an exact fact name and fact-set hash. Publications are
append-only records. Catalog rebuilding verifies those bindings, detects
cycles and publication conflicts, selects current heads, and propagates
staleness through downstream dependencies.

No uncertainty or covariance fields are part of these contracts. Reports store
direct observations such as correlation, residuals, duplicate disagreement,
direction agreement, and sweep coverage.

## UI

`/vision/` is generated only from the new catalog and calibration job
directories. It shows preparation/acquisition progress, immutable analyses,
publishable and current facts, and stale consumers. Each job page links every
raw frame and sidecar plus its overlays, contact sheet, plots, report, result,
and accepted fact set.

## Safety

Preparation requires Klipper ready, no active virtual-SD print, an idle printer,
XYZ already homed, a working fixed camera profile, and all resolved poses inside
active limits. Jobs never home implicitly. The first job resolves T0 X park,
configured Y minimum, and configured Z maximum from active Klipper rather than
embedding machine coordinates.
