"""
Whole Printer

Usage:
    cd <project_root> && ./run.sh path/to/whole_printer.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/whole_printer.py
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.metrics_collector import (
    log_metrics_report,
    reset_metrics,
)
from mege_ender_3v3ke_idex.designs.printer_feet import create_printer_feet
from mege_ender_3v3ke_idex.designs.printer_frame import create_printer_frame
from mege_ender_3v3ke_idex.designs.x_axis import (
    create_positioned_tool_head_mounts,
    create_x_axis,
    create_x_carriage_animation_map,
)
from mege_ender_3v3ke_idex.designs.y_axis import (
    align_y_axis_to_frame,
    create_positioned_print_bed_assembly,
    create_y_axis,
)
from mege_ender_3v3ke_idex.designs.y_axis_drive import (
    Y_AXIS_DRIVE_LEADER_NAME,
    create_y_axis_drive,
)
from mege_ender_3v3ke_idex.designs.z_axis import (
    create_positioned_z_axis_assembly,
    create_z_axis,
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


@dataclass
class WholePrinterAssembly:
    frame: LeaderFollowersCuttersPart
    printer_feet: LeaderFollowersCuttersPart
    y_axis: LeaderFollowersCuttersPart
    y_axis_drive: LeaderFollowersCuttersPart
    print_bed_assembly: Any
    positioned_z_axes: dict
    positioned_carriages: dict
    x_axis: LeaderFollowersCuttersPart
    tool_head_mounts: dict


def align_x_axis_to_z_carriages(x_axis, z_axes_fused, carriages_fused):
    """Place the X axis relative to the Z carriages using the shared assembly rules."""

    x_axis = align(x_axis, z_axes_fused, Alignment.CENTER, axes=[0, 1])

    lower_axis_profile = x_axis.get_non_production_part_by_name("lower_axis_profile")
    axis_profile_aligner = align_translation(
        lower_axis_profile,
        carriages_fused,
        Alignment.FRONT,
    )
    x_axis = axis_profile_aligner(x_axis)

    lower_axis_profile = x_axis.get_non_production_part_by_name("lower_axis_profile")
    axis_profile_aligner = align_translation(
        lower_axis_profile,
        carriages_fused,
        Alignment.BOTTOM,
    )
    x_axis = axis_profile_aligner(x_axis)

    x_axis = translate(0, 0, z_axis_carriage_x_axis_connector_thickness)(x_axis)

    return x_axis


def create_positioned_x_z_axis_assembly(
    x_axis,
    z_axis_factory,
    *,
    frame=None,
    carriage_z_offset,
):
    positioned_z_axes, positioned_carriages = create_positioned_z_axis_assembly(
        z_axis_factory=z_axis_factory,
        frame=frame,
        carriage_z_offset=carriage_z_offset,
    )

    z_axes_fused = PartCollector()
    carriages_fused = PartCollector()

    for z_axis in positioned_z_axes.values():
        z_axes_fused = z_axes_fused.fuse(z_axis.leader)

    for carriage in positioned_carriages.values():
        carriages_fused = carriages_fused.fuse(carriage.leaders_followers_fused())

    x_axis = align_x_axis_to_z_carriages(x_axis, z_axes_fused, carriages_fused)

    return positioned_z_axes, positioned_carriages, x_axis


def create_whole_printer():
    """Create the whole printer assembly from the frame and axis modules."""

    frame = create_printer_frame()
    printer_feet = create_printer_feet(frame)
    y_axis = align_y_axis_to_frame(create_y_axis(), frame)
    print_bed_assembly = create_positioned_print_bed_assembly(y_axis, frame)
    y_axis_drive = create_y_axis_drive(
        frame,
        back_belt_reference=print_bed_assembly.get_cutter_part_by_name(
            "belt_path_cutter_back"
        ),
        front_belt_reference=print_bed_assembly.get_cutter_part_by_name(
            "belt_path_cutter_front"
        ),
    )
    x_axis = create_x_axis()
    positioned_z_axes, positioned_carriages, x_axis = (
        create_positioned_x_z_axis_assembly(
            x_axis,
            create_z_axis,
            frame=frame,
            carriage_z_offset=z_axis_carriage_z_offset,
        )
    )
    tool_head_mounts = create_positioned_tool_head_mounts(x_axis)

    return WholePrinterAssembly(
        frame=frame,
        printer_feet=printer_feet,
        y_axis=y_axis,
        y_axis_drive=y_axis_drive,
        print_bed_assembly=print_bed_assembly,
        positioned_z_axes=positioned_z_axes,
        positioned_carriages=positioned_carriages,
        x_axis=x_axis,
        tool_head_mounts=tool_head_mounts,
    )


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()
    reset_metrics()
    z_animation = {"z_axis": (0, 0, z_axis_z_travel)}
    bed_animation = {"bed_y": (0, print_bed_y_travel, 0)}
    x_axis_carriage_animations = {
        carriage_name: {**z_animation, **animation}
        for carriage_name, animation in create_x_carriage_animation_map().items()
    }

    assembly = create_whole_printer()
    parts.add(assembly.frame, "printer_frame", flip=False, skip_in_production=True)

    for name, follower in assembly.printer_feet.get_named_follower_items():
        parts.add(follower, name, flip=False, skip_in_production=False)

    for name, npp in assembly.printer_feet.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    parts.add(assembly.y_axis.leader, "y_axis", flip=False, skip_in_production=True)
    # parts.add( # this is duplicated with the followers below, but keeping it here for clarity of the main assembly structure
    #     assembly.print_bed_assembly,
    #     "print_bed_undercarriage",
    #     flip=False,
    #     skip_in_production=False,
    #     animation=bed_animation,
    # )
    for name, follower in assembly.print_bed_assembly.get_named_follower_items():
        parts.add(
            follower,
            name,
            flip=False,
            skip_in_production=False,
            animation=bed_animation,
        )

    for name, npp in assembly.print_bed_assembly.get_named_non_production_part_items():
        parts.add(
            npp,
            name,
            flip=False,
            skip_in_production=True,
            animation=bed_animation,
        )

    for name, follower in assembly.y_axis.get_named_follower_items():
        animation = bed_animation if "carriage" in name else None
        parts.add(
            follower,
            name,
            flip=False,
            skip_in_production=True,
            animation=animation,
        )

    for name, npp in assembly.y_axis.get_named_non_production_part_items():
        animation = bed_animation if "carriage" in name else None
        parts.add(
            npp,
            name,
            flip=False,
            skip_in_production=True,
            animation=animation,
        )

    parts.add(
        assembly.y_axis_drive.leader,
        f"y_axis_drive_{Y_AXIS_DRIVE_LEADER_NAME}",
        flip=False,
        skip_in_production=True,
    )

    for name, follower in assembly.y_axis_drive.get_named_follower_items():
        parts.add(
            follower,
            f"y_axis_drive_{name}",
            flip=False,
            skip_in_production=True,
        )

    for name, npp in assembly.y_axis_drive.get_named_non_production_part_items():
        parts.add(
            npp,
            f"y_axis_drive_{name}",
            flip=False,
            skip_in_production=True,
        )

    for prefix, z_axis in assembly.positioned_z_axes.items():
        parts.add(z_axis, f"{prefix}_z_axis", flip=False, skip_in_production=True)

        for name, npp in z_axis.get_named_non_production_part_items():
            parts.add(npp, f"{prefix}_{name}", flip=False, skip_in_production=True)

        for name, follower in z_axis.get_named_follower_items():
            prod_rotation_angle = None
            prod_rotation_axis = None

            if "clamp" in name and "axial" not in name:
                prod_rotation_angle = 90
                prod_rotation_axis = (1, 0, 0)
            elif "pillow_bearing_mount_plate" in name:
                prod_rotation_angle = -90
                prod_rotation_axis = (1, 0, 0)

            parts.add(
                follower,
                f"{prefix}_{name}",
                flip=False,
                skip_in_production=False,
                prod_rotation_angle=prod_rotation_angle,
                prod_rotation_axis=prod_rotation_axis,
            )

    for prefix, carriage in assembly.positioned_carriages.items():
        parts.add(
            carriage,
            f"{prefix}_z_axis_carriage",
            flip=False,
            skip_in_production=False,
            animation=z_animation,
        )

        for name, follower in carriage.get_named_follower_items():
            prod_rotation_angle = None
            prod_rotation_axis = None
            if "clamp" in name:
                prod_rotation_angle = 90
                prod_rotation_axis = (1, 0, 0)

            parts.add(
                follower,
                f"{prefix}_{name}",
                flip=False,
                skip_in_production=False,
                prod_rotation_angle=prod_rotation_angle,
                prod_rotation_axis=prod_rotation_axis,
                animation=z_animation,
            )

        for name, npp in carriage.get_named_non_production_part_items():
            parts.add(
                npp,
                f"{prefix}_{name}",
                flip=False,
                skip_in_production=True,
                animation=z_animation,
            )

    for carriage_name, tool_head_mount in assembly.tool_head_mounts.items():
        parts.add(
            tool_head_mount,
            f"x_axis_tool_head_mount_{carriage_name}",
            flip=False,
            skip_in_production=True,
            prod_rotation_angle=180,
            prod_rotation_axis=(1, 0, 0),
            animation=x_axis_carriage_animations[carriage_name],
        )

        parts.add(
            tool_head_mount.get_follower_part_by_name("belt_clamp_base"),
            f"x_axis_tool_head_mount_clamp_{carriage_name}",
            flip=False,
            skip_in_production=True,
            prod_rotation_angle=90,
            prod_rotation_axis=(1, 0, 0),
            animation=x_axis_carriage_animations[carriage_name],
        )

        for name, npp in tool_head_mount.get_named_non_production_part_items():
            parts.add(
                npp,
                f"{carriage_name}_{name}",
                flip=False,
                skip_in_production=True,
                animation=x_axis_carriage_animations[carriage_name],
            )

    # parts.add(
    #     assembly.x_axis,
    #     "x_axis",
    #     flip=False,
    #     skip_in_production=True,
    #     animation=z_animation,
    # )

    already_added_names = set()
    for name, npp in assembly.x_axis.get_named_non_production_part_items():
        current_name = f"x_axis_{name}"
        already_added_names.add(current_name)
        animation = x_axis_carriage_animations.get(name, z_animation)
        parts.add(
            npp,
            current_name,
            flip=False,
            skip_in_production=True,
            animation=animation,
        )

    for name, follower in assembly.x_axis.get_named_follower_items():
        current_name = f"x_axis_{name}"
        if current_name in already_added_names:
            continue

        animation = x_axis_carriage_animations.get(name, z_animation)
        parts.add(
            follower,
            current_name,
            flip=False,
            skip_in_production=True,
            animation=animation,
        )

    log_metrics_report(_logger)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        export_stl=PROD,
        export_individual_parts=False,
        prod_gap=4,
    )

    _logger.info("whole_printer created successfully!")


if __name__ == "__main__":
    main()
