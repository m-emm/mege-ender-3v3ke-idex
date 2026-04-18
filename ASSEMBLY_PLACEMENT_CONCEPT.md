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

## Current implementation in the builder

The current implementation is graph-based, not a separate ad-hoc scheduler hack.

Concretely:
- the builder still computes one build dependency graph
- explicit `depends_on` edges are added first
- the builder then derives additional implicit edges from the global `placement.alignments` script
- topological generations are computed from that augmented graph
- after each built or cache-hit assembly, the eager placement cursor is advanced immediately as far as possible

So the answer to "did the scheduler get hacked to look at placement?" is:
- no separate runtime reordering layer was added
- yes, the scheduler now consults the placement script while constructing the build graph
- the actual build order is still determined by one graph

## Exact rule used today

The current rule is intentionally conservative and simple.

For each assembly `A`:
- inspect `A.inject_parts`
- collect the set of injected upstream assemblies
- find the first placement step whose moving assembly is `A`
- look only at the placement prefix before that step
- within that prefix, find the last placement step whose moving assembly is one of the injected assemblies
- then add implicit build dependencies from `A` to every assembly referenced anywhere in that prefix up to and including that last relevant step

Equivalent intuition:
- if `A` consumes injected assembly `B`
- and `B` is moved by the placement script before `A` starts moving in the global placement script
- then `A` must not build until the whole relevant placement prefix that settles `B` has become executable and has run

This is exactly what fixed the bracket case:
- `y_axis_rail_carrier_brackets_assembly` injects `y_axis_assembly`
- `y_axis_assembly` is moved again later by the step aligning it to `print_bed_undercarriage_assembly`
- therefore the bracket assembly gets an implicit build dependency on the assemblies required to execute that placement prefix, including `print_bed_undercarriage_assembly`
- that pushes the bracket build after the undercarriage-dependent y-axis placement step

## Why this is conservative

The current algorithm does not try to prove geometric solvability axis-by-axis.

It does not attempt to infer that:
- a later `CENTER` on `[0]` might be independent from an earlier `TOP`
- a seemingly cyclic placement script could still work because different axes are resolved at different times
- only part of the placement prefix actually matters for one injected consumer

Instead it uses a safe approximation:
- if the ordered placement prefix may affect the injected assembly pose that a consumer relies on, that whole prefix becomes a build-order requirement

This keeps scheduling explicit and deterministic, but may reject some theoretically solvable cases.

## Interaction with cycles

Because placement-derived constraints are turned into graph edges, they participate in cycle detection exactly like explicit `depends_on` edges.

That means:
- if the augmented graph is acyclic, the builder computes normal topological generations
- if the augmented graph becomes cyclic, the builder currently treats that as unschedulable and fails like any other dependency cycle

Important:
- some such cycles may represent genuinely impossible build ordering
- some may only be artifacts of this conservative approximation
- the current implementation deliberately does not try to distinguish those two cases from the placement script alone

So the present design choice is:
- prefer one explicit graph-based scheduling model
- accept conservative false-negative cycles rather than silently building against partially settled placement state

## Separation of responsibilities

The builder now has two separate but cooperating mechanisms:

1. Graph construction
- explicit `depends_on`
- implicit placement-derived edges for injected geometry consumers
- result: one augmented DAG used for build generations

2. Eager placement execution
- after each assembly finishes building or is loaded from cache
- repeatedly execute the next placement step while its referenced assemblies are available
- stop at the first blocked step

The graph decides when an assembly is allowed to build.
The eager placement cursor decides how much of the global scene script has already been applied at that moment.

## What is not implemented

The current implementation does not yet provide:
- a minimal dependency extraction based on per-axis reasoning
- a proof system for "cyclic but still workable" placement scripts
- user-visible placement dependency annotations separate from the graph
- a split between hard scheduling edges and softer placement-order hints

If those become necessary later, they would be a deliberate extension of the current conservative rule rather than a correction of it.

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

## Possible extension: `rigid_attach`

The new x-axis / extruder work exposes a real gap in the current placement model.

Today one placement step only ever moves the owning assembly named by `part`.
That is the current architecture:
- placement state stores transform history per assembly
- scene updates are applied by `assembly_name`
- the existing builder tests explicitly verify that one placement step moves only the owning assembly

So the current system does this correctly:
- align `sprite_extruder_left_assembly` to a carriage or profile
- remember that placed pose for later references

But it does not do this:
- when `x_axis_assembly` is moved later, automatically drag the already placed left and right extruder assemblies along with it

That means the need is real.
It is not already solved by the current placement state structure.

At the same time, this is not "impossible" today in a strict sense.
The same final scene can still be achieved with the current system by using less attractive patterns:
- repeat the extruder alignment later after every relevant x-axis move
- fold the extruders into a larger geometry assembly so they are no longer independent scene assemblies
- reintroduce Python-side assembly composition logic that manually reapplies those transforms

Those options all work against the current design goals:
- lean dependency graphs
- one readable global placement script
- independently buildable assemblies
- no return to builder-script placement magic

