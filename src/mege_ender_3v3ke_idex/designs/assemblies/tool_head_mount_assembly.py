"""Declarative tool head mount assembly."""

from mege_ender_3v3ke_idex.designs.nema_motors import NemaSizes
from shellforgepy.simple import *

hardware_store_angle_width = 14.3
hardware_store_angle_outer_size = 30.3
hardware_store_angle_thickness = 1.5

hardware_store_angle_clearance = 0.8

hardware_store_angle_screw_hole_diameter = 4.7

hardware_store_angle_screw_hole_positions = [ (  7.7, 6.2) , ( 5.7, 20) ]

def create_hardware_store_angle():
    top = create_box(
        hardware_store_angle_width,
        hardware_store_angle_outer_size,
        hardware_store_angle_thickness,
    )

    top_cutter = materialize_bounding_box(
        top,
        x_enlargement=hardware_store_angle_clearance,
        y_enlargement=hardware_store_angle_clearance,
        z_enlargement=hardware_store_angle_clearance,
    )

    for hole_center in hardware_store_angle_screw_hole_positions:
        hole = create_cylinder(
            hardware_store_angle_screw_hole_diameter / 2 ,
            hardware_store_angle_thickness + 2,            
        )

        hole = align(hole, top, Alignment.CENTER)
        hole = align(hole, top, Alignment.EDGE_FRONT)
        hole = align(hole, top, Alignment.EDGE_LEFT)

        hole = translate(hole_center[0] , hole_center[1], 0)(hole)

        top = top.cut(hole)

        smaller_hole = create_cylinder(
            hardware_store_angle_screw_hole_diameter / 2 - hardware_store_angle_clearance,
            hardware_store_angle_thickness + 2,
        )

        smaller_hole = align(smaller_hole, hole, Alignment.CENTER)
        top_cutter = top_cutter.cut(smaller_hole)


    top = LeaderFollowersCuttersPart(leader=top)
    top.add_named_cutter(top_cutter, "cutter")

    
    front = rotate(90, axis=(1, 0, 0))(top)

    front = align(front, top, Alignment.CENTER)
    front = align(front, top, Alignment.TOP)
    front = align(front, top, Alignment.FRONT)
    front = front.prefixed_copy("front")
    angle = top.fuse(front)

    retval = LeaderFollowersCuttersPart(leader=top.leader)

    retval.add_named_follower(angle.leader, "angle")
    for name, cutter in angle.get_named_cutter_items():
        retval.add_named_cutter(cutter, name)

    return retval


def _create_sprite_mount_hole_guides(*, mount_hole_cutter):
    mount_hole_cutter_bbox = get_bounding_box(mount_hole_cutter)
    mount_hole_cutter_size = get_bounding_box_size(mount_hole_cutter)
    mount_hole_cutter_center = get_bounding_box_center(mount_hole_cutter)

    mount_hole_diameter = mount_hole_cutter_size[0] - NemaSizes.NEMA17.hole_dist_mm
    if mount_hole_diameter <= 0:
        raise ValueError(
            "Sprite extruder mount hole cutter bbox does not match a NEMA17 pattern"
        )

    hole_radius = mount_hole_diameter / 2
    hole_length = mount_hole_cutter_size[1]
    top_hole_center_z = mount_hole_cutter_bbox[1][2] - hole_radius
    hole_centers_x = [
        mount_hole_cutter_bbox[0][0] + hole_radius,
        mount_hole_cutter_bbox[1][0] - hole_radius,
    ]

    hole_guides = []
    for side_name, hole_center_x in zip(["left", "right"], hole_centers_x):
        hole = create_cylinder(hole_radius, hole_length, direction=(0, 1, 0))
        hole = align(hole, mount_hole_cutter, Alignment.CENTER)
        hole = translate(
            hole_center_x - mount_hole_cutter_center[0],
            0,
            top_hole_center_z - mount_hole_cutter_center[2],
        )(hole)
        hole_guides.append((side_name, hole))

    return hole_guides


def _create_sprite_mount_screws(
    *,
    mount_hole_cutter,
    mount_base_plate,
    screw_size,
    screw_length,
):
    cylinder_head_height = MScrew.from_size(screw_size).cylinder_head_height
    screws = []

    for side_name, hole_guide in _create_sprite_mount_hole_guides(
        mount_hole_cutter=mount_hole_cutter,
    ):
        screw = create_cylinder_screw(screw_size, screw_length)
        screw = rotate(-90, axis=(1, 0, 0))(screw)
        screw = align(screw, hole_guide, Alignment.CENTER)
        screw = align(screw, mount_base_plate, Alignment.BACK)
        screw = translate(0, cylinder_head_height, 0)(screw)
        screws.append((side_name, screw))

    return screws


