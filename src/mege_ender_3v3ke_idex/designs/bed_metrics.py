"""Shared bed weight metrics for assembly-owned construction."""

from shellforgepy.metrics import (
    Material,
    record_measured_mass_metric,
    record_weight_metric,
)
from shellforgepy.simple import get_volume

Y_AXIS_MOVING_MASS_ASSEMBLY_ID = "y_axis_moving_mass"


def record_print_bed_weight_metrics(
    print_bed,
    *,
    print_bed_main_measured_mass_kg,
    print_bed_foil_measured_mass_kg,
):
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
