"""Render the TMC5160T Plus driver-before-logic sequencing schematic."""

import logging
from pathlib import Path
import re

from mege_circuits.simple import *

_logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path(__file__).with_name("diagrams")
SCHEMATIC_ARTIFACT_STEM = "tmc5160t_plus_power_sequencing"

IDEX_KIND_COLOR_MAP = {
    "power": "#ff0000",
    "hazard_power": "#8b4513",
    "lv_power": "#9ca3af",
    "ground": "#000000",
    "power_good": "#0057d8",
    "clock": "#0057d8",
    "data": "#d9a900",
    "control": "#7c3aed",
    "return": "#00838f",
    "default": "#4b5563",
}

SCHEMATIC_JUNCTION = "schematic_junction"

DETECTOR_INPUT_GAP = 0.9
D1_PACKAGE_GAP = 0.7
LOCAL_GROUND_GAP = 0.55

Q1_CONTROL_GAP = 2.1
Q1_BASE_PULLUP_GAP = 0.55
VIO_TO_GROUND_GAP = 4.8
VIO_SHUNT_GAP = 2.2

BUFFER_FROM_VIO_GAP = 8.0
BUFFER_NODE_GAP = 0.9
BUFFER_PULLUP_GAP = 0.7
BUFFER_RAIL_LENGTH = 8.4
RETURN_ROW_GAP = 2.4

VBUS_RAIL_LENGTH = 3.1
VIO_RAIL_LENGTH = 8.0
VIO_GROUND_RAIL_LENGTH = 8.0

BUFFER_CHANNELS = (
    ("step", "GPIO0", "STEP", "R7", "R13", "4.7 kohm"),
    ("dir", "GPIO1", "DIR", "R8", "R14", "4.7 kohm"),
    (
        "enable",
        "GPIO2",
        "ENABLE_N",
        "R9",
        "R15",
        "4.7 kohm",
    ),
    ("cs", "GPIO9", "CS_N", "R10", "R16", "2.2 kohm"),
    ("sclk", "GPIO10", "SCLK", "R11", "R17", "2.2 kohm"),
    ("mosi", "GPIO11", "MOSI", "R12", "R18", "2.2 kohm"),
)


def create_tmc5160t_plus_nets():
    net_kinds = {
        "switched_24v": "hazard_power",
        "detector_after_r1": "hazard_power",
        "detector_pin1": "hazard_power",
        "detector_led_link": "hazard_power",
        "gnd": "ground",
        "u2a_collector": "default",
        "q1_base": "default",
        "pico_vbus": "power",
        "q1_collector": "power",
        "tmc_vio": "power",
        "pico_3v3": "lv_power",
        "power_good": "power_good",
        "pico_step": "clock",
        "tmc_step": "clock",
        "pico_dir": "data",
        "tmc_dir": "data",
        "pico_enable": "control",
        "tmc_enable": "control",
        "pico_cs": "control",
        "tmc_cs": "control",
        "pico_sclk": "clock",
        "tmc_sclk": "clock",
        "pico_mosi": "data",
        "tmc_mosi": "data",
        "tmc_miso": "return",
        "pico_miso": "return",
        "tmc_diag1": "return",
        "pico_diag1": "return",
    }
    return {name: create_net(name, kind=kind) for name, kind in net_kinds.items()}


