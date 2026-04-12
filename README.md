# mege-ender-3v3ke-idex

IDEX (independent dual extruder) extension for the Creality Ender 3V3 KE, modeled in ShellForgePy for fast printable iterations of mounts, plates, and hardware interfaces.

Status: work in progress—early infrastructure parts only; detailed content and assemblies are still to come.

## Purpose
- Design and validate the mechanical pieces for the Ender 3V3 KE IDEX conversion.
- Provide quick CAD previews and exportable STLs/OBJs for printing and fit checks.

## Quick Start
- Install for development: `pip install -e ".[testing]"`
- Run design scripts from the repo root with `./run.sh <path/to/script.py>`; exports land in `runs/<timestamp>/`.
- Prefer the builder workflow for assemblies: `python -m shellforgepy build assembling/assemblies/assemblies.yaml --assembly <assembly_name> --visualize`

## Assembly Builder
- Use `assembling/assemblies/assemblies.yaml` as the top-level builder entrypoint.
- Prefer per-assembly `*_assembly.yaml` manifests over directly running the Python generator when the assembly already exists in the builder graph.
- Do not import one assembly generator module from another module under `src/mege_ender_3v3ke_idex/designs/assemblies/` and call it inside the downstream generator. That hides dependencies from the builder and has already caused incorrect parameter passing and stale cache invalidation.
- The correct pattern is: create a `*_assembly.yaml` for the reusable assembly, declare it as a dependency in the downstream assembly YAML, and consume the injected dependency in the downstream Python generator.
- Production slicing runs can be launched directly from the CLI, including opening the slicer UI for inspection.

Example production run for the print bed undercarriage adjustment wheel plate:

```bash
( cd /Users/mege/git/mege-ender-3v3ke-idex ; python -m shellforgepy build assembling/assemblies/assemblies.yaml --assembly print_bed_undercarriage_assembly --production --slice --visualize --open --plate adjustment_wheel_single )
```

This builds the `print_bed_undercarriage_assembly`, selects the `adjustment_wheel_single` production plate, slices it, visualizes it, and opens the slicer GUI.

## Demos
- **Extrusion profile (T-slot) demo:** build 2020/4040 profiles with aligned T-slot cutters  
  `./run.sh src/mege_ender_3v3ke_idex/designs/alu_extrusion_profile.py`  
  Outputs: `alu_extrusion_profile_2020.stl` and `alu_extrusion_profile_4040.stl` in the run folder.
- **NEMA motor demo:** visualize NEMA14/17/23/34 bodies and a plate cut with NEMA17 clearances  
  `./run.sh src/mege_ender_3v3ke_idex/designs/nema_motors.py`

## Klipper Configuration

The project includes Klipper configuration files for the IDEX conversion. Deployment uses a git-based workflow:

```bash
# On the Klipper Raspberry Pi
ssh pi@menderpi.local
cd ~/mege-ender-3v3ke-idex
git pull
./klipper_setup/klipper_config/install_printer_cfg.sh
sudo systemctl restart klipper
```

Configuration files are tracked in git under `klipper_setup/klipper_config/` and use descriptive names reflecting the hardware state (e.g., `toolhead_nitehawk_and_x_axis.cfg`). The install script deploys them as `printer.cfg` on the Raspberry Pi.

See `AGENTS.md` for detailed deployment workflow and configuration naming conventions.

## Development
- Tests: `pytest`
- License: see `LICENSE.txt`
