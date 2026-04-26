import os
import subprocess
import sys
from pathlib import Path

from shellforgepy.simple import *

PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"
creality_psu_width = 114.7
creality_psu_length = 215
creality_psu_height = 29.7
creality_psu_sheet_metal_thickness = 2
creality_psu_front_cutout_depth = 15.2
creality_psu_num_cable_clamps = 9
creality_psu_cable_clamp_width_one_wall = 85.5 / creality_psu_num_cable_clamps
creality_psu_cable_clamp_wall = 1.4
creality_psu_cable_clamp_depth = 18.3
creality_psu_cable_clamp_height = 14.1
creality_psu_cable_clamp_height_at_front = 7
creality_psu_cable_clamp_right_gap = 3.4
creality_psu_cable_clamp_front_gap = 0.7
creality_psu_cable_clamp_flight_height = 6
creality_psu_mount_screw_size = "M4"
creality_psu_mount_screw_hole_depth = 3
creality_psu_mount_screw_hole_inset = 32.3
creality_psu_mount_screw_hole_z_offset_from_bottom = 12


def create_creality_psu_assembly(
    *,
    psu_mount_screw_length,
    psu_mount_screw_cylinder_head_clearance,
    psu_mount_wall_thickness,
    psu_mount_base_thickness,
    psu_mount_electrics_box_width,
    psu_mount_electrics_box_depth,
    psu_mount_electrics_box_height,
    psu_mount_cable_hole_diameter,
    psu_mount_cable_clamp_length,
    psu_mount_cable_clamp_width,
    psu_mount_cable_clamp_clamp_screw_size,
    psu_mount_cable_clamp_clamp_screw_length,
):
    """Create a Creality PSU assembly."""

    psu_body = create_box(creality_psu_width, creality_psu_length, creality_psu_height)

    psu_inner_cutter = create_box(
        creality_psu_width - 2 * creality_psu_sheet_metal_thickness,
        creality_psu_length - creality_psu_sheet_metal_thickness,
        creality_psu_height - 2 * creality_psu_sheet_metal_thickness,
    )
    psu_inner_cutter = align(psu_inner_cutter, psu_body, Alignment.CENTER)
    psu_inner_cutter = align(psu_inner_cutter, psu_body, Alignment.FRONT)
    psu_body = psu_body.cut(psu_inner_cutter)

    psu_front_cutout_cutter = create_box(
        creality_psu_width - 2 * creality_psu_sheet_metal_thickness,
        creality_psu_front_cutout_depth,
        2 * creality_psu_sheet_metal_thickness,
    )
    psu_front_cutout_cutter = align(psu_front_cutout_cutter, psu_body, Alignment.CENTER)
    psu_front_cutout_cutter = align(psu_front_cutout_cutter, psu_body, Alignment.FRONT)
    psu_front_cutout_cutter = align(psu_front_cutout_cutter, psu_body, Alignment.TOP)
    psu_body = psu_body.cut(psu_front_cutout_cutter)

    psu_electrics_box = create_box(
        psu_mount_electrics_box_width,
        psu_mount_electrics_box_depth,
        psu_mount_electrics_box_height,
    )

    psu_electrics_box = align(psu_electrics_box, psu_body, Alignment.CENTER)
    psu_electrics_box = align(psu_electrics_box, psu_body, Alignment.STACK_FRONT)
    psu_electrics_box = align(psu_electrics_box, psu_body, Alignment.BOTTOM)

    mount_screw_holes = []
    mount_screw_hole_collector = PartCollector()
    mount_screw_hole_radius = (
        MScrew.from_size(creality_psu_mount_screw_size).clearance_hole_normal / 2
    )
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            mount_screw_hole = create_cylinder(
                mount_screw_hole_radius,
                creality_psu_mount_screw_hole_depth,
            )
            mount_screw_hole = rotate(90, axis=(0, 1, 0))(mount_screw_hole)
            mount_screw_hole = align(mount_screw_hole, psu_body, Alignment.CENTER)
            mount_screw_hole = align(mount_screw_hole, psu_body, Alignment.EDGE_BOTTOM)
            mount_screw_hole = align(mount_screw_hole, psu_body, fb.edge_alignment)
            mount_screw_hole = align(
                mount_screw_hole,
                psu_body,
                lr.stack_alignment,
                stack_gap=-creality_psu_mount_screw_hole_depth,
            )
            mount_screw_hole = translate(
                0,
                -fb.sign * creality_psu_mount_screw_hole_inset,
                creality_psu_mount_screw_hole_z_offset_from_bottom,
            )(mount_screw_hole)
            mount_screw_hole_collector = mount_screw_hole_collector.fuse(
                mount_screw_hole
            )
            mount_screw_holes.append((lr, fb, mount_screw_hole))

    bottom_mount_screw_holes = []
    bottom_mount_screw_hole_collector = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            bottom_mount_screw_hole = create_cylinder(
                mount_screw_hole_radius,
                creality_psu_mount_screw_hole_depth,
            )
            bottom_mount_screw_hole = align(
                bottom_mount_screw_hole,
                psu_body,
                Alignment.CENTER,
            )
            bottom_mount_screw_hole = align(
                bottom_mount_screw_hole,
                psu_body,
                Alignment.EDGE_BOTTOM,
            )
            bottom_mount_screw_hole = align(
                bottom_mount_screw_hole,
                psu_body,
                lr.edge_alignment,
            )
            bottom_mount_screw_hole = align(
                bottom_mount_screw_hole,
                psu_body,
                fb.edge_alignment,
            )
            bottom_mount_screw_hole = translate(
                -lr.sign * creality_psu_mount_screw_hole_inset,
                -fb.sign * creality_psu_mount_screw_hole_inset,
                0,
            )(bottom_mount_screw_hole)

            bottom_mount_screw_hole_collector = bottom_mount_screw_hole_collector.fuse(
                bottom_mount_screw_hole
            )
            bottom_mount_screw_holes.append((lr, fb, bottom_mount_screw_hole))

    psu_body = psu_body.cut(mount_screw_hole_collector)
    psu_body = psu_body.cut(bottom_mount_screw_hole_collector)

    cable_clamps = create_box(
        creality_psu_num_cable_clamps * creality_psu_cable_clamp_width_one_wall
        + creality_psu_cable_clamp_wall,
        creality_psu_cable_clamp_depth,
        creality_psu_cable_clamp_height,
    )

    cable_clamp_cutter = PartCollector()
    for i in range(creality_psu_num_cable_clamps):
        cutter = create_box(
            creality_psu_cable_clamp_width_one_wall - creality_psu_cable_clamp_wall,
            creality_psu_cable_clamp_depth - creality_psu_cable_clamp_wall,
            creality_psu_cable_clamp_height_at_front,
        )
        cutter = translate(i * creality_psu_cable_clamp_width_one_wall, 0, 0)(cutter)
        cable_clamp_cutter = cable_clamp_cutter.fuse(cutter)

    cable_clamp_cutter = align(cable_clamp_cutter, cable_clamps, Alignment.CENTER)
    cable_clamp_cutter = align(cable_clamp_cutter, cable_clamps, Alignment.TOP)
    cable_clamp_cutter = align(cable_clamp_cutter, cable_clamps, Alignment.FRONT)

    cable_clamps = cable_clamps.cut(cable_clamp_cutter)
    cable_clamps = align(cable_clamps, psu_body, Alignment.CENTER)
    cable_clamps = align(cable_clamps, psu_body, Alignment.BOTTOM)
    cable_clamps = align(cable_clamps, psu_body, Alignment.FRONT)
    cable_clamps = align(cable_clamps, psu_body, Alignment.RIGHT)
    cable_clamps = translate(
        -creality_psu_sheet_metal_thickness - creality_psu_cable_clamp_right_gap,
        creality_psu_cable_clamp_front_gap,
        creality_psu_cable_clamp_flight_height,
    )(cable_clamps)

    retval = LeaderFollowersCuttersPart(leader=psu_electrics_box)
    retval.add_named_non_production_part(psu_body, "psu_body")
    retval.add_named_non_production_part(cable_clamps, "cable_clamps")
    for lr, fb, mount_screw_hole in mount_screw_holes:
        retval.add_named_cutter(
            mount_screw_hole,
            f"mount_screw_hole_{lr.name.lower()}_{fb.name.lower()}",
        )
    for lr, fb, bottom_mount_screw_hole in bottom_mount_screw_holes:
        retval.add_named_cutter(
            bottom_mount_screw_hole,
            f"bottom_mount_screw_hole_{lr.name.lower()}_{fb.name.lower()}",
        )

    return retval


def main():
    repo_root = Path(__file__).resolve().parents[4]
    command = [
        sys.executable,
        "-m",
        "shellforgepy",
        "build",
        "assembling/assemblies/assemblies.yaml",
        "--assembly",
        "creality_psu_assembly",
        "--visualize",
    ]
    if PROD:
        command.append("--production")

    subprocess.run(command, check=True, cwd=repo_root)


if __name__ == "__main__":
    main()
