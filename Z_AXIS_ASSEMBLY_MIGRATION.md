# Z-Axis Assembly Migration Plan

## Status

Implemented:

- the assembly build path no longer imports anything from `src/mege_ender_3v3ke_idex/designs/z_axis.py`
- the profile, rods, bottom support, motor mount, top mount, carriage, and dual-z bridge helper are owned by assembly-era modules
- `src/mege_ender_3v3ke_idex/designs/z_axis.py` has been removed

The remainder of this document is kept as migration history/plan and still describes the intended decomposition, even where some items are now already completed.

## Goal

Refactor the Z-axis so that:

- `src/mege_ender_3v3ke_idex/designs/z_axis.py` can be deleted entirely.
- the Z-axis is composed from small assembly generators with clear responsibilities.
- left/right duplication happens in `assembling/assemblies/assemblies.yaml`, not in Python loops.
- placement is driven by already-placed dependency assemblies, not by wrapping a legacy monolith and translating it afterward.
- the current downstream interface needed by the printer scene can be preserved during migration, especially:
  - carriage followers
  - `carriages_fused`
  - `x_axis_alignment_reference`
  - the top bridge profile

## Current Inventory

### What the current files do

- `src/mege_ender_3v3ke_idex/designs/z_axis.py`
  - still owns almost all real Z-axis geometry.
  - contains both reusable low-level geometry helpers and high-level scene assembly logic.
  - still contains the legacy positioned dual-Z builder.
- `src/mege_ender_3v3ke_idex/designs/assemblies/z_axis_profile_assembly.py`
  - thin wrapper around `create_z_axis_profile()` from legacy `z_axis.py`.
- `src/mege_ender_3v3ke_idex/designs/assemblies/z_axis_side_assembly.py`
  - still calls `create_z_axis_from_profile()` and `create_carriage()` from legacy `z_axis.py`.
  - still translates the assembled mechanical stack in Python via `z_axis_base_z_offset`.
- `src/mege_ender_3v3ke_idex/designs/assemblies/z_axis_assembly.py`
  - still calls `create_top_bridge_profile()` from legacy `z_axis.py`.
  - still prefixes and merges left/right side outputs in Python.
- `assembling/assemblies/assemblies.yaml`
  - only splits the Z-axis into `profile`, `side`, and dual-axis wrapper assemblies.
  - left/right duplication already exists at the profile and side level, but the side generators are still monolithic.

### What one Z side really contains today

Each side currently bundles all of the following into one Python generator chain:

1. One `4040` Z profile.
2. One guide rod placed from the profile.
3. One threaded rod placed from the profile and guide rod.
4. One pillow-block bearing body with its hardware visuals.
5. One pillow-bearing mount plate that attaches the pillow block to the profile.
6. One bottom motor mount assembly:
   - motor visual
   - coupler visual
   - motor mount back plate
   - split guide-rod clamp half
7. One lower threaded-rod thrust/support stack:
    - axial bearing stopper
    - axial ball bearing
    - split axial clamp
8. One top guide-rod mount:
   - top mount body
   - split clamp half
9. One moving carriage:
   - carriage body
   - two split clamp halves
   - two drylin bearings
   - Creality nut interface
   - screw hardware
   - x-axis connector tabs

### Current side-level published artifacts

The current side assembly publishes these printable followers:

- `pillow_bearing_mount_plate`
- `axial_bearing_stopper`
- `axial_clamp_part_0`
- `axial_clamp_part_1`
- `mount_plate_clamp_part`
- `mount_plate_back`
- `top_mount`
- `top_mount_clamp`
- `carriage`
- `carriage_clamp_0`
- `carriage_clamp_1`

It also publishes a large non-production surface, including:

- rod references: `guide_rod`, `threaded_rod`
- motor visuals: `body`, `axle`, `coupler`, `connector`
- pillow-block internals and hardware
- axial bearing and clamp screws
- top-mount screws
- carriage bearings, nut, and clamp screws
- `carriage_fused`
- `x_axis_alignment_reference`

### Cross-side behavior that exists today

At the dual-Z level, the current system also does this:

- places one left profile and one right profile from `assemblies.yaml`
- duplicates the side assembly once per side
- creates one top bridge profile spanning both placed Z profiles
- fuses the two carriage references into:
  - `carriages_fused`
  - `x_axis_alignment_reference`

Those last two references are the current contract used by X-axis placement.

