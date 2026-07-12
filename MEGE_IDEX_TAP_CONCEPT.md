# MEGE IDEX Tap Concept

Status: concept draft.

Goal: add a Voron Tap style nozzle contact probe to the MEGE IDEX, first for
T0 only. T1 remains a normal rigid toolhead for now; its Z offset is handled by
vision calibration today and may later be corrected by a stepper/cam mechanism.

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

- Build Tap for T0 first.
- Do not modify `tool_head_mount_machined_top_assembly.leader`. It is treated as
  an existing machined part and a fixed attachment datum.
- Add the Tap mechanism around the existing machined mount instead of changing
  the machined mount generator.
- Use a vertical MGN7H linear guide for the Tap motion.
- Use M2 screws for the rail, carriage-side hardware, sensor bracket, and small
  retainers where practical.
- Model the OPB991T11Z wired optical interrupter and include it in the Tap
  assembly visualization.
- Model magnets and make their preload/reset role visible in the assembly.
- Keep T1 out of this scope except for documenting the future Z-offset path.
- Use the assembly-first builder flow: YAML assembly contract first, generator
  as implementation behind that contract.

Current repo checkpoint: firmware currently treats `T0` as the left carriage and
mechanically calibrated Z, while `T1` carries the runtime Z offset. The concept
also has the explicit CAD anchor `tool_head_mount_machined_top_assembly.leader`.
Before CAD work starts, reconcile that naming: either T0's Tap really attaches
to the top/right machined mount, or the top mount name is the required geometry
anchor even though the first probed tool is firmware T0. Do not silently infer
left/right from the tool number inside the generator.

## Mechanical Stack

Baseline stack, from fixed to moving:

1. Fixed datum:
   `tool_head_mount_machined_top_assembly.leader`, unchanged.
2. Fixed Tap frame:
   A printed or machined adapter plate bolts to the existing machined mount
   holes/faces. This part carries the MGN7 rail, the stationary sensor body, the
   fixed-side magnets, and hard stops.
3. Vertical guide:
   A short MGN7 rail is mounted vertically on the fixed Tap frame. The carriage
   moves with the toolhead stack. If packaging later proves better with the rail
   moving and carriage fixed, that can be considered, but the first concept
   should prefer fixed rail and moving carriage because sensor and wire routing
   are simpler.
4. Moving shuttle:
   A compact shuttle bolts to the MGN7H carriage and carries the toolhead
   mount/extruder-side load. The current direct attachment from toolhead mount
   to the machined carriage plate is replaced by this shuttle path.
5. Trigger flag:
   A thin opaque blade on the moving shuttle passes through the OPB991T11Z slot.
   The sensor should trigger early in the upward travel, not at the mechanical
   overtravel stop.
6. Magnetic return:
   Magnets preload the moving shuttle downward against a hard stop. The hard
   stop defines the printing position; the magnets only seat the mechanism
   there. They must not be the precision datum by themselves.

During normal printing, the shuttle is seated down against the hard stop and the
toolhead behaves as rigidly as possible. During probing, nozzle contact pushes
the toolhead/shuttle upward in +Z relative to the fixed mount. The optical flag
changes sensor state after a small lift, and the remaining travel is reserved as
overtravel/crash margin.

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

Proposed new assembly files:

- `assembling/assemblies/idex_tap_t0_assembly.yaml`
- `src/mege_ender_3v3ke_idex/designs/assemblies/idex_tap_t0_assembly.py`
- `assembling/assemblies/mgn7h_rail_with_carriage_assembly.yaml`
- `src/mege_ender_3v3ke_idex/designs/assemblies/mgn7h_rail_with_carriage_assembly.py`
- `assembling/assemblies/opb991t11z_sensor_assembly.yaml`
- `src/mege_ender_3v3ke_idex/designs/assemblies/opb991t11z_sensor_assembly.py`

The new generator should not import another assembly generator directly. It
should consume injected dependencies from YAML. At minimum:

- `fixed_tool_head_mount`: the unchanged
  `tool_head_mount_machined_top_assembly`
- `mgn7h_rail_with_carriage`: injected MGN7H rail assembly with built-in
  `carriage` follower
- `opb991t11z_sensor`: standalone injected OPB991T11Z sensor assembly
- moving toolhead context for collision checks and visualization
- optional fan/cage/Nitehawk context if those parts constrain the Tap envelope

