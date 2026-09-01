"""Declarative MGN12 counter-rail assembly."""

from shellforgepy.simple import *


def create_mgn_12_4040_m3_counter_rail_assembly():
    """Create the MGN12-to-4040 counter rail with M3 insert pockets."""

    hole_pitch = 25

    # groove_width = 8
    groove_guide_thickness = 0.8
    groove_guide_bottom_width = 8.4
    groove_guide_top_width = 7.9

    num_holes = 3

    counter_thickness = 5.8

    counter_width = 14

    bottom_cut_thickness = 2

    length = (num_holes - 0.6) * hole_pitch

    thread_inset_boss_extra_radius = 0.5
    thread_inset_hole_radius_adjustment = -0.1
    inserts = None
    for i in range(num_holes):
        insert = create_thread_inset_assembly(
            size="M3",
            thickness=counter_thickness + groove_guide_thickness,
            extra_radius=thread_inset_boss_extra_radius,
            clearance_type="normal",
            thread_inset_hole_radius_adjustment=thread_inset_hole_radius_adjustment,
        )

        insert = translate(i * hole_pitch, 0, 0)(insert)

        insert = insert.prefixed_copy(f"insert_{i}")

        if inserts is None:
            inserts = insert
        else:
            inserts = inserts.fuse(insert)

    base = LeaderFollowersCuttersPart(
        create_box(length, counter_width, counter_thickness)
    )

    groove_guide = create_pyramid_stump(
        length,
        length,
        groove_guide_bottom_width,
        groove_guide_top_width,
        groove_guide_thickness,
    )

    groove_guide = align(groove_guide, base, Alignment.CENTER)
    groove_guide = align(groove_guide, base, Alignment.STACK_TOP)

    base = base.fuse(groove_guide)

    inserts = align(inserts, base, Alignment.CENTER)
    inserts = align(inserts, base, Alignment.BOTTOM)

    base = inserts.use_as_cutter_on(base)

    base = base.fuse(inserts)

    bottom_cutter_positive = create_pyramid_stump(
        length + 10,
        length + 10,
        counter_width - 2 * bottom_cut_thickness,
        counter_width,
        bottom_cut_thickness,
    )
    bottom_cutter_positive = align(bottom_cutter_positive, base, Alignment.CENTER)
    bottom_cutter_positive = align(bottom_cutter_positive, base, Alignment.BOTTOM)

    bottom_cutter = create_box(500, 500, 500)
    bottom_cutter = align(bottom_cutter, base, Alignment.CENTER)
    bottom_cutter = align(
        bottom_cutter, base, Alignment.STACK_BOTTOM, stack_gap=-bottom_cut_thickness
    )

    bottom_cutter = bottom_cutter.cut(bottom_cutter_positive)

    base = base.cut(bottom_cutter)

    return base
