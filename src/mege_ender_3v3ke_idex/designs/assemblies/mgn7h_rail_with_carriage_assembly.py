"""Declarative standalone MGN7H rail-with-carriage assembly."""

from shellforgepy.metrics import record_length_metric
from shellforgepy.simple import *

mgn_7h_rail_width = 7
mgn_7h_rail_height = 4.8
mgn_7h_rail_mount_hole_pitch = 15
mgn_7h_rail_mount_hole_end_offset = 5
mgn_7h_rail_mount_hole_diameter = 2.4
mgn_7h_rail_mount_counterbore_diameter = 4.2
mgn_7h_rail_mount_counterbore_depth = 2.4
mgn_7h_rail_mount_screw_size = "M2"
mgn_7h_rail_groove_z_center = 2.8
mgn_7h_rail_groove_v_height = 1.25
mgn_7h_rail_groove_v_depth = 0.625
mgn_7h_rail_groove_slot_height = 0.65
mgn_7h_rail_groove_slot_depth = 0.95
mgn_7h_rail_top_fillet_radius = 0.18
mgn_7h_rail_bottom_chamfer_width = 0.32
mgn_7h_rail_bottom_chamfer_height = 0.35

mgn_7h_carriage_length = 30.8
mgn_7h_carriage_width = 16.65
mgn_7h_carriage_height = 6.5
mgn_7h_carriage_h1_offset = 1.5
mgn_7h_carriage_mount_hole_pitch_x = 20
mgn_7h_carriage_mount_hole_pitch_y = 8
mgn_7h_carriage_mount_hole_depth = 3
mgn_7h_carriage_mount_screw_size = "M2"


def create_mgn7h_carriage(*, mgn7h_carriage_mount_hole_drill_extra_length):
    """Create an MGN7H carriage reference part."""

    screw_hole_diameter = MScrew.from_size(
        mgn_7h_carriage_mount_screw_size
    ).clearance_hole_normal

    carriage = create_box(
        mgn_7h_carriage_length,
        mgn_7h_carriage_width,
        mgn_7h_carriage_height,
    )

    holes = LeaderFollowersCuttersPart(PartCollector())
    mount_hole_positions = [
        (x, y)
        for x in [
            -mgn_7h_carriage_mount_hole_pitch_x / 2,
            mgn_7h_carriage_mount_hole_pitch_x / 2,
        ]
        for y in [
            -mgn_7h_carriage_mount_hole_pitch_y / 2,
            mgn_7h_carriage_mount_hole_pitch_y / 2,
        ]
    ]
    for index, (x, y) in enumerate(mount_hole_positions, start=1):
        hole = create_cylinder(
            screw_hole_diameter / 2,
            mgn_7h_carriage_height + mgn7h_carriage_mount_hole_drill_extra_length,
        )
        hole = translate(x, y, 0)(hole)
        holes.add_named_follower(hole, f"carriage_mount_hole_{index}")
        holes = holes.fuse(hole)

    holes = align(holes, carriage, Alignment.CENTER)
    holes = align(
        holes,
        carriage,
        Alignment.STACK_TOP,
        stack_gap=-mgn_7h_carriage_mount_hole_depth,
    )

    carriage = carriage.cut(holes.leader)

    carriage = LeaderFollowersCuttersPart(carriage)
    carriage.add_named_cutter(holes.leader, "carriage_mount_holes")
    for name, hole in holes.get_named_follower_items():
        carriage.add_named_cutter(hole, name)
    carriage.add_named_follower(carriage.leader, "carriage_body")

    carriage = translate(0, 0, mgn_7h_carriage_h1_offset)(carriage)

    return carriage


