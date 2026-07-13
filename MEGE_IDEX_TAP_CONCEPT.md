# MEGE IDEX Tap Concept

Status: concept draft.

Goal: add a Voron Tap style nozzle contact probe to the MEGE IDEX, first as a
T1/right/top toolhead packaging study. T0/left/bottom is explicitly deferred:
the bottom belt carriage sits behind the extruder in the same volume a Tap
mechanism wants to occupy, while the top/right T1 toolhead has meaningfully more
usable space around the Sprite, machined mount, and belt carriage.

The core idea is not to copy Voron Tap geometry directly. The idea is to reuse
the mechanical pattern: the nozzle/toolhead stack is allowed to move a small,
well-constrained distance in Z, that motion is detected optically, and magnets
return the moving stack to a repeatable hard stop before printing.

## Reference Pattern

Voron Tap is a nozzle-based Z probe. In the Voron design the whole toolhead
moves to trigger an optical switch. Voron documents the benefits as high
repeatability, optical-sensor durability, no dock/undock action, no separate
Z-endstop requirement, and crash protection. Voron also calls out two useful
engineering boundaries for adapting the idea: the bed must tolerate roughly
500-800 g probing force, and final accuracy depends heavily on the mechanical
condition of the moving stack.

Useful references:

- Voron Tap repository: https://github.com/VoronDesign/Voron-Tap
- Voron Tap BOM: https://github.com/VoronDesign/Voron-Tap/blob/main/BOM.md
- Voron Tap Klipper notes:
  https://github.com/VoronDesign/Voron-Tap/blob/main/config/tap_klipper_instructions.md
- TT Electronics OPB991T11Z:
  https://www.ttelectronics.com/products/sensors/optoelectronics/slotted-switches/opb991t11z/
- TT Electronics OPB960/970/980/990 datasheet:
  https://www.ttelectronics.com/TTElectronics/media/ProductFiles/Datasheet/OPB960-990.pdf

## Non-Negotiable Constraints

- Build the first Tap concept around T1/right/top, not T0/left/bottom.
- Treat T0/left/bottom as a later packaging problem because the bottom belt
  carriage behind the extruder consumes the most promising Tap volume.
- Do not modify `tool_head_mount_machined_top_assembly.leader`. It is treated as
  an existing machined part and a fixed attachment datum for the first T1 study.
- Add the Tap mechanism around the existing machined mount instead of changing
  the machined mount generator.
- Keep the existing T1 Sprite, machined mount, belt carriage, cage, fans, and
  Nitehawk placement as the current environment. The Tap study must fit into
  that environment before it replaces any load path.
- Use a vertical MGN7H linear guide for the Tap motion.
- Use M2 screws for the rail, carriage-side hardware, sensor bracket, and small
  retainers where practical.
- Model the OPB991T11Z wired optical interrupter and include it in the Tap
  assembly visualization.
- Model magnets and make their preload/reset role visible in the assembly.
- Do not connect the Tap shuttle to the Sprite/toolhead stack in this phase.
  First model the available T1 space and collision envelope.
- Use the assembly-first builder flow: YAML assembly contract first, generator
  as implementation behind that contract.

## Current Assembly Checkpoint

The repository already contains exploratory Tap-related assemblies. They are
useful geometry and builder prototypes, but their names still reflect the older
T0-first idea and should not be treated as the final side choice:

- `opb991t11z_sensor_assembly` models the wired optical interrupter as a
  reusable hardware-reference assembly.
- `mgn7h_rail_with_carriage_assembly` models the short MGN7H rail as leader and
  the carriage as a named follower.
- `idex_tap_t0_assembly` currently represents a fixed Tap frame prototype with
  rail plate, sensor bracket, magnet retainers, and stop features.
- `idex_tap_t0_shuttle_assembly` currently represents a moving shuttle prototype
  with carriage screw holes and trigger flag.
- `idex_tap_t0_stack_assembly` is a focused visualization prototype.

Future T1-first implementation should either introduce clearly named T1 Tap
assemblies or rename/split the prototypes before they become production routing.
Do not silently reuse `idex_tap_t0_*` names for final T1 semantics.

## Mechanical Stack

Baseline T1 packaging stack, from fixed environment to candidate Tap geometry:

1. Fixed datum:
   `x_axis_right_carriage_assembly` and
   `tool_head_mount_machined_top_assembly.leader`, placed as they are today.
