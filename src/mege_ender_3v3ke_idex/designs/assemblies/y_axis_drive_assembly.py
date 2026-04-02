"""Declarative y-axis drive assembly."""

import logging
import math
from dataclasses import dataclass

from mege_ender_3v3ke_idex.designs.gt2belt import (
    create_gt2_pulley,
    create_gt2belt,
    gt2_pitch,
    gt2_teeth_thickness,
    gt2_thickness,
    gt2_width,
)
from mege_ender_3v3ke_idex.designs.idler_cage import create_idler_cage
from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

Y_AXIS_DRIVE_LEADER_NAME = "motor_mount_plate"

_GT2_IDLER_RUNNING_SURFACE_DIAMETER_FACTOR = (
    1.061032953945969  # TODO: Remove this magic number.
)


@dataclass(frozen=True)
class _DriveConfig:
    x_axis_motor_axle_length: float
    motor_mount_axle_clearance: float
    motor_mount_boss_clearance: float
    motor_mount_boss_clearance_z: float
    motor_mount_plate_thickness: float
    motor_mount_plate_fillet_radius: float
    y_axis_drive_profile_mount_plate_width: float
    y_axis_drive_profile_mount_plate_height: float
    y_axis_drive_profile_mount_plate_thickness: float
    y_axis_drive_profile_mount_plate_fillet_radius: float
    y_axis_motor_holder_side_wall_thickness: float
    y_axis_motor_holder_side_wall_height: float
    y_axis_motor_holder_side_wall_depth: float
    y_axis_drive_mount_screw_inset: float
    y_axis_drive_mount_screw_size: str
    y_axis_drive_mount_screw_length: float
    y_axis_drive_motor_plate_width: float
    y_axis_drive_motor_plate_depth: float
    y_axis_drive_idler_plate_width: float
    y_axis_drive_motor_pulley_teeth: int
    y_axis_drive_idler_teeth: int
    y_axis_drive_belt_clear_span_extra: float
    y_axis_drive_idler_housing_side_wall: float
    y_axis_drive_idler_housing_front_wall: float
    y_axis_drive_idler_housing_top_wall: float
    y_axis_drive_idler_cage_top_clearance: float
    y_axis_drive_idler_cage_front_clearance: float
    y_axis_drive_idler_cage_height: float
    y_axis_drive_tensioner_screw_holder_thickness: float
    y_axis_drive_tensioner_screw_holder_depth: float
    y_axis_drive_tensioner_screw_holder_width: float
    y_axis_drive_idler_cage_wall: float
    y_axis_drive_idler_cage_overlength: float
    y_axis_drive_idler_clearance: float
    y_axis_drive_idler_cage_back_wall: float
    y_axis_drive_idler_tensioner_screw_length: float
    y_axis_drive_idler_tensioner_screw_nut_wall: float
    y_axis_drive_idler_tensioner_guide_clearance: float
    y_axis_drive_idler_axle_screw_length: float
    y_axis_drive_tensioner_screw_size: str
    y_axis_drive_use_toothed_belt_visuals: bool
    y_axis_drive_tensioner_screw_z_offset: float
    endcap_tensioner_screw_size: str
    endcap_belt_clearance: float
    big_thing: float

    @property
    def y_axis_drive_tensioner_screw_holder_side_width(self) -> float:
        return self.y_axis_drive_tensioner_screw_holder_depth

    @property
    def y_axis_drive_clamped_run_side(self) -> Alignment:
        return Alignment.RIGHT

    @property
    def y_axis_drive_clamped_run_contact_alignment(self) -> Alignment:
        return (
            Alignment.STACK_LEFT
            if self.y_axis_drive_clamped_run_side == Alignment.RIGHT
            else Alignment.STACK_RIGHT
        )

    @property
    def y_axis_drive_return_run_alignment(self) -> Alignment:
        return (
            Alignment.STACK_LEFT
            if self.y_axis_drive_clamped_run_side == Alignment.RIGHT
            else Alignment.STACK_RIGHT
        )


def _align_part_to_frame_profile_inner_face(part, frame_cross_profile, front_back):
    if front_back == Alignment.BACK:
        return align(part, frame_cross_profile, Alignment.STACK_FRONT)
    return align(part, frame_cross_profile, Alignment.STACK_BACK)