Prefer YAML-based placement in `assembling/assemblies/assemblies.yaml` whenever
the builder can express the relationship. Place the MGN7H rail-with-carriage
assembly relative to the fixed Tap frame, place the OPB991T11Z sensor relative
to the sensor bracket, and place the tapped external toolhead assemblies
relative to the Tap moving-shuttle reference in YAML. Use the rail assembly's
built-in `carriage` follower as the rest-position reference for the
moving-shuttle geometry and Tap animation; do not introduce a separate carriage
assembly. The Tap Python generator may create adapter geometry, expose
cutters/keepouts, and use injected hardware for derived clearances, but it
should not re-export or manually arrange the reusable hardware assemblies just
to make them visible. Visualization and scene composition should come from
builder dependencies, injected parts, and top-level placement rules.

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
triggered state can be a ghosted copy of the moving shuttle/toolhead lifted by
`idex_tap_trigger_lift`, with a second ghost at total overtravel if useful.

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

Proposed nominal placement sequence:

1. Place the existing X rail, X carriage, and unchanged machined mount exactly as
   today. This keeps the machined mount as the fixed datum.
2. Place `idex_tap_t0_assembly.leader` fixed frame against
   `tool_head_mount_machined_top_assembly.leader` or the chosen T0 fixed mount
   after the T0/top mapping checkpoint is resolved. Use normal YAML placement:
   align the Tap frame to the machined mount with `CENTER`, stack it with
   `STACK_BOTTOM`, and add a `post_translation` only if clearance or service
   access needs a tuned offset.
3. Add a `rigid_group` from `idex_tap_t0_assembly` to the selected machined
   mount after the frame is aligned. This is the same assembly-to-assembly
   pattern already used for `tool_head_mount_machined_top_assembly` to
   `x_axis_right_carriage_assembly` and for `sprite_extruder_right_assembly` to
   `tool_head_mount_machined_top_assembly`; it is not a list of Tap-internal
   features.
4. Rotate/place `mgn7h_rail_with_carriage_assembly` so its travel axis is local
   Z. Align its rail centerline to
   `idex_tap_t0_assembly.followers.rail_mount_reference`, stack it onto the
   fixed frame face, and add a `rigid_group` from
   `mgn7h_rail_with_carriage_assembly` to `idex_tap_t0_assembly`.
   The assembly's built-in `followers.carriage` is already positioned at the
   nominal seated/rest position relative to the rail; do not create or place a
   separate MGN carriage assembly.
5. Place `opb991t11z_sensor_assembly` to the sensor bracket in YAML. Align the
   sensor slot/optical center to a named `sensor_slot_reference` or
   `optical_center_reference` on the bracket, then add a `rigid_group` from
   `opb991t11z_sensor_assembly` to `idex_tap_t0_assembly`. The sensor should
   not receive Tap trigger animation.
6. Place the Sprite/toolhead stack for the tapped tool to the moving shuttle,
   not directly to the machined mount. Reuse the existing Sprite-to-mount
   offsets where they still represent the Sprite interface, but target
   `idex_tap_t0_assembly.followers.toolhead_mount_reference` instead of
   `tool_head_mount_machined_top_assembly`. For the current top/right side this
   means aligning and then rigidly grouping
   `sprite_extruder_right_assembly`, `nitehawk_board_right_assembly`,
   `extruder_cage_right_joined_assembly`, and `part_fan_right_joined_assembly`
   to the moving-shuttle/toolhead reference. If the firmware T0 mapping resolves
   to the bottom/left side instead, use the corresponding left assemblies:
   `sprite_extruder_left_assembly`, `nitehawk_board_left_assembly`,
   `extruder_cage_left_joined_assembly`, and `part_fan_left_joined_assembly`.
7. Cable shields and strain relief need an explicit decision. Existing
   `tool_head_cable_attach_shield_right_assembly` or
   `tool_head_cable_attach_shield_left_assembly` stays rigid to the machined
   mount if it is bolted there, or is re-placed and rigidly grouped to the
   moving shuttle if it becomes an extruder-side cable support. The
   visualization should make this split visible so wire service loops can be
   checked.

Tap-internal artifact ownership:

- Author the moving-shuttle geometry inside `idex_tap_t0_assembly` against
  `mgn7h_rail_with_carriage_assembly.followers.carriage`. The Tap assembly
  should expose `idex_tap_moving_shuttle`, `idex_tap_trigger_flag`, the moving
  magnet targets, the moving stop target, and `toolhead_mount_reference` as
  followers or named artifacts. Because these are Tap-internal artifacts, they
  do not need `rigid_group` entries; they need to be selected together only in
  visualization animation.
- Keep fixed-frame details inside `idex_tap_t0_assembly`: the sensor bracket,
  fixed magnet pockets/retainers, fixed hard-stop pads or screws, and fixed
  reference cutters. These are not placement-sequence entries unless one of them
  is split into its own assembly later.

Helpful reference artifacts to add to `idex_tap_t0_assembly` for clean
placement:

- `rail_mount_reference`: fixed-frame datum for the MGN7H rail.
- `sensor_mount_reference`: fixed-frame datum for the OPB991T11Z sensor.
- `sensor_optical_center_reference`: fixed-frame optical line target.
- `toolhead_mount_reference`: moving-shuttle datum for the Sprite/toolhead stack.

Internal/debug artifacts that should be exposed for visualization and checks,
but not treated as top-level placement steps:

- `shuttle_carriage_mount_reference`: moving-shuttle datum that should coincide
  with `mgn7h_rail_with_carriage_assembly.followers.carriage` at rest.
- `trigger_flag_reference`: moving-shuttle datum for the sensor flag.
- `down_stop_reference` and `overtravel_stop_reference`: fixed/moving stop
  datum pair.

Rigid group summary:

- `idex_tap_t0_assembly` rigid to the selected fixed machined mount:
  `tool_head_mount_machined_top_assembly` or
  `tool_head_mount_machined_bottom_assembly` after the T0/top mapping is
  resolved.
- `mgn7h_rail_with_carriage_assembly` rigid to `idex_tap_t0_assembly`. The rail
  leader is fixed; its built-in `followers.carriage` is the only rail-assembly
  artifact that participates in Tap trigger animation.
- `opb991t11z_sensor_assembly` rigid to `idex_tap_t0_assembly`. It is fixed and
  does not participate in Tap trigger animation.
- The tapped toolhead's separate external assemblies rigid to
  `idex_tap_t0_assembly.followers.toolhead_mount_reference`: the selected
  `sprite_extruder_*_assembly`, `nitehawk_board_*_assembly`,
  `extruder_cage_*_joined_assembly`, `part_fan_*_joined_assembly`, and any
  cable-shield assembly that is physically bolted to the moving shuttle.
- No `rigid_group` entries for `idex_tap_sensor_bracket`,
  `idex_tap_trigger_flag`, fixed magnet retainers, moving magnet targets, or
  stop references when they are followers/non-production artifacts of
  `idex_tap_t0_assembly`. Their rigidity is already part of the generated Tap
  assembly.

Animation should make the mechanism understandable:

- Add `idex_tap_trigger_lift` as a small local-Z animation on the moving Tap
  artifacts only. In the standalone Tap/toolhead visualization, this should move
  `mgn7h_rail_with_carriage_assembly.followers.carriage`,
  `idex_tap_t0_assembly.followers.idex_tap_moving_shuttle`,
  `idex_tap_t0_assembly.followers.idex_tap_trigger_flag`, any explicitly named
  moving magnet/stop artifacts, and the tapped external toolhead assemblies.
  It should not move the MGN7 rail leader, the OPB991T11Z sensor assembly, or
  fixed-frame Tap followers.
- Add an optional `idex_tap_overtravel` animation using
  `idex_tap_total_travel` to show crash margin and verify that the sensor flag
  is not the overtravel stop.
- In `tool_heads_assembly.yaml`, the fixed Tap assembly, MGN7 rail leader,
  OPB991T11Z sensor assembly, MGN7 carriage follower, moving shuttle followers,
  and tapped external toolhead assemblies should receive the same `x_carriage_1`
  or `x_carriage_2` animation as the rest of that toolhead. Add
  `idex_tap_trigger_lift` only to the MGN7 carriage follower, moving shuttle
  followers, and tapped external toolhead assemblies.
- In `whole_printer_assembly.yaml`, those same tapped-tool parts should receive
  `z_axis` plus the selected X-carriage animation. Add the Tap trigger
  animation only to the same moving artifact selection used in
  `tool_heads_assembly.yaml`.
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
  belong to `idex_tap_t0_assembly.yaml`.
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