def create_tmc5160t_plus_power_sequencing_schema():
    nets = create_tmc5160t_plus_nets()

    u2_pin1 = create_node(
        Dot,
        "u2_pin1",
        net=nets["detector_pin1"],
        label="pin 1",
        label_alignment=Alignment.TOP,
    )
    u2_pin2 = create_node(
        Dot,
        "u2_pin2",
        net=nets["detector_led_link"],
        label="pins 2-4 linked",
        label_alignment=Alignment.LEFT,
    )
    u2_pin4 = create_node(
        Dot,
        "u2_pin4",
        net=nets["detector_led_link"],
        kind=SCHEMATIC_JUNCTION,
    )
    u2_pin3 = create_node(
        Dot,
        "u2_pin3",
        net=nets["gnd"],
        label="pin 3",
        label_alignment=Alignment.LEFT,
    )
    u2_pin7 = create_node(
        Dot,
        "u2_pin7",
        net=nets["u2a_collector"],
        label="pin 7",
        label_alignment=Alignment.TOP,
    )
    u2_pin8 = create_node(
        Dot,
        "u2_pin8",
        net=nets["gnd"],
        label="pin 8",
        label_alignment=Alignment.TOP,
    )
    u2_pin6 = create_node(
        Dot,
        "u2_pin6",
        net=nets["power_good"],
        label="pin 6",
        label_alignment=Alignment.BOTTOM,
    )
    u2_pin5 = create_node(
        Dot,
        "u2_pin5",
        net=nets["gnd"],
        label="pin 5",
        label_alignment=Alignment.TOP,
    )

    u2 = create_element(
        DualOptocoupler,
        "U2",
        "ILD74",
        a_anode=u2_pin1,
        a_cathode=u2_pin2,
        a_collector=u2_pin7,
        a_emitter=u2_pin8,
        b_anode=u2_pin4,
        b_cathode=u2_pin3,
        b_collector=u2_pin6,
        b_emitter=u2_pin5,
    )
    u2 = modify_label_alignment(u2, Alignment.TOP)

    u2_pin1 = align(u2_pin1, u2.a_anode, Alignment.CENTER)
    u2_pin2 = align(u2_pin2, u2.a_cathode, Alignment.CENTER)
    u2_pin4 = align(u2_pin4, u2.b_anode, Alignment.CENTER)
    u2_pin3 = align(u2_pin3, u2.b_cathode, Alignment.CENTER)
    u2_pin7 = align(u2_pin7, u2.a_collector, Alignment.CENTER)
    u2_pin8 = align(u2_pin8, u2.a_emitter, Alignment.CENTER)
    u2_pin6 = align(u2_pin6, u2.b_collector, Alignment.CENTER)
    u2_pin5 = align(u2_pin5, u2.b_emitter, Alignment.CENTER)

    pin3_ground = create_node(
        Ground,
        "pin3_ground",
        net=nets["gnd"],
    )
    pin3_ground = align(
        pin3_ground,
        u2_pin3,
        Alignment.STACK_BOTTOM,
        stack_gap=LOCAL_GROUND_GAP,
    )
    pin3_ground = align(pin3_ground, u2_pin3, Alignment.CENTER, axes=["x"])

    pin8_ground = create_node(
        Ground,
        "pin8_ground",
        net=nets["gnd"],
    )
    pin8_ground = align(
        pin8_ground,
        u2_pin8,
        Alignment.STACK_BOTTOM,
        stack_gap=LOCAL_GROUND_GAP,
    )
    pin8_ground = align(pin8_ground, u2_pin8, Alignment.CENTER, axes=["x"])

    pin5_ground = create_node(
        Ground,
        "pin5_ground",
        net=nets["gnd"],
    )
    pin5_ground = align(
        pin5_ground,
        u2_pin5,
        Alignment.STACK_BOTTOM,
        stack_gap=LOCAL_GROUND_GAP,
    )
    pin5_ground = align(pin5_ground, u2_pin5, Alignment.CENTER, axes=["x"])

    d1_anode = create_node(
        Dot,
        "d1_anode",
        net=nets["gnd"],
        kind=SCHEMATIC_JUNCTION,
    )
    d1_cathode = create_node(
        Dot,
        "d1_cathode",
        net=nets["detector_pin1"],
        kind=SCHEMATIC_JUNCTION,
    )
    d1 = create_element(Diode, "D1", "1N4148 antiparallel", d1_anode, d1_cathode)
    d1 = rotate(180)(d1)
    d1 = align(d1, u2, Alignment.STACK_LEFT, stack_gap=D1_PACKAGE_GAP)
    d1 = align(d1, u2, Alignment.CENTER, axes=["y"])
    d1 = modify_label_alignment(d1, Alignment.BOTTOM)
    d1_anode = align(d1_anode, d1.start, Alignment.CENTER)
    d1_cathode = align(d1_cathode, d1.end, Alignment.CENTER)

    d1_anode_tap = create_node(
        Dot,
        "d1_anode_tap",
        net=nets["gnd"],
        kind=SCHEMATIC_JUNCTION,
    )
    d1_anode_tap = align(d1_anode_tap, d1_anode, Alignment.CENTER, axes=["x"])
    d1_anode_tap = align(d1_anode_tap, u2_pin3, Alignment.CENTER, axes=["y"])

    d1_cathode_tap = create_node(
        Dot,
        "d1_cathode_tap",
        net=nets["detector_pin1"],
        kind=SCHEMATIC_JUNCTION,
    )
    d1_cathode_tap = align(
        d1_cathode_tap,
        d1_cathode,
        Alignment.CENTER,
        axes=["x"],
    )
    d1_cathode_tap = align(
        d1_cathode_tap,
        u2_pin1,
        Alignment.CENTER,
        axes=["y"],
    )

    detector_after_r1 = create_node(
        Dot,
        "detector_after_r1",
        net=nets["detector_after_r1"],
        kind=SCHEMATIC_JUNCTION,
    )
    dz1 = create_element(
        Zener,
        "DZ1",
        "12 V / 0.5 W",
        u2_pin1,
        detector_after_r1,
    )
    dz1 = rotate(-90)(dz1)
    dz1 = align(dz1.start, u2_pin1, Alignment.CENTER)
    dz1 = modify_label_alignment(dz1, Alignment.TOP)
    detector_after_r1 = align(detector_after_r1, dz1.end, Alignment.CENTER)

    switched_24v = create_node(
        Dot,
        "switched_24v",
        net=nets["switched_24v"],
        label="+24V_SW",
        label_alignment=Alignment.LEFT,
    )
    r1 = create_element(
        Resistor,
        "R1",
        "620 ohm / 0.5 W",
        switched_24v,
        detector_after_r1,
    )
    r1 = rotate(90)(r1)
    r1 = align(r1.end, detector_after_r1, Alignment.CENTER)
    r1 = modify_label_alignment(r1, Alignment.BOTTOM)
    switched_24v = align(
        switched_24v,
        r1.start,
        Alignment.STACK_LEFT,
        stack_gap=DETECTOR_INPUT_GAP,
    )
    switched_24v = align(switched_24v, r1.start, Alignment.CENTER, axes=["y"])

    power_good = create_node(
        Dot,
        "power_good",
        net=nets["power_good"],
        kind=SCHEMATIC_JUNCTION,
    )
    power_good = align(
        power_good,
        u2_pin6,
        Alignment.STACK_RIGHT,
        stack_gap=Q1_CONTROL_GAP,
    )
    power_good = align(power_good, u2_pin6, Alignment.CENTER, axes=["y"])

    power_good_gpio = create_node(
        Dot,
        "power_good_gpio",
        net=nets["power_good"],
        label="PWR_OK_N -> y_pico:gpio5\nactive-low: LOW = +24V_SW valid",
        label_alignment=Alignment.RIGHT,
    )
    power_good_gpio = align(
        power_good_gpio,
        power_good,
        Alignment.STACK_BOTTOM,
        stack_gap=1.4,
    )
    power_good_gpio = align(
        power_good_gpio,
        power_good,
        Alignment.CENTER,
        axes=["x"],
    )

    pico_3v3_power_good = create_node(
        Dot,
        "pico_3v3_power_good",
        net=nets["pico_3v3"],
        label="PICO_3V3",
        label_alignment=Alignment.TOP,
    )
    r6 = create_element(
        Resistor,
        "R6",
        "4.7 kohm",
        pico_3v3_power_good,
        power_good_gpio,
    )
    r6 = align(r6.end, power_good_gpio, Alignment.CENTER)
    r6 = modify_label_alignment(r6, Alignment.RIGHT)
    pico_3v3_power_good = align(
        pico_3v3_power_good,
        r6.start,
        Alignment.STACK_TOP,
        stack_gap=0.6,
    )
    pico_3v3_power_good = align(
        pico_3v3_power_good,
        r6.start,
        Alignment.CENTER,
        axes=["x"],
    )

    q1_base = create_node(
        Dot,
        "q1_base",
        net=nets["q1_base"],
        kind=SCHEMATIC_JUNCTION,
    )
    r3 = create_element(
        Resistor,
        "R3",
        "2.7 kohm",
        u2_pin7,
        q1_base,
    )
    r3 = rotate(90)(r3)
    r3 = align(
        r3,
        u2,
        Alignment.STACK_RIGHT,
        stack_gap=Q1_CONTROL_GAP,
    )
    r3 = align(r3.start, u2_pin7, Alignment.CENTER, axes=["y"])
    r3 = modify_label_alignment(r3, Alignment.BOTTOM)
    q1_base = align(q1_base, r3.end, Alignment.CENTER)

    pico_vbus_rail = create_node(
        Dot,
        "pico_vbus_rail",
        net=nets["pico_vbus"],
        label="PICO_VBUS_5V  RP2040-Plus pin 40",
        label_alignment=Alignment.TOP,
    )
    pico_vbus_rail = create_rail(
        pico_vbus_rail,
        Direction.HORIZONTAL,
        VBUS_RAIL_LENGTH,
    )
    q1_collector = create_node(
        Dot,
        "q1_collector",
        net=nets["q1_collector"],
        kind=SCHEMATIC_JUNCTION,
    )
    q1 = create_element(
        BjtPnp,
        "Q1",
        "BC327 PNP",
        base=q1_base,
        collector=q1_collector,
        emitter=pico_vbus_rail,
    )
    q1 = align(q1.base, q1_base, Alignment.CENTER)
    q1 = modify_label_alignment(q1, Alignment.RIGHT)
    q1_collector = align(q1_collector, q1.collector, Alignment.CENTER)

    pico_vbus_rail = align(
        pico_vbus_rail,
        q1,
        Alignment.STACK_TOP,
        stack_gap=Q1_BASE_PULLUP_GAP,
    )
    pico_vbus_rail = align(
        point_at(pico_vbus_rail, Alignment.RIGHT),
        q1.emitter,
        Alignment.CENTER,
        axes=["x"],
    )

    r2 = create_element(
        Resistor,
        "R2",
        "47 kohm",
        pico_vbus_rail,
        q1_base,
    )
    r2 = align(r2.end, q1_base, Alignment.CENTER)
    r2 = modify_label_alignment(r2, Alignment.LEFT)

    tmc_vio_rail = create_node(
        Dot,
        "tmc_vio_rail",
        net=nets["tmc_vio"],
    )
    tmc_vio_rail = create_rail(
        tmc_vio_rail,
        Direction.HORIZONTAL,
        VIO_RAIL_LENGTH,
        anchor=Alignment.LEFT,
    )
    r4 = create_element(
        Resistor,
        "R4",
        "39 ohm / 0.5 W",
        q1_collector,
        tmc_vio_rail,
    )
    r4 = align(r4.start, q1_collector, Alignment.CENTER)
    r4 = modify_label_alignment(r4, Alignment.RIGHT)
    tmc_vio_rail = align(
        point_at(tmc_vio_rail, Alignment.LEFT),
        r4.end,
        Alignment.CENTER,
    )

    tmc_vio_boundary = create_node(
        Dot,
        "tmc_vio_boundary",
        net=nets["tmc_vio"],
        label="TMC_VIO_3V3 -> adapter VIO",
        label_alignment=Alignment.RIGHT,
    )
    tmc_vio_boundary = align(
        tmc_vio_boundary,
        point_at(tmc_vio_rail, Alignment.RIGHT),
        Alignment.CENTER,
    )

    vio_ground_rail = create_node(
        Ground,
        "vio_ground_rail",
        net=nets["gnd"],
        label=(
            "COMMON GND\n" "CONCEPT REVIEW ONLY\n" "BENCH VALIDATE BEFORE CONSTRUCTION"
        ),
        label_alignment=Alignment.LEFT,
    )
    vio_ground_rail = create_rail(
        vio_ground_rail,
        Direction.HORIZONTAL,
        VIO_GROUND_RAIL_LENGTH,
        anchor=Alignment.LEFT,
    )
    vio_ground_rail = align(
        vio_ground_rail,
        tmc_vio_rail,
        Alignment.STACK_BOTTOM,
        stack_gap=VIO_TO_GROUND_GAP,
    )
    vio_ground_rail = align(
        point_at(vio_ground_rail, Alignment.LEFT),
        point_at(tmc_vio_rail, Alignment.LEFT),
        Alignment.CENTER,
        axes=["x"],
    )

    dz2 = create_element(
        Zener,
        "DZ2",
        "3.3 V / 0.5 W",
        vio_ground_rail,
        tmc_vio_rail,
    )
    dz2 = rotate(180)(dz2)
    dz2 = align(
        dz2,
        r4,
        Alignment.STACK_RIGHT,
        stack_gap=VIO_SHUNT_GAP,
    )
    dz2 = align(dz2.end, tmc_vio_rail, Alignment.CENTER, axes=["y"])
    dz2 = modify_label_alignment(dz2, Alignment.RIGHT)

    r5 = create_element(
        Resistor,
        "R5",
        "2.2 kohm",
        tmc_vio_rail,
        vio_ground_rail,
    )
    r5 = align(r5, dz2, Alignment.STACK_RIGHT, stack_gap=VIO_SHUNT_GAP)
    r5 = align(r5.start, tmc_vio_rail, Alignment.CENTER, axes=["y"])
    r5 = modify_label_alignment(r5, Alignment.RIGHT)

    c1 = create_element(
        Capacitor,
        "C1",
        "100 nF",
        tmc_vio_rail,
        vio_ground_rail,
    )
    c1 = align(c1, r5, Alignment.STACK_RIGHT, stack_gap=VIO_SHUNT_GAP)
    c1 = align(c1.start, tmc_vio_rail, Alignment.CENTER, axes=["y"])
    c1 = modify_label_alignment(c1, Alignment.RIGHT)

    input_nodes = {}
    output_nodes = {}
    u1_terminal_nodes = {
        "vcc": create_node(
            Dot,
            "u1_vcc",
            net=nets["pico_vbus"],
            kind=SCHEMATIC_JUNCTION,
        ),
        "gnd": create_node(
            Dot,
            "u1_gnd",
            net=nets["gnd"],
            kind=SCHEMATIC_JUNCTION,
        ),
    }
    for channel_number, (signal, input_label, output_label, *_values) in enumerate(
        BUFFER_CHANNELS,
        start=1,
    ):
        input_node = create_node(
            Dot,
            f"pico_{signal}",
            net=nets[f"pico_{signal}"],
            label=input_label,
            label_alignment=Alignment.TOP,
        )
        output_node = create_node(
            Dot,
            f"tmc_{signal}",
            net=nets[f"tmc_{signal}"],
            label=output_label,
            label_alignment=Alignment.TOP,
        )
        input_nodes[signal] = input_node
        output_nodes[signal] = output_node
        u1_terminal_nodes[f"a{channel_number}"] = input_node
        u1_terminal_nodes[f"y{channel_number}"] = output_node

    u1 = create_element(
        HexOpenCollectorBuffer,
        "U1",
        "SN7407N\n6x non-inverting open collector",
        **u1_terminal_nodes,
    )
    u1 = align(
        u1,
        point_at(tmc_vio_rail, Alignment.RIGHT),
        Alignment.STACK_RIGHT,
        stack_gap=BUFFER_FROM_VIO_GAP,
    )
    u1 = align(u1, u2, Alignment.CENTER, axes=["y"])
    u1 = modify_label_alignment(u1, Alignment.TOP)

    u1_terminal_nodes["vcc"] = align(
        u1_terminal_nodes["vcc"],
        u1.vcc,
        Alignment.CENTER,
    )
    u1_terminal_nodes["gnd"] = align(
        u1_terminal_nodes["gnd"],
        u1.gnd,
        Alignment.CENTER,
    )
    for channel_number, (signal, *_values) in enumerate(BUFFER_CHANNELS, start=1):
        input_nodes[signal] = align(
            input_nodes[signal],
            u1.anchor(f"a{channel_number}"),
            Alignment.STACK_LEFT,
            stack_gap=BUFFER_NODE_GAP,
        )
        input_nodes[signal] = align(
            input_nodes[signal],
            u1.anchor(f"a{channel_number}"),
            Alignment.CENTER,
            axes=["y"],
        )
        output_nodes[signal] = align(
            output_nodes[signal],
            u1.anchor(f"y{channel_number}"),
            Alignment.STACK_RIGHT,
            stack_gap=BUFFER_NODE_GAP,
        )
        output_nodes[signal] = align(
            output_nodes[signal],
            u1.anchor(f"y{channel_number}"),
            Alignment.CENTER,
            axes=["y"],
        )

    pico_3v3_input_rail = create_node(
        Dot,
        "pico_3v3_input_rail",
        net=nets["pico_3v3"],
    )
    pico_3v3_input_rail = create_rail(
        pico_3v3_input_rail,
        Direction.VERTICAL,
        BUFFER_RAIL_LENGTH,
    )

    signal_vio_rail = create_node(
        Dot,
        "signal_vio_rail",
        net=nets["tmc_vio"],
    )
    signal_vio_rail = create_rail(
        signal_vio_rail,
        Direction.VERTICAL,
        BUFFER_RAIL_LENGTH,
    )

    buffer_elements = []
    for (
        signal,
        _input_label,
        _output_label,
        input_ref,
        output_ref,
        output_value,
    ) in BUFFER_CHANNELS:
        input_pullup = create_element(
            Resistor,
            input_ref,
            "10 kohm",
            pico_3v3_input_rail,
            input_nodes[signal],
        )
        input_pullup = rotate(90)(input_pullup)
        input_pullup = align(input_pullup.end, input_nodes[signal], Alignment.CENTER)
        input_pullup = modify_label_alignment(input_pullup, Alignment.BOTTOM)

        output_pullup = create_element(
            Resistor,
            output_ref,
            output_value,
            output_nodes[signal],
            signal_vio_rail,
        )
        output_pullup = rotate(90)(output_pullup)
        output_pullup = align(
            output_pullup.start,
            output_nodes[signal],
            Alignment.CENTER,
        )
        output_pullup = modify_label_alignment(output_pullup, Alignment.BOTTOM)

        buffer_elements.extend((input_pullup, output_pullup))

    first_input_pullup = buffer_elements[0]
    pico_3v3_input_rail = align(
        pico_3v3_input_rail,
        first_input_pullup.start,
        Alignment.CENTER,
        axes=["x"],
    )
    pico_3v3_input_rail = align(pico_3v3_input_rail, u1, Alignment.CENTER, axes=["y"])

    first_output_pullup = buffer_elements[1]
    signal_vio_rail = align(
        signal_vio_rail,
        first_output_pullup.end,
        Alignment.CENTER,
        axes=["x"],
    )
    signal_vio_rail = align(signal_vio_rail, u1, Alignment.CENTER, axes=["y"])

    pico_3v3_input_label = create_node(
        Dot,
        "pico_3v3_input_label",
        net=nets["pico_3v3"],
        label="PICO_3V3\nall six inputs default HIGH",
        label_alignment=Alignment.TOP,
    )
    pico_3v3_input_label = align(
        pico_3v3_input_label,
        point_at(pico_3v3_input_rail, Alignment.TOP),
        Alignment.STACK_TOP,
        stack_gap=0.7,
    )
    pico_3v3_input_label = align(
        pico_3v3_input_label,
        point_at(pico_3v3_input_rail, Alignment.TOP),
        Alignment.CENTER,
        axes=["x"],
    )

    signal_vio_label = create_node(
        Dot,
        "signal_vio_label",
        net=nets["tmc_vio"],
        label="TMC_VIO_3V3\ncollector nodes continue to adapter",
        label_alignment=Alignment.TOP,
    )
    signal_vio_label = align(
        signal_vio_label,
        point_at(signal_vio_rail, Alignment.TOP),
        Alignment.STACK_TOP,
        stack_gap=0.7,
    )
    signal_vio_label = align(
        signal_vio_label,
        point_at(signal_vio_rail, Alignment.TOP),
        Alignment.CENTER,
        axes=["x"],
    )

    u1_vbus_rail = create_node(
        Dot,
        "u1_vbus_rail",
        net=nets["pico_vbus"],
        label="PICO_VBUS_5V -> U1 pin 14",
        label_alignment=Alignment.TOP,
    )
    u1_vbus_rail = create_rail(
        u1_vbus_rail,
        Direction.HORIZONTAL,
        3.0,
    )
    u1_vbus_rail = align(
        u1_vbus_rail,
        u1.vcc,
        Alignment.STACK_TOP,
        stack_gap=1.8,
    )
    u1_vbus_rail = align(u1_vbus_rail, u1.vcc, Alignment.CENTER, axes=["x"])

    u1_ground = create_node(
        Ground,
        "u1_ground",
        net=nets["gnd"],
    )
    u1_ground = align(
        u1_ground,
        u1.gnd,
        Alignment.STACK_BOTTOM,
        stack_gap=LOCAL_GROUND_GAP,
    )
    u1_ground = align(u1_ground, u1.gnd, Alignment.CENTER, axes=["x"])

    tmc_miso = create_node(
        Dot,
        "tmc_miso",
        net=nets["tmc_miso"],
        label="adapter MISO",
        label_alignment=Alignment.RIGHT,
    )
    pico_miso = create_node(
        Dot,
        "pico_miso",
        net=nets["pico_miso"],
        label="GPIO8 MISO",
        label_alignment=Alignment.LEFT,
    )
    r19 = create_element(Resistor, "R19", "1 kohm", pico_miso, tmc_miso)
    r19 = rotate(90)(r19)
    r19 = align(
        r19,
        u1,
        Alignment.STACK_BOTTOM,
        stack_gap=RETURN_ROW_GAP,
    )
    r19 = align(r19, point_at(u1, Alignment.LEFT), Alignment.CENTER, axes=["x"])
    r19 = modify_label_alignment(r19, Alignment.TOP)
    pico_miso = align(
        pico_miso,
        r19.start,
        Alignment.STACK_LEFT,
        stack_gap=BUFFER_NODE_GAP,
    )
    pico_miso = align(pico_miso, r19.start, Alignment.CENTER, axes=["y"])
    tmc_miso = align(
        tmc_miso,
        r19.end,
        Alignment.STACK_RIGHT,
        stack_gap=BUFFER_NODE_GAP,
    )
    tmc_miso = align(tmc_miso, r19.end, Alignment.CENTER, axes=["y"])

    tmc_diag1 = create_node(
        Dot,
        "tmc_diag1",
        net=nets["tmc_diag1"],
        label="adapter DIAG1",
        label_alignment=Alignment.RIGHT,
    )
    pico_diag1 = create_node(
        Dot,
        "pico_diag1",
        net=nets["pico_diag1"],
        label="GPIO3 DIAG1",
        label_alignment=Alignment.LEFT,
    )
    r20 = create_element(Resistor, "R20", "1 kohm", pico_diag1, tmc_diag1)
    r20 = rotate(90)(r20)
    r20 = align(
        r20,
        r19,
        Alignment.STACK_BOTTOM,
        stack_gap=RETURN_ROW_GAP,
    )
    r20 = align(r20, r19, Alignment.CENTER, axes=["x"])
    r20 = modify_label_alignment(r20, Alignment.TOP)
    pico_diag1 = align(
        pico_diag1,
        r20.start,
        Alignment.STACK_LEFT,
        stack_gap=BUFFER_NODE_GAP,
    )
    pico_diag1 = align(pico_diag1, r20.start, Alignment.CENTER, axes=["y"])
    tmc_diag1 = align(
        tmc_diag1,
        r20.end,
        Alignment.STACK_RIGHT,
        stack_gap=BUFFER_NODE_GAP,
    )
    tmc_diag1 = align(tmc_diag1, r20.end, Alignment.CENTER, axes=["y"])

    r21_ground_terminal = create_node(
        Dot,
        "r21_ground_terminal",
        net=nets["gnd"],
        kind=SCHEMATIC_JUNCTION,
    )
    r21 = create_element(
        Resistor,
        "R21",
        "47 kohm",
        pico_miso,
        r21_ground_terminal,
    )
    r21 = align(r21.start, pico_miso, Alignment.CENTER)
    r21 = modify_label_alignment(r21, Alignment.LEFT)
    r21_ground_terminal = align(r21_ground_terminal, r21.end, Alignment.CENTER)

    r21_ground = create_node(Ground, "r21_ground", net=nets["gnd"])
    r21_ground = align(
        r21_ground,
        r21.end,
        Alignment.STACK_BOTTOM,
        stack_gap=LOCAL_GROUND_GAP,
    )
    r21_ground = align(r21_ground, r21.end, Alignment.CENTER, axes=["x"])

    r22_ground_terminal = create_node(
        Dot,
        "r22_ground_terminal",
        net=nets["gnd"],
        kind=SCHEMATIC_JUNCTION,
    )
    r22 = create_element(
        Resistor,
        "R22",
        "47 kohm",
        pico_diag1,
        r22_ground_terminal,
    )
    r22 = align(r22.start, pico_diag1, Alignment.CENTER)
    r22 = modify_label_alignment(r22, Alignment.LEFT)
    r22_ground_terminal = align(r22_ground_terminal, r22.end, Alignment.CENTER)

    r22_ground = create_node(Ground, "r22_ground", net=nets["gnd"])
    r22_ground = align(
        r22_ground,
        r22.end,
        Alignment.STACK_BOTTOM,
        stack_gap=LOCAL_GROUND_GAP,
    )
    r22_ground = align(r22_ground, r22.end, Alignment.CENTER, axes=["x"])

    c2_vbus = create_node(
        Dot,
        "c2_vbus",
        net=nets["pico_vbus"],
        label="PICO_VBUS_5V",
        label_alignment=Alignment.TOP,
    )
    c2_ground_terminal = create_node(
        Dot,
        "c2_ground_terminal",
        net=nets["gnd"],
        kind=SCHEMATIC_JUNCTION,
    )
    c2 = create_element(
        Capacitor,
        "C2",
        "100 nF at U1 pins 14/7",
        c2_vbus,
        c2_ground_terminal,
    )
    c2 = align(
        c2,
        signal_vio_rail,
        Alignment.STACK_RIGHT,
        stack_gap=VIO_SHUNT_GAP,
    )
    c2 = align(c2, u1, Alignment.CENTER, axes=["y"])
    c2 = modify_label_alignment(c2, Alignment.RIGHT)
    c2_vbus = align(c2_vbus, c2.start, Alignment.CENTER)
    c2_vbus = align(
        c2_vbus,
        c2.start,
        Alignment.STACK_TOP,
        stack_gap=BUFFER_PULLUP_GAP,
    )
    c2_ground_terminal = align(c2_ground_terminal, c2.end, Alignment.CENTER)

    c2_ground = create_node(Ground, "c2_ground", net=nets["gnd"])
    c2_ground = align(
        c2_ground,
        c2.end,
        Alignment.STACK_BOTTOM,
        stack_gap=LOCAL_GROUND_GAP,
    )
    c2_ground = align(c2_ground, c2.end, Alignment.CENTER, axes=["x"])

    nodes = [
        u2_pin1,
        u2_pin2,
        u2_pin4,
        u2_pin3,
        u2_pin7,
        u2_pin8,
        u2_pin6,
        u2_pin5,
        pin3_ground,
        pin8_ground,
        pin5_ground,
        d1_anode,
        d1_cathode,
        d1_anode_tap,
        d1_cathode_tap,
        detector_after_r1,
        switched_24v,
        power_good,
        power_good_gpio,
        pico_3v3_power_good,
        q1_base,
        pico_vbus_rail,
        q1_collector,
        tmc_vio_rail,
        tmc_vio_boundary,
        vio_ground_rail,
        u1_terminal_nodes["vcc"],
        u1_terminal_nodes["gnd"],
        *input_nodes.values(),
        *output_nodes.values(),
        pico_3v3_input_rail,
        pico_3v3_input_label,
        signal_vio_rail,
        signal_vio_label,
        u1_vbus_rail,
        u1_ground,
        tmc_miso,
        pico_miso,
        tmc_diag1,
        pico_diag1,
        c2_vbus,
        r21_ground_terminal,
        r21_ground,
        r22_ground_terminal,
        r22_ground,
        c2_ground_terminal,
        c2_ground,
    ]
    elements = [
        r1,
        dz1,
        d1,
        u2,
        r6,
        r3,
        r2,
        q1,
        r4,
        dz2,
        r5,
        c1,
        u1,
        *buffer_elements,
        r19,
        r20,
        r21,
        r22,
        c2,
    ]
    wires = [
        create_wire(u2_pin2, u2_pin4),
        create_wire(u2_pin3, pin3_ground),
        create_wire(u2_pin8, pin8_ground),
        create_wire(u2_pin5, pin5_ground),
        create_wire(d1_anode, d1_anode_tap),
        create_wire(d1_anode_tap, u2_pin3),
        create_wire(d1_cathode, d1_cathode_tap),
        create_wire(d1_cathode_tap, u2_pin1),
        create_wire(u2_pin6, power_good),
        create_wire(power_good, power_good_gpio),
        create_wire(tmc_vio_rail, tmc_vio_boundary),
        create_wire(pico_3v3_input_rail, pico_3v3_input_label),
        create_wire(signal_vio_rail, signal_vio_label),
        create_wire(u1_terminal_nodes["vcc"], u1_vbus_rail),
        create_wire(u1_terminal_nodes["gnd"], u1_ground),
        create_wire(r21_ground_terminal, r21_ground),
        create_wire(r22_ground_terminal, r22_ground),
        create_wire(c2_ground_terminal, c2_ground),
    ]
    return create_schema(nodes, elements, wires=wires)


