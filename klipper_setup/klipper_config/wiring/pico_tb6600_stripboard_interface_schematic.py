"""Render the planned Pico-to-TB6600 stripboard interface schematic."""

from pathlib import Path

from mege_ender_3v3ke_idex.circuit_schematics.simple import *


DIAGRAM_DIR = Path(__file__).with_name("diagrams")
SVG_FILE = DIAGRAM_DIR / "pico_tb6600_stripboard_interface.svg"
PNG_FILE = DIAGRAM_DIR / "pico_tb6600_stripboard_interface.png"


TRANSISTOR_TYPE = "BC337"

TERMINAL_PAIR_GAP = 1.2
CHANNEL_GAP = 6.8
ENABLE_TERMINAL_PAIR_GAP = 1.3

RAIL_TOP_TO_FIRST_TERMINAL_GAP = 1.8
V5_RAIL_LENGTH = RAIL_TOP_TO_FIRST_TERMINAL_GAP + TERMINAL_PAIR_GAP + CHANNEL_GAP
GND_RAIL_LENGTH = 23.8
V5_RAIL_TO_TERMINAL_GAP = 12.8
TERMINAL_TO_GND_RAIL_GAP = 2.2

TRANSISTOR_TO_TERMINAL_GAP = 0.95
COLLECTOR_TO_TERMINAL_GAP = 1.7
EMITTER_TO_RETURN_GAP = 1.1

PULLDOWN_TO_TRANSISTOR_GAP = 1.6
GPIO_TO_BASE_RESISTOR_GAP = 2.4

ENA_JUNCTION_TO_TERMINAL_GAP = 1.0
ENA_COLLECTOR_TO_PLUS_GAP = 3.5
ENA_FEED_TO_JUNCTION_GAP = 5.4
ENA_FEED_TOP_GAP = 0.8
PARALLEL_FEED_GAP = 0.5

DECOUPLING_TO_V5_RAIL_GAP = 4.0

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


def create_tb6600_nets():
    return {
        name: create_net(name)
        for name in [
            "v5",
            "gnd",
            "v24",
            "step_pul_minus",
            "step_base",
            "step_gpio",
            "dir_minus",
            "dir_base",
            "dir_gpio",
            "ena_plus",
            "ena_base",
            "ena_gpio",
        ]
    }


def create_terminal_stack(nets):
    pul_plus = create_node(
        Dot,
        "STEP_plus",
        net=nets["v5"],
        label="PUL+",
        label_alignment=Alignment.RIGHT,
    )

    pul_minus = create_node(
        Dot,
        "STEP_minus",
        net=nets["step_pul_minus"],
        label="PUL-",
        label_alignment=Alignment.RIGHT,
    )
    pul_minus = align(pul_minus, pul_plus, Alignment.CENTER)
    pul_minus = align(
        pul_minus,
        pul_plus,
        Alignment.STACK_BOTTOM,
        stack_gap=TERMINAL_PAIR_GAP,
    )

    dir_plus = create_node(
        Dot,
        "DIR_plus",
        net=nets["v5"],
        label="DIR+",
        label_alignment=Alignment.RIGHT,
    )
    dir_plus = align(dir_plus, pul_minus, Alignment.CENTER)
    dir_plus = align(dir_plus, pul_minus, Alignment.STACK_BOTTOM, stack_gap=CHANNEL_GAP)

    dir_minus = create_node(
        Dot,
        "DIR_minus",
        net=nets["dir_minus"],
        label="DIR-",
        label_alignment=Alignment.RIGHT,
    )
    dir_minus = align(dir_minus, dir_plus, Alignment.CENTER)
    dir_minus = align(
        dir_minus,
        dir_plus,
        Alignment.STACK_BOTTOM,
        stack_gap=TERMINAL_PAIR_GAP,
    )

    ena_plus = create_node(
        Dot,
        "ena_plus",
        net=nets["ena_plus"],
        label="ENA+",
        label_alignment=Alignment.TOP,
    )
    ena_plus = align(ena_plus, dir_minus, Alignment.CENTER)
    ena_plus = align(ena_plus, dir_minus, Alignment.STACK_BOTTOM, stack_gap=CHANNEL_GAP)

    ena_minus = create_node(
        Dot,
        "ena_minus",
        net=nets["gnd"],
        label="ENA-",
        label_alignment=Alignment.BOTTOM,
    )
    ena_minus = align(ena_minus, ena_plus, Alignment.CENTER)
    ena_minus = align(
        ena_minus,
        ena_plus,
        Alignment.STACK_BOTTOM,
        stack_gap=ENABLE_TERMINAL_PAIR_GAP,
    )

    return {
        "pul_plus": pul_plus,
        "pul_minus": pul_minus,
        "dir_plus": dir_plus,
        "dir_minus": dir_minus,
        "ena_plus": ena_plus,
        "ena_minus": ena_minus,
    }


