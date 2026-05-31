# Pinout Config Format

The pinout CLI reads YAML (`.yaml`, `.yml`) or JSON config files and generates:
- top view SVG: `<basename>_top.svg`
- underside view SVG: `<basename>_bottom.svg`

## CLI usage

```bash
shellforgepy-pinout path/to/pinout.yaml -o output/
```

or

```bash
python -m mege_ender_3v3ke_idex.pinout path/to/pinout.yaml -o output/
```

Example:

```bash
shellforgepy-pinout \
  src/mege_ender_3v3ke_idex/pinout/examples/pico_w_btt_tmc2226.yaml \
  -o /tmp/pinout-demo
```

Options:
- `--basename NAME`: override output filename prefix
- `--top-only`: only write top view
- `--bottom-only`: only write underside view
- `--no-routing`: disable waypoint routing
- `--verbose`: print routing decisions

## YAML example

```yaml
basename: headmask_pinout

metadata:
  version_label: v1.2
  svg_margins_px:
    left: 24
    right: 20
    top: 20
    bottom: 24
  notes: |
    Diode: 1N5819 Schottky.
    Compass: QMC5883L.

color_map:
  power: "#d62728"
  ground: "#111111"
  clock: "#1f77b4"
  data: "#f2c94c"
  default: "#808080"

pin_sets:
  - prefix: xiao_
    origin: [0, 7]
    direction: up
    pins: [d6, d5, d4, d3, d2, d1, d0]
  - prefix: xiao_
    origin: [6, 7]
    direction: up
    pins: [d7, d8, d9, d10, "3v3", gnd, "5v"]
  - prefix: ls_
    origin: [0, 0]
    direction: up
    pins: [lv4, lv3, ls_gnd, lv, lv2, lv1]
  - prefix: ls_
    origin: [4, 0]
    direction: up
    pins: [hv4, hv3, gnd_hv, hv, hv2, hv1]

pins:
  dotstar_vcc: [7, 7]
  dotstar_clk: [7, 8]
  dotstar_di: [7, 9]
  dotstar_gnd: [7, 10]
  power_gnd: [7, 11]
  power_5v: [7, 12]
  power_diode_5v: [9, 12]
  compass_vcc: [20, 5]
  compass_gnd: [20, 4]
  compass_scl: [20, 3]
  compass_sda: [20, 2]

wires:
  - from: xiao_d8
    to: ls_lv1
    type: clock
  - from: xiao_d10
    to: ls_lv2
    type: data
  - from: xiao_3v3
    to: ls_lv
    type: power
  - from: power_gnd
    to: compass_gnd
    type: ground
  - from: xiao_d5
    to: compass_scl
    type: clock
  - from: xiao_d4
    to: compass_sda
    color: "#00b894"
```

## Schema summary

- `basename` (optional): output filename prefix (default `pinout`)
- `metadata.version_label` (optional): shown in SVG corner
- `metadata.notes` (optional): multiline notes shown in SVG corner
- `metadata.svg_margins_px` (optional): SVG pixel margins around rendered content.
  Use either one number for all sides or a `left`/`right`/`top`/`bottom` mapping.
  Defaults to `20`.
- `color_map` (optional): wire type to color mapping
- `pin_sets` (optional): repeated linear pin definitions
  - `origin`: `[x, y]` start coordinate
  - `pins` or `names`: list of pin names in sequence
  - `prefix` (optional): prepended to every pin name
  - `direction` (optional): `up`, `down`, `left`, or `right` (default `up`)
  - `step` (optional): spacing between consecutive pins (default `1`)
- `pins` (optional): explicit pin coordinates map (`name: [x, y]`)
- `wires` or `connections` (required): list of connections
  - `from`, `to` (required)
  - `type` or `kind` (optional, default `default`)
  - `color` (optional): explicit wire color override

Notes:
- At least one of `pin_sets` or `pins` must be provided.
- Duplicate pin names are rejected.
- Every `from` and `to` pin must exist.
