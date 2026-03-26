# Assembly Placement Concept

Goal: extend the declarative assembly system so that assemblies can be built in stable local coordinates first, and only afterwards be placed relative to each other in a declarative, ordered, ShellForgePy-idiomatic way.

## Core direction

The right abstraction for this codebase is:
- `align(...)`
- ordered sequences of alignments
- selectors that refer to `leader`, `followers`, `cutters`, and `non_production_parts`
- the same mental model as `aligned_from_follower(...)` and `aligned_from_non_production_part(...)`

The wrong abstraction for this codebase is:
- points
- planes
- mates
- axes as first-class feature objects
- extra indirection layers such as `instances` unless they become necessary later

So the placement layer should be intentionally small.

## Problem statement

The current builder handles geometry dependencies well:
- build one assembly
- cache it
- inject parts from it into downstream assemblies

That is enough for geometry generation, but not for final relative placement.

Example:
- the bed and undercarriage can only be placed correctly in `y` after the y-axis rails and carriages exist
- the y-axis can only be placed correctly in `z` after the bed and undercarriage stack exists

This is not really a geometry cycle.
It is a placement problem between already-built assemblies.

## What ShellForgePy already provides

### `align(...)` is already the placement language

In [alignment_operations.py](/Users/mege/git/shellforgepy/src/shellforgepy/construct/alignment_operations.py), `align_translation(...)` and `align(...)` already provide the placement model that the codebase uses successfully:
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

Complex placement is already normally written as:
- center this to that
- then put it on top of that
- then move it to the back of the other thing

That is the natural declarative shape too.

### Assemblies already expose named internal references

In [leader_followers_cutters_part.py](/Users/mege/git/shellforgepy/src/shellforgepy/construct/leader_followers_cutters_part.py), assemblies already expose:
- `leader`
- `followers`
- `cutters`
- `non_production_parts`

and those can be named.

That already gives us the reference system we need.

### `aligned_from_follower(...)` already shows the pattern

The important existing pattern is:
- align an assembly not from its `leader`
- but from one of its named `followers` or `non_production_parts`

That is exactly what declarative placement needs to express.

So the YAML should mirror that pattern directly, not invent a different placement language.

## Recommended architecture

Keep the two-layer idea, but make the placement layer minimal.

1. Geometry assemblies
- build canonical geometry
- remain acyclic
- remain cached exactly as now

2. Placement section
- works on already-built assemblies
- applies ordered alignments
- produces a derived placed composition for visualization or downstream use

Important:
- canonical assembly artifacts stay untouched
- placement is a derived layer on top of them

## Minimal placement shape

The first version should only support ordered alignments.

Recommended shape:

```yaml
placement:
  alignments:
    - part: y_axis_drive_assembly.non_production_parts.motor_pulley
      to: print_bed_assembly.non_production_parts.buffer_1
      alignment: CENTER
      axes: [1, 2]

    - part: print_bed_undercarriage_assembly
      to: printer_frame_assembly
      alignment: STACK_TOP
      stack_gap: { $ref: undercarriage_stack_gap }
```

This is intentionally small:
- no `operations`
- no `group`
- no `instances`
- no explicit `depends_on`

It is just an ordered list of alignments.

## Selector rules

The placement system should reuse the selector style already used elsewhere in the builder.

Recommended selector syntax:
- `assembly_name`
- `assembly_name.leader`
- `assembly_name.followers.<name>`
- `assembly_name.cutters.<name>`
- `assembly_name.non_production_parts.<name>`
- `assembly_name.fused`

If only `assembly_name` is given, it should mean `assembly_name.leader`.

Examples:
- `printer_frame_assembly`
- `y_axis_assembly.followers.carriage_front_carriage_left`
- `print_bed_assembly.non_production_parts.buffer_1`
- `print_bed_undercarriage_assembly.leader`

This is enough to cover:
- align whole assembly to whole assembly
- align whole assembly from one of its internal parts
- align to an internal part of another assembly

The same reference naming should be used consistently across:
- dependency injection
- visualization
- placement

So:
- `part` uses the same selector syntax as the other sections
- `to` uses the same selector syntax as the other sections
- a bare assembly name means its `leader`
- a dotted reference means a named anchor within that assembly

## Semantics of one alignment entry

Each alignment entry should mean:

1. Resolve the moving anchor from `part`
2. Resolve the target anchor from `to`
3. Determine the owning assembly named in `part`
4. Compute a translation using `align_translation(moving_anchor, target_anchor, alignment, ...)`
5. Apply that translation to the whole owning assembly
6. Keep that updated pose for the following alignment entries

Examples:
- `part: y_axis_drive_assembly` means `y_axis_drive_assembly.leader`
- `part: y_axis_drive_assembly.non_production_parts.motor_pulley` means that non-production part is the moving anchor, while the whole `y_axis_drive_assembly` moves
- `to: print_bed_assembly` means `print_bed_assembly.leader`
- `to: print_bed_assembly.non_production_parts.buffer_1` means that named non-production part is the target anchor

This is the declarative equivalent of:

```python
tool_head_mount = tool_head_mount.aligned_from_follower(
    "carriage",
    target_carriage,
    Alignment.CENTER,
)
```

except generalized to selector paths.

The key point is:
- the selector decides what geometric reference is used
- the whole assembly moves

## Ordering is essential

This model only works if alignments are executed in order.

That is already how the code works today.

Example:

```python
tool_head_mount = tool_head_mount.aligned_from_follower(
    "carriage", target_carriage, Alignment.CENTER
)
tool_head_mount = tool_head_mount.aligned_from_follower(
    "carriage", target_carriage, Alignment.BACK
)
tool_head_mount = tool_head_mount.aligned_from_follower(
    "carriage", target_carriage, Alignment.TOP
)
```

Declarative equivalent:

```yaml
placement:
  alignments:
    - part: tool_head_mount.followers.carriage
      to: target_carriage
      alignment: CENTER

    - part: tool_head_mount.followers.carriage
      to: target_carriage
      alignment: BACK

    - part: tool_head_mount.followers.carriage
      to: target_carriage
      alignment: TOP
```

The placement engine should not try to reorder, merge, or optimize these steps away.

## Implicit dependencies

Explicit `depends_on` should not be required in the placement layer.

Dependencies can be derived implicitly:
- the owning assembly mentioned in `part`
- every assembly mentioned in `to`

So if a placement block references:
- `printer_frame_assembly`
- `print_bed_assembly`
- `print_bed_undercarriage_assembly`
- `y_axis_assembly`

then those are the placement dependencies.

This is simpler and avoids duplicate declarations.

## Axes and stack gaps

The YAML layer should preserve the real behavior of the existing primitives.

That means:
- `stack_gap` should be supported
- `axes` should only be supported where `align_translation(...)` actually supports it

Today that means:
- `axes` is valid with `CENTER`
- it should not pretend to work generically for every alignment mode

If partial placement on selected axes is needed, the intended idiom remains:
- one `CENTER` with `axes`
- followed by further `TOP`, `BACK`, `STACK_*`, and similar alignments

## Current y-axis / bed problem in this model

The current coupled placement problem should be handled like this:

Geometry layer:
- `printer_frame_assembly`
- `y_axis_assembly`
- `print_bed_assembly`
- `print_bed_undercarriage_assembly`

Placement layer:

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

The exact numbers and selectors may change, but the structure is correct:
- build geometry independently
- place by ordered alignments afterwards

## Output of the placement layer

The placement layer should output:
- placed transforms for each referenced assembly
- metadata describing those transforms
- a placed scene for visualization

Optionally it may also export transformed STEP files, but that is secondary.

The important result is:
- resolved poses of already-built assemblies

## Caching

Geometry cache should remain based on:
- generator code hash
- assembly resource YAML hash
- public parameters
- injected dependency hashes

Placement cache should be based on:
- placement YAML content
- placement engine code
- hashes of all referenced assemblies

So:
- if geometry changes, placement re-runs automatically
- if only placement alignments change, geometry does not need rebuilding

## Recommendation

Recommendation: implement placement as a minimal second declarative layer based on ordered alignments only.

The first version should have:
- `placement`
- `alignments`
- `part`
- `to`
- selector paths
- `alignment`
- optional `axes`
- optional `stack_gap`

It should explicitly not have, for now:
- groups
- operations as a generic meta-layer
- instances indirection
- explicit placement `depends_on`
- point / plane / mate abstractions

That keeps the system:
- close to real ShellForgePy code
- easy to read in YAML
- expressive enough for the current problem
- acyclic at the geometry level
- cache-friendly

This is the cleanest next step for this codebase.
