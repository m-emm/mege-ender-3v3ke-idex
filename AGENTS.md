# Agent Orientation: mege-ender-3v3ke-idex

This repository (`mege-ender-3v3ke-idex`) contains ShellForgePy-based designs for an IDEX (Independent Dual Extruder) conversion of the Creality Ender 3V3 KE 3D printer. The project focuses on creating printable mechanical parts, mounts, frames, and hardware interfaces for the dual-extruder modification.

The current preferred workflow in this repo is assembly-first. Treat the declarative assembly builder stack as the default entrypoint for new work:
- Define or update an `assembling/assemblies/*_assembly.yaml` file for the assembly contract, dependencies, visualization output, production output, and process data
- Wire global parameters and top-level composition through `assembling/assemblies/assemblies.yaml`
- Keep Python geometry in `src/mege_ender_3v3ke_idex/designs/assemblies/*.py` as the generator implementation behind the assembly manifest

Prefer this latest assembly-style geometry assembling over older standalone design-script-only workflows whenever possible.

## Project Overview

This is a hardware design project that uses ShellForgePy to create parametric 3D models for:
- X-axis assemblies with dual motor mounts
- Z-axis carriages and guides
- Extruder mounting systems
- GT2 belt and pulley systems
- Aluminum extrusion profiles (2020/4040 T-slot)
- NEMA stepper motor mounts

## ShellForgePy Idiomatic Usage

This project follows ShellForgePy best practices. For comprehensive guidance on ShellForgePy patterns, see the companion guide in `shellforgepy-meges-workshop/AGENTS.md` or the main ShellForgePy repository.

But one hint: In a geometry building / assembly builder script, watch the ratio of align calls to translate calls / origin=(...). Most translate calls use
complex coordinate math to translate to the right place. align calls are human readable. Prefer align calls over translate calls, make 
the ratio align / translate as high as possible. translates cannot always be avoided, but often.

### Key Patterns Used in This Project

#### 1. Assembly-First Builder Workflow

Prefer the latest builder-driven assembly pattern for new geometry and refactors:

```yaml
ShellforgepyBuilderVersion: "2026-03-27"

Builder:
  Visualization:
    parts:
      - source: self
        artifact: leader
        name: main_part
      - source: self
        artifact: followers
        name_template: "{name}"
      - source: self
        artifact: non_production_parts
        name_template: "{name}"
```

- `assembling/assemblies/*_assembly.yaml` is the authoritative place for assembly structure
- Use the `Builder` section to describe visualization and production behavior instead of hard-coding export layout in Python
- Use `assemblies.yaml` for globals, shared parameters, and high-level assembly composition
- Treat the Python generator as geometry implementation, not as the primary assembly definition
- Do not import another module from `src/mege_ender_3v3ke_idex/designs/assemblies/` inside an assembly generator in order to build a subassembly. That bypasses explicit builder dependencies, makes parameter flow harder to reason about, and can break cache invalidation.
- If assembly A needs assembly B, give B its own `*_assembly.yaml`, declare B as a dependency of A in YAML, and consume the injected dependency object in A's generator. Keep shared low-level geometry in non-assembly helper modules when it truly needs to be reused outside the builder graph.

When adding a new assembly, create both:
- a generator in `src/mege_ender_3v3ke_idex/designs/assemblies/<name>.py`
- a matching manifest in `assembling/assemblies/<name>.yaml`

- Keep resource YAMLs cache-isolated: one `*_assembly.yaml` should normally point to one dedicated generator module. The builder hashes the generator source file, so two resource YAMLs sharing one module will invalidate each other's cached CAD artifacts when either generator changes.
- During staged refactors of expensive CAD assemblies, prefer intentional short-lived duplication in separate generator modules over sharing assembly generator modules. Remove the legacy copy once the downstream assembly has been migrated.

The generator should return assembly-friendly artifacts with stable names so the builder can select `leader`, `followers`, and `non_production_parts` cleanly.

#### 2. Composite Parts with LeaderFollowersCuttersPart

Complex assemblies use `LeaderFollowersCuttersPart` to manage printable parts, visual references, and cutting tools:

```python
retval = LeaderFollowersCuttersPart(
    leader=mount_plates,  # Main printable part
    non_production_parts=non_production_parts,  # Visual reference (motors, rails, etc.)
    non_production_names=non_production_names
)

# Add named followers for specific sub-parts
retval.add_named_follower(endcap_box, "endcap_box")
retval.add_named_non_production_part(axle, "axle")

# Retrieve parts by name
mount_plate = x_axis.get_follower_part_by_name("mount_plate")
motor_visual = x_axis.get_non_production_part_by_name("motor_left")
```

