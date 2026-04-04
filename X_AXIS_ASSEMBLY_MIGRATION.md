# X-Axis Assembly Migration Plan

## Status

Not implemented yet.

This document defines the intended migration of the IDEX X-axis core into a cleaner assembly-era structure before code changes are made.

## Goal

Refactor the X-axis and the two toolhead lanes so that:

- the X-axis is composed from small reusable assembly generators with clear responsibilities
- bottom/top or left/right duplication happens in `assembling/assemblies/assemblies.yaml`, not in Python loops
- multiple instances of the same mechanical thing share one Python generator and one resource YAML, and are instantiated twice in `assemblies.yaml`
- placement is expressed primarily through assembly dependencies and placement commands in YAML
- downstream assemblies do not copy leaders of dependency assemblies into their own non-production parts just to keep them around
- visualization should show the actual placed assemblies, not synthetic copies dragged through a larger aggregate

## Scope

This migration is about the structural core of the X-axis and IDEX toolhead stack:

- the X-axis frame itself
- rail and carriage references
- endcaps and belt path structure
- per-lane toolhead mounts
- per-lane toolhead payloads

This migration should not:

- redesign the printable geometry unless necessary to expose cleaner assembly boundaries
- change the printer-level external behavior beyond what is needed to improve the assembly graph
- fold in unrelated toolhead or fan redesigns

## Current Inventory

### What exists today

- `src/mege_ender_3v3ke_idex/designs/assemblies/x_axis_assembly.py`
  - still owns most of the X-axis structure as one large generator
  - creates the lower profile, top profile, rail, carriage references, endcaps, and endstop-related details in one place
  - still contains bottom/top duplication inside Python
- `src/mege_ender_3v3ke_idex/designs/assemblies/tool_head_mount_assembly.py`
  - already has a promising generic core
  - one shared generator is instantiated twice as `tool_head_mount_bottom_assembly` and `tool_head_mount_top_assembly`
  - still performs substantial internal placement in Python
- `src/mege_ender_3v3ke_idex/designs/assemblies/tool_head_assembly.py`
  - already composes sprite extruder, nitehawk holder, and part fans from dependency assemblies
  - but still merges payload assemblies into a larger aggregate leader and republishes fused references
- `src/mege_ender_3v3ke_idex/designs/assemblies/y_axis_endstop_holder_assembly.py`
  - already contains an assembly-era endstop board + holder implementation
  - this is relevant because the X-axis still constructs its endstop holder from the plain generator path
- `assembling/assemblies/x_axis_assembly.yaml`
  - currently exposes the monolithic `x_axis_assembly`
  - visualization rules also directly pull in both toolhead-mount assemblies and animate them from there

### What the current X-axis really contains

The current effective X-axis stack spans several responsibilities at once:

1. Lower `2020` profile
2. Upper `2020` profile
3. Linear rail
4. Two carriage references
5. Left/right endcaps for both belt levels
6. Endstop holder / groove-holder details
7. Toolhead-mount placement references
8. The two mounted toolhead lanes
9. Toolhead payload visualization through separate dependency wiring

That is already more than one assembly should own.

## Current Structural Problems

### `x_axis_assembly` is still too monolithic

The current X-axis assembly owns several different mechanical groups at once:

- beam structure
- rail/carriage structure
- endcaps
- local endstop support details
- references consumed by toolhead mounts

That makes it hard to:

- place or animate subassemblies independently
- reuse parts of the X-axis cleanly
- redesign only one side of the structure
- reason about what is a real assembly boundary versus an internal helper

### Some duplication still lives in Python

Although the toolhead mounts already share one generator, the broader X-axis still relies on Python branching for repeated structure:

- top/bottom drive-path behavior
- left/right endcap variants
- bundled carriage/reference creation inside the X-axis aggregate

Where possible, these should be expressed as reusable assemblies instantiated multiple times in `assemblies.yaml`.

### The X-axis still embeds a legacy endstop-holder path

The current X-axis code still builds the endstop-holder path inline inside `x_axis_assembly.py`:

- it creates the rail-stopper helper geometry
- it calls legacy `create_endstop_holder()`
- it rotates that holder in Python by side
- it aligns and translates it in Python

This is a strong candidate for migration because:

- it is structurally separate from the beam/endcap core
- it is already orientation-sensitive
- it is exactly the kind of repeated, placement-heavy logic that should move into assembly instances plus YAML placement

There is also already an assembly-era precedent in the tree:

- `y_axis_endstop_holder_assembly.py` contains an endstop board + holder assembly implementation

So the X-axis migration should explicitly evaluate reusing or generalizing that assembly-era implementation instead of continuing to keep a plain endstop-holder generator embedded in the monolith.

### The builder now supports rotation in YAML placement

