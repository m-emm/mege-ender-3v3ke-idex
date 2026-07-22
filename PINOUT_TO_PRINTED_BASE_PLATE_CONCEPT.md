# Pinout-to-Printed-Base-Plate Concept

## Status and scope

This document proposes a generic path from a `mege-circuits` pinout YAML file
to a printable electronics base plate and rigid, screw-down component holders.
The first target is
`klipper_setup/klipper_config/wiring/rp2040plus_btt_tmc5160t_plus_y.yaml`, but
the generator must not contain TMC5160T-, Pico-, or printer-specific placement
logic.

The generated assembly contains:

- one printable base plate;
- separate printable downholder parts selected per physical component;
- self-threading holes in the base plate and clearance holes in the
  downholders;
- non-production reference geometry for the real components;
- in particular, an exact-size non-production frame for the TMC5160T Plus
  `box`.

It does **not** generate the surrounding housing, side walls, lid, fan mount,
TPU cover, cable routing, or electrical wiring. Those remain consumers of the
base-plate assembly.

## Strict ownership boundary

There are two distinct inputs. Neither is allowed to duplicate the other's
responsibilities.

### Pinout YAML: circuit and placement truth

The pinout YAML owns facts which remain true regardless of how the carrier is
manufactured:

- electrical pin sets, pins, and nets;
- the single shared set of raster coordinates;
- grouping pin sets into the real physical components which provide them;
- the semantic component type, such as `rp2040_plus_2x20` or `ar20_2x10`;
- which grouped contacts are through-board contacts;
- the semantic downholder choice, such as `corner`, `center_strip`,
  `perimeter_frame`, `pin_line_clamp`, or `none`;
- physical module boxes and their raster dimensions.

The downholder choice belongs here because it follows the type and topology of
the retained component: a Pico needs corner retention, while a long DIL socket
needs a center strip. It is a semantic selection only; it carries no screw,
thickness, clearance, or printable geometry values.

The existing `boxes` section also belongs here. A 64 x 57 mm driver is a real
circuit-module footprint, just as its terminal row is real circuit topology.
The box remains expressed on the same raster as the pins and must not be
redeclared by the CAD assembly.

### Assembly parameters: manufacturing truth

The assembly instantiation, normally through `idex_parameters.yaml` and an
assembly resource, owns every construction and manufacturing dimension:

- raster pitch in millimetres;
- base-plate thickness, border, corner radius, and edge clearances;
- wire-wrap pin-tail size and pass-through clearance;
- physical body margins around a component's pin envelope;
- component height and clamp-surface height;
- downholder strip width, thickness, overlap, and body clearance;
- mount-eye size and offset;
- screw standard, length, clearance diameter, and head clearance;
- self-threading hole dimensions and lead-in parameters;
- preview-frame rail width and height;
- underside wire-wrap keepout depth.

None of those values may appear in the pinout YAML. They are supplied when the
generic assembly is instantiated and may be tuned for material, printer,
fastener, socket vendor, or manufacturing process without modifying circuit
data.

### Geometry code: calculation only

The Python generator owns algorithms, not project measurements. It combines:

1. the pinout's electrical topology, grouping, boxes, and raster coordinates;
2. the assembly's mechanical parameters and component profiles.

It derives geometry, validates clearances, and emits parts. It must not hide
project-specific dimensions or component coordinates in Python constants.

This split is the central rule of the design:

| Concern | Owner |
|---|---|
| Pin and net topology | Pinout YAML |
| Raster X/Y placement | Pinout YAML |
| Pin sets belonging to one real component | Pinout YAML |
| Semantic component/downholder type | Pinout YAML |
| Real module box size and position | Pinout YAML |
| Millimetres per raster pitch | Assembly parameters |
| Plate and downholder dimensions | Assembly parameters |
| Fasteners and printable clearances | Assembly parameters |
| Geometry construction | Generic Python generator |

## One layout, one coordinate system

The pinout YAML remains the only X/Y placement authority. Assembly parameters
may describe dimensions and clearances, but they must never provide a second
component origin.

The generator resolves every physical item from either:

1. existing `pin_sets`, whose pin coordinates define the item's location and
   orientation; or
