"""
Y Axis

Usage:
    cd <project_root> && ./run.sh path/to/y_axis.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/y_axis.py
"""

import copy
import inspect
import logging
import math
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.gt2belt import (
    create_gt2_pulley,
    create_gt2belt,
    gt2_pitch,
    gt2_teeth_thickness,
    gt2_thickness,
    gt2_width,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.idler_cage import create_idler_cage
from mege_ender_3v3ke_idex.designs.metrics_collector import (
    Material,
    log_metrics_report,
    record_length_metric,
    record_weight_metric,
    reset_metrics,
)
from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12ca_rail_with_carriages
from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from mege_ender_3v3ke_idex.designs.print_bed import (
    Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
    add_print_bed_parts_to_assembly,
    create_print_bed,
)
from mege_ender_3v3ke_idex.designs.print_bed_undercarriage import (
    create_print_bed_undercarriage,
)
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


# Production mode from environment variable
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


y_axis_drive_profile_mount_plate_width = z_axis_profile_mount_width
y_axis_drive_profile_mount_plate_height = z_axis_profile_mount_plate_height
y_axis_drive_profile_mount_plate_thickness = z_axis_profile_mount_plate_thickness
y_axis_drive_profile_mount_plate_fillet_radius = (
    z_axis_profile_mount_plate_fillet_radius
)
y_axis_drive_mount_screw_inset = 5
y_axis_drive_mount_screw_size = "M5"
y_axis_drive_motor_plate_width = motor_mount_plate_size
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
y_axis_drive_idler_cage_height = 19
y_axis_drive_clamped_run_side = Alignment.RIGHT
y_axis_drive_use_toothed_belt_visuals = False
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
gt2_idler_running_surface_diameter_factor = 1.061032953945969


def _record_weight_for_part(part, *, material: Material, part_id: str):
    record_weight_metric(
        Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
        material,
        get_volume(part),
        part_id=part_id,
    )


def _record_y_axis_carriage_weight_metrics(y_axis):
    carriage_volume_mm3 = 0.0
    for name, part in y_axis.get_named_follower_items():
        if "carriage" not in name:
            continue
        carriage_volume_mm3 += get_volume(part)

    if carriage_volume_mm3 > 0:
        record_weight_metric(
            Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
            Material.STEEL,
            carriage_volume_mm3,
            part_id="mgn12ca_carriages",
        )


def _get_y_axis_carriages_fused(y_axis):
    y_axis_carriages = PartCollector()
    for name, follower in y_axis.get_named_follower_items():
        if "carriage" not in name:
            continue

        y_axis_carriages = y_axis_carriages.fuse(follower)

    return y_axis_carriages


def _align_y_axis_to_print_bed_undercarriage(y_axis, frame):
    reference_print_bed = create_positioned_print_bed(
        y_axis,
        frame,
        record_metrics=False,
    )
    undercarriage = create_print_bed_undercarriage(
        reference_print_bed,
        record_metrics=False,
    )
    y_axis_carriages = _get_y_axis_carriages_fused(y_axis)

    undercarriage_bb = get_bounding_box(undercarriage.leader)
    y_axis_carriages_bb = get_bounding_box(y_axis_carriages)
    y_axis_drop_mm = y_axis_carriages_bb[1][2] - undercarriage_bb[0][2]

    _logger.info(
        "Dropping y_axis by %.3f mm so the print bed undercarriage seats on the Y carriages while preserving the bed Z reference",
        y_axis_drop_mm,
    )

    return translate(0, 0, -y_axis_drop_mm)(y_axis)


def create_positioned_print_bed(y_axis, frame, *, record_metrics=True):
    y_axis_carriages = _get_y_axis_carriages_fused(y_axis)

    print_bed = create_print_bed(record_metrics=record_metrics)
    print_bed = align(print_bed, y_axis_carriages, Alignment.CENTER, axes=[0, 1])
    print_bed = align(
        print_bed,
        frame,
        Alignment.STACK_TOP,
        stack_gap=print_bed_vertical_gap_to_frame,
    )

    return print_bed


def create_positioned_print_bed_assembly(y_axis, frame):
    print_bed = create_positioned_print_bed(y_axis, frame)
    print_bed_undercarriage = create_print_bed_undercarriage(print_bed)
    return add_print_bed_parts_to_assembly(print_bed_undercarriage, print_bed)


def align_y_axis_to_frame(y_axis, frame):
    y_axis = align(y_axis, frame, Alignment.CENTER, axes=[0, 1])
    y_axis_profile_left = y_axis.get_non_production_part_by_name("profile_left")

    axis_aligner = align_translation(
        y_axis_profile_left, frame, Alignment.CENTER, axes=[2]
    )

    y_axis = axis_aligner(y_axis)

    return _align_y_axis_to_print_bed_undercarriage(y_axis, frame)


def _get_y_axis_profiles_fused(y_axis):
    profile_left = y_axis.get_non_production_part_by_name("profile_left")
    profile_right = y_axis.get_non_production_part_by_name("profile_right")
    return profile_left.fuse(profile_right)


def _create_y_axis_frame_cross_profile_reference(frame, front_back):
    frame_cross_profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_4040,
        length_mm=frame_inner_width,
    )
    frame_cross_profile = rotate(90, axis=(0, 1, 0))(frame_cross_profile)
    frame_cross_profile = align(
        frame_cross_profile,
        frame.leader,
        Alignment.CENTER,
        axes=[0, 2],
    )
    frame_cross_profile = align(frame_cross_profile, frame.leader, front_back)

    return frame_cross_profile