## Problems In The Current Split

### The assembly layer is still a wrapper around legacy Python

- `z_axis_profile_assembly.py` imports legacy profile creation from `z_axis.py`.
- `z_axis_side_assembly.py` imports legacy side and carriage creation from `z_axis.py`.
- `z_axis_assembly.py` imports legacy top-bridge creation from `z_axis.py`.

As long as those imports exist, the legacy file is still the real source of truth.

### Responsibility boundaries are too coarse

`z_axis_side_assembly.py` currently owns almost the entire mechanical side stack. That makes it hard to:

- reuse subassemblies cleanly
- reason about placement anchors
- move side-specific duplication into YAML
- test one mechanical group at a time

### There is hidden placement coupling

The current side assembly builds geometry from an injected profile, then translates the whole result by `z_axis_base_z_offset`, while the actual profile assembly is placed separately in the global scene. That means the exported followers are not obviously anchored to the same thing that the final scene exposes as the profile.

This should be replaced by smaller generators that use already-placed dependencies directly and apply only the placement relevant to their own local responsibility.

### Side duplication is still conceptually in Python

The top-level dual assembly still knows about "left" and "right" as special hard-coded branches and prefixes their outputs in Python. The assembly graph should instead declare left/right instances in `assemblies.yaml` and keep the Python generators generic.

## Target Assembly Breakdown

The target is one reusable resource file per mechanical subassembly, then instantiate those resources twice in `assemblies.yaml` where needed.

### Reusable assembly resources

1. `z_axis_profile_assembly`
   - responsibility: one bare `4040` Z profile
   - output: profile leader
   - notes: keeps the per-side extrusion length metric

2. `z_axis_rods_assembly`
   - responsibility: one guide rod plus one threaded rod
   - inputs: `z_axis_profile`
   - parameters: `z_axis_base_z_offset`
   - output:
     - leader: `guide_rod`
     - non-production: `threaded_rod`
   - notes:
     - this is where `z_axis_base_z_offset` should move
     - downstream assemblies should build from rods that are already at the correct vertical stack origin

3. `z_axis_bottom_support_assembly`
   - responsibility:
     - pillow block bearing visual group
     - pillow-bearing mount plate
     - lower threaded-rod thrust/support stack
   - inputs:
     - `z_axis_profile`
     - `z_axis_rods`
   - output:
     - leader: `pillow_bearing_mount_plate`
     - followers:
       - `axial_bearing_stopper`
       - `axial_clamp_part_0`
       - `axial_clamp_part_1`
     - non-production:
       - pillow-block body, cage, filler, base, mount screws
       - `axial_bearing`
       - clamp screw hardware
   - notes:
     - verified stack order in the current code is:
       `pillow_block_bearing -> axial_bearing_stopper -> axial_bearing -> axial_rod_clamp`
     - this is not the top of the rod; it is the lower support/thrust stack above the pillow bearing
     - the stopper belongs with this lower support group because it rests directly on the pillow bearing and is what the axial bearing pushes against

4. `z_axis_motor_mount_assembly`
   - responsibility:
     - motor visual
     - coupler visual
     - lower motor mount back plate
     - split guide-rod clamp plate
   - inputs:
     - `z_axis_profile`
     - `z_axis_rods`
   - parameters:
     - `side`
   - output:
     - leader: `mount_plate_back`
     - followers:
       - `mount_plate_clamp_part`
     - non-production:
       - `body`
       - `axle`
       - `coupler`
       - `connector`
       - guide-rod clamp screw hardware
   - notes:
     - this is the only one-side bottom assembly that actually needs `side`, because the left motor is rotated
     - the main printable motor mount part is the back plate screwed to the profile; the clamp half is the follower

5. `z_axis_guide_rod_top_mount_assembly`
   - responsibility:
     - top guide-rod mount body
     - split top clamp
   - inputs:
     - `z_axis_profile`
     - `z_axis_rods`
   - output:
     - leader: `top_mount`
     - followers:
       - `top_mount_clamp`
     - non-production:
       - top-mount screw hardware

6. `z_axis_carriage_assembly`
   - responsibility: one moving carriage module
   - inputs:
     - `z_axis_rods`
   - parameters:
     - `carriage_z_offset`
   - output:
     - leader: `carriage`
     - followers:
       - `carriage_clamp_0`
       - `carriage_clamp_1`
     - non-production:
       - `top_bearing`
       - `bottom_bearing`
       - `threaded_rod_nut`
       - carriage clamp screw hardware
       - `carriage_fused`
       - `x_axis_alignment_reference`
   - notes:
     - the current `profile` argument should be removed here because the carriage geometry does not use it
     - the main carriage body is the leader; the two printed clamp halves are followers