So the right conclusion is:
- `rigid_attach` is feasible
- it fits the scene-placement architecture
- it is not mathematically necessary for final pose solvability
- but it is necessary if the goal is to keep the placement graph lean while allowing independently built assemblies to become rigid subassemblies over time

## Why a wrapper assembly is not enough

The current `extruders_assembly` is a useful scene wrapper, but it does not by itself solve this problem.

Why:
- its visualization is composed from dependency assemblies
- those scene parts keep their original `assembly_name`
- placement transforms are currently applied by `assembly_name`

So moving `extruders_assembly` would not automatically move `sprite_extruder_left_assembly`, `sprite_extruder_right_assembly`, `x_axis_lower_profile_assembly`, and `x_axis_rail_assembly` as one rigid unit unless the placement engine itself grows a notion of shared pose ownership.

This is exactly why the missing primitive is not "another wrapper assembly", but "these assemblies now move as one".

## Important selector detail

`rigid_attach` should attach owning assemblies, not arbitrary selected subparts.

So this entry:

```yaml
- part: sprite_extruder_left_assembly
  to: x_axis_lower_profile_assembly
  alignment: TOP
  rigid_attach: true
```

would rigidly couple:
- `sprite_extruder_left_assembly`
- `x_axis_lower_profile_assembly`

It would not automatically couple the extruder to `x_axis_assembly` unless `x_axis_assembly` and `x_axis_lower_profile_assembly` had themselves already become part of one rigid placement group.

For the stated goal, the more important case is usually to attach the extruder to an anchor owned by `x_axis_assembly`, for example:

```yaml
- part: sprite_extruder_left_assembly
  to: x_axis_assembly.non_production_parts.lower_axis_profile
  alignment: TOP
  rigid_attach: true
```

That way, later moves of `x_axis_assembly` would also move the extruder.

## Proposed semantics

The cleanest interpretation is:
- `rigid_attach: true` is optional on a placement entry
- it is valid only when `to` is present
- normal alignment, optional post rotation, and optional post translation run first
- after that step completes, the owning assembly of `part` and the owning assembly of `to` are merged into one rigid placement group
- from then on, any later transform applied to any member of that rigid group is applied to all members of that group
- rigid attachment is transitive
- rigid attachment is monotonic
- there is no detach operation in the first version

This matches the physical interpretation well:
- assemblies can be built independently
- they can be positioned relative to one another
- at some point they become bolted together
- after that, scene motion applies to the whole rigid subassembly

It also fits the existing placement philosophy:
- still one global ordered script
- still based on `align(...)` semantics
- still no mates, planes, or generic constraint solver
- still no geometry dependency loop

## What should happen after attachment

After two assemblies become rigidly attached:
- a later move of the original source must move the original target too
- a later move of the original target must move the original source too
- a later move of any third assembly rigidly attached to either one must move the whole merged set

That means `rigid_attach` is not just "remember that this alignment happened".
It is a transform propagation rule for all later placement steps.

It also means later placement steps that try to change the relative pose inside one already attached rigid group should be treated as invalid or redundant.
The first implementation should prefer strict validation over trying to silently guess intent. Placement / alignment operations where there is a path in the "rigid_attach" graph between the assemblies implicated by the  "part:" and the "to:" immediately raise an exception.

## What it would require in code

### 1. YAML and validation

The placement schema would need one new optional field:
- `rigid_attach: true`

Validation rules should include:
- `rigid_attach` requires `to`
- `rigid_attach` applies to owning assemblies, not only to the selected anchors
- attaching two assemblies already in the same rigid group should either be a no-op or a validation error
- a later placement step that tries to move one rigid-group member relative to another rigid-group member should fail clearly

### 2. Placement runtime state in `builder.py`

The eager placement execution state would need rigid-group tracking in addition to per-assembly transform history.

The best implementation hint here is to use a dedicated undirected `networkx.Graph` as the rigidity graph.

Shape:
- nodes are assembly names
- an undirected edge means "these two assemblies became rigidly attached at some placement step"
- rigid groups are exactly the connected components of that graph

That makes the core queries trivial and readable:
- "are `A` and `B` rigidly connected?" means "are they in the same connected component?"
- "give me everything rigidly connected to `A`" means `node_connected_component(...)`
- "how many rigid groups exist, and what are their members?" means `connected_components(...)`

This is a good fit here because the builder already uses `networkx` for graph reasoning, and the rigidity concept is naturally graph-shaped rather than list-shaped.

When a placement step executes:
- resolve the moving assembly
- resolve the target assembly
- determine the current rigid group of the moving assembly from the rigidity graph
- apply the computed transforms to every member of that moving rigid group, not only to the moving assembly
- if `rigid_attach: true`, add an edge between the owning assemblies of `part` and `to` after the step completes

The current transform model can still work.
Because transforms are ordinary translate / rotate functions, the first implementation can keep per-assembly histories and simply append the same step transforms to every assembly in the affected rigid group.