def _create_lower_side_plates(
    *,
    carriage_mount_plate,
    tool_head_mount_side_plate_thickness,
    tool_head_mount_side_plate_depth,
    tool_head_mount_side_plate_height,
    tool_head_mount_carriage_mount_plate_fillet_radius,
):

    side_plates = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        side_plate = create_filleted_box(
            tool_head_mount_side_plate_thickness,
            tool_head_mount_side_plate_depth,
            tool_head_mount_side_plate_height,
            fillet_radius=tool_head_mount_carriage_mount_plate_fillet_radius,
            no_fillets_at=[Alignment.TOP, lr.opposite],
        )
        side_plate = align(side_plate, carriage_mount_plate, Alignment.STACK_BOTTOM)
        side_plate = align(side_plate, carriage_mount_plate, Alignment.FRONT)
        side_plate = align(side_plate, carriage_mount_plate, lr)

        side_plates = side_plates.fuse(side_plate)

    return side_plates


def _create_upper_side_plates(
    *,
    carriage_mount_plate,
    x_axis_belt_carriage,
    tool_head_mount_base_plate_height,
    tool_head_mount_carriage_mount_plate_thickness,
    tool_head_mount_side_plate_thickness,
    tool_head_mount_side_plate_depth,
    tool_head_mount_carriage_mount_plate_fillet_radius,
):
    carriage_mount_plate_size = get_bounding_box_size(carriage_mount_plate)
    carriage_mount_plate_center = get_bounding_box_center(carriage_mount_plate)
    carriage_mount_plate_top_z = (
        carriage_mount_plate_center[2] + carriage_mount_plate_size[2] / 2
    )

    x_axis_belt_carriage_size = get_bounding_box_size(x_axis_belt_carriage)
    x_axis_belt_carriage_center = get_bounding_box_center(x_axis_belt_carriage)
    belt_carriage_top_z = (
        x_axis_belt_carriage_center[2] + x_axis_belt_carriage_size[2] / 2
    )

    upper_side_plate_height = max(
        belt_carriage_top_z - carriage_mount_plate_top_z + 2,
        tool_head_mount_base_plate_height
        + tool_head_mount_carriage_mount_plate_thickness,
    )

    upper_side_plates = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        side_plate = create_filleted_box(
            tool_head_mount_side_plate_thickness,
            tool_head_mount_side_plate_depth,
            upper_side_plate_height,
            fillet_radius=tool_head_mount_carriage_mount_plate_fillet_radius,
            no_fillets_at=[Alignment.BOTTOM, lr.opposite],
        )
        side_plate = align(side_plate, carriage_mount_plate, Alignment.STACK_TOP)
        side_plate = align(side_plate, carriage_mount_plate, Alignment.FRONT)
        side_plate = align(side_plate, carriage_mount_plate, lr)
        upper_side_plates = upper_side_plates.fuse(side_plate)

    return upper_side_plates


