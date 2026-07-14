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


def create_mgn7h_carriage(
    *,
    carriage_length,
    carriage_width,
    carriage_height,
    carriage_h1_offset,
    carriage_mount_hole_pitch_x,
    carriage_mount_hole_pitch_y,
    carriage_mount_hole_depth,
    carriage_mount_screw_size,
):
    """Create an MGN7H carriage reference part."""

    screw_hole_diameter = MScrew.from_size(
        carriage_mount_screw_size
    ).clearance_hole_normal

    carriage = create_box(carriage_length, carriage_width, carriage_height)

    holes = PartCollector()
    individual_holes = []
    for x in [-carriage_mount_hole_pitch_x / 2, carriage_mount_hole_pitch_x / 2]:
        for y in [-carriage_mount_hole_pitch_y / 2, carriage_mount_hole_pitch_y / 2]:
            hole = create_cylinder(screw_hole_diameter / 2, carriage_height)
            hole = translate(x, y, 0)(hole)
            individual_holes.append(hole)
            holes = holes.fuse(hole)

    holes = align(holes, carriage, Alignment.CENTER)
    holes = align(
        holes,
        carriage,
        Alignment.STACK_TOP,
        stack_gap=-carriage_mount_hole_depth,
    )
    holes_aligner_xy = align_translation(holes, carriage, Alignment.CENTER)
    holes_aligner_z = align_translation(
        holes,
        carriage,
        Alignment.STACK_TOP,
        stack_gap=-carriage_mount_hole_depth,
    )
    individual_holes = [holes_aligner_xy(hole) for hole in individual_holes]
    individual_holes = [holes_aligner_z(hole) for hole in individual_holes]

    carriage = carriage.cut(holes)

    carriage = LeaderFollowersCuttersPart(carriage, cutters=[holes])
    carriage.add_named_cutter(holes, "mount_holes")
    for index, hole in enumerate(individual_holes):
        carriage.add_named_cutter(hole, f"mount_hole_{index + 1}")
    carriage.add_named_follower(carriage.leader, "body")

    carriage = translate(0, 0, carriage_h1_offset)(carriage)

    return carriage


def create_mgn7h_rail(
    *,

    length_mm: float,
    mount_hole_drill_extra_length,
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


    num_holes = int((length_mm / mgn_7h_rail_mount_hole_pitch) + 1)

    holes_fused = PartCollector()
    holes_list = []
    for i in range(num_holes):
        hole_x = mgn_7h_rail_mount_hole_end_offset + i * mgn_7h_rail_mount_hole_pitch

        top_hole = create_cylinder(
            mgn_7h_rail_mount_counterbore_diameter / 2,
            mgn_7h_rail_mount_counterbore_depth,
        )
        top_hole = translate(hole_x, 0,  0)(top_hole)
        

        
        bottom_hole = create_cylinder(mgn_7h_rail_mount_hole_diameter / 2, rail_height- mgn_7h_rail_mount_counterbore_depth +mount_hole_drill_extra_length)
        bottom_hole = align(bottom_hole, top_hole, Alignment.CENTER)
        bottom_hole = align(bottom_hole, top_hole, Alignment.STACK_BOTTOM)



        current_hole = top_hole.fuse(bottom_hole)
        holes_list.append(current_hole)

        holes_fused = holes_fused.fuse(current_hole)


    
    hole_aligner = align_translation(holes_fused, rail, Alignment.CENTER)
    holes_aligned = [hole_aligner(hole) for hole in holes_list]
    holes_aligned_fused = PartCollector()
    for hole in holes_aligned:
        holes_aligned_fused = holes_aligned_fused.fuse(hole)
    
    holes_top_aligner = align_translation(
        holes_aligned_fused, rail, Alignment.TOP)

    holes_aligned = [holes_top_aligner(hole) for hole in holes_aligned]

        

        
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

    rail = LeaderFollowersCuttersPart(rail, profile_cutters)
    for index, hole in enumerate(holes_aligned):
        rail.add_named_cutter(hole, f"mounting_hole_{index + 1}")
    rail.add_named_follower(rail.leader, "rail_body")
    for index, hole in enumerate(holes_aligned):
        rail.add_named_cutter(hole, f"mounting_hole_{index + 1}")
    for name, profile_cutter in zip(profile_cutter_names, profile_cutters):
        rail.add_named_cutter(profile_cutter, name)

    return rail


def create_mgn7h_rail_with_carriage(
    *,
    length_mm: float,
    mount_hole_drill_extra_length=0,
    rail_mock_clearance,
    rail_mock_side_clearance,
    rail_mock_top_clearance,
    rail_mock_groove_clearance,
    rail_mock_groove_height_clearance,
    carriage_offset,
):
    """Create an MGN7H rail assembly with a built-in carriage follower."""

    rail = create_mgn7h_rail(
        length_mm=length_mm,
    )
    printable_rail = create_mgn7h_rail(
        length_mm=length_mm,
        mount_hole_drill_extra_length=mount_hole_drill_extra_length,
        rail_width=mgn_7h_rail_width - 2 * (rail_mock_clearance + rail_mock_side_clearance),
        rail_height=mgn_7h_rail_height - 2 * rail_mock_clearance - rail_mock_top_clearance,
        rail_groove_z_center=mgn_7h_rail_groove_z_center - rail_mock_clearance,
        rail_groove_v_height=mgn_7h_rail_groove_v_height + 2 * rail_mock_groove_height_clearance,        
        rail_groove_v_depth=mgn_7h_rail_groove_v_depth + rail_mock_groove_clearance,
        rail_groove_slot_height=mgn_7h_rail_groove_slot_height
        + 2 * rail_mock_groove_height_clearance,
        rail_groove_slot_depth=mgn_7h_rail_groove_slot_depth + rail_mock_groove_clearance,
    )
    printable_rail = translate(
        0,
        rail_mock_clearance + rail_mock_side_clearance,
        rail_mock_clearance,
    )(printable_rail)
    rail.add_named_follower(printable_rail.leader, "rail_mockup_printable")

    carriage = create_mgn7h_carriage(
    )
    carriage = align(carriage, rail.leader, Alignment.CENTER, axes=[0, 1])
    carriage = translate(carriage_offset, 0, 0)(carriage)
    carriage = carriage.prefixed_copy("carriage")

    rail.add_named_follower(carriage.leader, name="carriage")
    rail = rail.merge_except_leader(carriage)

    return rail


def create_mgn7h_rail_with_carriage_assembly(
    *,
    mgn7h_rail_length,
    rail_mock_clearance,
    rail_mock_side_clearance,
    rail_mock_top_clearance,
    rail_mock_groove_clearance,
    rail_mock_groove_height_clearance,
    mgn7h_carriage_rest_offset_on_rail,
):
    """Create an MGN7H rail leader with a named built-in carriage follower."""

    record_length_metric("linear_rail", "MGN7H", "idex_tap_t1", mgn7h_rail_length)

    return create_mgn7h_rail_with_carriage(
        length_mm=mgn7h_rail_length,
        carriage_offset=mgn7h_carriage_rest_offset_on_rail,
        rail_mock_clearance=rail_mock_clearance,
        rail_mock_side_clearance=rail_mock_side_clearance,
        rail_mock_top_clearance=rail_mock_top_clearance,
        rail_mock_groove_clearance=rail_mock_groove_clearance,
        rail_mock_groove_height_clearance=rail_mock_groove_height_clearance,
    )
