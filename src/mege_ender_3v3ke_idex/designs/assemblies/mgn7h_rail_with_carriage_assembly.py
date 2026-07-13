"""Declarative standalone MGN7H rail-with-carriage assembly."""

from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn7h_rail_with_carriage
from shellforgepy.metrics import record_length_metric


def create_mgn7h_rail_with_carriage_assembly(
    *,
    mgn7h_rail_length,
    mgn7h_rail_width,
    mgn7h_rail_height,
    mgn7h_rail_mount_hole_pitch,
    mgn7h_rail_mount_hole_end_offset,
    mgn7h_rail_mount_hole_diameter,
    mgn7h_rail_mount_counterbore_diameter,
    mgn7h_rail_mount_counterbore_depth,
    mgn7h_rail_mount_screw_size,
    mgn7h_rail_side_relief_depth,
    mgn7h_rail_side_relief_height,
    mgn7h_carriage_length,
    mgn7h_carriage_width,
    mgn7h_carriage_height,
    mgn7h_carriage_h1_offset,
    mgn7h_carriage_mount_hole_pitch_x,
    mgn7h_carriage_mount_hole_pitch_y,
    mgn7h_carriage_mount_hole_depth,
    mgn7h_carriage_mount_screw_size,
    mgn7h_carriage_rest_offset_on_rail,
):
    """Create an MGN7H rail leader with a named built-in carriage follower."""

    _ = mgn7h_rail_mount_screw_size

    record_length_metric("linear_rail", "MGN7H", "idex_tap_t0", mgn7h_rail_length)

    return create_mgn7h_rail_with_carriage(
        length_mm=mgn7h_rail_length,
        carriage_offset=mgn7h_carriage_rest_offset_on_rail,
        rail_width=mgn7h_rail_width,
        rail_height=mgn7h_rail_height,
        rail_mount_hole_pitch=mgn7h_rail_mount_hole_pitch,
        rail_mount_hole_end_offset=mgn7h_rail_mount_hole_end_offset,
        rail_mount_hole_diameter=mgn7h_rail_mount_hole_diameter,
        rail_mount_counterbore_diameter=mgn7h_rail_mount_counterbore_diameter,
        rail_mount_counterbore_depth=mgn7h_rail_mount_counterbore_depth,
        rail_side_relief_depth=mgn7h_rail_side_relief_depth,
        rail_side_relief_height=mgn7h_rail_side_relief_height,
        carriage_length=mgn7h_carriage_length,
        carriage_width=mgn7h_carriage_width,
        carriage_height=mgn7h_carriage_height,
        carriage_h1_offset=mgn7h_carriage_h1_offset,
        carriage_mount_hole_pitch_x=mgn7h_carriage_mount_hole_pitch_x,
        carriage_mount_hole_pitch_y=mgn7h_carriage_mount_hole_pitch_y,
        carriage_mount_hole_depth=mgn7h_carriage_mount_hole_depth,
        carriage_mount_screw_size=mgn7h_carriage_mount_screw_size,
    )