2. Existing toolhead context:
   `sprite_extruder_right_assembly`, `x_axis_belt_carriage_top_assembly`,
   `nitehawk_board_right_assembly`, `extruder_cage_right_joined_assembly`, and
   `part_fan_right_joined_assembly`, also placed as they are today. These parts
   define the collision envelope for the first Tap study.
3. Fixed Tap candidate:
   A printed or machined frame is explored around the existing top machined
   mount and right Sprite environment. This frame may carry the MGN7 rail,
   stationary sensor body, fixed-side magnets, and hard stops, but it must first
   prove that those features fit in the right/top space.
4. Vertical guide candidate:
   A short MGN7 rail is mounted vertically in the candidate fixed frame. The
   first concept should prefer fixed rail and moving carriage because sensor and
   wire routing are simpler, but the packaging study may compare fixed-carriage
   alternatives if they fit the T1 space better.
5. Moving shuttle candidate:
   A compact shuttle bolts to the MGN7H carriage and represents the future
   moving Tap member. In this phase it is not yet the structural connection to
   the Sprite/toolhead stack.
6. Trigger flag:
   A thin opaque blade on the moving shuttle passes through the OPB991T11Z slot.
   The sensor should trigger early in the upward travel, not at the mechanical
   overtravel stop.
7. Magnetic return:
   Magnets preload the moving shuttle downward against a hard stop. The hard
   stop defines the printing position; the magnets only seat the mechanism
   there. They must not be the precision datum by themselves.

The eventual mechanism will let nozzle contact push the moving toolhead/shuttle
upward in +Z relative to the fixed mount, then trip the optical flag after a
small lift. That final load path is deliberately out of scope for the first
T1 packaging pass. First prove that the fixed frame, rail, shuttle, sensor, flag,
magnets, stops, and service access can coexist with the current T1 toolhead
placement.

Initial geometry controls to model as YAML parameters, not hard-coded constants:

- `idex_tap_trigger_lift`: first sensor transition after about 0.3-0.5 mm of
  upward toolhead travel.
- `idex_tap_total_travel`: enough travel to protect the bed and hotend after
  trigger; start around 1.0-1.5 mm as a packaging target.
- `idex_tap_overtravel_clearance`: clearance between trigger point and hard
  overtravel stop.
- `idex_tap_down_stop_material_clearance`: allowance for a durable stop surface,
  preferably metal-on-metal or screw-head-on-metal rather than printed plastic
  alone.
- `idex_tap_magnet_gap_at_rest`: air gap or contact condition that actually
  changes magnetic preload.
- `idex_tap_magnet_gap_at_trigger`: magnet gap after trigger lift, used to keep
  the return force from dropping too far through the measured travel.

## OPB991T11Z Sensor Model

The available sensor is OPB991T11Z. Relevant details for the CAD and wiring
concept:

- Wired OPB990-family Photologic slotted switch, T-tab package.
- Slot width: 0.125 in / 3.18 mm.
- Slot depth: 0.345 in / 8.76 mm.
- Aperture code `11`: 0.010 in / 0.25 mm on both LED and sensor sides.
- Output family: OPB991 is buffer/open-collector.
- Supply range: 4.5-16 V.
- Operating temperature: -40 to 70 deg C.
- Wavelength: 890 nm.
- Wire colors from datasheet:
  red = LED anode, black = LED cathode, white = Vcc, blue = output,
  green = ground.
- The Voron Tap BOM lists OPB991T11Z as one of the supported wired sensor
  options and includes an external LED resistor in the wired sensor path.

CAD modeling notes:

- Add a reusable OPB991T11Z visual/reference assembly, similar in spirit to
  `creality_endstop_board_assembly` and `pico_w_board_assembly`. Use a small
  hardware-reference manifest plus generator pair instead of hiding the sensor
  inside the Tap generator:
  `assembling/assemblies/opb991t11z_sensor_assembly.yaml` and
  `src/mege_ender_3v3ke_idex/designs/assemblies/opb991t11z_sensor_assembly.py`.
- Put OPB991T11Z dimensions in the sensor assembly manifest/global parameters
  so the part can be reused and retuned independently of the Tap frame.
- Model the body, slot, T-tabs, mounting holes, wire exit, optical centerline,
  and a transparent/light-colored keep-out volume through the slot.
- The sensor tab holes are much larger than M2 clearance. If M2 screws are used,
  include printed pockets, bushings, washers, or clamp features so the sensor is
  positively located instead of floating around oversized holes.
