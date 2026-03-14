from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import ExtrusionProfileType
from mege_ender_3v3ke_idex.designs.nema_motors import NemaSizes
from shellforgepy.simple import *


BIG_THING = 500

mgn_12h_carriage_width = 27
mgn_12h_carriage_length = 45.4
mgn_12h_screw_hole_pitch = 20
mgn_12h_height = 10
mgn_12h_screw_hole_depth = 3.5
mgn_12h_h1 = 3.4


axial_ball_bearing_8_x_19_ball_count = 6
axial_ball_bearing_8_x_19_ball_diameter = 3.17
axial_ball_bearing_8_x_19_ball_holder_disc_inner_diameter = 9.6
axial_ball_bearing_8_x_19_ball_holder_disc_outer_diameter = 17.45
axial_ball_bearing_8_x_19_ball_holder_disc_thickness = 1.9
axial_ball_bearing_8_x_19_disc_thickness = 2.15
axial_ball_bearing_8_x_19_inner_diameter = 8.2
axial_ball_bearing_8_x_19_outer_diameter = 19
axial_ball_bearing_8_x_19_thickness = 7
axial_bearing_stopper_inner_diameter = 16
axial_bearing_stopper_outer_diameter = 24
axial_bearing_stopper_thickness = 4
axial_rod_clamp_cylinder_head_cutter_clearance = 0.25
axial_rod_clamp_gap = 1.2
axial_rod_clamp_inner_diameter = 8.2
axial_rod_clamp_nut_clearance = 0.15
axial_rod_clamp_outer_diameter = 30
axial_rod_clamp_outer_diameter_cutting_depth = 9
axial_rod_clamp_screw_hole_distance_from_center = 10
axial_rod_clamp_screw_length = 18
axial_rod_clamp_screw_size = "M3"
axial_rod_clamp_thickness = 10
axis_holder_fillet_radius = 1
axis_holder_thickness = 6
axle_screw_nut_hole_depth = 4
axle_screw_nut_slack = 0.4
axle_screw_size = "M3"
bb_608z_height = 7
bb_608z_outer_diameter = 22
blower_center_offset = 4
blowers_down_angle = 35
blowers_duct_diameter = 6
blowers_nozzle_center_distance = 10
blowers_wall = 1.5
counter_flange_mount_screw_length = 14
counter_flange_mount_screw_size = "M3"
duct_extension_width = 20
duct_front_mount_plate_height = 12
duct_front_mount_plate_height_border = 2.5
duct_front_mount_plate_offset = -3
duct_front_mount_plate_thickness = 4
duct_front_mount_plate_width = 41
duct_front_mount_plate_width_border = 10
endcap_axle_screw_length = 25
endcap_axle_screw_size = "M3"
endcap_belt_clearance = 6
endcap_belt_vertical_clearance = 1.2
endcap_belt_width = 6
endcap_clearance = 0.8
endcap_fillet_radius = 2
endcap_holder_length = 10
endcap_holder_thickness = 4
endcap_idler_clearance = 1.5
endcap_idler_tooth_count = 20
endcap_mount_fillet_radius = 2
endcap_mount_screw_size = "M5"
endcap_outer_box_back_wall = 4
endcap_profile_clearance = 0.2
endcap_profile_groove_depth = 8
endcap_profile_overlap = 15
endcap_side_hole_boundary = 5
endcap_side_hole_size = 4
endcap_tensioner_cage_back_wall = 8
endcap_tensioner_cage_clearance = 0.3
endcap_tensioner_length = 16
endcap_tensioner_outer_box_bottom_cage_clearance = 0.8
endcap_tensioner_outer_box_bottom_thickness = 1
endcap_tensioner_screw_size = "M3"
endcap_tensioner_slit_width = 0.4
endcap_tensioner_travel = 14
endcap_top_bottom_wall = 5
endcap_wall = 3.5
endstop_holder_groove_holder_bottom_width = 6.3
endstop_holder_groove_holder_height = 5
endstop_holder_groove_holder_slit = 1.5
endstop_holder_groove_holder_top_width = 6.0
endstop_holder_mount_plate_length = 20
endstop_holder_mount_plate_thickness = 4.5
endstop_holder_mount_plate_width = 8
endstop_holder_mount_screw_size = "M3"
endstop_holder_stack_gap = 30
endstop_holder_y_offset = -4
endstop_holder_z_offset = 8
feeder_ring_extra_angle = 10
feeder_ring_height = 11
feeder_ring_inner_diameter = 37
feeder_ring_rotation_angle = -10
feeder_ring_wall = 1.5
feeder_ring_width = 11
frame_alu_profile_size = 40
frame_width = 350
holder_mount_plate_depth = 28
holder_mount_plate_left_extension = 19
holder_mount_plate_size = 8
holder_mount_plate_spacer = 12
holder_mount_plate_thickness = 2.5
holder_mount_plate_top_offset = 5
idler_cage_back_wall = 4
idler_cage_clearance = 0.5
idler_cage_extra_screw_length = 6
idler_cage_idler_tooth_count = 20
idler_cage_overlength = 6
idler_cage_top_bottom_thickness = 4
idler_cage_wall = 2
idler_mount_axle_clearance = 0.1
idler_mount_axle_diameter = MScrew.from_size("M3").clearance_hole_normal
idler_mount_diameter = 4
idler_mount_thickness = 1
igus_drylin_bearing_inner_diameter = 8
igus_drylin_bearing_length = 25
igus_drylin_bearing_outer_diameter = 16
inset_cutter_hole_slack = 0.05
jig_thickness = 3.6
jig_width = 6
link_flange_depth = 12
link_flange_thickness = 7
link_screw_length = 20
link_screw_size = "M5"
motor_idler_out_offset = 17
motor_idler_profile_gap = 1
motor_mount_axle_clearance = 0.3
motor_mount_boss_clearance = 0.6
motor_mount_boss_clearance_z = 8
motor_mount_plate_fillet_radius = 2
motor_mount_plate_size = 52
motor_mount_plate_thickness = 5
motor_pulley_gap = 2
motor_pulley_idlers_distance = 28
motor_size = 42.3
motor_y_offset = 15
motor_z_offset = 2
mount_plate_connector_depth = 20
mount_plate_connector_link_thickness = 6
mount_shield_depth = 6
mount_shield_fillet_radius = 1
mount_shield_oversize_z = 0
mount_shield_width = 17
nitehawk_back_triangle_y_offset = 27.8
nitehawk_board_angle = 0
nitehawk_front_cutter_back_width = 10.8
nitehawk_front_cutter_width = 18.8
nitehawk_front_cutter_y_size = 7.0
nitehawk_heater_connector_length = 7.7
nitehawk_heater_connector_thickness = 8.8
nitehawk_heater_connector_width = 7.7
nitehawk_heater_connector_x_offset_from_right = 10.3
nitehawk_heater_connector_y_offset_from_front = 5.1
nitehawk_height = 40.8
nitehawk_holder_cable_attachment_fillet_radius = 3
nitehawk_holder_cable_attachment_holes_diameter = 4
nitehawk_holder_cable_attachment_length = 45
nitehawk_holder_cable_attachment_num_holes = 3
nitehawk_holder_cable_attachment_thickness = 4
nitehawk_holder_cable_attachment_y_offset = 20
nitehawk_holder_extruder_gap = 12
nitehawk_holder_fillet_radius = 3
nitehawk_holder_height_extension = -5
nitehawk_holder_height_offset = 0
nitehawk_holder_mount_screw_size = "M3"
nitehawk_holder_mount_tower_diameter = 6.5
nitehawk_holder_mount_tower_height = 5
nitehawk_holder_mount_tower_x_offset = 0
nitehawk_holder_mount_tower_y_offset = 0
nitehawk_holder_slit_height = 6
nitehawk_holder_thickness = 3
nitehawk_holder_width_extension = 15
nitehawk_holder_width_offset = 2
nitehawk_hole_diameter = 3.1
nitehawk_holes_center_distance = 43
nitehawk_holes_y_offset = 16
nitehawk_mount_tower_base_extension = 2.0
nitehawk_nut_cutter_slack = 0.19
nitehawk_pcb_thickness = 1.6
nitehawk_plug_length = 8.8
nitehawk_plug_overhang = 4
nitehawk_plug_thickness = 5.25
nitehawk_plug_width = 14
nitehawk_top_width = 23
nitehawk_umbilical_cable_diameter = 5.1
nitehawk_umbilical_cable_length = 30
nitehawk_umbilical_connector_cable_connector_end_diameter = 9.4
nitehawk_umbilical_connector_cable_connector_height = 14.4
nitehawk_umbilical_connector_gap = 0.15
nitehawk_umbilical_connector_height = 13.2
nitehawk_width = 51.3
num_blowers = 3
nut_cutter_offset_z = 2
part_fan_axis_from_left_offset = 17.2
part_fan_bed_clearance = 10
part_fan_body_cutter_clearance = 0.1
part_fan_diameter = 30
part_fan_duct_extension_length = 55
part_fan_ducts_clearance = 2
part_fan_fillet_radius = 2
part_fan_hole_diameter = 31
part_fan_mount_plate_thickness = 3.8
part_fan_nut_cutter_clearance = 0.15
part_fan_outlet_connector_length = 2
part_fan_screw_hole_inset = 2.5
part_fan_screw_mount_base_thickness = 3.5
part_fan_screw_mount_cutout_fillet_radius = 2
part_fan_screw_mount_cutout_size = 5.3
part_fan_screw_size = "M2.5"
part_fan_size = 40.2
part_fan_thickness = 10.5
part_fan_window_cutter_outside_length = 3
part_fan_window_height = 8.1
part_fan_window_width = 28
pillow_block_bearing_base_gap_length = 24.7
pillow_block_bearing_base_overall_length = 55
pillow_block_bearing_base_thickness = 5.1
pillow_block_bearing_base_width = 13.1
pillow_block_bearing_cage_diameter = 30
pillow_block_bearing_cage_rim = 2
pillow_block_bearing_cage_thickness = 9.6
pillow_block_bearing_mount_hole_center_distance = 41.5
pillow_block_bearing_mount_hole_diameter = 4.6
pillow_block_bearing_rod_holder_inner_diameter = 8.03
pillow_block_bearing_rod_holder_length = 11
pillow_block_bearing_rod_holder_outer_diameter = 12
pillow_block_bottom_base_bridge_width = 3.5
print_bed_depth = 310
print_bed_y_travel = 310
print_bed_thickness = 4
print_bed_width = 310
pulley_clearance_z = 0.8
rail_mount_screw_size = "M3"
tool_head_additional_mount_plate_clearance = 0.5
tool_head_additional_mount_plate_depth = 10
tool_head_additional_mount_plate_depth_offset = 0
tool_head_additional_mount_plate_fillet_radius = 2
tool_head_additional_mount_plate_height = 24
tool_head_additional_mount_plate_thickness = 3
tool_head_additional_mount_plate_z_offset = -10
tool_head_front_mount_plate_connector_height = 14
tool_head_front_mount_plate_connector_thickness = 4
tool_head_front_mount_plate_connector_width = 7.5
tool_head_mount_base_plate_height = 20
tool_head_mount_base_plate_thickness = 5
tool_head_mount_belt_clamp_base_thickness = 5
tool_head_mount_belt_clamp_gap = 3
tool_head_mount_belt_clamp_length = 12
tool_head_mount_belt_clamp_thickness = 5
tool_head_mount_belt_clamp_y_offset = 8
tool_head_mount_belt_deflector_belt_clearance = 3.5
tool_head_mount_belt_deflector_belt_z_clearance = 0.3
tool_head_mount_belt_deflector_cage_thickness = 3
tool_head_mount_belt_deflector_into_profile_distance = 0.3
tool_head_mount_belt_deflector_thickness = 3
tool_head_mount_belt_path_cutter_clearance = 0.5
tool_head_mount_carriage_mount_plate_fillet_radius = 1
tool_head_mount_carriage_mount_plate_thickness = 4
tool_head_mount_carriage_mount_plate_width = 78
tool_head_mount_clamp_base_cutter_clearance = 0.8
tool_head_mount_clamp_base_cutter_depth_clearance = 0.1
tool_head_mount_extruder_cutout_carriage_gap = 3
tool_head_mount_extruder_cutout_fillet_radius = 4
tool_head_mount_extruder_cutout_width = 58
tool_head_mount_nitehawk_board_clearance = 1
tool_head_mount_plate_carriage_clearance = 3
tool_head_mount_side_clearance = 0.5
tool_head_mount_side_plate_depth = 20
tool_head_mount_side_plate_height = 40
tool_head_mount_side_plate_thickness = 8
tool_head_mount_side_stiffener_thickness = 5
tool_head_mount_tool_head_base_plate_clearance = 0.5
tool_head_mount_tool_head_x_offset = 8
tool_head_mount_tool_head_z_offset = 10
tool_head_mount_x_offset = 20
v_slot_wheel_608z_bearing_radial_clearance = 0.0
v_slot_wheel_608z_ease_in_size = 0.7
v_slot_wheel_608z_inner_width = 5
v_slot_wheel_608z_outer_diameter = 27.5
v_slot_wheel_608z_singularity_cutter_thickness = 0.15
v_slot_wheel_608z_top_bottom_holder_axial_clearance = 0.05
v_slot_wheel_608z_top_bottom_holder_size = 0.65
v_slot_wheel_608z_width = 10.2
x_axis_motor_axle_length = 14
x_axis_profile_length = 600  # original length of profiles I got - no need to cut!
x_axis_profile_pitch = 48
x_axis_rail_length = 450
x_axis_x_travel = 355
y_axis_carriage_spacing = 80
y_axis_profile_extension = 20
y_axis_rail_spacing = 200
z_axis_base_z_offset = -20
z_axis_carriage_back_depth = 40
z_axis_carriage_back_height = 12
z_axis_carriage_bearing_inset = 5
z_axis_carriage_fillet_radius = 4
z_axis_carriage_front_depth = 25
z_axis_carriage_mount_screw_size = "M3"
z_axis_carriage_profile_clearance = 2
z_axis_carriage_rod_clamp_screw_inset = 4
z_axis_carriage_threaded_rod_clearance = 0.3
z_axis_carriage_width = 45
z_axis_carriage_x_axis_connector_thickness = 8
z_axis_carriage_z_offset = 118
z_axis_creality_nut_threaded_rod_cuide_cutter_clearance = 0.3
z_axis_cylinder_head_clearance = 0.6
z_axis_default_clearance_hole_type = "loose"
z_axis_default_screw_nut_cutter_clearance = 0.2
z_axis_guide_distance = 256
z_axis_guide_rod_carriage_clamp_screw_length = 20
z_axis_guide_rod_clamp_depth = 23.5
z_axis_guide_rod_clamp_screw_length = 20
z_axis_guide_rod_clamp_thickness = 22
z_axis_guide_rod_clamp_width = 28
z_axis_guide_rod_diameter = 8
z_axis_guide_rod_length = 550
z_axis_guide_rod_profile_distance = 55
z_axis_guide_rod_threaded_rod_distance = 18
z_axis_motor_mount_plate_depth = 69
z_axis_motor_mount_plate_profile_distance = 0
z_axis_motor_mount_plate_size = 52
z_axis_nut_screw_hole_clearence_type = "loose"
z_axis_pillow_block_bearing_z_offset = 2
z_axis_profile_length = 550
z_axis_profile_mount_plate_fillet_radius = 3
z_axis_profile_mount_plate_height = 33
z_axis_profile_mount_plate_thickness = 5
z_axis_profile_mount_width = 28
z_axis_rod_clamp_gap = 1.0
z_axis_thraded_rod_z_offset = 90
z_axis_threaded_rod_coupler_overlap = 17.5
z_axis_threaded_rod_diameter = 8
z_axis_threaded_rod_length = 500
z_axis_threaded_rod_profile_distance = 22
z_axis_top_mount_fillet_radius = 5
z_axis_top_mount_holder_depth = 20
z_axis_top_mount_holder_height = 35
z_axis_top_mount_profile_mount_width = 40
z_axis_top_mount_reinforcement_factor = 0.9
z_axis_top_mount_reinforcement_thickness = 3
z_axis_top_mount_screw_inset = 4
z_axis_top_mount_screw_length = 16
z_axis_top_mount_screw_size = "M3"
z_axis_top_mount_thickness = 5
z_axis_top_mount_threaded_rod_clearance = 1.5
z_axis_top_mount_width = 40
z_axis_x_axis_carriage_vertical_offset = 8
z_axis_x_axis_to_carriage_gap = 28
z_axis_x_offset_from_center = 235
z_axis_y_offset = 140
z_axis_z_travel = 300