7. `z_axis_top_bridge_assembly`
   - responsibility: one `2020` top bridge profile spanning left and right Z profiles
   - inputs:
     - `left_z_axis_profile`
     - `right_z_axis_profile`
   - output:
     - non-production: `top_bridge_profile`
   - notes:
     - keeps the bridge extrusion metric recording
     - this must be built once, not synthesized inside a dual-side wrapper
     - this refactor should only extract the existing bridge-profile behavior; do not add top brackets or new mounting features yet

### Composition-only assemblies

8. `z_axis_side_assembly`
   - responsibility: collect one side's already-built subassemblies into one named surface
   - inputs:
     - `z_axis_profile`
     - `z_axis_rods`
     - `z_axis_bottom_support`
     - `z_axis_motor_mount`
     - `z_axis_guide_rod_top_mount`
     - `z_axis_carriage`
   - notes:
     - should not recreate or reposition geometry
     - should be composition-first via YAML builder entries
     - Python, if needed at all, should be a trivial aggregator only

9. `z_axis_assembly`
   - responsibility:
     - collect left and right side assemblies
     - expose cross-side references
   - inputs:
     - `left_z_axis_side_assembly`
     - `right_z_axis_side_assembly`
     - `z_axis_top_bridge_assembly`
   - output:
     - non-production:
       - `carriages_fused`
       - `x_axis_alignment_reference`
       - `top_bridge_profile`
   - notes:
     - may still compute the two fused reference anchors in Python
     - should not own any actual side geometry generation

## Placement Model

### Global placement that stays in `assemblies.yaml`

Only the following needs explicit scene placement:

1. `left_z_axis_profile_assembly` to the printer frame.
2. `right_z_axis_profile_assembly` to the printer frame.
3. `x_axis_assembly` to `z_axis_assembly.non_production_parts.carriages_fused` and `z_axis_assembly.non_production_parts.x_axis_alignment_reference`.

Those profile placement lines already exist and should remain the scene anchors for the full Z system.

### Local placement that moves into smaller generators

Everything else should be expressed relative to injected dependencies:

- `z_axis_rods_assembly` places rods from the already-placed profile.
- `z_axis_bottom_support_assembly` places the pillow-bearing plate and lower thrust stack from the already-placed rods and profile.
- `z_axis_motor_mount_assembly` places motor and mount plates from the already-placed rods and profile.
- `z_axis_guide_rod_top_mount_assembly` places the top mount from the already-placed rods and profile.
- `z_axis_carriage_assembly` places the carriage from the already-placed rods and its own `carriage_z_offset`.
- `z_axis_top_bridge_assembly` computes bridge length and placement from the already-placed left/right profiles.

### Important placement rule

Do not build a large wrapper assembly and translate the wrapper afterward. Each small generator should consume already-placed dependencies and place only the geometry it owns.

That specifically means:

- `z_axis_base_z_offset` belongs in `z_axis_rods_assembly`, not in a side wrapper.
- `carriage_z_offset` belongs in `z_axis_carriage_assembly`, not in a side wrapper.

## `assemblies.yaml` Instance Matrix

The reusable assembly resources above should be instantiated explicitly in `assembling/assemblies/assemblies.yaml`.

### Left/right instances that must exist as separate YAML entries

- `left_z_axis_profile_assembly`
- `right_z_axis_profile_assembly`
- `left_z_axis_rods_assembly`
- `right_z_axis_rods_assembly`
- `left_z_axis_bottom_support_assembly`
- `right_z_axis_bottom_support_assembly`
- `left_z_axis_motor_mount_assembly`
- `right_z_axis_motor_mount_assembly`
- `left_z_axis_guide_rod_top_mount_assembly`
- `right_z_axis_guide_rod_top_mount_assembly`
- `left_z_axis_carriage_assembly`
- `right_z_axis_carriage_assembly`
- `left_z_axis_side_assembly`
- `right_z_axis_side_assembly`

### Single shared instances

- `z_axis_top_bridge_assembly`
- `z_axis_assembly`

### Required rule

Do not recreate left/right duplication inside Python like:

