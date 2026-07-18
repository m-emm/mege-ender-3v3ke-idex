"""Join Tap-related hardware with the fan-joined extruder cage.

Run the isolated magnet-holder demo with::

    ./run.sh src/mege_ender_3v3ke_idex/designs/assemblies/tap_extruder_cage_joiner.py
"""

import logging

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


def create_magnet_screw_assembly():
    magnet_screw_length = 6
    magnet_screw = create_conical_head_screw("M3", magnet_screw_length)

    magnet_screw = LeaderFollowersCuttersPart(magnet_screw)

    magnet_screw_thread_hole_cutter = create_self_threading_hole_cutter(
        "M3",
        magnet_screw_length + 2,
        core_radius_adjustment=-0.35,
        lead_in=True,
    )

    magnet_screw_thread_hole_cutter = align(
        magnet_screw_thread_hole_cutter, magnet_screw, Alignment.CENTER
    )
    magnet_screw_thread_hole_cutter = align(
        magnet_screw_thread_hole_cutter, magnet_screw, Alignment.TOP
    )
    magnet_screw_thread_hole_cutter = translate(
        0, 0, -MScrew.from_size("M3").conical_head_height
    )(magnet_screw_thread_hole_cutter)

    magnet_screw.add_named_cutter(magnet_screw_thread_hole_cutter, "thread_hole_cutter")

    magnet_screw_head_cutter = create_cone(
        radius1=3 / 2,
        radius2=MScrew.from_size("M3").conical_head_diameter / 2 + 0.2,
        height=MScrew.from_size("M3").conical_head_height + 0.1,
    )
    magnet_screw_head_cutter = align(
        magnet_screw_head_cutter, magnet_screw, Alignment.CENTER
    )
    magnet_screw_head_cutter = align(
        magnet_screw_head_cutter, magnet_screw, Alignment.TOP
    )
    magnet_screw.add_named_cutter(magnet_screw_head_cutter, "head_cutter")

    magnet_screw_top_cutter = create_box(50, 50, 50)
    magnet_screw_top_cutter = align(
        magnet_screw_top_cutter, magnet_screw, Alignment.CENTER
    )
    magnet_screw_top_cutter = align(
        magnet_screw_top_cutter, magnet_screw, Alignment.STACK_TOP
    )
    magnet_screw.add_named_cutter(magnet_screw_top_cutter, "top_cutter")

    magnet_diameter = 5
    magnet_height = 25
    magnet_holder_size = 12
    magnet_holder_y_size = 10
    magnet_holder_height = 15
    magnet_holder_clearance = 0.05
    magnet_to_screw_head_stack_gap = 0.3

    magnet_holder_slit_thickness = 1
    magnet_holder_slit_enlargement = 10
    magnet_holder_clamp_screw_material_thickness = 2
    magnet_clamp_screw_length = 8
    magnet_clamp_screw_vertical_inset = 3
    magnet_clamp_screw_horizontal_inset = 1.8
    magnet = create_cylinder(magnet_diameter / 2, magnet_height)
    magnet = align(magnet, magnet_screw, Alignment.CENTER)
    magnet = align(
        magnet,
        magnet_screw,
        Alignment.STACK_TOP,
        stack_gap=magnet_to_screw_head_stack_gap,
    )
    magnet_screw.add_named_non_production_part(magnet, "magnet")

    magnet_holder = create_box(
        magnet_holder_size, magnet_holder_y_size, magnet_holder_height
    )
    magnet_holder = LeaderFollowersCuttersPart(magnet_holder)
    magnet_holder = align(magnet_holder, magnet, Alignment.CENTER)
    magnet_holder = align(magnet_holder, magnet, Alignment.BOTTOM)
    magnet_holder = translate(0, 0, -0.3)(magnet_holder)

    magnet_holder_inner_cutter = create_cylinder(
        magnet_diameter / 2 + magnet_holder_clearance, 100
    )
    magnet_holder_inner_cutter = align(
        magnet_holder_inner_cutter, magnet, Alignment.CENTER
    )
    magnet_holder_inner_cutter = align(
        magnet_holder_inner_cutter, magnet, Alignment.BOTTOM
    )
    magnet_holder_inner_cutter = translate(0, 0, -magnet_to_screw_head_stack_gap)(
        magnet_holder_inner_cutter
    )
    magnet_holder = magnet_holder.cut(magnet_holder_inner_cutter)

    slit_cutter = materialize_bounding_box(
        magnet_holder,
        y_size=magnet_holder_slit_thickness,
        x_enlargement=magnet_holder_slit_enlargement,
    )
    slit_cutter = align(slit_cutter, magnet_holder, Alignment.CENTER)

    # slit_cutter, _ = cut_in_two(slit_cutter, cut_normal=[1, 0, 0])

    magnet_clamp_screw = create_complete_screw_assembly(
        "M2",
        magnet_clamp_screw_length,
        ScrewType.CYLINDER_HEAD,
        hole_type=HoleType.SELF_THREADING,
        core_radius_adjustment=-0.35,
        lead_in=True,
        hole_distance_from_head=magnet_holder_clamp_screw_material_thickness
        + magnet_holder_slit_thickness,
        with_access_hole=True,
        extra_access_hole_length=10,
        access_hole_clearance=0.3,
    )

    clearance_hole_top_cutter = create_cylinder(
        MScrew.from_size("M2").clearance_hole_loose / 2,
        magnet_holder_clamp_screw_material_thickness + magnet_holder_slit_thickness,
    )

    clearance_hole_top_cutter = align(
        clearance_hole_top_cutter, magnet_clamp_screw, Alignment.CENTER
    )
    clearance_hole_top_cutter = align(
        clearance_hole_top_cutter, magnet_clamp_screw, Alignment.TOP
    )

    magnet_clamp_screw.add_named_cutter(
        clearance_hole_top_cutter, "clearance_hole_top_cutter"
    )

    magnet_clamp_screw = rotate(180, axis=[1, 0, 0])(magnet_clamp_screw)

    magnet_clamp_screw = rotate(90, axis=[1, 0, 0])(magnet_clamp_screw)
    magnet_clamp_screw = align(magnet_clamp_screw, magnet_holder, Alignment.CENTER)
    magnet_clamp_screw = magnet_clamp_screw.aligned_from_non_production_part(
        "complete_screw", magnet_holder, Alignment.BACK
    )  # align(magnet_clamp_screw, magnet_holder, Alignment.BACK)
    magnet_clamp_screw = align(magnet_clamp_screw, magnet_holder, Alignment.EDGE_RIGHT)
    magnet_clamp_screw = align(magnet_clamp_screw, magnet_holder, Alignment.EDGE_BOTTOM)
    magnet_clamp_screw = translate(
        -magnet_clamp_screw_horizontal_inset, 0, magnet_clamp_screw_vertical_inset
    )(magnet_clamp_screw)

    magnet_clamp_screw = magnet_clamp_screw.prefixed_copy("magnet_clamp_screw")

    magnet_holder = magnet_clamp_screw.use_as_cutter_on(magnet_holder)

    # magnet_screw = magnet_screw.merge_except_leader(magnet_clamp_screw)

    magnet_screw.add_named_non_production_part(
        magnet_clamp_screw.get_named_non_production_part(
            "magnet_clamp_screw_complete_screw"
        ),
        "magnet_clamp_screw",
    )
    for name, cutter in magnet_clamp_screw.get_named_cutter_items():
        magnet_screw.add_named_cutter(cutter, f"magnet_clamp_screw_{name}")

    magnet_holder = magnet_holder.cut(slit_cutter)

    magnet_screw.add_named_non_production_part(magnet_holder.leader, "magnet_holder")
    magnet_screw.add_named_cutter(
        magnet_holder_inner_cutter, "magnet_holder_magnet_clearance_cutter"
    )

    magnet_holder_cutter = materialize_bounding_box(magnet_holder)
    magnet_holder_cutter = magnet_holder_cutter.fuse(slit_cutter)
    magnet_screw.add_named_cutter(magnet_holder_cutter, "magnet_holder_cutter")

    return magnet_screw


