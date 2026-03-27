# Global Assembly Placement Concept

Goal: the declarative assembly system defines assemblies in stable local coordinates, and the global placement script from `assemblies.yaml` executes eagerly in lockstep with assembly creation.

## Core model

The placement script lives once, centrally, in the global `assemblies.yaml`, because relative placement is a scene-level concern.

The build pipeline is:

1. Build selected assemblies geometrically in dependency order, each in its own canonical local coordinates.
2. Cache those canonical assembly artifacts using the geometry cache inputs: generator code hash, assembly resource YAML hash, public parameters, and injected dependency hashes.
3. As soon as an assembly finishes building, insert it into one shared global placement scene.
4. Keep a pointer into the ordered placement script from `assemblies.yaml`.
5. After each assembly build completion, repeatedly execute the next placement step if all assemblies referenced by that step are already present in the scene.
6. Stop as soon as the next placement step references an assembly that is not yet built.
7. Resume from that exact placement step after the next assembly build completes.
8. Build downstream assemblies against the currently placed scene state, not against a still-unplaced final batch.
9. After the build is complete, visualization, scene export, and scene-style production output operate on the already placed result.

## Abstraction

The abstraction for this codebase is:
- `align(...)`
- ordered sequences of alignments
- selectors that refer to `leader`, `followers`, `cutters`, and `non_production_parts`
- the same mental model as `aligned_from_follower(...)` and `aligned_from_non_production_part(...)`

The system does not use:
- points
- planes
- mates
- axes as first-class feature objects
- local per-assembly placement scripts
- extra indirection layers such as `instances` unless they become necessary later

The placement layer is intentionally small, global, and incrementally applied.

## Problem

The builder already solves the local geometry problem well:
- build one assembly
- cache it
- inject parts from it into downstream assemblies

That is sufficient for pure local geometry generation.
It is not sufficient for geometry that depends on the already resolved relative placement of multiple upstream assemblies.

The reason is that placement is not owned by one assembly.
It is a scene-level concern across already-built assemblies, and some later assemblies must be built against that already placed scene state.

Example:
- the bed may need to be positioned relative to the frame first
- the undercarriage may then need to be positioned relative to the bed
- the y-axis may then need to be positioned relative to the placed bed and undercarriage result
- the x-axis may then need to be positioned relative to the placed frame and other already-placed assemblies

That is not a geometry dependency cycle.
It is one global ordered placement script whose already-satisfied prefix is applied as early as possible.

Additional example:
- profile A is built
- profile B is built
- the placement step aligning A relative to B now becomes executable and runs immediately
- a corner bracket assembly that depends on both A and B can then be built against their already resolved relative pose

The corner bracket assembly relies on the true scene relationship between A and B rather than their canonical local coordinates.

## What ShellForgePy already provides

### `align(...)` is already the placement language

In [shellforgepy/src/shellforgepy/construct/alignment_operations.py](/Users/mege/git/shellforgepy/src/shellforgepy/construct/alignment_operations.py), `align_translation(...)` and `align(...)` already provide the placement language this codebase uses successfully:
- `LEFT`
- `RIGHT`
- `FRONT`
- `BACK`
- `TOP`
- `BOTTOM`
- `CENTER`
- `STACK_*`
- `EDGE_*`
- optional `stack_gap`

Complex placement is already normally expressed as:
- center this to that
- then put it on top of that
- then move it to the back of that

That is the declarative language here as well.

### Assemblies already expose the right anchors

In [shellforgepy/src/shellforgepy/construct/leader_followers_cutters_part.py](/Users/mege/git/shellforgepy/src/shellforgepy/construct/leader_followers_cutters_part.py), assemblies already expose:
- `leader`
- `followers`
- `cutters`
- `non_production_parts`

and those can already be named.

That is enough to define placement anchors.

### Existing alignment-from-subpart patterns already match this need

The important existing pattern is:
- align an assembly not from its `leader`
- but from one of its named `followers` or `non_production_parts`

The global placement YAML mirrors that pattern directly.
It does not introduce a second placement language.

## Architecture

The system has two layers.

