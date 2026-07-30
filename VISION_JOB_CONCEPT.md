# Vision Calibration Job Runtime

This document describes the clean runtime implemented by
`vision_calibration.py`. It has no reader, migration, alias, or UI path for an
older vision-job format.

## Lifecycle

Every job has three operations:

1. `prepare` resolves live limits and configuration, writes an immutable
   acquisition manifest, and generates virtual-SD G-code.
2. `run` executes the G-code and creates an immutable analysis.
3. An accepted analysis publishes immediately and advances the dependency
   graph. A rejected analysis publishes nothing.

The registry contains exactly:

```text
nozzle_cam_bed_fiducial_lighting_sweep
nozzle_cam_bed_fiducial_y_metric
nozzle_cam_bed_tab_corner
idex_tool_red_marker_x_sweep
idex_rough_tool_x_verify
idex_nozzle_fine_xz_grid
```

The command surface is:

```text
vision_calibration.py prepare <job-type>
vision_calibration.py acquire <job-type>
vision_calibration.py run <job-type>
vision_calibration.py analyze <job-id>
vision_calibration.py publish <job-id> <analysis-run-id>
vision_calibration.py sync-priors
vision_calibration.py rebuild-catalog
vision_calibration.py calculate-rough-x
vision_calibration.py record-rough-x-activation ...
```

## Contracts and storage

Jobs live under
`/home/pi/printer_data/vision/calibration/jobs/<job-id>/`; immutable analyses
live below each job, immutable publication records live in
`calibration/publications/`, and `catalog.json` is a rebuildable index.

Manifests, analyses, fact sets, and publications use schema version 1. Exact
fact hashes bind dependencies. Catalog rebuilding detects cycles and conflicts,
selects current heads, and propagates staleness when a dependency is
superseded.

Facts and every top-level value item declare whether they define the printer
coordinate system, select an acquisition profile, or are diagnostic. The
dashboard shows only coordinate-system values; reports retain diagnostics and
provenance. These contracts contain no uncertainty or covariance fields.

## Calibration chain

The chain begins with seed facts for the 8 mm square fiducial patch, its
printer-Z plane at `-0.6 mm`, and the bed-tab corner at `[173, -18, 0] mm`.
The live stages then:

1. select fixed low-glare fiducial lighting;
2. recover the fiducial plane metric and printer-Y image vector;
3. locate the bed-tab corner relative to the observed patch;
4. sweep both red markers and independently calculate each tool's rough X;
5. record and verify the activated rough X at X=183;
6. fit the fine T0/T1 nozzle X/Z projection grid and print-plane coordinates.

No configured pixel position or ROI identifies the fiducial patch. Detection is
coordinate-free within the image, and subsequent tight regions are derived
from observed features in the same dependency chain.

## UI

`/vision/` is generated only from the catalog and current job directories. It
shows frame progress, immutable analyses, artifacts, current facts, and stale
consumers. Each job page links its raw frames, sidecars, overlays, report,
result JSON, and accepted fact set.
