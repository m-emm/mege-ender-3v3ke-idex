"""Render the planned Pico-to-TB6600 stripboard interface schematic."""

from pathlib import Path

from mege_ender_3v3ke_idex.circuit_schematics.simple import *


DIAGRAM_DIR = Path(__file__).with_name("diagrams")
SVG_FILE = DIAGRAM_DIR / "pico_tb6600_stripboard_interface.svg"
PNG_FILE = DIAGRAM_DIR / "pico_tb6600_stripboard_interface.png"


TRANSISTOR_TYPE = "BC337"

V5_RAIL_X = -3.0
V5_RAIL_TOP_Y = 10.8
V5_RAIL_BOTTOM_Y = 1.0
V5_RAIL_LENGTH = V5_RAIL_TOP_Y - V5_RAIL_BOTTOM_Y

GND_RAIL_X = 12.0
GND_RAIL_TOP_Y = 10.8
GND_RAIL_BOTTOM_Y = -13.0
GND_RAIL_LENGTH = GND_RAIL_TOP_Y - GND_RAIL_BOTTOM_Y

TB6600_TERMINAL_X = 9.8
LOW_SIDE_TRANSISTOR_X = 8.5
LOW_SIDE_BASE_X = 5.7
ENABLE_TRANSISTOR_X = 8.8

TERMINAL_PAIR_GAP = 1.2

STEP_LAYOUT = {
    "terminal_y": 9.0,
    "gpio_y": 5.8,
    "transistor_y": 5.4,
    "return_y": 3.2,
    "base_resistor_x": 3.0,
    "pulldown_y": 4.3,
}

DIR_LAYOUT = {
    "terminal_y": 1.0,
    "gpio_y": -2.2,
    "transistor_y": -2.6,
    "return_y": -4.8,
    "base_resistor_x": 3.0,
    "pulldown_y": -3.7,
}

ENA_LAYOUT = {
    "v24_y": -6.0,
    "plus_y": -7.0,
    "minus_y": -8.3,
    "gpio_y": -10.6,
    "transistor_y": -11.2,
    "return_y": -13.0,
    "feed_x": 2.4,
    "feed_a_y": -5.8,
    "feed_b_y": -7.9,
    "base_resistor_x": 3.0,
    "pulldown_y": -12.1,
}

REFDES = {
    "STEP": {
        "base": "R1",
        "pulldown": "R2",
        "transistor": "Q1",
    },
    "DIR": {
        "base": "R3",
        "pulldown": "R4",
        "transistor": "Q2",
    },
}


def create_low_side_channel(
    *,
    refdes,
    prefix,
    layout,
    v5_rail,
    gnd_rail,
    input_label,
    plus_label,
    minus_label,
):
    plus = create_node(
        Dot,
        f"{prefix}_plus",
        label=plus_label,
        label_alignment=Alignment.RIGHT,
    )
    plus = translate(TB6600_TERMINAL_X, layout["terminal_y"])(plus)

    minus = create_node(
        Dot,
        f"{prefix}_minus",
        label=minus_label,
        label_alignment=Alignment.RIGHT,
    )
    minus = align(minus, plus, Alignment.CENTER)
    minus = align(minus, plus, Alignment.STACK_BOTTOM, stack_gap=TERMINAL_PAIR_GAP)

    gpio = create_node(
        Dot,
        f"{prefix}_gpio",
        label=input_label,
        label_alignment=Alignment.LEFT,
    )
    gpio = translate(0.0, layout["gpio_y"])(gpio)

    base = create_node(Dot, f"{prefix}_base")

    gnd_junction = create_node(Dot, f"{prefix}_gnd_junction")
    gnd_junction = translate(LOW_SIDE_TRANSISTOR_X, layout["return_y"])(gnd_junction)

    plus_feed = create_element(Wire, "", None, v5_rail, plus)
    gnd_feed = create_element(Wire, "", None, gnd_junction, gnd_rail)

    transistor = create_element(
        BjtNpn,
        refdes["transistor"],
        TRANSISTOR_TYPE,
        base=base,
        collector=minus,
        emitter=gnd_junction,
    )
    transistor = translate(LOW_SIDE_TRANSISTOR_X, layout["transistor_y"])(transistor)
    transistor = modify_label_alignment(transistor, Alignment.RIGHT)

    base_resistor = create_element(
        Resistor,
        refdes["base"],
        "2k2",
        gpio,
        base,
    )
    base_resistor = rotate(90)(base_resistor)
    base_resistor = translate(layout["base_resistor_x"], layout["gpio_y"])(
        base_resistor
    )
    base_resistor = modify_label_alignment(base_resistor, Alignment.TOP)

    pulldown = create_element(
        Resistor,
        refdes["pulldown"],
        "47k",
        base,
        gnd_junction,
    )
    pulldown = translate(LOW_SIDE_BASE_X, layout["pulldown_y"])(pulldown)
    pulldown = modify_label_alignment(pulldown, Alignment.RIGHT)

    return (
        [plus, minus, gpio, base, gnd_junction],
        [plus_feed, gnd_feed, transistor, base_resistor, pulldown],
    )