- Expose named followers/non-production artifacts such as `body`, `slot_keepout`,
  `optical_center`, `wire_bundle`, and `mounting_holes`, following the
  Creality-endstop pattern of making useful subfeatures addressable by YAML and
  downstream assemblies.
- The trigger flag should be black/opaque in the visualization and should have
  generous side clearance in the 3.18 mm slot while still crossing the
  0.25 mm optical aperture cleanly.

Electrical notes:

- Because OPB991 is open-collector, choose the pull-up voltage intentionally.
  Do not allow a 5 V pull-up into a non-5 V-tolerant MCU input.
- Preferred wiring concept is 5 V sensor supply, common ground, LED current set
  by an external resistor, and output pulled up to the MCU-safe logic voltage
  unless the selected toolhead board explicitly supports 5 V input.
- Add the Tap sensor to the wiring truth only after the target MCU input is
  chosen.

## Magnets And Stops

Magnets are part of the reset/preload system, not the precision stop by
themselves.

Baseline concept:

- Two symmetric magnet stations, left/right of the MGN7 rail or above/below the
  sensor envelope depending on packaging.
- Cylindrical magnets in printed pockets, with a positive floor and a printed
  or screw-retained cap so they cannot migrate toward the hotend.
- Ferrous screw heads or opposing magnets on the moving shuttle.
- Downward preload seats the shuttle against a fixed hard stop in the printing
  position.
- A separate upward overtravel stop prevents the MGN7 carriage, OPB sensor, or
  flag from becoming the crash stop.

Voron Tap uses 6 mm x 3 mm magnets in its BOM. That size is a reasonable first
reference, but the IDEX packaging may require smaller magnets or a different
count. The CAD should keep magnet diameter, height, count, and spacing as YAML
parameters.

Do not model `probe_force` as a primary CAD parameter unless a real magnet-force
or spring-preload model is implemented. Probe force is a derived validation
target from magnet grade/size/count, steel or opposing magnet target, rest gap,
trigger gap, friction, and toolhead mass. Record it in design notes or tests
after bench measurement; drive the geometry with magnet dimensions, gaps,
travel, and stop placement.

## MGN7H And M2 Hardware

Extend the existing MGN hardware modeling path for MGN7H instead of starting a
new one. The repo already models MGN rails and carriages in
`src/mege_ender_3v3ke_idex/designs/mgh_linear.py`:

- `create_mgn12h_rail()` is used by
  `src/mege_ender_3v3ke_idex/designs/assemblies/x_axis_rail_assembly.py`.
- `create_mgn12h_carriage()` is used by
  `src/mege_ender_3v3ke_idex/designs/assemblies/x_axis_carriage_assembly.py`.
- `assembling/assemblies/x_axis_rail_assembly.yaml` and
  `assembling/assemblies/x_axis_carriage_assembly.yaml` are good manifest
  precedents for standalone hardware-reference assemblies with visualization
  output and no production parts.
- `create_mgn12ca_carriage()` is used by the print bed undercarriage for the Y
  carriages.
- `create_mgn12h_rail_with_carriages()` and
  `create_mgn12ca_rail_with_carriages()` show the intended rail-leader,
  carriage-follower pattern.

Add MGN7H geometry support in that same module, or a very close sibling module
only if `mgh_linear.py` becomes too crowded. Then wrap the MGN7H rail and its
carriage as one hardware-reference assembly, like the existing
`create_mgn12h_rail_with_carriages()` pattern and like the Creality endstop or
Pico W board assemblies:

- `assembling/assemblies/mgn7h_rail_with_carriage_assembly.yaml`
- `src/mege_ender_3v3ke_idex/designs/assemblies/mgn7h_rail_with_carriage_assembly.py`

That assembly should carry MGN7H rail and carriage dimensions, expose the rail
as the leader, expose the carriage as a named follower in the correct rail-local
position, expose rail/carriage holes as named cutters or reference artifacts,
and normally have no production output. The Tap assembly should consume this
rail-with-carriage assembly through builder dependencies and injected parts
rather than constructing hidden rail/sensor references inside the Tap generator.
The built-in `carriage` follower should be the placement reference for the Tap
moving shuttle.

`src/mege_ender_3v3ke_idex/designs/linear_guide.py` is still useful as an
older printed-slide reference, but it is not the primary model for this Tap
rail. The Tap needs a physical MGN7H rail/carriage variant inspired by the
existing MGN12H/MGN12CA hardware code.

