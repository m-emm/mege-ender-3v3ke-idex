# Vision Calibration Job Runtime

This document describes the clean-slate runtime implemented by
`vision_calibration.py`. It has no reader, migration, alias, or UI path for the
previous vision-job format.

## Job lifecycle

Every calibration job has three separate operations:

1. `prepare` resolves active printer limits and configuration, writes an
   immutable acquisition manifest, and generates the virtual-SD G-code.
2. `run` executes that G-code and then invokes an immutable analysis run.
3. An accepted analysis publishes its facts immediately by default and advances
   the dependency catalog. Rejected analyses publish nothing. The explicit
   `publish` command remains available for job definitions that deliberately
   disable automatic publication.

The registered bed-reference job types are:

```text
nozzle_cam_bed_tab_y_scale
nozzle_cam_bed_tab_corner
```

The public command surface is:

```text
vision_calibration.py prepare nozzle_cam_bed_tab_y_scale
vision_calibration.py run nozzle_cam_bed_tab_y_scale
vision_calibration.py prepare nozzle_cam_bed_tab_corner
vision_calibration.py run nozzle_cam_bed_tab_corner
vision_calibration.py analyze <job_id>
vision_calibration.py publish <job_id> <analysis_run_id>
vision_calibration.py sync-priors
vision_calibration.py rebuild-catalog
```

Klipper exposes the equivalent acquisition-and-analysis entry point as:

```text
IDEX_BED_TAB_Y_SCALE_CALIBRATE NAME=...
IDEX_BED_TAB_CORNER_CALIBRATE NAME=...
```

## Storage

```text
/home/pi/printer_data/vision/
  index.html
  calibration/
    catalog.json
    publications/
      <publication_id>.json
    seeds/
      <fact-set-hash>/
        fact_set.json
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

An accepted analysis is publication-eligible and becomes current immediately
when its manifest enables the default `publish_on_accept` policy. A rejected
analysis stores diagnostics and artifacts, writes no fact set, changes no
current head, and invalidates nothing.

Fact dependencies bind an exact fact name and fact-set hash. Every current fact
declares whether the fact itself is coordinate-system defining or diagnostic.
It also declares the role of every top-level value item as either
`coordinate_system` or `diagnostic`; declarations must exactly cover the
stored value. Publications are append-only records. Catalog rebuilding verifies
those bindings and declarations, detects cycles and publication conflicts,
selects current heads, and propagates staleness through downstream dependencies.

No uncertainty or covariance fields are part of these contracts. Reports store
direct observations such as correlation, residuals, duplicate disagreement,
direction agreement, and sweep coverage.

The definition-v4 bed-tab job has no configured pixel position or ROI. It
detects and clusters near-horizontal line segments independently in both
zero-offset frames. A candidate is semantically a bed-tab top only when a steep
side continues downward to its right in both zero-offset frames. This rejects
long lower frame reflections even when they move cleanly with Y. The remaining
candidates are tracked through the complete forward/reverse sweep. Stationary
enclosure lines and poor or inconsistent registrations are rejected. The valid
tab top with the best normalized motion fit is selected; a close fit prefers
the longer span, while two equally supported distinct tab tops reject the
analysis as ambiguous.

The selected edge is tracked independently in grayscale and CLAHE. A Sobel-Y
positive/negative edge pair supplies the authoritative seam Y position. The
published fact stores the measured two-dimensional image displacement per
commanded Y millimetre. Discovered line endpoints and the expanded tracking
strip are retained as observed provenance for that analysis only; they are not
inputs to a later run.

The bed-tab corner job binds the exact current Y-parallax fact plus two
versioned seed facts: the provisional printer XYZ of the physical corner and
the tab-plane-to-print-plane Z relationship. It captures five duplicates at
the fixed `Y_min + 20 mm` view. The upstream Y vector projects the previously
observed tab top/side intersection into this view without a configured pixel
ROI. Line geometry localizes the semantic corner once; grayscale/CLAHE
forward/reverse registration refines it across duplicates, while independent
line intersections confirm attachment to the same feature.

## UI

`/vision/` is generated only from the new catalog and calibration job
directories. It shows preparation/acquisition progress, immutable analyses,
publishable and current facts, and stale consumers. Each job page links every
raw frame and sidecar plus its overlays, contact sheet, plots, report, result,
and accepted fact set.

The dashboard resolves each current catalog head to its immutable fact set and
shows only value items declared as coordinate-system defining. Derived views of
those values may be shown, but diagnostics, quality observations, capture
details, provenance, and hashes are omitted. A dedicated
`/vision/calibration/facts/` page shows all declared coordinate-system and
diagnostic items, with raw fact data and provenance in a collapsible section.

For the bed-tab job, the first large artifact shows all candidates in both
zero-offset frames with selection or rejection labels. The selected tab top
and its descending side are green. The second shows all six full frames side by
side with the measured seam/strip in yellow, fitted seam/strip in cyan, and
forward/reverse labels in green/magenta.

## Safety

Preparation requires Klipper ready, no active virtual-SD print, an idle printer,
XYZ already homed, a working fixed camera profile, and all resolved poses inside
active limits. Jobs never home implicitly. The first job resolves T0 X park,
configured Y minimum, and configured Z maximum from active Klipper rather than
embedding machine coordinates.
