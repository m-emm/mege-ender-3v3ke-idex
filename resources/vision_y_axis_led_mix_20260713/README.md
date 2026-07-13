# Vision Y-Axis LED Mix Experiment

This folder contains the final white-only combined-LED check for the nozzle
camera Y-axis bed-feature measurement.

## Capture Settings

- Captured at: `2026-07-13T17:40:22Z`
- Remote capture folder: `/tmp/vision_y_axis_led_mix_20260713`
- Local folder: `resources/vision_y_axis_led_mix_20260713/`
- Camera: `nozzle_cam`
- Camera profile: `analysis`
- Frame size: `1920x1080`
- Capture count: `5`
- Y positions: `-14.8`, `-9.8`, `-4.8`, `0.2`, `5.2` mm
- Y offsets from endstop/base: `0`, `5`, `10`, `15`, `20` mm
- X position during capture: `-80.4`
- Z position during capture: `293.75`
- Motion settle before capture: `900 ms`
- Light color: white only
- Active LEDs: indices `1` and `2`
- Light level: `0.30` per active channel

Lighting G-code:

```gcode
VISION_LIGHT_OFF
SET_LED LED=vision_light INDEX=1 RED=0.300 GREEN=0.300 BLUE=0.300
SET_LED LED=vision_light INDEX=2 RED=0.300 GREEN=0.300 BLUE=0.300
```

The capture script restored `NOZZLE_CAM_ANALYSIS_LIGHT` after the sweep and
returned Y to `-14.8`.

## Files

- `capture_plan.json`: full capture metadata and per-frame sidecars
- `*.jpg`: raw nozzle-camera captures
- `*.json`: per-frame capture metadata
- `analysis/opencv_y_led_mix_results.json`: OpenCV registration results and
  comparison against the single-LED dataset
- `analysis/README.md`: compact analysis notes
- `analysis/mix_y_sweep_contact_sheet.jpg`: visual sweep contact sheet
- `analysis/roi_reference.jpg`: marked ROIs
- `analysis/overlays/*.jpg`: registration overlays for selected results

## Result Summary

The mix is usable but not a clear replacement for the best single LED.

- Best mix context result: `marked_line_context`, gray-normalized,
  `[-0.20, -10.46] px/mm`, Y RMS `0.245 px`, minimum correlation `0.991`.
- Best mix tight-line result: `marked_line_tight`, gradient-Y,
  `[-0.20, -10.46] px/mm`, Y RMS `0.245 px`, minimum correlation `0.841`.
- Compared through the same OpenCV script, LED 2 alone at white `0.45` still
  has the cleaner wider-context residual, while the mix has slightly stronger
  wider-context correlation.

Recommendation: keep white LED index `2` at `0.45` as the primary
`NOZZLE_CAM_Y_FEATURE_LIGHT`. Keep the `1+2` mix at `0.30` as a validated
fallback pattern.
