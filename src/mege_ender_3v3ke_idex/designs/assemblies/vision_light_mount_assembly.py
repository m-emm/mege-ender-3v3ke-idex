"""Vision light mount for below-bed nozzle-offset illumination."""

from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from shellforgepy.simple import *


def create_vision_light_mount_assembly(
    *,
    print_bed,
    print_bed_undercarriage,
    apa_strip_front,
    apa_strip_back,
    apa_strip_left,
    apa_strip_right,
    vision_light_mount_plate_thickness,
    vision_light_mount_plate_border,
    vision_light_mount_plate_fillet_radius,
    vision_light_mount_aperture_clearance,
    vision_light_mount_strip_pocket_clearance,
    vision_light_mount_strip_pocket_depth,
    vision_light_mount_vertical_plate_thickness,
    vision_light_mount_clamp_x_oversize,
    vision_light_mount_clamp_height,
    vision_light_mount_clamp_jaw_thickness,
    vision_light_mount_clamp_span_y,
    vision_light_mount_clamp_clearance,
    vision_light_mount_clamp_screw_size,
    vision_light_mount_clamp_screw_length,
    vision_light_mount_clamp_screw_inset,
    vision_light_mount_clamp_nut_clearance,
    vision_light_mount_clamp_cylinder_head_clearance,
    vision_light_mount_screw_mount_clearance_type,
    BIG_THING,
):
    """Build a PETG-CF mount using the bed/undercarriage as references."""

    _ = print_bed.leader
    _ = BIG_THING

    strip_leaders = {
        "front": apa_strip_front.leader,
        "back": apa_strip_back.leader,
        "left": apa_strip_left.leader,
        "right": apa_strip_right.leader,
    }
    strip_bboxes = {
        name: get_bounding_box(strip) for name, strip in strip_leaders.items()
    }

    strip_min_x = min(bbox[0][0] for bbox in strip_bboxes.values())
    strip_max_x = max(bbox[1][0] for bbox in strip_bboxes.values())
    strip_min_y = min(bbox[0][1] for bbox in strip_bboxes.values())
    strip_max_y = max(bbox[1][1] for bbox in strip_bboxes.values())
    strip_min_z = min(bbox[0][2] for bbox in strip_bboxes.values())
    strip_max_z = max(bbox[1][2] for bbox in strip_bboxes.values())

    strip_min_x_part = min(
        strip_leaders.values(), key=lambda part: get_bounding_box(part)[0][0]
    )
    strip_min_y_part = min(
        strip_leaders.values(), key=lambda part: get_bounding_box(part)[0][1]
    )
    strip_min_z_part = min(
        strip_leaders.values(), key=lambda part: get_bounding_box(part)[0][2]
    )
    strip_reference = create_box(
        strip_max_x - strip_min_x,
        strip_max_y - strip_min_y,
        strip_max_z - strip_min_z,
    )
    strip_reference = align(strip_reference, strip_min_x_part, Alignment.LEFT)
    strip_reference = align(strip_reference, strip_min_y_part, Alignment.FRONT)
    strip_reference = align(strip_reference, strip_min_z_part, Alignment.BOTTOM)

    aperture_x_gap = strip_bboxes["right"][0][0] - strip_bboxes["left"][1][0]
    aperture_y_gap = strip_bboxes["back"][0][1] - strip_bboxes["front"][1][1]
    if aperture_x_gap <= 0 or aperture_y_gap <= 0:
        raise ValueError("APA strips do not leave a positive aperture")

    raw_aperture_reference = create_box(aperture_x_gap, aperture_y_gap, 1)
    raw_aperture_reference = align(
        raw_aperture_reference,
        strip_leaders["left"],
        Alignment.STACK_RIGHT,
    )
    raw_aperture_reference = align(
        raw_aperture_reference,
        strip_leaders["front"],
        Alignment.STACK_BACK,
    )
    aperture_size = max(
        aperture_x_gap + vision_light_mount_aperture_clearance,
        aperture_y_gap + vision_light_mount_aperture_clearance,
    )
    aperture_reference = create_box(aperture_size, aperture_size, 1)
    aperture_reference = align(
        aperture_reference,
        raw_aperture_reference,
        Alignment.CENTER,
        axes=[0, 1],
    )

    plate_width = (
        strip_max_x - strip_min_x + 2 * vision_light_mount_plate_border
    )
    plate_depth = (
        strip_max_y - strip_min_y + 2 * vision_light_mount_plate_border
    )

    pocket_depth_reference = create_box(1, 1, vision_light_mount_strip_pocket_depth)
    pocket_depth_reference = align(
        pocket_depth_reference,
        strip_reference,
        Alignment.CENTER,
        axes=[0, 1],
    )
    pocket_depth_reference = align(
        pocket_depth_reference,
        strip_reference,
        Alignment.BOTTOM,
    )

    plate = create_filleted_box(
        plate_width,
        plate_depth,
        vision_light_mount_plate_thickness,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    plate = align(plate, strip_reference, Alignment.CENTER, axes=[0, 1])
    plate = align(plate, pocket_depth_reference, Alignment.TOP)

    aperture = create_box(
        aperture_size,
        aperture_size,
        vision_light_mount_plate_thickness + 2,
    )
    aperture = align(aperture, aperture_reference, Alignment.CENTER, axes=[0, 1])
    aperture = align(aperture, plate, Alignment.CENTER, axes=[2])
    plate = plate.cut(aperture)

    pocket_top_reference = create_box(1, 1, 0.1)
    pocket_top_reference = align(pocket_top_reference, plate, Alignment.STACK_TOP)
    strip_pockets = PartCollector()
    for strip in strip_leaders.values():
        strip_bbox = get_bounding_box(strip)
        pocket = create_box(
            strip_bbox[1][0]
            - strip_bbox[0][0]
            + 2 * vision_light_mount_strip_pocket_clearance,
            strip_bbox[1][1]
            - strip_bbox[0][1]
            + 2 * vision_light_mount_strip_pocket_clearance,
            vision_light_mount_strip_pocket_depth + 0.2,
        )
        pocket = align(pocket, strip, Alignment.CENTER, axes=[0, 1])
        pocket = align(pocket, pocket_top_reference, Alignment.TOP)
        strip_pockets = strip_pockets.fuse(pocket)
    plate = plate.cut(strip_pockets)

    front_left_uc = print_bed_undercarriage.get_named_follower("front_left_uc")
    front_right_uc = print_bed_undercarriage.get_named_follower("front_right_uc")
    front_uc_parts = [front_left_uc, front_right_uc]
    front_uc_bboxes = [get_bounding_box(part) for part in front_uc_parts]
    front_min_x = min(bbox[0][0] for bbox in front_uc_bboxes)
    front_max_x = max(bbox[1][0] for bbox in front_uc_bboxes)
    front_min_z = min(bbox[0][2] for bbox in front_uc_bboxes)
    front_max_z = max(bbox[1][2] for bbox in front_uc_bboxes)
    front_min_x_part = min(
        front_uc_parts, key=lambda part: get_bounding_box(part)[0][0]
    )
    front_min_y_part = min(
        front_uc_parts, key=lambda part: get_bounding_box(part)[0][1]
    )
    front_min_z_part = min(
        front_uc_parts, key=lambda part: get_bounding_box(part)[0][2]
    )

    front_spar_reference = create_box(
        front_max_x - front_min_x,
        vision_light_mount_clamp_span_y,
        front_max_z - front_min_z,
    )
    front_spar_reference = align(
        front_spar_reference,
        front_min_x_part,
        Alignment.LEFT,
    )
    front_spar_reference = align(
        front_spar_reference,
        front_min_y_part,
        Alignment.FRONT,
    )
    front_spar_reference = align(
        front_spar_reference,
        front_min_z_part,
        Alignment.BOTTOM,
    )

    clamp_width = max(
        plate_width,
        get_bounding_box_size(front_spar_reference)[0],
    ) + 2 * vision_light_mount_clamp_x_oversize
    saddle_wall_thickness = vision_light_mount_clamp_jaw_thickness
    saddle_height = (
        get_bounding_box_size(front_spar_reference)[2]
        + 2 * saddle_wall_thickness
        + 2 * vision_light_mount_clamp_clearance
    )
    profile_keepout = create_box(
        get_bounding_box_size(front_spar_reference)[0]
        + 2 * vision_light_mount_clamp_clearance,
        get_bounding_box_size(front_spar_reference)[1]
        + 2 * vision_light_mount_clamp_clearance,
        get_bounding_box_size(front_spar_reference)[2]
        + 2 * vision_light_mount_clamp_clearance,
    )
    profile_keepout = align(profile_keepout, front_spar_reference, Alignment.CENTER)

    front_wall = create_filleted_box(
        clamp_width,
        saddle_wall_thickness,
        saddle_height,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    front_wall = align(front_wall, front_spar_reference, Alignment.CENTER, axes=[0])
    front_wall = align(front_wall, profile_keepout, Alignment.STACK_FRONT)
    front_wall = align(front_wall, profile_keepout, Alignment.CENTER, axes=[2])

    lip_depth = get_bounding_box_size(profile_keepout)[1] + saddle_wall_thickness
    top_lip = create_filleted_box(
        clamp_width,
        lip_depth,
        saddle_wall_thickness,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    top_lip = align(top_lip, front_wall, Alignment.CENTER, axes=[0])
    top_lip = align(top_lip, front_wall, Alignment.FRONT)
    top_lip = align(top_lip, profile_keepout, Alignment.STACK_TOP)

    bottom_lip = create_filleted_box(
        clamp_width,
        lip_depth,
        saddle_wall_thickness,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    bottom_lip = align(bottom_lip, front_wall, Alignment.CENTER, axes=[0])
    bottom_lip = align(bottom_lip, front_wall, Alignment.FRONT)
    bottom_lip = align(bottom_lip, profile_keepout, Alignment.STACK_BOTTOM)

    saddle = front_wall.fuse(top_lip).fuse(bottom_lip)
    saddle = saddle.cut(profile_keepout)

    clamp_cap = create_filleted_box(
        clamp_width,
        saddle_wall_thickness,
        saddle_height,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    clamp_cap = align(clamp_cap, front_wall, Alignment.CENTER, axes=[0, 2])
    clamp_cap = align(clamp_cap, profile_keepout, Alignment.STACK_BACK)
    clamp_cap = clamp_cap.cut(profile_keepout)

    plate_bbox = get_bounding_box(plate)
    aperture_bbox = get_bounding_box(aperture)
    saddle_bbox = get_bounding_box(saddle)
    connector_y_min = min(plate_bbox[0][1], saddle_bbox[0][1])
    connector_y_max = max(plate_bbox[0][1] + saddle_wall_thickness, saddle_bbox[1][1])
    vertical_z_min = min(plate_bbox[0][2], saddle_bbox[0][2])
    vertical_z_max = max(plate_bbox[1][2], saddle_bbox[1][2])
    vertical_reference = create_box(1, 1, vertical_z_max - vertical_z_min)
    if plate_bbox[0][2] <= saddle_bbox[0][2]:
        vertical_reference = align(vertical_reference, plate, Alignment.BOTTOM)
    else:
        vertical_reference = align(vertical_reference, saddle, Alignment.BOTTOM)

    side_webs = PartCollector()
    for web_width, side_alignment in (
        (aperture_bbox[0][0] - plate_bbox[0][0], Alignment.LEFT),
        (plate_bbox[1][0] - aperture_bbox[1][0], Alignment.RIGHT),
    ):
        if web_width <= 0:
            continue

        horizontal_web = create_box(
            web_width,
            connector_y_max - connector_y_min,
            vision_light_mount_vertical_plate_thickness,
        )
        horizontal_web = align(horizontal_web, plate, side_alignment)
        if plate_bbox[0][1] <= saddle_bbox[0][1]:
            horizontal_web = align(horizontal_web, plate, Alignment.FRONT)
        else:
            horizontal_web = align(horizontal_web, saddle, Alignment.FRONT)
        horizontal_web = align(horizontal_web, plate, Alignment.STACK_BOTTOM)
        side_webs = side_webs.fuse(horizontal_web)

        vertical_web = create_box(
            web_width,
            vision_light_mount_vertical_plate_thickness,
            vertical_z_max - vertical_z_min,
        )
        vertical_web = align(vertical_web, plate, side_alignment)
        vertical_web = align(vertical_web, saddle, Alignment.FRONT)
        vertical_web = align(vertical_web, vertical_reference, Alignment.CENTER, axes=[2])
        side_webs = side_webs.fuse(vertical_web)

    leader = plate.fuse(side_webs).fuse(saddle)

    screw_reference = saddle.fuse(clamp_cap)
    screw_mounts = create_four_screws_mount_assembly(
        screw_reference,
        screw_size=vision_light_mount_clamp_screw_size,
        screw_length=vision_light_mount_clamp_screw_length,
        screw_direction=Alignment.FRONT,
        with_nut_cutter=True,
        nut_cutter_clearance=vision_light_mount_clamp_nut_clearance,
        flush_with_top=True,
        cylinder_head_cutter_clearance=vision_light_mount_clamp_cylinder_head_clearance,
        width_inset=vision_light_mount_clamp_screw_inset,
        length_inset=vision_light_mount_clamp_screw_inset,
        clearance_type=vision_light_mount_screw_mount_clearance_type,
    )
    leader = screw_mounts.use_as_cutter_on(leader)
    clamp_cap = screw_mounts.use_as_cutter_on(clamp_cap)

    clamp_screw_holes = PartCollector()
    for _name, cutter in screw_mounts.get_named_cutter_items():
        clamp_screw_holes = clamp_screw_holes.fuse(cutter)

    clamp_screws = PartCollector()
    clamp_nuts = PartCollector()
    for name, part in screw_mounts.get_named_non_production_part_items():
        if name.endswith("_screw"):
            clamp_screws = clamp_screws.fuse(part)
        elif name.endswith("_nut"):
            clamp_nuts = clamp_nuts.fuse(part)

    assembly = LeaderFollowersCuttersPart(leader)
    assembly.add_named_follower(clamp_cap, "vision_light_mount_clamp_cap")
    assembly.add_named_cutter(aperture, "aperture")
    assembly.add_named_cutter(strip_pockets, "strip_pockets")
    assembly.add_named_cutter(profile_keepout, "undercarriage_keepout")
    assembly.add_named_cutter(clamp_screw_holes, "clamp_screw_holes")
    assembly.add_named_non_production_part(clamp_screws, "clamp_screws")
    assembly.add_named_non_production_part(clamp_nuts, "clamp_nuts")

    return assembly
