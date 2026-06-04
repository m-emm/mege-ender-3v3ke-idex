"""24 V electric switchboard enclosure assembly."""

from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from shellforgepy.simple import *


def create_electric_switchboard_assembly(
    *,
    emergency_button,
    fuse_holder,
    electric_switchboard_height,
    electric_switchboard_width,
    electric_switchboard_depth,
    electric_switchboard_wall_thickness,
    electric_switchboard_fuse_holder_bottom_clearance,
    electric_switchboard_mount_flange_screw_size,
    electric_switchboard_mount_flange_width,
    electric_switchboard_mount_flange_length,
    electric_switchboard_mount_flange_thickness,
    electric_switchboard_mount_flange_fillet_radius,
    electric_switchboard_corner_fillet_radius,
    electric_switchboard_lid_thickness,
    electric_switchboard_lid_rim_depth,
    electric_switchboard_lid_rim_clearance,
    electric_switchboard_lid_screw_size,
    electric_switchboard_lid_screw_length,
    electric_switchboard_lid_screw_inset,
    electric_switchboard_lid_screw_mount_block_size,
    electric_switchboard_lid_screw_mount_depth,
):
    """Create a left-open switchboard box with a screw-on side lid."""

    switchboard_reference = create_box(
        electric_switchboard_width,
        electric_switchboard_depth,
        electric_switchboard_height,
    )

    switchboard_box = create_filleted_box(
        electric_switchboard_width,
        electric_switchboard_depth,
        electric_switchboard_height,
        fillet_radius=electric_switchboard_corner_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.BOTTOM, Alignment.RIGHT],
    )

    inner_space_cutter = create_box(
        electric_switchboard_width - electric_switchboard_wall_thickness + 1,
        electric_switchboard_depth - 2 * electric_switchboard_wall_thickness,
        electric_switchboard_height - 2 * electric_switchboard_wall_thickness,
        origin=(
            -1,
            electric_switchboard_wall_thickness,
            electric_switchboard_wall_thickness,
        ),
    )
    switchboard_box = switchboard_box.cut(inner_space_cutter)

    top_panel_reference = create_box(
        electric_switchboard_width,
        electric_switchboard_depth,
        electric_switchboard_wall_thickness,
        origin=(
            0,
            0,
            electric_switchboard_height - electric_switchboard_wall_thickness,
        ),
    )

    emergency_button = rotate(90)(emergency_button)

    emergency_button = emergency_button.aligned_from_non_production_part(
        "mount_panel_reference",
        top_panel_reference,
        Alignment.CENTER,
    )
    switchboard_box = switchboard_box.cut(
        emergency_button.get_cutter_part_by_name("neck_mount_hole")
    )

    fuse_holder_front_panel_reference = create_box(
        electric_switchboard_width,
        electric_switchboard_wall_thickness,
        electric_switchboard_height,
    )
    fuse_holder = rotate(-90, axis=(0, 0, 1))(fuse_holder)
    fuse_holder = fuse_holder.aligned_from_non_production_part(
        "mount_panel_reference",
        fuse_holder_front_panel_reference,
        Alignment.CENTER,
        axes=[0, 1],
    )
    fuse_holder = fuse_holder.aligned_from_non_production_part(
        "mount_panel_reference",
        fuse_holder_front_panel_reference,
        Alignment.BOTTOM,
    )
    fuse_holder = translate(0, 0, electric_switchboard_fuse_holder_bottom_clearance)(
        fuse_holder
    )
    switchboard_box = switchboard_box.cut(
        fuse_holder.get_cutter_part_by_name("mount_hole")
    )

    lid = create_filleted_box(
        electric_switchboard_lid_thickness,
        electric_switchboard_depth,
        electric_switchboard_height,
        fillet_radius=electric_switchboard_corner_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
    )
    lid = align(lid, switchboard_reference, Alignment.CENTER, axes=[1, 2])
    lid = align(lid, switchboard_reference, Alignment.STACK_LEFT)

    lid_rim_outer_width = (
        electric_switchboard_depth
        - 2 * electric_switchboard_wall_thickness
        - 2 * electric_switchboard_lid_rim_clearance
    )
    lid_rim_outer_height = (
        electric_switchboard_height
        - 2 * electric_switchboard_wall_thickness
        - 2 * electric_switchboard_lid_rim_clearance
    )
    lid_rim_inner_width = lid_rim_outer_width - 2 * electric_switchboard_wall_thickness
    lid_rim_inner_height = (
        lid_rim_outer_height - 2 * electric_switchboard_wall_thickness
    )
    lid_rim_fillet_radius = min(
        electric_switchboard_corner_fillet_radius,
        electric_switchboard_wall_thickness / 2 - 0.1,
    )
    lid_rim = create_filleted_box(
        electric_switchboard_lid_rim_depth,
        lid_rim_outer_width,
        lid_rim_outer_height,
        fillet_radius=lid_rim_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
    )
    lid_rim_inner_cutter = create_box(
        electric_switchboard_lid_rim_depth + 2,
        lid_rim_inner_width,
        lid_rim_inner_height,
    )
    lid_rim_inner_cutter = align(lid_rim_inner_cutter, lid_rim, Alignment.CENTER)
    lid_rim = lid_rim.cut(lid_rim_inner_cutter)
    lid_rim = align(lid_rim, switchboard_reference, Alignment.CENTER, axes=[1, 2])
    lid_rim = align(lid_rim, lid, Alignment.STACK_RIGHT)
    lid = lid.fuse(lid_rim)

    lid_screw_mount_blocks = PartCollector()

    for fb in [Alignment.FRONT, Alignment.BACK]:
        for tb in [Alignment.TOP, Alignment.BOTTOM]:
            screw_mount_block = create_filleted_box(
                electric_switchboard_width,
                electric_switchboard_lid_screw_mount_block_size,
                electric_switchboard_lid_screw_mount_block_size,
                fillet_radius=min(
                    electric_switchboard_corner_fillet_radius,
                    electric_switchboard_lid_screw_mount_block_size / 4,
                ),
                no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
            )

            screw_mount_block = align(
                screw_mount_block, switchboard_reference, Alignment.CENTER, axes=[1, 2]
            )
            screw_mount_block = align(screw_mount_block, switchboard_reference, fb)
            screw_mount_block = align(screw_mount_block, switchboard_reference, tb)

            lid_screw_mount_blocks = lid_screw_mount_blocks.fuse(screw_mount_block)

    lid_screw_span_reference = lid.fuse(lid_screw_mount_blocks)
    lid_screw_mount = create_four_screws_mount_assembly(
        lid_screw_span_reference,
        electric_switchboard_lid_screw_size,
        electric_switchboard_lid_screw_length,
        screw_direction=Alignment.LEFT,
        with_nut_cutter=True,
        flush_with_top=True,
        width_inset=electric_switchboard_lid_screw_inset,
        length_inset=electric_switchboard_lid_screw_inset,
        clearance_type="loose",
    )

    lid = lid_screw_mount.use_as_cutter_on(lid)
    lid_screw_mount_blocks = lid_screw_mount.use_as_cutter_on(lid_screw_mount_blocks)
    switchboard_box = switchboard_box.fuse(lid_screw_mount_blocks)
    switchboard_box = lid_screw_mount.use_as_cutter_on(switchboard_box)

    mount_flange_screw_hole_diameter = MScrew.from_size(
        electric_switchboard_mount_flange_screw_size
    ).clearance_hole_normal
    mount_flange_screw_holes = PartCollector()
    mount_flanges = PartCollector()
    for side in [Alignment.FRONT, Alignment.BACK]:
        mount_flange = create_filleted_box(
            electric_switchboard_mount_flange_width,
            electric_switchboard_mount_flange_length,
            electric_switchboard_mount_flange_thickness,
            fillet_radius=electric_switchboard_mount_flange_fillet_radius,
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, side.opposite],
        )
        mount_flange = align(mount_flange, switchboard_box, Alignment.CENTER, axes=[0])
        mount_flange = align(mount_flange, switchboard_box, side.stack_alignment)
        mount_flange = align(mount_flange, switchboard_box, Alignment.BOTTOM)
        mount_flanges = mount_flanges.fuse(mount_flange)

        mount_flange_screw_hole = create_cylinder(
            mount_flange_screw_hole_diameter / 2,
            electric_switchboard_mount_flange_thickness + 2,
            origin=(
                get_bounding_box_center(mount_flange)[0],
                get_bounding_box_center(mount_flange)[1],
                -1,
            ),
        )
        mount_flange_screw_holes = mount_flange_screw_holes.fuse(
            mount_flange_screw_hole
        )

    switchboard_box = switchboard_box.fuse(mount_flanges)
    switchboard_box = switchboard_box.cut(mount_flange_screw_holes)

    switchboard = LeaderFollowersCuttersPart(leader=switchboard_box)
    switchboard.add_named_follower(lid, "electric_switchboard_lid")
    switchboard.add_named_cutter(mount_flange_screw_holes, "mount_flange_screw_holes")
    switchboard = switchboard.merge_except_leader(
        lid_screw_mount.prefixed_copy("lid_mount")
    )

    for name, part in emergency_button.get_named_follower_items():
        switchboard.add_named_non_production_part(part, f"emergency_button_{name}")

    for name, part in emergency_button.get_named_cutter_items():
        switchboard.add_named_cutter(part, f"emergency_button_{name}")

    for name, part in emergency_button.get_named_non_production_part_items():
        switchboard.add_named_non_production_part(part, f"emergency_button_{name}")

    for name, part in fuse_holder.get_named_follower_items():
        switchboard.add_named_non_production_part(part, f"fuse_holder_{name}")

    for name, part in fuse_holder.get_named_cutter_items():
        switchboard.add_named_cutter(part, f"fuse_holder_{name}")

    for name, part in fuse_holder.get_named_non_production_part_items():
        switchboard.add_named_non_production_part(part, f"fuse_holder_{name}")

    return switchboard
