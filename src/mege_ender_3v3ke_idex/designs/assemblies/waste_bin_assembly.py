"""Standalone waste bin assembly."""

from shellforgepy.simple import *

waste_bin_mount_plate_thickness = 4.0
waste_bin_mount_plate_depth = 25
waste_bin_mount_plate_outside_offset = 15
waste_bin_body_nozzle_clearance = 3
waste_bin_mount_screw_size = "M3"
waste_bin_mount_screw_length = 8
waste_bin_vertical_mount_plate_depth = 4
waste_bin_connector_thickness = 2


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

        vertical_mount_plate = vertical_mount_plate.fuse(connector)

        vertical_mount_plates = vertical_mount_plates.fuse(vertical_mount_plate)

    body = body.fuse(vertical_mount_plates)

    body = body.fuse(mount_plates)

    retval = LeaderFollowersCuttersPart(
        leader=body,
    )

    for i, mount_screw in enumerate(mount_screws):
        retval.add_named_non_production_part(
            mount_screw.get_named_non_production_part("complete_screw"),
            f"mount_screw_{i}",
        )

    return retval
