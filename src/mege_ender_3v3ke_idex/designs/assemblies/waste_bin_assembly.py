"""Standalone waste bin assembly."""

from shellforgepy.simple import *

waste_bin_mount_plate_thickness = 4.0
waste_bin_mount_plate_depth = 19
waste_bin_mount_plate_outside_offset = 17
waste_bin_body_nozzle_clearance = 3
waste_bin_mount_screw_size = "M3"
waste_bin_mount_screw_length = 8
waste_bin_vertical_mount_plate_depth = 2.5
waste_bin_vertical_rib_depth = 6
waste_bin_vertical_rib_width = 3

waste_bin_connector_thickness = 2

waste_bin_brush_long_slit_inset = 3
waste_bin_brush_mount_screw_size = "M3"

nozzle_brush_width = 14
nozzle_brush_depth = 6
nozzle_brush_base_height = 4.6
nozzle_brush_total_height = 6.3
nozzle_brush_hairs_height = nozzle_brush_total_height - nozzle_brush_base_height


nozzle_brush_num_depth_hairs = 4
nozzle_brush_num_width_hairs = 7
nozzle_brush_hair_diameter = 1

waste_bin_brush_nozzle_overlap = 0.5

nozzle_brush_holder_wall_thickness = 2.5

nozzle_brush_holder_clearance = -0.05
nozzle_brush_holder_height = 14
nozzle_brush_holder_slider_height = 8

nozzle_brush_up_offset = 0.8

def create_nozzle_brush():
    base = create_box(nozzle_brush_width, nozzle_brush_depth, nozzle_brush_base_height)
    hairs = PartCollector()
    hair_x_pitch = nozzle_brush_width / nozzle_brush_num_width_hairs
    hair_y_pitch = nozzle_brush_depth / nozzle_brush_num_depth_hairs
    for depth_index in range(nozzle_brush_num_depth_hairs):
        for width_index in range(nozzle_brush_num_width_hairs):
            hair = create_cylinder(
                nozzle_brush_hair_diameter / 2, nozzle_brush_hairs_height
            )
            hair = translate(
                width_index * hair_x_pitch,
                depth_index * hair_y_pitch,
                0,
            )(hair)
            hairs = hairs.fuse(hair)

    hairs = align(hairs, base, Alignment.CENTER)
    hairs = align(hairs, base, Alignment.STACK_TOP)

    brush = base.fuse(hairs)

    return brush