The builder now supports `post_rotation` in placement steps.

The supported shape is:

- `post_rotation.angle`
- optional `post_rotation.axis`
- optional `post_rotation.center`

The center can be:

- a literal 3-vector
- or a `"<reference>.CENTER"` anchor string

This matters directly for the X-axis endstop-holder migration, because it means we no longer need Python-only placement just to rotate a reused assembly into a different orientation.

### Visualization currently crosses assembly boundaries

`x_axis_assembly.yaml` directly visualizes:

- self artifacts from `x_axis_assembly`
- dependency artifacts from `tool_head_mount_bottom_assembly`
- dependency artifacts from `tool_head_mount_top_assembly`

That means the scene contract is spread across multiple sibling assemblies instead of being cleanly staged through explicit parent-level composition.

This works, but it makes the graph harder to reason about and easier to regress.

### There is still leader-copy style aggregation

The current toolhead and X-axis path still use patterns where a larger assembly republishes dependency geometry as its own non-production parts to preserve references or visualization convenience.

That is exactly the pattern we should avoid going forward:

- if a downstream consumer needs a fused reference, it should fuse the specific dependency artifacts itself
- if the viewer should show an assembly, the viewer should reference that real assembly directly
- dependency leaders should not be copied into downstream non-production parts unless there is a very strong reason

## Target Design Principles

### 1. One mechanical responsibility per reusable assembly

Examples:

- one beam assembly
- one rail assembly
- one carriage-reference assembly
- one endcap assembly
- one toolhead mount assembly
- one toolhead payload assembly

### 2. Shared resource files for repeated instances

Repeated structures should use:

- one Python generator
- one resource YAML
- two instantiations in `assemblies.yaml`

Examples:

- bottom and top toolhead mounts
- left and right endcaps
- possibly left and right carriage/endstop subassemblies if that split is chosen

### 3. Placement in YAML over Python where feasible

Prefer this pattern:

- assembly A exposes a clean leader and/or named references
- assembly B injects A
- `assemblies.yaml` places A and B relative to already-placed parts

Avoid this pattern:

- generator B creates or translates surrogate geometry internally just to simulate final scene placement

### 4. No duplicated dependency leaders

If an assembly is already first-class in the graph:

- do not copy its leader into another assembly just to keep it around
- do not republish it as a downstream non-production part unless absolutely required
- keep real assemblies visible as real assemblies in the scene

## Proposed Target Breakdown

The exact final partition may change during implementation, but the intended decomposition should look roughly like this.

### Reusable assembly resources

1. `x_axis_profile_assembly`
   - responsibility: one `2020` X-beam profile
   - parameters:
     - profile role, likely `lower` or `upper`
     - profile length
   - output:
     - leader: one profile only

2. `x_axis_rail_assembly`
   - responsibility: one rail with its carriage references
   - inputs:
     - lower profile
   - output:
     - leader: rail
     - non-production parts: carriage references

3. `x_axis_endcap_assembly`
   - responsibility: one endcap unit
   - one generic resource instantiated multiple times
   - parameters:
     - side: left/right
     - drive position: bottom/top
     - with/without tensioner
   - notes:
     - this is a good candidate for the “one resource, multiple instances” rule

4. `x_axis_endstop_support_assembly`
   - responsibility: groove-holder / rail-stopper / endstop-support details
   - should not be hidden inside the large X-axis beam assembly if it can be made independent
   - should evaluate reuse of the existing assembly-era endstop-holder implementation
   - preferred direction:
     - either generalize `y_axis_endstop_holder_assembly.py`
     - or extract a shared endstop-holder assembly resource used by both X and Y

5. `tool_head_mount_assembly`
   - keep one generic resource
   - instantiate it twice in `assemblies.yaml`
   - inputs should be explicit X-axis references rather than implicit internal placement assumptions

6. `tool_head_payload_assembly`
   - keep one generic resource for sprite extruder + nitehawk holder + part fans
   - instantiate it twice if needed, or keep the current bottom/top payload split if that reflects real geometry differences

7. `x_axis_core_assembly`
   - responsibility: aggregate only the actual X-axis structural pieces
   - should not absorb toolhead payloads as copied geometry
   - may expose:
     - `carriage_1`
     - `carriage_2`
     - beam references
     - belt-path / alignment references

## Intended Graph Shape

The new graph should separate the structural X-axis from the two moving toolhead lanes.

One likely target order is:

1. `x_axis_lower_profile_assembly`
2. `x_axis_upper_profile_assembly`
3. `x_axis_rail_assembly`
4. `x_axis_endcap_*_assembly` instances
5. `x_axis_endstop_support_*_assembly` instances as needed
6. `x_axis_core_assembly`
7. `tool_head_payload_bottom_assembly`
8. `tool_head_payload_top_assembly`
9. `tool_head_mount_bottom_assembly`
10. `tool_head_mount_top_assembly`