def create_mgn7h_rail(
    *,
    length_mm: float,
    mgn7h_rail_mount_hole_drill_extra_length,
    rail_width=mgn_7h_rail_width,
    rail_height=mgn_7h_rail_height,
    rail_groove_z_center=mgn_7h_rail_groove_z_center,
    rail_groove_v_height=mgn_7h_rail_groove_v_height,
    rail_groove_v_depth=mgn_7h_rail_groove_v_depth,
    rail_groove_slot_height=mgn_7h_rail_groove_slot_height,
    rail_groove_slot_depth=mgn_7h_rail_groove_slot_depth,
    rail_top_fillet_radius=mgn_7h_rail_top_fillet_radius,
    rail_bottom_chamfer_width=mgn_7h_rail_bottom_chamfer_width,
    rail_bottom_chamfer_height=mgn_7h_rail_bottom_chamfer_height,
):
    """Create an MGN7H rail reference part."""

    rail = create_box(length_mm, rail_width, rail_height)
    if rail_top_fillet_radius > 0:
        rail = apply_fillet_by_alignment(
            rail,
            rail_top_fillet_radius,
            fillets_at=[Alignment.TOP],
        )

    profile_cutters = []
    profile_cutter_names = []
    cutter_x_min = -0.1
    cutter_x_max = length_mm + 0.1

    if rail_bottom_chamfer_width > 0 and rail_bottom_chamfer_height > 0:
        front_chamfer = create_triangular_prism(
            [
                (cutter_x_min, 0, 0),
                (cutter_x_min, rail_bottom_chamfer_width, 0),
                (cutter_x_min, 0, rail_bottom_chamfer_height),
                (cutter_x_max, 0, 0),
                (cutter_x_max, rail_bottom_chamfer_width, 0),
                (cutter_x_max, 0, rail_bottom_chamfer_height),
            ]
        )
        back_chamfer = create_triangular_prism(
            [
                (cutter_x_min, rail_width, 0),
                (cutter_x_min, rail_width - rail_bottom_chamfer_width, 0),
                (cutter_x_min, rail_width, rail_bottom_chamfer_height),
                (cutter_x_max, rail_width, 0),
                (cutter_x_max, rail_width - rail_bottom_chamfer_width, 0),
                (cutter_x_max, rail_width, rail_bottom_chamfer_height),
            ]
        )
        for name, chamfer in [
            ("bottom_chamfer_front", front_chamfer),
            ("bottom_chamfer_back", back_chamfer),
        ]:
            rail = rail.cut(chamfer)
            profile_cutters.append(chamfer)
            profile_cutter_names.append(name)

    holes = LeaderFollowersCuttersPart(PartCollector())
    rail_mount_hole_span = length_mm - 2 * mgn_7h_rail_mount_hole_end_offset
    hole_x = 0
    hole_index = 1

    while hole_x <= rail_mount_hole_span + 1e-6:
        top_hole = create_cylinder(
            mgn_7h_rail_mount_counterbore_diameter / 2,
            mgn_7h_rail_mount_counterbore_depth,
        )
        top_hole = translate(hole_x, 0, 0)(top_hole)

        bottom_hole = create_cylinder(
            mgn_7h_rail_mount_hole_diameter / 2,
            rail_height
            - mgn_7h_rail_mount_counterbore_depth
            + mgn7h_rail_mount_hole_drill_extra_length,
        )
        bottom_hole = align(bottom_hole, top_hole, Alignment.CENTER)
        bottom_hole = align(bottom_hole, top_hole, Alignment.STACK_BOTTOM)

        current_hole = top_hole.fuse(bottom_hole)
        holes.add_named_follower(current_hole, f"rail_mount_hole_{hole_index}")
        holes = holes.fuse(current_hole)
        hole_x += mgn_7h_rail_mount_hole_pitch
        hole_index += 1

    if rail_groove_v_depth > 0 and rail_groove_v_height > 0:
        groove_v_convergence_depth = rail_groove_v_depth
        if rail_groove_slot_depth > 0 and rail_groove_slot_height > 0:
            # A 90-degree side V converges on the rounded slot end-circle center.
            groove_v_convergence_depth = max(
                0,
                rail_groove_slot_depth - rail_groove_slot_height / 2,
            )

        z_min = rail_groove_z_center - groove_v_convergence_depth
        z_max = rail_groove_z_center + groove_v_convergence_depth
        front_groove_v = create_triangular_prism(
            [
                (cutter_x_min, 0, z_min),
                (cutter_x_min, 0, z_max),
                (cutter_x_min, groove_v_convergence_depth, rail_groove_z_center),
                (cutter_x_max, 0, z_min),
                (cutter_x_max, 0, z_max),
                (cutter_x_max, groove_v_convergence_depth, rail_groove_z_center),
            ]
        )
        back_groove_v = create_triangular_prism(
            [
                (cutter_x_min, rail_width, z_min),
                (cutter_x_min, rail_width, z_max),
                (
                    cutter_x_min,
                    rail_width - groove_v_convergence_depth,
                    rail_groove_z_center,
                ),
                (cutter_x_max, rail_width, z_min),
                (cutter_x_max, rail_width, z_max),
                (
                    cutter_x_max,
                    rail_width - groove_v_convergence_depth,
                    rail_groove_z_center,
                ),
            ]
        )
        for name, groove_v in [
            ("groove_v_front", front_groove_v),
            ("groove_v_back", back_groove_v),
        ]:
            rail = rail.cut(groove_v)
            profile_cutters.append(groove_v)
            profile_cutter_names.append(name)

    if rail_groove_slot_depth > 0 and rail_groove_slot_height > 0:
        slot_overshoot = 0.1
        groove_slot = create_rounded_slab(
            rail_groove_slot_depth + slot_overshoot,
            rail_groove_slot_height,
            length_mm + 2 * slot_overshoot,
            rail_groove_slot_height / 2,
        )
        groove_slot = rotate(90, axis=(0, 1, 0))(groove_slot)
        groove_slot = rotate(-90, axis=(1, 0, 0))(groove_slot)
        groove_slot = translate(
            -slot_overshoot,
            0,
            rail_groove_z_center + rail_groove_slot_height / 2,
        )(groove_slot)
        front_groove_slot = align(
            groove_slot,
            rail,
            Alignment.STACK_FRONT,
            stack_gap=-rail_groove_slot_depth,
        )
        back_groove_slot = align(
            groove_slot,
            rail,
            Alignment.STACK_BACK,
            stack_gap=-rail_groove_slot_depth,
        )
        for name, groove_slot_cutter in [
            ("groove_slot_front", front_groove_slot),
            ("groove_slot_back", back_groove_slot),
        ]:
            rail = rail.cut(groove_slot_cutter)
            profile_cutters.append(groove_slot_cutter)
            profile_cutter_names.append(name)

    rail_without_holes = rail

    rail_mount_holes = []
    if hole_index > 1:
        holes = align(holes, rail, Alignment.CENTER, axes=[0, 1])
        holes = align(holes, rail, Alignment.TOP)
        rail = rail.cut(holes.leader)
        rail_mount_holes = holes.get_named_follower_items()

    rail = LeaderFollowersCuttersPart(rail)
    rail.add_named_follower(rail.leader, "rail_body")
    if rail_mount_holes:
        rail.add_named_cutter(holes.leader, "rail_mount_holes")
    rail.add_named_cutter(rail_without_holes, "rail_without_holes")
    for name, hole in rail_mount_holes:
        rail.add_named_cutter(hole, name)
    return rail