def create_waste_bin_assembly(
    *,
    sprite_extruder,
    x_axis_bottom_profile,
    waste_bin_width,
    waste_bin_depth,
    waste_bin_height,
    waste_bin_wall_thickness,
    waste_bin_fillet_radius,
):
    """Create the waste bin assembly."""

    body = create_filleted_box(
        waste_bin_width,
        waste_bin_depth,
        waste_bin_height,
        fillet_radius=waste_bin_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )

    body_cutter = materialize_bounding_box(
        body,
        x_enlargement=-2 * waste_bin_wall_thickness,
        y_enlargement=-2 * waste_bin_wall_thickness,
    )
    body_cutter = align(body_cutter, body, Alignment.BOTTOM)
    body_cutter = translate(0, 0, waste_bin_wall_thickness)(body_cutter)

    body = body.cut(body_cutter)

    hotend = sprite_extruder.get_named_non_production_part("hotend")

    body = align(body, hotend, Alignment.CENTER)
    body = align(
        body, hotend, Alignment.STACK_BOTTOM, stack_gap=waste_bin_body_nozzle_clearance
    )
    base = body
    nozzle_brush_mount_hole_diameter = MScrew.from_size(
        waste_bin_brush_mount_screw_size
    ).clearance_hole_loose

    cut_size = 5 * waste_bin_wall_thickness

    nozzle_brush_long_slit_cutter = PartCollector()

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        nozzle_brush_long_slit_cutter_part = create_rounded_slab(
            waste_bin_height - 2 * waste_bin_brush_long_slit_inset,
            nozzle_brush_mount_hole_diameter,
            cut_size,
            nozzle_brush_mount_hole_diameter / 2,
        )

        nozzle_brush_long_slit_cutter_part = rotate(90, axis=(0, 1, 0))(
            nozzle_brush_long_slit_cutter_part
        )

        nozzle_brush_long_slit_cutter_part = align(
            nozzle_brush_long_slit_cutter_part, body, Alignment.CENTER
        )
        nozzle_brush_long_slit_cutter_part = align(
            nozzle_brush_long_slit_cutter_part,
            body,
            lr.stack_alignment,
            stack_gap=-cut_size / 2,
        )
        nozzle_brush_long_slit_cutter = nozzle_brush_long_slit_cutter.fuse(
            nozzle_brush_long_slit_cutter_part
        )

    profile_size = get_bounding_box_size(x_axis_bottom_profile)
    profile_width = profile_size[1]
    mount_plates = PartCollector()
    mount_screws = []
    moount_plates_dict = {}
    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        mount_plate = create_box(
            profile_width,
            waste_bin_mount_plate_depth,
            waste_bin_mount_plate_thickness,
        )

        mount_plate = align(mount_plate, x_axis_bottom_profile, Alignment.CENTER)
        mount_plate = align(mount_plate, x_axis_bottom_profile, Alignment.FRONT)
        mount_plate = align(mount_plate, x_axis_bottom_profile, Alignment.STACK_BOTTOM)
        mount_plate = align(mount_plate, body, lr)
        mount_plate = translate(lr.sign * waste_bin_mount_plate_outside_offset, 0, 0)(
            mount_plate
        )

        mount_screw = create_complete_screw_assembly(
            waste_bin_mount_screw_size, waste_bin_mount_screw_length
        )

        mount_screw = rotate(180, axis=(1, 0, 0))(mount_screw)
        mount_screw = align(mount_screw, mount_plate, Alignment.CENTER)
        mount_screw = align(
            mount_screw, x_axis_bottom_profile, Alignment.CENTER, axes=[1]
        )

        mount_screw = align(mount_screw, mount_plate, Alignment.BOTTOM)

        mount_screws.append(mount_screw)

        mount_plates = mount_plates.fuse(mount_plate)

        moount_plates_dict[lr] = mount_plate

    for mount_screw in mount_screws:

        mount_plates = mount_screw.use_as_cutter_on(mount_plates)

    body_bbox = get_bounding_box(body)
    body_size = get_bounding_box_size(body)

    vertical_mount_plates = PartCollector()
    for lr, mount_plate in moount_plates_dict.items():
        mount_plate_bbox = get_bounding_box(mount_plate)

        height = mount_plate_bbox[1][2] - body_bbox[0][2]

        vertical_mount_plate = materialize_bounding_box(
            mount_plate, z_size=height, y_size=waste_bin_vertical_mount_plate_depth
        )

        vertical_mount_plate = align(vertical_mount_plate, mount_plate, Alignment.BACK)
        vertical_mount_plate = align(vertical_mount_plate, mount_plate, Alignment.TOP)

        connector_depth = mount_plate_bbox[1][1] - body_bbox[0][1]

        connector = create_box(
            waste_bin_connector_thickness, connector_depth, body_size[2]
        )
        connector = align(connector, vertical_mount_plate, Alignment.CENTER)
        connector = align(connector, vertical_mount_plate, Alignment.BOTTOM)
        connector = align(connector, vertical_mount_plate, Alignment.BACK)
        connector = align(connector, body, lr)

        rib = materialize_bounding_box(
            vertical_mount_plate,
            y_size=waste_bin_vertical_rib_depth,
            x_size=waste_bin_vertical_rib_width,
        )
        rib = align(rib, vertical_mount_plate, Alignment.STACK_FRONT)
        rib = align(rib, vertical_mount_plate, lr.opposite)

        vertical_mount_plate = vertical_mount_plate.fuse(connector)

        connector_angle_part = create_right_triangle(
            waste_bin_mount_plate_depth,
            waste_bin_mount_plate_depth,
            waste_bin_wall_thickness,
            extrusion_direction=(1, 0, 0),
            a_normal=(0, 1, 0),
            b_normal=(0, 0, -1),
        )

        connector_angle_part = align(
            connector_angle_part, vertical_mount_plate, Alignment.CENTER
        )
        connector_angle_part = align(connector_angle_part, mount_plate, Alignment.BACK)
        connector_angle_part = align(
            connector_angle_part, mount_plate, Alignment.STACK_BOTTOM
        )

        connector_angle_part = align(connector_angle_part, mount_plate, lr.opposite)

        vertical_mount_plate = vertical_mount_plate.fuse(connector_angle_part)
        vertical_mount_plate = vertical_mount_plate.fuse(rib)

        vertical_mount_plates = vertical_mount_plates.fuse(vertical_mount_plate)

    body = body.fuse(vertical_mount_plates)

    body = body.fuse(mount_plates)

    body = body.cut(nozzle_brush_long_slit_cutter)

    nozzle_brush = create_nozzle_brush()
    nozzle_brush = rotate(90)(nozzle_brush)

    nozzle_brush = align(nozzle_brush, hotend, Alignment.CENTER)

    nozzle_brush = align(nozzle_brush, base, Alignment.RIGHT)
    nozzle_brush = align(
        nozzle_brush,
        hotend,
        Alignment.STACK_BOTTOM,
        stack_gap=-waste_bin_brush_nozzle_overlap,
    )

    nozzle_brush = translate(
        -waste_bin_wall_thickness
        - nozzle_brush_holder_wall_thickness
        - nozzle_brush_holder_clearance,
        0,
        0,
    )(nozzle_brush)

    nozzle_brush_holder = materialize_bounding_box(
        nozzle_brush,
        x_enlargement=2 * nozzle_brush_holder_wall_thickness
        + 2 * nozzle_brush_holder_clearance,
        y_enlargement=2 * nozzle_brush_holder_wall_thickness
        + 2 * nozzle_brush_holder_clearance,
        z_size=nozzle_brush_holder_height,
    )


    nozzle_brush_cutter = materialize_bounding_box(
        nozzle_brush,
        x_enlargement=2 * nozzle_brush_holder_clearance,
        y_enlargement=2 * nozzle_brush_holder_clearance,
        z_enlargement=2 * nozzle_brush_holder_clearance,
    )

    nozzle_brush_holder = align(
        nozzle_brush_holder,
        nozzle_brush,
        Alignment.STACK_BOTTOM,
        stack_gap=-nozzle_brush_base_height+nozzle_brush_up_offset,
    )
    nozzle_brush_holder = nozzle_brush_holder.cut(nozzle_brush_cutter)

    slider_width = MScrew.from_size(waste_bin_brush_mount_screw_size).core_hole + 0.45
    nozzle_brush_holder_slider = create_rounded_slab(
        nozzle_brush_holder_slider_height,
        slider_width,
        nozzle_brush_holder_wall_thickness,
        slider_width / 2,
    )
    nozzle_brush_holder_slider = rotate(90, axis=(0, 1, 0))(nozzle_brush_holder_slider)
    nozzle_brush_holder_slider = align(
        nozzle_brush_holder_slider, nozzle_brush_long_slit_cutter, Alignment.CENTER
    )
    nozzle_brush_holder_slider = align(
        nozzle_brush_holder_slider, nozzle_brush_holder, Alignment.BOTTOM
    )
    nozzle_brush_holder_slider = align(
        nozzle_brush_holder_slider, base, Alignment.RIGHT
    )
    nozzle_brush_holder_slider = translate(-nozzle_brush_holder_clearance, 0, 0)(
        nozzle_brush_holder_slider
    )

    nozzle_brush_holder = nozzle_brush_holder.fuse(nozzle_brush_holder_slider)
    nozzle_brush_holder_size = get_bounding_box_size(nozzle_brush_holder)
    nozzle_brlush_holder_screw_length = int(nozzle_brush_holder_size[1] / 4) * 4

    nozzle_brush_holder_screw = create_complete_screw_assembly(
        waste_bin_brush_mount_screw_size,
        nozzle_brlush_holder_screw_length,
        clearance_type="close",
    )
    nozzle_brush_holder_screw = rotate(90, axis=(0, 1, 0))(nozzle_brush_holder_screw)
    nozzle_brush_holder_screw = align(
        nozzle_brush_holder_screw, nozzle_brush_holder_slider, Alignment.CENTER
    )
    nozzle_brush_holder_screw = align(
        nozzle_brush_holder_screw, nozzle_brush_holder_slider, Alignment.RIGHT
    )

    nozzle_brush_holder = nozzle_brush_holder_screw.use_as_cutter_on(
        nozzle_brush_holder
    )

    threaded_insert = create_thread_inset_assembly(
        waste_bin_brush_mount_screw_size,
        6,
        extra_radius=0,
        thread_inset_hole_radius_adjustment=-0.35,
        clearance_type="close",
    )

    threaded_insert = rotate(90, axis=(0, 1, 0))(threaded_insert)
    threaded_insert = align(
        threaded_insert, nozzle_brush_holder_screw, Alignment.CENTER
    )
    threaded_insert = align(threaded_insert, nozzle_brush_holder, Alignment.LEFT)

    nozzle_brush_holder = threaded_insert.use_as_cutter_on(nozzle_brush_holder)

    thread_inset_boss = threaded_insert.get_named_cutter("assembly_cutter")
    thread_inset_boss = nozzle_brush_holder_screw.use_as_cutter_on(thread_inset_boss)
    nozzle_brush_holder = nozzle_brush_holder.fuse(thread_inset_boss)

    nozzle_brush_holder = threaded_insert.use_as_cutter_on(nozzle_brush_holder)

    retval = LeaderFollowersCuttersPart(
        leader=body,
    )

    retval.add_named_non_production_part(nozzle_brush, "nozzle_brush")
    retval.add_named_follower(nozzle_brush_holder, "nozzle_brush_holder")
    retval.add_named_non_production_part(
        threaded_insert.get_named_non_production_part("thread_inset"),
        "nozzle_brush_holder_threaded_insert",
    )
    retval.add_named_non_production_part(
        nozzle_brush_holder_screw.get_named_non_production_part("complete_screw"),
        "nozzle_brush_holder_screw",
    )
    for i, mount_screw in enumerate(mount_screws):
        retval.add_named_non_production_part(
            mount_screw.get_named_non_production_part("complete_screw"),
            f"mount_screw_{i}",
        )

    return retval