def create_rails(terminals, nets):
    v5_rail = create_node(
        Dot,
        "v5_rail",
        net=nets["v5"],
        label="+5V rail",
        label_alignment=Alignment.LEFT,
    )
    v5_rail = create_rail(
        v5_rail,
        Direction.VERTICAL,
        V5_RAIL_LENGTH,
        anchor=Alignment.TOP,
    )
    v5_rail = align(
        v5_rail,
        terminals["pul_plus"],
        Alignment.STACK_LEFT,
        stack_gap=V5_RAIL_TO_TERMINAL_GAP,
    )
    v5_rail = align(
        point_at(v5_rail, Alignment.TOP),
        terminals["pul_plus"],
        Alignment.STACK_TOP,
        stack_gap=RAIL_TOP_TO_FIRST_TERMINAL_GAP,
    )

    gnd_rail = create_node(
        Ground,
        "gnd_rail",
        net=nets["gnd"],
        label="GND rail",
        label_alignment=Alignment.RIGHT,
    )
    gnd_rail = create_rail(
        gnd_rail,
        Direction.VERTICAL,
        GND_RAIL_LENGTH,
        anchor=Alignment.BOTTOM,
    )
    gnd_rail = align(
        gnd_rail,
        terminals["pul_plus"],
        Alignment.STACK_RIGHT,
        stack_gap=TERMINAL_TO_GND_RAIL_GAP,
    )
    gnd_rail = align(
        point_at(gnd_rail, Alignment.TOP),
        point_at(v5_rail, Alignment.TOP),
        Alignment.CENTER,
        axes=["y"],
    )

    return {"v5": v5_rail, "gnd": gnd_rail}


