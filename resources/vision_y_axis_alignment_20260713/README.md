# Vision Y-Axis Alignment Feasibility Capture

Manual Y-only nozzle-camera capture set for
`VISION_Y_Z_MEASUREMENT_CONCEPT.md`.

## Capture Settings

- Printer: `menderpi.local`
- Date: 2026-07-13
- Camera: `nozzle_cam`
- Camera profile: `analysis`
- Motion: X and Z left unchanged, Y moved only
- Observed pose during captures: X `-80.4`, Z `293.75`
- Y positions: `-14.8`, `-9.8`, `-4.8`, `0.2`, `5.2`
- Y offsets from endstop: `0`, `5`, `10`, `15`, `20` mm
- Move feedrate: `1800` mm/min
- Settle time: `900` ms before each capture
- Frames: 15 total, 3 lighting profiles x 5 Y positions

`latest.jpg` and `latest.json` are the capture helper's latest-frame aliases
for the final `uniform_green_y20p0` capture, not additional measurements.

Lighting profiles:

- `analysis_light`: `NOZZLE_CAM_ANALYSIS_LIGHT`
- `dim_uniform_white`: `VISION_LIGHT R=0.10 G=0.10 B=0.10`
- `uniform_green`: `VISION_LIGHT R=0.00 G=0.35 B=0.00`

The capture sidecars and full machine status are in `capture_plan.json`.

## OpenCV Findings

The user-marked faint horizontal line is matchable. The most reliable crop was
`marked_line_tight`, rectangle `[690, 438, 300, 125]` in the 1920x1080 images.

Best fitted Y image motion:

- `analysis_light` with CLAHE: `[-0.26, -10.50]` px/mm, Y residual `0.37` px,
  minimum correlation `0.974`
- `dim_uniform_white` with gradient magnitude: `[-0.26, -10.50]` px/mm,
  Y residual `0.24` px, minimum correlation `0.794`
- `uniform_green` with gradient magnitude: `[-0.26, -10.50]` px/mm,
  Y residual `0.24` px, minimum correlation `0.750`

Uniform green did not improve the match. It made the line more visible to the
eye but added glow and saturation. The current analysis light is already strong
for the line ROI; dim white is a useful low-glare fallback.

Generated analysis artifacts:

- `analysis/roi_reference.jpg`
- `analysis/opencv_y_alignment_results.json`
- `analysis/overlays/overlay_analysis_light_marked_line_tight_clahe.jpg`
- `analysis/overlays/overlay_dim_uniform_white_marked_line_tight_grad_mag.jpg`
- `analysis/overlays/overlay_uniform_green_marked_line_tight_grad_mag.jpg`

## Implementation Takeaway

Use template registration around the marked line with local context, not a pure
single-edge detector. A robust first production path is:

1. Capture the Y sweep with `NOZZLE_CAM_ANALYSIS_LIGHT`.
2. Match `marked_line_tight` using CLAHE and gradient-magnitude feature maps.
3. Search a vertically expanded window around the reference ROI.
4. Fit image displacement vs commanded Y.
5. Accept only if correlation and residual thresholds agree across at least one
   primary ROI and one contextual ROI.
