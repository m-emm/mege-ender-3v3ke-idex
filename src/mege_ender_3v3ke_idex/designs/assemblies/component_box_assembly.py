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


def create_component_box_assembly(
    *,
    inner_length,
    inner_width,
    inner_height,
    wall_thickness,
    floor_thickness,
    lid_thickness,
    lid_clearance,
    wire_cut_width,
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
        ("wire_cut_width", wire_cut_width),
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

    body = create_box(outer_length, outer_width, body_height)
    body = _fillet_box(
        body,
        fillet_radius,
        min(outer_length, outer_width, body_height, floor_thickness),
    )

    body_inner_space_cutter = create_box(inner_length, inner_width, inner_height + 1)
    body_inner_space_cutter = align(
        body_inner_space_cutter, body, Alignment.CENTER, axes=[0, 1]
    )
    body_inner_space_cutter = align(body_inner_space_cutter, body, Alignment.BOTTOM)
    body_inner_space_cutter = translate(0, 0, floor_thickness)(body_inner_space_cutter)
    body = body.cut(body_inner_space_cutter)

    wire_slit = create_box(wall_thickness + 1, wire_cut_width, inner_height / 2)
    wire_slit = align(wire_slit, body, Alignment.CENTER, axes=[1])
    wire_slit = align(wire_slit, body, Alignment.TOP)
    body = body.cut(align(wire_slit, body, Alignment.LEFT))
    body = body.cut(align(wire_slit, body, Alignment.RIGHT))

    lid = create_box(lid_outer_length, lid_outer_width, lid_outer_height)
    lid = _fillet_box(
        lid,
        fillet_radius,
        min(lid_outer_length, lid_outer_width, lid_outer_height, lid_thickness),
    )
    lid = align(lid, body, Alignment.CENTER, axes=[0])
    lid = align(lid, body, Alignment.BOTTOM)
    lid = align(lid, body, Alignment.STACK_BACK, stack_gap=hinge_gap)

    lid_inner_space_cutter = create_box(
        lid_inner_length, lid_inner_width, lid_inner_height + 1
    )
    lid_inner_space_cutter = align(
        lid_inner_space_cutter, lid, Alignment.CENTER, axes=[0, 1]
    )
    lid_inner_space_cutter = align(lid_inner_space_cutter, lid, Alignment.BOTTOM)
    lid_inner_space_cutter = translate(0, 0, lid_thickness)(lid_inner_space_cutter)
    lid = lid.cut(lid_inner_space_cutter)

    hinge = create_box(hinge_width, hinge_gap + hinge_depth, hinge_thickness)
    hinge = align(hinge, body, Alignment.CENTER, axes=[0])
    hinge = align(hinge, body, Alignment.BOTTOM)
    hinge = align(hinge, body, Alignment.STACK_BACK, stack_gap=-hinge_depth / 2)

    lid_hinge_clearance = create_box(
        hinge_width + 2 * lid_clearance,
        wall_thickness + hinge_depth + 2 * lid_clearance,
        hinge_thickness + lid_clearance + 1e-3,
    )
    lid_hinge_clearance = align(lid_hinge_clearance, hinge, Alignment.CENTER)
    lid_hinge_clearance = align(lid_hinge_clearance, lid, Alignment.FRONT)
    lid_hinge_clearance = align(lid_hinge_clearance, lid, Alignment.TOP)
    lid = lid.cut(lid_hinge_clearance)

    resistor_body = create_cylinder(RESISTOR_BODY_DIAMETER / 2, RESISTOR_BODY_LENGTH)
    resistor_body = rotate(90, axis=(0, 1, 0))(resistor_body)
    resistor_body = align(resistor_body, body, Alignment.CENTER)
    resistor_body = align(resistor_body, body, Alignment.TOP)

    resistor_wire = create_cylinder(RESISTOR_WIRE_DIAMETER / 2, RESISTOR_WIRE_LENGTH)
    resistor_wire = rotate(90, axis=(0, 1, 0))(resistor_wire)
    resistor_wire = align(resistor_wire, resistor_body, Alignment.CENTER)

    resistor_visual = resistor_wire.fuse(resistor_body)

    component_box = body.fuse(lid).fuse(hinge)

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