ShellForgePy in the local sibling checkout already has M2 data in
`m_screws_table`, including normal clearance, close clearance, core hole,
cylinder head diameter, and cylinder head height. If the IDEX environment is
using an older installed ShellForgePy package, verify that M2 is available
before implementing the generator.

Hardware to represent:

- MGN7 rail length, rail width, rail height, mounting hole pitch, and end
  distance.
- MGN7H carriage envelope, carriage mounting hole pattern, and screw access.
- Rail/carriage vertical offset equivalent to the existing MGN12 `h1` handling,
  so a carriage follower stays correctly positioned when the rail assembly is
  aligned or moved.
- Named rail mounting-hole cutters, equivalent in spirit to the X carriage
  `mount_holes` cutter naming, so Tap frame holes can be derived instead of
  manually duplicated.
- One assembly-level parameter set for rail and carriage dimensions, so a
  different vendor rail/carriage pair can be modeled without touching the Tap
  adapter generator.
- M2 rail screws and carriage screws.
- M2 heat-set inserts only where there is enough plastic wall around them; many
  Tap features may need direct plastic pilot holes, nuts, or captured hardware
  instead.

## Assembly Builder Shape

Current exploratory assembly files:

- `assembling/assemblies/idex_tap_t0_assembly.yaml`
- `src/mege_ender_3v3ke_idex/designs/assemblies/idex_tap_t0_assembly.py`
- `assembling/assemblies/idex_tap_t0_shuttle_assembly.yaml`
- `src/mege_ender_3v3ke_idex/designs/assemblies/idex_tap_t0_shuttle_assembly.py`
- `assembling/assemblies/idex_tap_t0_stack_assembly.yaml`
- `src/mege_ender_3v3ke_idex/designs/assemblies/idex_tap_t0_stack_assembly.py`
- `assembling/assemblies/mgn7h_rail_with_carriage_assembly.yaml`
- `src/mege_ender_3v3ke_idex/designs/assemblies/mgn7h_rail_with_carriage_assembly.py`
- `assembling/assemblies/opb991t11z_sensor_assembly.yaml`
- `src/mege_ender_3v3ke_idex/designs/assemblies/opb991t11z_sensor_assembly.py`

These files prove the reusable hardware and split Tap-frame/shuttle shape are
already underway. The next implementation should not make those T0 names the
final public contract for a T1-first design. Prefer either a new T1-focused
assembly contract or an explicit rename/migration once the packaging direction
is chosen.

The T1-first Tap generator should not import another assembly generator
directly. It should consume injected dependencies from YAML. For the packaging
study, the required injected context is the already-placed environment:

- `x_axis_right_carriage`: the right/top carriage reference.
- `fixed_tool_head_mount`: `tool_head_mount_machined_top_assembly`, unchanged.
- `sprite_extruder`: `sprite_extruder_right_assembly`, placed where it is today.
- `x_axis_belt_carriage`: `x_axis_belt_carriage_top_assembly`, placed where it
  is today.
- Optional but useful collision context:
  `nitehawk_board_right_assembly`, `extruder_cage_right_joined_assembly`,
  `part_fan_right_joined_assembly`, and `tool_head_cable_attach_shield_right_assembly`.
- `mgn7h_rail_with_carriage`: injected MGN7H rail assembly with built-in
  `carriage` follower.
- `opb991t11z_sensor`: standalone injected OPB991T11Z sensor assembly.

The Tap Python generator may create candidate adapter geometry, reference
surfaces, cutters, and keepouts from this context. It should not move the
existing Sprite/mount/belt-carriage relationship, and it should not re-export or
manually arrange reusable hardware assemblies just to make them visible.
Visualization and scene composition should come from builder dependencies,
injected parts, and top-level placement rules.

Stable artifact names to expose:

- leader: `idex_tap_fixed_frame`
- followers:
  - `idex_tap_moving_shuttle`
  - `idex_tap_sensor_bracket`
  - `idex_tap_trigger_flag`
  - `idex_tap_down_stop`
  - `idex_tap_overtravel_stop`
  - `idex_tap_magnet_retainers`
- non-production parts:
  - `mgn7h_rail_keepout`
  - `mgn7h_carriage_keepout`
  - `opb991t11z_sensor_keepout`
  - `magnets`
  - `moving_stack_nominal`
  - `moving_stack_triggered`