def add_magnet_screw_holders(*, extruder_cage, idex_tap_t1, carriage):
    """Add the paired magnet screw holders, clamp hardware, and Tap slits."""

    joined_extruder_cage = extruder_cage
    joined_idex_tap_t1 = idex_tap_t1
    joined_idex_tap_t1_additions = None

    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        magnet_screw = create_magnet_screw_assembly()
        magnet_screw = rotate(180)(magnet_screw)

        if lr == Alignment.RIGHT:
            magnet_screw = mirror(normal=(1, 0, 0))(magnet_screw)

        magnet_screw = rotate(180 + 45, axis=[1, 0, 0])(magnet_screw)
        magnet_screw = align(magnet_screw, carriage, Alignment.CENTER)
        magnet_screw = align(magnet_screw, carriage, Alignment.BACK)
        magnet_screw = align(magnet_screw, carriage, lr.stack_alignment, stack_gap=4)
        magnet_screw = translate(0, 1.7, -5)(magnet_screw)

        joined_extruder_cage.add_named_non_production_part(
            magnet_screw.leader, f"magnet_screw_{lr.name.lower()}"
        )

        magnet_screw_holder_cage_side = materialize_bounding_box(
            magnet_screw, x_enlargement=1, y_enlargement=3, z_enlargement=2
        )
        magnet_screw_holder_cage_side = align(
            magnet_screw_holder_cage_side, carriage, Alignment.BACK
        )
        magnet_screw_holder_cage_side = translate(0, -0.5, 0)(
            magnet_screw_holder_cage_side
        )
        magnet_screw_holder_cage_side = magnet_screw.use_as_cutter_on(
            magnet_screw_holder_cage_side
        )
        joined_extruder_cage = joined_extruder_cage.fuse(magnet_screw_holder_cage_side)

        joined_extruder_cage = joined_extruder_cage.cut(
            magnet_screw.get_named_cutter("thread_hole_cutter")
        )

        joined_idex_tap_t1.add_named_non_production_part(
            magnet_screw.get_named_non_production_part("magnet"),
            f"magnet_{lr.name}",
        )

        joined_idex_tap_t1.add_named_non_production_part(
            magnet_screw.get_named_non_production_part("magnet_clamp_screw"),
            f"magnet_clamp_screw_{lr.name}",
        )
        rotated_magnet_holder_cutter = magnet_screw.get_named_cutter(
            "magnet_holder_cutter"
        )
        joined_idex_tap_t1 = joined_idex_tap_t1.cut(rotated_magnet_holder_cutter)

        magnet_holder = magnet_screw.get_named_non_production_part("magnet_holder")

        back_cutter = create_box(100, 100, 100)
        back_cutter = align(back_cutter, magnet_holder, Alignment.CENTER)
        back_cutter = align(
            back_cutter, joined_idex_tap_t1, Alignment.STACK_BACK, stack_gap=1
        )

        bottom_cutter = create_box(100, 100, 100)
        bottom_cutter = align(bottom_cutter, magnet_holder, Alignment.CENTER)
        bottom_cutter = align(bottom_cutter, joined_idex_tap_t1, Alignment.STACK_BOTTOM)

        rotated_magnet_holder_cutter = rotated_magnet_holder_cutter.cut(back_cutter)
        magnet_holder = magnet_holder.cut(back_cutter)
        magnet_holder = magnet_holder.cut(bottom_cutter)

        joined_idex_tap_t1 = joined_idex_tap_t1.cut(rotated_magnet_holder_cutter)

        if joined_idex_tap_t1_additions is None:
            joined_idex_tap_t1_additions = magnet_holder
        else:
            joined_idex_tap_t1_additions = joined_idex_tap_t1_additions.fuse(
                magnet_holder
            )

        magnet_holder_path_cutter = materialize_bounding_box(
            magnet_screw.leader, x_enlargement=1, y_enlargement=1, z_size=5
        )
        magnet_holder_path_cutter = align(
            magnet_holder_path_cutter,
            magnet_screw.get_named_non_production_part("magnet"),
            Alignment.STACK_TOP,
        )
        magnet_holder_path_cutter = translate(0, 0, -2)(magnet_holder_path_cutter)
        joined_idex_tap_t1 = joined_idex_tap_t1.cut(magnet_holder_path_cutter)
        joined_idex_tap_t1_additions = joined_idex_tap_t1_additions.cut(
            magnet_holder_path_cutter
        )

        for name, cutter in magnet_screw.get_named_cutter_items():
            if "clamp_screw" in name:
                _logger.info(f"Cutting idex_tap_t1 with {name}")
                joined_idex_tap_t1 = joined_idex_tap_t1.cut(cutter)
                joined_idex_tap_t1_additions = joined_idex_tap_t1_additions.cut(cutter)

    if joined_idex_tap_t1_additions is not None:
        joined_idex_tap_t1 = joined_idex_tap_t1.fuse(joined_idex_tap_t1_additions)

    return {
        "extruder_cage": joined_extruder_cage,
        "idex_tap_t1": joined_idex_tap_t1,
    }