2. an existing `boxes` entry, whose `top_left` and `size_pitches` define its
   exact footprint.

Moving a pin set or box in the pinout YAML therefore moves the diagram,
base-plate holes, reference geometry, and downholders together. The top and
bottom SVG transformations are presentation only and are never CAD input.

The coordinate contract is:

- X increases to the right and Y increases upward when viewed from the
  component side;
- coordinates are in raster pitches;
- pin coordinates are contact centres;
- a `box` extends rightward and downward from `top_left`, as in the SVG
  renderer;
- the assembly-supplied raster pitch converts those coordinates to
  millimetres;
- CAD X/Y retain the component-side orientation, followed only by one global
  translation that places the fitted plate at a convenient origin.

No automatic packing or component repositioning is allowed. If parts overlap
or a downholder has no room, generation fails with the conflicting component
names; the shared YAML coordinates must then be corrected.

## Existing geometry patterns to reuse

### Base plate

`board_holder_assembly.py` already demonstrates the useful base idea: compute
a combined physical envelope, add a configurable border, create a plate, and
use component geometry as cutters. The new generator should retain that
geometry-first approach and `LeaderFollowersCuttersPart` composition, but it
must not depend on the existing assembly's board-count layout, TPU cover,
plugs, walls, lid, fan, or enclosure hardware. The Pico USB cable bridge is
the one retained pattern: it is derived from the Pico pin rows and the
assembly-supplied connector/cable dimensions, fused into the plate, and cut
through by the cable passage.

The generic helper should be implemented independently or extracted as a
public reusable helper; it should not call private functions from
`board_holder_assembly.py`.

### Rigid downholders and screw holes

The downholder geometry should follow the `strip_downholder` and mount-eye
pattern in `vision_light_mount_assembly.py`:

- a rigid printable strip or corner land bears on the retained component;
- rounded mount eyes extend beyond its footprint;
- the downholder receives loose screw-clearance holes;
- the base plate receives lead-in self-threading holes made with
  `create_self_threading_hole_cutter`;
- screw visuals are non-production parts.

The proven M2.5 setup is a useful starting value, but its screw size, screw
length, downholder thickness, eye clearance, and self-threading adjustment are
assembly parameters. They are not pinout schema fields and are not constants
hidden in geometry code.

## Pinout schema extension: `physical_components`

Add one optional top-level `physical_components` list to `mege-circuits`.
`mege-circuits` parses and validates this neutral topology without importing
ShellForgePy.

Each record may contain:

- `id`: unique stable component identity;
- `label`: optional human-readable name;
- `component_type`: semantic key used by the assembly to select a supplied
  mechanical profile;
- `pin_sets`: all existing pin sets that belong to this real component;
- `through_pin_sets`: optional subset whose contacts physically pass through
  the carrier; omission means all listed pin sets;
- `downholder`: semantic retention kind: `corner`, `center_strip`,
  `perimeter_frame`, `pin_line_clamp`, or `none`;
- `box`: optional reference to an existing exact-size physical module box.

There are deliberately no millimetre values in this structure.

An illustrative extension for the current TMC5160T Plus pinout is:

```yaml
physical_components:
  - id: pico
    label: RP2040-Plus
    component_type: rp2040_plus_2x20
    pin_sets: [pico_left, pico_right]
    downholder: corner

  - id: socket_b
    label: Socket B
    component_type: ar20_2x10
    pin_sets: [socket_b_left, socket_b_right]
    downholder: center_strip

  - id: socket_a
    label: Socket A
    component_type: ar20_2x10
    pin_sets: [socket_a_left, socket_a_right]
    downholder: center_strip

  - id: u1_socket
    label: U1 SN7407N socket
    component_type: dip14_socket
    pin_sets: [u1_left, u1_right]
    downholder: center_strip

  - id: socket_hv
    label: HV detector socket
    component_type: ar20_2x10
    pin_sets: [socket_hv_left, socket_hv_right]
    downholder: center_strip

  - id: socket_c
    label: Socket C
    component_type: ar20_2x10
    pin_sets: [socket_c_left, socket_c_right]
    downholder: center_strip

  - id: tmc_adapter
    label: TMC5160T Plus StepStick adapter
    component_type: stepstick_adapter
    pin_sets: [tmc1_j1, tmc1_j2, tmc1_top]
    downholder: perimeter_frame

  - id: external_io_pin_line
    label: 18-pin fuse, power, spare, and Y-endstop row
    component_type: pin_line
    pin_sets: [external_io]
    downholder: pin_line_clamp

  - id: tmc5160t_plus_driver
    label: TMC5160T Plus
    component_type: boxed_module
    pin_sets: [tmc5160_hv]
    through_pin_sets: []
    box: tmc5160t_plus_driver
    downholder: none
```