Builder visualization should show both nominal and triggered states. The
triggered state can be a ghosted copy of the moving shuttle candidate lifted by
`idex_tap_trigger_lift`, with a second ghost at total overtravel if useful.
For the first T1 packaging pass, also show a "clearance environment" scene where
the existing Sprite, machined mount, belt carriage, cage/fans, and Nitehawk are
opaque enough to inspect collisions. Do not imply the Tap shuttle is already the
Sprite load path.

Production output should include only the printable or machinable Tap adapter
parts. It should not export the machined mount, MGN rail, sensor, magnets, or
existing toolhead context as production parts.

## Placement And Animation Concept

Current placement pattern in `assembling/assemblies/assemblies.yaml`:

- The X rail is aligned to `x_axis_lower_profile_assembly`, then made rigid to
  that profile.
- The left/right X carriages are aligned to `x_axis_rail_assembly` with X
  offsets, then both are treated as rail-relative rigid groups for the nominal
  scene.
- `tool_head_mount_machined_bottom_assembly` is made rigid to
  `x_axis_left_carriage_assembly`; `tool_head_mount_machined_top_assembly` is
  made rigid to `x_axis_right_carriage_assembly`.
- The current Sprite extruder assemblies are centered on the machined mounts
  with `x_axis_sprite_extruder_tool_head_mount_*_offset`, then made rigid to
  the machined mounts.
- Nitehawk boards, fan assemblies, extruder cages, joined fan/cage assemblies,
  and cable shields are placed after the Sprite/machined-mount relationship and
  then made rigid to their local parent.
- In `whole_printer_assembly.yaml`, bed-moving parts receive `bed_y`, X/Z gantry
  parts receive `z_axis`, and each toolhead side receives both the appropriate
  X-carriage animation and `z_axis`. In `tool_heads_assembly.yaml`, the same
  toolhead-side parts receive `x_carriage_1` or `x_carriage_2`.

Tap should follow the same builder-owned placement style. Python should create
reference geometry and named artifacts; `assemblies.yaml` should decide where
those artifacts sit in the real printer scene.

Proposed T1 packaging placement sequence:

1. Place the existing X rail and right X carriage exactly as today.
2. Place `tool_head_mount_machined_top_assembly` exactly as today, rigid to
   `x_axis_right_carriage_assembly`.
3. Place `sprite_extruder_right_assembly` exactly as today, centered on
   `tool_head_mount_machined_top_assembly` with the existing
   `x_axis_sprite_extruder_tool_head_mount_*_offset` parameters, then rigid to
   the machined mount.
4. Place `x_axis_belt_carriage_top_assembly` exactly as today, using the current
   top belt-carriage generator and placement. This part is part of the fixed
   clearance environment for the T1 Tap study.
5. Place the right Nitehawk board, part fans, blower ring, joined fan/cage, and
   cable shield exactly as today. These are collision and service-loop context,
   not Tap-owned parts.
6. Build or place the T1 Tap candidate geometry into this already-placed
   environment. Candidate fixed frame, rail, shuttle, sensor, magnets, and stops
   may reference the placed machined mount, Sprite, belt carriage, and cage/fan
   envelope for clearances.
7. Place `mgn7h_rail_with_carriage_assembly` and `opb991t11z_sensor_assembly`
   relative to Tap candidate reference artifacts when the builder can express
   the relationship cleanly. Keep their reusable hardware identities separate
   from Tap printable geometry.
8. Explicitly defer the mechanical connection between the Tap shuttle and
   `sprite_extruder_right_assembly`. The first pass is a fit study, not a load
   path replacement.

This is intentionally different from the older plan where the Sprite/toolhead
stack was placed to a Tap moving-shuttle reference. For T1-first work, the
existing toolhead stack stays put first; Tap geometry is designed around it.

Tap-internal artifact ownership:

- Author moving-shuttle candidate geometry as Tap-owned geometry, whether it
  remains in the current split `idex_tap_t0_shuttle_assembly` prototype or moves
  into a future T1-named assembly.
- Keep fixed-frame details as Tap-owned geometry: the rail plate, sensor bracket,
  fixed magnet pockets/retainers, fixed hard-stop pads or screws, and fixed
  reference cutters.
- External T1 assemblies remain external. The Tap generator can use them for
  collision and clearance, but should not absorb them as followers or production
  parts.

Helpful reference artifacts to add or preserve for clean placement:

- `rail_mount_reference`: fixed-frame datum for the MGN7H rail.
- `sensor_mount_reference`: fixed-frame datum for the OPB991T11Z sensor.
- `sensor_optical_center_reference`: fixed-frame optical line target.
- `sprite_keepout_reference`: placed Sprite envelope reference.
- `belt_carriage_keepout_reference`: placed top belt carriage envelope reference.
- `future_toolhead_mount_reference`: moving-shuttle datum reserved for the later
  load-path rework, not used for placement in the first T1 packaging pass.

Internal/debug artifacts that should be exposed for visualization and checks,
but not treated as top-level placement steps:

- `shuttle_carriage_mount_reference`: moving-shuttle datum that should coincide
  with `mgn7h_rail_with_carriage_assembly.followers.carriage` at rest.
- `trigger_flag_reference`: moving-shuttle datum for the sensor flag.
- `down_stop_reference` and `overtravel_stop_reference`: fixed/moving stop
  datum pair.

Rigid group summary:

- Existing T1 toolhead rigid groups stay as they are: top machined mount to
  right carriage, right Sprite to top machined mount, and right downstream
  assemblies to the right Sprite.
- Candidate Tap fixed frame may become rigid to
  `tool_head_mount_machined_top_assembly` for visualization once its placement
  is chosen.
- MGN7H rail hardware may become rigid to the candidate Tap fixed frame.
- OPB991T11Z sensor hardware may become rigid to the candidate Tap fixed frame.
- Do not rigid-group `sprite_extruder_right_assembly` or right joined fan/cage
  assemblies to a Tap shuttle in this phase.
- No `rigid_group` entries for `idex_tap_sensor_bracket`,
  `idex_tap_trigger_flag`, fixed magnet retainers, moving magnet targets, or
  stop references when they are followers/non-production artifacts of a Tap
  assembly. Their rigidity is already part of the generated Tap assembly.

Animation should make the mechanism understandable:

- Add `idex_tap_trigger_lift` as a small local-Z animation on the moving Tap
  artifacts only. In the standalone Tap visualization, this should move
  `mgn7h_rail_with_carriage_assembly.followers.carriage`,
  the moving shuttle, the trigger flag, and any explicitly named moving
  magnet/stop artifacts. It should not move the MGN7 rail leader, the OPB991T11Z
  sensor assembly, fixed-frame Tap followers, or the existing right Sprite stack
  in the first packaging pass.
- Add an optional `idex_tap_overtravel` animation using
  `idex_tap_total_travel` to show crash margin and verify that the sensor flag
  is not the overtravel stop.
- In `tool_heads_assembly.yaml`, any T1 Tap packaging scene parts should receive
  `x_carriage_2` if they are physically mounted to the right/top toolhead. Add
  `idex_tap_trigger_lift` only to Tap moving artifacts, not to the fixed T1
  environment.
- In `whole_printer_assembly.yaml`, those same T1 Tap packaging scene parts
  should receive `z_axis` plus `x_carriage_2` if they are physically mounted to
  the right/top toolhead. Add Tap trigger animation only to the same moving Tap
  artifact selection used in `tool_heads_assembly.yaml`.
- Use light, contrasting colors: fixed frame/rail/sensor in light neutral
  colors, moving shuttle/flag in a distinct bright color, and ghosted trigger or
  overtravel states with translucent/light coloring if the builder supports it.

## Parameters To Add

Prefer parameters in `assembling/assemblies/idex_parameters.yaml` and manifest
parameter declarations in the relevant hardware assembly YAML. Keep ownership
split by assembly:

- OPB991T11Z dimensions belong to `opb991t11z_sensor_assembly.yaml`.
- MGN7H rail and carriage dimensions belong to
  `mgn7h_rail_with_carriage_assembly.yaml`.
- Tap-frame dimensions, travel, clearances, magnet pockets, and hard stops
  belong to the current `idex_tap_t0_assembly.yaml` prototype or to a future
  T1-named Tap assembly after the rename/split decision. Do not treat the
  current T0 filename as final semantics.
- Part-to-part placement offsets should live in `assemblies.yaml` placements
  whenever possible, not as hidden transforms inside Python generators.

MGN7H rail-with-carriage assembly parameters:

- `mgn7h_rail_length`
- `mgn7h_rail_width`
- `mgn7h_rail_height`
- `mgn7h_rail_mount_hole_pitch`
- `mgn7h_rail_mount_hole_end_offset`
- `mgn7h_rail_mount_hole_diameter`
- `mgn7h_rail_mount_counterbore_diameter`
- `mgn7h_rail_mount_counterbore_depth`
- `mgn7h_rail_mount_screw_size`
- `mgn7h_carriage_length`
- `mgn7h_carriage_width`
- `mgn7h_carriage_height`
- `mgn7h_carriage_h1_offset`
- `mgn7h_carriage_mount_hole_pitch_x`
- `mgn7h_carriage_mount_hole_pitch_y`
- `mgn7h_carriage_mount_hole_depth`
- `mgn7h_carriage_mount_screw_size`
- `mgn7h_carriage_rest_offset_on_rail`

OPB991T11Z sensor assembly parameters:

- `opb991t11z_body_width`
- `opb991t11z_body_depth`
- `opb991t11z_body_height`
- `opb991t11z_slot_width`
- `opb991t11z_slot_depth`
- `opb991t11z_aperture_width`
- `opb991t11z_optical_center_z`
- `opb991t11z_mount_tab_width`
- `opb991t11z_mount_hole_diameter`
- `opb991t11z_mount_hole_pitch`
- `opb991t11z_wire_exit_width`
- `opb991t11z_wire_exit_depth`

Tap mechanism parameters:

- `idex_tap_frame_thickness`
- `idex_tap_frame_mount_screw_size`
- `idex_tap_shuttle_thickness`
- `idex_tap_shuttle_carriage_screw_size`
- `idex_tap_frame_to_mount_clearance`
- `idex_tap_trigger_lift`
- `idex_tap_total_travel`
- `idex_tap_overtravel_clearance`
- `idex_tap_down_stop_screw_size`
- `idex_tap_down_stop_contact_diameter`
- `idex_tap_down_stop_material_clearance`
- `idex_tap_overtravel_stop_screw_size`
- `idex_tap_overtravel_stop_contact_diameter`
- `idex_tap_trigger_flag_thickness`
- `idex_tap_trigger_flag_width`
- `idex_tap_trigger_flag_slot_clearance`
- `idex_tap_trigger_flag_sensor_overlap_at_rest`
- `idex_tap_trigger_flag_sensor_overlap_at_trigger`
- `idex_tap_sensor_mount_screw_size`
- `idex_tap_sensor_mount_bushing_outer_diameter`
- `idex_tap_sensor_mount_slop_compensation`
- `idex_tap_wire_exit_clearance`
- `idex_tap_service_screw_access_clearance`

Magnet geometry parameters:

- `idex_tap_magnet_diameter`
- `idex_tap_magnet_height`
- `idex_tap_magnet_count`
- `idex_tap_magnet_center_spacing`
- `idex_tap_magnet_pocket_clearance_radial`
- `idex_tap_magnet_pocket_clearance_axial`
- `idex_tap_magnet_retainer_thickness`
- `idex_tap_magnet_gap_at_rest`
- `idex_tap_magnet_gap_at_trigger`
- `idex_tap_magnet_target_screw_size`
- `idex_tap_magnet_target_screw_head_diameter`

Placement inputs for `assemblies.yaml`:

- candidate fixed-frame placement relative to
  `tool_head_mount_machined_top_assembly` and the already-placed right carriage
- Sprite, joined cage/fan, Nitehawk, cable shield, and top belt-carriage keepout
  references derived from their current T1 placements
- MGN7H rail-with-carriage assembly placement relative to the candidate fixed
  frame's `rail_mount_reference`
- moving-shuttle rest alignment against the rail assembly's built-in
  `followers.carriage` reference
- OPB991T11Z sensor placement relative to the candidate fixed frame's
  `sensor_mount_reference` and `sensor_optical_center_reference`
- trigger-state ghost offset for Tap moving artifacts only: normally
  `idex_tap_trigger_lift` in local Z
- overtravel-state ghost offset for Tap moving artifacts only: normally
  `idex_tap_total_travel` in local Z
- a reserved future shuttle-to-toolhead datum, explicitly unused for first-pass
  T1 placement

Derived validation targets, not primary CAD parameters:

- probe force / preload force, estimated from magnet geometry and measured on
  the bench
- trigger repeatability from repeated probe tests
- return reliability after full overtravel
- sensor electrical threshold and input polarity

Do not lock visually tuned values into literal tests. Tests should verify
structure, positive/ranged dimensions, trigger travel relationships, and that
production exports do not accidentally include reference hardware.

## Firmware And Calibration Concept

Stage firmware integration conservatively. The first T1/right/top work is a
mechanical packaging and visualization study, not a firmware authority change:

1. Model and bench-test the OPB991T11Z as an input before making it the Z
   authority.