def _create_gt2_pulley_running_surface_reference(num_teeth, belt_width=gt2_width):
    pulley_running_surface_diameter = (
        (num_teeth * gt2_pitch) / math.pi - gt2_thickness + gt2_teeth_thickness
    )
    return create_cylinder(pulley_running_surface_diameter / 2, belt_width)


def _create_gt2_idler_running_surface_reference(num_teeth, belt_width=gt2_width):
    idler_running_surface_diameter = (
        (num_teeth * gt2_pitch) / math.pi / _GT2_IDLER_RUNNING_SURFACE_DIAMETER_FACTOR
    )
    return create_cylinder(idler_running_surface_diameter / 2, belt_width)


def _align_part_from_belt_contact_surface(part, contact_surface, belt_reference, cfg):
    part = align_translation(
        contact_surface,
        belt_reference,
        Alignment.CENTER,
        axes=[2],
    )(part)
    return align_translation(
        contact_surface,
        belt_reference,
        cfg.y_axis_drive_clamped_run_contact_alignment,
    )(part)


def _create_y_axis_belt_visual(num_teeth, cfg):
    if cfg.y_axis_drive_use_toothed_belt_visuals:
        return create_gt2belt(num_teeth=num_teeth)

    belt_length = num_teeth * gt2_pitch
    return create_box(
        belt_length,
        gt2_thickness,
        gt2_width,
        origin=(-belt_length / 2, -gt2_thickness / 2, -gt2_width / 2),
    )


def _create_y_axis_profile_mount_plate(cfg):
    plate = create_filleted_box(
        cfg.y_axis_drive_profile_mount_plate_width,
        cfg.y_axis_drive_profile_mount_plate_thickness,
        cfg.y_axis_drive_profile_mount_plate_height,
        cfg.y_axis_drive_profile_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK, Alignment.TOP],
    )

    hole_drill_diameter = MScrew.from_size(
        cfg.y_axis_drive_mount_screw_size
    ).clearance_hole_loose

    screws = []
    screw_names = []
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        hole = create_cylinder(
            hole_drill_diameter / 2,
            cfg.big_thing,
            direction=(0, 1, 0),
        )
        hole = align(hole, plate, Alignment.CENTER)
        hole = align(hole, plate, lr.edge_alignment)
        hole = translate(-lr.sign * cfg.y_axis_drive_mount_screw_inset, 0, 0)(hole)
        plate = plate.cut(hole)

        screw = create_cylinder_screw(
            cfg.y_axis_drive_mount_screw_size,
            cfg.y_axis_drive_mount_screw_length,
        )
        screw = rotate(90, axis=(1, 0, 0))(screw)
        screw = align(screw, hole, Alignment.CENTER)
        screw = align(screw, plate, Alignment.FRONT)
        screw = translate(
            0,
            -MScrew.from_size(cfg.y_axis_drive_mount_screw_size).cylinder_head_height,
            0,
        )(screw)

        screws.append(screw)
        screw_names.append(f"profile_mount_screw_{lr.name.lower()}")

    return LeaderFollowersCuttersPart(
        leader=plate,
        non_production_parts=screws,
        non_production_names=screw_names,
    )


def _create_y_axis_profile_mount_hole_drills(cfg, num_holes=2, screw_inset=None):
    if screw_inset is None:
        screw_inset = cfg.y_axis_drive_mount_screw_inset

    hole_drill_diameter = MScrew.from_size(
        cfg.y_axis_drive_mount_screw_size
    ).clearance_hole_loose

    hole_drills = PartCollector()
    hole_pitch = (
        (
            cfg.y_axis_drive_profile_mount_plate_width
            - 2 * screw_inset
            - hole_drill_diameter
        )
        / (num_holes - 1)
        if num_holes > 1
        else 0
    )

    for i in range(num_holes):
        hole_drill = create_cylinder(
            hole_drill_diameter / 2,
            cfg.big_thing,
            direction=(0, 1, 0),
        )
        hole_drill = translate(i * hole_pitch, 0, 0)(hole_drill)
        hole_drills = hole_drills.fuse(hole_drill)

    return hole_drills


