import os
import subprocess
import sys
from pathlib import Path

from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (  # noqa: F401
    create_screw_mount_assembly,
)
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
creality_psu_cable_clamp_depth = 14.5
creality_psu_cable_clamp_height = 14.1
creality_psu_cable_clamp_height_at_front = 7
creality_psu_cable_clamp_right_gap = 3.4
creality_psu_cable_clamp_front_gap = 0.7
creality_psu_cable_clamp_flight_height = 6
creality_psu_mount_screw_size = "M4"
creality_psu_mount_screw_hole_depth = 3
creality_psu_mount_screw_hole_inset = 32.3
creality_psu_mount_screw_hole_z_offset_from_bottom = 12
creality_psu_cable_clamp_lid_thickness = 2.9
creality_psu_cable_clamp_lid_depth = 12


def create_creality_psu_assembly(
    *,
    frame,
    psu_mount_screw_length,
    psu_mount_screw_cylinder_head_clearance,
    psu_mount_wall_thickness,
    psu_mount_base_thickness,
    psu_mount_electrics_box_width,
    psu_mount_electrics_box_depth,
    psu_mount_electrics_box_height,
    psu_mount_electrics_box_wall_thickness,
    psu_mount_electrics_box_depth_overlap,
    psu_mount_electrics_box_low_voltage_window_width,
    psu_mount_electrics_box_low_voltage_window_depth,
    psu_mount_cable_clamp_length,
    psu_mount_cable_clamp_width,
    psu_mount_cable_clamp_clamp_screw_size,
    psu_mount_cable_clamp_clamp_screw_length,
    BIG_THING,
):
    """Create a Creality PSU assembly."""

    psu_mount_electrics_box_psu_clearance = 0.5
    psu_mount_cable_camps_top_extra_clearance = 4
    psu_mount_eye_screw_size = "M5"
    cable_hole_diameter = 9
    cable_holder_hole_diameter = 5
    cable_holder_slit_width = 2.5
    cable_holder_arm_thickness = 7
    cable_holder_arm_depth = 22
    cable_holder_tightner_screw_size = "M3"
    cable_holder_tightner_screw_length = 10
    cable_holder_wall_clearance = 1.2
    cable_hole_x_inset = 16
    cable_hole_y_inset = 12
    cable_holder_arm_width = 3.5

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

    # Mount screw hole parameters
    mount_screw_hole_radius = (
        MScrew.from_size(creality_psu_mount_screw_size).clearance_hole_normal / 2
    )
    mount_screw_core_hole_radius = (
        MScrew.from_size(creality_psu_mount_screw_size).core_hole / 2
    )

    # Define hole positions with their properties:
    # (hole_type, lr_alignment, fb_alignment)
    # hole_type: "side" = X-axis oriented (rotated 90° around Y)
    #            "bottom" = Z-axis oriented (upright)
    hole_specs = []
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            hole_specs.append(("side", lr, fb))
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            hole_specs.append(("bottom", lr, fb))

    # Collect all core bores to cut the PSU body
    core_bore_collector = PartCollector()
    # Store clearance holes for cutting the electrics box
    clearance_holes = []

    for hole_type, lr, fb in hole_specs:
        # Create and position core bore
        core_bore = create_cylinder(mount_screw_core_hole_radius, BIG_THING)

        if hole_type == "side":
            # Side holes: X-axis oriented (rotate 90° around Y axis)
            core_bore = rotate(90, axis=(0, 1, 0))(core_bore)
            core_bore = align(core_bore, psu_body, Alignment.CENTER)
            core_bore = align(
                core_bore,
                psu_body,
                lr.stack_alignment,
                stack_gap=-creality_psu_mount_screw_hole_depth,
            )
            core_bore = align(core_bore, psu_body, Alignment.EDGE_BOTTOM)
            core_bore = align(core_bore, psu_body, fb.edge_alignment)
            core_bore = align(
                core_bore,
                psu_body,
                lr.stack_alignment,
                stack_gap=-creality_psu_mount_screw_hole_depth,
            )
            core_bore = translate(
                0,
                -fb.sign * creality_psu_mount_screw_hole_inset,
                creality_psu_mount_screw_hole_z_offset_from_bottom,
            )(core_bore)
        else:
            # Bottom holes: Z-axis oriented (upright)
            core_bore = align(core_bore, psu_body, Alignment.CENTER)
            core_bore = align(
                core_bore,
                psu_body,
                Alignment.STACK_BOTTOM,
                stack_gap=-creality_psu_mount_screw_hole_depth,
            )
            core_bore = align(core_bore, psu_body, lr.edge_alignment)
            core_bore = align(core_bore, psu_body, fb.edge_alignment)
            core_bore = translate(
                -lr.sign * creality_psu_mount_screw_hole_inset,
                -fb.sign * creality_psu_mount_screw_hole_inset,
                0,
            )(core_bore)

        core_bore_collector = core_bore_collector.fuse(core_bore)

        # Create and position clearance hole (same position as core bore)
        clearance_hole = create_cylinder(mount_screw_hole_radius, BIG_THING)

        if hole_type == "side":
            # Side clearance holes: same X-axis orientation
            clearance_hole = rotate(90, axis=(0, 1, 0))(clearance_hole)
            clearance_hole = align(clearance_hole, core_bore, Alignment.CENTER)
            clearance_hole = align(clearance_hole, psu_body, lr.stack_alignment)
        else:
            # Bottom clearance holes: align to core bore position
            clearance_hole = align(clearance_hole, core_bore, Alignment.CENTER)

        clearance_holes.append((hole_type, lr, fb, clearance_hole))

    # Cut all core bores into the PSU body
    psu_body = psu_body.cut(core_bore_collector)

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

    cable_clamps_lid = create_box(
        creality_psu_num_cable_clamps * creality_psu_cable_clamp_width_one_wall
        + creality_psu_cable_clamp_wall,
        creality_psu_cable_clamp_lid_depth,
        creality_psu_cable_clamp_lid_thickness,
    )
    cable_clamps_lid = align(cable_clamps_lid, cable_clamps, Alignment.CENTER)
    cable_clamps_lid = align(cable_clamps_lid, cable_clamps, Alignment.FRONT)
    cable_clamps_lid = align(cable_clamps_lid, cable_clamps, Alignment.STACK_TOP)

    psu_electrics_box = create_box(
        creality_psu_width
        + 2 * psu_mount_electrics_box_wall_thickness
        + 2 * psu_mount_electrics_box_psu_clearance,
        psu_mount_electrics_box_depth,
        creality_psu_height
        + 2 * psu_mount_electrics_box_wall_thickness
        + 2 * psu_mount_electrics_box_psu_clearance
        + psu_mount_cable_camps_top_extra_clearance,
    )

    low_voltage_window_cutter = create_box(
        psu_mount_electrics_box_low_voltage_window_width,
        psu_mount_electrics_box_low_voltage_window_depth,
        psu_mount_electrics_box_wall_thickness
        + psu_mount_electrics_box_psu_clearance
        + psu_mount_cable_camps_top_extra_clearance,
    )
    low_voltage_window_cutter = align(
        low_voltage_window_cutter, psu_electrics_box, Alignment.LEFT
    )
    low_voltage_window_cutter = align(
        low_voltage_window_cutter, psu_electrics_box, Alignment.FRONT
    )
    low_voltage_window_cutter = align(
        low_voltage_window_cutter, psu_electrics_box, Alignment.TOP
    )
    low_voltage_window_cutter = translate(
        psu_mount_electrics_box_wall_thickness,
        psu_mount_electrics_box_wall_thickness,
        0,
    )(low_voltage_window_cutter)

    psu_electrics_box_inner_cutter = create_box(
        creality_psu_width + 2 * psu_mount_electrics_box_psu_clearance,
        psu_mount_electrics_box_depth - psu_mount_electrics_box_wall_thickness,
        creality_psu_height + 2 * psu_mount_electrics_box_psu_clearance,
    )
    psu_electrics_box_inner_cutter = align(
        psu_electrics_box_inner_cutter, psu_electrics_box, Alignment.CENTER
    )
    psu_electrics_box_inner_cutter = align(
        psu_electrics_box_inner_cutter, psu_electrics_box, Alignment.BACK
    )
    psu_electrics_box = psu_electrics_box.cut(psu_electrics_box_inner_cutter)

    low_voltage_separator_wall = create_box(
        psu_mount_electrics_box_wall_thickness,
        psu_mount_electrics_box_depth,
        get_bounding_box_size(psu_electrics_box)[2],
    )
    low_voltage_separator_wall = align(
        low_voltage_separator_wall,
        low_voltage_window_cutter,
        Alignment.STACK_RIGHT,
    )
    low_voltage_separator_wall = align(
        low_voltage_separator_wall, psu_electrics_box, Alignment.FRONT
    )
    low_voltage_separator_wall = align(
        low_voltage_separator_wall, psu_electrics_box, Alignment.BOTTOM
    )
    psu_electrics_box = psu_electrics_box.fuse(low_voltage_separator_wall)

    psu_electrics_box_clearance_cutter = create_box(
        creality_psu_width + 2 * psu_mount_electrics_box_psu_clearance,
        psu_mount_electrics_box_depth_overlap,
        creality_psu_height + 2 * psu_mount_electrics_box_psu_clearance,
    )
    psu_electrics_box_clearance_cutter = align(
        psu_electrics_box_clearance_cutter, psu_electrics_box, Alignment.CENTER
    )
    psu_electrics_box_clearance_cutter = align(
        psu_electrics_box_clearance_cutter, psu_electrics_box, Alignment.BACK
    )
    psu_electrics_box = psu_electrics_box.cut(psu_electrics_box_clearance_cutter)

    psu_electrics_box = psu_electrics_box.cut(low_voltage_window_cutter)

    psu_electrics_box = align(psu_electrics_box, psu_body, Alignment.CENTER)
    psu_electrics_box = align(
        psu_electrics_box,
        psu_body,
        Alignment.STACK_FRONT,
        stack_gap=-psu_mount_electrics_box_depth_overlap,
    )

    # Cut all clearance holes into the electrics box
    for hole_type, lr, fb, clearance_hole in clearance_holes:
        psu_electrics_box = psu_electrics_box.cut(clearance_hole)

    psu_front_to_extra_clearance_cutter = create_box(
        creality_psu_width - 2 * creality_psu_sheet_metal_thickness,
        creality_psu_front_cutout_depth,
        psu_mount_electrics_box_psu_clearance
        + psu_mount_cable_camps_top_extra_clearance,
    )
    psu_front_to_extra_clearance_cutter = align(
        psu_front_to_extra_clearance_cutter, psu_body, Alignment.CENTER
    )
    psu_front_to_extra_clearance_cutter = align(
        psu_front_to_extra_clearance_cutter, psu_body, Alignment.FRONT
    )
    psu_front_to_extra_clearance_cutter = align(
        psu_front_to_extra_clearance_cutter, psu_body, Alignment.STACK_TOP
    )

    psu_electrics_box = psu_electrics_box.cut(psu_front_to_extra_clearance_cutter)
    cable_hole = create_cylinder(
        cable_hole_diameter / 2,
        BIG_THING,
    )
    cable_hole = align(cable_hole, psu_electrics_box, Alignment.CENTER)
    cable_hole = align(
        cable_hole,
        psu_electrics_box,
        Alignment.STACK_BOTTOM,
        stack_gap=-2 * psu_mount_electrics_box_wall_thickness,
    )

    cable_hole = align(cable_hole, psu_electrics_box, Alignment.EDGE_RIGHT)
    cable_hole = align(cable_hole, psu_electrics_box, Alignment.EDGE_FRONT)

    cable_hole = translate(-cable_hole_x_inset, cable_hole_y_inset, 0)(cable_hole)
    psu_electrics_box = psu_electrics_box.cut(cable_hole)

    cable_holder = create_box(
        cable_holder_arm_depth,
        cable_holder_hole_diameter + 2 * cable_holder_arm_width,
        cable_holder_arm_thickness,
    )

    cable_holder = align(cable_holder, cable_hole, Alignment.CENTER)
    cable_holder = align(cable_holder, cable_hole, Alignment.LEFT)
    cable_holder = align(cable_holder, psu_electrics_box, Alignment.BOTTOM)
    cable_holder = translate(
        -cable_holder_hole_diameter,
        0,
        psu_mount_electrics_box_wall_thickness
        + psu_mount_electrics_box_psu_clearance
        + cable_holder_wall_clearance,
    )(cable_holder)

    cable_holder_cable_hole_cutter = create_cylinder(
        cable_holder_hole_diameter / 2,
        BIG_THING,
    )
    cable_holder_cable_hole_cutter = align(
        cable_holder_cable_hole_cutter, cable_hole, Alignment.CENTER
    )
    cable_holder_cable_hole_cutter = align(
        cable_holder_cable_hole_cutter, cable_holder, Alignment.CENTER, axes=[2]
    )

    cable_holder = cable_holder.cut(cable_holder_cable_hole_cutter)

    cable_holder_slit_cutter = create_filleted_box(
        BIG_THING,
        cable_holder_slit_width,
        BIG_THING,
        fillet_radius=cable_holder_slit_width / 3,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    cable_holder_slit_cutter = align(
        cable_holder_slit_cutter, cable_holder, Alignment.CENTER
    )
    cable_holder_slit_cutter = align(
        cable_holder_slit_cutter,
        cable_holder,
        Alignment.STACK_RIGHT,
        stack_gap=-cable_holder_arm_depth + cable_holder_hole_diameter / 2,
    )

    cable_holder = cable_holder.cut(cable_holder_slit_cutter)
    cable_holder_screw_reference = create_box(
        2 * cable_holder_hole_diameter,
        cable_holder_hole_diameter + 2 * cable_holder_arm_width,
        cable_holder_arm_thickness,
    )
    cable_holder_screw_reference = align(
        cable_holder_screw_reference, cable_holder, Alignment.CENTER
    )
    cable_holder_screw_reference = align(
        cable_holder_screw_reference, cable_holder, Alignment.RIGHT
    )

    cable_holder_mount_screw_assembly = create_screw_mount_assembly(
        cable_holder_screw_reference,
        cable_holder_tightner_screw_size,
        cable_holder_tightner_screw_length,
        Alignment.BACK,
        flush_with_top=True,
    )

    cable_holder = cable_holder_mount_screw_assembly.use_as_cutter_on(cable_holder)

    cable_holder_clearance_cutter = materialize_bounding_box(
        cable_holder,
        x_enlargement=2 * cable_holder_wall_clearance,
        y_enlargement=2 * cable_holder_wall_clearance,
        z_enlargement=2 * cable_holder_wall_clearance,
    )

    psu_electrics_box = psu_electrics_box.cut(cable_holder_clearance_cutter)

    mount_eyes = PartCollector()
    for side in [Alignment.LEFT, Alignment.RIGHT]:
        mount_eye = create_filleted_box(
            10,
            30,
            4,
            fillet_radius=3,
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, side.opposite],
        )
        mount_eye_screw_hole_cutter = create_cylinder(
            MScrew.from_size(psu_mount_eye_screw_size).clearance_hole_normal / 2,
            BIG_THING,
        )
        mount_eye_screw_hole_cutter = align(
            mount_eye_screw_hole_cutter,
            mount_eye,
            Alignment.CENTER,
        )
        mount_eye = mount_eye.cut(mount_eye_screw_hole_cutter)
        mount_eye = rotate(90, axis=(1, 0, 0))(mount_eye)

        mount_eye = align(mount_eye, psu_electrics_box, Alignment.CENTER)
        mount_eye = align(mount_eye, psu_electrics_box, side.stack_alignment)
        mount_eye = align(mount_eye, psu_electrics_box, Alignment.FRONT)
        mount_eyes = mount_eyes.fuse(mount_eye)

    psu_electrics_box = psu_electrics_box.fuse(mount_eyes)

    retval = LeaderFollowersCuttersPart(leader=psu_electrics_box)
    retval.add_named_non_production_part(psu_body, "psu_body")
    retval.add_named_non_production_part(cable_clamps, "cable_clamps")
    retval.add_named_non_production_part(cable_clamps_lid, "cable_clamps_lid")
    retval.add_named_non_production_part(
        cable_holder_mount_screw_assembly.get_named_non_production_part("screw"),
        "cable_holder_tightner_screw",
    )
    retval.add_named_follower(cable_holder, "cable_holder")

    # Export clearance holes as cutters for other consumers
    for hole_type, lr, fb, clearance_hole in clearance_holes:
        retval.add_named_cutter(
            clearance_hole,
            f"{hole_type}_mount_screw_hole_{lr.name.lower()}_{fb.name.lower()}",
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