The final list reflects the real construction. The 18-pin line replaces the
separate fuse, power-input, and endstop pin components. From its power end it
provides separate external-fuse output and input contacts, two switched-24V
contacts, one empty isolation contact, two ground contacts, eight unassigned
contacts, and the three endstop contacts. The serviceable 5 A fuse is external
to the carrier and connects only between its two dedicated line contacts; the
generator therefore creates no fuse body, fuse holes, or fuse retainer. These
are topology decisions made in the pinout, not coordinates or dimensions
added by CAD code.

### Why this is not `discrete_view.groups`

`discrete_view.groups` controls SVG presentation. A CAD component grouping is
a physical-topology fact needed even if no discrete SVG is rendered. The two
features may refer to the same pin sets, but the assembly must consume
`physical_components`, never presentation groups.

### Pin-set ownership and contact roles

A pin set may belong to exactly one physical component. This prevents two CAD
parts from cutting holes for the same contacts.

`through_pin_sets` distinguishes contacts which need plate pass-throughs from
contacts which merely belong to or are exposed by the component. The StepStick
adapter's J1 and J2 rows **and** its separate two-pin `DIAG0`/`DIAG1` row all
pass through the carrier, so the adapter omits `through_pin_sets` and uses the
default that all three grouped pin sets require holes. `DIAG0` remains
electrically unused in the current circuit, but its physical pin still needs a
hole. Only `DIAG1` connects to the protected Pico diagnostic input. By
contrast, a boxed driver's screw-terminal row is associated with the driver,
but those terminals do not pass through the carrier plate.

An explicitly empty `through_pin_sets` means no grouped contacts penetrate the
plate. An omitted key defaults to all `pin_sets`.

### Boxes

The existing `boxes` records remain the sole source of exact module outline and
position. For example:

```yaml
boxes:
  - id: tmc5160t_plus_driver
    label: TMC5160T Plus
    top_left: [42, 36]
    size_pitches: [25.1968503937, 22.4409448819]
```

The `physical_components` record references this box; it does not repeat its
position or dimensions. Box dimensions are allowed in the pinout because they
describe the real circuit module and participate in the shared raster layout.

## Assembly-side mechanical parameters

Mechanical profiles are selected by `component_type`, but their measurements
come from the assembly instantiation. A profile may contain body margins around
the pin envelope, height, clamp height, corner radius, and any manufacturing
clearance required to model that component.

The project may expose the values as named parameters in
`assembling/assemblies/idex_parameters.yaml`, or in a dedicated imported
mechanical-parameter YAML if that keeps the main parameter file manageable.
Either way, the values enter through the assembly resource's `Properties`.

A schematic example is:

```yaml
Parameters:
  pinout_plate_raster_pitch:
    Type: Float
  pinout_plate_thickness:
    Type: Float
  pinout_plate_border:
    Type: Float
  pinout_plate_corner_radius:
    Type: Float
  pinout_pin_tail_width:
    Type: Float
  pinout_pin_pass_through_clearance:
    Type: Float
  pinout_downholder_thickness:
    Type: Float
  pinout_downholder_strip_width:
    Type: Float
  pinout_mount_screw_size:
    Type: String
  pinout_mount_screw_length:
    Type: Float
  pinout_mount_eye_head_clearance:
    Type: Float
  pinout_self_threading_core_radius_adjustment:
    Type: Float
  pinout_reference_frame_width:
    Type: Float
  pinout_reference_frame_height:
    Type: Float

  # Measured body profile for component_type: rp2040_plus_2x20
  pinout_rp2040_left_margin:
    Type: Float
  pinout_rp2040_right_margin:
    Type: Float
  pinout_rp2040_top_margin:
    Type: Float
  pinout_rp2040_bottom_margin:
    Type: Float
  pinout_rp2040_clamp_surface_height:
    Type: Float

  # Equivalent measured profile parameters follow for ar20_2x10,
  # dip14_socket, stepstick_adapter, and any connector component types.
```

