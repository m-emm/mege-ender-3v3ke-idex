"""
Mgh Linear

Usage:
    cd <project_root> && ./run.sh path/to/mgh_linear.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/mgh_linear.py
"""

import logging
import os

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

mgn_12h_carriage_width = 27
mgn_12h_carriage_length = 45.4
mgn_12h_screw_hole_pitch = 20
mgn_12h_height = 10
mgn_12h_screw_hole_depth = 3.5
mgn_12h_h1 = 3.4

mgn_12ca_carriage_width = 27
mgn_12ca_carriage_length = 33.5
mgn_12ca_screw_hole_pitch_x = 15
mgn_12ca_screw_hole_pitch_y = 20
mgn_12ca_height = 10
mgn_12ca_screw_hole_depth = 3.5
mgn_12ca_h1 = 3.4

mgn_7h_rail_width = 7
mgn_7h_rail_height = 4.8
mgn_7h_rail_mount_hole_pitch = 15
mgn_7h_rail_mount_hole_end_offset = 7.5
mgn_7h_rail_mount_hole_diameter = 2.4
mgn_7h_rail_mount_counterbore_diameter = 4.2
mgn_7h_rail_mount_counterbore_depth = 2.4
mgn_7h_rail_mount_screw_size = "M2"
mgn_7h_rail_groove_z_center = 2.8
mgn_7h_rail_groove_v_height = 1.25
mgn_7h_rail_groove_v_depth = 0.625
mgn_7h_rail_groove_slot_height = 0.65
mgn_7h_rail_groove_slot_depth = 0.95
mgn_7h_rail_top_fillet_radius = 0.18
mgn_7h_rail_bottom_chamfer_width = 0.32
mgn_7h_rail_bottom_chamfer_height = 0.35
mgn_7h_rail_mock_clearance = 0.15
mgn_7h_rail_mock_groove_clearance = 0.06
mgn_7h_rail_mock_groove_height_clearance = 0.0

mgn_7h_carriage_length = 30.8
mgn_7h_carriage_width = 17
mgn_7h_carriage_height = 8
mgn_7h_carriage_h1 = 1.5
mgn_7h_carriage_screw_hole_pitch_x = 20
mgn_7h_carriage_screw_hole_pitch_y = 8
mgn_7h_carriage_screw_hole_depth = 3
mgn_7h_carriage_mount_screw_size = "M2"


def create_mgn7h_carriage(
    *,
    carriage_length=mgn_7h_carriage_length,
    carriage_width=mgn_7h_carriage_width,
    carriage_height=mgn_7h_carriage_height,
    carriage_h1_offset=mgn_7h_carriage_h1,
    carriage_mount_hole_pitch_x=mgn_7h_carriage_screw_hole_pitch_x,
    carriage_mount_hole_pitch_y=mgn_7h_carriage_screw_hole_pitch_y,
    carriage_mount_hole_depth=mgn_7h_carriage_screw_hole_depth,
    carriage_mount_screw_size=mgn_7h_carriage_mount_screw_size,
):
    """Create an MGN7H carriage reference part."""

    screw_hole_diameter = MScrew.from_size(
        carriage_mount_screw_size
    ).clearance_hole_normal

    carriage = create_box(carriage_length, carriage_width, carriage_height)

    holes = PartCollector()
    individual_holes = []
    for x in [-carriage_mount_hole_pitch_x / 2, carriage_mount_hole_pitch_x / 2]:
        for y in [-carriage_mount_hole_pitch_y / 2, carriage_mount_hole_pitch_y / 2]:
            hole = create_cylinder(screw_hole_diameter / 2, carriage_height)
            hole = translate(x, y, 0)(hole)
            individual_holes.append(hole)
            holes = holes.fuse(hole)

    holes = align(holes, carriage, Alignment.CENTER)
    holes = align(
        holes,
        carriage,
        Alignment.STACK_TOP,
        stack_gap=-carriage_mount_hole_depth,
    )
    holes_aligner_xy = align_translation(holes, carriage, Alignment.CENTER)
    holes_aligner_z = align_translation(
        holes,
        carriage,
        Alignment.STACK_TOP,
        stack_gap=-carriage_mount_hole_depth,
    )
    individual_holes = [holes_aligner_xy(hole) for hole in individual_holes]
    individual_holes = [holes_aligner_z(hole) for hole in individual_holes]

    carriage = carriage.cut(holes)

    carriage = LeaderFollowersCuttersPart(carriage, cutters=[holes])
    carriage.add_named_cutter(holes, "mount_holes")
    for index, hole in enumerate(individual_holes):
        carriage.add_named_cutter(hole, f"mount_hole_{index + 1}")
    carriage.add_named_follower(carriage.leader, "body")

    carriage = translate(0, 0, carriage_h1_offset)(carriage)

    return carriage


