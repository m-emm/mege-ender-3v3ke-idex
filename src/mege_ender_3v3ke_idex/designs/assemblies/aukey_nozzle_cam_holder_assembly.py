"""Prototype holder plate for the placed Aukey nozzle camera."""

import logging

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


def create_aukey_nozzle_cam_holder_assembly(
    *,
    nozzle_cam,
    y_axis,
    aukey_nozzle_cam_holder_base_plate_margin,
    aukey_nozzle_cam_holder_base_plate_thickness,
    aukey_nozzle_cam_holder_base_plate_fillet_radius,
):
    """Build only the holder plate around the already-placed nozzle camera."""

    wall_clearance = 0.6
    wall_height = 4
    wall_thickness = 2
    fix_slit_width = 6
    fix_slit_depth = 3

    fix_slit_x_inset = 35
    fix_slit_y_inset = 3
    lens_cutout_margin = 5

    mount_plate_top_clearance = 1

    right_profile = y_axis.get_named_non_production_part("profile_right")

    nozzle_cam_bbox = get_bounding_box(nozzle_cam)
    profile_bbox = get_bounding_box(right_profile)

    profile_size = get_bounding_box_size(right_profile)

    camera_size = get_bounding_box_size(nozzle_cam)
    core_base_plate_width = camera_size[0] + aukey_nozzle_cam_holder_base_plate_margin
    core_base_plate_depth = (
        camera_size[1] + 4 * aukey_nozzle_cam_holder_base_plate_margin
    )

    base_plate = create_filleted_box(
        core_base_plate_width,
        core_base_plate_depth,
        aukey_nozzle_cam_holder_base_plate_thickness,
        fillet_radius=aukey_nozzle_cam_holder_base_plate_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, Alignment.RIGHT],
    )
    base_plate = align(base_plate, nozzle_cam, Alignment.CENTER)
    base_plate = align(base_plate, nozzle_cam, Alignment.STACK_TOP)

    base_plate_right_extension = create_box(
        200, core_base_plate_depth, aukey_nozzle_cam_holder_base_plate_thickness
    )
    base_plate_right_extension = align(
        base_plate_right_extension, base_plate, Alignment.CENTER
    )
    base_plate_right_extension = align(
        base_plate_right_extension, base_plate, Alignment.STACK_RIGHT
    )

    base_plate_right_extension = fit_part_between(
        base_plate_right_extension,
        cut_normal=(1, 0, 0),
        limiting_start_part=base_plate,
        limiting_end_part=right_profile,
    )

    lens = nozzle_cam.get_named_non_production_part("lens")

    lens_cutout_diameter = get_bounding_box_size(lens)[0] + lens_cutout_margin

    lens_cutout = create_cylinder(lens_cutout_diameter / 2, 500)
    lens_cutout = align(lens_cutout, lens, Alignment.CENTER)

    base_plate = base_plate.cut(lens_cutout)

    base_plate_bbox = get_bounding_box(base_plate)

    mount_plate_height = (
        profile_bbox[1][2] - mount_plate_top_clearance - base_plate_bbox[0][2]
    )

    mount_plate = create_filleted_box(
        aukey_nozzle_cam_holder_base_plate_thickness,
        core_base_plate_depth,
        mount_plate_height,
        fillet_radius=aukey_nozzle_cam_holder_base_plate_fillet_radius,
        no_fillets_at=[Alignment.RIGHT, Alignment.LEFT, Alignment.BOTTOM],
    )

    mount_plate = align(mount_plate, base_plate, Alignment.CENTER)
    mount_plate = align(mount_plate, right_profile, Alignment.TOP)
    mount_plate = align(mount_plate, right_profile, Alignment.STACK_LEFT)
    mount_plate = translate(0, 0, -mount_plate_top_clearance)(mount_plate)

    drills = PartCollector()
    for i in [0, 1]:

        m5_hole_diameter = MScrew.from_size("M5").clearance_hole_loose

        m5_hole = create_cylinder(m5_hole_diameter / 2, 500)
        m5_hole = rotate(90, axis=(0, 1, 0))(m5_hole)

        m5_hole = translate(
            0,
            i * (core_base_plate_depth - 2 * aukey_nozzle_cam_holder_base_plate_margin),
            0,
        )(m5_hole)

        drills = drills.fuse(m5_hole)

    wall = create_filleted_box(
        camera_size[0] + 2 * wall_clearance + 2 * wall_thickness,
        camera_size[1] + 2 * wall_clearance + 2 * wall_thickness,
        wall_height,
        fillet_radius=wall_thickness / 2,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    wall = align(wall, nozzle_cam, Alignment.CENTER)

    wall = align(wall, base_plate, Alignment.STACK_BOTTOM)

    camera_cutout = materialize_bounding_box(
        nozzle_cam, x_enlargement=wall_clearance, y_enlargement=wall_clearance
    )

    wall = wall.cut(camera_cutout)

    base_plate = base_plate.fuse(wall)

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            slit = create_box(fix_slit_width, fix_slit_depth, 500)
            slit = align(slit, nozzle_cam, Alignment.CENTER)
            slit = align(slit, base_plate, lr)
            slit = align(slit, base_plate, fb)
            slit = translate(
                -lr.sign * fix_slit_x_inset, -fb.sign * fix_slit_y_inset, 0
            )(slit)

            base_plate = base_plate.cut(slit)

    base_plate = base_plate.fuse(base_plate_right_extension)

    drills = align(drills, mount_plate, Alignment.CENTER)
    drills = align(drills, right_profile, Alignment.CENTER, axes=[2])

    mount_plate = mount_plate.cut(drills)

    base_plate = base_plate.fuse(mount_plate)

    return LeaderFollowersCuttersPart(leader=base_plate)