This example describes ownership, not final names or measurements. The concrete
assembly configuration should follow the repository's existing parameter and
resource conventions. If the assembly resource system cannot pass mappings,
the wrapper builds internal profile objects from explicit named parameters;
that is preferable to moving mechanical profiles into the pinout.

The Python boundary should make the split visible. Approximately:

```python
def create_pinout_base_plate_assembly(
    *,
    pinout_yaml_path: str | Path,
    raster_pitch_mm: float,
    plate_thickness_mm: float,
    plate_border_left_mm: float,
    plate_border_right_mm: float,
    plate_border_top_mm: float,
    plate_border_bottom_mm: float,
    plate_corner_radius_mm: float,
    pin_tail_width_mm: float,
    pin_pass_through_clearance_mm: float,
    pin_row_base_width_mm: float,
    pin_row_slot_clearance_mm: float,
    pin_row_vertical_clearance_mm: float,
    wire_wrap_pin_length_mm: float,
    wire_wrap_pin_base_thickness_mm: float,
    top_pin_length_mm: float,
    pin_line_clamp_base_length_mm: float,
    pin_line_clamp_holder_slack_mm: float,
    pin_line_clamp_vertical_slack_mm: float,
    pin_line_clamp_lip_size_mm: float,
    pin_line_clamp_slit_width_mm: float,
    screw_size: str,
    screw_length_mm: float,
    self_threading_core_radius_adjustment_mm: float,
    downholder_thickness_mm: float,
    downholder_strip_width_mm: float,
    mount_eye_head_clearance_mm: float,
    reference_frame_width_mm: float,
    reference_frame_height_mm: float,
    component_profiles: ComponentProfileRegistry,
    downholder_profiles: DownholderProfileRegistry,
    usb_bridge_wall_thickness_mm: float,
    usb_cable_hole_width_mm: float,
    usb_cable_hole_height_mm: float,
    pico_usb_connector_width_mm: float,
    pico_usb_connector_thickness_mm: float,
    pico_usb_connector_depth_mm: float,
    pico_usb_connector_offset_mm: float,
) -> LeaderFollowersCuttersPart:
    ...
```

The assembly wrapper may construct the two registries from flat resource
properties. The generic geometry function should receive explicit values and
must not read `idex_parameters.yaml` directly.

## Footprint derivation

For a pin-set-backed component, the generator calculates the axis-aligned
envelope of the referenced through-contact centres. It then expands the four
edges by the assembly-supplied mechanical profile for that `component_type`.
Named margins are required because modules such as the Pico are asymmetric and
have a meaningful USB/top edge.

The profile does not contain an X/Y origin. It is always applied to the
pinout-derived pin envelope. Thus changing a body measurement cannot move its
pin centres, and moving its pins cannot leave the CAD body behind.

The long and short axes are derived from the resulting body footprint. A
mechanical component profile may supply an orientation rule for ambiguous
footprints, but never an absolute X/Y location.

A box-backed component uses the referenced box directly for its X/Y footprint.
No body margins or duplicate size are needed unless the assembly adds a
manufacturing clearance around it.

## Downholder variants

The pinout selects the following semantic kind; the assembly parameters define
its actual printable geometry.

### `corner`

This is the Pico/RP2040-Plus pattern.

- One printable grid has two rails resting on the two 20-pin rows.
- Three one-raster bridges cross the board at assembly-configured, bottom-based
  pin-row indices.
- Four mount eyes extend outside the two long sides while remaining within the
  Pico's top/bottom pin extent.
- Each eye is a filleted land with an unfilleted face stacked against its rail,
  so the eye and rail share a full joining face rather than touching at an
  edge.
