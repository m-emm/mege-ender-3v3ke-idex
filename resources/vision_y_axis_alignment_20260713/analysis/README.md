# Vision Y-Axis Alignment Feasibility Capture

Captured 15 frames: 3 lighting profiles x 5 Y positions.
Y positions: [-14.8, -9.8, -4.8, 0.2, 5.2] mm. Camera profile: analysis.

## Best Alignment Results

- analysis_light: roi=marked_line_tight, mode=clahe, axis=[-0.26, -10.5] px/mm, rms_y=0.37417 px, corr_min=0.97378, overlay=analysis/overlays/overlay_analysis_light_marked_line_tight_clahe.jpg
- dim_uniform_white: roi=marked_line_tight, mode=grad_mag, axis=[-0.26, -10.5] px/mm, rms_y=0.24495 px, corr_min=0.79379, overlay=analysis/overlays/overlay_dim_uniform_white_marked_line_tight_grad_mag.jpg
- uniform_green: roi=marked_line_tight, mode=grad_mag, axis=[-0.26, -10.5] px/mm, rms_y=0.24495 px, corr_min=0.75024, overlay=analysis/overlays/overlay_uniform_green_marked_line_tight_grad_mag.jpg

## Notes

- The user-marked horizontal line can be matched when the crop includes nearby context; the tight line alone is more ambiguous.
- `grad_y` emphasizes the horizontal edge and usually suppresses brightness differences better than raw CLAHE.
- Uniform green increases apparent contrast but also increases saturation/glow; dim white is cleaner than green for template matching in this sample.
