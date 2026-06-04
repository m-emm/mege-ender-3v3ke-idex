"""Heatbed PSU housing enclosure assembly."""

from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from shellforgepy.simple import *


def create_heatbed_psu_housing_assembly(
    *,
    heatbed_psu_housing_height,
    heatbed_psu_housing_width,
    heatbed_psu_housing_depth,
    heatbed_psu_housing_wall_thickness,
    heatbed_psu_housing_cable_hole_diameter,
    heatbed_psu_housing_cable_hole_x_inset,
    heatbed_psu_housing_cable_hole_y_inset,
    heatbed_psu_housing_mount_flange_screw_size,
    heatbed_psu_housing_mount_flange_width,
    heatbed_psu_housing_mount_flange_length,
    heatbed_psu_housing_mount_flange_thickness,
    heatbed_psu_housing_mount_flange_fillet_radius,
    heatbed_psu_housing_corner_fillet_radius,
    heatbed_psu_housing_lid_thickness,
    heatbed_psu_housing_lid_body_clearance,
    heatbed_psu_housing_lid_rim_depth,
    heatbed_psu_housing_lid_rim_thickness,
    heatbed_psu_housing_lid_rim_clearance,
    heatbed_psu_housing_lid_screw_size,
    heatbed_psu_housing_lid_screw_length,
    heatbed_psu_housing_lid_screw_inset,
    heatbed_psu_housing_lid_screw_mount_block_size,
):
    """Create a left-open heatbed PSU housing with a screw-on side lid."""

    housing_reference = create_box(
        heatbed_psu_housing_width,
        heatbed_psu_housing_depth,
        heatbed_psu_housing_height,
    )

    housing_box = create_filleted_box(
        heatbed_psu_housing_width,
        heatbed_psu_housing_depth,
        heatbed_psu_housing_height,
        fillet_radius=heatbed_psu_housing_corner_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.BOTTOM, Alignment.RIGHT],
    )

    inner_space_cutter = create_box(
        heatbed_psu_housing_width - heatbed_psu_housing_wall_thickness + 1,
        heatbed_psu_housing_depth - 2 * heatbed_psu_housing_wall_thickness,
        heatbed_psu_housing_height - 2 * heatbed_psu_housing_wall_thickness,
        origin=(
            -1,
            heatbed_psu_housing_wall_thickness,
            heatbed_psu_housing_wall_thickness,
        ),
    )
    housing_box = housing_box.cut(inner_space_cutter)

    cable_hole = create_cylinder(
        heatbed_psu_housing_cable_hole_diameter / 2,
        4 * heatbed_psu_housing_wall_thickness,
    )
    cable_hole = align(cable_hole, housing_reference, Alignment.CENTER)
    cable_hole = align(
        cable_hole,
        housing_reference,
        Alignment.STACK_BOTTOM,
        stack_gap=-2 * heatbed_psu_housing_wall_thickness,
    )
    cable_hole = align(cable_hole, housing_reference, Alignment.EDGE_RIGHT)
    cable_hole = align(cable_hole, housing_reference, Alignment.EDGE_FRONT)
    cable_hole = translate(
        -heatbed_psu_housing_cable_hole_x_inset,
        heatbed_psu_housing_cable_hole_y_inset,
        0,
    )(cable_hole)
    housing_box = housing_box.cut(cable_hole)

    lid = create_filleted_box(
        heatbed_psu_housing_lid_thickness,
        heatbed_psu_housing_depth,
        heatbed_psu_housing_height,
        fillet_radius=heatbed_psu_housing_corner_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT, Alignment.BOTTOM],
    )
    lid = align(lid, housing_reference, Alignment.CENTER, axes=[1, 2])
    lid = align(
        lid,
        housing_reference,
        Alignment.STACK_LEFT,
        stack_gap=heatbed_psu_housing_lid_body_clearance,
    )

    lid_rim_outer_width = (
        heatbed_psu_housing_depth
        - 2 * heatbed_psu_housing_wall_thickness
        - 2 * heatbed_psu_housing_lid_rim_clearance
    )
    lid_rim_outer_height = (
        heatbed_psu_housing_height
        - 2 * heatbed_psu_housing_wall_thickness
        - 2 * heatbed_psu_housing_lid_rim_clearance
    )
    lid_rim_inner_width = (
        lid_rim_outer_width - 2 * heatbed_psu_housing_lid_rim_thickness
    )
    lid_rim_inner_height = (
        lid_rim_outer_height - 2 * heatbed_psu_housing_lid_rim_thickness
    )
    lid_rim_fillet_radius = min(
        heatbed_psu_housing_corner_fillet_radius,
        heatbed_psu_housing_lid_rim_thickness / 2 - 0.1,
    )
    lid_rim = create_filleted_box(
        heatbed_psu_housing_lid_body_clearance + heatbed_psu_housing_lid_rim_depth,
        lid_rim_outer_width,
        lid_rim_outer_height,
        fillet_radius=lid_rim_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
    )
    lid_rim_inner_cutter = create_box(
        heatbed_psu_housing_lid_body_clearance + heatbed_psu_housing_lid_rim_depth + 2,
        lid_rim_inner_width,
        lid_rim_inner_height,
    )
    lid_rim_inner_cutter = align(lid_rim_inner_cutter, lid_rim, Alignment.CENTER)
    lid_rim = lid_rim.cut(lid_rim_inner_cutter)
    lid_rim = align(lid_rim, housing_reference, Alignment.CENTER, axes=[1, 2])
    lid_rim = align(lid_rim, lid, Alignment.STACK_RIGHT)
    lid = lid.fuse(lid_rim)

    lid_screw_mount_blocks = PartCollector()
    lid_screw_mount_blocks_list = []
    for fb in [Alignment.FRONT, Alignment.BACK]:
        for tb in [Alignment.TOP, Alignment.BOTTOM]:
            screw_mount_block = create_filleted_box(
                heatbed_psu_housing_width,
                heatbed_psu_housing_lid_screw_mount_block_size,
                heatbed_psu_housing_lid_screw_mount_block_size,
                fillet_radius=min(
                    heatbed_psu_housing_corner_fillet_radius,
                    heatbed_psu_housing_lid_screw_mount_block_size / 4,
                ),
                no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
            )

            screw_mount_block = align(
                screw_mount_block, housing_reference, Alignment.CENTER, axes=[1, 2]
            )
            screw_mount_block = align(screw_mount_block, housing_reference, fb)
            screw_mount_block = align(screw_mount_block, housing_reference, tb)

            lid_screw_mount_blocks = lid_screw_mount_blocks.fuse(screw_mount_block)
            lid_screw_mount_blocks_list.append(screw_mount_block)

    lid_screw_span_reference = lid.fuse(lid_screw_mount_blocks)
    lid_screw_mount = create_four_screws_mount_assembly(
        lid_screw_span_reference,
        heatbed_psu_housing_lid_screw_size,
        heatbed_psu_housing_lid_screw_length,
        screw_direction=Alignment.LEFT,
        with_nut_cutter=True,
        flush_with_top=True,
        width_inset=heatbed_psu_housing_lid_screw_inset,
        length_inset=heatbed_psu_housing_lid_screw_inset,
        clearance_type="loose",
    )

    lid = lid_screw_mount.use_as_cutter_on(lid)

    for lid_screw_mount_block in lid_screw_mount_blocks_list:
        lid_screw_mount_block_cutter = materialize_bounding_box(
            lid_screw_mount_block,
            x_enlargement=0.2,
            y_enlargement=0.2,
            z_enlargement=0.2,
        )
        lid = lid.cut(lid_screw_mount_block_cutter)

    lid_screw_mount_blocks = lid_screw_mount.use_as_cutter_on(lid_screw_mount_blocks)
    housing_box = housing_box.fuse(lid_screw_mount_blocks)
    housing_box = lid_screw_mount.use_as_cutter_on(housing_box)

    mount_flange_screw_hole_diameter = MScrew.from_size(
        heatbed_psu_housing_mount_flange_screw_size
    ).clearance_hole_normal
    mount_flange_screw_holes = PartCollector()
    mount_flanges = PartCollector()
    for side in [Alignment.FRONT, Alignment.BACK]:
        mount_flange = create_filleted_box(
            heatbed_psu_housing_mount_flange_width,
            heatbed_psu_housing_mount_flange_length,
            heatbed_psu_housing_mount_flange_thickness,
            fillet_radius=heatbed_psu_housing_mount_flange_fillet_radius,
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, side.opposite],
        )
        mount_flange = align(mount_flange, housing_box, Alignment.CENTER, axes=[0])
        mount_flange = align(mount_flange, housing_box, side.stack_alignment)
        mount_flange = align(mount_flange, housing_box, Alignment.BOTTOM)
        mount_flanges = mount_flanges.fuse(mount_flange)

        mount_flange_screw_hole = create_cylinder(
            mount_flange_screw_hole_diameter / 2,
            heatbed_psu_housing_mount_flange_thickness + 2,
            origin=(
                get_bounding_box_center(mount_flange)[0],
                get_bounding_box_center(mount_flange)[1],
                -1,
            ),
        )
        mount_flange_screw_holes = mount_flange_screw_holes.fuse(
            mount_flange_screw_hole
        )

    housing_box = housing_box.fuse(mount_flanges)
    housing_box = housing_box.cut(mount_flange_screw_holes)
    housing_box = housing_box.cut(cable_hole)

    housing = LeaderFollowersCuttersPart(leader=housing_box)
    housing.add_named_follower(lid, "heatbed_psu_housing_lid")
    housing.add_named_cutter(mount_flange_screw_holes, "mount_flange_screw_holes")
    housing.add_named_cutter(cable_hole, "cable_hole")
    housing.add_named_non_production_part(
        housing_reference, "heatbed_psu_housing_body_reference"
    )
    housing = housing.merge_except_leader(lid_screw_mount.prefixed_copy("lid_mount"))

    return housing