def join_tap_with_extruder_cage(
    *,
    extruder_cage,
    sprite_extruder,
    mgn7h_rail_with_carriage,
    idex_tap_t1,
    opb991t11z_sensor,
):
    """Return the final extruder cage and Tap assemblies."""

    joined_extruder_cage = extruder_cage.copy()
    joined_idex_tap_t1 = idex_tap_t1.copy()

    if mgn7h_rail_with_carriage is not None:
        back_plate = materialize_bounding_box(
            mgn7h_rail_with_carriage, y_size=3, x_enlargement=5
        )
        back_plate = align(back_plate, mgn7h_rail_with_carriage, Alignment.STACK_FRONT)
        joined_extruder_cage = joined_extruder_cage.cut(back_plate)

        full_bbox_cutter = materialize_bounding_box(
            mgn7h_rail_with_carriage,
            x_enlargement=0.1,
            y_enlargement=2,
            z_enlargement=0.1,
        )

        carriage = mgn7h_rail_with_carriage.get_named_follower("carriage")
        carriage_size = get_bounding_box_size(carriage)
        joined_extruder_cage = joined_extruder_cage.cut(full_bbox_cutter)
        carriage_cutter = materialize_bounding_box(
            carriage,
            x_enlargement=0.8,
            y_enlargement=0.6,
            z_enlargement=40,
        )
        carriage_cutter = align(
            carriage_cutter, mgn7h_rail_with_carriage, Alignment.BOTTOM
        )
        joined_extruder_cage = joined_extruder_cage.cut(carriage_cutter)
        for name, cutter in mgn7h_rail_with_carriage.get_named_cutter_items():
            if name.startswith("rail_mount_hole_"):
                cutter_bbox = get_bounding_box(cutter)
                _logger.info(
                    f"Cutting extruder cage with {name}, bbox: {point_string(cutter_bbox[0])} to {point_string(cutter_bbox[1])}"
                )

                clearance_cutter = create_cylinder(
                    MScrew.from_size("M2").clearance_hole_close / 2, 50
                )
                clearance_cutter = rotate(90, axis=[1, 0, 0])(clearance_cutter)
                clearance_cutter = align(clearance_cutter, cutter, Alignment.CENTER)
                clearance_cutter = align(
                    clearance_cutter, back_plate, Alignment.CENTER, axes=[1]
                )

                back_plate = back_plate.cut(clearance_cutter)

                m2_nut_cutter = create_nut("M2", slack=0.3, no_hole=True)
                m2_nut_cutter = rotate(90, axis=[1, 0, 0])(m2_nut_cutter)
                m2_nut_cutter = align(m2_nut_cutter, cutter, Alignment.CENTER)
                m2_nut_cutter = align(m2_nut_cutter, back_plate, Alignment.FRONT)
                back_plate = back_plate.cut(m2_nut_cutter)

                m2_nut = create_nut("M2")
                m2_nut = rotate(90, axis=[1, 0, 0])(m2_nut)
                m2_nut = align(m2_nut, m2_nut_cutter, Alignment.CENTER)
                m2_nut = align(m2_nut, back_plate, Alignment.FRONT)

                joined_extruder_cage.add_named_non_production_part(
                    m2_nut, f"m2_nut_{name}"
                )

            else:
                _logger.info(f"Skipping cutting extruder cage with {name}")
        joined_extruder_cage = joined_extruder_cage.fuse(back_plate)

        bottom_stopper = materialize_bounding_box(
            mgn7h_rail_with_carriage,
            z_size=2,
            y_enlargement=0.5,
            x_size=carriage_size[0],
        )

        bottom_stopper = align(
            bottom_stopper, mgn7h_rail_with_carriage, Alignment.STACK_BOTTOM
        )
        joined_extruder_cage = joined_extruder_cage.fuse(bottom_stopper)

        for lr in [Alignment.LEFT, Alignment.RIGHT]:

            top_stopper_screw = create_cylinder_screw("M2", 4)

            top_stopper_screw = LeaderFollowersCuttersPart(top_stopper_screw)

            self_thread_hole_cutter = create_self_threading_hole_cutter(
                "M2", 6, core_radius_adjustment=-0.35, lead_in=True
            )
            self_thread_hole_cutter = align(
                self_thread_hole_cutter, top_stopper_screw, Alignment.CENTER
            )
            self_thread_hole_cutter = align(
                self_thread_hole_cutter, top_stopper_screw, Alignment.TOP
            )
            self_thread_hole_cutter = translate(
                0, 0, -MScrew.from_size("M2").cylinder_head_height
            )(self_thread_hole_cutter)

            top_stopper_screw.add_named_cutter(
                self_thread_hole_cutter, "self_thread_hole_cutter"
            )

            top_stopper_screw = rotate(-90, axis=[1, 0, 0])(top_stopper_screw)
            top_stopper_screw = align(
                top_stopper_screw, mgn7h_rail_with_carriage, Alignment.CENTER
            )
            top_stopper_screw = align(
                top_stopper_screw, mgn7h_rail_with_carriage, Alignment.STACK_TOP
            )
            top_stopper_screw = align(
                top_stopper_screw,
                mgn7h_rail_with_carriage,
                lr.stack_alignment,
                stack_gap=0.3,
            )
            top_stopper_screw = align(
                top_stopper_screw, carriage_cutter, Alignment.STACK_FRONT
            )
            top_stopper_screw = translate(
                0, MScrew.from_size("M2").cylinder_head_height, 0
            )(top_stopper_screw)

            joined_extruder_cage.add_named_non_production_part(
                top_stopper_screw.leader, f"top_stopper_screw_{lr.name.lower()}"
            )

            joined_extruder_cage = joined_extruder_cage.cut(
                top_stopper_screw.get_named_cutter("self_thread_hole_cutter")
            )

        magnet_holder_outputs = add_magnet_screw_holders(
            extruder_cage=joined_extruder_cage,
            idex_tap_t1=joined_idex_tap_t1,
            carriage=carriage,
        )
        joined_extruder_cage = magnet_holder_outputs["extruder_cage"]
        joined_idex_tap_t1 = magnet_holder_outputs["idex_tap_t1"]

    if opb991t11z_sensor is not None:

        holder = materialize_bounding_box(
            opb991t11z_sensor, x_enlargement=1.5, y_size=3.2, z_enlargement=4.0
        )
        holder = align(holder, sprite_extruder, Alignment.STACK_FRONT, stack_gap=0.5)
        holder = opb991t11z_sensor.use_as_cutter_on(holder)

        joined_extruder_cage = joined_extruder_cage.fuse(holder)

    return {
        "extruder_cage": joined_extruder_cage,
        "idex_tap_t1": joined_idex_tap_t1,
    }