def create_mgn7h_rail_with_carriage(
    *,
    length_mm: float,
    mgn7h_rail_mount_hole_drill_extra_length,
    mgn7h_rail_mock_clearance,
    mgn7h_rail_mock_side_clearance,
    mgn7h_rail_mock_top_clearance,
    mgn7h_rail_mock_groove_clearance,
    mgn7h_rail_mock_groove_height_clearance,
    mgn7h_carriage_mount_hole_drill_extra_length,
    carriage_offset,
):
    """Create an MGN7H rail assembly with a built-in carriage follower."""

    rail = create_mgn7h_rail(
        length_mm=length_mm,
        mgn7h_rail_mount_hole_drill_extra_length=(
            mgn7h_rail_mount_hole_drill_extra_length
        ),
    )
    printable_rail = create_mgn7h_rail(
        length_mm=length_mm,
        mgn7h_rail_mount_hole_drill_extra_length=(
            mgn7h_rail_mount_hole_drill_extra_length
        ),
        rail_width=mgn_7h_rail_width
        - 2 * (mgn7h_rail_mock_clearance + mgn7h_rail_mock_side_clearance),
        rail_height=mgn_7h_rail_height
        - 2 * mgn7h_rail_mock_clearance
        - mgn7h_rail_mock_top_clearance,
        rail_groove_z_center=mgn_7h_rail_groove_z_center - mgn7h_rail_mock_clearance,
        rail_groove_v_height=mgn_7h_rail_groove_v_height
        + 2 * mgn7h_rail_mock_groove_height_clearance,
        rail_groove_v_depth=mgn_7h_rail_groove_v_depth
        + mgn7h_rail_mock_groove_clearance,
        rail_groove_slot_height=mgn_7h_rail_groove_slot_height
        + 2 * mgn7h_rail_mock_groove_height_clearance,
        rail_groove_slot_depth=mgn_7h_rail_groove_slot_depth
        + mgn7h_rail_mock_groove_clearance,
    )
    printable_rail = translate(
        0,
        mgn7h_rail_mock_clearance + mgn7h_rail_mock_side_clearance,
        mgn7h_rail_mock_clearance,
    )(printable_rail)
    rail.add_named_follower(printable_rail.leader, "rail_mockup_printable")

    carriage = create_mgn7h_carriage(
        mgn7h_carriage_mount_hole_drill_extra_length=(
            mgn7h_carriage_mount_hole_drill_extra_length
        ),
    )
    carriage = align(carriage, rail, Alignment.CENTER, axes=[0, 1])
    carriage = translate(carriage_offset, 0, 0)(carriage)

    carriage = carriage.cut(rail.get_named_cutter("rail_without_holes"))

    rail.add_named_follower(carriage.leader, name="carriage")
    rail = rail.merge_except_leader(carriage)

    return rail


