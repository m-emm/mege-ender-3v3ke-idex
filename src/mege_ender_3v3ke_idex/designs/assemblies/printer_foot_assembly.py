"""
Printer Foot Assembly

Usage:
    cd <project_root> && ./run.sh path/to/printer_foot_assembly.py
    # Delegates to the builder-based printer_foot_assembly manifest.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_screw_mount_assembly,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"


stablilization_slit_thickness = 0.1

def create_printer_foot_assembly(
    *,
    printer_foot_height,
    printer_foot_base_size,
    printer_foot_top_size,
    printer_foot_screw_length,
    printer_foot_screw_cylinder_head_clearance,
    printer_foot_mount_screw_size,
    printer_foot_mount_screw_sink,
    printer_foot_groove_filler_width,
    printer_foot_groove_filler_thickness,
    tpu_slit_thickness,
    tpu_slit_clearance,
    tpu_slit_distance,
    tpu_num_slits,
):
    """Create a single printer foot assembly."""

    foot = create_pyramid_stump(
        printer_foot_base_size,
        printer_foot_top_size,
        printer_foot_base_size,
        printer_foot_top_size,
        printer_foot_height,
    )

    
    
    

    foot = rotate(180, axis=(1, 0, 0))(foot)

    screw_mount_assembly = create_screw_mount_assembly(
        foot,
        printer_foot_mount_screw_size,
        printer_foot_screw_length,
        screw_direction=Alignment.BOTTOM,
        with_nut_cutter=False,
        cylinder_head_cutter_clearance=printer_foot_screw_cylinder_head_clearance,
        flush_with_top=True,
        top_sink=printer_foot_mount_screw_sink,
    )
    foot = screw_mount_assembly.use_as_cutter_on(foot)

    slit_height = (
        printer_foot_screw_length
        - 2 * tpu_slit_clearance
        - printer_foot_mount_screw_sink
    )

    for i in range(tpu_num_slits):
        radius = (
            MScrew.from_size(printer_foot_mount_screw_size).clearance_hole_loose / 2
            + i * tpu_slit_distance
        )

        slit = create_ring(
            outer_radius=radius + tpu_slit_thickness / 2,
            inner_radius=radius - tpu_slit_thickness / 2,
            height=slit_height,
        )

        slit = align(slit, foot, Alignment.CENTER)
        slit = align(slit, foot, Alignment.TOP)
        slit = translate(0, 0, -tpu_slit_clearance)(slit)
        foot = foot.cut(slit)


    stablization_slit_cutter = create_box(printer_foot_base_size / 7, stablilization_slit_thickness, printer_foot_height - 4)
    stablization_slit_turned = rotate(90)(stablization_slit_cutter)
    stablization_slit_turned = align(stablization_slit_turned, stablization_slit_cutter, Alignment.CENTER)

    stablization_slit_cutter = stablization_slit_cutter.fuse(stablization_slit_turned)
    stablization_slit_cutter = rotate(45)(stablization_slit_cutter)


    slit_cutters = PartCollector()
    for slit_alignment in [Alignment.STACK_FRONT, Alignment.STACK_BACK, Alignment.STACK_LEFT, Alignment.STACK_RIGHT]:
        slit_cutter = align(stablization_slit_cutter, foot, Alignment.CENTER)
        slit_cutter = align(slit_cutter, screw_mount_assembly.cutters[0], slit_alignment, stack_gap= 3)

        slit_cutter_limiter = create_cylinder (MScrew.from_size(printer_foot_mount_screw_size).clearance_hole_loose / 2 + 3,500)
        slit_cutter_limiter = align(slit_cutter_limiter, foot, Alignment.CENTER)
        slit_cutter = slit_cutter.cut(slit_cutter_limiter)
                                                                        

        foot = foot.cut(slit_cutter)
        slit_cutters = slit_cutters.fuse(slit_cutter)

        

    ratio = ((printer_foot_base_size - printer_foot_top_size) / 2) / printer_foot_height

    groove_filler = create_pyramid_stump(
        printer_foot_groove_filler_width,
        printer_foot_groove_filler_width,
        printer_foot_base_size,
        printer_foot_base_size + (2 * ratio * printer_foot_groove_filler_thickness),
        printer_foot_groove_filler_thickness,
    )

    groove_filler = align(groove_filler, foot, Alignment.CENTER)
    groove_filler = align(groove_filler, foot, Alignment.STACK_TOP)
    groove_filler = screw_mount_assembly.use_as_cutter_on(groove_filler)

    foot = foot.fuse(groove_filler)

    retval = LeaderFollowersCuttersPart(leader=foot)
    retval = retval.merge_except_leader(screw_mount_assembly)
    retval.add_named_non_production_part(slit_cutters, "stablization_slits")
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
        "printer_foot_assembly",
        "--visualize",
    ]
    if PROD:
        command.append("--production")

    subprocess.run(command, check=True, cwd=repo_root)


if __name__ == "__main__":
    main()
