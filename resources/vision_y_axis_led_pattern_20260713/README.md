# Vision Y-Axis LED Pattern Experiment

This folder contains a white-only lighting experiment for the nozzle-camera
Y-axis bed-feature measurement.

## Capture Settings

- Captured at: `2026-07-13T16:45:34Z`
- Remote capture folder: `/tmp/vision_y_axis_led_pattern_20260713`
- Local folder: `resources/vision_y_axis_led_pattern_20260713/`
- Camera: `nozzle_cam`
- Camera profile: `analysis`
- Frame size: `1920x1080`
- Capture count: `40`
- Pattern count: `8`
- Y positions: `-14.8`, `-9.8`, `-4.8`, `0.2`, `5.2` mm
- Y offsets from endstop/base: `0`, `5`, `10`, `15`, `20` mm
- X position during capture: `-80.4`
- Z position during capture: `293.75`
- Motion settle before capture: `900 ms`
- Light color: white only
- Light level: `0.45` per active channel

Each pattern turned off the full vision light first, then enabled exactly one
APA102 LED index:

```gcode
VISION_LIGHT_OFF
SET_LED LED=vision_light INDEX=<1..8> RED=0.450 GREEN=0.450 BLUE=0.450
```

The capture script restored `NOZZLE_CAM_ANALYSIS_LIGHT` after the sweep and
returned Y to `-14.8`.

## Files

- `capture_plan.json`: full capture metadata and per-frame sidecars
- `*.jpg`: raw nozzle-camera captures
- `*.json`: per-frame capture metadata
- `latest.jpg`, `latest.json`: final capture duplicates from the capture helper
- `analysis/opencv_y_led_pattern_results.json`: OpenCV registration results
- `analysis/README.md`: compact analysis ranking
- `analysis/led_index_y0_contact_sheet.jpg`: visual comparison at Y=0
- `analysis/roi_reference.jpg`: marked ROIs
- `analysis/overlays/*.jpg`: registration overlays for selected results

## Result Summary

The useful marked-line feature was measured in the same primary ROI as the
earlier lighting experiment: `marked_line_tight = [690, 438, 300, 125]`.

Best tight-line results:

- LED 1, white 0.45: `[-0.20, -10.46] px/mm`, Y RMS `0.245 px`,
  minimum correlation `0.818`, gradient-Y preprocessing.
- LED 2, white 0.45: `[-0.20, -10.50] px/mm`, Y RMS `0.245 px`,
  minimum correlation `0.855`, gradient-Y preprocessing.

Best contextual result:

- LED 2, white 0.45, wider marked-line context ROI:
  `[-0.26, -10.40] px/mm`, minimum correlation `0.985`, CLAHE preprocessing.

Visual inspection of `analysis/led_index_y0_contact_sheet.jpg` agrees with the
numeric ranking: LEDs 1 and 2 light the faint upper horizontal bed/fixture line
best. LEDs 3 and 4 emphasize lower glare and other body edges more than the
marked line. LEDs 5 and 6 still register but make the primary feature dimmer.
LEDs 7 and 8 are the weakest choices for this Y feature.

## Implementation Recommendation

Use a dedicated Y-feature lighting profile instead of relying on the existing
nozzle-tip lighting profile.

Initial default from this dataset:

```gcode
VISION_LIGHT_OFF
SET_LED LED=vision_light INDEX=2 RED=0.450 GREEN=0.450 BLUE=0.450
```

Keep LED 1 as the first single-LED fallback candidate because it gave the
strongest vertical-gradient contrast and tied the tight-line residual. The
lower-level combined white pattern using indices 1 and 2 was captured later in
`resources/vision_y_axis_led_mix_20260713/`; it is usable, but LED 2 remains
the primary default.
