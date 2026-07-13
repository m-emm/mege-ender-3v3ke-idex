# Vision Y-Axis LED Pattern Experiment

Captured 40 frames: 8 single-white-LED patterns x 5 Y positions.
White level: 0.45. Y positions: [-14.8, -9.8, -4.8, 0.2, 5.2] mm. Camera profile: analysis.

## Primary Marked-Line Ranking

- white_led_1 index=[1]: mode=grad_y, axis=[-0.2, -10.46] px/mm, rms_y=0.24495 px, corr_min=0.81813, score=0.24495, overlay=analysis/overlays/overlay_white_led_1_marked_line_tight_grad_y.jpg
- white_led_2 index=[2]: mode=grad_y, axis=[-0.2, -10.5] px/mm, rms_y=0.24495 px, corr_min=0.855, score=0.24495, overlay=analysis/overlays/overlay_white_led_2_marked_line_tight_grad_y.jpg
- white_led_5 index=[5]: mode=clahe, axis=[-0.26, -10.5] px/mm, rms_y=0.24495 px, corr_min=0.76135, score=0.33068, overlay=analysis/overlays/overlay_white_led_5_marked_line_tight_clahe.jpg
- white_led_6 index=[6]: mode=clahe, axis=[-0.26, -10.36] px/mm, rms_y=0.28284 px, corr_min=0.73931, score=0.36857, overlay=None
- white_led_7 index=[7]: mode=grad_mag, axis=[-0.3, -10.48] px/mm, rms_y=0.28284 px, corr_min=0.45065, score=0.36857, overlay=analysis/overlays/overlay_white_led_7_marked_line_tight_grad_mag.jpg
- white_led_4 index=[4]: mode=clahe, axis=[-0.3, -10.34] px/mm, rms_y=0.46904 px, corr_min=0.79426, score=0.55477, overlay=None
- white_led_3 index=[3]: mode=clahe, axis=[-0.3, -10.26] px/mm, rms_y=0.61644 px, corr_min=0.83856, score=0.70217, overlay=None
- white_led_8 index=[8]: mode=clahe, axis=[-0.24, -10.6] px/mm, rms_y=1.09545 px, corr_min=0.83445, score=1.19444, overlay=None

## Notes

- Results rank individual white LED indices only; useful combinations should be tested from the best single indices.
- The primary comparison uses the same `marked_line_tight` ROI as the earlier color/lighting experiment.
- Lower score is better: Y residual plus X residual penalty plus weak-correlation penalty.

## Interpretation

LED 2 is the best first default for the Y-feature sweep because it tied the
best tight-line residual while also giving the strongest wider-context match:
`marked_line_context`, CLAHE, `[-0.26, -10.40] px/mm`, minimum correlation
`0.98495`.

LED 1 is the best fallback and likely companion candidate. It gave the highest
tight-line vertical-gradient contrast and the same tight-line Y residual as
LED 2.

The first implementation should therefore make Y-feature lighting its own
named profile, initially using white LED index 2 at level `0.45`, with LED
index 1 available as the first single-LED alternate. The combined white 1+2
pattern at lower current was captured later in
`resources/vision_y_axis_led_mix_20260713/`; it is usable, but not a clearer
default than LED 2 alone.
