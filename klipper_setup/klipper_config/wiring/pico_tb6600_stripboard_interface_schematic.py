"""Render the planned Pico-to-TB6600 stripboard interface schematic."""

from pathlib import Path

from mege_ender_3v3ke_idex.circuit_schematics.simple import *


DIAGRAM_DIR = Path(__file__).with_name("diagrams")
SVG_FILE = DIAGRAM_DIR / "pico_tb6600_stripboard_interface.svg"
PNG_FILE = DIAGRAM_DIR / "pico_tb6600_stripboard_interface.png"


LOW_SIDE_TRANSISTOR_X = 8.5
LOW_SIDE_INPUT_X = 0.0
LOW_SIDE_BASE_X = 5.7
LOW_SIDE_GROUND_OFFSET_Y = -5.8
TRANSISTOR_TYPE = "BC337"
V5_RAIL_X = -3.0
GND_RAIL_X = 12.0
TB6600_TERMINAL_X = 9.8

REFDES = (
    {
        "base": "R1",
        "pulldown": "R2",
        "transistor": "Q1",
    },
    {
        "base": "R3",
        "pulldown": "R4",
        "transistor": "Q2",
    },
)


def placed_node(node_type, name, label, x, y, alignment=Alignment.RIGHT):
    node = create_node(node_type, name, label=label)
    node = modify_label_alignment(node, alignment)
    return translate(x, y)(node)


def horizontal(element):
    return rotate(90)(element)


def wire_between(start, end):
    element = create_element(Wire, "", None, start, end)
    x1, y1 = start.position
    x2, y2 = end.position
    if abs(y1 - y2) < 1e-9:
        element = horizontal(element)
    return translate((x1 + x2) / 2.0, (y1 + y2) / 2.0)(element)


def place(element, x, y, label_alignment=None):
    element = translate(x, y)(element)
    if label_alignment is not None:
        element = modify_label_alignment(element, label_alignment)
    return element


def create_low_side_channel(
    *,
    refdes,
    prefix,
    y,
    v5_tap,
    gnd_tap,
    input_label,
    plus_label,
    minus_label,
):
    plus = placed_node(
        Dot, f"{prefix}_plus", plus_label, TB6600_TERMINAL_X, y, Alignment.RIGHT
    )
    minus = placed_node(
        Dot,
        f"{prefix}_minus",
        minus_label,
        TB6600_TERMINAL_X,
        y - 1.2,
        Alignment.RIGHT,
    )
    gpio = placed_node(
        Dot,
        f"{prefix}_gpio",
        input_label,
        LOW_SIDE_INPUT_X,
        y - 3.2,
        Alignment.LEFT,
    )
    base = create_node(Dot, f"{prefix}_base")

    plus_feed = wire_between(v5_tap, plus)

    transistor = create_element(
        BjtNpn,
        refdes["transistor"],
        TRANSISTOR_TYPE,
        base=base,
        collector=minus,
        emitter=gnd_tap,
    )
    transistor = place(
        transistor,
        LOW_SIDE_TRANSISTOR_X,
        y - 3.6,
        Alignment.RIGHT,
    )

    base_resistor = create_element(
        Resistor,
        refdes["base"],
        "2k2",
        gpio,
        base,
    )
    base_resistor = place(horizontal(base_resistor), 3.0, y - 3.2, Alignment.TOP)

    pulldown = create_element(
        Resistor,
        refdes["pulldown"],
        "47k",
        base,
        gnd_tap,
    )
    pulldown = place(pulldown, LOW_SIDE_BASE_X, y - 4.7, Alignment.RIGHT)

    return (
        [plus, minus, gpio, base],
        [plus_feed, transistor, base_resistor, pulldown],
    )


def create_enable_channel(gnd_tap, ena_minus_tap):
    y = -6.0
    v24 = placed_node(Dot, "ena_v24", "+24V", 0.0, y, Alignment.LEFT)
    ena_plus = placed_node(
        Dot, "ena_plus", "ENA+", TB6600_TERMINAL_X, y - 1.0, Alignment.TOP
    )
    ena_minus = placed_node(
        Dot, "ena_minus", "ENA-", TB6600_TERMINAL_X, y - 2.3, Alignment.BOTTOM
    )
    gpio = placed_node(
        Dot,
        "ena_gpio",
        "Pico ENABLE GPIO2",
        0.0,
        y - 4.6,
        Alignment.LEFT,
    )
    base = create_node(Dot, "ena_base")

    feed_a = create_element(Resistor, "R5", "4k7 0.25W", v24, ena_plus)
    feed_a = place(horizontal(feed_a), 2.4, y + 0.2, Alignment.TOP)

    feed_b = create_element(Resistor, "R6", "4k7 0.25W", v24, ena_plus)
    feed_b = place(horizontal(feed_b), 2.4, y - 1.9, Alignment.BOTTOM)

    transistor = create_element(
        BjtNpn,
        "Q3",
        TRANSISTOR_TYPE,
        base=base,
        collector=ena_plus,
        emitter=gnd_tap,
    )
    transistor = place(transistor, 8.8, y - 5.2, Alignment.RIGHT)

    base_resistor = create_element(Resistor, "R7", "2k2", gpio, base)
    base_resistor = place(horizontal(base_resistor), 3.0, y - 4.6, Alignment.TOP)

    pulldown = create_element(Resistor, "R8", "47k", base, gnd_tap)
    pulldown = place(pulldown, LOW_SIDE_BASE_X, y - 6.1, Alignment.RIGHT)

    ena_minus_wire = wire_between(ena_minus_tap, ena_minus)

    return (
        [v24, ena_plus, ena_minus, gpio, base],
        [feed_a, feed_b, transistor, base_resistor, pulldown, ena_minus_wire],
    )


