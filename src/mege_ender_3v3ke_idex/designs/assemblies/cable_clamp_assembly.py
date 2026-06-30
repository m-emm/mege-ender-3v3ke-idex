"""Reusable Creality-style cable clamp assembly."""

from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_screw_mount_assembly,
)
from shellforgepy.simple import *


def create_cable_clamp_assembly(
    *,
    cable_clamp_hole_diameter,
    cable_clamp_slit_width,
    cable_clamp_arm_width,
    cable_clamp_arm_depth,
    cable_clamp_arm_thickness,
    cable_clamp_clearance,
    cable_clamp_screw_size,
    cable_clamp_screw_length,
    BIG_THING,
):
    """Create a standalone cable holder with bore, slit, and tightening screw."""

    cable_holder = create_box(
        cable_clamp_arm_depth,
        cable_clamp_hole_diameter + 2 * cable_clamp_arm_width,
        cable_clamp_arm_thickness,
    )

    cable_hole_reference = create_cylinder(
        cable_clamp_hole_diameter / 2,
        cable_clamp_arm_thickness,
    )

    cable_hole_offset_reference = create_box(
        cable_clamp_hole_diameter,
        cable_clamp_hole_diameter,
        cable_clamp_arm_thickness,
    )
    cable_hole_offset_reference = align(
        cable_hole_offset_reference,
        cable_hole_reference,
        Alignment.CENTER,
        axes=[1, 2],
    )
    cable_hole_offset_reference = align(
        cable_hole_offset_reference,
        cable_hole_reference,
        Alignment.STACK_LEFT,
    )

    cable_holder = align(cable_holder, cable_hole_reference, Alignment.CENTER)
    cable_holder = align(cable_holder, cable_hole_reference, Alignment.LEFT)
    cable_holder = align(
        cable_holder,
        cable_hole_offset_reference,
        Alignment.LEFT,
    )

    cable_hole_cutter = create_cylinder(
        cable_clamp_hole_diameter / 2,
        BIG_THING,
    )
    cable_hole_cutter = align(
        cable_hole_cutter,
        cable_hole_reference,
        Alignment.CENTER,
    )
    cable_hole_cutter = align(
        cable_hole_cutter,
        cable_holder,
        Alignment.CENTER,
        axes=[2],
    )
    cable_holder = cable_holder.cut(cable_hole_cutter)

    cable_slit_cutter = create_filleted_box(
        BIG_THING,
        cable_clamp_slit_width,
        BIG_THING,
        fillet_radius=cable_clamp_slit_width / 3,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    cable_slit_cutter = align(cable_slit_cutter, cable_holder, Alignment.CENTER)
    cable_slit_cutter = align(
        cable_slit_cutter,
        cable_holder,
        Alignment.STACK_RIGHT,
        stack_gap=-cable_clamp_arm_depth + cable_clamp_hole_diameter / 2,
    )
    cable_holder = cable_holder.cut(cable_slit_cutter)

    screw_reference = create_box(
        2 * cable_clamp_hole_diameter,
        cable_clamp_hole_diameter + 2 * cable_clamp_arm_width,
        cable_clamp_arm_thickness,
    )
    screw_reference = align(screw_reference, cable_holder, Alignment.CENTER)
    screw_reference = align(screw_reference, cable_holder, Alignment.RIGHT)

    screw_assembly = create_screw_mount_assembly(
        screw_reference,
        cable_clamp_screw_size,
        cable_clamp_screw_length,
        Alignment.BACK,
        flush_with_top=True,
    )
    cable_holder = screw_assembly.use_as_cutter_on(cable_holder)

    clearance_cutter = materialize_bounding_box(
        cable_holder,
        x_enlargement=2 * cable_clamp_clearance,
        y_enlargement=2 * cable_clamp_clearance,
        z_enlargement=2 * cable_clamp_clearance,
    )

    assembly = LeaderFollowersCuttersPart(leader=cable_holder)
    assembly.add_named_cutter(cable_hole_cutter, "cable_hole_cutter")
    assembly.add_named_cutter(cable_slit_cutter, "cable_slit_cutter")
    assembly.add_named_cutter(clearance_cutter, "clearance_cutter")
    for name, cutter in screw_assembly.get_named_cutter_items():
        assembly.add_named_cutter(cutter, f"tightening_screw_{name}")
    assembly.add_named_non_production_part(
        screw_assembly.get_named_non_production_part("screw"),
        "tightening_screw",
    )

    return assembly