def create_enable_channel(gnd_rail):
    v24 = create_node(Dot, "ena_v24", label="+24V", label_alignment=Alignment.LEFT)
    v24 = translate(0.0, ENA_LAYOUT["v24_y"])(v24)

    ena_plus_terminal = create_node(
        Dot,
        "ena_plus",
        label="ENA+",
        label_alignment=Alignment.TOP,
    )
    ena_plus_terminal = translate(TB6600_TERMINAL_X, ENA_LAYOUT["plus_y"])(
        ena_plus_terminal
    )

    ena_plus_junction = create_node(Dot, "ena_plus_junction")
    ena_plus_junction = translate(ENABLE_TRANSISTOR_X, ENA_LAYOUT["plus_y"])(
        ena_plus_junction
    )

    ena_minus = create_node(
        Dot,
        "ena_minus",
        label="ENA-",
        label_alignment=Alignment.BOTTOM,
    )
    ena_minus = translate(TB6600_TERMINAL_X, ENA_LAYOUT["minus_y"])(ena_minus)

    gpio = create_node(
        Dot,
        "ena_gpio",
        label="Pico ENABLE GPIO2",
        label_alignment=Alignment.LEFT,
    )
    gpio = translate(0.0, ENA_LAYOUT["gpio_y"])(gpio)

    base = create_node(Dot, "ena_base")

    gnd_junction = create_node(Dot, "ena_gnd_junction")
    gnd_junction = translate(ENABLE_TRANSISTOR_X, ENA_LAYOUT["return_y"])(gnd_junction)

    feed_a = create_element(Resistor, "R5", "4k7 0.25W", v24, ena_plus_junction)
    feed_a = rotate(90)(feed_a)
    feed_a = translate(ENA_LAYOUT["feed_x"], ENA_LAYOUT["feed_a_y"])(feed_a)
    feed_a = modify_label_alignment(feed_a, Alignment.TOP)

    feed_b = create_element(Resistor, "R6", "4k7 0.25W", v24, ena_plus_junction)
    feed_b = rotate(90)(feed_b)
    feed_b = translate(ENA_LAYOUT["feed_x"], ENA_LAYOUT["feed_b_y"])(feed_b)
    feed_b = modify_label_alignment(feed_b, Alignment.BOTTOM)

    transistor = create_element(
        BjtNpn,
        "Q3",
        TRANSISTOR_TYPE,
        base=base,
        collector=ena_plus_junction,
        emitter=gnd_junction,
    )
    transistor = translate(ENABLE_TRANSISTOR_X, ENA_LAYOUT["transistor_y"])(transistor)
    transistor = modify_label_alignment(transistor, Alignment.RIGHT)

    base_resistor = create_element(Resistor, "R7", "2k2", gpio, base)
    base_resistor = rotate(90)(base_resistor)
    base_resistor = translate(
        ENA_LAYOUT["base_resistor_x"],
        ENA_LAYOUT["gpio_y"],
    )(base_resistor)
    base_resistor = modify_label_alignment(base_resistor, Alignment.TOP)

    pulldown = create_element(Resistor, "R8", "47k", base, gnd_junction)
    pulldown = translate(LOW_SIDE_BASE_X, ENA_LAYOUT["pulldown_y"])(pulldown)
    pulldown = modify_label_alignment(pulldown, Alignment.RIGHT)

    ena_plus_wire = create_element(Wire, "", None, ena_plus_junction, ena_plus_terminal)
    ena_minus_wire = create_element(Wire, "", None, gnd_rail, ena_minus)
    gnd_feed = create_element(Wire, "", None, gnd_junction, gnd_rail)

    return (
        [
            v24,
            ena_plus_terminal,
            ena_plus_junction,
            ena_minus,
            gpio,
            base,
            gnd_junction,
        ],
        [
            feed_a,
            feed_b,
            transistor,
            base_resistor,
            pulldown,
            ena_plus_wire,
            ena_minus_wire,
            gnd_feed,
        ],
    )


def create_decoupling(v5_rail, gnd_rail):
    capacitor = create_element(Capacitor, "C1", "100nF", v5_rail, gnd_rail)
    capacitor = rotate(90)(capacitor)
    capacitor = translate(4.0, V5_RAIL_TOP_Y)(capacitor)
    capacitor = modify_label_alignment(capacitor, Alignment.BOTTOM)
    return [], [capacitor]


def create_rails():
    v5_rail = create_node(
        Dot,
        "v5_rail",
        label="+5V rail",
        label_alignment=Alignment.LEFT,
    )
    v5_rail = translate(V5_RAIL_X, V5_RAIL_TOP_Y)(v5_rail)
    v5_rail = create_rail(
        v5_rail,
        Direction.VERTICAL,
        V5_RAIL_LENGTH,
        anchor=Alignment.TOP,
    )

    gnd_rail = create_node(
        Ground,
        "gnd_rail",
        label="GND rail",
        label_alignment=Alignment.RIGHT,
    )
    gnd_rail = translate(GND_RAIL_X, GND_RAIL_BOTTOM_Y)(gnd_rail)
    gnd_rail = create_rail(
        gnd_rail,
        Direction.VERTICAL,
        GND_RAIL_LENGTH,
        anchor=Alignment.BOTTOM,
    )

    return [v5_rail, gnd_rail], [], {"v5": v5_rail, "gnd": gnd_rail}


def create_schema_for_tb6600_interface():
    nodes, elements, rails = create_rails()

    for channel_nodes, channel_elements in [
        create_low_side_channel(
            refdes=REFDES["STEP"],
            prefix="STEP",
            layout=STEP_LAYOUT,
            v5_rail=rails["v5"],
            gnd_rail=rails["gnd"],
            input_label="Pico STEP GPIO0",
            plus_label="PUL+",
            minus_label="PUL-",
        ),
        create_low_side_channel(
            refdes=REFDES["DIR"],
            prefix="DIR",
            layout=DIR_LAYOUT,
            v5_rail=rails["v5"],
            gnd_rail=rails["gnd"],
            input_label="Pico DIR GPIO1",
            plus_label="DIR+",
            minus_label="DIR-",
        ),
        create_enable_channel(rails["gnd"]),
        create_decoupling(rails["v5"], rails["gnd"]),
    ]:
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