def _create_y_axis_motor_mount(frame_back_profile, belt_reference, cfg):
    motor = create_nema_composite(
        axle_length=cfg.x_axis_motor_axle_length,
        axle_clearance=cfg.motor_mount_axle_clearance,
        boss_clearance=cfg.motor_mount_boss_clearance,
        boss_clearance_z=cfg.motor_mount_boss_clearance_z,
    )

    motor_mount_plate = create_filleted_box(
        cfg.y_axis_drive_motor_plate_width,
        cfg.y_axis_drive_motor_plate_depth,
        cfg.motor_mount_plate_thickness,
        cfg.motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.BACK],
    )

    pulley = create_gt2_pulley(
        num_teeth=cfg.y_axis_drive_motor_pulley_teeth,
        belt_width=gt2_width,
    )
    pulley = align(pulley, motor_mount_plate, Alignment.CENTER, axes=[1])
    pulley_running_surface = _create_gt2_pulley_running_surface_reference(
        cfg.y_axis_drive_motor_pulley_teeth
    )
    pulley_running_surface = align(pulley_running_surface, pulley, Alignment.CENTER)
    pulley = _align_part_from_belt_contact_surface(
        pulley,
        pulley_running_surface,
        belt_reference,
        cfg,
    )

    motor = motor.aligned_from_follower("axle", pulley, Alignment.CENTER)

    motor_body = motor.get_follower_part_by_name("body")
    motor_mount_plate = align(motor_mount_plate, pulley, Alignment.CENTER, axes=[0])
    motor_mount_plate = align(motor_mount_plate, motor_body, Alignment.STACK_TOP)

    side_walls = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        side_wall = create_box(
            cfg.y_axis_motor_holder_side_wall_thickness,
            cfg.y_axis_motor_holder_side_wall_depth,
            cfg.y_axis_motor_holder_side_wall_height,
        )
        side_wall = align(side_wall, motor_mount_plate, Alignment.CENTER)
        side_wall = align(side_wall, motor_mount_plate, Alignment.BACK)
        side_wall = align(side_wall, motor_mount_plate, lr)
        side_wall = align(side_wall, motor_mount_plate, Alignment.STACK_BOTTOM)
        side_walls = side_walls.fuse(side_wall)

    motor_mount_plate = motor_mount_plate.fuse(side_walls)
    motor_mount_plate = motor.use_as_cutter_on(motor_mount_plate)

    profile_mount_plate = _create_y_axis_profile_mount_plate(cfg).prefixed_copy("motor")
    profile_mount_plate = align(
        profile_mount_plate,
        motor_mount_plate,
        Alignment.CENTER,
        axes=[0],
    )
    profile_mount_plate = align(
        profile_mount_plate, motor_mount_plate, Alignment.STACK_BACK
    )
    profile_mount_plate = align(
        profile_mount_plate,
        frame_back_profile,
        Alignment.CENTER,
        axes=[2],
    )

    motor_mount_plate = motor_mount_plate.fuse(profile_mount_plate.leader)

    motor_visual_items = [
        (f"motor_{name}", part)
        for name, part in motor.get_named_follower_items()
        if name != "coupler"
    ]
    mount_visual_items = list(profile_mount_plate.get_named_non_production_part_items())
    visual_items = motor_visual_items + mount_visual_items + [("motor_pulley", pulley)]

    retval = LeaderFollowersCuttersPart(
        leader=motor_mount_plate,
        non_production_parts=[part for _, part in visual_items],
        non_production_names=[name for name, _ in visual_items],
    )
    retval = _align_part_to_frame_profile_inner_face(
        retval,
        frame_back_profile,
        Alignment.BACK,
    )
    return retval


