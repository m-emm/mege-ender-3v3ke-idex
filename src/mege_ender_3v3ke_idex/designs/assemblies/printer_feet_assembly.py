"""
Printer Feet Assembly

Usage:
    cd <project_root> && ./run.sh path/to/printer_feet_assembly.py
    # Delegates to the builder-based printer_feet_assembly manifest.
"""

import copy
import logging
import os
from pathlib import Path
import subprocess
import sys

from mege_3devops.process_data.mender3.process_data_04_high_speed import (
    PROCESS_DATA_TPU_04_HS,
)
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_screw_mount_assembly,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_TPU_04_HS)
PROCESS_DATA["process_overrides"].update(
    {
        "brim_type": "no_brim",
    }
)


def create_printer_feet_assembly(
    *,
    frame,
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
    """Create the printer feet assembly aligned to an injected printer frame."""

    retval = LeaderFollowersCuttersPart(PartCollector())
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            foot = create_pyramid_stump(
                printer_foot_base_size,
                printer_foot_top_size,
                printer_foot_base_size,
                printer_foot_top_size,
                printer_foot_height,
            )
            foot = rotate(180, axis=(1, 0, 0))(foot)

            foot = align(foot, frame, lr)
            foot = align(foot, frame, fb)
            foot = align(foot, frame, Alignment.STACK_BOTTOM)

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
            foot_assembly = LeaderFollowersCuttersPart(foot)
            foot_assembly = foot_assembly.merge_except_leader(screw_mount_assembly)
            foot_assembly = foot_assembly.prefixed_copy(
                f"printer_foot_{lr.name.lower()}_{fb.name.lower()}"
            )

            slit_height = (
                printer_foot_screw_length
                - 2 * tpu_slit_clearance
                - printer_foot_mount_screw_sink
            )

            for i in range(tpu_num_slits):
                radius = (
                    MScrew.from_size(printer_foot_mount_screw_size).clearance_hole_loose
                    / 2
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

            ratio = (
                (printer_foot_base_size - printer_foot_top_size)
                / 2
                / printer_foot_height
            )

            groove_filler = create_pyramid_stump(
                printer_foot_groove_filler_width,
                printer_foot_groove_filler_width,
                printer_foot_base_size,
                printer_foot_base_size
                + (2 * ratio * printer_foot_groove_filler_thickness),
                printer_foot_groove_filler_thickness,
            )

            groove_filler = align(groove_filler, foot, Alignment.CENTER)
            groove_filler = align(groove_filler, foot, Alignment.STACK_TOP)
            groove_filler = screw_mount_assembly.use_as_cutter_on(groove_filler)

            foot = foot.fuse(groove_filler)

            retval = retval.fuse(foot_assembly)
            retval.add_named_follower(foot, f"foot_{lr.name.lower()}_{fb.name.lower()}")

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
        "printer_feet_assembly",
        "--visualize",
    ]
    if PROD:
        command.append("--production")

    subprocess.run(command, check=True, cwd=repo_root)


if __name__ == "__main__":
    main()