def _align_part_to_frame_profile_inner_face(part, frame_cross_profile, front_back):
    if front_back == Alignment.BACK:
        return align(part, frame_cross_profile, Alignment.STACK_FRONT)

    return align(part, frame_cross_profile, Alignment.STACK_BACK)


def create_y_axis_profile_mount_plate(
    num_holes=2,
    screw_inset=y_axis_drive_mount_screw_inset,
):
    plate = create_filleted_box(
        y_axis_drive_profile_mount_plate_width,
        y_axis_drive_profile_mount_plate_thickness,
        y_axis_drive_profile_mount_plate_height,
        y_axis_drive_profile_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK, Alignment.BOTTOM],
    )

    hole_drill_diameter = MScrew.from_size(
        y_axis_drive_mount_screw_size
    ).clearance_hole_loose

    hole_drills = create_y_axis_profile_mount_hole_drills(
        num_holes=num_holes,
        screw_inset=screw_inset,
    )
    hole_drills = align(hole_drills, plate, Alignment.CENTER)
    plate = plate.cut(hole_drills)

    return plate


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


def _create_gt2_pulley_running_surface_reference(num_teeth, belt_width=6):
    pulley_running_surface_diameter = (
        (num_teeth * gt2_pitch) / math.pi - gt2_thickness + gt2_teeth_thickness
    )
    return create_cylinder(pulley_running_surface_diameter / 2, belt_width)


def _create_gt2_idler_running_surface_reference(num_teeth, belt_width=6):
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


def _create_y_axis_motor_mount(y_axis, frame, back_belt_reference):
    frame_back_profile = _create_y_axis_frame_cross_profile_reference(
        frame,
        Alignment.BACK,
    )
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
        belt_width=6,
    )
    pulley = align(pulley, motor_mount_plate, Alignment.CENTER, axes=[1])
    pulley_running_surface = _create_gt2_pulley_running_surface_reference(
        y_axis_drive_motor_pulley_teeth
    )
    pulley_running_surface = align(pulley_running_surface, pulley, Alignment.CENTER)
    pulley = _align_part_from_belt_contact_surface(
        pulley,
        pulley_running_surface,
        back_belt_reference,
    )

    motor = motor.aligned_from_follower("axle", pulley, Alignment.CENTER)

    motor_body = motor.get_follower_part_by_name("body")
    motor_mount_plate = align(motor_mount_plate, pulley, Alignment.CENTER, axes=[0])
    motor_mount_plate = align(motor_mount_plate, motor_body, Alignment.STACK_TOP)

    motor_mount_plate = motor.use_as_cutter_on(motor_mount_plate)

    profile_mount_plate = create_y_axis_profile_mount_plate()
    profile_mount_plate = align(
        profile_mount_plate, motor_mount_plate, Alignment.CENTER, axes=[0]
    )
    profile_mount_plate = align(profile_mount_plate, motor_mount_plate, Alignment.BACK)
    profile_mount_plate = align(
        profile_mount_plate, motor_mount_plate, Alignment.STACK_BOTTOM
    )

    motor_mount_plate = motor_mount_plate.fuse(profile_mount_plate)

    y_axis.add_named_follower(motor_mount_plate, "motor_mount_plate")
    for name, part in motor.get_named_follower_items():
        if name == "coupler":
            continue
        y_axis.add_named_non_production_part(part, f"motor_{name}")
    y_axis.add_named_non_production_part(pulley, "motor_pulley")

    return pulley


def _translate_part_center_to_axis_value(part, axis, value):
    center = get_bounding_box_center(part)
    delta = [0, 0, 0]
    delta[axis] = value - center[axis]
    return translate(*delta)(part)