def _create_y_axis_idler_cage(cfg):
    idler_cage = create_idler_cage(
        cage_back_wall=cfg.y_axis_drive_idler_cage_back_wall,
        cage_front_wall_thickness=cfg.y_axis_drive_idler_cage_wall,
        cage_wall=cfg.y_axis_drive_idler_cage_wall,
        cage_height=cfg.y_axis_drive_idler_cage_height,
        cage_overlength=cfg.y_axis_drive_idler_cage_overlength,
        idler_tooth_count=cfg.y_axis_drive_idler_teeth,
        idler_clearance=cfg.y_axis_drive_idler_clearance,
        with_tensioner=False,
        tensioner_screw_size=cfg.endcap_tensioner_screw_size,
        axle_screw_length=cfg.y_axis_drive_idler_axle_screw_length,
        belt_clearance=cfg.endcap_belt_clearance,
        cage_width_override=cfg.y_axis_drive_idler_plate_width,
        tensioner_screw_z_offset=cfg.y_axis_drive_tensioner_screw_z_offset,
    )
    return rotate(90)(idler_cage)


def _create_y_axis_idler_mount(frame_front_profile, belt_reference, cfg):
    idler_cage = _create_y_axis_idler_cage(cfg)

    idler_cage_raw_size = get_bounding_box_size(idler_cage)

    front_tensioner_screw_holder = create_box(
        cfg.y_axis_drive_tensioner_screw_holder_width,
        cfg.y_axis_drive_tensioner_screw_holder_depth,
        cfg.y_axis_drive_tensioner_screw_holder_thickness,
    )
    front_tensioner_screw_holder = align(
        front_tensioner_screw_holder,
        idler_cage,
        Alignment.CENTER,
    )
    front_tensioner_screw_holder = align(
        front_tensioner_screw_holder,
        idler_cage,
        Alignment.BACK,
    )
    front_tensioner_screw_holder = align(
        front_tensioner_screw_holder,
        idler_cage,
        Alignment.STACK_BOTTOM,
    )

    tensioner_screw_holder_sides = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        front_tensioner_screw_holder_side = create_box(
            cfg.y_axis_drive_tensioner_screw_holder_side_width,
            idler_cage_raw_size[1],
            cfg.y_axis_drive_tensioner_screw_holder_thickness,
        )
        front_tensioner_screw_holder_side = align(
            front_tensioner_screw_holder_side,
            front_tensioner_screw_holder,
            Alignment.CENTER,
        )
        front_tensioner_screw_holder_side = align(
            front_tensioner_screw_holder_side,
            front_tensioner_screw_holder,
            Alignment.BACK,
        )
        front_tensioner_screw_holder_side = align(
            front_tensioner_screw_holder_side,
            front_tensioner_screw_holder,
            lr,
        )
        tensioner_screw_holder_sides = tensioner_screw_holder_sides.fuse(
            front_tensioner_screw_holder_side
        )

    front_tensioner_screw_holder = front_tensioner_screw_holder.fuse(
        tensioner_screw_holder_sides
    )

    tensioner_screw = create_cylinder_screw(
        cfg.y_axis_drive_tensioner_screw_size,
        cfg.y_axis_drive_idler_tensioner_screw_length,
    )
    tensioner_screw = rotate(-90, axis=(1, 0, 0))(tensioner_screw)
    tensioner_screw = align(
        tensioner_screw,
        front_tensioner_screw_holder,
        Alignment.CENTER,
    )
    tensioner_screw = align(
        tensioner_screw,
        front_tensioner_screw_holder,
        Alignment.BACK,
    )
    tensioner_screw = translate(
        0,
        MScrew.from_size(cfg.y_axis_drive_tensioner_screw_size).cylinder_head_height,
        0,
    )(tensioner_screw)

    tensioner_screw_hole_drill = create_cylinder(
        MScrew.from_size(cfg.y_axis_drive_tensioner_screw_size).clearance_hole_loose
        / 2,
        cfg.big_thing,
        direction=(0, 1, 0),
    )
    tensioner_screw_hole_drill = align(
        tensioner_screw_hole_drill,
        tensioner_screw,
        Alignment.CENTER,
    )
    front_tensioner_screw_holder = front_tensioner_screw_holder.cut(
        tensioner_screw_hole_drill
    )

    idler_cage = idler_cage.fuse(front_tensioner_screw_holder)
    idler_cage.add_named_non_production_part(tensioner_screw, "idler_tensioner_screw")

    idler_cage_size = get_bounding_box_size(idler_cage)

    outer_box = create_box(
        idler_cage_size[0] + 2 * cfg.y_axis_drive_idler_housing_side_wall,
        idler_cage_size[1] + cfg.y_axis_drive_idler_housing_front_wall,
        cfg.y_axis_drive_profile_mount_plate_height,
    )

    front_wall_ref = create_box(
        get_bounding_box_size(outer_box)[0],
        cfg.y_axis_drive_idler_housing_front_wall,
        get_bounding_box_size(outer_box)[2],
    )
    front_wall_ref = align(front_wall_ref, outer_box, Alignment.CENTER, axes=[0, 2])
    front_wall_ref = align(front_wall_ref, outer_box, Alignment.FRONT)

    top_wall_ref = create_box(
        get_bounding_box_size(outer_box)[0],
        get_bounding_box_size(outer_box)[1],
        cfg.y_axis_drive_idler_housing_top_wall,
    )
    top_wall_ref = align(top_wall_ref, outer_box, Alignment.CENTER, axes=[0, 1])
    top_wall_ref = align(top_wall_ref, outer_box, Alignment.TOP)

    idler_cage = align(idler_cage, outer_box, Alignment.CENTER, axes=[0])
    idler_cage = align(
        idler_cage,
        front_wall_ref,
        Alignment.STACK_BACK,
        stack_gap=cfg.y_axis_drive_idler_cage_front_clearance,
    )
    idler_cage = align(
        idler_cage,
        top_wall_ref,
        Alignment.STACK_BOTTOM,
        stack_gap=cfg.y_axis_drive_idler_cage_top_clearance,
    )

    inner_cutter = create_box(
        idler_cage_size[0] + 2 * cfg.y_axis_drive_idler_clearance,
        cfg.big_thing,
        idler_cage_size[2] + 2 * cfg.y_axis_drive_idler_clearance,
    )
    inner_cutter = align(inner_cutter, idler_cage, Alignment.CENTER, axes=[0, 2])
    inner_cutter = align(inner_cutter, front_wall_ref, Alignment.STACK_BACK)
    outer_box = outer_box.cut(inner_cutter)

    tensioner_screw = idler_cage.get_non_production_part_by_name(
        "idler_tensioner_screw"
    )

    tensioner_guide_width = (
        cfg.y_axis_drive_tensioner_screw_holder_width
        - 2 * cfg.y_axis_drive_tensioner_screw_holder_side_width
        - 2 * cfg.y_axis_drive_idler_tensioner_guide_clearance
    )
    tensioner_guide_thickness = (
        cfg.y_axis_drive_tensioner_screw_holder_thickness
        + cfg.y_axis_drive_idler_clearance
        - cfg.y_axis_drive_idler_tensioner_guide_clearance
    )
    tensioner_guide_depth = (
        idler_cage_size[1]
        - cfg.y_axis_drive_tensioner_screw_holder_depth
        - cfg.y_axis_drive_idler_tensioner_guide_clearance
    )

    tensioner_guide = create_box(
        tensioner_guide_width,
        tensioner_guide_depth,
        tensioner_guide_thickness,
    )
    tensioner_guide = align(tensioner_guide, idler_cage, Alignment.CENTER)
    tensioner_guide = align(tensioner_guide, idler_cage, Alignment.BOTTOM)
    tensioner_guide = align(tensioner_guide, outer_box, Alignment.BACK)
    tensioner_guide = translate(
        0,
        -cfg.y_axis_drive_tensioner_screw_holder_depth
        - cfg.y_axis_drive_idler_tensioner_guide_clearance,
        -cfg.y_axis_drive_idler_clearance,
    )(tensioner_guide)

    outer_box = outer_box.fuse(tensioner_guide)

    hidden_nut_cutter = create_hidden_nut_pocket_cutter(
        cfg.y_axis_drive_tensioner_screw_size,
        bottom_cutter_length=20,
        top_cutter_length=20,
        slack=0.3,
    )
    hidden_nut_cutter = rotate(-90, axis=(1, 0, 0))(hidden_nut_cutter)
    hidden_nut_cutter = rotate(180, axis=(0, 0, 1))(hidden_nut_cutter)
    hidden_nut_cutter = align(hidden_nut_cutter, tensioner_screw, Alignment.CENTER)
    hidden_nut_cutter = align(hidden_nut_cutter, tensioner_guide, Alignment.BACK)
    hidden_nut_cutter = translate(
        0,
        -cfg.y_axis_drive_idler_tensioner_screw_nut_wall,
        0,
    )(hidden_nut_cutter)
    outer_box = hidden_nut_cutter.use_as_cutter_on(outer_box)

    profile_mount_hole_drills = _create_y_axis_profile_mount_hole_drills(cfg)
    profile_mount_hole_drills = align(
        profile_mount_hole_drills,
        outer_box,
        Alignment.CENTER,
    )
    outer_box = outer_box.cut(profile_mount_hole_drills)

    idler_mount = LeaderFollowersCuttersPart(
        leader=outer_box,
        followers=[idler_cage.leader],
        non_production_parts=[
            idler_cage.get_non_production_part_by_name("idler"),
            idler_cage.get_non_production_part_by_name("axle"),
            idler_cage.get_non_production_part_by_name("axle_threaded_inset"),
            idler_cage.get_non_production_part_by_name("idler_tensioner_screw"),
        ],
        follower_names=["idler_tensioner_cage"],
        non_production_names=[
            "idler",
            "idler_axle_screw",
            "idler_axle_threaded_inset",
            "idler_tensioner_screw",
        ],
    )

    idler_running_surface = _create_gt2_idler_running_surface_reference(
        cfg.y_axis_drive_idler_teeth
    )
    idler_running_surface = align(
        idler_running_surface,
        idler_mount.get_non_production_part_by_name("idler"),
        Alignment.CENTER,
    )
    idler_mount = _align_part_from_belt_contact_surface(
        idler_mount,
        idler_running_surface,
        belt_reference,
        cfg,
    )
    idler_mount = _align_part_to_frame_profile_inner_face(
        idler_mount,
        frame_front_profile,
        Alignment.FRONT,
    )

    idler_profile_mount_plate = _create_y_axis_profile_mount_plate(cfg).prefixed_copy(
        "idler"
    )
    idler_profile_center = get_bounding_box_center(idler_cage.leader)
    idler_profile_mount_plate = rotate(180, center=idler_profile_center)(
        idler_profile_mount_plate
    )
    idler_profile_mount_plate = align(
        idler_profile_mount_plate,
        idler_mount,
        Alignment.CENTER,
        axes=[0],
    )
    idler_profile_mount_plate = align(
        idler_profile_mount_plate,
        idler_mount,
        Alignment.FRONT,
    )
    idler_profile_mount_plate = align(
        idler_profile_mount_plate,
        frame_front_profile,
        Alignment.CENTER,
        axes=[2],
    )

    outer_box_cutter = materialize_bounding_box(idler_mount)
    idler_profile_mount_plate = idler_profile_mount_plate.cut(outer_box_cutter)

    return idler_mount.fuse(idler_profile_mount_plate)


