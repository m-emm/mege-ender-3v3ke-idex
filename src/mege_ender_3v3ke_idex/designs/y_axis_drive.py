"""
Y Axis Drive

Usage:
    cd <project_root> && ./run.sh path/to/y_axis_drive.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/y_axis_drive.py
"""

import copy
import logging
import math
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.gt2belt import (
    create_gt_belt_clamp,
    create_gt2_pulley,
    create_gt2belt,
    gt2_pitch,
    gt2_teeth_thickness,
    gt2_thickness,
    gt2_width,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.idler_cage import create_idler_cage
from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from mege_ender_3v3ke_idex.designs.print_bed_undercarriage import (
    print_bed_undercarriage_belt_clamp_base_thickness,
    print_bed_undercarriage_belt_clamp_clamp_length,
    print_bed_undercarriage_belt_clamp_clamp_thickness,
    print_bed_undercarriage_belt_clamp_screw_hole_border,
    print_bed_undercarriage_belt_clamp_x_offset,
    print_bed_undercarriage_central_annulus_diameter,
    print_bed_undercarriage_profiles_height,
    print_bed_undercarriage_profiles_width,
)
from mege_ender_3v3ke_idex.designs.printer_frame import create_printer_frame
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF_04_HS)
PROCESS_DATA["process_overrides"].update(
    {
        "brim_type": "no_brim",
        "enable_support": "0",
        "support_object_first_layer_gap": 0.8,
        "external_perimeter_speed": "75",
        "fan_max_speed": "25",
        "fan_min_speed": "10",
        "outer_wall_speed": "75",
        "sparse_infill_density": "75%",
        "support_critical_regions_only": "1",
        "support_interface_spacing": "0.8",
        "support_on_build_plate_only": "1",
        "support_threshold_angle": "30",
        "support_top_z_distance": "0.3",
        "wall_loops": "3",
    }
)

y_axis_drive_profile_mount_plate_width = 90
y_axis_drive_profile_mount_plate_height = 40
y_axis_drive_profile_mount_plate_thickness = 9
y_axis_drive_profile_mount_plate_fillet_radius = (
    z_axis_profile_mount_plate_fillet_radius
)

y_axis_motor_holder_side_wall_thickness = 6
y_axis_motor_holder_side_wall_height = 25
y_axis_motor_holder_side_wall_depth = 40

y_axis_drive_mount_screw_inset = 5
y_axis_drive_mount_screw_size = "M5"
y_axis_drive_mount_screw_length = 16

y_axis_drive_motor_plate_width = 70
y_axis_drive_motor_plate_depth = 60
y_axis_drive_idler_plate_width = 34
y_axis_drive_idler_plate_depth = 40
y_axis_drive_motor_pulley_teeth = 20

y_axis_drive_idler_teeth = 20
y_axis_drive_belt_clear_span_extra = 0
y_axis_drive_idler_housing_side_wall = endcap_wall
y_axis_drive_idler_housing_front_wall = motor_mount_plate_thickness
y_axis_drive_idler_housing_top_wall = 1.0
y_axis_drive_idler_cage_top_clearance = 0.0
y_axis_drive_idler_cage_front_clearance = idler_cage_clearance
y_axis_drive_idler_cage_height = 20
y_axis_drive_use_toothed_belt_visuals = False
y_axis_drive_tensioner_screw_z_offset = 3.5
y_axis_drive_clamped_run_side = Alignment.RIGHT
y_axis_drive_clamped_run_contact_alignment = (
    Alignment.STACK_LEFT
    if y_axis_drive_clamped_run_side == Alignment.RIGHT
    else Alignment.STACK_RIGHT
)
y_axis_drive_return_run_alignment = (
    Alignment.STACK_LEFT
    if y_axis_drive_clamped_run_side == Alignment.RIGHT
    else Alignment.STACK_RIGHT
)

gt2_idler_running_surface_diameter_factor = (
    1.061032953945969  # TODO: Remove this magic number
)

Y_AXIS_DRIVE_LEADER_NAME = "motor_mount_plate"


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
        (num_teeth * gt2_pitch) / math.pi / gt2_idler_running_surface_diameter_factor
    )
    return create_cylinder(idler_running_surface_diameter / 2, belt_width)