############## Calculated parameters ##############
tool_head_mount_y_extension = tool_head_mount_side_plate_depth + 1

motor_x_offset = z_axis_guide_distance / 2 - 60

mount_plate_connector_length = (
    z_axis_guide_distance - 2 * motor_x_offset - motor_size + 8
)


mount_plate_link_width = mount_plate_connector_length * 0.8
axis_holder_width = mount_plate_connector_length

flange_thickness = 5
flange_depth = 15
bevel_depth = flange_depth * 0.75
mount_flange_bevel_oversize = 2.0
idler_screw_size = "M3"
idler_screw_head_clearance = 0.3
mount_flange_screw_hole_inset = 10
axis_holder_depth = ExtrusionProfileType.PROFILE_2020.grid_pitch_mm + flange_depth
z_axis_top_mount_depth = (
    z_axis_guide_rod_profile_distance + 2 * z_axis_guide_rod_diameter
)
y_axis_rail_length = (
    print_bed_depth + y_axis_carriage_spacing +  mgn_12h_carriage_length
)

y_axis_profile_length = y_axis_rail_length + 2 * y_axis_profile_extension

nitehawk_holder_width = NemaSizes.NEMA17.size_mm + nitehawk_holder_width_extension
nitehawk_holder_height = NemaSizes.NEMA17.size_mm + nitehawk_holder_height_extension

