"""TB6600 stripboard interface housing assembly."""

from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from shellforgepy.simple import *


def create_tb6600_stripboard_interface_housing_assembly(
    *,
    tb6600_stripboard_interface_housing_board_columns,
    tb6600_stripboard_interface_housing_board_rows,
    tb6600_stripboard_interface_housing_board_pitch,
    tb6600_stripboard_interface_housing_board_clearance,
    tb6600_stripboard_interface_housing_front_cable_corridor,
    tb6600_stripboard_interface_housing_internal_height,
    tb6600_stripboard_interface_housing_wall_thickness,
    tb6600_stripboard_interface_housing_corner_fillet_radius,
    tb6600_stripboard_interface_housing_lid_thickness,
    tb6600_stripboard_interface_housing_lid_body_clearance,
    tb6600_stripboard_interface_housing_lid_outer_overhang,
    tb6600_stripboard_interface_housing_lid_rim_depth,
    tb6600_stripboard_interface_housing_lid_rim_thickness,
    tb6600_stripboard_interface_housing_lid_rim_clearance,
    tb6600_stripboard_interface_housing_lid_screw_size,
    tb6600_stripboard_interface_housing_lid_screw_length,
    tb6600_stripboard_interface_housing_lid_screw_inset,
    tb6600_stripboard_interface_housing_lid_screw_mount_block_size,
    tb6600_stripboard_interface_housing_lid_thread_inset_extra_screw_depth,
    tb6600_stripboard_interface_housing_cable_exit_width,
    tb6600_stripboard_interface_housing_cable_exit_height,
    tb6600_stripboard_interface_housing_cable_exit_floor_bridge,
    tb6600_stripboard_interface_housing_cable_exit_fillet_radius,
    tb6600_stripboard_interface_housing_cable_tie_slot_length,
    tb6600_stripboard_interface_housing_cable_tie_slot_width,
    tb6600_stripboard_interface_housing_cable_tie_slot_pair_spacing,
    tb6600_stripboard_interface_housing_cable_tie_pair_x_spacing,
    tb6600_stripboard_interface_housing_cable_tie_slot_y_center_from_front_inside,
    tb6600_stripboard_interface_housing_mount_flange_screw_size,
    tb6600_stripboard_interface_housing_mount_flange_screw_length,
    tb6600_stripboard_interface_housing_mount_flange_width,
    tb6600_stripboard_interface_housing_mount_flange_length,
    tb6600_stripboard_interface_housing_mount_flange_thickness,
    tb6600_stripboard_interface_housing_mount_flange_fillet_radius,
):
    """Create a roomy lidded tray for the hand-built TB6600 stripboard interface."""

    board_keepout_width = (
        tb6600_stripboard_interface_housing_board_columns
        * tb6600_stripboard_interface_housing_board_pitch
    )
    board_keepout_depth = (
        tb6600_stripboard_interface_housing_board_rows
        * tb6600_stripboard_interface_housing_board_pitch
    )
    wall = tb6600_stripboard_interface_housing_wall_thickness
    screw_block = tb6600_stripboard_interface_housing_lid_screw_mount_block_size
    post_clearance = screw_block + tb6600_stripboard_interface_housing_board_clearance

    internal_width = board_keepout_width + 2 * post_clearance
    internal_depth = (
        board_keepout_depth
        + tb6600_stripboard_interface_housing_front_cable_corridor
        + 2 * post_clearance
    )
    housing_width = internal_width + 2 * wall
    housing_depth = internal_depth + 2 * wall
    housing_height = tb6600_stripboard_interface_housing_internal_height + wall

    housing_reference = create_box(housing_width, housing_depth, housing_height)
    housing_box = create_filleted_box(
        housing_width,
        housing_depth,
        housing_height,
        fillet_radius=tb6600_stripboard_interface_housing_corner_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )

    inner_space_cutter = create_box(
        internal_width,
        internal_depth,
        tb6600_stripboard_interface_housing_internal_height + 1,
        origin=(wall, wall, wall),
    )
    housing_box = housing_box.cut(inner_space_cutter)

    lid_screw_mount_blocks = PartCollector()
    post_centers_x = [
        wall + screw_block / 2,
        housing_width - wall - screw_block / 2,
    ]
    post_centers_y = [
        wall + screw_block / 2,
        housing_depth - wall - screw_block / 2,
    ]
    for x_center in post_centers_x:
        for y_center in post_centers_y:
            screw_mount_block = create_filleted_box(
                screw_block,
                screw_block,
                housing_height,
                fillet_radius=min(
                    tb6600_stripboard_interface_housing_corner_fillet_radius,
                    screw_block / 4,
                ),
            )
            screw_mount_block = translate(
                x_center - screw_block / 2,
                y_center - screw_block / 2,
                0,
            )(screw_mount_block)
            lid_screw_mount_blocks = lid_screw_mount_blocks.fuse(screw_mount_block)

    mount_flange = create_filleted_box(
        tb6600_stripboard_interface_housing_mount_flange_width,
        tb6600_stripboard_interface_housing_mount_flange_length,
        tb6600_stripboard_interface_housing_mount_flange_thickness,
        fillet_radius=tb6600_stripboard_interface_housing_mount_flange_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, Alignment.FRONT],
    )
    mount_flange = align(mount_flange, housing_reference, Alignment.CENTER, axes=[0])
    mount_flange = align(mount_flange, housing_reference, Alignment.STACK_BACK)
    mount_flange = align(mount_flange, housing_reference, Alignment.BOTTOM)

    mount_flange_screw_hole = create_cylinder(
        MScrew.from_size(
            tb6600_stripboard_interface_housing_mount_flange_screw_size
        ).clearance_hole_normal
        / 2,
        tb6600_stripboard_interface_housing_mount_flange_thickness + 2,
        origin=(
            get_bounding_box_center(mount_flange)[0],
            get_bounding_box_center(mount_flange)[1],
            -1,
        ),
    )
    housing_box = housing_box.fuse(mount_flange)
    housing_box = housing_box.cut(mount_flange_screw_hole)

    mount_flange_screw = create_cylinder_screw(
        tb6600_stripboard_interface_housing_mount_flange_screw_size,
        tb6600_stripboard_interface_housing_mount_flange_screw_length,
    )
    mount_flange_screw = align(
        mount_flange_screw, mount_flange_screw_hole, Alignment.CENTER, axes=[0, 1]
    )
    mount_flange_screw = translate(
        0,
        0,
        get_bounding_box(mount_flange)[1][2]
        - tb6600_stripboard_interface_housing_mount_flange_screw_length,
    )(mount_flange_screw)

    cable_exit = create_filleted_box(
        tb6600_stripboard_interface_housing_cable_exit_width,
        wall + 2,
        tb6600_stripboard_interface_housing_cable_exit_height,
        fillet_radius=tb6600_stripboard_interface_housing_cable_exit_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    cable_exit = translate(
        (housing_width - tb6600_stripboard_interface_housing_cable_exit_width) / 2,
        -1,
        tb6600_stripboard_interface_housing_cable_exit_floor_bridge,
    )(cable_exit)
    housing_box = housing_box.cut(cable_exit)

    cable_tie_slots = PartCollector()
    cable_tie_slot_items = []
    cable_tie_center_y = (
        wall
        + tb6600_stripboard_interface_housing_cable_tie_slot_y_center_from_front_inside
    )
    for side_name, x_offset in [
        ("left", -tb6600_stripboard_interface_housing_cable_tie_pair_x_spacing / 2),
        ("right", tb6600_stripboard_interface_housing_cable_tie_pair_x_spacing / 2),
    ]:
        x_center = housing_width / 2 + x_offset
        for position_name, y_offset in [
            (
                "front",
                -tb6600_stripboard_interface_housing_cable_tie_slot_pair_spacing / 2,
            ),
            (
                "back",
                tb6600_stripboard_interface_housing_cable_tie_slot_pair_spacing / 2,
            ),
        ]:
            cable_tie_slot = create_box(
                tb6600_stripboard_interface_housing_cable_tie_slot_length,
                tb6600_stripboard_interface_housing_cable_tie_slot_width,
                wall + 2,
                origin=(
                    x_center
                    - tb6600_stripboard_interface_housing_cable_tie_slot_length / 2,
                    cable_tie_center_y
                    + y_offset
                    - tb6600_stripboard_interface_housing_cable_tie_slot_width / 2,
                    -1,
                ),
            )
            cable_tie_slots = cable_tie_slots.fuse(cable_tie_slot)
            cable_tie_slot_items.append(
                (f"cable_tie_slot_{side_name}_{position_name}", cable_tie_slot)
            )
    housing_box = housing_box.cut(cable_tie_slots)

    lid_width = (
        housing_width + 2 * tb6600_stripboard_interface_housing_lid_outer_overhang
    )
    lid_depth = (
        housing_depth + 2 * tb6600_stripboard_interface_housing_lid_outer_overhang
    )
    lid_base = create_filleted_box(
        lid_width,
        lid_depth,
        tb6600_stripboard_interface_housing_lid_thickness,
        fillet_radius=tb6600_stripboard_interface_housing_corner_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    lid_base = align(lid_base, housing_reference, Alignment.CENTER, axes=[0, 1])
    lid_base = align(
        lid_base,
        housing_reference,
        Alignment.STACK_TOP,
        stack_gap=tb6600_stripboard_interface_housing_lid_body_clearance,
    )

    lid_rim_outer_width = (
        internal_width - 2 * tb6600_stripboard_interface_housing_lid_rim_clearance
    )
    lid_rim_outer_depth = (
        internal_depth - 2 * tb6600_stripboard_interface_housing_lid_rim_clearance
    )
    lid_rim_inner_width = (
        lid_rim_outer_width - 2 * tb6600_stripboard_interface_housing_lid_rim_thickness
    )
    lid_rim_inner_depth = (
        lid_rim_outer_depth - 2 * tb6600_stripboard_interface_housing_lid_rim_thickness
    )
    lid_rim_height = (
        tb6600_stripboard_interface_housing_lid_body_clearance
        + tb6600_stripboard_interface_housing_lid_rim_depth
    )
    lid_rim_fillet_radius = min(
        tb6600_stripboard_interface_housing_corner_fillet_radius,
        tb6600_stripboard_interface_housing_lid_rim_thickness / 2 - 0.1,
    )
    lid_rim = create_filleted_box(
        lid_rim_outer_width,
        lid_rim_outer_depth,
        lid_rim_height,
        fillet_radius=lid_rim_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    lid_rim_inner_cutter = create_box(
        lid_rim_inner_width,
        lid_rim_inner_depth,
        lid_rim_height + 2,
    )
    lid_rim_inner_cutter = align(lid_rim_inner_cutter, lid_rim, Alignment.CENTER)
    lid_rim = lid_rim.cut(lid_rim_inner_cutter)
    lid_rim = align(lid_rim, housing_reference, Alignment.CENTER, axes=[0, 1])
    lid_rim = align(lid_rim, lid_base, Alignment.STACK_BOTTOM)
    lid = lid_base.fuse(lid_rim)

    lid_screw_span_reference = housing_reference.fuse(lid)
    lid_screw_mount = create_four_screws_mount_assembly(
        lid_screw_span_reference,
        tb6600_stripboard_interface_housing_lid_screw_size,
        tb6600_stripboard_interface_housing_lid_screw_length,
        screw_direction=Alignment.TOP,
        with_nut_cutter=False,
        flush_with_top=True,
        width_inset=tb6600_stripboard_interface_housing_lid_screw_inset,
        length_inset=tb6600_stripboard_interface_housing_lid_screw_inset,
        clearance_type="loose",
    )
    lid = lid_screw_mount.use_as_cutter_on(lid)

    lid_screw_mount_blocks = lid_screw_mount.use_as_cutter_on(lid_screw_mount_blocks)
    lid_thread_insets = None
    lid_thread_inset_depth = (
        MScrew.from_size(
            tb6600_stripboard_interface_housing_lid_screw_size
        ).thread_inset_length
        + tb6600_stripboard_interface_housing_lid_thread_inset_extra_screw_depth
    )
    for lid_screw_index in range(4):
        lid_screw_hole = lid_screw_mount.get_named_cutter(
            f"screw_{lid_screw_index}_hole_cutter"
        )
        lid_thread_inset = create_thread_inset_assembly(
            size=tb6600_stripboard_interface_housing_lid_screw_size,
            thickness=lid_thread_inset_depth,
            extra_radius=0.01,
            clearance_type="loose",
        )
        lid_thread_inset = align(
            lid_thread_inset, lid_screw_hole, Alignment.CENTER, axes=[0, 1]
        )
        lid_thread_inset = align(
            lid_thread_inset, lid_screw_mount_blocks, Alignment.TOP
        )

        lid_screw_mount_blocks = lid_thread_inset.use_as_cutter_on(
            lid_screw_mount_blocks
        )
        lid_screw_mount_blocks = lid_screw_mount_blocks.fuse(lid_thread_inset.leader)

        named_lid_thread_inset = lid_thread_inset.prefixed_copy(
            f"screw_{lid_screw_index}"
        )
        if lid_thread_insets is None:
            lid_thread_insets = named_lid_thread_inset
        else:
            lid_thread_insets = lid_thread_insets.fuse(named_lid_thread_inset)

    housing_box = housing_box.fuse(lid_screw_mount_blocks)
    housing_box = lid_screw_mount.use_as_cutter_on(housing_box)

    housing = LeaderFollowersCuttersPart(leader=housing_box)
    housing.add_named_follower(lid, "tb6600_stripboard_interface_housing_lid")
    housing.add_named_cutter(inner_space_cutter, "inner_space")
    housing.add_named_cutter(cable_exit, "cable_exit")
    housing.add_named_cutter(cable_tie_slots, "cable_tie_slots")
    housing.add_named_cutter(mount_flange_screw_hole, "mount_flange_screw_hole")
    for name, cable_tie_slot in cable_tie_slot_items:
        housing.add_named_cutter(cable_tie_slot, name)
    housing.add_named_non_production_part(
        housing_reference, "tb6600_stripboard_interface_housing_body_reference"
    )
    housing.add_named_non_production_part(mount_flange_screw, "mount_flange_screw")
    housing = housing.merge_except_leader(lid_screw_mount.prefixed_copy("lid_mount"))
    housing = housing.merge_except_leader(lid_thread_insets.prefixed_copy("lid_mount"))

    return housing
