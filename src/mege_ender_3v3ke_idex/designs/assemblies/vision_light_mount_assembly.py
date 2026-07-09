"""Vision light mount for below-bed nozzle-offset illumination."""

from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_screw_mount_assembly,
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
    vision_light_mount_bridge_thickness,
    vision_light_mount_bridge_overlap,
    vision_light_mount_clamp_width,
    vision_light_mount_u_wall_thickness,
    vision_light_mount_u_bottom_thickness,
    vision_light_mount_u_spar_clearance_y,
    vision_light_mount_u_spar_clearance_z,
    vision_light_mount_u_ear_height_above_spar,
    vision_light_mount_u_screw_gap_above_spar,
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
        Alignment.FRONT: apa_strip_front.leader,
        Alignment.BACK: apa_strip_back.leader,
        Alignment.LEFT: apa_strip_left.leader,
        Alignment.RIGHT: apa_strip_right.leader,
    }

    strip_front_size = get_bounding_box_size(strip_leaders[Alignment.FRONT])
    
    strip_leaders_fused = PartCollector()
    for strip in strip_leaders.values():
        strip_leaders_fused = strip_leaders_fused.fuse(strip)

    strip_leaders_size = get_bounding_box_size(strip_leaders_fused)

    
    
    plate_width =  strip_leaders_size[0] + 2 * vision_light_mount_plate_border
    plate_depth = strip_leaders_size[1] + 2 * vision_light_mount_plate_border


    plate = create_filleted_box(
        plate_width,
        plate_depth,
        vision_light_mount_plate_thickness,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    plate = align(plate, strip_leaders_fused, Alignment.CENTER)
    plate = align(plate, strip_leaders_fused, Alignment.STACK_BOTTOM, stack_gap=-vision_light_mount_strip_pocket_depth)

    aperture_boundary_width =  2*strip_front_size[1]+ 2 * vision_light_mount_aperture_clearance

    aperture = materialize_bounding_box(
        strip_leaders_fused,
        x_enlargement=- aperture_boundary_width,
        y_enlargement=-aperture_boundary_width,z_enlargement=500)
    aperture = align(aperture, strip_leaders_fused, Alignment.CENTER)    
    plate = plate.cut(aperture)

    pocket_top_reference = create_box(1, 1, 0.1)
    pocket_top_reference = align(pocket_top_reference, plate, Alignment.STACK_TOP)
    strip_pockets = PartCollector()
    for strip in strip_leaders.values():
        pocket = materialize_bounding_box(
            strip,
            x_enlargement=2 * vision_light_mount_strip_pocket_clearance,
            y_enlargement=2 * vision_light_mount_strip_pocket_clearance,
            z_enlargement=(
                vision_light_mount_strip_pocket_depth
                + 0.2
                - get_bounding_box_size(strip)[2]
            ),
        )
        pocket = align(pocket, pocket_top_reference, Alignment.TOP)
        strip_pockets = strip_pockets.fuse(pocket)
    plate = plate.cut(strip_pockets)
    plate_bbox = get_bounding_box(plate)
    aperture_bbox = get_bounding_box(aperture)

    front_spar_reference = print_bed_undercarriage.get_named_non_production_part(
        "front_spar_profile_reference"
    )
    spar_size = get_bounding_box_size(front_spar_reference)
    front_spar_keepout = create_box(
        vision_light_mount_clamp_width,
        spar_size[1] + 2 * vision_light_mount_u_spar_clearance_y,
        spar_size[2] + vision_light_mount_u_spar_clearance_z,
    )
    front_spar_keepout = align(
        front_spar_keepout,
        aperture,
        Alignment.CENTER,
        axes=[0],
    )
    front_spar_keepout = align(
        front_spar_keepout,
        front_spar_reference,
        Alignment.CENTER,
        axes=[1, 2],
    )
    front_spar_keepout_bbox = get_bounding_box(front_spar_keepout)

    u_outer_depth = (
        get_bounding_box_size(front_spar_keepout)[1]
        + 2 * vision_light_mount_u_wall_thickness
    )
    configured_u_outer_height = (
        get_bounding_box_size(front_spar_keepout)[2]
        + vision_light_mount_u_bottom_thickness
        + vision_light_mount_u_ear_height_above_spar
    )
    u_bottom_z = front_spar_keepout_bbox[0][2] - vision_light_mount_u_bottom_thickness
    bridge_u_overlap_z = min(
        vision_light_mount_bridge_overlap,
        vision_light_mount_bridge_thickness / 2,
    )
    bridge_bottom_z = plate_bbox[0][2]
    u_outer_height = max(
        configured_u_outer_height,
        bridge_bottom_z + bridge_u_overlap_z - u_bottom_z,
    )

    bottom_wall = create_filleted_box(
        vision_light_mount_clamp_width,
        u_outer_depth,
        vision_light_mount_u_bottom_thickness,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.TOP],
    )
    bottom_wall = align(bottom_wall, front_spar_keepout, Alignment.CENTER)
    bottom_wall = align(bottom_wall, front_spar_keepout, Alignment.STACK_BOTTOM)
    bottom_wall = align(bottom_wall, plate, Alignment.LEFT)

    front_wall = create_filleted_box(
        vision_light_mount_clamp_width,
        vision_light_mount_u_wall_thickness,
        u_outer_height,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BACK, Alignment.FRONT],
    )
    front_wall = align(front_wall, bottom_wall, Alignment.CENTER)
    front_wall = align(front_wall, front_spar_keepout, Alignment.STACK_FRONT)
    front_wall = align(front_wall, bottom_wall, Alignment.BOTTOM)

    back_wall = create_filleted_box(
        vision_light_mount_clamp_width,
        vision_light_mount_u_wall_thickness,
        u_outer_height,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    back_wall = align(back_wall, bottom_wall, Alignment.CENTER)
    back_wall = align(back_wall, front_spar_keepout, Alignment.STACK_BACK)
    back_wall = align(back_wall, bottom_wall, Alignment.BOTTOM)

    u_channel = front_wall.fuse(back_wall).fuse(bottom_wall)

    screw_z_reference = create_box(
        1,
        1,
        2 * vision_light_mount_u_screw_gap_above_spar,
    )
    screw_z_reference = align(
        screw_z_reference,
        front_spar_reference,
        Alignment.CENTER,
        axes=[0, 1],
    )
    screw_z_reference = align(
        screw_z_reference,
        front_spar_reference,
        Alignment.STACK_TOP,
    )

    screw_x_span = create_box(
        vision_light_mount_clamp_width - 2 * vision_light_mount_clamp_screw_inset,
        1,
        1,
    )
    screw_x_span = align(screw_x_span, u_channel, Alignment.CENTER, axes=[0, 1])
    screw_x_span = align(screw_x_span, screw_z_reference, Alignment.CENTER, axes=[2])

    screw_mounts = None
    for side_alignment in (
        Alignment.LEFT,
        Alignment.RIGHT,
    ):
        screw_target = create_box(0.1, u_outer_depth, 0.1)
        screw_target = align(screw_target, screw_x_span, side_alignment)
        screw_target = align(screw_target, u_channel, Alignment.CENTER, axes=[1])
        screw_target = align(
            screw_target,
            screw_z_reference,
            Alignment.CENTER,
            axes=[2],
        )
        screw_mount = create_screw_mount_assembly(
            screw_target,
            screw_size=vision_light_mount_clamp_screw_size,
            screw_length=vision_light_mount_clamp_screw_length,
            screw_direction=Alignment.FRONT,
            with_nut_cutter=True,
            nut_cutter_clearance=vision_light_mount_clamp_nut_clearance,
            flush_with_top=False,
            cylinder_head_cutter_clearance=(
                vision_light_mount_clamp_cylinder_head_clearance
            ),
            clearance_type=vision_light_mount_screw_mount_clearance_type,
        )
        screw_mount = screw_mount.prefixed_copy(f"pinch_{side_alignment.name.lower()}_")
        screw_mounts = screw_mount if screw_mounts is None else screw_mounts.fuse(
            screw_mount
        )

    u_channel = screw_mounts.use_as_cutter_on(u_channel)

    u_bbox = get_bounding_box(u_channel)
    bridge_front_part = plate if plate_bbox[0][1] <= u_bbox[0][1] else u_channel
    bridge_front_y = min(plate_bbox[0][1], u_bbox[0][1])
    bridge_depth = aperture_bbox[0][1] - bridge_front_y

    leader = plate.fuse(u_channel)
    if bridge_depth > 0:
        bridge = create_box(
            vision_light_mount_clamp_width,
            bridge_depth,
            vision_light_mount_bridge_thickness,
        )
        bridge = align(bridge, u_channel, Alignment.CENTER, axes=[0])
        bridge = align(
            bridge,
            bridge_front_part,
            Alignment.FRONT,
        )
        bridge = align(bridge, plate, Alignment.BOTTOM)

        bridge_plate_overlap = create_box(
            vision_light_mount_clamp_width,
            vision_light_mount_bridge_overlap,
            vision_light_mount_bridge_thickness,
        )
        bridge_plate_overlap = align(
            bridge_plate_overlap,
            bridge,
            Alignment.CENTER,
            axes=[0, 2],
        )
        bridge_plate_overlap = align(
            bridge_plate_overlap,
            aperture,
            Alignment.STACK_FRONT,
        )

        leader = leader.fuse(bridge).fuse(bridge_plate_overlap)

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
    assembly.add_named_cutter(aperture, "aperture")
    assembly.add_named_cutter(strip_pockets, "strip_pockets")
    assembly.add_named_cutter(front_spar_keepout, "front_spar_keepout")
    assembly.add_named_cutter(clamp_screw_holes, "clamp_screw_holes")
    assembly.add_named_non_production_part(clamp_screws, "clamp_screws")
    assembly.add_named_non_production_part(clamp_nuts, "clamp_nuts")

    return assembly