frame_depth = y_axis_profile_length + 2 * (ExtrusionProfileType.PROFILE_4040.size_mm[1])
nitehawk_holder_mount_cut_radius = nitehawk_holder_height * 0.5
nitehawk_holder_cable_attachment_width = nitehawk_plug_width + 4

z_axis_carriage_front_height = (
    x_axis_profile_pitch
    + ExtrusionProfileType.PROFILE_2020.size_mm[1]
    + 2 * z_axis_carriage_x_axis_connector_thickness
)


part_fan_parameters = {
    Alignment.LEFT: {  # this is the vertical downblower on the left
        "around_angle": 0,
        "x_offset": 27.8,
        "y_offset": 35,
        "z_offset": 6,
        "rotation": 90,
        "tilt": 0,
        "mount_plate_blow_direction_oversize": 3,
        "mount_plate_cross_oversize": 2,
        "mount_plate_blow_direction_offset": -1,
    },
    Alignment.RIGHT: {  # this is the flat blower on the back
        "around_angle": 90,
        "x_offset": 21,
        "y_offset": 5,
        "z_offset": -4.5,
        "rotation": 15,
        "tilt": 0,
        "mount_plate_blow_direction_oversize": 7,
        "mount_plate_cross_oversize": 8,
        "mount_plate_blow_direction_offset": -2,
    },
}

__all__ = sorted(
    name
    for name, value in globals().items()
    if not name.startswith("_")
    and name not in {"math", "__builtins__"}
    and not callable(value)
    and not isinstance(value, type)
)
