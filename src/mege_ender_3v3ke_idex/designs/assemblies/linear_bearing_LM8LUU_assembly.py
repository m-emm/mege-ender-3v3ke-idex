"""Printable TPU umbilical cable guide for the x-axis."""

from shellforgepy.simple import *

lm8luu_length = 44.9
lm8luu_outer_diameter = 15
lm8luu_inner_diameter = 8

lm8luu_outer_groove_width = 1.2
lm8luu_groove_offset = 6
lm8luu_groove_diameter = 14.25


def create_linear_bearing_LM8LUU_assembly():

    retval = create_ring(
        lm8luu_outer_diameter / 2, lm8luu_inner_diameter / 2, lm8luu_length
    )

    groove_cutters = PartCollector()
    for i in [-1, 1]:
        groove_cutter = create_ring(
            2 * lm8luu_outer_diameter,
            lm8luu_groove_diameter / 2,
            lm8luu_outer_groove_width,
        )
        groove_cutter = align(groove_cutter, retval, Alignment.CENTER)

        groove_cutter = translate(0, 0, i * (lm8luu_length - lm8luu_groove_offset) / 2)(
            groove_cutter
        )

        groove_cutters = groove_cutters.fuse(groove_cutter)

    retval = retval.cut(groove_cutters)

    return retval