def _stable_artifact_paths(output_dir, stem):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{stem}.svg", output_dir / f"{stem}.png"


def _normalize_schematic_svg(svg_file):
    text = Path(svg_file).read_text(encoding="utf-8")
    text = re.sub(
        r"<dc:date>[^<]*</dc:date>",
        "<dc:date>stable-idex-generated-artifact</dc:date>",
        text,
    )

    clip_ids = []
    for match in re.finditer(r"p[0-9a-f]{10}", text):
        clip_id = match.group(0)
        if clip_id not in clip_ids:
            clip_ids.append(clip_id)
    for index, clip_id in enumerate(clip_ids):
        text = text.replace(clip_id, f"idex_clip_{index}")

    Path(svg_file).write_text(text, encoding="utf-8")


def render_tmc5160t_plus_power_sequencing(output_dir=None):
    output_dir = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    schema = create_tmc5160t_plus_power_sequencing_schema()
    svg_file, png_file = _stable_artifact_paths(output_dir, SCHEMATIC_ARTIFACT_STEM)
    for output_file in (svg_file, png_file):
        render_schemdraw(
            schema,
            file=output_file,
            kind_color_map=IDEX_KIND_COLOR_MAP,
            background_color="#ffffff",
        )
        if output_file.suffix == ".svg":
            _normalize_schematic_svg(output_file)
        _logger.info("Wrote %s", output_file)
    return svg_file, png_file


def main():
    render_tmc5160t_plus_power_sequencing()


if __name__ == "__main__":
    main()