def _add_y_axis_belt_sections(
    y_axis,
    pulley,
    idler,
    front_belt_reference,
    back_belt_reference,
):
    pulley_center = get_bounding_box_center(pulley)
    idler_center = get_bounding_box_center(idler)
    belt_length = (
        abs(pulley_center[1] - idler_center[1]) + y_axis_drive_belt_clear_span_extra
    )
    num_teeth = max(1, int(round(belt_length / gt2_pitch)))
    belt_center_y = (pulley_center[1] + idler_center[1]) / 2

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
                belt, pulley_running_surface, y_axis_drive_return_run_alignment
            )

        y_axis.add_named_non_production_part(
            belt,
            f"y_axis_belt_section_{side.name.lower()}",
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
    )

    return rotate(90)(idler_cage)


def _add_y_axis_idler_mount(y_axis, frame, front_belt_reference):
    frame_front_profile = _create_y_axis_frame_cross_profile_reference(
        frame,
        Alignment.FRONT,
    )
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

    idler_mount_assembly = LeaderFollowersCuttersPart(leader=outer_box)
    idler_mount_assembly.add_named_follower(idler_cage.leader, "idler_tensioner_cage")
    idler_mount_assembly.add_named_non_production_part(
        idler_cage.get_non_production_part_by_name("idler"),
        "idler",
    )
    idler_mount_assembly.add_named_non_production_part(
        idler_cage.get_non_production_part_by_name("axle"),
        "idler_axle_screw",
    )
    idler_mount_assembly.add_named_non_production_part(
        idler_cage.get_non_production_part_by_name("axle_threaded_inset"),
        "idler_axle_threaded_inset",
    )
    idler_mount_assembly.add_named_non_production_part(
        tensioner_screw_part,
        "idler_tensioner_screw",
    )
    idler_mount_assembly.add_named_non_production_part(
        idler_cage.get_non_production_part_by_name("tensioner_nut"),
        "idler_tensioner_nut",
    )

    idler_running_surface = _create_gt2_idler_running_surface_reference(
        y_axis_drive_idler_teeth
    )
    idler_running_surface = align(
        idler_running_surface,
        idler_mount_assembly.get_non_production_part_by_name("idler"),
        Alignment.CENTER,
    )
    idler_mount_assembly = _align_part_from_belt_contact_surface(
        idler_mount_assembly,
        idler_running_surface,
        front_belt_reference,
    )
    idler_mount_assembly = _align_part_to_frame_profile_inner_face(
        idler_mount_assembly,
        frame_front_profile,
        Alignment.FRONT,
    )

    y_axis.add_named_follower(idler_mount_assembly.leader, "idler_mount_box")
    y_axis.add_named_follower(
        idler_mount_assembly.get_follower_part_by_name("idler_tensioner_cage"),
        "idler_tensioner_cage",
    )
    y_axis.add_named_non_production_part(
        idler_mount_assembly.get_non_production_part_by_name("idler"),
        "idler",
    )
    y_axis.add_named_non_production_part(
        idler_mount_assembly.get_non_production_part_by_name("idler_axle_screw"),
        "idler_axle_screw",
    )
    y_axis.add_named_non_production_part(
        idler_mount_assembly.get_non_production_part_by_name(
            "idler_axle_threaded_inset"
        ),
        "idler_axle_threaded_inset",
    )
    y_axis.add_named_non_production_part(
        idler_mount_assembly.get_non_production_part_by_name("idler_tensioner_screw"),
        "idler_tensioner_screw",
    )
    y_axis.add_named_non_production_part(
        idler_mount_assembly.get_non_production_part_by_name("idler_tensioner_nut"),
        "idler_tensioner_nut",
    )

    return idler_mount_assembly.get_non_production_part_by_name("idler")


def add_y_axis_drive_hardware(y_axis, print_bed_assembly, frame):
    back_belt_reference = print_bed_assembly.get_cutter_part_by_name(
        "belt_path_cutter_back"
    )
    front_belt_reference = print_bed_assembly.get_cutter_part_by_name(
        "belt_path_cutter_front"
    )

    pulley = _create_y_axis_motor_mount(y_axis, frame, back_belt_reference)
    idler = _add_y_axis_idler_mount(y_axis, frame, front_belt_reference)
    _add_y_axis_belt_sections(
        y_axis,
        pulley,
        idler,
        front_belt_reference,
        back_belt_reference,
    )

    return y_axis