- No holder member enters the USB bridge or cable-passage keepout.
- Each eye's loose clearance hole aligns with a self-threading hole in the base
  plate.

Contact overlap, eye offset, strip width, clamp height, screw size, and all
clearances come from the assembly's `corner` profile and component profile.

### `center_strip`

This is the DIL and AR20 socket pattern.

- One narrow strip runs through the socket's central channel along its long
  axis.
- One rounded mount eye extends beyond each short end.
- The strip and eyes form one printable piece.
- The two loose holder holes align with base-plate self-threading holes.

The assembly supplies strip width, thickness, clamp height, body clearance,
eye geometry, and screw details. Socket downholders are installed before
plug-in ICs, resistors, diodes, and transistors. The real socket channel must be
fit-checked; the generator must not silently invent a side-offset strip if the
configured profile does not fit.

### `perimeter_frame`

This is the StepStick-adapter retention pattern.

- Two rails bear on the adapter's two long pin rows.
- One crossbar closes each short end, one raster pitch beyond the first and
  last pin positions.
- One mount eye extends outward from each short-edge crossbar.
- Each eye is a filleted land whose flat joining face is stacked against its
  crossbar.
- The two loose holder holes align with base-plate self-threading holes.
- Additional through-pin sets, such as the adapter's two-pin diagnostic row,
  still receive their plate slot but do not define a third frame rail.

The assembly supplies rail width, crossbar width, holder thickness, clamp
height, eye geometry, and screw details. The pinout supplies only the
`perimeter_frame` selection and the adapter's real pin-set grouping.

### `pin_line_clamp`

This is the retained SIL row pattern from the original board holder.

- One physical component owns exactly one collinear through-pin set.
- The pin count and row direction come entirely from that pin set.
- One continuous full-depth slot admits the plastic pin-header base and all
  wire-wrap tails.
- A slit-and-lip clamp replaces a matching patch of the base plate and retains
  the row without a TPU cover.
- The header body, upper contacts, and wire-wrap tails are non-production
  reference geometry.

Header width, slot clearance, base thickness, slit, lip, and clamp dimensions
come from assembly parameters. The pinout contains none of those values.

### `none`

The component contributes its physical footprint and relevant contact holes,
but the generator creates no holder or holder screw holes. This is appropriate
for components retained by soldering, another assembly, or a not-yet-designed
mechanism.

Unknown downholder kinds fail validation. Future semantic kinds can be added
when a real component requires them, without adding manufacturing dimensions to
the pinout.

## Plate and pin-tail geometry

The base plate is derived in this order:

1. load pin sets, boxes, and `physical_components` through `mege-circuits`;
2. convert their shared raster coordinates using the assembly's raster pitch;
3. resolve each component body from its pin envelope plus assembly profile, or
   from its referenced box;
4. generate downholders and screw centres from the selected semantic variant
   plus assembly parameters;
5. calculate the union envelope of component bodies, downholder eyes, and
   box-backed reference footprints;
6. expand it by the assembly-supplied plate border;
7. create one filleted plate using assembly-supplied dimensions;
8. for every `through_pin_set`, use its component profile to cut either one
   continuous row slot or individual contact holes;
9. replace the pin-line clamp region with the slit-and-lip holder geometry;
10. cut the other downholder self-threading holes;
11. add separately printed downholders as named followers;
12. add bodies, pin tails, screws, and box frames as named non-production
    reference parts.

Socket and header profiles use one continuous slot for each physical pin row,
matching the base cutters used by the original Pico/TMC holder. The Pico, AR20,
DIP-14, StepStick J1/J2, StepStick DIAG0/DIAG1, and generic pin-line rows all
use this form. Slots must be collinear and regularly spaced at one raster
pitch. The current assembly has no discrete fuse contacts or individual fuse
holes. `individual_holes` remains available for a future genuinely discrete
through component. Both styles are dimensioned only by assembly parameters.

The generator also exposes a non-production underside keepout for wire-wrap
tails, with depth supplied by the assembly. Housing generators can consume it
to guarantee tool and wire clearance.

## Box and driver reference behavior