def create_low_side_channel(
    *,
    refdes,
    prefix,
    plus,
    minus,
    base_net,
    input_net,
    gnd_net,
    v5_rail,
    gnd_rail,
    input_label,
):
    base = create_node(Dot, f"{prefix}_base", net=base_net)
    gnd_junction = create_node(Dot, f"{prefix}_gnd_junction", net=gnd_net)

    transistor = create_element(
        BjtNpn,
        refdes["transistor"],
        TRANSISTOR_TYPE,
        base=base,
        collector=minus,
        emitter=gnd_junction,
    )
    transistor = align(
        transistor,
        minus,
        Alignment.STACK_LEFT,
        stack_gap=TRANSISTOR_TO_TERMINAL_GAP,
    )
    transistor = align(
        transistor.collector,
        minus,
        Alignment.STACK_BOTTOM,
        stack_gap=COLLECTOR_TO_TERMINAL_GAP,
    )
    transistor = modify_label_alignment(transistor, Alignment.RIGHT)

    gnd_junction = align(gnd_junction, transistor.emitter, Alignment.CENTER)
    gnd_junction = align(
        gnd_junction,
        transistor.emitter,
        Alignment.STACK_BOTTOM,
        stack_gap=EMITTER_TO_RETURN_GAP,
    )

    pulldown = create_element(
        Resistor,
        refdes["pulldown"],
        "47k",
        base,
        gnd_junction,
    )
    pulldown = align(
        pulldown,
        transistor,
        Alignment.STACK_LEFT,
        stack_gap=PULLDOWN_TO_TRANSISTOR_GAP,
    )
    pulldown = align(pulldown.start, transistor.base, Alignment.CENTER, axes=["y"])
    pulldown = modify_label_alignment(pulldown, Alignment.RIGHT)

    gpio = create_node(
        Dot,
        f"{prefix}_gpio",
        net=input_net,
        label=input_label,
        label_alignment=Alignment.LEFT,
    )
    base_resistor = create_element(
        Resistor,
        refdes["base"],
        "2k2",
        gpio,
        base,
    )
    base_resistor = rotate(90)(base_resistor)
    base_resistor = align(base_resistor.end, pulldown.start, Alignment.CENTER)
    base_resistor = modify_label_alignment(base_resistor, Alignment.TOP)

    gpio = align(gpio, base_resistor.start, Alignment.CENTER)
    gpio = align(
        gpio,
        base_resistor.start,
        Alignment.STACK_LEFT,
        stack_gap=GPIO_TO_BASE_RESISTOR_GAP,
    )

    return (
        [gpio, base, gnd_junction],
        [
            create_wire(v5_rail, plus),
            create_wire(gnd_junction, gnd_rail),
            transistor,
            base_resistor,
            pulldown,
        ],
    )


def create_enable_channel(terminals, nets, gnd_rail):
    v24 = create_node(
        Dot,
        "ena_v24",
        net=nets["v24"],
        label="+24V",
        label_alignment=Alignment.LEFT,
    )

    ena_plus_junction = create_node(
        Dot,
        "ena_plus_junction",
        net=nets["ena_plus"],
    )
    ena_plus_junction = align(
        ena_plus_junction,
        terminals["ena_plus"],
        Alignment.CENTER,
    )
    ena_plus_junction = align(
        ena_plus_junction,
        terminals["ena_plus"],
        Alignment.STACK_LEFT,
        stack_gap=ENA_JUNCTION_TO_TERMINAL_GAP,
    )

    base = create_node(Dot, "ena_base", net=nets["ena_base"])
    gnd_junction = create_node(Dot, "ena_gnd_junction", net=nets["gnd"])

    transistor = create_element(
        BjtNpn,
        "Q3",
        TRANSISTOR_TYPE,
        base=base,
        collector=ena_plus_junction,
        emitter=gnd_junction,
    )
    transistor = align(transistor.collector, ena_plus_junction, Alignment.CENTER)
    transistor = align(
        transistor.collector,
        ena_plus_junction,
        Alignment.STACK_BOTTOM,
        stack_gap=ENA_COLLECTOR_TO_PLUS_GAP,
    )
    transistor = modify_label_alignment(transistor, Alignment.RIGHT)

    gnd_junction = align(gnd_junction, transistor.emitter, Alignment.CENTER)
    gnd_junction = align(
        gnd_junction,
        transistor.emitter,
        Alignment.STACK_BOTTOM,
        stack_gap=EMITTER_TO_RETURN_GAP,
    )

    feed_a = create_element(Resistor, "R5", "4k7 0.25W", v24, ena_plus_junction)
    feed_a = rotate(90)(feed_a)
    feed_a = align(
        feed_a,
        ena_plus_junction,
        Alignment.STACK_LEFT,
        stack_gap=ENA_FEED_TO_JUNCTION_GAP,
    )
    feed_a = align(
        feed_a,
        ena_plus_junction,
        Alignment.STACK_TOP,
        stack_gap=ENA_FEED_TOP_GAP,
    )
    feed_a = modify_label_alignment(feed_a, Alignment.TOP)

    feed_b = create_element(Resistor, "R6", "4k7 0.25W", v24, ena_plus_junction)
    feed_b = rotate(90)(feed_b)
    feed_b = align(feed_b, feed_a, Alignment.CENTER, axes=["x"])
    feed_b = align(feed_b, feed_a, Alignment.STACK_BOTTOM, stack_gap=PARALLEL_FEED_GAP)
    feed_b = modify_label_alignment(feed_b, Alignment.BOTTOM)

    gpio = create_node(
        Dot,
        "ena_gpio",
        net=nets["ena_gpio"],
        label="Pico ENABLE GPIO2",
        label_alignment=Alignment.LEFT,
    )

    pulldown = create_element(Resistor, "R8", "47k", base, gnd_junction)
    pulldown = align(
        pulldown,
        transistor,
        Alignment.STACK_LEFT,
        stack_gap=PULLDOWN_TO_TRANSISTOR_GAP,
    )
    pulldown = align(pulldown.start, transistor.base, Alignment.CENTER, axes=["y"])
    pulldown = modify_label_alignment(pulldown, Alignment.RIGHT)

    base_resistor = create_element(Resistor, "R7", "2k2", gpio, base)
    base_resistor = rotate(90)(base_resistor)
    base_resistor = align(base_resistor.end, pulldown.start, Alignment.CENTER)
    base_resistor = modify_label_alignment(base_resistor, Alignment.TOP)

    gpio = align(gpio, base_resistor.start, Alignment.CENTER)
    gpio = align(
        gpio,
        base_resistor.start,
        Alignment.STACK_LEFT,
        stack_gap=GPIO_TO_BASE_RESISTOR_GAP,
    )

    return (
        [
            v24,
            ena_plus_junction,
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
            create_wire(ena_plus_junction, terminals["ena_plus"]),
            create_wire(gnd_rail, terminals["ena_minus"]),
            create_wire(gnd_junction, gnd_rail),
        ],
    )


