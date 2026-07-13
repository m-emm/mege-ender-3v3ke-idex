# Vision Y-Axis LED Mix Analysis

Captured 5 frames for `white_led_1_2_level_0p30`: LEDs [1, 2] white at level `0.3`.
Y positions: [-14.8, -9.8, -4.8, 0.2, 5.2] mm. Camera profile: `analysis`.

## Best Mix Results

- Best overall: ROI `marked_line_context`, mode `gray_norm`, axis `[-0.2, -10.46]` px/mm, Y RMS `0.24495` px, corr min `0.99055`, score `0.24495`.
- Best marked-line-tight: mode `grad_y`, axis `[-0.2, -10.46]` px/mm, Y RMS `0.24495` px, corr min `0.84146`, score `0.24495`.

## Comparison

The mix is usable but it does not clearly replace LED 2 alone as the first
default. In the prior single-LED run, LED 2 on the wider marked-line context
ROI had the cleaner residual score. The 1+2 mix has slightly stronger
wider-context correlation, but the tight-line residual is only tied and the
tight-line correlation is essentially unchanged.

Recommendation: keep white LED index 2 at `0.45` as the primary `NOZZLE_CAM_Y_FEATURE_LIGHT`; keep LED index 1 or the 1+2 mix as fallback experiments.
