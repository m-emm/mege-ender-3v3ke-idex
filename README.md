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

## Circuit Schematics

The alignment-first circuit drawing and stripboard preview DSL has moved to
the standalone open-source project
[`mege-circuits`](https://github.com/m-emm/mege-circuits).

The checked-in TB6600 interface diagrams in
`klipper_setup/klipper_config/wiring/diagrams/` are kept here as printer wiring
reference artifacts. Their source example now lives in `mege-circuits`.

## Klipper Configuration

The active Klipper configuration lives at `klipper_setup/klipper_config/printer.cfg`.
That file is the source of truth for the active printer. Everything under
`klipper_setup/klipper_config/archive/` is historical/reference material.
Active Pico/TMC wiring sources and generated SVG review artifacts live at
`klipper_setup/klipper_config/wiring/`.
The generic pinout renderer used for those wiring diagrams now lives in
[`mege-circuits`](https://github.com/m-emm/mege-circuits).

```bash
# From the local checkout
cd /Users/mege/git/mege-ender-3v3ke-idex/klipper_setup/klipper_config
python generate_printer_cfg.py --check
wiring/generate_wiring_svgs.sh --check
python wiring/validate_wiring.py
./update_menderpi.sh --check
./update_menderpi.sh
```

`./update_menderpi.sh --check` verifies the generated local config, the remote
file, and the active Klippy config without uploading files or restarting
Klipper.

The updater copies local `printer.cfg` to
`pi@menderpi.local:~/printer_data/config/printer.cfg`, backs up the previous
remote file, installs the custom Klipper host patch from
`klipper_setup/klipper_host/`, restarts Klipper, and prints the Klippy state.

The boosted heatbed uses the normal `[heater_bed]` object with the 24V bed on
`gpio21` and the SSR boost output on `gpio20`. Run the supervised calibration
helper before changing the bed to PID operation:

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex/klipper_setup/klipper_config
./calibrate_boosted_bed_pid.sh --target 80
```

See `AGENTS.md` for the detailed deployment workflow.

## Development
- Tests: `pytest`
- License: see `LICENSE.txt`
