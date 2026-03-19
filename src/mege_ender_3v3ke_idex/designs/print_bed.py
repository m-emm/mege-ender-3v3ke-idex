from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.metrics_collector import (
    Material,
    log_metrics_report,
    record_length_metric,
    record_measured_mass_metric,
    record_weight_metric,
    reset_metrics,
)
from shellforgepy.simple import *

Y_AXIS_MOVING_MASS_ASSEMBLY_ID = "y_axis_moving_mass"


def _record_print_bed_weight_metrics(print_bed):
    record_measured_mass_metric(
        Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
        material=Material.ALUMINUM,
        mass_kg=print_bed_main_measured_mass_kg,
        part_id="print_bed_main",
    )

    screw_volume_mm3 = 0.0
    for name, part in print_bed.get_named_non_production_part_items():
        if name == "print_bed_foil":
            record_measured_mass_metric(
                Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
                material=Material.STEEL,
                mass_kg=print_bed_foil_measured_mass_kg,
                part_id="print_bed_magnetic_foil",
            )
            continue

        if name.startswith("screw_"):
            screw_volume_mm3 += get_volume(part)

    if screw_volume_mm3 > 0:
        record_weight_metric(
            Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
            Material.STEEL,
            screw_volume_mm3,
            part_id="print_bed_mount_screws",
        )


def create_print_bed():

    plate = create_box(print_bed_width, print_bed_depth, print_bed_thickness)

    inset = (print_bed_depth - print_bed_mount_hole_pitch) / 2

    retval = LeaderFollowersCuttersPart(plate)

    for lr in [Alignment.EDGE_LEFT, Alignment.EDGE_RIGHT]:
        for fb in [Alignment.EDGE_FRONT, Alignment.EDGE_BACK]:

            hole_drill = create_cylinder(print_bed_mount_hole_diameter / 2, BIG_THING)
            hole_drill = align(hole_drill, plate, Alignment.CENTER, axes=[2])
            hole_drill = align(hole_drill, plate, lr)
            hole_drill = align(hole_drill, plate, fb)
            hole_drill = translate(-inset * lr.sign, -inset * fb.sign, 0)(hole_drill)

            retval = retval.cut(hole_drill)

            screw = create_conical_head_screw(
                print_bed_mount_screw_size, print_bed_mount_screw_length
            )

            screw = align(screw, hole_drill, Alignment.CENTER)
            screw = align(screw, plate, Alignment.TOP)

            retval.add_named_non_production_part(
                screw,
                f"screw_{lr.name.lower().replace('edge_','')}_{fb.name.lower().replace('edge_','')}",
            )
            retval = retval.cut(screw)

            damper = create_cylinder(
                print_bed_damper_diameter / 2, print_bed_damper_height
            )

            damper = align(damper, hole_drill, Alignment.CENTER)
            damper = align(damper, plate, Alignment.STACK_BOTTOM)
            damper = damper.cut(hole_drill)

            retval.add_named_non_production_part(
                damper,
                f"damper_{lr.name.lower().replace('edge_','')}_{fb.name.lower().replace('edge_','')}",
            )

    foil = create_box(print_bed_width, print_bed_depth, print_bed_foil_thickness)
    foil = align(foil, plate, Alignment.CENTER, axes=[0, 1])
    foil = align(foil, plate, Alignment.STACK_TOP)
    retval.add_named_non_production_part(foil, "print_bed_foil")
    _record_print_bed_weight_metrics(retval)

    return retval