This pattern is especially important for the declarative builder, because production and visualization manifests frequently address parts by follower or non-production name.

#### 3. Parameterized Design

All dimensions are defined as module-level constants for easy tuning:

```python
motor_size = 42.3
axis_profile_length = 500
motor_mount_plate_thickness = 6
idler_gap = 2
# ... etc.
```

#### 4. Mechanical Hardware Integration

The project uses mechanical screws and fasteners:

```python
from shellforgepy.simple import MScrew

screw = MScrew.from_size("M3")
hole_diameter = screw.clearance_hole_normal
head_diameter = screw.cylinder_head_diameter

# Create threaded inserts
thread_inset_cutter = create_cylinder(
    m_screws_table["M3"]["thread_inset_hole_diameter"] / 2,
    m_screws_table["M3"]["thread_inset_length"]
)
```

#### 5. Process Data and Slicer Integration

Production parts include detailed slicer configuration via `mege_3devops.process_data`:

```python
from mege_3devops.process_data.mender3.process_data_08_high_speed import (
    PROCESS_DATA_PLA_08_HS,
)
import copy

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLA_08_HS)
PROCESS_DATA["process_overrides"].update({
    "wall_loops": "1",
    "layer_height": "0.42",
    "outer_wall_speed": "70",
    # ... extensive print settings
})

arrange_and_export(
    parts.as_list(),
    script_file=__file__,
    prod=PROD,
    process_data=PROCESS_DATA,
)
```

For support tuning, interpret `support_threshold_angle` carefully: higher values produce more aggressive support generation, while lower values produce less support. In practice, values like `80` can support near-vertical walls, while values like `10` can leave even near-horizontal geometry unsupported. Do not assume that increasing `support_threshold_angle` reduces support.

## Code Style

### Python Conventions
- Follow the ShellForgePy style: Black formatting (line length 88), isort for imports
- Use descriptive variable names over comments
- Keep functions focused on single mechanical components
- Prefer module-level constants for all tunable parameters

### Design Patterns
- Avoid local internal helpers in assembly generator modules, use straight scripts telling the story of constructing the part in a linear way. shellforgepy is a DSL, use it directly and do not wrap it in local wrappers
- Separate reusable components into their own functions (e.g., `create_motor_with_mount()`, `create_idler_cage()`)
- Use `PartCollector` for accumulating multiple parts in a loop before fusing. However for normal fusing of two known parts, they are not necessary.
- Prefer assembly manifests plus builder configuration for composition, export, and visualization
- Use `LeaderFollowersCuttersPart` for complex assemblies with visual references and stable named artifacts
- Align parts relative to each other using the `align()` function with `Alignment` enums; do not use align_translation, unless absolutely necessary to move multiple parts together
- For symmetric corner hardware, prefer a nested `left/right` x `front/back` loop over copy-pasted per-corner code. Use an outer loop like `("left", Alignment.LEFT)` / `("right", Alignment.RIGHT)` and an inner loop over `Alignment.FRONT` and `Alignment.BACK`; then derive placement from `side_alignment.opposite.stack_alignment`, `front_back_alignment.stack_alignment`, and `front_back_alignment.opposite` instead of manual sign math.
- Stack gaps are a great feature to space parts apart, but also to sink one part into another. align(...,stack_gap=my_stack_gap) allows positive (gap) and negative (sink into) values for my_stack_gap
- Often initial align calls use `Alignment.CENTER`. Even though this supports `axes=[..]` this is often not necessary, because the subsequent LEFT or FRONT or other alignments will completely define the alignment along other axes, so leaving it out in the inital call will yield the same geometry but reduce code noise.
- Prefer named `followers` / `non_production_parts` that are easy to reference from YAML `Builder.Visualization.parts` and `Builder.Production.parts`
- Prefer wiring process data, production flips, rotations, prototype selections, and plate arrangement in YAML instead of embedding that export logic in Python