### 3. Final scene placement in `_apply_placement_alignments(...)`

The non-eager final scene placement path must mirror the same semantics.

Today `_apply_transform_to_scene_parts(...)` updates scene parts by matching `assembly_name`.
With rigid attachment, the caller would need to:
- determine the current rigid group of the moving assembly
- apply the step transform to every scene part whose `assembly_name` belongs to that rigid group
- merge groups after a `rigid_attach` step

Without that mirrored logic, eager placement during build and final scene export would diverge.

### 4. Placement graph model in `graph_model.py`

This is the subtle part.

The current graph model reasons about placement steps mostly in terms of the moving assembly and the target assembly.
With rigid attachment, later motion of assembly `B` may also move previously attached assembly `A`, even if `A` is not named as the moving assembly of that later step.

So the graph model would need to simulate rigid-group growth while it walks the ordered placement script.
The cleanest way to do that is again with an undirected `networkx.Graph` that is updated step by step while the placement DAG is constructed.

Concretely:
- `PlacementStep` should carry `rigid_attach`
- placement DAG construction should track rigid groups while iterating through the steps
- the current rigid group of any assembly should be derived from the current connected component in that rigidity graph
- the predecessor set for a step should be derived from the latest placement event that affected any member of the moving rigid group and any member of the target rigid group
- after a step with `rigid_attach`, the graph model should add the new rigidity edge so subsequent steps see the merged connected component

This matters for scheduling as well:
- if a later move of `x_axis_assembly` also moves `sprite_extruder_left_assembly` because they are rigidly attached
- then any downstream assembly that injects the extruder and depends on its placed pose must wait for that later x-axis move too

But there is an important boundary here for subset builds:
- the rigidity graph should not be allowed to pull additional assemblies into the selected build set
- `rigid_attach` should not extend `assembly_dependency_graph`
- `rigid_attach` should not extend the global placement-derived build dependency closure used to decide which assemblies must be built

So the safer rule is:
- rigid attachment may affect transform propagation and placement-step reasoning inside the already selected active scene
- but it must not create new assembly-selection pressure beyond what the non-rigid model would already require

If full-printer placement fidelity requires assemblies outside the chosen subset, the user must explicitly build that larger subset.
`rigid_attach` itself should not silently widen the scope.

## Scope boundary

This feature should remain a placement-layer feature, not a geometry-layer feature.

That means:
- canonical cached assembly artifacts stay unchanged
- no new geometry dependency edges are introduced just because two assemblies later become rigidly attached in the scene
- cache invalidation still belongs to the placement layer
- the geometry layer remains acyclic

This is important architecturally.
`rigid_attach` should not turn scene composition back into one giant build-time geometry graph.

## Subset builds must stay lean

Yes, this is feasible, and it is a good design constraint.

The intended rule should be:
- building a small subset must not pull in extra assemblies just because some placement step somewhere uses `rigid_attach`
- placement steps whose referenced assemblies are outside the active subset remain simply non-executable and therefore inert
- no rigidity edge is created unless that placement step actually executes in the active build

So the rigidity graph should be:
- selection-scoped
- scene-local
- built only from the placement steps that actually execute for the current build

In practice that means:
- if the subset contains both `sprite_extruder_left_assembly` and `x_axis_assembly`, their rigid attachment can still work inside that subset
- if the subset does not contain the later frame-level assemblies that would move the x-axis in the full printer build, those later moves are simply absent
- the subset result is therefore intentionally a locally correct partial scene, not automatically the same as the fully placed global printer scene

This is the tradeoff, and it is probably the right one:
- subset builds stay fast and predictable
- `rigid_attach` remains a transform-propagation mechanism
- it does not become a hidden dependency-expansion mechanism

So your proposed rule is a good one:
- the rigidity graph should not extend the other dependency graphs

More precisely:
- it should not add new assembly build dependencies
- it should not enlarge the selected assembly closure
- it may still influence how already selected assemblies move together once their relevant placement steps have executed

## Recommended first version

The lean first version is:
- support `rigid_attach: true` only on normal placement entries with `to`
- attach owning assemblies after the step has been executed
- propagate later transforms to all members of the rigid group
- keep attachment monotonic and transitive
- reject relative-motion steps inside an already attached rigid group

That version is strong enough for the current x-axis / extruder problem and still keeps the system conceptually small.

## Tests that would be required

The builder test suite should gain explicit coverage for:
- aligning `A` to `B` with `rigid_attach: true`, then later moving `A`, and verifying that `B` moves too
- aligning `A` to `B` with `rigid_attach: true`, then later moving `B`, and verifying that `A` moves too
- transitive attachment such as `A` attached to `B`, then `B` attached to `C`
- final scene placement and eager placement producing the same rigid-group result
- subset builds not enlarging the selected assembly closure just because `rigid_attach` exists elsewhere in the placement script
- placement steps outside the active subset remaining inert rather than forcing extra assemblies to be built

If those tests pass, the feature would be well grounded in the current architecture rather than being a placement hack.
