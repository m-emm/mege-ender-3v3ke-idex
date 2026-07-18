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
    "buffer_enable": "#ffd400",
    "default": "#808080",
}

SCHEMATIC_JUNCTION = "schematic_junction"

DETECTOR_STAGE_GAP = 0.7
D1_TO_PACKAGE_GAP = 0.25
DETECTOR_TERMINAL_GAP = 0.8
LOCAL_GROUND_GAP = 0.55

POWER_GOOD_FROM_PACKAGE_GAP = 1.8
POWER_GOOD_INPUT_GAP = 0.8
BUFFER_NODE_GAP = 0.7
PARALLEL_DIODE_GAP = 0.6

Q1_FROM_PACKAGE_GAP = 6.5
Q1_ABOVE_U2A_GAP = 1.0
VIO_TO_GND_RAIL_GAP = 5.0
VIO_STAGE_GAP = 2.8

VBUS_RAIL_LENGTH = 3.2
VIO_RAIL_LENGTH = 8.8
GND_RAIL_LENGTH = 13.0


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
        "buffer_oe": "buffer_enable",
    }
    return {name: create_net(name, kind=kind) for name, kind in net_kinds.items()}


def create_tmc5160t_plus_power_sequencing_schema():
    nets = create_tmc5160t_plus_nets()

    switched_24v = create_node(
        Dot,
        "switched_24v",
        net=nets["switched_24v"],
        label="+24V_SW",
        label_alignment=Alignment.LEFT,
    )
    detector_after_r1 = create_node(
        Dot,
        "detector_after_r1",
        net=nets["detector_after_r1"],
        kind=SCHEMATIC_JUNCTION,
    )
    u2_pin1 = create_node(
        Dot,
        "u2_pin1",
        net=nets["detector_pin1"],
        label="pin 1",
        label_alignment=Alignment.TOP,
    )
    u2_led_link = create_node(
        Dot,
        "u2_led_link",
        net=nets["detector_led_link"],
        label="pins 2-4 linked",
        label_alignment=Alignment.LEFT,
    )
    u2_pin3_ground = create_node(
        Ground,
        "u2_pin3_ground",
        net=nets["gnd"],
        label="pin 3",
        label_alignment=Alignment.LEFT,
    )
    u2a_collector = create_node(
        Dot,
        "u2a_collector",
        net=nets["u2a_collector"],
        label="pin 7",
        label_alignment=Alignment.TOP,
    )
    u2a_emitter_ground = create_node(
        Ground,
        "u2a_emitter_ground",
        net=nets["gnd"],
        label="pin 8",
        label_alignment=Alignment.RIGHT,
    )
    power_good = create_node(
        Dot,
        "power_good",
        net=nets["power_good"],
        label="pin 6  PWR_OK_N",
        label_alignment=Alignment.BOTTOM,
    )
    power_good_gpio = create_node(
        Dot,
        "power_good_gpio",
        net=nets["power_good"],
        label=(
            "y_pico:gpio5 boundary\nPWR_OK_N is active-low\n"
            "LOW = switched 24 V valid"
        ),
        label_alignment=Alignment.LEFT,
    )
    u2b_emitter_ground = create_node(
        Ground,
        "u2b_emitter_ground",
        net=nets["gnd"],
        label="pin 5",
        label_alignment=Alignment.RIGHT,
    )

    q1_base = create_node(
        Dot,
        "q1_base",
        net=nets["q1_base"],
        kind=SCHEMATIC_JUNCTION,
    )
    q1_collector = create_node(
        Dot,
        "q1_collector",
        net=nets["q1_collector"],
        kind=SCHEMATIC_JUNCTION,
    )
    pico_3v3 = create_node(
        Dot,
        "pico_3v3",
        net=nets["pico_3v3"],
        label="PICO_3V3",
        label_alignment=Alignment.TOP,
    )
    buffer_oe = create_node(
        Dot,
        "buffer_oe",
        net=nets["buffer_oe"],
        label=(
            "BUFFER_OE_N -> U1 OE pins 1/19\n"
            "SN74HC244N: LOW enables; 7-13 ms on-delay; D2 fast-off"
        ),
        label_alignment=Alignment.RIGHT,
    )

    pico_vbus_rail = create_node(
        Dot,
        "pico_vbus_rail",
        net=nets["pico_vbus"],
        label="PICO_VBUS_5V  RP2040-Plus pin 40",
        label_alignment=Alignment.LEFT,
    )
    pico_vbus_rail = create_rail(
        pico_vbus_rail,
        Direction.HORIZONTAL,
        VBUS_RAIL_LENGTH,
        anchor=Alignment.LEFT,
    )

    tmc_vio_rail = create_node(
        Dot,
        "tmc_vio_rail",
        net=nets["tmc_vio"],
        label="TMC_VIO_3V3 -> adapter VIO\nVIO established before OE enables",
        label_alignment=Alignment.RIGHT,
    )
    tmc_vio_rail = create_rail(
        tmc_vio_rail,
        Direction.HORIZONTAL,
        VIO_RAIL_LENGTH,
        anchor=Alignment.RIGHT,
    )

    gnd_rail = create_node(
        Ground,
        "gnd_rail",
        net=nets["gnd"],
        label=(
            "GND rail\nCONCEPT REVIEW ONLY\n"
            "Bench validate before construction: threshold, VIO/load, OE timing, fast shutdown"
        ),
        label_alignment=Alignment.LEFT,
    )
    gnd_rail = create_rail(
        gnd_rail,
        Direction.HORIZONTAL,
        GND_RAIL_LENGTH,
        anchor=Alignment.LEFT,
    )

    u2 = create_element(
        DualOptocoupler,
        "U2",
        "ILD74",
        a_anode=u2_pin1,
        a_cathode=u2_led_link,
        a_collector=u2a_collector,
        a_emitter=u2a_emitter_ground,
        b_anode=u2_led_link,
        b_cathode=u2_pin3_ground,
        b_collector=power_good,
        b_emitter=u2b_emitter_ground,
    )
    u2 = modify_label_alignment(u2, Alignment.TOP)

    u2_pin1 = align(u2_pin1, u2.a_anode, Alignment.CENTER)
    u2_pin3_ground = align(
        u2_pin3_ground,
        u2.b_cathode,
        Alignment.CENTER,
        axes=["x"],
    )
    u2_pin3_ground = align(
        u2_pin3_ground,
        u2.b_cathode,
        Alignment.STACK_BOTTOM,
        stack_gap=LOCAL_GROUND_GAP,
    )
    u2a_collector = align(u2a_collector, u2.a_collector, Alignment.CENTER)
    u2a_emitter_ground = align(
        u2a_emitter_ground,
        u2,
        Alignment.STACK_RIGHT,
        stack_gap=LOCAL_GROUND_GAP,
    )
    u2a_emitter_ground = align(
        u2a_emitter_ground,
        u2.a_emitter,
        Alignment.CENTER,
        axes=["y"],
    )
    u2b_emitter_ground = align(
        u2b_emitter_ground,
        u2,
        Alignment.STACK_RIGHT,
        stack_gap=LOCAL_GROUND_GAP,
    )
    u2b_emitter_ground = align(
        u2b_emitter_ground,
        u2.b_emitter,
        Alignment.CENTER,
        axes=["y"],
    )
    power_good = align(
        power_good,
        u2,
        Alignment.STACK_RIGHT,
        stack_gap=POWER_GOOD_FROM_PACKAGE_GAP,
    )
    power_good = align(
        power_good,
        u2.b_collector,
        Alignment.CENTER,
        axes=["y"],
    )
    power_good_gpio = align(
        power_good_gpio,
        power_good,
        Alignment.CENTER,
    )
    power_good_gpio = translate(0, -3.0)(power_good_gpio)

    d1 = create_element(Diode, "D1", "1N4148", u2_pin3_ground, u2_pin1)
    d1 = rotate(180)(d1)
    d1 = align(
        d1,
        u2,
        Alignment.STACK_LEFT,
        stack_gap=D1_TO_PACKAGE_GAP,
    )
    d1 = align(d1.end, u2_pin1, Alignment.CENTER, axes=["y"])
    d1 = modify_label_alignment(d1, Alignment.LEFT)

    dz1 = create_element(
        Zener,
        "DZ1",
        "12 V / 0.5 W",
        u2_pin1,
        detector_after_r1,
    )
    dz1 = rotate(-90)(dz1)
    dz1 = align(
        dz1,
        d1,
        Alignment.STACK_LEFT,
        stack_gap=DETECTOR_STAGE_GAP,
    )
    dz1 = align(dz1, d1, Alignment.CENTER, axes=["y"])
    dz1 = modify_label_alignment(dz1, Alignment.TOP)

    detector_after_r1 = align(
        detector_after_r1,
        dz1.end,
        Alignment.STACK_LEFT,
        stack_gap=DETECTOR_STAGE_GAP,
    )
    r1 = create_element(
        Resistor,
        "R1",
        "620 ohm / 0.5 W",
        switched_24v,
        detector_after_r1,
    )
    r1 = rotate(90)(r1)
    r1 = align(
        r1,
        detector_after_r1,
        Alignment.STACK_LEFT,
        stack_gap=DETECTOR_STAGE_GAP,
    )
    r1 = align(r1, detector_after_r1, Alignment.CENTER, axes=["y"])
    r1 = modify_label_alignment(r1, Alignment.BOTTOM)

    switched_24v = align(switched_24v, r1.start, Alignment.CENTER, axes=["y"])
    switched_24v = align(
        switched_24v,
        r1.start,
        Alignment.STACK_LEFT,
        stack_gap=DETECTOR_TERMINAL_GAP,
    )

    r6 = create_element(Resistor, "R6", "4.7 kohm", pico_3v3, power_good)
    r6 = align(r6.end, power_good, Alignment.CENTER)
    r6 = modify_label_alignment(r6, Alignment.RIGHT)
    pico_3v3 = align(pico_3v3, r6.start, Alignment.CENTER)
    pico_3v3 = align(
        pico_3v3,
        r6.start,
        Alignment.STACK_TOP,
        stack_gap=POWER_GOOD_INPUT_GAP,
    )

    r7 = create_element(Resistor, "R7", "2.2 Mohm", power_good, buffer_oe)
    r7 = rotate(90)(r7)
    r7 = align(
        r7,
        power_good,
        Alignment.STACK_RIGHT,
        stack_gap=POWER_GOOD_INPUT_GAP,
    )
    r7 = align(r7, power_good, Alignment.CENTER, axes=["y"])
    r7 = modify_label_alignment(r7, Alignment.BOTTOM)

    buffer_oe = align(buffer_oe, r7.end, Alignment.CENTER, axes=["y"])
    buffer_oe = align(
        buffer_oe,
        r7.end,
        Alignment.STACK_RIGHT,
        stack_gap=BUFFER_NODE_GAP,
    )

    d2 = create_element(Diode, "D2", "1N4148", power_good, buffer_oe)
    d2 = rotate(90)(d2)
    d2 = align(
        d2,
        r7,
        Alignment.STACK_TOP,
        stack_gap=PARALLEL_DIODE_GAP,
    )
    d2 = align(d2, r7, Alignment.CENTER, axes=["x"])
    d2 = modify_label_alignment(d2, Alignment.TOP)

    q1_base = align(
        q1_base,
        u2,
        Alignment.STACK_RIGHT,
        stack_gap=Q1_FROM_PACKAGE_GAP,
    )
    q1_base = align(
        q1_base,
        u2.a_collector,
        Alignment.CENTER,
        axes=["y"],
    )
    q1_base = translate(0, Q1_ABOVE_U2A_GAP)(q1_base)

    r3 = create_element(
        Resistor,
        "R3",
        "2.7 kohm",
        u2a_collector,
        q1_base,
    )
    r3 = rotate(90)(r3)
    r3 = align(r3.end, q1_base, Alignment.CENTER)
    r3 = modify_label_alignment(r3, Alignment.BOTTOM)

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

    r2 = create_element(Resistor, "R2", "47 kohm", pico_vbus_rail, q1_base)
    r2 = align(r2.end, q1_base, Alignment.CENTER)
    r2 = modify_label_alignment(r2, Alignment.LEFT)

    pico_vbus_rail = align(
        point_at(pico_vbus_rail, Alignment.LEFT),
        r2.start,
        Alignment.CENTER,
    )

    r4 = create_element(
        Resistor,
        "R4",
        "39 ohm / 0.5 W",
        q1_collector,
        tmc_vio_rail,
    )
    r4 = align(r4.start, q1.collector, Alignment.CENTER)
    r4 = modify_label_alignment(r4, Alignment.LEFT)

    tmc_vio_rail = align(
        point_at(tmc_vio_rail, Alignment.LEFT),
        r4.end,
        Alignment.CENTER,
    )
    gnd_rail = align(
        gnd_rail,
        tmc_vio_rail,
        Alignment.STACK_BOTTOM,
        stack_gap=VIO_TO_GND_RAIL_GAP,
    )
    gnd_rail = align(
        point_at(gnd_rail, Alignment.RIGHT),
        point_at(tmc_vio_rail, Alignment.RIGHT),
        Alignment.CENTER,
        axes=["x"],
    )

    dz2 = create_element(
        Zener,
        "DZ2",
        "3.3 V / 0.5 W",
        gnd_rail,
        tmc_vio_rail,
    )
    dz2 = rotate(180)(dz2)
    dz2 = align(
        dz2,
        r4,
        Alignment.STACK_RIGHT,
        stack_gap=VIO_STAGE_GAP,
    )
    dz2 = align(dz2.end, tmc_vio_rail, Alignment.CENTER, axes=["y"])
    dz2 = modify_label_alignment(dz2, Alignment.RIGHT)

    r5 = create_element(Resistor, "R5", "2.2 kohm", tmc_vio_rail, gnd_rail)
    r5 = align(
        r5,
        dz2,
        Alignment.STACK_RIGHT,
        stack_gap=VIO_STAGE_GAP,
    )
    r5 = align(r5.start, tmc_vio_rail, Alignment.CENTER, axes=["y"])
    r5 = modify_label_alignment(r5, Alignment.RIGHT)

    c1 = create_element(Capacitor, "C1", "100 nF", tmc_vio_rail, gnd_rail)
    c1 = align(
        c1,
        r5,
        Alignment.STACK_RIGHT,
        stack_gap=VIO_STAGE_GAP,
    )
    c1 = align(c1.start, tmc_vio_rail, Alignment.CENTER, axes=["y"])
    c1 = modify_label_alignment(c1, Alignment.RIGHT)

    c2 = create_element(Capacitor, "C2", "4.7 nF", buffer_oe, gnd_rail)
    c2 = align(c2.start, buffer_oe, Alignment.CENTER)
    c2 = modify_label_alignment(c2, Alignment.RIGHT)

    nodes = [
        switched_24v,
        detector_after_r1,
        u2_pin1,
        u2_led_link,
        u2_pin3_ground,
        u2a_collector,
        u2a_emitter_ground,
        power_good,
        power_good_gpio,
        u2b_emitter_ground,
        q1_base,
        q1_collector,
        pico_3v3,
        buffer_oe,
        pico_vbus_rail,
        tmc_vio_rail,
        gnd_rail,
    ]
    elements = [
        r1,
        dz1,
        d1,
        u2,
        r6,
        r7,
        d2,
        r3,
        r2,
        q1,
        r4,
        dz2,
        r5,
        c1,
        c2,
    ]
    return create_schema(
        nodes,
        elements,
        wires=[create_wire(power_good, power_good_gpio)],
    )


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
        )
        if output_file.suffix == ".svg":
            _normalize_schematic_svg(output_file)
        _logger.info("Wrote %s", output_file)
    return svg_file, png_file


def main():
    render_tmc5160t_plus_power_sequencing()


if __name__ == "__main__":
    main()
