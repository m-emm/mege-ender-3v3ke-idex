"""Declarative y-axis drive assembly."""

import copy
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
    y_axis_drive_idler_housing_top_above_frame_profile: float
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


def _create_y_axis_motor_bracket_adapter(frame_back_profile, motor_bracket, cfg):
    frame_center_z = get_bounding_box_center(frame_back_profile)[2]
    profile_half_height = cfg.y_axis_drive_profile_mount_plate_height / 2
    slot_bbox = get_bounding_box(
        motor_bracket.get_cutter_part_by_name("frame_mount_slots")
    )
    slot_z_clearance = max(6.0, 2 * cfg.motor_mount_plate_fillet_radius)
    adapter_z_min = min(
        frame_center_z - profile_half_height,
        slot_bbox[0][2] - slot_z_clearance,
    )
    adapter_z_max = max(
        frame_center_z + profile_half_height,
        slot_bbox[1][2] + slot_z_clearance,
    )
    adapter_height = adapter_z_max - adapter_z_min

    adapter = create_filleted_box(
        cfg.y_axis_drive_profile_mount_plate_width,
        cfg.y_axis_drive_profile_mount_plate_thickness,
        adapter_height,
        cfg.motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    adapter = align(adapter, motor_bracket.leader, Alignment.CENTER, axes=[0])
    adapter = align(adapter, motor_bracket.leader, Alignment.STACK_BACK)

    adapter_center_z = get_bounding_box_center(adapter)[2]
    adapter = translate(
        0,
        0,
        (adapter_z_min + adapter_z_max) / 2 - adapter_center_z,
    )(adapter)

    adapter = adapter.cut(motor_bracket.get_cutter_part_by_name("frame_mount_slots"))

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
        hole = align(hole, adapter, Alignment.CENTER, axes=[1])
        hole = align(hole, adapter, lr.edge_alignment)
        hole = translate(-lr.sign * cfg.y_axis_drive_mount_screw_inset, 0, 0)(hole)
        hole_center_z = get_bounding_box_center(hole)[2]
        hole = translate(0, 0, frame_center_z - hole_center_z)(hole)
        adapter = adapter.cut(hole)

        screw = create_cylinder_screw(
            cfg.y_axis_drive_mount_screw_size,
            cfg.y_axis_drive_mount_screw_length,
        )
        screw = rotate(90, axis=(1, 0, 0))(screw)
        screw = align(screw, hole, Alignment.CENTER)
        screw = align(screw, adapter, Alignment.FRONT)
        screw = translate(
            0,
            -MScrew.from_size(cfg.y_axis_drive_mount_screw_size).cylinder_head_height,
            0,
        )(screw)

        screws.append(screw)
        screw_names.append(f"profile_mount_screw_{lr.name.lower()}")

    return LeaderFollowersCuttersPart(
        leader=adapter,
        non_production_parts=screws,
        non_production_names=screw_names,
    )


def _create_y_axis_motor_mount(
    frame_back_profile,
    belt_reference,
    y_axis_nema23_motor_bracket_assembly,
    cfg,
):
    motor_bracket = copy.deepcopy(y_axis_nema23_motor_bracket_assembly)

    pulley = create_gt2_pulley(
        num_teeth=cfg.y_axis_drive_motor_pulley_teeth,
        belt_width=gt2_width,
    )
    pulley = align(
        pulley,
        motor_bracket.get_follower_part_by_name("axle"),
        Alignment.CENTER,
        axes=[1],
    )
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

    motor_bracket = motor_bracket.aligned_from_follower(
        "axle",
        pulley,
        Alignment.CENTER,
    )
    motor_mount_plate = _create_y_axis_motor_bracket_adapter(
        frame_back_profile,
        motor_bracket,
        cfg,
    )

    motor_visual_items = [("motor_bracket", motor_bracket.leader)]
    motor_visual_items = [
        *motor_visual_items,
        *[
            ("motor_axle" if name == "axle" else name, part)
            for name, part in motor_bracket.get_named_follower_items()
        ],
    ]
    motor_visual_items.extend(
        [
            (f"motor_bracket_{name}", part)
            for name, part in motor_bracket.get_named_non_production_part_items()
        ]
    )
    mount_visual_items = [
        (f"motor_{name}", part)
        for name, part in motor_mount_plate.get_named_non_production_part_items()
    ]
    visual_items = motor_visual_items + mount_visual_items + [("motor_pulley", pulley)]

    retval = LeaderFollowersCuttersPart(
        leader=motor_mount_plate.leader,
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

    idler_running_surface = _create_gt2_idler_running_surface_reference(
        cfg.y_axis_drive_idler_teeth
    )
    idler_running_surface = align(
        idler_running_surface,
        idler_cage.get_non_production_part_by_name("idler"),
        Alignment.CENTER,
    )
    idler_cage = _align_part_from_belt_contact_surface(
        idler_cage,
        idler_running_surface,
        belt_reference,
        cfg,
    )

    idler_cage_bbox = get_bounding_box(idler_cage)
    idler_cage_size = get_bounding_box_size(idler_cage)
    frame_front_profile_bbox = get_bounding_box(frame_front_profile)
    housing_inner_bottom_z = idler_cage_bbox[0][2] - cfg.y_axis_drive_idler_clearance
    housing_bottom_wall_thickness = cfg.y_axis_drive_idler_housing_side_wall

    housing_x_min = idler_cage_bbox[0][0] - cfg.y_axis_drive_idler_housing_side_wall
    housing_y_min = frame_front_profile_bbox[1][1]
    housing_z_min = housing_inner_bottom_z - housing_bottom_wall_thickness
    housing_top_z = (
        frame_front_profile_bbox[1][2]
        + cfg.y_axis_drive_idler_housing_top_above_frame_profile
    )

    outer_box_size_x = idler_cage_size[0] + 2 * cfg.y_axis_drive_idler_housing_side_wall
    outer_box_size_y = idler_cage_size[1] + cfg.y_axis_drive_idler_housing_front_wall
    outer_box_size_z = housing_top_z - housing_z_min
    if outer_box_size_z <= 0:
        raise ValueError(
            "y_axis_drive_idler_housing_top_above_frame_profile produces a "
            f"non-positive housing height ({outer_box_size_z:.2f} mm)"
        )

    outer_box = create_box(
        outer_box_size_x,
        outer_box_size_y,
        outer_box_size_z,
        origin=(housing_x_min, housing_y_min, housing_z_min),
    )

    front_wall_ref = create_box(
        outer_box_size_x,
        cfg.y_axis_drive_idler_housing_front_wall,
        outer_box_size_z,
        origin=(housing_x_min, housing_y_min, housing_z_min),
    )

    idler_cage = align(
        idler_cage,
        front_wall_ref,
        Alignment.STACK_BACK,
        stack_gap=cfg.y_axis_drive_idler_cage_front_clearance,
    )
    idler_cage_bbox = get_bounding_box(idler_cage)
    housing_inner_top_z = (
        idler_cage_bbox[1][2]
        + cfg.y_axis_drive_idler_clearance
        + cfg.y_axis_drive_idler_cage_top_clearance
    )
    housing_top_wall_thickness = housing_top_z - housing_inner_top_z
    if housing_top_wall_thickness < cfg.y_axis_drive_idler_housing_top_wall:
        raise ValueError(
            "y_axis_drive_idler_housing_top_above_frame_profile is too small: "
            f"derived top wall thickness {housing_top_wall_thickness:.2f} mm "
            f"is below minimum {cfg.y_axis_drive_idler_housing_top_wall:.2f} mm"
        )

    inner_cutter = create_box(
        idler_cage_size[0] + 2 * cfg.y_axis_drive_idler_clearance,
        cfg.big_thing,
        housing_inner_top_z - housing_inner_bottom_z,
        origin=(
            idler_cage_bbox[0][0] - cfg.y_axis_drive_idler_clearance,
            get_bounding_box(front_wall_ref)[1][1],
            housing_inner_bottom_z,
        ),
    )
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
        axes=[0, 1],
    )
    profile_mount_hole_drills = align(
        profile_mount_hole_drills,
        frame_front_profile,
        Alignment.CENTER,
        axes=[2],
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
        frame_front_profile,
        Alignment.STACK_BACK,
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
    y_axis_nema23_motor_bracket_assembly,
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
    y_axis_drive_idler_housing_top_above_frame_profile,
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
    BIG_THING,
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
        y_axis_drive_idler_housing_top_above_frame_profile=y_axis_drive_idler_housing_top_above_frame_profile,
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
        big_thing=BIG_THING,
    )

    motor_mount = _create_y_axis_motor_mount(
        frame_back_profile,
        back_belt_reference,
        y_axis_nema23_motor_bracket_assembly,
        cfg,
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
