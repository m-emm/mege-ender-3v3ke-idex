# Circuit Schematics

This package contains a small alignment-first DSL for drawing circuit
schematics with Schemdraw. It follows the same value-style layout feel as the
ShellForgePy geometry scripts in this repository: create nodes and elements,
place them with `align`, `translate`, and `rotate`, then render the resulting
schema.

Use it for lightweight circuit diagrams that should live beside the printer
hardware and wiring work. For connector pin maps and harness views, keep using
the `mege_ender_3v3ke_idex.pinout` tools.

## Quick Start

```python
from pathlib import Path

from mege_ender_3v3ke_idex.circuit_schematics.simple import *


def create_voltage_divider():
    vcc = create_node(Dot, "vcc", label="+5V")
    midpoint = create_node(Dot, "midpoint", label="OUT")
    gnd = create_node(Ground, "gnd")

    r1 = create_element(Resistor, "R1", "10K", vcc, midpoint)
    r2 = create_element(Resistor, "R2", "20K", midpoint, gnd)

    r1 = align(r1, vcc, Alignment.CENTER)
    r1 = align(r1, vcc, Alignment.STACK_BOTTOM)
    midpoint = align(midpoint, r1, Alignment.BOTTOM)

    r2 = align(r2, midpoint, Alignment.CENTER)
    r2 = align(r2, midpoint, Alignment.TOP)
    gnd = align(gnd, r2.end, Alignment.CENTER)
    gnd = align(gnd, r2, Alignment.BOTTOM)

    return create_schema([vcc, midpoint, gnd], [r1, r2])


schema = create_voltage_divider()
render_schemdraw(schema, file=Path("voltage_divider.svg"))
```

Use a `.png` filename instead of `.svg` to render a PNG preview:

```python
render_schemdraw(schema, file=Path("voltage_divider.png"))
```

Rails are visible materializations of normal nodes. They are useful when many
connections should visibly share one supply or ground rail:

```python
vcc = create_node(Dot, "vcc", label="+5V", label_alignment=Alignment.LEFT)
vcc = translate(0, 4)(vcc)
vcc = create_rail(vcc, Direction.VERTICAL, 8, anchor=Alignment.TOP)

pul_plus = create_node(Dot, "pul_plus", label="PUL+")
pul_plus = translate(4, 1)(pul_plus)

feed = create_element(Wire, "", None, vcc, pul_plus)
```

Run an example from the repository root:

```bash
src/mege_ender_3v3ke_idex/circuit_schematics/run.sh \
  src/mege_ender_3v3ke_idex/circuit_schematics/examples/voltage_divider.py
```

The helper runs the script with the repository `src/` directory on
`PYTHONPATH`, finds the generated SVG next to the example, and opens it.

## Concepts

- Nodes are electrical connection points created with `create_node`.
- Use `label_alignment=Alignment.LEFT/RIGHT/TOP/BOTTOM` when creating labeled
  nodes whose labels should face a specific way.
- Rails are created from normal nodes with `create_rail`; connected terminals
  project onto the visible rail and render tap dots.
- Elements are connected to nodes with `create_element`.
- `Wire` is a direct conductor between two nodes and does not need placement.
- Layout is explicit and copy-returning: `align(...)`, `translate(...)`, and
  `rotate(...)` return placed copies.
- Schemas group nodes and elements with `create_schema`.
- `render_schemdraw` turns the schema into a Schemdraw-backed SVG or PNG based
  on the output filename extension.

Supported node types are `Dot` and `Ground`. Supported element types are
`Wire`, `Resistor`, `Fuse`, `Capacitor`, `PMos`, `BjtNpn`, and `Zener`.

See `ALIGNMENT_BASED_SCHEMDRAW.md` for the design notes behind the DSL.