def create_decoupling(v5_tap, gnd_tap):
    capacitor = create_element(Capacitor, "C1", "100nF", v5_tap, gnd_tap)
    capacitor = place(horizontal(capacitor), 4.0, 10.8, Alignment.BOTTOM)
    return [], [capacitor]


def create_rails():
    v5_top = placed_node(Dot, "v5_top", "+5V rail", V5_RAIL_X, 10.8, Alignment.LEFT)
    v5_step = placed_node(Dot, "v5_step", None, V5_RAIL_X, 9.0, Alignment.LEFT)
    v5_dir = placed_node(Dot, "v5_dir", None, V5_RAIL_X, 1.0, Alignment.LEFT)

    gnd_top = placed_node(Dot, "gnd_top", None, GND_RAIL_X, 10.8, Alignment.RIGHT)
    gnd_step = placed_node(Dot, "gnd_step", None, GND_RAIL_X, 3.2, Alignment.RIGHT)
    gnd_dir = placed_node(Dot, "gnd_dir", None, GND_RAIL_X, -4.8, Alignment.RIGHT)
    gnd_ena_minus = placed_node(
        Dot, "gnd_ena_minus", None, GND_RAIL_X, -8.3, Alignment.RIGHT
    )
    gnd_ena = placed_node(
        Ground, "gnd_ena", "GND rail", GND_RAIL_X, -13.0, Alignment.RIGHT
    )

    rail_nodes = [
        v5_top,
        v5_step,
        v5_dir,
        gnd_top,
        gnd_step,
        gnd_dir,
        gnd_ena_minus,
        gnd_ena,
    ]
    rail_elements = [
        wire_between(v5_top, v5_step),
        wire_between(v5_step, v5_dir),
        wire_between(gnd_top, gnd_step),
        wire_between(gnd_step, gnd_dir),
        wire_between(gnd_dir, gnd_ena_minus),
        wire_between(gnd_ena_minus, gnd_ena),
    ]
    return (
        rail_nodes,
        rail_elements,
        {
            "v5_top": v5_top,
            "v5_step": v5_step,
            "v5_dir": v5_dir,
            "gnd_top": gnd_top,
            "gnd_step": gnd_step,
            "gnd_dir": gnd_dir,
            "gnd_ena_minus": gnd_ena_minus,
            "gnd_ena": gnd_ena,
        },
    )


def create_schema_for_tb6600_interface():
    nodes, elements, rails = create_rails()

    for channel in [
        create_low_side_channel(
            refdes=REFDES[0],
            prefix="STEP",
            y=9.0,
            v5_tap=rails["v5_step"],
            gnd_tap=rails["gnd_step"],
            input_label="Pico STEP GPIO0",
            plus_label="PUL+",
            minus_label="PUL-",
        ),
        create_low_side_channel(
            refdes=REFDES[1],
            prefix="DIR",
            y=1.0,
            v5_tap=rails["v5_dir"],
            gnd_tap=rails["gnd_dir"],
            input_label="Pico DIR GPIO1",
            plus_label="DIR+",
            minus_label="DIR-",
        ),
        create_enable_channel(rails["gnd_ena"], rails["gnd_ena_minus"]),
        create_decoupling(rails["v5_top"], rails["gnd_top"]),
    ]:
        channel_nodes, channel_elements = channel
        nodes.extend(channel_nodes)
        elements.extend(channel_elements)

    return create_schema(nodes, elements)


def strip_trailing_whitespace(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(line.rstrip() for line in lines) + "\n", encoding="utf-8")


def main():
    DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)
    schema = create_schema_for_tb6600_interface()
    for output_file in (SVG_FILE, PNG_FILE):
        render_schemdraw(schema, file=output_file)
        if output_file.suffix == ".svg":
            strip_trailing_whitespace(output_file)
        print(f"Wrote {output_file}")


if __name__ == "__main__":
    main()
