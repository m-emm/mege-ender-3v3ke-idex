from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import ExtrusionProfileType
from shellforgepy.simple import *
from mege_ender_3v3ke_idex.designs.nema_motors import NemaSizes

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


tool_head_mount_base_plate_height = 37
tool_head_mount_base_plate_thickness = 10
tool_head_mount_belt_clamp_base_thickness = 5
tool_head_mount_belt_clamp_gap = 3
tool_head_mount_belt_clamp_thickness = 3.5
tool_head_mount_belt_clamp_y_offset = 8
tool_head_mount_belt_deflector_belt_clearance = 3.5
tool_head_mount_belt_deflector_belt_z_clearance = 0.3
tool_head_mount_belt_deflector_cage_thickness = 3
tool_head_mount_belt_deflector_into_profile_distance = 0.3
tool_head_mount_belt_deflector_thickness = 3
tool_head_mount_belt_path_cutter_clearance = 0.5
tool_head_mount_carriage_mount_plate_fillet_radius = 1
tool_head_mount_carriage_mount_plate_thickness = 4
tool_head_mount_carriage_mount_plate_width = 75
tool_head_mount_clamp_base_cutter_clearance = 0.8
tool_head_mount_clamp_base_cutter_depth_clearance = 0.1
tool_head_mount_extruder_cutout_carriage_gap = 3
tool_head_mount_extruder_cutout_fillet_radius = 4
tool_head_mount_extruder_cutout_width = 40
tool_head_mount_nitehawk_board_clearance = 1
tool_head_mount_side_clearance = 0.5
tool_head_mount_side_plate_depth = 20
tool_head_mount_side_plate_thickness = 5
tool_head_mount_side_stiffener_thickness = 5
tool_head_mount_sprite_extruder_clearance = 6
tool_head_mount_tool_head_x_offset = 0
tool_head_mount_tool_head_z_offset = 38
tool_head_mount_y_extension = tool_head_mount_side_plate_depth + 1
tool_head_mount_belt_clamp_length = 12

tool_head_additional_mount_plate_thickness = 3

tool_head_additional_mount_plate_height = 10
tool_head_additional_mount_plate_depth = 19

tool_head_additional_mount_plate_fillet_radius = 2
tool_head_additional_mount_plate_clearance = 0.5
tool_head_additional_mount_plate_depth_offset = -7


nitehawk_holder_extruder_gap = 2
part_fan_bed_clearance = 10
part_fan_body_cutter_clearance = 0.1
part_fan_window_cutter_outside_length = 3

part_fan_ducts_clearance = 2
part_fan_mount_plate_thickness = 3.8

part_fan_nut_cutter_clearance = 0.15
part_fan_size = 40.2
part_fan_fillet_radius = 2
part_fan_thickness = 10.5
part_fan_screw_size = "M2.5"
part_fan_screw_hole_inset = 2.5
part_fan_screw_mount_cutout_size = 5.3
part_fan_screw_mount_cutout_fillet_radius = 2
part_fan_screw_mount_base_thickness = 3.5
part_fan_window_width = 28
part_fan_window_height = 8.1
part_fan_hole_diameter = 31
part_fan_diameter = 30
part_fan_axis_from_left_offset = 17.2
part_fan_outlet_connector_length = 2

print_bed_width = 310
print_bed_depth = 310
print_bed_thickness = 4

frame_width = 350
frame_depth = 420
frame_alu_profile_size = 40


nitehawk_width = 51.3
nitehawk_height = 40.8
nitehawk_pcb_thickness = 1.6
nitehawk_top_width = 23
nitehawk_holes_y_offset = 16
nitehawk_holes_center_distance = 43
nitehawk_back_triangle_y_offset = 27.8
nitehawk_hole_diameter = 3.1
nitehawk_plug_width = 14
nitehawk_plug_thickness = 5.25
nitehawk_plug_length = 8.8
nitehawk_plug_overhang = 4
nitehawk_heater_connector_width = 7.7
nitehawk_heater_connector_length = 7.7
nitehawk_heater_connector_thickness = 8.8
nitehawk_heater_connector_x_offset_from_right = 10.3
nitehawk_heater_connector_y_offset_from_front = 5.1
nitehawk_front_cutter_width = 18.8
nitehawk_front_cutter_y_size = 7.0
nitehawk_front_cutter_back_width = 10.8
nitehawk_umbilical_connector_height = 13.2
nitehawk_umbilical_connector_gap = 0.15
nitehawk_umbilical_connector_cable_connector_height = 14.4
nitehawk_umbilical_connector_cable_connector_end_diameter = 9.4
nitehawk_umbilical_cable_diameter = 5.1
nitehawk_umbilical_cable_length = 30

nitehawk_board_angle = 0
nitehawk_holder_thickness = 3
nitehawk_holder_width_extension = 15
nitehawk_holder_height_extension = -5
nitehawk_holder_height_offset = 0
nitehawk_holder_width_offset = 2

nitehawk_holder_width = NemaSizes.NEMA17.size_mm + nitehawk_holder_width_extension
nitehawk_holder_height = NemaSizes.NEMA17.size_mm + nitehawk_holder_height_extension
nitehawk_holder_fillet_radius = 3
nitehawk_holder_mount_tower_diameter = 6.5
nitehawk_holder_mount_tower_height = 5
nitehawk_holder_mount_tower_x_offset = 0
nitehawk_holder_mount_tower_y_offset = 0
nitehawk_holder_mount_screw_size = "M3"
nitehawk_holder_mount_cut_radius = nitehawk_holder_height * 0.5
nitehawk_holder_cable_attachment_width = nitehawk_plug_width + 4
nitehawk_holder_cable_attachment_length = 45
nitehawk_holder_cable_attachment_y_offset = 20
nitehawk_holder_cable_attachment_fillet_radius = 3

nitehawk_holder_cable_attachment_thickness = 4
nitehawk_holder_cable_attachment_holes_diameter = 4
nitehawk_holder_cable_attachment_num_holes = 3

nitehawk_holder_slit_height = 6
nitehawk_nut_cutter_slack = 0.19
nitehawk_mount_tower_base_extension = 2.0


part_fan_parameters = {
    Alignment.LEFT: { # this is the vertical downblower on the left
        "base_rotation": 0,
        "around_angle": 0,
        "x_offset": 27.8,
        "y_offset": 35,
        "z_offset": 10,
        "rotation": 90,
        "tilt": 0,
        "mount_plate_blow_direction_oversize": 15,
        "mount_plate_cross_oversize": 3,
        "mount_plate_blow_direction_offset": -12
    },
    Alignment.RIGHT: { # this is the flat blower on the back
        "base_rotation": 0,
        "around_angle": 90,
        "x_offset": 20,
        "y_offset": 5,
        "z_offset": 0,
        "rotation": 17,
        "tilt": 0,
        "mount_plate_blow_direction_oversize": 7,
        "mount_plate_cross_oversize": 3,
        "mount_plate_blow_direction_offset":-2
    },
}


num_blowers = 3
blower_center_offset = 4
blowers_down_angle = 35
blowers_duct_diameter = 6
blowers_wall = 1.5
blowers_nozzle_center_distance = 10
feeder_ring_height = 11
feeder_ring_width = 11
part_fan_duct_extension_length = 55

feeder_ring_inner_diameter = 37
feeder_ring_wall = 1.5
feeder_ring_extra_angle = 10

feeder_ring_rotation_angle = -10

duct_extension_width = 20


__all__ = sorted(
    name
    for name, value in globals().items()
    if not name.startswith("_")
    and name not in {"math", "__builtins__"}
    and not callable(value)
    and not isinstance(value, type)
)