- fixed-frame placement relative to `tool_head_mount_machined_top_assembly`
- MGN7H rail-with-carriage assembly placement relative to the fixed frame
- moving-shuttle rest alignment against the rail assembly's built-in
  `followers.carriage` reference
- OPB991T11Z sensor placement relative to the sensor bracket
- external tapped-toolhead assembly placement relative to
  `idex_tap_t0_assembly.followers.toolhead_mount_reference`
- trigger-state ghost offset: normally `idex_tap_trigger_lift` in local Z
- overtravel-state ghost offset: normally `idex_tap_total_travel` in local Z

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

Stage firmware integration conservatively:

1. Model and bench-test the OPB991T11Z as an input before making it the Z
   authority.
2. Add wiring truth for the selected input pin and regenerate the wiring
   diagrams.
3. Add a Klipper diagnostic macro that reports raw Tap sensor state while the
   current Z homing remains unchanged.
4. Run repeatability tests by manually lifting the T0 toolhead and then probing
   against a controlled surface.
5. Only after the sensor and mechanics are proven, choose whether Tap becomes a
   `[probe]` used after normal Z homing or the actual `probe:z_virtual_endstop`
   for Z homing.

The current IDEX config intentionally rejects runtime T0 Z offsets: T0 Z is the
mechanical reference, while T1 Z is a derived offset. This fits the Tap concept
well. Tap should become the way T0 establishes the real nozzle/bed reference;
T1 remains an offset against that reference until the future vision or cam
system closes the loop.

Calibration flow target:

- Home axes using the current safe sequence.
- Select T0.
- Probe bed with the T0 Tap.
- Store or apply T0 Z reference through the normal Klipper/probe mechanism.
- Use vision to measure T1 relative to T0, or apply the existing T1 Z offset.
- Later: replace manual/vision-only T1 correction with a stepper/cam adjuster
  that drives T1 to zero relative Z offset.

## Risks

- Added moving mass can hurt ringing and X carriage dynamics.
- The moving shuttle can introduce nozzle compliance if the hard stop and rail
  preload are not stiff enough.
- Magnet force can be too low for accelerations or too high for safe probing.
- The OPB991T11Z sensor mount holes are not naturally M2-locating features.
- Wiring can become fragile if the moving stack has no explicit service loop.
- Heat from the hotend may soften printed sensor/flag/magnet retainers.
- If the trigger flag is the crash stop, the sensor will eventually lose.
- If the top/bottom or T0/T1 naming is resolved incorrectly, the design can be
  mechanically right but integrated on the wrong carriage.

## Implementation Order

1. Confirm the T0/top-mount mapping and choose the exact injected fixed mount.
2. Add `opb991t11z_sensor_assembly` as a reusable hardware-reference assembly
   with its own YAML parameters and named artifacts.
3. Extend/copy the existing MGN12 rail/carriage code in `mgh_linear.py` to add
   an MGN7H rail/carriage model with the same leader/follower and named-cutter
   conventions.
4. Add standalone `mgn7h_rail_with_carriage_assembly` wrapper with rail as
   leader, carriage as a named follower, visualization output, and no production
   parts.
5. Create `idex_tap_t0_assembly.yaml` with injected fixed mount, injected
   hardware-reference assemblies, and visual context.
6. Use `assembling/assemblies/assemblies.yaml` placement rules to position the
   rail-with-carriage assembly, sensor, external tapped-toolhead assemblies, and
   cross-assembly rigid groups whenever possible.
7. Create the fixed frame and moving shuttle with named artifacts.
8. Add sensor bracket, trigger flag, magnets, hard stops, and wire keep-outs.
9. Add production rules for only the new Tap printable/machined parts.
10. Visualize the assembly in nominal, triggered, and overtravel states.
11. Add focused tests for assembly wiring, artifact names, positive dimensions,
    trigger travel ordering, and production/reference-part separation.
12. After CAD fit looks sane, add wiring truth and firmware diagnostics.

## Out Of Scope For This Draft

- T1 stepper/cam Z adjuster.
- Final Klipper probe configuration.
- Detailed magnet force calculation.
- Final MGN7H vendor-specific rail dimensions.
- Copying Voron Tap CAD geometry.
- Changing the machined top mount geometry.