def _align_part_from_belt_contact_surface(part, contact_surface, belt_reference):
    part = align_translation(
        contact_surface,
        belt_reference,
        Alignment.CENTER,
        axes=[2],
    )(part)
    return align_translation(
        contact_surface,
        belt_reference,
        y_axis_drive_clamped_run_contact_alignment,
    )(part)


def _create_y_axis_belt_visual(num_teeth):
    if y_axis_drive_use_toothed_belt_visuals:
        return create_gt2belt(num_teeth=num_teeth)

    belt_length = num_teeth * gt2_pitch
    return create_box(
        belt_length,
        gt2_thickness,
        gt2_width,
        origin=(-belt_length / 2, -gt2_thickness / 2, -gt2_width / 2),
    )


def _create_positioned_print_bed_reference(frame):
    print_bed = create_box(print_bed_width, print_bed_depth, print_bed_thickness)
    print_bed = align(print_bed, frame, Alignment.CENTER, axes=[0, 1])
    print_bed = translate(0, -print_bed_y_travel / 2, 0)(print_bed)
    return align(
        print_bed,
        frame,
        Alignment.STACK_TOP,
        stack_gap=print_bed_vertical_gap_to_frame,
    )


def _create_positioned_undercarriage_reference(print_bed_reference):
    undercarriage_reference = create_box(
        print_bed_undercarriage_central_annulus_diameter,
        print_bed_undercarriage_central_annulus_diameter,
        print_bed_undercarriage_profiles_height,
    )
    undercarriage_reference = align(
        undercarriage_reference,
        print_bed_reference,
        Alignment.CENTER,
        axes=[0, 1],
    )
    return align(
        undercarriage_reference,
        print_bed_reference,
        Alignment.STACK_BOTTOM,
        stack_gap=print_bed_damper_height,
    )


def create_y_axis_drive_belt_references(frame):
    print_bed_reference = _create_positioned_print_bed_reference(frame)
    undercarriage_reference = _create_positioned_undercarriage_reference(
        print_bed_reference
    )
    belt_references = {}

    for front_back in [Alignment.FRONT, Alignment.BACK]:
        belt_clamp = create_gt_belt_clamp(
            base_thicknness=print_bed_undercarriage_belt_clamp_base_thickness,
            clamp_thickness=print_bed_undercarriage_belt_clamp_clamp_thickness,
            clamp_length=print_bed_undercarriage_belt_clamp_clamp_length,
            screw_hole_border=print_bed_undercarriage_belt_clamp_screw_hole_border,
        )
        belt_clamp = rotate(90, axis=(1, 0, 0))(belt_clamp)
        belt_clamp = rotate(90)(belt_clamp)
        belt_clamp = align(belt_clamp, undercarriage_reference, Alignment.CENTER)
        belt_clamp = align(belt_clamp, undercarriage_reference, Alignment.STACK_BOTTOM)
        belt_clamp = translate(
            -print_bed_undercarriage_belt_clamp_base_thickness / 2
            + print_bed_undercarriage_belt_clamp_x_offset,
            front_back.sign
            * (
                print_bed_undercarriage_central_annulus_diameter / 2
                + print_bed_undercarriage_belt_clamp_clamp_length / 2
                - print_bed_undercarriage_profiles_width
            ),
            0,
        )(belt_clamp)

        belt_references[front_back] = belt_clamp.get_follower_part_by_name(
            "belt_path_cutter"
        )

    return belt_references[Alignment.BACK], belt_references[Alignment.FRONT]