def create_y_axis():
    """Create the y_axis part."""

    rails = []
    for i in [-1, 1]:

        rail_side_name = "left" if i == -1 else "right"
        record_length_metric(
            "extrusion_profile",
            ExtrusionProfileType.PROFILE_2020.value,
            f"y_axis_profile_{rail_side_name}",
            y_axis_profile_length,
        )
        profile = create_alu_extrusion_profile(
            ExtrusionProfileType.PROFILE_2020, length_mm=y_axis_profile_length
        )

        profile = rotate(90, axis=(1, 0, 0))(profile)
        profile = align(profile, None, Alignment.CENTER)
        profile = translate(i * y_axis_rail_spacing / 2, 0, 0)(profile)

        rail_side_name = "left" if i == -1 else "right"
        record_length_metric(
            "linear_rail",
            "MGN12",
            f"y_axis_rail_{rail_side_name}",
            y_axis_rail_length,
        )
        rail = create_mgn12ca_rail_with_carriages(
            y_axis_rail_length,
            carriage_offsets=[
                -y_axis_rail_length / 2 + mgn_12ca_carriage_length / 2,
                -y_axis_rail_length / 2
                + y_axis_carriage_spacing
                + mgn_12ca_carriage_length / 2,
            ],
            carriage_names=["carriage_front", "carriage_back"],
        )
        rail = rotate(90)(rail)
        rail = rail.prefixed_copy(f"rail_{rail_side_name}")
        rail.rename_follower(
            f"rail_{rail_side_name}_carriage_front",
            f"carriage_front_carriage_{rail_side_name}",
        )
        rail.rename_follower(
            f"rail_{rail_side_name}_carriage_back",
            f"carriage_back_carriage_{rail_side_name}",
        )

        rail = align(rail, profile, Alignment.CENTER)
        rail = align(rail, profile, Alignment.STACK_TOP)
        rail.add_named_non_production_part(profile, f"profile_{rail_side_name}")

        rails.append(rail)

    y_axis = rails[0].fuse(rails[1])
    _record_y_axis_carriage_weight_metrics(y_axis)

    return y_axis


def main():

    from mege_ender_3v3ke_idex.designs.printer_frame import (  # noqa: F401
        create_printer_frame,
    )

    logging.basicConfig(level=logging.INFO)
    reset_metrics()

    _logger.info(f"y_axis_profile_length: {y_axis_profile_length}")
    _logger.info(f"y_axis_rail_length: {y_axis_rail_length}")

    bed_animation = {"bed_y": (0, print_bed_y_travel, 0)}

    parts = PartList()

    frame = create_printer_frame()

    parts.add(frame, "printer_frame", flip=False, skip_in_production=True)

    y_axis = align_y_axis_to_frame(create_y_axis(), frame)
    print_bed_assembly = create_positioned_print_bed_assembly(y_axis, frame)
    y_axis = add_y_axis_drive_hardware(y_axis, print_bed_assembly, frame)

    parts.add(y_axis.leader, "y_axis", flip=False, skip_in_production=True)
    # parts.add(
    #     print_bed_assembly,
    #     "print_bed_undercarriage",
    #     flip=False,
    #     skip_in_production=False,
    #     animation=bed_animation,
    # )
    for name, follower in print_bed_assembly.get_named_follower_items():
        parts.add(
            follower,
            name,
            flip=False,
            skip_in_production=True,
            animation=bed_animation,
        )
    for name, npp in print_bed_assembly.get_named_non_production_part_items():
        parts.add(
            npp,
            name,
            flip=False,
            skip_in_production=True,
            animation=bed_animation,
        )

    for name, follower in y_axis.get_named_follower_items():
        animation = None
        skip_in_production = True

        if "carriage" in name:
            _logger.info(f"Using bed_animation for {name}")
            animation = bed_animation
        elif "mount" in name or "cage" in name:
            skip_in_production = False
        else:
            _logger.info(f"NOT Using bed_animation for {name}")

        parts.add(
            follower,
            name,
            flip=False,
            skip_in_production=skip_in_production,
            animation=animation,
        )

    for name, npp in y_axis.get_named_non_production_part_items():
        animation = None

        if "carriage" in name:
            _logger.info(f"Using bed_animation for {name}")
            animation = bed_animation
        else:
            _logger.info(f"NOT Using bed_animation for {name}")

        parts.add(npp, name, flip=False, skip_in_production=True, animation=animation)

    log_metrics_report(_logger)
    _logger.info(
        "Y-axis moving mass currently includes the bed plate, magnetic foil, MGN12CA carriages, bed screws, "
        "the PETG_CF print bed undercarriage, and the aluminum mount towers. "
        "The bed plate and foil use measured masses. The linear rails do not move and are excluded. "
        "Dampers are currently excluded."
    )

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        export_stl=PROD,
    )

    _logger.info("y_axis created successfully!")


if __name__ == "__main__":
    main()
