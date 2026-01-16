# mege-ender-3v3ke-idex

Add a short description here!

## Installation

```bash
pip install mege-ender-3v3ke-idex
```

## Usage

```python
import mege_ender_3v3ke_idex

# Your code here
```

## NEMA Motor Demo (ShellForgePy)

Visualize all NEMA sizes (14/17/23/34) side-by-side and a plate cut with a NEMA17 clearance:

```bash
cd mege-ender-3v3ke-idex
./run.sh src/mege_ender_3v3ke_idex/designs/nema_motors.py
```

Artifacts land in `runs/<timestamp>/`:
- `nema_motors_motor_visual_0..3.stl`: fused leaders+followers for NEMA14/17/23/34
- `nema_motors_demo_plate_cut.stl`: plate with NEMA17 holes cut using `use_as_cutter_on`
- `nema_motors.stl`/`.obj`: combined export for quick viewing

## Development

### Setup

```bash
git clone <your-repo-url>
cd mege-ender-3v3ke-idex
pip install -e ".[testing]"
```

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black src/ tests/
isort src/ tests/
```

## License

See LICENSE.txt for details.
