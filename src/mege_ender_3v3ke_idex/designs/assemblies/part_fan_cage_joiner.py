"""Join part fan and extruder cage assemblies with a shared flange."""

import logging

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


def _create_flange_block(width, depth, height, fillet_radius, attachment_alignment):
    if fillet_radius > 0:
        return create_filleted_box(
            width,
            depth,
            height,
            fillet_radius=fillet_radius,
            no_fillets_at=[attachment_alignment, Alignment.TOP, Alignment.BOTTOM],
        )
    return create_box(width, depth, height)


def _flange_layout(anchor_part, extension_alignment, flange_extension):
    anchor_size = get_bounding_box_size(anchor_part)
    if extension_alignment == Alignment.STACK_LEFT:
        return {
            "flange_size": (anchor_size[0] + flange_extension, anchor_size[1]),
            "tab_size": (flange_extension, anchor_size[1]),
            "attachment_alignment": Alignment.RIGHT,
            "center_axes": [1],
        }
    if extension_alignment == Alignment.STACK_RIGHT:
        return {
            "flange_size": (anchor_size[0] + flange_extension, anchor_size[1]),
            "tab_size": (flange_extension, anchor_size[1]),
            "attachment_alignment": Alignment.LEFT,
            "center_axes": [1],
        }
    if extension_alignment == Alignment.STACK_BACK:
        return {
            "flange_size": (anchor_size[0], anchor_size[1] + flange_extension),
            "tab_size": (anchor_size[0], flange_extension),
            "attachment_alignment": Alignment.FRONT,
            "center_axes": [0],
        }
    if extension_alignment == Alignment.STACK_FRONT:
        return {
            "flange_size": (anchor_size[0], anchor_size[1] + flange_extension),
            "tab_size": (anchor_size[0], flange_extension),
            "attachment_alignment": Alignment.BACK,
            "center_axes": [0],
        }
    raise ValueError(f"Unsupported flange extension alignment: {extension_alignment}")


def _create_join_flange_halves(
    *,
    anchor_part=None,
    side_mount_plate=None,
    extension_alignment=Alignment.STACK_LEFT,
    flange_extension,
    flange_half_height,
    screw_size,
    clearance_type,
    fillet_radius,
):
    if anchor_part is None:
        anchor_part = side_mount_plate
    layout = _flange_layout(
        anchor_part,
        extension_alignment,
        flange_extension,
    )
    flange_width, flange_depth = layout["flange_size"]
    tab_width, tab_depth = layout["tab_size"]
    attachment_alignment = layout["attachment_alignment"]
    center_axes = layout["center_axes"]

    bottom_flange = _create_flange_block(
        flange_width,
        flange_depth,
        flange_half_height,
        fillet_radius,
        attachment_alignment,
    )
    bottom_flange = align(
        bottom_flange,
        anchor_part,
        Alignment.CENTER,
        axes=center_axes,
    )
    bottom_flange = align(bottom_flange, anchor_part, attachment_alignment)
    bottom_flange = align(bottom_flange, anchor_part, Alignment.TOP)

    top_flange = _create_flange_block(
        flange_width,
        flange_depth,
        flange_half_height,
        fillet_radius,
        attachment_alignment,
    )
    top_flange = align(top_flange, bottom_flange, Alignment.CENTER, axes=[0, 1])
    top_flange = align(top_flange, bottom_flange, Alignment.STACK_TOP)

    tab_reference = create_box(tab_width, tab_depth, flange_half_height)
    tab_reference = align(
        tab_reference,
        anchor_part,
        Alignment.CENTER,
        axes=center_axes,
    )
    tab_reference = align(tab_reference, anchor_part, extension_alignment)
    tab_reference = align(tab_reference, anchor_part, Alignment.TOP)

    flange_stack = bottom_flange.fuse(top_flange)
    clearance_hole = create_cylinder(
        get_clearance_hole_diameter(screw_size, clearance_type) / 2,
        flange_half_height * 2 + 2,
    )
    clearance_hole = align(clearance_hole, flange_stack, Alignment.CENTER)
    clearance_hole = align(clearance_hole, tab_reference, Alignment.CENTER, axes=[0, 1])

    bottom_flange = bottom_flange.cut(clearance_hole)
    top_flange = top_flange.cut(clearance_hole)

    return bottom_flange, top_flange, clearance_hole