def create_mgn7h_rail_with_carriage_assembly(
    *,
    mgn7h_rail_length,
    mgn7h_rail_mount_hole_drill_extra_length,
    mgn7h_rail_mock_clearance,
    mgn7h_rail_mock_side_clearance,
    mgn7h_rail_mock_top_clearance,
    mgn7h_rail_mock_groove_clearance,
    mgn7h_rail_mock_groove_height_clearance,
    mgn7h_carriage_mount_hole_drill_extra_length,
    mgn7h_carriage_rest_offset_on_rail,
):
    """Create an MGN7H rail leader with a named built-in carriage follower."""

    record_length_metric("linear_rail", "MGN7H", "idex_tap_t1", mgn7h_rail_length)

    return create_mgn7h_rail_with_carriage(
        length_mm=mgn7h_rail_length,
        mgn7h_rail_mount_hole_drill_extra_length=(
            mgn7h_rail_mount_hole_drill_extra_length
        ),
        carriage_offset=mgn7h_carriage_rest_offset_on_rail,
        mgn7h_rail_mock_clearance=mgn7h_rail_mock_clearance,
        mgn7h_rail_mock_side_clearance=mgn7h_rail_mock_side_clearance,
        mgn7h_rail_mock_top_clearance=mgn7h_rail_mock_top_clearance,
        mgn7h_rail_mock_groove_clearance=mgn7h_rail_mock_groove_clearance,
        mgn7h_rail_mock_groove_height_clearance=(
            mgn7h_rail_mock_groove_height_clearance
        ),
        mgn7h_carriage_mount_hole_drill_extra_length=(
            mgn7h_carriage_mount_hole_drill_extra_length
        ),
    )