def _translate_part_center_to_axis_value(part, axis, value):
    center = get_bounding_box_center(part)
    delta = [0, 0, 0]
    delta[axis] = value - center[axis]
    return translate(*delta)(part)


def _create_y_axis_drive_belt_sections(
    motor_mount,
    idler_mount,
    back_belt_reference,
    cfg,
):
    pulley = motor_mount.get_non_production_part_by_name("motor_pulley")
    idler = idler_mount.get_non_production_part_by_name("idler")

    pulley_center = get_bounding_box_center(pulley)
    idler_center = get_bounding_box_center(idler)
    belt_length = (
        abs(pulley_center[1] - idler_center[1]) + cfg.y_axis_drive_belt_clear_span_extra
    )
    num_teeth = max(1, int(round(belt_length / gt2_pitch)))
    belt_center_y = (pulley_center[1] + idler_center[1]) / 2

    belt_sections = []
    right_belt_reference = back_belt_reference
    pulley_running_surface = _create_gt2_pulley_running_surface_reference(
        cfg.y_axis_drive_motor_pulley_teeth
    )
    pulley_running_surface = align(pulley_running_surface, pulley, Alignment.CENTER)

    for side, rotation_angle in (
        (Alignment.LEFT, 90),
        (Alignment.RIGHT, -90),
    ):
        belt = _create_y_axis_belt_visual(num_teeth, cfg)
        belt = rotate(rotation_angle)(belt)
        belt = _translate_part_center_to_axis_value(belt, 1, belt_center_y)
        belt = align(belt, right_belt_reference, Alignment.CENTER, axes=[2])

        if side == cfg.y_axis_drive_clamped_run_side:
            belt = align(belt, right_belt_reference, Alignment.CENTER, axes=[0])
        else:
            belt = align(
                belt,
                pulley_running_surface,
                cfg.y_axis_drive_return_run_alignment,
            )

        belt_sections.append((f"y_axis_belt_section_{side.name.lower()}", belt))

    return belt_sections


