# Klipper XYZ Contact Probing — v0 Design Note

## Purpose

Provide a slow, repeatable 3D contact-measurement move for a Klipper-based
printer. A contact switch stops an arbitrary XYZ trajectory and reports the
corresponding Cartesian contact point.

The calibration goal is a high-accuracy X/Y/Z measurement of each toolhead's
ball crown using 18 physical contacts per toolhead: nine phase-1 seed contacts,
one phase-1 summit contact, and eight phase-2 ring contacts.

## Architecture

```text
planned XYZ move
        |
        v
custom contact-probe object ----> MCU contact input
        |                                  |
        | registers X, Y, Z steppers       | trigger timestamp
        v                                  v
Klipper HomingMove / probing_move ----> Cartesian XYZ trigger position
```

Use Klipper's existing `PrinterHoming.probing_move()` / `HomingMove` path. The
custom probe object registers every stepper that may move during the contact
trajectory with its MCU endstop:

```python
for stepper in toolhead.get_kinematics().get_steppers():
    mcu_endstop.add_stepper(stepper)
```

With `probe_pos=True`, Klipper reconstructs the Cartesian contact position from
the participating steppers at the switch trigger timestamp. The standard
`[probe]` object remains Z-oriented and is not used for this general contact
measurement.

Klipper supports contact input and moved steppers on different MCUs. All
steppers of one multi-stepper axis must remain on the same MCU. The mechanism
must tolerate the small physical overtravel caused by deceleration and any
multi-MCU trigger relay delay.

Call the probing move with `check_movement=False`. Keep the returned trigger
position separate from the physical halt position: trigger position is the
measurement; halt position is relevant only to mechanical clearance. The
current vertical implementation approaches at 1 mm/s and retracts to Z=2.5 mm
after every completed or no-contact attempt.

## Lean first step: ten-contact coarse maximum

The only implemented search is a deliberately rough, fast locator. It exists
to provide an approximate T0/T1 ball crown for a later refinement method.

The fixed safe envelope is:

```text
X: 72 to 79 mm
Y: -14.8 to -9 mm
```

For each tool independently:

1. Select the tool, home XYZ, clear the bed mesh, and require the normally
   closed contact switch to be released.
2. Measure a wide 3 × 3 seed grid spanning the envelope. Every attempt starts
   from the configured approach height, probes toward the conservative lower-Z
   target, and retracts to clearance.
3. Exclude `no_contact` samples from fitting, while retaining them in the raw
   records and plot.
4. Fit the completed seed contacts to the normalized six-term quadratic
   `z = c + bx*x + by*y + qxx*x^2 + qxy*x*y + qyy*y^2`.
5. Require at least six completed contacts, full rank, acceptable conditioning,
   a strictly negative-definite Hessian, and a vertex strictly inside the safe
   envelope. Any failure aborts; there is no alternative or fallback search.
6. Move to the fitted X/Y vertex and take exactly one tenth physical contact.
   This contact must trigger and retract successfully.

The coarse paraboloid's fitted Z is not a calibration measurement: fitting the
whole ball envelope overestimates the crown height. The result used downstream
is therefore:

- X/Y: the fitted paraboloid vertex;
- Z: the raw trigger Z from the tenth physical verification contact.

The live measurements observed approximately 0.18–0.20 mm XY disagreement
between this coarse result and the former 19-contact local refinement. The
tenth raw Z agreed within 0.000–0.0025 mm in those runs. For planning, treat the
coarse locator as roughly 0.25 mm in XY and 0.01 mm in Z, not as final metrology.

## Artifacts and calibration

Each run writes an immutable CSV plus a schema-v3 JSON manifest. Records include
the tool, phase, commanded X/Y, contact status, approach parameters, trigger and
halt coordinates, and final retraction state. The manifest stores the fit
coefficients and normalization, rank, condition number, RMSE, curvature,
predicted vertex, highest raw contact, and verified coarse point.

The single plot is named `T0_maximum_search.png` or
`T1_maximum_search.png`. It shows seed contacts, no-contact markers, fitted
contours, the highest raw contact, and the fitted/verified XY vertex. The title
always identifies the tool.

Calibration and deployment are separate from measurement acquisition. First,
complete one paired 18-contact run for T0 and T1 with the same source
configuration. Only after both runs have completed successfully may the helper
calculate the calibration values and prepare a deployable result. It adjusts
only T1:

- subtract the measured T1-minus-T0 X/Y difference from the T1 X/Y endstops;
- add the measured T1-minus-T0 raw-Z difference to the T1 Z endstop;
- preserve T0 values, regenerate `printer.cfg`, and require the normal deploy
  and parity check.

