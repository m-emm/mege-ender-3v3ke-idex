"""Vector-labelled pressure-advance corner-strip calibration assembly."""

from mege_ender_3v3ke_idex.designs.pressure_advance_gcode_postprocessor import (
    expand_pressure_advance_sweep,
)
from shellforgepy.simple import *

DEFAULT_PRESSURE_ADVANCE_SWEEP = {
    "y_min_start": 43.5,
    "band_height": 13.0,
    "y_pitch": 20.0,
    "advance_start": 0.025,
    "advance_pitch": 0.005,
    "count": 7,
    "label_decimals": 3,
}
PRESSURE_ADVANCE_VALUES = tuple(
    band["advance"]
    for band in expand_pressure_advance_sweep(DEFAULT_PRESSURE_ADVANCE_SWEEP)
)
STRIP_WIDTH = 70.0
STRIP_DEPTH = 12.0
STRIP_HEIGHT = 3.0
STRIP_WALL_THICKNESS = 1.2
STRIP_GAP = 8.0
CALIBRATION_LAYER_HEIGHT = 0.32
LABEL_PLAQUE_WIDTH = 32.0
LABEL_PLAQUE_DEPTH = 12.0
LABEL_PLAQUE_HEIGHT = CALIBRATION_LAYER_HEIGHT
LABEL_TEXT_SIZE = 7.0
LABEL_TEXT_HEIGHT = 4 * CALIBRATION_LAYER_HEIGHT
LABEL_TEXT_STROKE_WIDTH = 1.5
LABEL_STRIP_OVERLAP = 0.6


def create_pressure_advance_calibration_assembly(pressure_advance_sweep=None):
    """Create labelled strips for comparing pressure advance by Y position."""

    calibration = PartCollector()
    bands = expand_pressure_advance_sweep(
        pressure_advance_sweep or DEFAULT_PRESSURE_ADVANCE_SWEEP
    )

    for index, band in enumerate(bands):
        strip = create_box(STRIP_WIDTH, STRIP_DEPTH, STRIP_HEIGHT)
        strip_cutter = create_box(
            STRIP_WIDTH - 2 * STRIP_WALL_THICKNESS,
            STRIP_DEPTH - 2 * STRIP_WALL_THICKNESS,
            STRIP_HEIGHT * 2,
        )
        strip_cutter = align(strip_cutter, strip, Alignment.CENTER)
        strip = strip.cut(strip_cutter)

        label_plaque = create_box(
            LABEL_PLAQUE_WIDTH,
            LABEL_PLAQUE_DEPTH,
            LABEL_PLAQUE_HEIGHT,
        )
        label_plaque = align(label_plaque, strip, Alignment.CENTER)
        label_plaque = align(label_plaque, strip, Alignment.BOTTOM)
        label_plaque = align(
            label_plaque,
            strip,
            Alignment.STACK_LEFT,
            stack_gap=-LABEL_STRIP_OVERLAP,
        )

        label = create_vector_text_object(
            band["label"],
            size=LABEL_TEXT_SIZE,
            thickness=LABEL_TEXT_HEIGHT,
            stroke_width=LABEL_TEXT_STROKE_WIDTH,
        )
        label = align(label, label_plaque, Alignment.CENTER)
        label = align(label, label_plaque, Alignment.STACK_TOP)
        label_plaque = label_plaque.fuse(label)

        strip_with_label = strip.fuse(label_plaque)
        strip_with_label = translate(
            0,
            index * (STRIP_DEPTH + STRIP_GAP),
            0,
        )(strip_with_label)
        calibration = calibration.fuse(strip_with_label)

    side_connector = materialize_bounding_box(
        calibration, x_size=LABEL_PLAQUE_WIDTH * 0.1, z_size=LABEL_PLAQUE_HEIGHT
    )
    side_connector = align(side_connector, calibration, Alignment.LEFT)
    side_connector = align(side_connector, calibration, Alignment.BOTTOM)
    calibration = calibration.fuse(side_connector)

    return LeaderFollowersCuttersPart(leader=calibration)