### Avoid
- Do not use `collector.part` directly - treat collectors as parts themselves
- Do use as little translation offset calculations as possible - use align(), align(part, target, Alignment.STACK_RIGHT,stack_gap=-move_into_part) .. patterns wherever possible
- Do not catch exceptions - let scripts fail fast on geometry errors
- Do not add tons of validations for parameters - parameters are visually tuned by users, they will see if something is off
- Do not create ad-hoc test scripts - write proper pytest tests
- Do not introduce new standalone export-oriented geometry scripts when the work belongs in the builder-based assembly system
- Do not duplicate assembly structure in Python when the same concern belongs in `*_assembly.yaml`
- Do not import or call another assembly generator from inside an assembly generator; model that relationship in YAML dependencies and use the injected assembly instead
- Do not use dark colors for visualization - they hide the shape. Use ample lightness and bright colors.
- Always perfer align() calls over translate() calls and origin=(...) using complex coordinate calculations

## Testing

- Prefer creating proper pytest tests in `tests/` directory
- Do not assert that configurable calibration, Klipper, process data, slicer profile, machine limit, purge path, bed temperature, support, filament, or other visually tuned defaults equal specific literals. Tests should verify consistency, valid structure, generated outputs matching their sources, positive/ranged values, derived relationships, or explicit test-local fixtures so calibration and process tuning do not require test edits.
- Run tests: `pytest` from repo root
- For visual verification: `./run.sh src/mege_ender_3v3ke_idex/designs/<design_file>.py`
- Production exports: `SHELLFORGEPY_PRODUCTION=1 ./run.sh <design_file>.py`

## Repository Layout

```
mege-ender-3v3ke-idex/
├── src/
│   └── mege_ender_3v3ke_idex/
│       └── designs/
│           ├── alu_extrusion_profile.py      # T-slot extrusion profiles
│           ├── extruder.py                   # Extruder mounting
│           ├── gt2belt.py                    # Belt/pulley components
│           ├── nema_motors.py                # Stepper motor models
│           ├── jury_rigged_z_carriage.py     # Z-axis components
│           └── assemblies/
│               └── x_axis_assembly.py        # X-axis assembly generator
├── klipper_setup/
│   ├── klipper_config/                  # Active Klipper config truth
│   │   ├── printer.cfg                  # THE generated active printer config
│   │   ├── printer.cfg.template         # THE active config template
│   │   ├── calib.yaml                   # IDEX calibration input
│   │   ├── wiring/                      # THE active Pico/TMC wiring truth
│   │   ├── update_menderpi.sh           # THE active deploy script
│   │   └── archive/                     # Historical/reference helpers only
│   └── image_build/                     # Raspberry Pi image build system
│       └── overlays/stage2/99-klipperpi/
├── resources/
│   └── *.step                           # Reference CAD files (OEM parts)
├── runs/
│   └── <timestamp>/                     # Generated STL/OBJ exports
└── tests/                               # Unit tests
```

## Klipper Configuration Deployment

`klipper_setup/klipper_config/printer.cfg` is THE generated active printer
config. It is the local source of truth for
`pi@menderpi.local:~/printer_data/config/printer.cfg`.

The root of `klipper_setup/klipper_config/` should stay intentionally small:
`README.md`, `calib.yaml`, `generate_printer_cfg.py`, `printer.cfg`,
`printer.cfg.template`, `update_menderpi.sh`, `wiring/`, and `archive/`.
Active wiring lives under `wiring/`; files under `archive/` are
historical/reference material only.

### Deployment Workflow

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex/klipper_setup/klipper_config
# Edit calib.yaml, printer.cfg.template, or wiring/*.yaml
python generate_printer_cfg.py --check
wiring/generate_wiring_svgs.sh --check
python wiring/validate_wiring.py
./update_menderpi.sh
```

`update_menderpi.sh` copies local `printer.cfg` to the Pi, backs up the previous
remote `printer.cfg`, restarts Klipper, and reports Moonraker/Klippy status.

### Git Tracking of Configuration Files

Klipper `.cfg` files in `klipper_setup/klipper_config/` and its archive are
tracked in git (see `.gitignore` exception rules) to enable version-controlled
deployment and historical rollback. This allows:
- Configuration history and rollback
- Collaborative development of printer settings
- Direct deployment via `update_menderpi.sh`

## Common Tasks

### Running Declarative Assemblies

Use the repository's pyenv-selected Python directly from the repo root. Do not create or activate an ad-hoc `venv` here.
**Do not use** `--force` unless absolutely necessary for shellforgepy development - the caching mechanism works reliably.

```bash
# Visualize the x-axis assembly
python -m shellforgepy build assembling/assemblies/assemblies.yaml --assembly x_axis_assembly --visualize