def create_mgn12h_carriage():
    """Create the MGN12H carriage part."""

    screw_hole_diameter = MScrew.from_size("M3").clearance_hole_normal

    carriage = create_box(
        mgn_12h_carriage_length, mgn_12h_carriage_width, mgn_12h_height
    )

    holes = PartCollector()
    for x in [-mgn_12h_screw_hole_pitch / 2, mgn_12h_screw_hole_pitch / 2]:
        for y in [-mgn_12h_screw_hole_pitch / 2, mgn_12h_screw_hole_pitch / 2]:
            hole = create_cylinder(screw_hole_diameter / 2, mgn_12h_height)
            hole = translate(x, y, 0)(hole)
            holes = holes.fuse(hole)

    holes = align(holes, carriage, Alignment.CENTER)
    holes = align(
        holes, carriage, Alignment.STACK_TOP, stack_gap=-mgn_12h_screw_hole_depth
    )

    carriage = carriage.cut(holes)

    carriage = LeaderFollowersCuttersPart(carriage, cutters=[holes])

    carriage = translate(0, 0, mgn_12h_h1)(carriage)

    return carriage


def create_mgn12ca_carriage():
    """Create the MGN12CA carriage part."""

    screw_hole_diameter = MScrew.from_size("M3").clearance_hole_normal

    carriage = create_box(
        mgn_12ca_carriage_length, mgn_12ca_carriage_width, mgn_12ca_height
    )

    holes = PartCollector()
    individual_holes = []
    for x in [-mgn_12ca_screw_hole_pitch_x / 2, mgn_12ca_screw_hole_pitch_x / 2]:
        for y in [-mgn_12ca_screw_hole_pitch_y / 2, mgn_12ca_screw_hole_pitch_y / 2]:
            hole = create_cylinder(screw_hole_diameter / 2, mgn_12ca_height)
            hole = translate(x, y, 0)(hole)
            individual_holes.append(hole)
            holes = holes.fuse(hole)

    holes = align(holes, carriage, Alignment.CENTER)
    holes = align(
        holes, carriage, Alignment.STACK_TOP, stack_gap=-mgn_12ca_screw_hole_depth
    )
    holes_aligner_xy = align_translation(holes, carriage, Alignment.CENTER)
    holes_aligner_z = align_translation(
        holes,
        carriage,
        Alignment.STACK_TOP,
        stack_gap=-mgn_12ca_screw_hole_depth,
    )
    individual_holes = [holes_aligner_xy(hole) for hole in individual_holes]
    individual_holes = [holes_aligner_z(hole) for hole in individual_holes]

    hole_centers = [get_bounding_box_center(hole) for hole in individual_holes]
    hole_centers_sorted = sorted(
        [
            (round(center[0], 3), round(center[1], 3), round(center[2], 3))
            for center in hole_centers
        ]
    )
    x_positions = sorted({round(center[0], 3) for center in hole_centers})
    y_positions = sorted({round(center[1], 3) for center in hole_centers})
    _logger.debug(
        "MGN12CA carriage hole centers=%s x_positions=%s y_positions=%s x_pitch=%.3f y_pitch=%.3f",
        hole_centers_sorted,
        x_positions,
        y_positions,
        x_positions[-1] - x_positions[0],
        y_positions[-1] - y_positions[0],
    )

    carriage = carriage.cut(holes)

    carriage = LeaderFollowersCuttersPart(carriage, cutters=[holes])

    carriage = translate(0, 0, mgn_12ca_h1)(carriage)

    return carriage


