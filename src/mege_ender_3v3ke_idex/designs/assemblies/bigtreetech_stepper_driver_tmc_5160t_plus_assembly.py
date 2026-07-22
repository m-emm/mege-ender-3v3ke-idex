"""BIGTREETECH TMC5160T Plus stepper-driver reference assembly."""

from shellforgepy.simple import *


def create_bigtreetech_stepper_driver_tmc_5160t_plus_assembly(
    *,
    bigtreetech_tmc5160t_plus_housing_length,
    bigtreetech_tmc5160t_plus_housing_width,
    bigtreetech_tmc5160t_plus_housing_height,
    bigtreetech_tmc5160t_plus_capacitor_diameter,
    bigtreetech_tmc5160t_plus_capacitor_top_height,
    bigtreetech_tmc5160t_plus_capacitor_left_x,
    bigtreetech_tmc5160t_plus_capacitor_right_x,
    bigtreetech_tmc5160t_plus_capacitor_y,
    bigtreetech_tmc5160t_plus_mount_hole_front_left_x,
    bigtreetech_tmc5160t_plus_mount_hole_front_left_y,
    bigtreetech_tmc5160t_plus_mount_hole_pitch_x,
    bigtreetech_tmc5160t_plus_mount_hole_pitch_y,
    bigtreetech_tmc5160t_plus_mount_screw_size,
    bigtreetech_tmc5160t_plus_mount_hole_core_bore_depth,
):
    """Create a space-claim mock-up with reusable mounting-hole cutters."""
    if bigtreetech_tmc5160t_plus_capacitor_top_height <= (
        bigtreetech_tmc5160t_plus_housing_height
    ):
        raise ValueError("Capacitor top must be above the housing top.")
    if (
        not 0
        < bigtreetech_tmc5160t_plus_mount_hole_core_bore_depth
        < (bigtreetech_tmc5160t_plus_housing_height)
    ):
        raise ValueError("Mount-hole core bores must be blind and have positive depth.")

    capacitor_radius = bigtreetech_tmc5160t_plus_capacitor_diameter / 2
    for name, capacitor_x in (
        ("left", bigtreetech_tmc5160t_plus_capacitor_left_x),
        ("right", bigtreetech_tmc5160t_plus_capacitor_right_x),
    ):
        if (
            not capacitor_radius
            <= capacitor_x
            <= (bigtreetech_tmc5160t_plus_housing_length - capacitor_radius)
        ):
            raise ValueError(f"The {name} capacitor does not fit on the housing.")
    if (
        not capacitor_radius
        <= bigtreetech_tmc5160t_plus_capacitor_y
        <= (bigtreetech_tmc5160t_plus_housing_width - capacitor_radius)
    ):
        raise ValueError("The capacitors do not fit on the housing width.")

    housing = create_box(
        bigtreetech_tmc5160t_plus_housing_length,
        bigtreetech_tmc5160t_plus_housing_width,
        bigtreetech_tmc5160t_plus_housing_height,
        origin=(0, 0, 0),
    )
    capacitor_height = (
        bigtreetech_tmc5160t_plus_capacitor_top_height
        - bigtreetech_tmc5160t_plus_housing_height
    )
    capacitors = []
    for name, capacitor_x in (
        ("capacitor_left", bigtreetech_tmc5160t_plus_capacitor_left_x),
        ("capacitor_right", bigtreetech_tmc5160t_plus_capacitor_right_x),
    ):
        capacitor = create_cylinder(capacitor_radius, capacitor_height)
        capacitor = translate(
            capacitor_x,
            bigtreetech_tmc5160t_plus_capacitor_y,
            bigtreetech_tmc5160t_plus_housing_height,
        )(capacitor)
        capacitors.append((name, capacitor))

    mount_screw = MScrew.from_size(bigtreetech_tmc5160t_plus_mount_screw_size)
    mount_hole_radius = mount_screw.clearance_hole_normal / 2
    mount_hole_core_bore_radius = mount_screw.core_hole / 2
    mount_hole_positions = (
        (
            "mount_hole_front_left",
            bigtreetech_tmc5160t_plus_mount_hole_front_left_x,
            bigtreetech_tmc5160t_plus_mount_hole_front_left_y,
        ),
        (
            "mount_hole_front_right",
            bigtreetech_tmc5160t_plus_mount_hole_front_left_x
            + bigtreetech_tmc5160t_plus_mount_hole_pitch_x,
            bigtreetech_tmc5160t_plus_mount_hole_front_left_y,
        ),
        (
            "mount_hole_back_left",
            bigtreetech_tmc5160t_plus_mount_hole_front_left_x,
            bigtreetech_tmc5160t_plus_mount_hole_front_left_y
            + bigtreetech_tmc5160t_plus_mount_hole_pitch_y,
        ),
        (
            "mount_hole_back_right",
            bigtreetech_tmc5160t_plus_mount_hole_front_left_x
            + bigtreetech_tmc5160t_plus_mount_hole_pitch_x,
            bigtreetech_tmc5160t_plus_mount_hole_front_left_y
            + bigtreetech_tmc5160t_plus_mount_hole_pitch_y,
        ),
    )
    mount_holes = []
    for name, mount_hole_x, mount_hole_y in mount_hole_positions:
        if not mount_hole_radius <= mount_hole_x <= (
            bigtreetech_tmc5160t_plus_housing_length - mount_hole_radius
        ) or not mount_hole_radius <= mount_hole_y <= (
            bigtreetech_tmc5160t_plus_housing_width - mount_hole_radius
        ):
            raise ValueError(f"{name} does not fit within the housing footprint.")

        core_bore = create_cylinder(
            mount_hole_core_bore_radius,
            bigtreetech_tmc5160t_plus_mount_hole_core_bore_depth + 0.1,
        )
        core_bore = align(
            core_bore,
            housing,
            Alignment.STACK_BOTTOM,
            stack_gap=-bigtreetech_tmc5160t_plus_mount_hole_core_bore_depth,
        )
        core_bore = translate(mount_hole_x, mount_hole_y, 0)(core_bore)
        housing = housing.cut(core_bore)

        mount_hole = create_cylinder(
            mount_hole_radius,
            bigtreetech_tmc5160t_plus_housing_height,
        )
        mount_hole = align(mount_hole, housing, Alignment.STACK_BOTTOM)
        mount_hole = translate(mount_hole_x, mount_hole_y, 0)(mount_hole)
        mount_holes.append((name, mount_hole))

    front_height = 15.6
    side_width = 13
    front_cut_depth = 30
    front_center_depth = 8
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        cutter_box = create_box(500, 500, 500)
        cutter_box = align(cutter_box, housing, Alignment.CENTER)
        cutter_box = align(cutter_box, housing, Alignment.BOTTOM)
        cutter_box = translate(0, 0, front_height)(cutter_box)
        cutter_box = align(
            cutter_box, housing, lr.stack_alignment, stack_gap=-side_width
        )

        cutter_box = align(
            cutter_box, housing, Alignment.STACK_FRONT, stack_gap=-front_cut_depth
        )
        housing = housing.cut(cutter_box)

    cutter_box = create_box(500, 500, 500)
    cutter_box = align(cutter_box, housing, Alignment.CENTER)
    cutter_box = align(cutter_box, housing, Alignment.BOTTOM)
    cutter_box = translate(0, 0, front_height)(cutter_box)
    cutter_box = align(
        cutter_box, housing, Alignment.STACK_FRONT, stack_gap=-front_center_depth
    )
    housing = housing.cut(cutter_box)

    assembly = LeaderFollowersCuttersPart(leader=housing)
    for name, capacitor in capacitors:
        assembly.add_named_non_production_part(capacitor, name)
    for name, mount_hole in mount_holes:
        assembly.add_named_cutter(mount_hole, name)

    return assembly