def main():
    logging.basicConfig(level=logging.INFO)

    carriage = create_box(16.65, 6.5, 30.8)

    tap_shield = create_box(60, 4, 30.8)
    tap_shield = align(tap_shield, carriage, Alignment.CENTER)
    tap_shield = align(tap_shield, carriage, Alignment.STACK_BACK)
    idex_tap_t1 = LeaderFollowersCuttersPart(tap_shield)

    cage_shield = create_box(60, 3, 34)
    cage_shield = align(cage_shield, carriage, Alignment.CENTER)
    cage_shield = align(cage_shield, carriage, Alignment.STACK_FRONT)
    extruder_cage = LeaderFollowersCuttersPart(cage_shield)

    outputs = add_magnet_screw_holders(
        extruder_cage=extruder_cage,
        idex_tap_t1=idex_tap_t1,
        carriage=carriage,
    )

    parts = PartList()
    if True:
        parts.add(outputs["extruder_cage"].leader, "extruder_cage_shield", flip=False)
        parts.add(outputs["idex_tap_t1"].leader, "tap_shield", flip=False)
        for name, part in outputs[
            "extruder_cage"
        ].get_named_non_production_part_items():
            parts.add(part, f"extruder_cage_{name}", flip=False)
        for name, part in outputs["idex_tap_t1"].get_named_non_production_part_items():
            parts.add(part, f"tap_{name}", flip=False)

    magnet_srew_stack = create_magnet_screw_assembly()

    magnet_srew_stack = align(
        magnet_srew_stack,
        outputs["idex_tap_t1"].leader,
        Alignment.STACK_RIGHT,
        stack_gap=50,
    )

    parts.add(magnet_srew_stack.leader, "magnet_screw_stack", flip=False)
    for name, part in magnet_srew_stack.get_named_non_production_part_items():
        parts.add(part, f"magnet_screw_stack_{name}", flip=False)

    magnet_srew_stack_2 = rotate(180 + 45, axis=[1, 0, 0])(magnet_srew_stack)
    magnet_srew_stack_2 = align(
        magnet_srew_stack_2, magnet_srew_stack, Alignment.CENTER
    )

    magnet_srew_stack_2 = align(
        magnet_srew_stack_2,
        magnet_srew_stack,
        Alignment.STACK_RIGHT,
        stack_gap=20,
    )

    parts.add(magnet_srew_stack_2.leader, "magnet_screw_stack_2", flip=False)
    for name, part in magnet_srew_stack_2.get_named_non_production_part_items():
        parts.add(part, f"magnet_screw_stack_2_{name}", flip=False)

    # screw_assembly  = create_complete_screw_assembly(
    #     "M2",
    #     12,
    #     ScrewType.CYLINDER_HEAD,
    #     hole_type=HoleType.SELF_THREADING,
    #     core_radius_adjustment=-0.35,
    #     lead_in=True,
    #     hole_distance_from_head=2,
    #     with_access_hole=True,
    #     extra_access_hole_length = 10,
    #     access_hole_clearance = 0.3
    # )

    # parts.add(screw_assembly.leader, "demo_screw_assembly", flip=False)
    # for name, part in screw_assembly.get_named_non_production_part_items():
    #     parts.add(part, f"demo_screw_assembly_{name}", flip=False)

    # for name, cutter in screw_assembly.get_named_cutter_items():
    #     parts.add(cutter, f"demo_screw_assembly_{name}_cutter", flip=False)

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=False,
    )

    _logger.info("Tap magnet screw holder demo created successfully")


if __name__ == "__main__":
    main()