def create_mgn12h_rail(length_mm: float):
    """Create the MGN12H rail part."""

    width = 12
    height = 8.5
    hole_pitch = 25
    top_hole_diameter = 8
    bottom_hole_diameter = 4.5
    top_hole_depth = 4.5

    rail = create_box(length_mm, width, height)

    num_holes = int(length_mm // hole_pitch)
    holes_aligned = []

    if num_holes > 0:
        holes = PartCollector()
        holes_list = []
        for i in range(num_holes):
            x = i * hole_pitch
            # Top hole
            top_hole = create_cylinder(top_hole_diameter / 2, top_hole_depth)
            top_hole = translate(x, 0, 0)(top_hole)
            top_hole = align(top_hole, rail, Alignment.TOP)

            current_hole = top_hole
            holes = holes.fuse(top_hole)
            # Bottom hole
            bottom_hole = create_cylinder(bottom_hole_diameter / 2, height)
            bottom_hole = translate(x, 0, 0)(bottom_hole)
            bottom_hole = align(bottom_hole, rail, Alignment.BOTTOM)
            holes = holes.fuse(bottom_hole)
            current_hole = current_hole.fuse(bottom_hole)
            holes_list.append(current_hole)

        holes_align_translation = align_translation(
            holes, rail, Alignment.CENTER, axes=[0, 1]
        )

        holes_aligned = [holes_align_translation(hole) for hole in holes_list]

        for hole in holes_aligned:
            rail = rail.cut(hole)

    return LeaderFollowersCuttersPart(rail, cutters=holes_aligned)


def create_mgn7h_rail(
    *,
    length_mm: float,
    rail_width=mgn_7h_rail_width,
    rail_height=mgn_7h_rail_height,
    rail_mount_hole_pitch=mgn_7h_rail_mount_hole_pitch,
    rail_mount_hole_end_offset=mgn_7h_rail_mount_hole_end_offset,
    rail_mount_hole_diameter=mgn_7h_rail_mount_hole_diameter,
    rail_mount_counterbore_diameter=mgn_7h_rail_mount_counterbore_diameter,
    rail_mount_counterbore_depth=mgn_7h_rail_mount_counterbore_depth,
    rail_groove_z_center=mgn_7h_rail_groove_z_center,
    rail_groove_v_height=mgn_7h_rail_groove_v_height,
    rail_groove_v_depth=mgn_7h_rail_groove_v_depth,
    rail_groove_slot_height=mgn_7h_rail_groove_slot_height,
    rail_groove_slot_depth=mgn_7h_rail_groove_slot_depth,
    rail_top_fillet_radius=mgn_7h_rail_top_fillet_radius,
    rail_bottom_chamfer_width=mgn_7h_rail_bottom_chamfer_width,
    rail_bottom_chamfer_height=mgn_7h_rail_bottom_chamfer_height,
):
    """Create an MGN7H rail reference part."""

    rail = create_box(length_mm, rail_width, rail_height)
    if rail_top_fillet_radius > 0:
        rail = apply_fillet_by_alignment(
            rail,
            rail_top_fillet_radius,
            fillets_at=[Alignment.TOP],
        )

    profile_cutters = []
    profile_cutter_names = []
    cutter_x_min = -0.1
    cutter_x_max = length_mm + 0.1

    if rail_bottom_chamfer_width > 0 and rail_bottom_chamfer_height > 0:
        front_chamfer = create_triangular_prism(
            [
                (cutter_x_min, 0, 0),
                (cutter_x_min, rail_bottom_chamfer_width, 0),
                (cutter_x_min, 0, rail_bottom_chamfer_height),
                (cutter_x_max, 0, 0),
                (cutter_x_max, rail_bottom_chamfer_width, 0),
                (cutter_x_max, 0, rail_bottom_chamfer_height),
            ]
        )
        back_chamfer = create_triangular_prism(
            [
                (cutter_x_min, rail_width, 0),
                (cutter_x_min, rail_width - rail_bottom_chamfer_width, 0),
                (cutter_x_min, rail_width, rail_bottom_chamfer_height),
                (cutter_x_max, rail_width, 0),
                (cutter_x_max, rail_width - rail_bottom_chamfer_width, 0),
                (cutter_x_max, rail_width, rail_bottom_chamfer_height),
            ]
        )
        for name, chamfer in [
            ("bottom_chamfer_front", front_chamfer),
            ("bottom_chamfer_back", back_chamfer),
        ]:
            rail = rail.cut(chamfer)
            profile_cutters.append(chamfer)
            profile_cutter_names.append(name)

    last_hole_x = length_mm - rail_mount_hole_end_offset
    hole_x = rail_mount_hole_end_offset
    holes_aligned = []

    if last_hole_x >= hole_x:
        holes_list = []
        while hole_x <= last_hole_x + 1e-6:
            top_hole = create_cylinder(
                rail_mount_counterbore_diameter / 2,
                rail_mount_counterbore_depth,
            )
            top_hole = translate(hole_x, rail_width / 2, 0)(top_hole)
            top_hole = align(top_hole, rail, Alignment.TOP)

            current_hole = top_hole
            bottom_hole = create_cylinder(rail_mount_hole_diameter / 2, rail_height)
            bottom_hole = translate(hole_x, rail_width / 2, 0)(bottom_hole)
            bottom_hole = align(bottom_hole, rail, Alignment.BOTTOM)
            current_hole = current_hole.fuse(bottom_hole)
            holes_list.append(current_hole)
            hole_x += rail_mount_hole_pitch

        holes_aligned = holes_list

        for hole in holes_aligned:
            rail = rail.cut(hole)

    if rail_groove_v_depth > 0 and rail_groove_v_height > 0:
        groove_v_convergence_depth = rail_groove_v_depth
        if rail_groove_slot_depth > 0 and rail_groove_slot_height > 0:
            # A 90-degree side V converges on the rounded slot end-circle center.
            groove_v_convergence_depth = max(
                0,
                rail_groove_slot_depth - rail_groove_slot_height / 2,
            )

        z_min = rail_groove_z_center - groove_v_convergence_depth
        z_max = rail_groove_z_center + groove_v_convergence_depth
        front_groove_v = create_triangular_prism(
            [
                (cutter_x_min, 0, z_min),
                (cutter_x_min, 0, z_max),
                (cutter_x_min, groove_v_convergence_depth, rail_groove_z_center),
                (cutter_x_max, 0, z_min),
                (cutter_x_max, 0, z_max),
                (cutter_x_max, groove_v_convergence_depth, rail_groove_z_center),
            ]
        )
        back_groove_v = create_triangular_prism(
            [
                (cutter_x_min, rail_width, z_min),
                (cutter_x_min, rail_width, z_max),
                (
                    cutter_x_min,
                    rail_width - groove_v_convergence_depth,
                    rail_groove_z_center,
                ),
                (cutter_x_max, rail_width, z_min),
                (cutter_x_max, rail_width, z_max),
                (
                    cutter_x_max,
                    rail_width - groove_v_convergence_depth,
                    rail_groove_z_center,
                ),
            ]
        )
        for name, groove_v in [
            ("groove_v_front", front_groove_v),
            ("groove_v_back", back_groove_v),
        ]:
            rail = rail.cut(groove_v)
            profile_cutters.append(groove_v)
            profile_cutter_names.append(name)

    if rail_groove_slot_depth > 0 and rail_groove_slot_height > 0:
        slot_overshoot = 0.1
        groove_slot = create_rounded_slab(
            rail_groove_slot_depth + slot_overshoot,
            rail_groove_slot_height,
            length_mm + 2 * slot_overshoot,
            rail_groove_slot_height / 2,
        )
        groove_slot = rotate(90, axis=(0, 1, 0))(groove_slot)
        groove_slot = rotate(-90, axis=(1, 0, 0))(groove_slot)
        groove_slot = translate(
            -slot_overshoot,
            0,
            rail_groove_z_center + rail_groove_slot_height / 2,
        )(groove_slot)
        front_groove_slot = align(
            groove_slot,
            rail,
            Alignment.STACK_FRONT,
            stack_gap=-rail_groove_slot_depth,
        )
        back_groove_slot = align(
            groove_slot,
            rail,
            Alignment.STACK_BACK,
            stack_gap=-rail_groove_slot_depth,
        )
        for name, groove_slot_cutter in [
            ("groove_slot_front", front_groove_slot),
            ("groove_slot_back", back_groove_slot),
        ]:
            rail = rail.cut(groove_slot_cutter)
            profile_cutters.append(groove_slot_cutter)
            profile_cutter_names.append(name)

    rail = LeaderFollowersCuttersPart(rail, cutters=holes_aligned + profile_cutters)
    rail.add_named_follower(rail.leader, "rail_body")
    for index, hole in enumerate(holes_aligned):
        rail.add_named_cutter(hole, f"mounting_hole_{index + 1}")
    for name, profile_cutter in zip(profile_cutter_names, profile_cutters):
        rail.add_named_cutter(profile_cutter, name)

    return rail


def create_mgn7h_rail_with_carriage(
    *,
    length_mm: float,
    carriage_offset=0,
    rail_width=mgn_7h_rail_width,
    rail_height=mgn_7h_rail_height,
    rail_mount_hole_pitch=mgn_7h_rail_mount_hole_pitch,
    rail_mount_hole_end_offset=mgn_7h_rail_mount_hole_end_offset,
    rail_mount_hole_diameter=mgn_7h_rail_mount_hole_diameter,
    rail_mount_counterbore_diameter=mgn_7h_rail_mount_counterbore_diameter,
    rail_mount_counterbore_depth=mgn_7h_rail_mount_counterbore_depth,
    rail_groove_z_center=mgn_7h_rail_groove_z_center,
    rail_groove_v_height=mgn_7h_rail_groove_v_height,
    rail_groove_v_depth=mgn_7h_rail_groove_v_depth,
    rail_groove_slot_height=mgn_7h_rail_groove_slot_height,
    rail_groove_slot_depth=mgn_7h_rail_groove_slot_depth,
    rail_top_fillet_radius=mgn_7h_rail_top_fillet_radius,
    rail_bottom_chamfer_width=mgn_7h_rail_bottom_chamfer_width,
    rail_bottom_chamfer_height=mgn_7h_rail_bottom_chamfer_height,
    rail_mock_clearance=mgn_7h_rail_mock_clearance,
    rail_mock_groove_clearance=mgn_7h_rail_mock_groove_clearance,
    rail_mock_groove_height_clearance=mgn_7h_rail_mock_groove_height_clearance,
    carriage_length=mgn_7h_carriage_length,
    carriage_width=mgn_7h_carriage_width,
    carriage_height=mgn_7h_carriage_height,
    carriage_h1_offset=mgn_7h_carriage_h1,
    carriage_mount_hole_pitch_x=mgn_7h_carriage_screw_hole_pitch_x,
    carriage_mount_hole_pitch_y=mgn_7h_carriage_screw_hole_pitch_y,
    carriage_mount_hole_depth=mgn_7h_carriage_screw_hole_depth,
    carriage_mount_screw_size=mgn_7h_carriage_mount_screw_size,
):
    """Create an MGN7H rail assembly with a built-in carriage follower."""

    rail = create_mgn7h_rail(
        length_mm=length_mm,
        rail_width=rail_width,
        rail_height=rail_height,
        rail_mount_hole_pitch=rail_mount_hole_pitch,
        rail_mount_hole_end_offset=rail_mount_hole_end_offset,
        rail_mount_hole_diameter=rail_mount_hole_diameter,
        rail_mount_counterbore_diameter=rail_mount_counterbore_diameter,
        rail_mount_counterbore_depth=rail_mount_counterbore_depth,
        rail_groove_z_center=rail_groove_z_center,
        rail_groove_v_height=rail_groove_v_height,
        rail_groove_v_depth=rail_groove_v_depth,
        rail_groove_slot_height=rail_groove_slot_height,
        rail_groove_slot_depth=rail_groove_slot_depth,
        rail_top_fillet_radius=rail_top_fillet_radius,
        rail_bottom_chamfer_width=rail_bottom_chamfer_width,
        rail_bottom_chamfer_height=rail_bottom_chamfer_height,
    )
    printable_rail = create_mgn7h_rail(
        length_mm=length_mm,
        rail_width=rail_width - 2 * rail_mock_clearance,
        rail_height=rail_height - 2 * rail_mock_clearance,
        rail_mount_hole_pitch=rail_mount_hole_pitch,
        rail_mount_hole_end_offset=rail_mount_hole_end_offset,
        rail_mount_hole_diameter=rail_mount_hole_diameter,
        rail_mount_counterbore_diameter=rail_mount_counterbore_diameter,
        rail_mount_counterbore_depth=rail_mount_counterbore_depth,
        rail_groove_z_center=rail_groove_z_center - rail_mock_clearance,
        rail_groove_v_height=rail_groove_v_height
        + 2 * rail_mock_groove_height_clearance,
        rail_groove_v_depth=rail_groove_v_depth + rail_mock_groove_clearance,
        rail_groove_slot_height=rail_groove_slot_height
        + 2 * rail_mock_groove_height_clearance,
        rail_groove_slot_depth=rail_groove_slot_depth + rail_mock_groove_clearance,
        rail_top_fillet_radius=rail_top_fillet_radius,
        rail_bottom_chamfer_width=rail_bottom_chamfer_width,
        rail_bottom_chamfer_height=rail_bottom_chamfer_height,
    )
    printable_rail = translate(0, rail_mock_clearance, rail_mock_clearance)(
        printable_rail
    )
    rail.add_named_follower(printable_rail.leader, "rail_mockup_printable")

    carriage = create_mgn7h_carriage(
        carriage_length=carriage_length,
        carriage_width=carriage_width,
        carriage_height=carriage_height,
        carriage_h1_offset=carriage_h1_offset,
        carriage_mount_hole_pitch_x=carriage_mount_hole_pitch_x,
        carriage_mount_hole_pitch_y=carriage_mount_hole_pitch_y,
        carriage_mount_hole_depth=carriage_mount_hole_depth,
        carriage_mount_screw_size=carriage_mount_screw_size,
    )
    carriage = align(carriage, rail.leader, Alignment.CENTER, axes=[0, 1])
    carriage = translate(carriage_offset, 0, 0)(carriage)
    carriage = carriage.prefixed_copy("carriage")

    rail.add_named_follower(carriage.leader, name="carriage")
    rail = rail.merge_except_leader(carriage)

    return rail


def create_mgn12h_rail_with_carriages(
    length_mm: float,
    carriage_offsets=None,
    carriage_names=None,
):
    """Create a rail assembly with carriages mounted at the correct rail-relative height.

    The carriage body is modeled in its own local coordinates with the required vertical
    offset above the rail floor. By attaching carriages as followers of the rail assembly,
    any later alignment or translation of the assembly preserves that relationship.
    """

    rail = create_mgn12h_rail(length_mm=length_mm)

    if carriage_offsets is None:
        return rail

    if carriage_names is None:
        carriage_names = [f"carriage_{i + 1}" for i in range(len(carriage_offsets))]

    if len(carriage_names) != len(carriage_offsets):
        raise ValueError("carriage_names must match carriage_offsets length")

    for carriage_offset, carriage_name in zip(carriage_offsets, carriage_names):
        carriage = create_mgn12h_carriage()
        carriage = align(carriage, rail.leader, Alignment.CENTER, axes=[0, 1])
        carriage = translate(carriage_offset, 0, 0)(carriage)
        carriage = carriage.prefixed_copy(carriage_name)
        rail.add_named_follower(carriage.leader, name=carriage_name)
        rail = rail.merge_except_leader(carriage)

    return rail


def create_mgn12ca_rail_with_carriages(
    length_mm: float,
    carriage_offsets=None,
    carriage_names=None,
):
    """Create a rail assembly with carriages mounted at the correct rail-relative height.

    The carriage body is modeled in its own local coordinates with the required vertical
    offset above the rail floor. By attaching carriages as followers of the rail assembly,
    any later alignment or translation of the assembly preserves that relationship.
    """

    rail = create_mgn12h_rail(length_mm=length_mm)

    if carriage_offsets is None:
        return rail

    if carriage_names is None:
        carriage_names = [f"carriage_{i + 1}" for i in range(len(carriage_offsets))]

    if len(carriage_names) != len(carriage_offsets):
        raise ValueError("carriage_names must match carriage_offsets length")

    for carriage_offset, carriage_name in zip(carriage_offsets, carriage_names):
        carriage = create_mgn12ca_carriage()
        carriage = align(carriage, rail.leader, Alignment.CENTER, axes=[0, 1])
        carriage = translate(carriage_offset, 0, 0)(carriage)
        carriage = carriage.prefixed_copy(carriage_name)
        rail.add_named_follower(carriage.leader, name=carriage_name)
        rail = rail.merge_except_leader(carriage)

    return rail


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    part = create_mgn12h_rail_with_carriages(length_mm=150, carriage_offsets=[0])
    parts.add(part.leader, "mgh_linear", flip=False)
    parts.add(
        part.get_named_follower("carriage_1"),
        "mgh_linear_carriage",
        flip=False,
    )

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("mgh_linear created successfully!")


if __name__ == "__main__":
    main()
