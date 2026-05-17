"""Reusable one-piece TPU component box assembly."""

import logging
import os
import subprocess
import sys
from pathlib import Path

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"


def _validate_positive(name, value):
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _fillet_box(part, fillet_radius, smallest_dimension):
    if fillet_radius <= 0:
        return part

    effective_fillet_radius = min(fillet_radius, smallest_dimension / 3)
    if effective_fillet_radius <= 0:
        return part

    return apply_fillet_by_alignment(
        part,
        effective_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )


def create_component_box_assembly(
    *,
    inner_length,
    inner_width,
    inner_height,
    wall_thickness,
    floor_thickness,
    lid_thickness,
    fillet_radius,
    hinge_gap,
    hinge_width,
    hinge_depth,
    hinge_thickness,
):
    """Create a one-piece open TPU box with tray, lid, and ribbon hinge."""

    for name, value in [
        ("inner_length", inner_length),
        ("inner_width", inner_width),
        ("inner_height", inner_height),
        ("wall_thickness", wall_thickness),
        ("floor_thickness", floor_thickness),
        ("lid_thickness", lid_thickness),
        ("hinge_width", hinge_width),
        ("hinge_depth", hinge_depth),
        ("hinge_thickness", hinge_thickness),
    ]:
        _validate_positive(name, value)

    if hinge_gap < 0:
        raise ValueError("hinge_gap must not be negative")
    if fillet_radius < 0:
        raise ValueError("fillet_radius must not be negative")

    outer_length = inner_length + 2 * wall_thickness
    outer_width = inner_width + 2 * wall_thickness
    body_height = inner_height + floor_thickness

    if hinge_width > outer_length:
        raise ValueError("hinge_width must not exceed the box outer length")

    body = create_box(outer_length, outer_width, body_height)
    body = _fillet_box(
        body,
        fillet_radius,
        min(outer_length, outer_width, body_height, wall_thickness, floor_thickness),
    )

    cavity = create_box(
        inner_length,
        inner_width,
        inner_height + wall_thickness,
        origin=(wall_thickness, wall_thickness, floor_thickness),
    )
    body = body.cut(cavity)

    lid_y = outer_width + hinge_gap
    lid = create_box(
        outer_length,
        outer_width,
        lid_thickness,
        origin=(0, lid_y, 0),
    )
    lid = _fillet_box(
        lid,
        fillet_radius,
        min(outer_length, outer_width, lid_thickness),
    )

    hinge_x = (outer_length - hinge_width) / 2
    hinge_y = outer_width - hinge_depth / 2
    hinge = create_box(
        hinge_width,
        hinge_gap + hinge_depth,
        hinge_thickness,
        origin=(hinge_x, hinge_y, 0),
    )

    component_box = body.fuse(lid).fuse(hinge)

    resistor_visual = create_box(
        inner_length,
        inner_width,
        inner_height,
        origin=(wall_thickness, wall_thickness, floor_thickness),
    )

    assembly = LeaderFollowersCuttersPart(component_box)
    assembly.add_named_non_production_part(resistor_visual, "resistor_visual")
    return assembly


def main():
    logging.basicConfig(level=logging.INFO)

    repo_root = Path(__file__).resolve().parents[4]
    command = [
        sys.executable,
        "-m",
        "shellforgepy",
        "build",
        "assembling/assemblies/assemblies.yaml",
        "--assembly",
        "resistor_box_assembly",
        "--visualize",
    ]
    if PROD:
        command.append("--production")

    subprocess.run(command, check=True, cwd=repo_root)


if __name__ == "__main__":
    main()
