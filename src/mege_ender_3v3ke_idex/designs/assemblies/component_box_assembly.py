"""Reusable one-piece TPU component box assembly."""

import logging
import os
import subprocess
import sys
from pathlib import Path

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

RESISTOR_BODY_DIAMETER = 2.5
RESISTOR_BODY_LENGTH = 7
RESISTOR_WIRE_LENGTH = 30
RESISTOR_WIRE_DIAMETER = 0.5


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


def _create_hollow_box(
    *,
    outer_length,
    outer_width,
    outer_height,
    inner_length,
    inner_width,
    inner_height,
    bottom_thickness,
    origin=(0, 0, 0),
    fillet_radius=0,
):
    box = create_box(outer_length, outer_width, outer_height, origin=origin)
    box = _fillet_box(
        box,
        fillet_radius,
        min(outer_length, outer_width, outer_height, bottom_thickness),
    )

    inner_origin = (
        origin[0] + (outer_length - inner_length) / 2,
        origin[1] + (outer_width - inner_width) / 2,
        origin[2] + bottom_thickness,
    )
    cutter = create_box(
        inner_length,
        inner_width,
        inner_height + bottom_thickness,
        origin=inner_origin,
    )
    return box.cut(cutter)


def _create_resistor_visual(*, center):
    body_start = (center[0] - RESISTOR_BODY_LENGTH / 2, center[1], center[2])
    wire_start = (center[0] - RESISTOR_WIRE_LENGTH / 2, center[1], center[2])

    body = directed_cylinder_at(
        body_start,
        direction=(1, 0, 0),
        radius=RESISTOR_BODY_DIAMETER / 2,
        height=RESISTOR_BODY_LENGTH,
    )
    wire = directed_cylinder_at(
        wire_start,
        direction=(1, 0, 0),
        radius=RESISTOR_WIRE_DIAMETER / 2,
        height=RESISTOR_WIRE_LENGTH,
    )
    return body.fuse(wire)


def _cut_lid_hinge_clearance(
    lid,
    *,
    lid_origin,
    lid_outer_height,
    wall_thickness,
    hinge_x,
    hinge_width,
    hinge_depth,
    hinge_thickness,
    lid_clearance,
):
    cutout_width = hinge_width + 2 * lid_clearance
    cutout_depth = wall_thickness + hinge_depth + 2 * lid_clearance
    cutout_height = hinge_thickness + lid_clearance
    cutout_z = lid_outer_height - cutout_height

    cutout = create_box(
        cutout_width,
        cutout_depth,
        cutout_height + 1e-3,
        origin=(
            hinge_x - lid_clearance,
            lid_origin[1] - lid_clearance,
            lid_origin[2] + cutout_z,
        ),
    )
    return lid.cut(cutout)


def create_component_box_assembly(
    *,
    inner_length,
    inner_width,
    inner_height,
    wall_thickness,
    floor_thickness,
    lid_thickness,
    lid_clearance,
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
        ("lid_clearance", lid_clearance),
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
    lid_inner_length = outer_length + 2 * lid_clearance
    lid_inner_width = outer_width + 2 * lid_clearance
    lid_inner_height = body_height + lid_clearance
    lid_outer_length = lid_inner_length + 2 * wall_thickness
    lid_outer_width = lid_inner_width + 2 * wall_thickness
    lid_outer_height = lid_inner_height + lid_thickness

    if hinge_width > outer_length:
        raise ValueError("hinge_width must not exceed the box outer length")

    if RESISTOR_WIRE_LENGTH > inner_length:
        raise ValueError("inner_length must fit the resistor wire visual")
    if RESISTOR_BODY_DIAMETER > min(inner_width, inner_height):
        raise ValueError(
            "inner_width and inner_height must fit the resistor body visual"
        )

    body = _create_hollow_box(
        outer_length=outer_length,
        outer_width=outer_width,
        outer_height=body_height,
        inner_length=inner_length,
        inner_width=inner_width,
        inner_height=inner_height,
        bottom_thickness=floor_thickness,
        fillet_radius=fillet_radius,
    )

    lid_y = outer_width + hinge_gap
    lid_origin = ((outer_length - lid_outer_length) / 2, lid_y, 0)
    lid = _create_hollow_box(
        outer_length=lid_outer_length,
        outer_width=lid_outer_width,
        outer_height=lid_outer_height,
        inner_length=lid_inner_length,
        inner_width=lid_inner_width,
        inner_height=lid_inner_height,
        bottom_thickness=lid_thickness,
        origin=lid_origin,
        fillet_radius=fillet_radius,
    )

    hinge_x = (outer_length - hinge_width) / 2
    lid = _cut_lid_hinge_clearance(
        lid,
        lid_origin=lid_origin,
        lid_outer_height=lid_outer_height,
        wall_thickness=wall_thickness,
        hinge_x=hinge_x,
        hinge_width=hinge_width,
        hinge_depth=hinge_depth,
        hinge_thickness=hinge_thickness,
        lid_clearance=lid_clearance,
    )

    hinge_y = outer_width - hinge_depth / 2
    hinge = create_box(
        hinge_width,
        hinge_gap + hinge_depth,
        hinge_thickness,
        origin=(hinge_x, hinge_y, 0),
    )

    component_box = body.fuse(lid).fuse(hinge)

    resistor_visual = _create_resistor_visual(
        center=(
            wall_thickness + inner_length / 2,
            wall_thickness + inner_width / 2,
            floor_thickness + inner_height / 2,
        )
    )

    assembly = LeaderFollowersCuttersPart(component_box)
    assembly.add_named_non_production_part(resistor_visual, "resistor_visual")
    assembly.add_named_non_production_part(lid, "lid_closing_preview")
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
