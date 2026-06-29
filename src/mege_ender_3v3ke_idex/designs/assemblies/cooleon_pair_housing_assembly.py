"""Open-top housing with lid for a back-to-back Cooleon PSU pair."""

from mege_ender_3v3ke_idex.designs.trellis_plate import create_trellis_cutters
from shellforgepy.simple import *


def create_cooleon_pair_housing_assembly(
    *,
    cooleon_psu_1,
    cooleon_psu_2,
    cooleon_pair_housing_clearance,
    cooleon_pair_housing_wall_thickness,
    cooleon_pair_housing_mount_rib_length,
    cooleon_pair_housing_mount_rib_thickness,
    cooleon_pair_housing_mount_rib_end_inset,
    cooleon_pair_housing_vent_diamond_size,
    cooleon_pair_housing_vent_pitch,
    cooleon_pair_housing_vent_end_inset,
    cooleon_pair_housing_vent_height,
    cooleon_pair_housing_vent_row_z,
    cooleon_pair_housing_lid_thickness,
    cooleon_pair_housing_lid_body_clearance,
    cooleon_pair_housing_lid_outer_overhang,
    cooleon_pair_housing_lid_rim_depth,
    cooleon_pair_housing_lid_rim_thickness,
    cooleon_pair_housing_lid_rim_clearance,
    cooleon_pair_housing_lid_screw_size,
    cooleon_pair_housing_lid_screw_length,
    cooleon_pair_housing_lid_screw_inset,
    cooleon_pair_housing_lid_screw_boss_diameter,
    cooleon_pair_housing_self_threading_core_radius_adjustment,
    cooleon_pair_housing_self_threading_lead_in,
):
    """Create a lidded open-top tray around the placed Cooleon PSU bodies."""

    psu_pair_reference = cooleon_psu_1.leader.fuse(cooleon_psu_2.leader)
    psu_pair_bbox = get_bounding_box(psu_pair_reference)
    psu_pair_min, psu_pair_max = psu_pair_bbox
    psu_1_min, psu_1_max = get_bounding_box(cooleon_psu_1.leader)
    psu_2_min, psu_2_max = get_bounding_box(cooleon_psu_2.leader)

    inner_min_x = psu_pair_min[0] - cooleon_pair_housing_clearance
    inner_min_y = psu_pair_min[1] - cooleon_pair_housing_clearance
    inner_min_z = psu_pair_min[2] - cooleon_pair_housing_clearance
    inner_max_x = psu_pair_max[0] + cooleon_pair_housing_clearance
    inner_max_y = psu_pair_max[1] + cooleon_pair_housing_clearance
    inner_max_z = psu_pair_max[2] + cooleon_pair_housing_clearance

    wall_thickness = cooleon_pair_housing_wall_thickness
    outer_min_x = inner_min_x - wall_thickness
    outer_min_y = inner_min_y - wall_thickness
    outer_min_z = inner_min_z - wall_thickness
    outer_max_x = inner_max_x + wall_thickness
    outer_max_y = inner_max_y + wall_thickness
    outer_max_z = inner_max_z

    housing_box = create_box(
        outer_max_x - outer_min_x,
        outer_max_y - outer_min_y,
        outer_max_z - outer_min_z,
        origin=(outer_min_x, outer_min_y, outer_min_z),
    )

    inner_space_cutter = create_box(
        inner_max_x - inner_min_x,
        inner_max_y - inner_min_y,
        outer_max_z - inner_min_z + 1,
        origin=(inner_min_x, inner_min_y, inner_min_z),
    )
    housing_box = housing_box.cut(inner_space_cutter)

    psu_y_faces = sorted([psu_1_min[1], psu_1_max[1], psu_2_min[1], psu_2_max[1]])
    psu_gap_center_y = (psu_y_faces[1] + psu_y_faces[2]) / 2
    rib_z_min = outer_min_z + wall_thickness
    rib_height = outer_max_z - rib_z_min
    rib_y_min = psu_gap_center_y - cooleon_pair_housing_mount_rib_thickness / 2
    left_rib = create_box(
        cooleon_pair_housing_mount_rib_length,
        cooleon_pair_housing_mount_rib_thickness,
        rib_height,
        origin=(
            inner_min_x + cooleon_pair_housing_mount_rib_end_inset,
            rib_y_min,
            rib_z_min,
        ),
    )
    right_rib = create_box(
        cooleon_pair_housing_mount_rib_length,
        cooleon_pair_housing_mount_rib_thickness,
        rib_height,
        origin=(
            inner_max_x
            - cooleon_pair_housing_mount_rib_end_inset
            - cooleon_pair_housing_mount_rib_length,
            rib_y_min,
            rib_z_min,
        ),
    )
    housing_box = housing_box.fuse(left_rib).fuse(right_rib)

    lid_screw_record = MScrew.from_size(cooleon_pair_housing_lid_screw_size)
    lid_screw_bosses = PartCollector()
    lid_pilot_holes = PartCollector()
    lid_clearance_holes = PartCollector()
    lid_screws = PartCollector()
    lid_bosses = []
    lid_screw_positions = []
    boss_radius = cooleon_pair_housing_lid_screw_boss_diameter / 2
    boss_height = outer_max_z - rib_z_min
    lid_z_min = outer_max_z + cooleon_pair_housing_lid_body_clearance
    lid_z_top = lid_z_min + cooleon_pair_housing_lid_thickness
    for x_alignment in [Alignment.LEFT, Alignment.RIGHT]:
        for y_alignment in [Alignment.FRONT, Alignment.BACK]:
            x = (
                outer_min_x + cooleon_pair_housing_lid_screw_inset
                if x_alignment == Alignment.LEFT
                else outer_max_x - cooleon_pair_housing_lid_screw_inset
            )
            y = (
                outer_min_y + cooleon_pair_housing_lid_screw_inset
                if y_alignment == Alignment.FRONT
                else outer_max_y - cooleon_pair_housing_lid_screw_inset
            )
            lid_boss = create_cylinder(
                boss_radius,
                boss_height,
                origin=(x, y, rib_z_min),
            )
            lid_screw_bosses = lid_screw_bosses.fuse(lid_boss)
            lid_bosses.append(lid_boss)

            lid_pilot_hole = create_self_threading_hole_cutter(
                cooleon_pair_housing_lid_screw_size,
                boss_height + 2,
                core_radius_adjustment=(
                    cooleon_pair_housing_self_threading_core_radius_adjustment
                ),
                lead_in=cooleon_pair_housing_self_threading_lead_in,
            )
            lid_pilot_hole = translate(x, y, rib_z_min - 1)(lid_pilot_hole)
            lid_pilot_holes = lid_pilot_holes.fuse(lid_pilot_hole)

            lid_clearance_hole = create_cylinder(
                lid_screw_record.clearance_hole_loose / 2,
                cooleon_pair_housing_lid_thickness + 2,
                origin=(x, y, lid_z_min - 1),
            )
            lid_clearance_holes = lid_clearance_holes.fuse(lid_clearance_hole)
            lid_screw_positions.append((lid_pilot_hole, lid_clearance_hole))

            lid_screw = create_cylinder_screw(
                cooleon_pair_housing_lid_screw_size,
                cooleon_pair_housing_lid_screw_length,
            )
            lid_screw = translate(
                x,
                y,
                lid_z_top - cooleon_pair_housing_lid_screw_length,
            )(lid_screw)
            lid_screws = lid_screws.fuse(lid_screw)

    housing_box = housing_box.fuse(lid_screw_bosses)
    housing_box = housing_box.cut(lid_pilot_holes)

    vent_cutters = PartCollector()
    vent_panel_length = inner_max_x - inner_min_x
    vent_panel_height = cooleon_pair_housing_vent_height
    vent_panel_depth = wall_thickness + 4
    vent_center_z = (
        inner_min_z + (inner_max_z - inner_min_z) * cooleon_pair_housing_vent_row_z
    )
    vent_min_z = vent_center_z - vent_panel_height / 2
    vent_band_width = (
        cooleon_pair_housing_vent_pitch - cooleon_pair_housing_vent_diamond_size
    )
    for y_center in [
        outer_min_y + wall_thickness / 2,
        outer_max_y - wall_thickness / 2,
    ]:
        side_vent_cutters = create_trellis_cutters(
            length=vent_panel_length,
            width=vent_panel_height,
            thickness=vent_panel_depth,
            x_border_width=cooleon_pair_housing_vent_end_inset,
            y_border_width=vent_band_width,
            band_width=vent_band_width,
            band_pitch=cooleon_pair_housing_vent_pitch,
            cutter_depth=vent_panel_depth,
        )
        side_vent_cutters = rotate(
            -90,
            center=get_bounding_box_center(side_vent_cutters),
            axis=(1, 0, 0),
        )(side_vent_cutters)
        side_vent_target = create_box(
            vent_panel_length,
            vent_panel_depth,
            vent_panel_height,
            origin=(
                inner_min_x,
                y_center - vent_panel_depth / 2,
                vent_min_z,
            ),
        )
        side_vent_cutters = align(side_vent_cutters, side_vent_target, Alignment.CENTER)
        vent_cutters = vent_cutters.fuse(side_vent_cutters)
    housing_box = housing_box.cut(vent_cutters)

    lid_length = outer_max_x - outer_min_x + 2 * cooleon_pair_housing_lid_outer_overhang
    lid_width = outer_max_y - outer_min_y + 2 * cooleon_pair_housing_lid_outer_overhang
    lid_min_x = outer_min_x - cooleon_pair_housing_lid_outer_overhang
    lid_min_y = outer_min_y - cooleon_pair_housing_lid_outer_overhang

    lid_base = create_filleted_box(
        lid_length,
        lid_width,
        cooleon_pair_housing_lid_thickness,
        fillet_radius=min(
            wall_thickness,
            cooleon_pair_housing_lid_outer_overhang,
        ),
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    lid_base = translate(lid_min_x, lid_min_y, lid_z_min)(lid_base)

    lid_drop_depth = (
        cooleon_pair_housing_lid_body_clearance + cooleon_pair_housing_lid_rim_depth
    )
    lid_rim_outer_length = (
        inner_max_x - inner_min_x - 2 * cooleon_pair_housing_lid_rim_clearance
    )
    lid_rim_outer_width = (
        inner_max_y - inner_min_y - 2 * cooleon_pair_housing_lid_rim_clearance
    )
    lid_rim_inner_length = lid_rim_outer_length - 2 * (
        cooleon_pair_housing_lid_rim_thickness
    )
    lid_rim_inner_width = lid_rim_outer_width - 2 * (
        cooleon_pair_housing_lid_rim_thickness
    )
    lid_ring_fillet = min(
        wall_thickness,
        cooleon_pair_housing_lid_rim_thickness / 2 - 0.1,
    )
    lid_drop_z_min = lid_z_min - lid_drop_depth
    lid_rim = create_filleted_box(
        lid_rim_outer_length,
        lid_rim_outer_width,
        lid_drop_depth,
        fillet_radius=lid_ring_fillet,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    lid_rim = translate(
        (inner_min_x + inner_max_x - lid_rim_outer_length) / 2,
        (inner_min_y + inner_max_y - lid_rim_outer_width) / 2,
        lid_drop_z_min,
    )(lid_rim)
    lid_rim_inner_cutter = create_box(
        lid_rim_inner_length,
        lid_rim_inner_width,
        lid_drop_depth + 2,
        origin=(
            (inner_min_x + inner_max_x - lid_rim_inner_length) / 2,
            (inner_min_y + inner_max_y - lid_rim_inner_width) / 2,
            lid_drop_z_min - 1,
        ),
    )
    lid_rim = lid_rim.cut(lid_rim_inner_cutter)

    lid_outer_lip_inner_length = (
        outer_max_x - outer_min_x + 2 * cooleon_pair_housing_lid_rim_clearance
    )
    lid_outer_lip_inner_width = (
        outer_max_y - outer_min_y + 2 * cooleon_pair_housing_lid_rim_clearance
    )
    lid_outer_lip_outer_length = lid_outer_lip_inner_length + 2 * (
        cooleon_pair_housing_lid_rim_thickness
    )
    lid_outer_lip_outer_width = lid_outer_lip_inner_width + 2 * (
        cooleon_pair_housing_lid_rim_thickness
    )
    lid_outer_lip = create_filleted_box(
        lid_outer_lip_outer_length,
        lid_outer_lip_outer_width,
        lid_drop_depth,
        fillet_radius=lid_ring_fillet,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    lid_outer_lip = translate(
        (outer_min_x + outer_max_x - lid_outer_lip_outer_length) / 2,
        (outer_min_y + outer_max_y - lid_outer_lip_outer_width) / 2,
        lid_drop_z_min,
    )(lid_outer_lip)
    lid_outer_lip_inner_cutter = create_box(
        lid_outer_lip_inner_length,
        lid_outer_lip_inner_width,
        lid_drop_depth + 2,
        origin=(
            (outer_min_x + outer_max_x - lid_outer_lip_inner_length) / 2,
            (outer_min_y + outer_max_y - lid_outer_lip_inner_width) / 2,
            lid_drop_z_min - 1,
        ),
    )
    lid_outer_lip = lid_outer_lip.cut(lid_outer_lip_inner_cutter)

    for lid_boss in lid_bosses:
        lid_boss_relief_cutter = materialize_bounding_box(
            lid_boss,
            x_enlargement=cooleon_pair_housing_lid_screw_inset,
            y_enlargement=cooleon_pair_housing_lid_screw_inset,
            z_enlargement=cooleon_pair_housing_lid_body_clearance + 0.2,
        )
        lid_rim = lid_rim.cut(lid_boss_relief_cutter)
        lid_outer_lip = lid_outer_lip.cut(lid_boss_relief_cutter)

    lid = lid_base.fuse(lid_rim).fuse(lid_outer_lip)
    lid = lid.cut(lid_clearance_holes)

    housing = LeaderFollowersCuttersPart(leader=housing_box)
    housing.add_named_follower(lid, "cooleon_pair_housing_lid")
    housing.add_named_cutter(inner_space_cutter, "inner_space")
    housing.add_named_cutter(vent_cutters, "side_vent_diamond_cutters")
    housing.add_named_cutter(lid_pilot_holes, "lid_mount_pilot_holes")
    housing.add_named_cutter(lid_clearance_holes, "lid_mount_clearance_holes")
    for index, (pilot_hole, clearance_hole) in enumerate(lid_screw_positions, start=1):
        housing.add_named_cutter(pilot_hole, f"lid_mount_pilot_hole_{index}")
        housing.add_named_cutter(clearance_hole, f"lid_mount_clearance_hole_{index}")
    housing.add_named_non_production_part(
        psu_pair_reference,
        "cooleon_psu_pair_body_reference",
    )
    housing.add_named_non_production_part(lid_screws, "lid_mount_screws")

    return housing