For the TMC5160T Plus, the generator creates a thin rectangular rail at the
plate top using the existing box's exact X/Y footprint. Only the rail's
print-independent preview width and height come from assembly parameters. The
frame is registered as a non-production part such as
`reference_tmc5160t_plus_driver`.

The frame is a placement reference, not a model of the driver. No mounting
holes, capacitors, heatsink, fan header, or other unmeasured features may be
invented. Its contained terminal pin set remains available as circuit context
without creating plate pass-through holes.

The driver box contributes to the plate envelope. Retention of the real driver
remains `none` until its actual mounting interfaces are measured and a semantic
retention type is chosen.

## Output boundary

The implementation belongs in a narrow module such as:

`src/mege_ender_3v3ke_idex/designs/assemblies/pinout_base_plate_assembly.py`

It exports:

- `base_plate` as the leader;
- `downholder_<component-id>` or separately named pieces as production
  followers;
- pin pass-through and self-threading-hole cutters;
- component body previews, pin tails, screws, and box frames as non-production
  parts.

The generator uses `from shellforgepy.simple import *` for geometry and the
public `mege-circuits` pinout loader for schema resolution. It does not parse
rendered SVG, and electrical wire paths and colours do not affect the CAD
geometry.

The build is reproducible from the pinout YAML **plus the explicit assembly
parameters**. It is intentionally not reproducible from the pinout alone,
because construction dimensions do not belong to circuit data.

## Validation and failure behavior

### Pinout validation

`mege-circuits` should reject:

- duplicate physical-component IDs;
- unknown or reused pin-set references;
- unknown box references;
- a `through_pin_sets` entry absent from that component's `pin_sets`;
- duplicate ownership of one pin set;
- unknown downholder kinds;
- a component with neither pin sets nor a box;
- malformed or non-positive existing box dimensions.

It should not validate printable thicknesses or screws because it never loads
those values.

### Assembly validation

The ShellForgePy generator should reject:

- an unknown `component_type` with no supplied mechanical profile;
- missing, non-positive, or inconsistent assembly dimensions;
- multiple resolved through contacts at one coordinate;
- an ambiguous footprint orientation not resolved by its mechanical profile;
- a pin pass-through or self-threading hole outside the plate;
- a downholder or screw eye colliding with another component or keepout;
- merged screw holes or insufficient configured wall thickness;
- inadequate configured screw reach or thread engagement;
- a production part intersecting a component keepout.

Diagnostics should name the physical component and report raster and
millimetre coordinates. Exceptions should propagate; the generator must not
emit partial geometry.

## Test strategy

Tests protect structure, ownership, and derived relationships, not tunable YAML
coordinates or mechanical parameter values.

Useful tests include:

- parser fixtures for component grouping, semantic type, downholder kind,
  through-contact roles, and box references;
- translating every input pin and box by an arbitrary raster vector translates
  the complete assembly by the corresponding millimetre vector without
  changing its dimensions;
- pass-through centres equal the selected through-contact centres after the
  assembly-supplied raster transform;
- box-frame dimensions equal `size_pitches * raster_pitch_mm`;
- changing plate thickness, screw size, or downholder thickness changes the
  CAD result without changing or rewriting the pinout model;
- corner holders have the required topology and avoid the Pico USB edge;
- the plate extends beyond the Pico USB edge and the derived cable passage cuts
  completely through the plate beneath the raised bridge and out to the edge;
- center-strip holders have two end eyes and align to the derived long axis;
- perimeter-frame holders have two long-side rails, two one-pitch-offset end
  crossbars, and two short-edge eyes;
- every screw centre is shared by a downholder clearance hole and a base-plate
  self-threading cutter;
- production solids satisfy the supplied clearances and plate wall thickness;
- reference frames and screw/component previews are excluded from production;
- generation is deterministic.

Tests must not assert the current Pico, socket, driver, endstop, or adapter X/Y
coordinates, current colours, plate width, screw size, or other configurable
values. Integration tests may load the real TMC5160T pinout and assembly
parameters and assert only that the combined configuration validates and
generates consistently.

## Implementation phases

### Phase 1: neutral physical-topology model

Status: implemented in `mege-circuits`.