1. Geometry layer
- defined by assembly resource YAML files such as `printer_frame_assembly.yaml`, `x_axis_assembly.yaml`, and similar
- builds canonical geometry in stable local coordinates
- remains acyclic
- remains cached exactly as now

2. Global placement layer
- defined only once in `assemblies.yaml`
- works on already-built assemblies inside one shared scene state
- applies one ordered script of alignments across the whole scene
- advances eagerly whenever the next placement step has all required assemblies available
- exposes the currently placed scene state to later assembly builds
- produces the final placed composition for visualization and output

Important:
- canonical assembly artifacts stay untouched
- placement is a derived scene layer on top of them
- the placed scene layer is updated incrementally during the build, not only after the build
- assembly resource files do not define final relative scene placement

## Placement in `assemblies.yaml`

The placement section is top-level in the global assembly orchestration file.

Shape:

```yaml
globals:
  print_bed_vertical_gap_to_frame: 60

assemblies:
  - name: printer_frame_assembly
  - name: print_bed_assembly
  - name: print_bed_undercarriage_assembly
  - name: y_axis_assembly
  - name: x_axis_assembly

placement:
  alignments:
    - part: print_bed_assembly
      to: printer_frame_assembly
      alignment: CENTER
      axes: [0]

    - part: print_bed_assembly
      to: printer_frame_assembly
      alignment: STACK_TOP
      stack_gap: { $ref: print_bed_vertical_gap_to_frame }

    - part: print_bed_assembly.non_production_parts.print_bed_foil
      to: printer_frame_assembly
      alignment: TOP
      post_translation: [0, 0, { $ref: print_bed_vertical_gap_to_frame }]

    - part: print_bed_undercarriage_assembly
      to: print_bed_assembly
      alignment: CENTER
      axes: [0, 1]

    - part: y_axis_assembly.followers.carriage_front_carriage_left
      to: print_bed_assembly
      alignment: TOP

    - part: x_axis_assembly
      to: printer_frame_assembly
      alignment: CENTER
      axes: [0, 1]
```

This structure is intentionally minimal:
- one global `placement` block
- one `alignments` list
- one ordered placement script for the whole scene
- one implicit placement cursor that advances through the sequence as builds finish
- no per-assembly placement blocks
- no explicit placement graph model
- no `instances`
- no generic `operations` framework

Execution properties:
- the script is globally declared
- the script executes incrementally rather than in one terminal batch

## Why local placement blocks do not fit

If placement is attached to one assembly resource file, several things become unclear or incorrect:

1. It implies placement is owned by that assembly.
It is not. Final placement is scene-level.

2. It suggests placement order is fragmented by assembly ownership.
The user reads and edits one global ordered script.

3. It fragments ordering.
The user actually needs one long ordered script, not many local scripts whose interaction rules are hard to reason about.

4. It makes review harder.
Users want to inspect and edit one placement script for the whole printer, not hunt through assembly resource files.

The design optimizes for one global script that reads top to bottom.

## Eager execution model

The placement script is global, and its execution is incremental.

The builder maintains:
- a shared placed-scene state containing all assemblies built so far
- a placement cursor pointing at the next not-yet-executed alignment entry
- canonical cached assembly artifacts, unchanged from today

After each assembly finishes building:

1. Insert the newly built assembly into the shared scene state at its current canonical pose.
2. Look at the next alignment entry referenced by the placement cursor.
3. Resolve which assemblies are required by that entry:
  - the owning assembly named by `part`
  - the assembly named by `to`
4. If any required assembly is still missing from the scene, stop immediately.
5. If all required assemblies are present, execute the alignment.
6. Advance the placement cursor by one.
7. Repeat from step 2 until the next placement entry cannot yet run.

Placement progresses in lockstep with assembly availability.
At any moment, the applied state is the maximal executable prefix of the global placement script.

## Why eager execution exists

Some assemblies depend not just on upstream geometry, but on upstream geometry after a certain prefix of the placement script has already been applied.

Example:
- `profile_a_assembly` is built
- `profile_b_assembly` is built
- placement step 0 aligns `profile_b_assembly` to `profile_a_assembly`
- `corner_bracket_assembly` depends on both profiles and is built afterwards