def create_y_axis_drive_assembly(
    *,
    frame_back_profile,
    frame_front_profile,
    back_belt_reference,
    front_belt_reference,
    x_axis_motor_axle_length,
    motor_mount_axle_clearance,
    motor_mount_boss_clearance,
    motor_mount_boss_clearance_z,
    motor_mount_plate_thickness,
    motor_mount_plate_fillet_radius,
    y_axis_drive_profile_mount_plate_width,
    y_axis_drive_profile_mount_plate_height,
    y_axis_drive_profile_mount_plate_thickness,
    y_axis_drive_profile_mount_plate_fillet_radius,
    y_axis_motor_holder_side_wall_thickness,
    y_axis_motor_holder_side_wall_height,
    y_axis_motor_holder_side_wall_depth,
    y_axis_drive_mount_screw_inset,
    y_axis_drive_mount_screw_size,
    y_axis_drive_mount_screw_length,
    y_axis_drive_motor_plate_width,
    y_axis_drive_motor_plate_depth,
    y_axis_drive_idler_plate_width,
    y_axis_drive_motor_pulley_teeth,
    y_axis_drive_idler_teeth,
    y_axis_drive_belt_clear_span_extra,
    y_axis_drive_idler_housing_side_wall,
    y_axis_drive_idler_housing_front_wall,
    y_axis_drive_idler_housing_top_wall,
    y_axis_drive_idler_cage_top_clearance,
    y_axis_drive_idler_cage_front_clearance,
    y_axis_drive_idler_cage_height,
    y_axis_drive_tensioner_screw_holder_thickness,
    y_axis_drive_tensioner_screw_holder_depth,
    y_axis_drive_tensioner_screw_holder_width,
    y_axis_drive_idler_cage_wall,
    y_axis_drive_idler_cage_overlength,
    y_axis_drive_idler_clearance,
    y_axis_drive_idler_cage_back_wall,
    y_axis_drive_idler_tensioner_screw_length,
    y_axis_drive_idler_tensioner_screw_nut_wall,
    y_axis_drive_idler_tensioner_guide_clearance,
    y_axis_drive_idler_axle_screw_length,
    y_axis_drive_tensioner_screw_size,
    y_axis_drive_use_toothed_belt_visuals,
    y_axis_drive_tensioner_screw_z_offset,
    endcap_tensioner_screw_size,
    endcap_belt_clearance,
    context=None,
):
    """Create the y-axis drive positioned against the frame and bed clamps."""

    cfg = _DriveConfig(
        x_axis_motor_axle_length=x_axis_motor_axle_length,
        motor_mount_axle_clearance=motor_mount_axle_clearance,
        motor_mount_boss_clearance=motor_mount_boss_clearance,
        motor_mount_boss_clearance_z=motor_mount_boss_clearance_z,
        motor_mount_plate_thickness=motor_mount_plate_thickness,
        motor_mount_plate_fillet_radius=motor_mount_plate_fillet_radius,
        y_axis_drive_profile_mount_plate_width=y_axis_drive_profile_mount_plate_width,
        y_axis_drive_profile_mount_plate_height=y_axis_drive_profile_mount_plate_height,
        y_axis_drive_profile_mount_plate_thickness=y_axis_drive_profile_mount_plate_thickness,
        y_axis_drive_profile_mount_plate_fillet_radius=y_axis_drive_profile_mount_plate_fillet_radius,
        y_axis_motor_holder_side_wall_thickness=y_axis_motor_holder_side_wall_thickness,
        y_axis_motor_holder_side_wall_height=y_axis_motor_holder_side_wall_height,
        y_axis_motor_holder_side_wall_depth=y_axis_motor_holder_side_wall_depth,
        y_axis_drive_mount_screw_inset=y_axis_drive_mount_screw_inset,
        y_axis_drive_mount_screw_size=y_axis_drive_mount_screw_size,
        y_axis_drive_mount_screw_length=y_axis_drive_mount_screw_length,
        y_axis_drive_motor_plate_width=y_axis_drive_motor_plate_width,
        y_axis_drive_motor_plate_depth=y_axis_drive_motor_plate_depth,
        y_axis_drive_idler_plate_width=y_axis_drive_idler_plate_width,
        y_axis_drive_motor_pulley_teeth=y_axis_drive_motor_pulley_teeth,
        y_axis_drive_idler_teeth=y_axis_drive_idler_teeth,
        y_axis_drive_belt_clear_span_extra=y_axis_drive_belt_clear_span_extra,
        y_axis_drive_idler_housing_side_wall=y_axis_drive_idler_housing_side_wall,
        y_axis_drive_idler_housing_front_wall=y_axis_drive_idler_housing_front_wall,
        y_axis_drive_idler_housing_top_wall=y_axis_drive_idler_housing_top_wall,
        y_axis_drive_idler_cage_top_clearance=y_axis_drive_idler_cage_top_clearance,
        y_axis_drive_idler_cage_front_clearance=y_axis_drive_idler_cage_front_clearance,
        y_axis_drive_idler_cage_height=y_axis_drive_idler_cage_height,
        y_axis_drive_tensioner_screw_holder_thickness=y_axis_drive_tensioner_screw_holder_thickness,
        y_axis_drive_tensioner_screw_holder_depth=y_axis_drive_tensioner_screw_holder_depth,
        y_axis_drive_tensioner_screw_holder_width=y_axis_drive_tensioner_screw_holder_width,
        y_axis_drive_idler_cage_wall=y_axis_drive_idler_cage_wall,
        y_axis_drive_idler_cage_overlength=y_axis_drive_idler_cage_overlength,
        y_axis_drive_idler_clearance=y_axis_drive_idler_clearance,
        y_axis_drive_idler_cage_back_wall=y_axis_drive_idler_cage_back_wall,
        y_axis_drive_idler_tensioner_screw_length=y_axis_drive_idler_tensioner_screw_length,
        y_axis_drive_idler_tensioner_screw_nut_wall=y_axis_drive_idler_tensioner_screw_nut_wall,
        y_axis_drive_idler_tensioner_guide_clearance=y_axis_drive_idler_tensioner_guide_clearance,
        y_axis_drive_idler_axle_screw_length=y_axis_drive_idler_axle_screw_length,
        y_axis_drive_tensioner_screw_size=y_axis_drive_tensioner_screw_size,
        y_axis_drive_use_toothed_belt_visuals=y_axis_drive_use_toothed_belt_visuals,
        y_axis_drive_tensioner_screw_z_offset=y_axis_drive_tensioner_screw_z_offset,
        endcap_tensioner_screw_size=endcap_tensioner_screw_size,
        endcap_belt_clearance=endcap_belt_clearance,
        big_thing=(context or {}).get("BIG_THING", 500),
    )

    motor_mount = _create_y_axis_motor_mount(
        frame_back_profile, back_belt_reference, cfg
    )
    idler_mount = _create_y_axis_idler_mount(
        frame_front_profile,
        front_belt_reference,
        cfg,
    )
    belt_sections = _create_y_axis_drive_belt_sections(
        motor_mount,
        idler_mount,
        back_belt_reference,
        cfg,
    )

    follower_items = [("idler_mount_box", idler_mount.leader)] + list(
        idler_mount.get_named_follower_items()
    )
    visual_items = list(motor_mount.get_named_non_production_part_items())
    visual_items.extend(idler_mount.get_named_non_production_part_items())
    visual_items.extend(belt_sections)

    return LeaderFollowersCuttersPart(
        leader=motor_mount.leader,
        followers=[part for _, part in follower_items],
        non_production_parts=[part for _, part in visual_items],
        follower_names=[name for name, _ in follower_items],
        non_production_names=[name for name, _ in visual_items],
    )