The important structural consequence is:

- the X-axis core should exist independently of the mounted toolhead payloads
- the two toolhead lanes should be attached through explicit carriage references rather than by being visually baked into the X-axis aggregate

## Placement Strategy

### Structural X-axis placement

The X-axis core should continue to take its global placement from the Z-axis carriage contract:

- `z_axis_assembly.non_production_parts.carriages_fused`
- `z_axis_assembly.non_production_parts.x_axis_alignment_reference`

But internally, the X-axis should prefer explicit placed subassemblies over Python-side translation chains.

### Toolhead-mount placement

The two toolhead mount instances should be positioned from:

- the actual carriage references exposed by the rail or X-axis core assembly
- explicit placement steps in YAML where practical

This is already partly true conceptually, but the migration should tighten that contract and reduce internal hidden positioning.

### Toolhead payload placement

The toolhead payload assemblies should remain separate from the mount assemblies in the graph.

The preferred contract is:

- payload assembly builds the payload only
- mount assembly builds the printable mounting hardware only
- printer-level visualization references both real assemblies
- if one assembly needs a reference from the other, inject it explicitly rather than fusing them into one visualization artifact

### Endstop-holder placement

The X-axis migration should treat endstop-holder orientation and placement as a YAML problem where possible.

Preferred direction:

- instantiate a reusable endstop-holder assembly
- place it relative to rail-stopper or endcap references in YAML
- use `post_rotation` in YAML when the canonical local orientation does not match the X-axis scene orientation
- keep only truly local connector geometry inside the X-axis structural assembly

## Specific Anti-Patterns To Remove

### 1. Toolhead visualization routed through `x_axis_assembly.yaml`

Today the X-axis resource YAML directly includes the two mounted toolhead assemblies in its visualization rules.

Target:

- `x_axis_assembly.yaml` should visualize X-axis artifacts only
- whole-printer visualization should reference the real toolhead-mount and toolhead-payload assemblies directly

### 2. Dependency leader copies in downstream assemblies

If a downstream assembly currently keeps a dependency alive by copying its leader into non-production parts, replace that with:

- direct scene reference to the source assembly
- or local fused references built only where truly needed

### 3. Python-side repeated branching for identical resources

If left/right or bottom/top instances share the same logic:

- keep one Python generator
- keep one resource YAML
- instantiate twice in `assemblies.yaml`

### 4. Inline endstop-holder construction inside `x_axis_assembly.py`

The current X-axis path:

- `create_endstop_holder()`
- `rotate(...)`
- `align(...)`
- `translate(...)`

should be replaced by:

- a first-class endstop-holder assembly dependency
- YAML-driven orientation and placement
- local connector geometry only where still genuinely needed

## Migration Stages

### Stage 1: Inventory and contracts

- document the current X-axis exported interface
- identify which artifacts are truly structural and which are only visualization conveniences
- identify which references the toolhead mounts actually require

### Stage 2: Split the structural X-axis core

- peel out reusable structural subassemblies from the current monolithic `x_axis_assembly.py`
- keep the public X-axis contract stable where possible
- include the endstop-holder path in that split rather than leaving it embedded in the monolith

### Stage 3: Normalize repeated instances

- convert repeated left/right or top/bottom structures into shared reusable resources
- instantiate them explicitly in `assemblies.yaml`
- specifically test whether the X-axis can reuse an assembly-era endstop-holder resource via YAML `post_rotation`

### Stage 4: Remove cross-assembly visualization coupling

- stop using `x_axis_assembly.yaml` as a scene-level collector for toolhead assemblies
- reference the real mount/payload assemblies directly in the whole-printer scene

### Stage 5: Remove leader-copy patterns

- audit downstream non-production parts
- eliminate copied dependency leaders
- keep only true local references or true local fused helper geometry

## Acceptance Criteria

The migration should be considered complete when:

- the X-axis structural core is no longer one monolithic ownership boundary
- repeated X-axis resources are instantiated in `assemblies.yaml` rather than duplicated in Python
- the two toolhead lanes are separate first-class assemblies attached by explicit references
- whole-printer visualization uses the real placed assemblies instead of copied leader geometry
- the X-axis no longer constructs endstop holders inline from the plain generator path
- endstop-holder orientation can be expressed in YAML placement, including rotation where needed
- the assembly graph is easier to evolve for later IDEX redesign work

## Notes For The Eventual Implementation

- preserve external names that downstream placement currently relies on unless there is a compelling reason to rename them
- do not combine this migration with a large mechanical redesign of the printable X-axis parts
- prefer incremental graph cleanup over a full rewrite in one step
- if a temporary compatibility layer is needed, keep it shallow and explicitly documented
