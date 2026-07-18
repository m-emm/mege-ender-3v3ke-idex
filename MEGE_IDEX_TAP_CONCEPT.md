# MEGE IDEX Tap Concept

Status: shared T0/T1 mechanical CAD implementation.

Both IDEX toolheads use the same Tap-enabled cage and fixed-frame Tap geometry.
T0 is the left/bottom-belt toolhead and T1 is the right/top-belt toolhead. Each
side has its own MGN7H rail/carriage, OPB991T11Z sensor, sensor-flag cable shield,
Tap animation, and focused inspection stack.

Klipper probe configuration and probe-authority decisions remain out of scope.

## Mechanical Pattern

The mechanism follows the Voron Tap pattern without copying Voron CAD: nozzle
contact lifts the Sprite, cage, fans, optical flag, and MGN7H rail a short
distance in Z. The MGN7H carriage and printed Tap frame remain fixed relative to
the X carriage. Magnets return the moving toolhead stack to a repeatable hard
stop after probing.

Useful references:

- Voron Tap repository: https://github.com/VoronDesign/Voron-Tap
- Voron Tap BOM: https://github.com/VoronDesign/Voron-Tap/blob/main/BOM.md
- Voron Tap Klipper notes:
  https://github.com/VoronDesign/Voron-Tap/blob/main/config/tap_klipper_instructions.md
- TT Electronics OPB991T11Z:
  https://www.ttelectronics.com/products/sensors/optoelectronics/slotted-switches/opb991t11z/
- TT Electronics OPB960/970/980/990 datasheet:
  https://www.ttelectronics.com/TTElectronics/media/ProductFiles/Datasheet/OPB960-990.pdf

## Shared Assembly Contract

The side-neutral implementation is split into reusable assembly resources:

- `extruder_cage_assembly.yaml` and `extruder_cage_assembly.py` implement the
  shared Tap-compatible cage used by both toolheads.
- `idex_tap_assembly.yaml` and `idex_tap_assembly.py` implement the shared fixed
  Tap frame.
- `mgn7h_rail_with_carriage_assembly.yaml` models the MGN7H rail as leader and
  its carriage as a named follower.
- `opb991t11z_sensor_assembly.yaml` models the wired optical interrupter.
- `idex_tap_stack_assembly.yaml` provides a focused, side-neutral visualization
  of an injected Tap stack.

`assemblies.yaml` instantiates those resources with explicit side context:

- `idex_tap_t0_assembly` uses the bottom machined mount, left X carriage, and
  left MGN7H instance.
- `idex_tap_t1_assembly` uses the top machined mount, right X carriage, and
  right MGN7H instance.
- `opb991t11z_sensor_left_assembly` and
  `opb991t11z_sensor_right_assembly` keep sensor placement and cable-shield
  clearance independent.
- `idex_tap_t0_stack_assembly` and `idex_tap_t1_stack_assembly` allow either
  completed stack to be inspected in isolation.

Assembly generators consume injected dependencies from YAML. They do not import
other assembly generators directly.

## Join Order

Both sides first use the same cage chain:

1. Raw shared cage.
2. `part_fan_cage_joiner` joins the fan interface into the cage.
3. `tap_extruder_cage_joiner` adds the MGN7H, magnet, stopper, and optical-sensor
   interfaces. Its side-neutral output key is `idex_tap`.

The right chain ends after step 3 as `idex_tap_t1_joined_assembly`, preserving
the proven T1 geometry and top belt carriage.

The left chain continues through `tap_belt_carriage_joiner`:

1. Materialize the exact axis-aligned bounding box of the printable
   `idex_tap.leader`; followers, screws, magnets, and reference hardware are not
   included in this cutting volume.
2. Cut that box from `x_axis_belt_carriage_bottom_assembly.leader` without any
   enlargement.
3. Fuse the surviving exterior belt-clamp regions into the fixed Tap frame.
4. Preserve belt-carriage followers and non-production hardware as prefixed
   visualization artifacts while marking the original belt-carriage leader as
   consumed.

The result is `idex_tap_t0_joined_assembly`. The raw bottom belt carriage and
the internal cut remainder are join inputs only; neither appears separately in
the tool-head or whole-printer scene. Already-separate clamp-base followers are
not fused into the printable leader or routed to production.

## Placement And Motion Ownership

Each toolhead retains normal X motion, and the whole-printer scene additionally
applies Z-axis motion. Tap trigger lift is independent per side through
`idex_tap_trigger_lift_left` and `idex_tap_trigger_lift_right`, both currently
backed by the shared `idex_tap_trigger_lift` value.

Tap lift moves:

- Sprite extruder;
- final joined cage;
- joined fan and both fan-body references;
- side-specific OPB991T11Z sensor/flag context;
- MGN7H rail.

Tap lift does not move:

- the fixed printable Tap frame;
- the MGN7H carriage follower;
- the T0 belt-clamp regions fused into the fixed Tap frame;
- the machined mount or X carriage.

This separation keeps the fixed probe frame attached to X motion while the
nozzle/toolhead stack can rise locally to trigger the sensor.

## Cable Shields

Both `tool_head_cable_attach_shield_left_assembly` and
`tool_head_cable_attach_shield_right_assembly` consume their side-specific OPB
sensor. Each shield therefore includes the optical-sensor clearance and Tap
flag accommodation. The two shield instances remain separate so their mount
and sensor placement stay explicit in the builder graph.

## Production

`tool_heads_assembly.yaml` retains the proven right-side PETG-CF plate and adds
`tool_heads_left_tap_petgcf` using
`petgcf_max_strength_high_speed_06`. The left plate contains exactly:

- `extruder_cage_left_joined`, rotated 135 degrees around Y;
- `idex_tap_t0_joined`, rotated 29 degrees around X;
- `tool_head_cable_attach_shield_left`, rotated 90 degrees around X;
- `part_fan_left_joined`, rotated 50 degrees around X.

The raw lower belt carriage and its clamp-base followers are intentionally not
on this plate.

## Parameters And Hardware Ownership

- OPB991T11Z dimensions belong to
  `opb991t11z_sensor_assembly.yaml`.
- MGN7H rail and carriage dimensions belong to
  `mgn7h_rail_with_carriage_assembly.yaml`.
- Tap-frame dimensions, magnet interfaces, stops, and clearances belong to
  `idex_tap_assembly.yaml` and the Tap/cage joiner.
- Trigger and total travel remain shared parameters in
  `idex_parameters.yaml`, while side-specific animation aliases are wired in
  `assemblies.yaml`.
- Part-to-part placement stays in `assemblies.yaml` wherever practical.

Do not lock visually tuned values into literal tests. Tests should verify graph
structure, identity and mapping relationships, positive geometry, exact
bounding-box subtraction, artifact preservation, motion ownership, and plate
membership.

## Firmware And Calibration Boundary

The mechanical implementation does not choose the final Z authority. Before
Tap is enabled as a Klipper probe, both sensors need wiring truth, safe input
configuration, polarity checks, repeatability measurements, and verification
that the bed tolerates the probing force. The existing homing and calibration
behavior remains unchanged by this CAD work.

## Remaining Validation Risks

- Added moving mass may affect ringing and X-carriage dynamics.
- Magnet force must reliably reseat the hard stop without creating excessive
  probing force.
- The moving stack needs a durable sensor-wire service loop.
- Heat must not soften the sensor, flag, magnet, or stop geometry.
- The optical flag must never become the mechanical overtravel stop.
- The T0 composite must retain only the two exterior belt-clamp regions outside
  the Tap leader envelope, with no duplicate raw lower carriage in scenes or
  production.
