# Agent Orientation: mege-ender-3v3ke-idex

This repository (`mege-ender-3v3ke-idex`) contains ShellForgePy-based designs for an IDEX (Independent Dual Extruder) conversion of the Creality Ender 3V3 KE 3D printer. The project focuses on creating printable mechanical parts, mounts, frames, and hardware interfaces for the dual-extruder modification.

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

### Key Patterns Used in This Project

#### 1. Composite Parts with LeaderFollowersCuttersPart

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

#### 2. Parameterized Design

All dimensions are defined as module-level constants for easy tuning:

```python
motor_size = 42.3
axis_profile_length = 500
motor_mount_plate_thickness = 6
idler_gap = 2
# ... etc.
```

#### 3. Mechanical Hardware Integration

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

#### 4. Process Data and Slicer Integration

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

## Code Style

### Python Conventions
- Follow the ShellForgePy style: Black formatting (line length 88), isort for imports
- Use descriptive variable names over comments
- Keep functions focused on single mechanical components
- Prefer module-level constants for all tunable parameters

### Design Patterns
- Separate reusable components into their own functions (e.g., `create_motor_with_mount()`, `create_idler_cage()`)
- Use `PartCollector` for accumulating multiple parts before fusing
- Use `LeaderFollowersCuttersPart` for complex assemblies with visual references
- Align parts relative to each other using the `align()` function with `Alignment` enums


### Avoid
- Do not use `collector.part` directly - treat collectors as parts themselves
- Do use as little translation offset calculations as possible - use align(), align(part, target, Alignment.STACK_RIGHT,stack_gap=-move_into_part) .. patterns wherever possible
- Do not catch exceptions - let scripts fail fast on geometry errors
- Do not create ad-hoc test scripts - write proper pytest tests

## Testing

- Prefer creating proper pytest tests in `tests/` directory
- Run tests: `pytest` from repo root
- For visual verification: `./run.sh src/mege_ender_3v3ke_idex/designs/<design_file>.py`
- Production exports: `SHELLFORGEPY_PRODUCTION=1 ./run.sh <design_file>.py`

## Repository Layout

```
mege-ender-3v3ke-idex/
├── src/
│   └── mege_ender_3v3ke_idex/
│       └── designs/
│           ├── alu_extrusion_profile.py  # T-slot extrusion profiles
│           ├── extruder.py               # Extruder mounting
│           ├── gt2belt.py                # Belt/pulley components
│           ├── nema_motors.py            # Stepper motor models
│           ├── x_axis.py                 # X-axis assembly (main)
│           └── jury_rigged_z_carriage.py # Z-axis components
├── resources/
│   └── *.step                           # Reference CAD files (OEM parts)
├── runs/
│   └── <timestamp>/                     # Generated STL/OBJ exports
└── tests/                               # Unit tests
```

## Common Tasks

### Running Design Scripts

```bash
# Development mode (all parts, colored)
./run.sh src/mege_ender_3v3ke_idex/designs/x_axis.py

# Production mode (printable parts only)
SHELLFORGEPY_PRODUCTION=1 ./run.sh src/mege_ender_3v3ke_idex/designs/x_axis.py
```

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
- Install with: `pip install -e ".[testing]"` for development
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