def create_decoupling(v5_rail, gnd_rail):
    capacitor = create_element(Capacitor, "C1", "100nF", v5_rail, gnd_rail)
    capacitor = rotate(90)(capacitor)
    capacitor = align(
        capacitor,
        point_at(v5_rail, Alignment.TOP),
        Alignment.CENTER,
        axes=["y"],
    )
    capacitor = align(
        capacitor,
        point_at(v5_rail, Alignment.TOP),
        Alignment.STACK_RIGHT,
        stack_gap=DECOUPLING_TO_V5_RAIL_GAP,
    )
    capacitor = modify_label_alignment(capacitor, Alignment.BOTTOM)
    return [], [capacitor]


def create_schema_for_tb6600_interface():
    nets = create_tb6600_nets()
    terminals = create_terminal_stack(nets)
    rails = create_rails(terminals, nets)

    nodes = [*terminals.values(), *rails.values()]
    elements = []

    for channel_nodes, channel_elements in [
        create_low_side_channel(
            refdes=REFDES["STEP"],
            prefix="STEP",
            plus=terminals["pul_plus"],
            minus=terminals["pul_minus"],
            base_net=nets["step_base"],
            input_net=nets["step_gpio"],
            gnd_net=nets["gnd"],
            v5_rail=rails["v5"],
            gnd_rail=rails["gnd"],
            input_label="Pico STEP GPIO0",
        ),
        create_low_side_channel(
            refdes=REFDES["DIR"],
            prefix="DIR",
            plus=terminals["dir_plus"],
            minus=terminals["dir_minus"],
            base_net=nets["dir_base"],
            input_net=nets["dir_gpio"],
            gnd_net=nets["gnd"],
            v5_rail=rails["v5"],
            gnd_rail=rails["gnd"],
            input_label="Pico DIR GPIO1",
        ),
        create_enable_channel(terminals, nets, rails["gnd"]),
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