# Production run for the x-axis with slicing
python -m shellforgepy build assembling/assemblies/assemblies.yaml --assembly x_axis_assembly --production --slice --visualize

# Visualize a single assembly
python -m shellforgepy build assembling/assemblies/assemblies.yaml --assembly y_axis_rail_carrier_brackets_assembly --visualize

# Force a fresh rebuild and visualize the whole printer scene
python -m shellforgepy build assembling/assemblies/assemblies.yaml --assembly whole_printer_assembly --visualize

# Rebuild just the print bed assembly and export the geometry artifacts
python -m shellforgepy build assembling/assemblies/assemblies.yaml --assembly print_bed_assembly --visualize

# Production run for one selected plate, including slicing
python -m shellforgepy build assembling/assemblies/assemblies.yaml --assembly print_bed_undercarriage_assembly --production --slice --visualize --plate adjustment_wheel_single
```

Prefer these builder commands over directly running a Python generator whenever the target geometry already exists as an assembly manifest.

For assembly-related code changes, coding agents should prefer verification runs through `python -m shellforgepy build ...` instead of only running the generator module directly. Use `--production --slice` when the change affects production output, plate arrangement, process data, or slicer-facing geometry.

Do not use `--open` in routine agent verification runs. Reserve `--open` for interactive user-requested slicer GUI sessions. The user-facing equivalent is:

```bash
python -m shellforgepy build assembling/assemblies/assemblies.yaml --assembly print_bed_undercarriage_assembly --production --slice --visualize --open --plate adjustment_wheel_single
```

Use the generated previews to asess if the design you created or modified is correct and fitting the requirements.

### Assembly File Roles

- `assembling/assemblies/assemblies.yaml` is the top-level builder input with globals, shared dimensions, and assembly graph wiring
- `assembling/assemblies/*_assembly.yaml` defines one assembly's parameters, generator mapping, dependencies, visualization parts, production parts, arrangement, and process data
- `src/mege_ender_3v3ke_idex/designs/assemblies/*.py` implements the geometry generator referenced by the YAML manifest

For repo work, prefer editing the assembly YAML and builder configuration first, then adjust the Python generator only where geometry must change.

### Typical Design Workflow

1. **Define parameters** at module level (dimensions, clearances, etc.)
2. **Create component functions** for reusable parts (motors, mounts, idlers)
3. **Build assemblies** using `LeaderFollowersCuttersPart` to combine parts
4. **Add to PartList** with appropriate production flags
5. **Configure process_data** for slicer integration
6. **Export** using `arrange_and_export()`

### Example: Creating a New Mount

```python
def create_motor_mount(motor_size, thickness):
    """Create a motor mount plate."""
    mount = create_filleted_box(
        motor_size * 1.2,
        motor_size * 1.2,
        thickness,
        fillet_radius=2.0,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP]
    )
    
    # Add motor mounting holes
    motor = create_nema_composite()
    mount = motor.use_as_cutter_on(mount)
    
    return mount
```

## Environment Notes

- Python ≥3.11 required
- This repo relies on its pyenv environment selection being already configured per development directory. From the repo root, plain `python ...` commands should use the correct interpreter automatically.
- Do not create or suggest a separate `venv` for routine work in this repository unless the user explicitly asks for it.
- Install/update dependencies into the selected environment with: `pip install -e ".[testing]"`
- Dependencies: ShellForgePy, mege_3devops (for process_data)
- Optional: FreeCAD or CadQuery backends (auto-selected by ShellForgePy)

## Integration with Other Repositories

- **shellforgepy**: Core CAD library (geometry primitives, alignment, export)
- **mege_3devops**: Process data and slicer configuration presets
- **shellforgepy-meges-workshop**: Example designs and patterns

## Design Philosophy

- **Parametric first**: All dimensions configurable via constants
- **Fast iteration**: Quick preview and export for rapid prototyping
- **Print-ready**: Designs consider printability, support requirements, clearances
- **Modular**: Reusable component functions for common mechanical elements
- **Assembly-aware**: Use `LeaderFollowersCuttersPart` to maintain visual context

## Debugging Tips

- Use non-production parts to visualize reference geometry (motors, rails, screws)
- Add parts with `skip_in_production=True` to see assembly context without exporting
- Log important dimensions: `_logger.info(f"mount_plate_size: {get_bounding_box_size(mount_plate)}")`
- Check alignment by temporarily fusing parts to verify positioning
- Export intermediate steps during development to verify geometry

Keep this guide current as the IDEX conversion design evolves.
