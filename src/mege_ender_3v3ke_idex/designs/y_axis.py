"""
Y Axis

Usage:
    cd <project_root> && ./run.sh path/to/y_axis.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/y_axis.py
"""

import logging
import os

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt2_idler, create_gt2_pulley
from mege_ender_3v3ke_idex.designs.idex_parameters import *
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
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

# Optional slicer process overrides
PROCESS_DATA = {
    "filament": "FilamentPLAMegeMaster",
    "process_overrides": {
        "nozzle_diameter": "0.6",
        "layer_height": "0.2",
    },
}

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
    part_bb = get_bounding_box(part)
    frame_cross_profile_bb = get_bounding_box(frame_cross_profile)

    if front_back == Alignment.BACK:
        delta_y = frame_cross_profile_bb[0][1] - part_bb[1][1]
    else:
        delta_y = frame_cross_profile_bb[1][1] - part_bb[0][1]

    return translate(0, delta_y, 0)(part)


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

    hole_drills = PartCollector()
    hole_pitch = (
        (
            y_axis_drive_profile_mount_plate_width
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
            BIG_THING,
            direction=(0, 1, 0),
        )
        hole_drill = translate(i * hole_pitch, 0, 0)(hole_drill)
        hole_drills = hole_drills.fuse(hole_drill)

    hole_drills = align(hole_drills, plate, Alignment.CENTER)
    plate = plate.cut(hole_drills)

    return plate


def _create_y_axis_motor_mount(y_axis, frame, back_belt_clamp):
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
    motor_mount_plate = align(
        motor_mount_plate, back_belt_clamp, Alignment.CENTER, axes=[0]
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
    pulley = align(pulley, back_belt_clamp, Alignment.CENTER, axes=[0, 2])
    pulley = align(pulley, motor_mount_plate, Alignment.CENTER, axes=[1])

    motor = motor.aligned_from_follower("axle", pulley, Alignment.CENTER)

    motor_body = motor.get_follower_part_by_name("body")
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


def _add_y_axis_idler_mount(y_axis, frame, front_belt_clamp):
    frame_front_profile = _create_y_axis_frame_cross_profile_reference(
        frame,
        Alignment.FRONT,
    )

    idler_mount_plate = create_filleted_box(
        y_axis_drive_idler_plate_width,
        y_axis_drive_idler_plate_depth,
        motor_mount_plate_thickness,
        motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    idler_mount_plate = align(
        idler_mount_plate, front_belt_clamp, Alignment.CENTER, axes=[0]
    )
    idler_mount_plate = _align_part_to_frame_profile_inner_face(
        idler_mount_plate,
        frame_front_profile,
        Alignment.FRONT,
    )

    idler = create_gt2_idler(num_teeth=y_axis_drive_idler_teeth)
    idler = align(idler, front_belt_clamp, Alignment.CENTER, axes=[0, 2])
    idler = align(idler, idler_mount_plate, Alignment.CENTER, axes=[1])

    idler_mount_plate = align(idler_mount_plate, idler, Alignment.STACK_BOTTOM)

    axle_cutter = create_cylinder(
        idler_mount_axle_diameter / 2 + idler_mount_axle_clearance,
        BIG_THING,
    )
    axle_cutter = align(axle_cutter, idler, Alignment.CENTER)
    idler_mount_plate = idler_mount_plate.cut(axle_cutter)

    screw_head_cutter = create_cylinder(
        MScrew.from_size(axle_screw_size).cylinder_head_diameter / 2
        + idler_screw_head_clearance,
        MScrew.from_size(axle_screw_size).cylinder_head_height
        + 2 * idler_screw_head_clearance,
    )
    screw_head_cutter = align(screw_head_cutter, idler, Alignment.CENTER)
    screw_head_cutter = align(screw_head_cutter, idler_mount_plate, Alignment.BOTTOM)
    idler_mount_plate = idler_mount_plate.cut(screw_head_cutter)

    profile_mount_plate = create_y_axis_profile_mount_plate()
    profile_mount_plate = align(
        profile_mount_plate, idler_mount_plate, Alignment.CENTER, axes=[0]
    )
    profile_mount_plate = align(profile_mount_plate, idler_mount_plate, Alignment.FRONT)
    profile_mount_plate = align(
        profile_mount_plate, idler_mount_plate, Alignment.STACK_BOTTOM
    )

    idler_mount_plate = idler_mount_plate.fuse(profile_mount_plate)

    idler_axle_screw = create_cylinder_screw(
        size=axle_screw_size,
        length=endcap_axle_screw_length,
    )
    idler_axle_screw = align(idler_axle_screw, idler, Alignment.CENTER)
    idler_axle_screw = align(idler_axle_screw, idler_mount_plate, Alignment.BOTTOM)

    y_axis.add_named_follower(idler_mount_plate, "idler_mount_plate")
    y_axis.add_named_non_production_part(idler, "idler")
    y_axis.add_named_non_production_part(idler_axle_screw, "idler_axle_screw")


def add_y_axis_drive_hardware(y_axis, print_bed_assembly, frame):
    back_belt_clamp = print_bed_assembly.get_follower_part_by_name(
        "belt_clamp_clamp_back"
    )
    front_belt_clamp = print_bed_assembly.get_follower_part_by_name(
        "belt_clamp_clamp_front"
    )

    _create_y_axis_motor_mount(y_axis, frame, back_belt_clamp)
    _add_y_axis_idler_mount(y_axis, frame, front_belt_clamp)

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
            skip_in_production=False,
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
        elif "mount" in name:
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