2. Add wiring truth for the selected input pin only after the target toolhead
   board input and safe pull-up voltage are chosen.
3. Add a Klipper diagnostic macro that reports raw Tap sensor state while the
   current Z homing remains unchanged.
4. For the T1 packaging prototype, run repeatability checks by manually lifting
   only the Tap moving artifacts or a controlled bench fixture before any
   Sprite/toolhead load path is attached.
5. Only after the sensor, mechanics, and actual shuttle-to-toolhead connection
   are proven, choose whether Tap becomes a diagnostic probe, a `[probe]` used
   after normal Z homing, or a future `probe:z_virtual_endstop`.

The current IDEX config intentionally rejects runtime T0 Z offsets: the
T0/left/bottom toolhead is the mechanical Z reference, while T1/right/top
carries a derived offset. A T1-first Tap is therefore not an immediate
replacement for the current Z authority. It is the first sane packaging target
because it has more physical space. Later calibration work must decide whether
the final probing strategy is a migrated T0 Tap, a second T0 mechanism, a T1
diagnostic/reference probe, or a larger IDEX Z-authority change.

Deferred calibration decision points:

- Keep the current safe homing sequence unchanged during the packaging pass.
- Select T1 only for raw sensor-state diagnostics and controlled repeatability
  experiments; do not store it as the bed Z reference yet.
- Compare any T1 Tap measurements against the existing T0 baseline before using
  them for printer calibration.
- Decide the final probe authority only after the mechanical connection between
  Tap shuttle and Sprite/toolhead exists and is repeatable.
- Later: replace manual/vision-only T1 correction with a stepper/cam adjuster if
  the design still needs active T1 relative-Z correction.

## Risks

- Added moving mass can hurt ringing and X carriage dynamics.
- The moving shuttle can introduce nozzle compliance if the hard stop and rail
  preload are not stiff enough.
- Magnet force can be too low for accelerations or too high for safe probing.
- The OPB991T11Z sensor mount holes are not naturally M2-locating features.
- Wiring can become fragile if the moving stack has no explicit service loop.
- Heat from the hotend may soften printed sensor/flag/magnet retainers.
- If the trigger flag is the crash stop, the sensor will eventually lose.
- A successful T1 package does not by itself solve T0/left/bottom nozzle probing
  or the current firmware Z-reference model.
- The T0 bottom belt-carriage conflict remains unresolved and may need a
  different mechanism or layout.
- Existing `idex_tap_t0_*` prototype names can mislead integration if they are
  silently reused for T1/right/top semantics.

## Implementation Order

1. Use this document as the checkpoint: no code, YAML, or public API changes are
   implied by the concept update itself.
2. Build a T1-focused placement/collision visualization that keeps
   `x_axis_right_carriage_assembly`, `tool_head_mount_machined_top_assembly`,
   `sprite_extruder_right_assembly`, `x_axis_belt_carriage_top_assembly`, and
   the right cage/fan/Nitehawk stack where they are today.
3. Overlay the existing exploratory Tap hardware and frame/shuttle candidates in
   that placed T1 environment to identify real clearances, collisions, and
   service-access problems.
4. Decide whether to introduce new `idex_tap_t1_*` assemblies or explicitly
   rename/split the current `idex_tap_t0_*` prototypes before production routing.
5. Rework the Tap assembly contract so generators consume injected placed
   context for collision and clearance, instead of moving or replacing the
   existing Sprite/mount/belt-carriage relationship.
6. Iterate the candidate fixed frame, MGN7H rail placement, OPB991T11Z sensor
   placement, moving shuttle, trigger flag, magnets, stops, and wire keepouts in
   the T1 envelope.
7. Visualize nominal, triggered, and overtravel states with only Tap moving
   artifacts animated.
8. Only after the fit study is clean, design the mechanical connection between
   the Tap shuttle and the Sprite/toolhead stack.
9. Add production routing, focused assembly tests, wiring truth, and firmware
   diagnostics after the T1 mechanical package and naming contract are stable.

## Out Of Scope For This Draft

- T1 stepper/cam Z adjuster.
- T0/left/bottom Tap implementation.
- Mechanical connection between the T1 Tap shuttle and Sprite/toolhead stack.
- Final Klipper probe configuration.
- Detailed magnet force calculation.
- Final MGN7H vendor-specific rail dimensions.
- Copying Voron Tap CAD geometry.
- Changing the machined top mount geometry.