def join_part_fans_with_extruder_cage(
    *,
    part_fans,
    extruder_cage,
    belt_carriage=None,
    sprite_extruder=None,
    flange_extension=8.0,
    flange_half_height=3.0,
    screw_size="M3",
    clearance_type="loose",
    fillet_radius=0.0,
    mgn7h_rail_with_carriage=None,
    idex_tap_t1=None,
):
    """Return joined output assemblies for a part fan and extruder cage pair."""

    flange_specs = [
        ("side_mount_plate", Alignment.STACK_LEFT),
        ("duct_back_mount_plate_connector", Alignment.STACK_BACK),
    ]

    bottom_flanges = []
    top_flanges = []
    consumed_part_fan_refs = []
    for anchor_name, extension_alignment in flange_specs:
        anchor_part = part_fans.get_named_non_production_part(anchor_name)
        consumed_part_fan_refs.append(
            part_fans.part_ref_for_named_non_production_part(anchor_name)
        )
        bottom_flange, top_flange, _ = _create_join_flange_halves(
            anchor_part=anchor_part,
            extension_alignment=extension_alignment,
            flange_extension=flange_extension,
            flange_half_height=flange_half_height,
            screw_size=screw_size,
            clearance_type=clearance_type,
            fillet_radius=fillet_radius,
        )
        bottom_flanges.append(bottom_flange)
        top_flanges.append(top_flange)

    joined_part_fans = LeaderFollowersCuttersPart(part_fans.leader.copy())
    for name, follower in part_fans.get_named_follower_items():
        if name in [anchor_name for anchor_name, _ in flange_specs]:
            continue
        joined_part_fans.add_named_follower(follower.copy(), name)

    for name, nfp in part_fans.get_named_non_production_part_items():
        if name in [anchor_name for anchor_name, _ in flange_specs]:
            continue
        joined_part_fans.add_named_non_production_part(nfp.copy(), name)

    for name, cutter in part_fans.get_named_cutter_items():
        joined_part_fans.add_named_cutter(cutter.copy(), name)

    joined_extruder_cage = LeaderFollowersCuttersPart(extruder_cage.leader.copy())
    for name, follower in extruder_cage.get_named_follower_items():
        if name in [anchor_name for anchor_name, _ in flange_specs]:
            continue
        joined_extruder_cage.add_named_follower(follower.copy(), name)
    for name, nfp in extruder_cage.get_named_non_production_part_items():
        if name in [anchor_name for anchor_name, _ in flange_specs]:
            continue
        joined_extruder_cage.add_named_non_production_part(nfp.copy(), name)
    for name, cutter in extruder_cage.get_named_cutter_items():
        if name in [anchor_name for anchor_name, _ in flange_specs]:
            continue
        joined_extruder_cage.add_named_cutter(cutter.copy(), name)

    joined_idex_tap_t1 = idex_tap_t1.copy() if idex_tap_t1 is not None else None

    for bottom_flange in bottom_flanges:
        joined_part_fans.leader = joined_part_fans.leader.fuse(bottom_flange)
    for top_flange in top_flanges:
        joined_extruder_cage.leader = joined_extruder_cage.leader.fuse(top_flange)
    for consumed_part_fan_ref in consumed_part_fan_refs:
        _logger.info(f"Adding consumed part ref for {consumed_part_fan_ref}")
        joined_part_fans.add_consumed_part_ref(consumed_part_fan_ref)

    if belt_carriage is not None:
        mount_eye_width = 12.5
        mount_eye_depth = 5
        mount_eye_height = 20
        mount_eye_l_depth = 10
        mount_eye_l_thickness = 3

        belt_carriage_mount_eye = create_box(
            mount_eye_width, mount_eye_depth, mount_eye_height
        )
        belt_carriage_mount_eye = align(
            belt_carriage_mount_eye, belt_carriage, Alignment.CENTER
        )
        belt_carriage_mount_eye = align(
            belt_carriage_mount_eye, belt_carriage, Alignment.TOP
        )
        belt_carriage_mount_eye = align(
            belt_carriage_mount_eye, belt_carriage, Alignment.STACK_FRONT
        )
        belt_carriage_mount_eye = align(
            belt_carriage_mount_eye, sprite_extruder, Alignment.STACK_RIGHT, stack_gap=1
        )

        belt_carriage_mount_eye_l = create_box(
            mount_eye_width, mount_eye_l_depth, mount_eye_l_thickness
        )
        belt_carriage_mount_eye_l = align(
            belt_carriage_mount_eye_l, belt_carriage_mount_eye, Alignment.CENTER
        )
        belt_carriage_mount_eye_l = align(
            belt_carriage_mount_eye_l, belt_carriage_mount_eye, Alignment.STACK_FRONT
        )
        belt_carriage_mount_eye_l = align(
            belt_carriage_mount_eye_l, belt_carriage_mount_eye, Alignment.TOP
        )

        belt_carriage_mount_eye = belt_carriage_mount_eye.fuse(
            belt_carriage_mount_eye_l
        )

        right_clamp_hole_drill = belt_carriage.get_named_cutter(
            "right_clamp_hole_drill"
        )

        joined_extruder_cage = joined_extruder_cage.fuse(belt_carriage_mount_eye)
        joined_extruder_cage = joined_extruder_cage.cut(right_clamp_hole_drill)

        left_bridge_hole_drill = belt_carriage.get_named_cutter(
            "left_bridge_hole_drill"
        )

        left_bridge_mount_eye_width = 8
        left_bridge_mount_eye_depth = 3
        left_bridge_mount_eye_height = 30
        left_bridge_mount_eye = create_box(
            left_bridge_mount_eye_width,
            left_bridge_mount_eye_depth,
            left_bridge_mount_eye_height,
        )
        left_bridge_mount_eye = align(
            left_bridge_mount_eye, left_bridge_hole_drill, Alignment.CENTER
        )

        left_bridge_mount_eye = align(
            left_bridge_mount_eye, sprite_extruder, Alignment.STACK_BACK
        )
        left_bridge_mount_eye = align(
            left_bridge_mount_eye, joined_extruder_cage, Alignment.TOP
        )

        left_bridge_mount_eye = align(
            left_bridge_mount_eye, joined_extruder_cage, Alignment.LEFT
        )

        left_bridge_mount_eye = left_bridge_mount_eye.cut(left_bridge_hole_drill)
        joined_extruder_cage = joined_extruder_cage.fuse(left_bridge_mount_eye)

    if mgn7h_rail_with_carriage is not None:
        back_plate = materialize_bounding_box(
            mgn7h_rail_with_carriage, y_size=3, x_enlargement=5
        )
        back_plate = align(back_plate, mgn7h_rail_with_carriage, Alignment.STACK_FRONT)
        joined_extruder_cage = joined_extruder_cage.cut(back_plate)

        full_bbox_cutter = materialize_bounding_box(
            mgn7h_rail_with_carriage,
            x_enlargement=0.1,
            y_enlargement=0.1,
            z_enlargement=0.1,
        )

        carriage = mgn7h_rail_with_carriage.get_named_follower("carriage")
        carriage_size = get_bounding_box_size(carriage)
        joined_extruder_cage = joined_extruder_cage.cut(full_bbox_cutter)
        carriage_cutter = materialize_bounding_box(
            carriage,
            x_enlargement=0.8,
            y_enlargement=0.6,
            z_enlargement=18,
        )
        joined_extruder_cage = joined_extruder_cage.cut(carriage_cutter)
        for name, cutter in mgn7h_rail_with_carriage.get_named_cutter_items():
            if name.startswith("rail_mount_hole_"):
                cutter_bbox = get_bounding_box(cutter)
                _logger.info(
                    f"Cutting extruder cage with {name}, bbox: {point_string(cutter_bbox[0])} to {point_string(cutter_bbox[1])}"
                )
                back_plate = back_plate.cut(cutter)

                m2_nut_cutter = create_nut("M2", slack=0.3, no_hole=True)
                m2_nut_cutter = rotate(90, axis=[1, 0, 0])(m2_nut_cutter)
                m2_nut_cutter = align(m2_nut_cutter, cutter, Alignment.CENTER)
                m2_nut_cutter = align(m2_nut_cutter, back_plate, Alignment.FRONT)
                back_plate = back_plate.cut(m2_nut_cutter)

                m2_nut = create_nut("M2")
                m2_nut = rotate(90, axis=[1, 0, 0])(m2_nut)
                m2_nut = align(m2_nut, m2_nut_cutter, Alignment.CENTER)
                m2_nut = align(m2_nut, back_plate, Alignment.FRONT)

                joined_extruder_cage.add_named_non_production_part(
                    m2_nut, f"m2_nut_{name}"
                )

            else:
                _logger.info(f"Skipping cutting extruder cage with {name}")
        joined_extruder_cage = joined_extruder_cage.fuse(back_plate)

        bottom_stopper = materialize_bounding_box(
            mgn7h_rail_with_carriage,
            z_size=2,
            y_enlargement=0.5,
            x_size=carriage_size[0],
        )

        bottom_stopper = align(
            bottom_stopper, mgn7h_rail_with_carriage, Alignment.STACK_BOTTOM
        )
        joined_extruder_cage = joined_extruder_cage.fuse(bottom_stopper)

        for lr in [Alignment.LEFT, Alignment.RIGHT]:
            magnet_screw_length = 6
            magnet_screw = create_conical_head_screw("M3", magnet_screw_length)

            magnet_screw = LeaderFollowersCuttersPart(magnet_screw)

            magnet_screw_thread_hole_cutter = create_self_threading_hole_cutter(
                "M3",
                magnet_screw_length + 2,
                core_radius_adjustment=-0.35,
                lead_in=True,
            )

            magnet_screw_thread_hole_cutter = align(
                magnet_screw_thread_hole_cutter, magnet_screw, Alignment.CENTER
            )
            magnet_screw_thread_hole_cutter = align(
                magnet_screw_thread_hole_cutter, magnet_screw, Alignment.TOP
            )
            magnet_screw_thread_hole_cutter = translate(
                0, 0, -MScrew.from_size("M3").conical_head_height
            )(magnet_screw_thread_hole_cutter)

            magnet_screw.add_named_cutter(
                magnet_screw_thread_hole_cutter, "thread_hole_cutter"
            )

            magnet_screw_head_cutter = create_cone(
                radius1=3 / 2,
                radius2=MScrew.from_size("M3").conical_head_diameter / 2 + 0.2,
                height=MScrew.from_size("M3").conical_head_height + 0.1,
            )
            magnet_screw_head_cutter = align(
                magnet_screw_head_cutter, magnet_screw, Alignment.CENTER
            )
            magnet_screw_head_cutter = align(
                magnet_screw_head_cutter, magnet_screw, Alignment.TOP
            )
            magnet_screw.add_named_cutter(magnet_screw_head_cutter, "head_cutter")
            magnet_screw_top_cutter = create_box(50, 50, 50)
            magnet_screw_top_cutter = align(
                magnet_screw_top_cutter, magnet_screw, Alignment.CENTER
            )
            magnet_screw_top_cutter = align(
                magnet_screw_top_cutter, magnet_screw, Alignment.STACK_TOP
            )
            magnet_screw.add_named_cutter(magnet_screw_top_cutter, "top_cutter")

            magnet = create_cylinder(
                6 / 2, 3
            )  # cylindrical magnet, 6mm diameter, 3mm height

            magnet = align(magnet, magnet_screw, Alignment.CENTER)
            magnet = align(magnet, magnet_screw, Alignment.STACK_TOP)

            magnet_screw.add_named_non_production_part(magnet, "magnet")

            magnet_screw = rotate(180 + 45, axis=[1, 0, 0])(magnet_screw)

            magnet_screw = align(magnet_screw, carriage, Alignment.CENTER)

            magnet_screw = align(magnet_screw, carriage, Alignment.BACK)

            magnet_screw = align(
                magnet_screw, carriage, lr.stack_alignment, stack_gap=4
            )

            magnet_screw = translate(0, 0, -4)(magnet_screw)

            joined_extruder_cage.add_named_non_production_part(
                magnet_screw.leader, f"magnet_screw_{lr.name}"
            )

            magnet_screw_holder = materialize_bounding_box(
                magnet_screw, x_enlargement=1, y_enlargement=3, z_enlargement=2
            )

            magnet_screw_holder = align(magnet_screw_holder, carriage, Alignment.BACK)
            magnet_screw_holder = translate(0, -0.5, 0)(magnet_screw_holder)

            magnet_screw_holder = magnet_screw.use_as_cutter_on(magnet_screw_holder)
            joined_extruder_cage = joined_extruder_cage.fuse(magnet_screw_holder)

            for name, cutter in magnet_screw.get_named_cutter_items():
                if name in ["thread_hole_cutter"]:
                    joined_extruder_cage = joined_extruder_cage.cut(cutter)

            if joined_idex_tap_t1 is not None:
                joined_idex_tap_t1.add_named_non_production_part(
                    magnet_screw.get_named_non_production_part("magnet"),
                    f"magnet_{lr.name}",
                )

    result = {
        "part_fans": joined_part_fans,
        "extruder_cage": joined_extruder_cage,
    }
    if joined_idex_tap_t1 is not None:
        result["idex_tap_t1"] = joined_idex_tap_t1

    return result
