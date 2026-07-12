"""OPB991T11Z wired optical interrupter reference assembly."""

from shellforgepy.simple import *


def create_opb991t11z_sensor_assembly(
    *,
    opb991t11z_body_width,
    opb991t11z_body_depth,
    opb991t11z_body_height,
    opb991t11z_base_height,
    opb991t11z_slot_width,
    opb991t11z_slot_depth,
    opb991t11z_aperture_width,
    opb991t11z_optical_center_z,
    opb991t11z_mount_tab_width,
    opb991t11z_mount_hole_diameter,
    opb991t11z_mount_hole_pitch,
    opb991t11z_wire_exit_width,
    opb991t11z_wire_exit_depth,
    opb991t11z_wire_diameter,
    opb991t11z_wire_length,
):
    """Create a simplified datasheet-sized OPB991T11Z sensor model."""

    base = create_box(
        opb991t11z_body_width,
        opb991t11z_body_depth,
        opb991t11z_base_height,
    )

    tab = create_box(
        opb991t11z_mount_tab_width,
        opb991t11z_body_depth,
        opb991t11z_base_height,
    )
    tab = align(tab, base, Alignment.CENTER)

    tower_width = (opb991t11z_body_width - opb991t11z_slot_width) / 2
    tower_height = opb991t11z_body_height - opb991t11z_base_height

    left_tower = create_box(tower_width, opb991t11z_body_depth, tower_height)
    left_tower = align(left_tower, base, Alignment.LEFT)
    left_tower = align(left_tower, base, Alignment.CENTER, axes=[1])
    left_tower = align(left_tower, base, Alignment.STACK_TOP)

    right_tower = create_box(tower_width, opb991t11z_body_depth, tower_height)
    right_tower = align(right_tower, base, Alignment.RIGHT)
    right_tower = align(right_tower, base, Alignment.CENTER, axes=[1])
    right_tower = align(right_tower, base, Alignment.STACK_TOP)

    leader = tab.fuse(base).fuse(left_tower).fuse(right_tower)

    mounting_holes = PartCollector()
    for index, x_offset in enumerate(
        [-opb991t11z_mount_hole_pitch / 2, opb991t11z_mount_hole_pitch / 2]
    ):
        mounting_hole = create_cylinder(
            opb991t11z_mount_hole_diameter / 2,
            opb991t11z_base_height + 2,
        )
        mounting_hole = align(mounting_hole, tab, Alignment.CENTER, axes=[1])
        mounting_hole = align(mounting_hole, tab, Alignment.CENTER, axes=[2])
        mounting_hole = translate(x_offset, 0, 0)(mounting_hole)
        leader = leader.cut(mounting_hole)
        mounting_holes = mounting_holes.fuse(mounting_hole)
        if index == 0:
            mounting_hole_1 = mounting_hole
        else:
            mounting_hole_2 = mounting_hole

    slot_keepout = create_box(
        opb991t11z_slot_width,
        opb991t11z_body_depth + 2,
        opb991t11z_slot_depth,
    )
    slot_keepout = align(slot_keepout, leader, Alignment.CENTER, axes=[0, 1])
    slot_keepout = align(slot_keepout, leader, Alignment.TOP)

    optical_center = create_cylinder(
        opb991t11z_aperture_width / 2,
        opb991t11z_body_depth + 2,
        direction=(0, 1, 0),
    )
    optical_center = align(optical_center, leader, Alignment.CENTER, axes=[0, 1])
    optical_center = align(optical_center, leader, Alignment.BOTTOM)
    optical_center = translate(0, 0, opb991t11z_optical_center_z)(optical_center)

    wire_exit = create_box(
        opb991t11z_wire_exit_width,
        opb991t11z_wire_exit_depth,
        opb991t11z_base_height,
    )
    wire_exit = align(wire_exit, leader, Alignment.CENTER, axes=[0])
    wire_exit = align(wire_exit, leader, Alignment.STACK_FRONT)
    wire_exit = align(wire_exit, leader, Alignment.BOTTOM)

    wire_bundle = PartCollector()
    wire_pitch = opb991t11z_wire_diameter * 1.6
    for wire_index in range(5):
        wire = create_cylinder(
            opb991t11z_wire_diameter / 2,
            opb991t11z_wire_length,
            direction=(0, 0, 1),
        )
        wire = align(wire, wire_exit, Alignment.CENTER, axes=[1])
        wire = align(wire, wire_exit, Alignment.STACK_BOTTOM)
        wire = translate(
            (wire_index - 2) * wire_pitch,
            -opb991t11z_wire_exit_depth / 2,
            0,
        )(wire)
        wire_bundle = wire_bundle.fuse(wire)

    sensor = LeaderFollowersCuttersPart(leader=leader)
    sensor.add_named_follower(leader, "body")
    sensor.add_named_follower(base, "base")
    sensor.add_named_follower(left_tower, "emitter_tower")
    sensor.add_named_follower(right_tower, "sensor_tower")
    sensor.add_named_non_production_part(slot_keepout, "slot_keepout")
    sensor.add_named_non_production_part(optical_center, "optical_center")
    sensor.add_named_non_production_part(wire_exit, "wire_exit")
    sensor.add_named_non_production_part(wire_bundle, "wire_bundle")
    sensor.add_named_cutter(mounting_holes, "mounting_holes")
    sensor.add_named_cutter(mounting_hole_1, "mounting_hole_1")
    sensor.add_named_cutter(mounting_hole_2, "mounting_hole_2")

    return sensor
