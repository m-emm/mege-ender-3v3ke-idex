from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import ExtrusionProfileType
from shellforgepy.simple import *

BIG_THING = 500

motor_size = 42.3
axis_profile_length = 500
rail_length = 450
axis_profile_pitch = 40
motor_y_offset = 15

rail_mount_screw_size = "M3"

z_axis_guide_distance = 256

motor_x_offset = z_axis_guide_distance / 2 - 60
motor_z_offset = 2
motor_idler_out_offset = 17

motor_pulley_idlers_distance = 28
motor_pulley_gap = 2


x_axis_motor_axle_length = 14

motor_idler_profile_gap = 1


motor_mount_plate_size = 52


motor_mount_plate_thickness = 5
motor_mount_plate_fillet_radius = 2
motor_mount_axle_clearance = 0.3
motor_mount_boss_clearance = 0.6
motor_mount_boss_clearance_z = 8

idler_mount_diameter = 4
idler_mount_thickness = 1
idler_mount_axle_clearance = 0.1
idler_mount_axle_diameter = MScrew.from_size("M3").clearance_hole_normal
axle_screw_size = "M3"
axle_screw_nut_hole_depth = 4
axle_screw_nut_slack = 0.4

mount_shield_width = 17
mount_shield_depth = 6
mount_shield_fillet_radius = 1
mount_shield_oversize_z = 0


mount_plate_connector_length = (
    z_axis_guide_distance - 2 * motor_x_offset - motor_size + 8
)
mount_plate_connector_depth = 20

mount_plate_link_width = mount_plate_connector_length * 0.8
mount_plate_connector_link_thickness = 6

pulley_clearance_z = 0.8

flange_thickness = 5
flange_depth = 15
bevel_depth = flange_depth * 0.75
mount_flange_bevel_oversize = 2.0
idler_screw_size = "M3"
idler_screw_head_clearance = 0.3
mount_flange_screw_hole_inset = 10

idler_cage_back_wall = 4
idler_cage_wall = 2
idler_cage_top_bottom_thickness = 4
idler_cage_overlength = 6
idler_cage_clearance = 0.5
idler_cage_extra_screw_length = 6
idler_cage_idler_tooth_count = 20

axis_holder_width = mount_plate_connector_length
axis_holder_depth = ExtrusionProfileType.PROFILE_2020.grid_pitch_mm + flange_depth
axis_holder_thickness = 6
axis_holder_fillet_radius = 1
counter_flange_mount_screw_size = "M3"
counter_flange_mount_screw_length = 14

nut_cutter_offset_z = 2


link_screw_size = "M5"
link_screw_length = 20

link_flange_thickness = 7
link_flange_depth = 12


endcap_wall = 3
endcap_top_bottom_wall = 5
endcap_clearance = 0.8
endcap_holder_thickness = 4
endcap_holder_length = 10
endcap_fillet_radius = 2
endcap_idler_tooth_count = 20
endcap_profile_overlap = 15
endcap_profile_clearance = 0.2
endcap_axle_screw_length = 25
endcap_axle_screw_size = "M3"
inset_cutter_hole_slack = 0.05
endcap_tensioner_length = 16
endcap_tensioner_slit_width = 0.4
endcap_idler_clearance = 1.5
endcap_belt_clearance = 6
endcap_tensioner_cage_clearance = 0.3
endcap_tensioner_travel = 14
endcap_belt_width = 6
endcap_profile_groove_depth = 8
endcap_belt_vertical_clearance = 1.2
endcap_tensioner_screw_size = "M3"
endcap_tensioner_cage_back_wall = 8
endcap_outer_box_back_wall = 4
endcap_mount_screw_size = "M5"

endcap_mount_fillet_radius = 2

endcap_side_hole_size = 4
endcap_side_hole_boundary = 5

endcap_tensioner_outer_box_bottom_thickness = 1
endcap_tensioner_outer_box_bottom_cage_clearance = 0.8


jig_width = 6
jig_thickness = 3.6

tool_head_mount_carriage_mount_plate_thickness = 4
tool_head_mount_carriage_mount_plate_fillet_radius = 1


tool_head_mount_base_plate_thickness = 10
tool_head_mount_base_plate_height = 45
tool_head_belt_clamp_gap = 3


tool_head_mount_side_clearance = 0.5
carriage_mount_plate_width = 75
tool_head_mount_side_stiffener_thickness = 2

tool_head_mount_side_plate_depth = 12
tool_head_mount_y_extension = tool_head_mount_side_plate_depth + 1

tool_head_mount_side_plate_thickness = 2
tool_head_mount_belt_clamp_thickness = 3.5
tool_head_mount_belt_clamp_base_thickness = 5
tool_head_mount_clamp_base_cutter_clearance = 0.8
tool_head_mount_clamp_base_cutter_depth_clearance = 0.1
tool_head_mount_belt_path_cutter_clearance = 0.5
tool_head_mount_belt_deflector_thickness = 3
tool_head_mount_belt_deflector_cage_thickness = 3
tool_head_mount_belt_deflector_belt_clearance = 3.5
tool_head_mount_belt_deflector_belt_z_clearance = 0.3
tool_head_mount_belt_deflector_into_profile_distance = 0.3


__all__ = sorted(
    name
    for name, value in globals().items()
    if not name.startswith("_")
    and name not in {"math", "__builtins__"}
    and not callable(value)
    and not isinstance(value, type)
)
