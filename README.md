# mege-ender-3v3ke-idex

IDEX (independent dual extruder) extension for the Creality Ender 3V3 KE, modeled in ShellForgePy for fast printable iterations of mounts, plates, and hardware interfaces.

Status: work in progress—early infrastructure parts only; detailed content and assemblies are still to come.

## Purpose
- Design and validate the mechanical pieces for the Ender 3V3 KE IDEX conversion.
- Provide quick CAD previews and exportable STLs/OBJs for printing and fit checks.

## Quick Start
- Install for development: `pip install -e ".[testing]"`
- Run design scripts from the repo root with `./run.sh <path/to/script.py>`; exports land in `runs/<timestamp>/`.

## Demos
- **Extrusion profile (T-slot) demo:** build 2020/4040 profiles with aligned T-slot cutters  
  `./run.sh src/mege_ender_3v3ke_idex/designs/alu_extrusion_profile.py`  
  Outputs: `alu_extrusion_profile_2020.stl` and `alu_extrusion_profile_4040.stl` in the run folder.
- **NEMA motor demo:** visualize NEMA14/17/23/34 bodies and a plate cut with NEMA17 clearances  
  `./run.sh src/mege_ender_3v3ke_idex/designs/nema_motors.py`

## Development
- Tests: `pytest`
- License: see `LICENSE.txt`