- `for side in [Alignment.LEFT, Alignment.RIGHT]: ...`
- hard-coded left/right generation inside `create_z_axis_assembly()`
- hidden side duplication inside a legacy helper

Instead:

- define one generic resource file
- instantiate it twice in `assemblies.yaml`
- pass `side: left` or `side: right` only where the geometry truly differs

## Files To Create And Update

### New Python modules

- `src/mege_ender_3v3ke_idex/designs/assemblies/z_axis_rods_assembly.py`
- `src/mege_ender_3v3ke_idex/designs/assemblies/z_axis_bottom_support_assembly.py`
- `src/mege_ender_3v3ke_idex/designs/assemblies/z_axis_motor_mount_assembly.py`
- `src/mege_ender_3v3ke_idex/designs/assemblies/z_axis_guide_rod_top_mount_assembly.py`
- `src/mege_ender_3v3ke_idex/designs/assemblies/z_axis_carriage_assembly.py`
- `src/mege_ender_3v3ke_idex/designs/assemblies/z_axis_top_bridge_assembly.py`
- `src/mege_ender_3v3ke_idex/designs/assemblies/z_axis_components.py`

### Existing Python modules to rewrite

- `src/mege_ender_3v3ke_idex/designs/assemblies/z_axis_profile_assembly.py`
  - remove import from legacy `z_axis.py`
- `src/mege_ender_3v3ke_idex/designs/assemblies/z_axis_side_assembly.py`
  - convert into a thin composition/aggregation layer
- `src/mege_ender_3v3ke_idex/designs/assemblies/z_axis_assembly.py`
  - reduce to cross-side aggregation only

### New assembly resource YAML files

- `assembling/assemblies/z_axis_rods_assembly.yaml`
- `assembling/assemblies/z_axis_bottom_support_assembly.yaml`
- `assembling/assemblies/z_axis_motor_mount_assembly.yaml`
- `assembling/assemblies/z_axis_guide_rod_top_mount_assembly.yaml`
- `assembling/assemblies/z_axis_carriage_assembly.yaml`
- `assembling/assemblies/z_axis_top_bridge_assembly.yaml`

### Existing assembly resource YAML files to update

- `assembling/assemblies/z_axis_profile_assembly.yaml`
- `assembling/assemblies/z_axis_side_assembly.yaml`
- `assembling/assemblies/z_axis_assembly.yaml`
- `assembling/assemblies/assemblies.yaml`
- `assembling/assemblies/whole_printer_assembly.yaml`

### File to delete at the end

- `src/mege_ender_3v3ke_idex/designs/z_axis.py`

## Suggested Migration Sequence

1. Create `z_axis_components.py` and move over the low-level reusable geometry helpers:
   - profile mount plate
   - pillow-block helper geometry
   - drylin bearing helper
   - axial bearing helper
   - threaded-rod nut helper
   - other non-scene-specific part builders
2. Rewrite `z_axis_profile_assembly.py` so it no longer imports legacy `z_axis.py`.
3. Add `z_axis_rods_assembly`.
4. Add `z_axis_bottom_support_assembly` and `z_axis_motor_mount_assembly`.
5. Add `z_axis_guide_rod_top_mount_assembly`.
6. Add `z_axis_carriage_assembly`.
7. Add `z_axis_top_bridge_assembly`.
8. Rewrite `assemblies.yaml` so all left/right side instances are explicit YAML entries.
9. Reduce `z_axis_side_assembly` to composition only.
10. Reduce `z_axis_assembly` to cross-side aggregation only.
11. Update `whole_printer_assembly.yaml` to consume the new surface, while preserving current external names where practical.
12. Delete `designs/z_axis.py` once no assembly imports remain.

## Definition Of Done

The migration is complete when all of the following are true:

- no assembly generator imports anything from `src/mege_ender_3v3ke_idex/designs/z_axis.py`
- left/right Z duplication is declared only in `assembling/assemblies/assemblies.yaml`
- `z_axis_side_assembly.py` no longer builds the full mechanical side stack
- `z_axis_assembly.py` no longer builds the top bridge or prefixes side internals from a legacy monolith
- `z_axis_assembly.non_production_parts.carriages_fused` still exists
- `z_axis_assembly.non_production_parts.x_axis_alignment_reference` still exists
- the whole-printer scene still has the left/right carriage followers and top bridge profile available
- `src/mege_ender_3v3ke_idex/designs/z_axis.py` is removed