def create_y_axis_profile_mount_plate():
    plate = create_filleted_box(
        y_axis_drive_profile_mount_plate_width,
        y_axis_drive_profile_mount_plate_thickness,
        y_axis_drive_profile_mount_plate_height,
        y_axis_drive_profile_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK, Alignment.TOP],
    )

    hole_drill_diameter = MScrew.from_size(
        y_axis_drive_mount_screw_size
    ).clearance_hole_loose

    screws = []
    screw_names = []
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        hole = create_cylinder(hole_drill_diameter / 2, BIG_THING, direction=(0, 1, 0))
        hole = align(hole, plate, Alignment.CENTER)
        hole = align(hole, plate, lr.edge_alignment)
        hole = translate(-lr.sign * y_axis_drive_mount_screw_inset, 0, 0)(hole)
        plate = plate.cut(hole)

        screw = create_cylinder_screw(
            y_axis_drive_mount_screw_size, y_axis_drive_mount_screw_length
        )
        screw = rotate(90, axis=(1, 0, 0))(screw)
        screw = align(screw, hole, Alignment.CENTER)
        screw = align(screw, plate, Alignment.FRONT)
        screw = translate(
            0, -MScrew.from_size(y_axis_drive_mount_screw_size).cylinder_head_height, 0
        )(screw)

        screws.append(screw)
        screw_names.append(f"profile_mount_screw_{lr.name.lower()}")

    return LeaderFollowersCuttersPart(
        leader=plate,
        non_production_parts=screws,
        non_production_names=screw_names,
    )


def create_y_axis_profile_mount_hole_drills(
    num_holes=2,
    screw_inset=y_axis_drive_mount_screw_inset,
):
    hole_drill_diameter = MScrew.from_size(
        y_axis_drive_mount_screw_size
    ).clearance_hole_loose

    hole_drills = PartCollector()
    hole_pitch = (
        (y_axis_drive_profile_mount_plate_width - 2 * screw_inset - hole_drill_diameter)
        / (num_holes - 1)
        if num_holes > 1
        else 0
    )

    for i in range(num_holes):
        hole_drill = create_cylinder(
            hole_drill_diameter / 2,
            BIG_THING,
            direction=(0, 1, 0),
        )
        hole_drill = translate(i * hole_pitch, 0, 0)(hole_drill)
        hole_drills = hole_drills.fuse(hole_drill)

    return hole_drills