def create_tool_head_mount_assembly(
    *,
    carriage,
    sprite_extruder,
    x_axis_belt_carriage,
    extruder_mount_screw_size,
    tool_head_mount_base_plate_height,
    tool_head_mount_base_plate_thickness,
    tool_head_mount_belt_clamp_base_thickness,
    tool_head_mount_belt_clamp_length,
    tool_head_mount_belt_clamp_thickness,
    tool_head_mount_belt_clamp_y_offset,
    tool_head_mount_belt_deflector_belt_clearance,
    tool_head_mount_belt_deflector_cage_thickness,
    tool_head_mount_belt_deflector_into_profile_distance,
    tool_head_mount_belt_deflector_thickness,
    tool_head_mount_belt_path_cutter_clearance,
    tool_head_mount_carriage_mount_plate_fillet_radius,
    tool_head_mount_carriage_mount_plate_thickness,
    tool_head_mount_carriage_mount_plate_width,
    tool_head_mount_clamp_base_cutter_clearance,
    tool_head_mount_extruder_cutout_carriage_gap,
    tool_head_mount_extruder_cutout_fillet_radius,
    tool_head_mount_extruder_cutout_width,
    tool_head_mount_plate_carriage_clearance,
    tool_head_mount_side_plate_depth,
    tool_head_mount_side_plate_height,
    tool_head_mount_side_plate_thickness,
    tool_head_mount_side_stiffener_thickness,
    tool_head_mount_sprite_mount_screw_length,
    tool_head_mount_tool_head_base_plate_clearance,
    tool_head_mount_tool_head_x_offset,
    tool_head_mount_tool_head_z_offset,
    tool_head_mount_x_offset,
    tool_head_mount_y_extension,
    drive_position,
    tool_head_mount_top_box_wall,
    tool_head_mount_top_box_height,
    tool_head_mount_carriage_mount_l_profile_thickness,
    tool_head_mount_carriage_mount_l_profile_outer_size,
    BIG_THING,
):
    """Create a single tool head mount assembly."""

    big_thing = BIG_THING
    normalized_drive_position = str(drive_position).strip().lower()
    if normalized_drive_position == "bottom":
        drive_position = Alignment.BOTTOM
    elif normalized_drive_position == "top":
        drive_position = Alignment.TOP
    else:
        raise ValueError(f"Unsupported drive_position '{drive_position}'")

    carriage_size = get_bounding_box_size(carriage)

    base_plate_width = (
        tool_head_mount_carriage_mount_plate_width
        - 2 * tool_head_mount_side_plate_thickness
    )

    carriage_mount_plate = create_filleted_box(
        tool_head_mount_carriage_mount_plate_width,
        carriage_size[1] + tool_head_mount_y_extension,
        tool_head_mount_carriage_mount_plate_thickness,
        fillet_radius=tool_head_mount_carriage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM],
    )
    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.CENTER)
    carriage_mount_plate = align(
        carriage_mount_plate,
        carriage,
        Alignment.STACK_TOP,
    )
    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.BACK)
    carriage_mount_plate = align(
        carriage_mount_plate,
        carriage,
        Alignment.RIGHT if drive_position == Alignment.BOTTOM else Alignment.LEFT,
    )

    carriage_mount_plate = carriage.use_as_cutter_on(carriage_mount_plate)

    mount_base_plate = create_box(
        base_plate_width,
        tool_head_mount_base_plate_thickness,
        tool_head_mount_base_plate_height,
    )
    mount_base_plate = align(mount_base_plate, carriage_mount_plate, Alignment.CENTER)
    mount_base_plate = align(
        mount_base_plate,
        carriage_mount_plate,
        Alignment.STACK_BOTTOM,
    )
    mount_base_plate = align(
        mount_base_plate,
        sprite_extruder,
        Alignment.STACK_BACK,
    )

    mount_hole_cutter = sprite_extruder.get_named_cutter("mount_hole_cutter")

    mount_base_plate = mount_base_plate.cut(mount_hole_cutter)
    mount_base_plate = mount_base_plate.cut(sprite_extruder.leader)
    sprite_mount_screws = _create_sprite_mount_screws(
        mount_hole_cutter=mount_hole_cutter,
        mount_base_plate=mount_base_plate,
        screw_size=extruder_mount_screw_size,
        screw_length=tool_head_mount_sprite_mount_screw_length,
    )

    extruder_cutout = create_filleted_box(
        tool_head_mount_extruder_cutout_width,
        big_thing,
        big_thing,
        fillet_radius=tool_head_mount_extruder_cutout_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    extruder_cutout = align(extruder_cutout, carriage_mount_plate, Alignment.CENTER)
    extruder_cutout = align(extruder_cutout, sprite_extruder, Alignment.RIGHT)
    extruder_cutout = align(extruder_cutout, sprite_extruder, Alignment.BACK)

    carriage_mount_plate = carriage_mount_plate.cut(extruder_cutout)

    end_of_extruder_helper = create_box(100, 1, 100)
    end_of_extruder_helper = align(
        end_of_extruder_helper, sprite_extruder, Alignment.CENTER
    )
    end_of_extruder_helper = align(
        end_of_extruder_helper, sprite_extruder, Alignment.STACK_FRONT
    )


    carriage_mount_plate_top = carriage_mount_plate


    tool_head_mount = carriage_mount_plate
    tool_head_mount = tool_head_mount.fuse(mount_base_plate)

    for name, part in x_axis_belt_carriage.get_named_cutter_items():
        mount_box = create_box(8, 8, 15)
        mount_box = align(mount_box, part, Alignment.CENTER)
        mount_box = align(
            mount_box,
            x_axis_belt_carriage,
            (
                Alignment.STACK_BOTTOM
                if drive_position == Alignment.TOP
                else Alignment.STACK_TOP
            ),
        )
        mount_box = mount_box.cut(sprite_extruder.leader)
        tool_head_mount = tool_head_mount.fuse(mount_box)

    tool_head_mount = x_axis_belt_carriage.use_as_cutter_on(tool_head_mount)


    x_axis_belt_carriage_cutter = materialize_bounding_box(
        x_axis_belt_carriage, x_enlargement=5, y_enlargement=0.2, z_enlargement=0.2
    )
    tool_head_mount = tool_head_mount.cut(x_axis_belt_carriage_cutter)

    for name, cutter in sprite_extruder.get_named_cutter_items():
        if "mount_hole" in name:
            tool_head_mount = tool_head_mount.cut(cutter)

    tool_head_mount = tool_head_mount.fuse(carriage_mount_plate_top)



    l_profile = create_hardware_store_angle()

    l_profile = align(l_profile, carriage, Alignment.CENTER)
    l_profile = align(l_profile, carriage, Alignment.STACK_TOP)
    l_profile = align(l_profile, sprite_extruder, Alignment.STACK_BACK)


    angle_full = l_profile.get_named_follower("angle")

    tool_head_mount = l_profile.use_as_cutter_on(tool_head_mount)

    tool_head_mount = LeaderFollowersCuttersPart(leader=tool_head_mount)
    tool_head_mount.add_named_cutter(mount_hole_cutter, "mount_hole_cutter")

    for side_name, screw in sprite_mount_screws:
        tool_head_mount.add_named_non_production_part(
            screw,
            f"sprite_mount_screw_{side_name}",
        )


    tool_head_mount.add_named_non_production_part(angle_full, "l_profile")

    return tool_head_mount