- Add `physical_components` dataclasses and validation to `mege-circuits`.
- Export the neutral model through its public API.
- Document pin-set ownership, through-contact roles, box references, semantic
  downholder kinds, and the no-second-origin rule.
- Add parser and reference-validation tests using isolated fixtures.

### Phase 2: assembly parameter boundary and base plate

Status: implemented. The current TMC5160T review pinout supplies the physical
component grouping, continuous socket/header row slots, and retained 18-pin
external I/O line. Both serviceable fuse terminals are contacts on that line;
there is no separate fuse-hole geometry. Measured profile refinement remains
Phase 4.

- Add the required mechanical values to `idex_parameters.yaml` or an imported
  mechanical-parameter file.
- Add an assembly resource which passes them explicitly to the generator.
- Implement raster-to-CAD conversion, component-profile resolution, fitted
  plate generation, continuous row slots, and discrete-contact pass-throughs.
- Extend the plate beyond the Pico USB edge and derive the open cable bridge
  from the Pico rows plus assembly-owned USB dimensions.
- Generate non-production body previews and exact box frames.
- Reuse the original SIL slit-and-lip construction for `pin_line_clamp`.

### Phase 3: downholders

Status: implemented for the current carrier.

- The Pico uses one rigid grid follower: two rails over its 20-pin rows, three
  raster-width bridges counted from the bottom pin row, and four outward,
  full-face-joined filleted eyes.
- Each AR20 and DIP socket uses one central strip follower with a rounded eye
  beyond each short end.
- The StepStick adapter uses one closed-frame follower with two long-side rails,
  crossbars one pitch beyond the end pins, and one eye at each short edge.
- Every eye receives a loose M2.5 hole and shares its centre with a lead-in
  self-threading hole in the base plate; screws are preview-only parts.
- All seven rigid downholders export as separately printable named followers.
  `pin_line_clamp` remains integrated with the plate and `none` adds no holder.

### Phase 4: measurements and first assembly

- Add only the physical-component grouping, semantic component types,
  downholder choices, and required box references to the TMC5160T pinout YAML.
- Measure the RP2040-Plus, AR20 and DIP sockets, StepStick adapter, and 18-pin
  SIL row.
- Put those body, holder, plate, and fastener measurements into the IDEX
  assembly parameters, not the pinout.
- Render and inspect component-side and underside CAD previews.
- Print small fit coupons for the self-threading holes, AR20 strip, and Pico
  corner contact before printing the full plate.
- Only then integrate the generated base plate into a housing assembly.

## Acceptance criteria

- Editing a pin-set origin or box position changes all diagrams and CAD output
  from the same coordinate source.
- The pinout contains no plate thickness, screw dimension, holder thickness,
  printable clearance, clamp height, or other manufacturing parameter.
- The pinout explicitly groups the pin sets belonging to each real component
  and selects its semantic downholder kind.
- The assembly instantiation supplies every manufacturing and fastener value.
- The generated plate encloses all configured component footprints,
  downholder eyes, and the exact TMC5160T Plus reference box.
- Wire-wrap tails pass through the plate and remain accessible from below.
- Every configured socket/header pin set forms one full-depth continuous slot;
  there is no separate fuse component or fuse-hole geometry.
- The 18-pin external row is retained by the integrated slit-and-lip clamp,
  exposes separate serviceable-fuse input/output contacts, and keeps its empty
  isolation and spare contacts electrically unused.
- The Pico uses the `corner` variant, while the plate continues past its USB
  edge into a raised bridge; the plate beneath it is removed for the USB-C
  plug and cable and remains unobstructed by the holder.
- Each configured IC/wire-wrap socket uses the `center_strip` variant.
- The StepStick adapter uses the `perimeter_frame` variant with its J1/J2 rails,
  two end crossbars, and two short-edge mount eyes.
- Base holes reuse the vision-light self-threading pattern; no TPU cover is
  generated.
- The driver box appears as an exact-size non-production frame without
  invented driver features.
- Separately printed downholders export independently; the pin-line clamp is
  intentionally integrated into the base plate, and reference geometry remains
  preview-only.
- No test freezes layout coordinates, colours, mechanical parameter values, or
  other intentionally configurable data.
