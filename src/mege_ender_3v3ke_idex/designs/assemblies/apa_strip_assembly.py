"""APA102 LED strip reference assembly."""

from shellforgepy.simple import *


APA_STRIP_INFO = {
    "D60pm": {
        "leds_per_meter": 60,
        "pcb_width": 10.0,
        "pcb_thickness": 0.33,
        "led_pitch": 1000.0 / 60.0,
    },
    "D144pm": {
        "leds_per_meter": 144,
        "pcb_width": 12.0,
        "pcb_thickness": 0.33,
        "led_pitch": 1000.0 / 144.0,
    },
}

APA_LED_SIDE = 5.0
APA_LED_THICKNESS = 1.4
APA_PAD_LENGTH = 2.2
APA_PAD_WIDTH = 1.55
APA_PAD_THICKNESS = 0.04
APA_PAD_PITCH = 2.0


def _strip_info(density):
    density_name = getattr(density, "name", str(density))
    try:
        return APA_STRIP_INFO[density_name]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported APA strip density {density!r}; "
            f"expected one of {sorted(APA_STRIP_INFO)}"
        ) from exc


def create_apa_strip_assembly(
    *,
    apa_strip_density,
    apa_strip_num_leds,
    apa_strip_with_hull=False,
):
    """Create an APA102 strip with the flex PCB as the leader.

    Local axes are intentionally stable for placement:
    ``+X`` follows strip length, ``+Y`` follows strip width, and ``+Z`` points
    toward the LED face.
    """

    if apa_strip_num_leds <= 0:
        raise ValueError("apa_strip_num_leds must be positive")

    strip_info = _strip_info(apa_strip_density)
    pitch = strip_info["led_pitch"]
    pcb_width = strip_info["pcb_width"]
    pcb_thickness = strip_info["pcb_thickness"]
    strip_length = apa_strip_num_leds * pitch

    pcb = create_box(strip_length, pcb_width, pcb_thickness)
    assembly = LeaderFollowersCuttersPart(pcb)

    previous_cell = None
    for led_index in range(apa_strip_num_leds):
        cell = create_box(pitch, pcb_width, pcb_thickness)
        if previous_cell is None:
            cell = align(cell, pcb, Alignment.LEFT)
        else:
            cell = align(cell, previous_cell, Alignment.STACK_RIGHT)
        cell = align(cell, pcb, Alignment.FRONT)
        cell = align(cell, pcb, Alignment.BOTTOM)

        led = create_filleted_box(
            APA_LED_SIDE,
            APA_LED_SIDE,
            APA_LED_THICKNESS,
            fillet_radius=0.2,
            no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
        )
        led = align(led, cell, Alignment.CENTER, axes=[0, 1])
        led = align(led, pcb, Alignment.STACK_TOP)
        assembly.add_named_follower(led, f"apa_led_{led_index + 1}")
        previous_cell = cell

    pad_column_height = 3 * APA_PAD_PITCH + APA_PAD_WIDTH
    pad_stack_gap = APA_PAD_PITCH - APA_PAD_WIDTH
    for end_name, x_alignment in (
        ("left", Alignment.LEFT),
        ("right", Alignment.RIGHT),
    ):
        pad_column = create_box(
            APA_PAD_LENGTH,
            pad_column_height,
            APA_PAD_THICKNESS,
        )
        pad_column = align(pad_column, pcb, x_alignment)
        pad_column = align(pad_column, pcb, Alignment.CENTER, axes=[1])
        pad_column = align(pad_column, pcb, Alignment.STACK_TOP)

        previous_pad = None
        for pad_index in range(4):
            pad = create_box(APA_PAD_LENGTH, APA_PAD_WIDTH, APA_PAD_THICKNESS)
            pad = align(pad, pad_column, Alignment.CENTER, axes=[0])
            if previous_pad is None:
                pad = align(pad, pad_column, Alignment.FRONT)
            else:
                pad = align(pad, previous_pad, Alignment.STACK_BACK, stack_gap=pad_stack_gap)
            pad = align(pad, pad_column, Alignment.CENTER, axes=[2])
            assembly.add_named_follower(
                pad,
                f"apa_pad_{end_name}_{pad_index + 1}",
            )
            previous_pad = pad

    if apa_strip_with_hull:
        hull_wall = 0.8
        hull_height = pcb_thickness + 0.35
        hull = create_box(
            strip_length,
            pcb_width + 2 * hull_wall,
            hull_height,
        )
        hull = align(hull, pcb, Alignment.CENTER, axes=[0, 1, 2])
        hull_cutter = create_box(
            strip_length + 2,
            pcb_width + 0.3,
            hull_height + 2,
        )
        hull_cutter = align(hull_cutter, hull, Alignment.CENTER)
        hull = hull.cut(hull_cutter)
        assembly.add_named_follower(hull, "apa_strip_hull")

    return assembly
