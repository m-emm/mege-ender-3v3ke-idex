"""Printable TPU umbilical cable guide for the x-axis."""

from shellforgepy.simple import *

length = 44.9
outer_diameter = 15
inner_diameter = 8

outer_groove_width = 1.2
groove_offset = 6
groove_diameter = 14.25


def create_linear_bearing_LM8LUU_assembly():

    retval = create_ring(outer_diameter / 2, inner_diameter / 2, length)

    groove_cutters = PartCollector()
    for i in [-1, 1]:
        groove_cutter = create_ring(
            2 * outer_diameter, groove_diameter / 2, outer_groove_width
        )
        groove_cutter = align(groove_cutter, retval, Alignment.CENTER)

        groove_cutter = translate(0, 0, i * (length - groove_offset) / 2)(groove_cutter)

        groove_cutters = groove_cutters.fuse(groove_cutter)

    retval = retval.cut(groove_cutters)

    return retval