The bracket generator inspects or injects the already placed profiles as they relate in the scene:
- centered
- stacked
- top-aligned
- offset by a declared gap

The first placement step runs as soon as both profiles exist, so the bracket builds against the correct placed state.

## Selector rules

The placement system reuses the selector style already used elsewhere in the builder.

Selector syntax:
- `assembly_name`
- `assembly_name.leader`
- `assembly_name.followers.<name>`
- `assembly_name.cutters.<name>`
- `assembly_name.non_production_parts.<name>`
- `assembly_name.fused`

If only `assembly_name` is given, it means `assembly_name.leader`.

Examples:
- `printer_frame_assembly`
- `y_axis_assembly.followers.carriage_front_carriage_left`
- `print_bed_assembly.non_production_parts.damper_left_front`
- `print_bed_undercarriage_assembly.leader`

This is enough to cover:
- align whole assembly to whole assembly
- align whole assembly from one of its internal parts
- align to an internal part of another assembly

The same reference naming is used consistently across:
- dependency injection
- visualization
- placement

So:
- `part` uses the same selector syntax as the other sections
- `to` uses the same selector syntax as the other sections
- a bare assembly name means its `leader`
- a dotted reference means a named anchor within that assembly

## Semantics of one global alignment entry

Each alignment entry means:

1. Resolve the moving anchor from `part`
2. Resolve the target anchor from `to`
3. Determine the owning assembly named in `part`
4. Verify that all assemblies referenced by `part` and `to` are already present in the shared scene
5. Look up the current already-placed pose of both referenced assemblies in that scene
6. Compute a translation using `align_translation(moving_anchor, target_anchor, alignment, ...)`
7. Apply that translation to the whole owning assembly of `part`
8. Keep that updated global pose for all subsequent alignment entries and downstream assembly builds

Examples:
- `part: y_axis_drive_assembly` means `y_axis_drive_assembly.leader`
- `part: y_axis_drive_assembly.non_production_parts.motor_pulley` means that non-production part is the moving anchor, while the whole `y_axis_drive_assembly` moves
- `to: print_bed_assembly` means `print_bed_assembly.leader`
- `to: print_bed_assembly.non_production_parts.buffer_1` means that named non-production part is the target anchor

The key point is:
- the selector decides what geometric reference is used
- the whole owning assembly moves
- the move happens in the shared global placement scene
- once applied, that updated pose becomes immediately visible to later placement steps and later assembly builds

## Ordering is essential

This model only works if alignments are executed exactly in order.

The placement engine does not:
- reorder alignments
- merge them
- try to optimize them away
- split them by owning assembly

The user needs one script because each step may depend on the already-updated scene state from previous steps.

Declarative example:

```yaml
placement:
  alignments:
    - part: tool_head_mount_bottom_assembly.followers.carriage
      to: x_axis_assembly.non_production_parts.carriage_1
      alignment: CENTER

    - part: tool_head_mount_bottom_assembly.followers.carriage
      to: x_axis_assembly.non_production_parts.carriage_1
      alignment: BACK

    - part: tool_head_mount_bottom_assembly.followers.carriage
      to: x_axis_assembly.non_production_parts.carriage_1
      alignment: TOP
```

This must be interpreted literally as three sequential scene updates.

This rule stays the same.
The difference is when the next entry is attempted:
- after each assembly build completion
- and repeatedly until the next entry is blocked by a missing assembly

## Implicit placement dependencies

Explicit `depends_on` is not required in the placement layer.

Placement dependencies can be derived implicitly from the selectors mentioned in the global script:
- the owning assembly mentioned in `part`
- every assembly mentioned in `to`

This is useful for validation and cache invalidation.

It is also useful for eager execution:
- to decide whether the current placement entry is runnable yet
- to know exactly why the placement cursor must stop

It does not become another user-maintained declaration layer.

## Axes and stack gaps

The YAML layer preserves the real behavior of the existing primitives.

That means:
- `stack_gap` is supported
- `axes` are supported where `align_translation(...)` supports them
- `post_translation` is supported as an additional translation applied immediately after the alignment move

That means:
- `axes` is valid with `CENTER`
- `axes` is not treated as generic across every alignment mode