def create_y_axis_motor_mount(frame, belt_reference):
    frame_back_profile = frame.get_non_production_part_by_name("frame_profile_back")
    motor = create_nema_composite(
        axle_length=x_axis_motor_axle_length,
        axle_clearance=motor_mount_axle_clearance,
        boss_clearance=motor_mount_boss_clearance,
        boss_clearance_z=motor_mount_boss_clearance_z,
    )

    motor_mount_plate = create_filleted_box(
        y_axis_drive_motor_plate_width,
        y_axis_drive_motor_plate_depth,
        motor_mount_plate_thickness,
        motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    motor_mount_plate = _align_part_to_frame_profile_inner_face(
        motor_mount_plate,
        frame_back_profile,
        Alignment.BACK,
    )

    pulley = create_gt2_pulley(
        num_teeth=y_axis_drive_motor_pulley_teeth,
        belt_width=gt2_width,
    )
    pulley = align(pulley, motor_mount_plate, Alignment.CENTER, axes=[1])
    pulley_running_surface = _create_gt2_pulley_running_surface_reference(
        y_axis_drive_motor_pulley_teeth
    )
    pulley_running_surface = align(pulley_running_surface, pulley, Alignment.CENTER)
    pulley = _align_part_from_belt_contact_surface(
        pulley,
        pulley_running_surface,
        belt_reference,
    )

    motor = motor.aligned_from_follower("axle", pulley, Alignment.CENTER)

    motor_body = motor.get_follower_part_by_name("body")
    motor_mount_plate = align(motor_mount_plate, pulley, Alignment.CENTER, axes=[0])
    motor_mount_plate = align(motor_mount_plate, motor_body, Alignment.STACK_TOP)

    side_walls = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        side_wall = create_box(
            y_axis_motor_holder_side_wall_thickness,
            y_axis_motor_holder_side_wall_depth,
            y_axis_motor_holder_side_wall_height,
        )
        side_wall = align(side_wall, motor_mount_plate, Alignment.CENTER)
        side_wall = align(side_wall, motor_mount_plate, Alignment.BACK)
        side_wall = align(side_wall, motor_mount_plate, lr)
        side_wall = align(side_wall, motor_mount_plate, Alignment.STACK_BOTTOM)
        side_walls = side_walls.fuse(side_wall)

    motor_mount_plate = motor_mount_plate.fuse(side_walls)
    motor_mount_plate = motor.use_as_cutter_on(motor_mount_plate)

    profile_mount_plate = create_y_axis_profile_mount_plate().prefixed_copy("motor")
    profile_mount_plate = align(
        profile_mount_plate,
        motor_mount_plate,
        Alignment.CENTER,
        axes=[0],
    )
    profile_mount_plate = align(profile_mount_plate, motor_mount_plate, Alignment.BACK)
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

    return LeaderFollowersCuttersPart(
        leader=motor_mount_plate,
        non_production_parts=[part for _, part in visual_items],
        non_production_names=[name for name, _ in visual_items],
    )


def _create_y_axis_idler_tensioner_cage():
    idler_cage = create_idler_cage(
        cage_back_wall=endcap_tensioner_cage_back_wall,
        cage_front_wall_thickness=idler_cage_wall,
        cage_wall=idler_cage_wall,
        cage_height=y_axis_drive_idler_cage_height,
        cage_overlength=endcap_tensioner_length,
        idler_tooth_count=y_axis_drive_idler_teeth,
        idler_clearance=endcap_idler_clearance,
        with_tensioner=True,
        tensioner_screw_size=endcap_tensioner_screw_size,
        axle_screw_length=endcap_axle_screw_length,
        belt_clearance=endcap_belt_clearance,
        cage_width_override=y_axis_drive_idler_plate_width,
        tensioner_screw_z_offset=y_axis_drive_tensioner_screw_z_offset,
    )

    return rotate(90)(idler_cage)


def create_y_axis_idler_mount(frame, belt_reference):
    frame_front_profile = frame.get_non_production_part_by_name("frame_profile_front")
    idler_cage = _create_y_axis_idler_tensioner_cage()
    idler_cage_size = get_bounding_box_size(idler_cage.leader)

    outer_box = create_box(
        idler_cage_size[0] + 2 * y_axis_drive_idler_housing_side_wall,
        idler_cage_size[1] + y_axis_drive_idler_housing_front_wall,
        y_axis_drive_profile_mount_plate_height,
    )

    front_wall_ref = create_box(
        get_bounding_box_size(outer_box)[0],
        y_axis_drive_idler_housing_front_wall,
        get_bounding_box_size(outer_box)[2],
    )
    front_wall_ref = align(front_wall_ref, outer_box, Alignment.CENTER, axes=[0, 2])
    front_wall_ref = align(front_wall_ref, outer_box, Alignment.FRONT)

    top_wall_ref = create_box(
        get_bounding_box_size(outer_box)[0],
        get_bounding_box_size(outer_box)[1],
        y_axis_drive_idler_housing_top_wall,
    )
    top_wall_ref = align(top_wall_ref, outer_box, Alignment.CENTER, axes=[0, 1])
    top_wall_ref = align(top_wall_ref, outer_box, Alignment.TOP)

    idler_cage = align(idler_cage, outer_box, Alignment.CENTER, axes=[0])
    idler_cage = align(
        idler_cage,
        front_wall_ref,
        Alignment.STACK_BACK,
        stack_gap=y_axis_drive_idler_cage_front_clearance,
    )
    idler_cage = align(
        idler_cage,
        top_wall_ref,
        Alignment.STACK_BOTTOM,
        stack_gap=y_axis_drive_idler_cage_top_clearance,
    )

    inner_cutter = create_box(
        idler_cage_size[0] + 2 * idler_cage_clearance,
        BIG_THING,
        idler_cage_size[2] + 2 * idler_cage_clearance,
    )
    inner_cutter = align(inner_cutter, idler_cage.leader, Alignment.CENTER, axes=[0, 2])
    inner_cutter = align(inner_cutter, front_wall_ref, Alignment.STACK_BACK)
    outer_box = outer_box.cut(inner_cutter)

    profile_mount_hole_drills = create_y_axis_profile_mount_hole_drills()
    profile_mount_hole_drills = align(
        profile_mount_hole_drills,
        outer_box,
        Alignment.CENTER,
    )
    outer_box = outer_box.cut(profile_mount_hole_drills)

    tensioner_screw_part = idler_cage.get_non_production_part_by_name("tensioner_screw")
    tensioner_screw_hole_cutter = create_cylinder(
        MScrew.from_size(endcap_tensioner_screw_size).clearance_hole_normal / 2,
        BIG_THING,
        direction=(0, 1, 0),
    )
    tensioner_screw_hole_cutter = align(
        tensioner_screw_hole_cutter,
        tensioner_screw_part,
        Alignment.CENTER,
        axes=[0, 2],
    )
    outer_box = outer_box.cut(tensioner_screw_hole_cutter)

    idler_mount = LeaderFollowersCuttersPart(
        leader=outer_box,
        followers=[idler_cage.leader],
        non_production_parts=[
            idler_cage.get_non_production_part_by_name("idler"),
            idler_cage.get_non_production_part_by_name("axle"),
            idler_cage.get_non_production_part_by_name("axle_threaded_inset"),
            tensioner_screw_part,
            idler_cage.get_non_production_part_by_name("tensioner_nut"),
        ],
        follower_names=["idler_tensioner_cage"],
        non_production_names=[
            "idler",
            "idler_axle_screw",
            "idler_axle_threaded_inset",
            "idler_tensioner_screw",
            "idler_tensioner_nut",
        ],
    )

    idler_running_surface = _create_gt2_idler_running_surface_reference(
        y_axis_drive_idler_teeth
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
    )
    idler_mount = _align_part_to_frame_profile_inner_face(
        idler_mount,
        frame_front_profile,
        Alignment.FRONT,
    )

    idler_profile_mount_plate = create_y_axis_profile_mount_plate().prefixed_copy(
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


def create_y_axis_drive_belt_sections(
    motor_mount,
    idler_mount,
    back_belt_reference,
):
    pulley = motor_mount.get_non_production_part_by_name("motor_pulley")
    idler = idler_mount.get_non_production_part_by_name("idler")

    pulley_center = get_bounding_box_center(pulley)
    idler_center = get_bounding_box_center(idler)
    belt_length = (
        abs(pulley_center[1] - idler_center[1]) + y_axis_drive_belt_clear_span_extra
    )
    num_teeth = max(1, int(round(belt_length / gt2_pitch)))
    belt_center_y = (pulley_center[1] + idler_center[1]) / 2

    belt_sections = []
    right_belt_reference = back_belt_reference
    pulley_running_surface = _create_gt2_pulley_running_surface_reference(
        y_axis_drive_motor_pulley_teeth
    )
    pulley_running_surface = align(pulley_running_surface, pulley, Alignment.CENTER)

    for side, rotation_angle in (
        (Alignment.LEFT, 90),
        (Alignment.RIGHT, -90),
    ):
        belt = _create_y_axis_belt_visual(num_teeth)
        belt = rotate(rotation_angle)(belt)
        belt = _translate_part_center_to_axis_value(belt, 1, belt_center_y)
        belt = align(belt, right_belt_reference, Alignment.CENTER, axes=[2])

        if side == y_axis_drive_clamped_run_side:
            belt = align(belt, right_belt_reference, Alignment.CENTER, axes=[0])
        else:
            belt = align(
                belt,
                pulley_running_surface,
                y_axis_drive_return_run_alignment,
            )

        belt_sections.append((f"y_axis_belt_section_{side.name.lower()}", belt))

    return belt_sections


def create_y_axis_drive(frame, *, back_belt_reference, front_belt_reference):
    motor_mount = create_y_axis_motor_mount(frame, back_belt_reference)
    idler_mount = create_y_axis_idler_mount(frame, front_belt_reference)
    belt_sections = create_y_axis_drive_belt_sections(
        motor_mount,
        idler_mount,
        back_belt_reference,
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


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    frame = create_printer_frame()
    back_belt_reference, front_belt_reference = create_y_axis_drive_belt_references(
        frame
    )
    drive = create_y_axis_drive(
        frame,
        back_belt_reference=back_belt_reference,
        front_belt_reference=front_belt_reference,
    )

    parts.add(frame, "printer_frame", flip=False, skip_in_production=True)

    parts.add(
        drive.leader,
        Y_AXIS_DRIVE_LEADER_NAME,
        flip=False,
        skip_in_production=False,
    )

    for name, follower in drive.get_named_follower_items():
        parts.add(follower, name, flip=False, skip_in_production=False)

    for name, npp in drive.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        export_stl=PROD,
    )

    _logger.info("y_axis_drive created successfully!")


if __name__ == "__main__":
    main()