After deployment, run a separate, deliberately quick five-contact verification
for each toolhead using a common verification pattern under that deployed
configuration.
This verification is measurement-only: it must report the residual T0/T1 X/Y/Z
alignment and pass/fail result, but it must not calculate, write, or deploy
another calibration. Its purpose is to demonstrate that the just-deployed
calibration aligned T0 and T1, not to fold verification data back into it.

## Phase 2: eight-contact ring refinement

Phase 1 and phase 2 have deliberately different jobs:

- **Phase 1:** nine seed contacts plus one physical summit contact provide a
  rough X/Y centre and an excellent measured `z_max` at the ball crown.
- **Phase 2:** eight contacts on a ring provide the accurate X/Y centre. The
  ring intentionally moves down the sphere, where a horizontal position error
  produces a strong and measurable Z variation.

This is not another search, and it is not a local two-step sphere fit. Start
with the rough phase-1 centre `(x_rough, y_rough)`, known ball radius
`R = 5 mm`, and the known summit height `z_max`. Command eight equally spaced
contacts on a circle of radius `r = 3.5 mm`:

```text
theta_i = 0, 45, ..., 315 degrees
x_i = x_rough + r * cos(theta_i)
y_i = y_rough + r * sin(theta_i)
```

Collect the eight trigger heights `z_i` and fit their first Fourier harmonic:

```text
z(theta) ~= C + A * cos(theta) + B * sin(theta)

A = (2 / 8) * sum(z_i * cos(theta_i))
B = (2 / 8) * sum(z_i * sin(theta_i))
```

The displacement from the rough centre to the ball centre is then:

```text
dx = A * sqrt(R^2 - r^2) / r
dy = B * sqrt(R^2 - r^2) / r

x_refined = x_rough + dx
y_refined = y_rough + dy
```

For `R = 5 mm` and `r = 3.5 mm`, the scale factor
`sqrt(R^2 - r^2) / r` is about `1.0202`. Thus the first-harmonic Z amplitude
has nearly 1:1 micrometre sensitivity to the XY error. A constant Z offset
cancels from `A` and `B`, so `z_max` is not required for the XY estimate.

The excellent phase-1 `z_max` remains useful as a diagnostic. It predicts each
ring contact using the exact known sphere; the eight residuals can validate the
contacts and, if wanted, support a two-parameter least-squares refinement of
only `(dx, dy)`. The sphere radius and top height are fixed--there is no sphere
fit and no second local search.

```python
import numpy as np


R_BALL = 5.0
R_CIRCLE = 3.5
N_TAPS = 8


def make_ring_points(x_rough, y_rough, r_circle=R_CIRCLE, n=N_TAPS):
    """Return equally spaced angles and XY contact targets around rough XY."""
    theta = np.arange(n) * 2.0 * np.pi / n
    xy = np.column_stack((
        x_rough + r_circle * np.cos(theta),
        y_rough + r_circle * np.sin(theta),
    ))
    return theta, xy


def fit_xy_from_ring(x_rough, y_rough, theta, z,
                     r_ball=R_BALL, r_circle=R_CIRCLE):
    """First-harmonic estimate of the true ball centre from ring contacts."""
    theta = np.asarray(theta)
    z = np.asarray(z)
    if len(theta) != len(z):
        raise ValueError("theta and z must have the same length")

    # z(theta) ~= C + A*cos(theta) + B*sin(theta)
    A = 2.0 / len(theta) * np.sum(z * np.cos(theta))
    B = 2.0 / len(theta) * np.sum(z * np.sin(theta))
    scale = np.sqrt(r_ball**2 - r_circle**2) / r_circle

    dx = scale * A
    dy = scale * B
    return x_rough + dx, y_rough + dy


def sphere_z(xy, x_center, y_center, z_max, r_ball=R_BALL):
    """Exact expected Z on the upper hemisphere; used for diagnostics."""
    xy = np.asarray(xy)
    radial_sq = (xy[:, 0] - x_center)**2 + (xy[:, 1] - y_center)**2
    return z_max - r_ball + np.sqrt(r_ball**2 - radial_sq)


def calibrate_xy(x_rough, y_rough, z_max, tap_function):
    """
    tap_function(xy_points) returns the eight measured trigger Z values.

    z_max is not needed by the harmonic estimate. It is retained to check the
    exact-sphere residuals produced by the resulting XY centre.
    """
    theta, ring_xy = make_ring_points(x_rough, y_rough)
    ring_z = np.asarray(tap_function(ring_xy))
    x_fit, y_fit = fit_xy_from_ring(x_rough, y_rough, theta, ring_z)

    residuals = ring_z - sphere_z(ring_xy, x_fit, y_fit, z_max)
    return {
        "x": x_fit,
        "y": y_fit,
        "z": z_max,
        "dx": x_fit - x_rough,
        "dy": y_fit - y_rough,
        "ring_xy": ring_xy,
        "ring_z": ring_z,
        "sphere_residuals": residuals,
    }
```