Partial placement on selected axes uses this idiom:
- one `CENTER` with `axes`
- followed by further `TOP`, `BACK`, `STACK_*`, and similar alignments

`post_translation` is useful when the main anchor relationship should still be expressed as a normal alignment, but the final assembly pose needs an additional parameterized offset from globals.

## Y-axis / bed example

The coupled placement problem is expressed as one global scene script.

Geometry layer:
- `printer_frame_assembly`
- `print_bed_assembly`
- `print_bed_undercarriage_assembly`
- `y_axis_assembly`

Global placement layer in `assemblies.yaml`:

```yaml
placement:
  alignments:
    - part: print_bed_assembly
      to: printer_frame_assembly
      alignment: CENTER
      axes: [0]

    - part: print_bed_assembly
      to: printer_frame_assembly
      alignment: STACK_TOP
      stack_gap: { $ref: print_bed_vertical_gap_to_frame }

    - part: print_bed_undercarriage_assembly
      to: print_bed_assembly
      alignment: CENTER
      axes: [0, 1]

    - part: print_bed_undercarriage_assembly
      to: print_bed_assembly.non_production_parts.damper_left_front
      alignment: STACK_BOTTOM

    - part: y_axis_assembly.followers.carriage_front_carriage_left
      to: print_bed_assembly
      alignment: TOP
```

The exact selectors may change, but the structure stays the same:
- build geometry independently
- insert finished assemblies into the shared scene as they become available
- advance the global placement script whenever the next step is now runnable
- let later assemblies consume the already placed upstream scene state

## Rendering and production

The execution model is:

1. Build canonical assemblies in dependency order.
2. Insert each completed assembly into the shared scene.
3. Advance the global placement script eagerly as far as possible after each build completion.
4. Allow downstream assemblies to build against that current placed scene state when needed.
5. Materialize visualization scene parts from the final placed scene.
6. Export or render from that placed scene.

Visualization and production operate on placed assemblies, not on pre-placement local geometry, whenever final assembly positioning matters.

This is especially important for:
- preview scenes
- combined STEP export
- final printer assembly visualization
- any output where relative assembly positions are part of the result

Production of individual printable parts can still use canonical local geometry where appropriate.
Scene-style output uses the placed scene.

## Output of the placement layer

The placement layer outputs:
- placed transforms for each referenced assembly
- metadata describing those transforms
- a placed scene for visualization and export
- placement cursor metadata describing which prefix of the global script has been applied at each stage

Transformed STEP export is secondary.

The important result is:
- resolved global poses of already-built assemblies
- available incrementally during the build, not only after it

## Caching

Geometry cache is based on:
- generator code hash
- assembly resource YAML hash
- public parameters
- injected dependency hashes

Global placement cache is based on:
- the global `placement` section in `assemblies.yaml`
- placement engine code
- hashes of all assemblies referenced by placement selectors

Therefore:
- if geometry changes, placement re-runs automatically
- if only placement alignments change, geometry does not need rebuilding

In the eager model:
- rebuilding an upstream assembly may invalidate the already-applied placement prefix at or after the first step that references it
- the placement cursor must then be recomputed from the beginning or from a safe invalidation point
- downstream assemblies that depend on placed upstream scene state may also need rebuilding if their effective injected context changes

## System shape

Placement is one minimal global declarative script in `assemblies.yaml`, based on ordered alignments and executed eagerly in lockstep with dependency-order assembly creation.

The system has:
- top-level `placement`
- `alignments`
- `part`
- `to`
- selector paths
- `alignment`
- optional `axes`
- optional `stack_gap`
- one internal placement cursor managed by the builder
- one shared placed-scene state visible during later assembly builds

The system does not have:
- per-assembly placement blocks
- groups
- operations as a generic meta-layer
- instances indirection
- explicit placement `depends_on`
- point / plane / mate abstractions

The resulting system is:
- close to real ShellForgePy code
- easy to read in one place
- aligned with the actual execution order
- able to support downstream assemblies that rely on already placed upstream geometry
- expressive enough for the current problem
- acyclic at the geometry level
- cache-friendly
