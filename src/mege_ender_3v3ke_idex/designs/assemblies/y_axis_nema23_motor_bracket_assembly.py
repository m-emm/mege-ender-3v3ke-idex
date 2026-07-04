"""NEMA23 Y-axis motor with purchased metal bracket reference assembly."""

from mege_ender_3v3ke_idex.designs.nema_motors import NemaSizes, create_nema_composite
from shellforgepy.simple import *


def _create_vertical_slot_cutter(slot_width, slot_length, depth):
    straight_length = max(0.0, slot_length - slot_width)
    if straight_length <= 0:
        return create_cylinder(slot_width / 2, depth, direction=(0, 1, 0))

    slot = create_box(
        slot_width,
        depth,
        straight_length,
        origin=(-slot_width / 2, -depth / 2, -straight_length / 2),
    )

    for z_offset in (-straight_length / 2, straight_length / 2):
        cap = create_cylinder(slot_width / 2, depth, direction=(0, 1, 0))
        cap = align(cap, slot, Alignment.CENTER)
        cap = translate(0, 0, z_offset)(cap)
        slot = slot.fuse(cap)

    return slot


def _create_frame_mount_slots(
    *,
    frame_face,
    slot_width,
    slot_length,
    slot_center_spacing,
    BIG_THING,
):
    slots = PartCollector()
    for side in (Alignment.LEFT, Alignment.RIGHT):
        slot = _create_vertical_slot_cutter(slot_width, slot_length, BIG_THING)
        slot = align(slot, frame_face, Alignment.CENTER)
        slot = translate(side.sign * slot_center_spacing / 2, 0, 0)(slot)
        slots = slots.fuse(slot)

    return slots


def _create_motor_mount_screws(
    *,
    motor_face_plate,
    hole_spacing,
    screw_size,
    screw_length,
):
    screw_items = []
    offset = hole_spacing / 2

    for x_side in (Alignment.LEFT, Alignment.RIGHT):
        for y_side in (Alignment.FRONT, Alignment.BACK):
            screw = create_cylinder_screw(screw_size, screw_length)
            screw = align(screw, motor_face_plate, Alignment.CENTER, axes=[2])
            screw = align(screw, motor_face_plate, Alignment.TOP)
            screw = translate(
                x_side.sign * offset,
                y_side.sign * offset,
                MScrew.from_size(screw_size).cylinder_head_height,
            )(screw)
            screw_items.append(
                (
                    f"motor_mount_screw_{x_side.name.lower()}_{y_side.name.lower()}",
                    screw,
                )
            )

    return screw_items


def _create_frame_mount_screws(
    *,
    frame_face,
    slot_center_spacing,
    screw_size,
    screw_length,
):
    screw_items = []

    for side in (Alignment.LEFT, Alignment.RIGHT):
        screw = create_cylinder_screw(screw_size, screw_length)
        screw = rotate(90, axis=(1, 0, 0))(screw)
        screw = align(screw, frame_face, Alignment.CENTER)
        screw = translate(side.sign * slot_center_spacing / 2, 0, 0)(screw)
        screw = align(screw, frame_face, Alignment.BACK)
        screw = translate(
            0,
            MScrew.from_size(screw_size).cylinder_head_height,
            0,
        )(screw)
        screw_items.append((f"frame_mount_screw_{side.name.lower()}", screw))

    return screw_items


def create_y_axis_nema23_motor_bracket_assembly(
    *,
    y_axis_nema23_motor_body_length,
    y_axis_nema23_motor_axle_diameter,
    y_axis_nema23_motor_axle_length,
    y_axis_nema23_motor_mount_screw_size,
    y_axis_nema23_motor_mount_screw_length,
    y_axis_nema23_bracket_width,
    y_axis_nema23_bracket_motor_face_depth,
    y_axis_nema23_bracket_frame_face_height,
    y_axis_nema23_bracket_thickness,
    y_axis_nema23_bracket_fillet_radius,
    y_axis_nema23_bracket_mount_slot_width,
    y_axis_nema23_bracket_mount_slot_length,
    y_axis_nema23_bracket_mount_slot_center_spacing,
    y_axis_nema23_bracket_mount_screw_size,
    y_axis_nema23_bracket_mount_screw_length,
    BIG_THING=500,
):
    """Create a NEMA23 motor mounted to the purchased metal angle bracket."""

    motor = create_nema_composite(
        nema=NemaSizes.NEMA23,
        axle_diameter=y_axis_nema23_motor_axle_diameter,
        axle_length=y_axis_nema23_motor_axle_length,
        body_thickness=y_axis_nema23_motor_body_length,
        mount_hole_back_extension=y_axis_nema23_bracket_thickness + 2.0,
        mount_hole_clearance=0.25,
        axle_clearance=0.25,
        boss_clearance=0.3,
        boss_clearance_z=y_axis_nema23_bracket_thickness + 1.0,
    )

    motor_body = motor.get_follower_part_by_name("body")
    motor_face_plate = create_filleted_box(
        y_axis_nema23_bracket_width,
        y_axis_nema23_bracket_motor_face_depth,
        y_axis_nema23_bracket_thickness,
        y_axis_nema23_bracket_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.BACK],
    )
    motor_face_plate = align(
        motor_face_plate, motor_body, Alignment.CENTER, axes=[0, 1]
    )
    motor_face_plate = align(motor_face_plate, motor_body, Alignment.STACK_TOP)
    motor_face_plate = motor.use_as_cutter_on(motor_face_plate)

    frame_face = create_filleted_box(
        y_axis_nema23_bracket_width,
        y_axis_nema23_bracket_thickness,
        y_axis_nema23_bracket_frame_face_height,
        y_axis_nema23_bracket_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BOTTOM],
    )
    frame_face = align(frame_face, motor_face_plate, Alignment.CENTER, axes=[0])
    frame_face = align(frame_face, motor_face_plate, Alignment.STACK_BACK)
    frame_face = align(frame_face, motor_face_plate, Alignment.TOP)

    frame_mount_slots = _create_frame_mount_slots(
        frame_face=frame_face,
        slot_width=y_axis_nema23_bracket_mount_slot_width,
        slot_length=y_axis_nema23_bracket_mount_slot_length,
        slot_center_spacing=y_axis_nema23_bracket_mount_slot_center_spacing,
        BIG_THING=BIG_THING,
    )
    frame_face = frame_face.cut(frame_mount_slots)

    bracket = motor_face_plate.fuse(frame_face)

    screw_items = _create_motor_mount_screws(
        motor_face_plate=motor_face_plate,
        hole_spacing=NemaSizes.NEMA23.hole_dist_mm,
        screw_size=y_axis_nema23_motor_mount_screw_size,
        screw_length=y_axis_nema23_motor_mount_screw_length,
    )
    screw_items.extend(
        _create_frame_mount_screws(
            frame_face=frame_face,
            slot_center_spacing=y_axis_nema23_bracket_mount_slot_center_spacing,
            screw_size=y_axis_nema23_bracket_mount_screw_size,
            screw_length=y_axis_nema23_bracket_mount_screw_length,
        )
    )

    return LeaderFollowersCuttersPart(
        leader=bracket,
        followers=[
            motor.leader,
            motor.get_follower_part_by_name("axle"),
        ],
        follower_names=[
            "motor_body",
            "axle",
        ],
        cutters=[frame_mount_slots],
        cutter_names=["frame_mount_slots"],
        non_production_parts=[part for _, part in screw_items],
        non_production_names=[name for name, _ in screw_items],
    )
