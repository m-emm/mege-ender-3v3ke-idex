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
    input_label,
    plus_label,
    minus_label,
):
    v5 = placed_node(
        Dot, f"{prefix}_v5", "+5V rail", LOW_SIDE_INPUT_X, y, Alignment.LEFT
    )
    plus = placed_node(Dot, f"{prefix}_plus", plus_label, 4.0, y, Alignment.RIGHT)
    minus = placed_node(
        Dot,
        f"{prefix}_minus",
        minus_label,
        LOW_SIDE_TRANSISTOR_X,
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
    gnd = placed_node(
        Ground,
        f"{prefix}_gnd",
        "GND rail",
        LOW_SIDE_TRANSISTOR_X,
        y + LOW_SIDE_GROUND_OFFSET_Y,
        Alignment.RIGHT,
    )

    plus_feed = create_element(Wire, "", None, v5, plus)
    plus_feed = place(horizontal(plus_feed), 2.0, y)

    transistor = create_element(
        BjtNpn,
        refdes["transistor"],
        TRANSISTOR_TYPE,
        base=base,
        collector=minus,
        emitter=gnd,
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
        gnd,
    )
    pulldown = place(pulldown, LOW_SIDE_BASE_X, y - 4.7, Alignment.RIGHT)

    return (
        [v5, plus, minus, gpio, base, gnd],
        [plus_feed, transistor, base_resistor, pulldown],
    )


def create_enable_channel():
    y = -6.0
    v24 = placed_node(Dot, "ena_v24", "+24V", 0.0, y, Alignment.LEFT)
    ena_plus = placed_node(Dot, "ena_plus", "ENA+", 5.0, y - 1.0, Alignment.TOP)
    ena_minus = placed_node(Ground, "ena_minus", "ENA-", 8.8, y - 7.0)
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
        emitter=ena_minus,
    )
    transistor = place(transistor, 8.8, y - 5.2, Alignment.RIGHT)

    base_resistor = create_element(Resistor, "R7", "2k2", gpio, base)
    base_resistor = place(horizontal(base_resistor), 3.0, y - 4.6, Alignment.TOP)

    pulldown = create_element(Resistor, "R8", "47k", base, ena_minus)
    pulldown = place(pulldown, LOW_SIDE_BASE_X, y - 6.1, Alignment.RIGHT)

    return (
        [v24, ena_plus, ena_minus, gpio, base],
        [feed_a, feed_b, transistor, base_resistor, pulldown],
    )


def create_decoupling():
    v5 = placed_node(Dot, "decouple_v5", "+5V rail", 11.5, 4.0, Alignment.LEFT)
    gnd = placed_node(Ground, "decouple_gnd", "GND rail", 11.5, 0.6, Alignment.RIGHT)
    capacitor = create_element(Capacitor, "C1", "100nF", v5, gnd)
    capacitor = place(capacitor, 11.5, 2.3, Alignment.RIGHT)
    return [v5, gnd], [capacitor]


def create_schema_for_tb6600_interface():
    nodes = []
    elements = []

    for channel in [
        create_low_side_channel(
            refdes=REFDES[0],
            prefix="STEP",
            y=9.0,
            input_label="Pico STEP GPIO0",
            plus_label="PUL+",
            minus_label="PUL-",
        ),
        create_low_side_channel(
            refdes=REFDES[1],
            prefix="DIR",
            y=1.0,
            input_label="Pico DIR GPIO1",
            plus_label="DIR+",
            minus_label="DIR-",
        ),
        create_enable_channel(),
        create_decoupling(),
    ]:
        channel_nodes, channel_elements = channel
        nodes.extend(channel_nodes)
        elements.extend(channel_elements)

    return create_schema(nodes, elements)


def main():
    DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)
    schema = create_schema_for_tb6600_interface()
    for output_file in (SVG_FILE, PNG_FILE):
        render_schemdraw(schema, file=output_file)
        print(f"Wrote {output_file}")


if __name__ == "__main__":
    main()
