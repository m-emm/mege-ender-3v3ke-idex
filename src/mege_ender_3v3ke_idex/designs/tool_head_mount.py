"""
Tool Head Mount

Usage:
    cd <project_root> && ./run.sh path/to/tool_head_mount.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/tool_head_mount.py
"""

import copy
import logging
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt_belt_clamp
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.mgh_linear import (
    create_mgn12h_carriage,
    create_mgn12h_rail,
)
from mege_ender_3v3ke_idex.designs.sprite_extruder import create_sprite_extruder
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"


_logger = logging.getLogger(__name__)

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF_04_HS)
PROCESS_DATA["process_overrides"].update(
    {
        "brim_type": "no_brim",
        "enable_support": "1",
        "external_perimeter_speed": "75",
        "fan_max_speed": "25",
        "fan_min_speed": "10",
        "outer_wall_speed": "75",
        "sparse_infill_density": "75%",
        "support_critical_regions_only": "1",
        "support_interface_spacing": "0.8",
        "support_on_build_plate_only": "1",
        "support_threshold_angle": "30",
        "support_top_z_distance": "0.3",
        "wall_loops": "3",
    }
)


def create_tool_head_mount(target_profile):

    carriage = create_mgn12h_carriage()
    carriage_size = get_bounding_box_size(carriage)

    dummy_rail = create_mgn12h_rail(length_mm=10)

    carriage_rail_fused = carriage.fuse(dummy_rail)
    rail_plus_carriage = LeaderFollowersCuttersPart(
        carriage_rail_fused, followers=[dummy_rail, carriage]
    )
    rail_plus_carriage = align(
        rail_plus_carriage, target_profile, Alignment.CENTER, axes=[0, 1]
    )
    rail_plus_carriage = align(rail_plus_carriage, target_profile, Alignment.STACK_TOP)

    carriage = rail_plus_carriage.followers[1]

    tool_head_mount_base_plate_width = (
        tool_head_mount_carriage_mount_plate_width
        - 2 * tool_head_mount_side_plate_thickness
    )

    clamp_1 = create_gt_belt_clamp(
        base_thicknness=tool_head_mount_belt_clamp_base_thickness,
        clamp_thickness=tool_head_mount_belt_clamp_thickness,
        clamp_length=tool_head_mount_belt_clamp_length,
        screw_size="M3",
        screw_hole_border=1.9,
        teeth_clearance=0.1,
        single_screw=True,
        extra_scew_hole_clearance=0.2,
    )
    clamp_1 = rotate(90, axis=(1, 0, 0))(clamp_1)
    clamp_1 = rotate(90)(clamp_1)

    carriage_mount_plate = create_filleted_box(
        tool_head_mount_carriage_mount_plate_width,
        carriage_size[1] + tool_head_mount_y_extension,
        tool_head_mount_carriage_mount_plate_thickness,
        fillet_radius=tool_head_mount_carriage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM],
    )

    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.CENTER)
    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.STACK_TOP)
    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.BACK)
    carriage_mount_plate = carriage.use_as_cutter_on(carriage_mount_plate)

    extruder_cutout = create_filleted_box(
        tool_head_mount_extruder_cutout_width,
        BIG_THING,
        BIG_THING,
        fillet_radius=tool_head_mount_extruder_cutout_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    extruder_cutout = align(extruder_cutout, carriage_mount_plate, Alignment.CENTER)
    extruder_cutout = align(
        extruder_cutout,
        carriage,
        Alignment.STACK_FRONT,
        stack_gap=tool_head_mount_extruder_cutout_carriage_gap,
    )
    carriage_mount_plate = carriage_mount_plate.cut(extruder_cutout)

    mount_base_plate = create_box(
        tool_head_mount_base_plate_width,
        tool_head_mount_base_plate_thickness,
        tool_head_mount_base_plate_height,
    )

    mount_base_plate = align(mount_base_plate, carriage_mount_plate, Alignment.CENTER)
    mount_base_plate = align(
        mount_base_plate, carriage_mount_plate, Alignment.STACK_BOTTOM
    )
    mount_base_plate = align(
        mount_base_plate,
        carriage,
        Alignment.STACK_FRONT,
        stack_gap=tool_head_mount_plate_carriage_clearance,
    )

    side_plates = PartCollector()
    side_plate_stiffeners = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        side_plate = create_filleted_box(
            tool_head_mount_side_plate_thickness,
            tool_head_mount_side_plate_depth,
            tool_head_mount_side_plate_height,
            fillet_radius=tool_head_mount_carriage_mount_plate_fillet_radius,
            no_fillets_at=[Alignment.TOP, lr.opposite],
        )

        side_plate = align(side_plate, carriage_mount_plate, Alignment.STACK_BOTTOM)
        side_plate = align(side_plate, carriage_mount_plate, Alignment.FRONT)
        side_plate = align(side_plate, carriage_mount_plate, lr)

        side_plate_stiffener = create_right_triangle(
            carriage_size[2],
            carriage_size[2],
            tool_head_mount_side_stiffener_thickness,
            extrusion_direction=(1, 0, 0),
            a_normal=(0, -1, 0),
            b_normal=(0, 0, -1),
        )
        side_plate_stiffener = align(side_plate_stiffener, side_plate, Alignment.CENTER)
        side_plate_stiffener = align(
            side_plate_stiffener, carriage_mount_plate, Alignment.STACK_BOTTOM
        )
        side_plate_stiffener = align(
            side_plate_stiffener,
            side_plate,
            Alignment.STACK_BACK,
            stack_gap=-tool_head_mount_carriage_mount_plate_fillet_radius,
        )
        side_plate_stiffener = align(side_plate_stiffener, carriage_mount_plate, lr)

        side_plate_stiffeners = side_plate_stiffeners.fuse(side_plate_stiffener)

        side_plates = side_plates.fuse(side_plate)

    clamp_1 = align(clamp_1, mount_base_plate, Alignment.CENTER, axes=[0])
    clamp_1 = align(clamp_1, side_plates, Alignment.BACK)

    clamp_1 = align(clamp_1, side_plates, Alignment.STACK_LEFT)

    clamp_1 = align(clamp_1, target_profile, Alignment.CENTER, axes=[2])

    clamp_1_center = get_bounding_box_center(clamp_1)
    clamp_2 = rotate(180, axis=(0, 1, 0), center=clamp_1_center)(clamp_1)

    clamp_2 = align(clamp_2, side_plates, Alignment.STACK_RIGHT)

    clamp = LeaderFollowersCuttersPart(leader=clamp_1.leader.fuse(clamp_2.leader))

    clamp.add_named_follower(clamp_1.get_follower_part_by_name("clamp"), "clamp_1")
    clamp.add_named_follower(clamp_2.get_follower_part_by_name("clamp"), "clamp_2")
    clamp.add_named_follower(clamp_1.leader, "belt_clamp_base_1")
    clamp.add_named_follower(clamp_2.leader, "belt_clamp_base_2")
    clamp.add_named_follower(
        clamp_1.get_follower_part_by_name("belt_path_cutter"), "belt_path_cutter_1"
    )
    clamp.add_named_follower(
        clamp_2.get_follower_part_by_name("belt_path_cutter"), "belt_path_cutter_2"
    )

    clamp = clamp.aligned_from_follower("clamp_1", side_plates, Alignment.BACK)
    clamp = translate(0, -tool_head_mount_belt_clamp_y_offset, 0)(clamp)

    clamps_list = [
        clamp.get_follower_part_by_name("clamp_1"),
        clamp.get_follower_part_by_name("clamp_2"),
    ]
    bases_list = [
        clamp.get_follower_part_by_name("belt_clamp_base_1"),
        clamp.get_follower_part_by_name("belt_clamp_base_2"),
    ]

    belt_path_cutters_list = [
        clamp.get_follower_part_by_name("belt_path_cutter_1"),
        clamp.get_follower_part_by_name("belt_path_cutter_2"),
    ]

    clamps_fused = clamp.get_follower_part_by_name("clamp_1").fuse(
        clamp.get_follower_part_by_name("clamp_2")
    )

    clamp_cutter = PartCollector()
    bases_cutter = PartCollector()
    belt_path_cutter = PartCollector()
    belt_deflectors = PartCollector()
    for current_clamp, current_base, current_belt_path_cutter, clamp_side in zip(
        clamps_list,
        bases_list,
        belt_path_cutters_list,
        [Alignment.LEFT, Alignment.RIGHT],
    ):
        current_clamp_size = get_bounding_box_size(current_clamp)
        current_clamp_cutter = create_box(
            current_clamp_size[0],
            current_clamp_size[1],
            current_clamp_size[2],
        )
        current_clamp_cutter = align(
            current_clamp_cutter, current_clamp, Alignment.CENTER
        )
        clamp_cutter = clamp_cutter.fuse(current_clamp_cutter)

        current_base_size = get_bounding_box_size(current_base)
        current_base_cutter = create_box(
            BIG_THING,
            current_base_size[1] + 2 * tool_head_mount_clamp_base_cutter_clearance,
            current_base_size[2],
        )
        current_base_cutter = align(current_base_cutter, current_base, Alignment.CENTER)
        current_base_cutter = align(current_base_cutter, current_base, Alignment.BACK)

        bases_cutter = bases_cutter.fuse(current_base_cutter)

        curent_belt_path_cutter_size = get_bounding_box_size(current_belt_path_cutter)
        current_belt_path_cutter_enlarged = create_box(
            curent_belt_path_cutter_size[0]
            + 2 * tool_head_mount_belt_path_cutter_clearance,
            curent_belt_path_cutter_size[1]
            + 2 * tool_head_mount_belt_path_cutter_clearance,
            curent_belt_path_cutter_size[2]
            + 2 * tool_head_mount_belt_path_cutter_clearance,
        )
        current_belt_path_cutter_enlarged = align(
            current_belt_path_cutter_enlarged,
            current_belt_path_cutter,
            Alignment.CENTER,
        )

        belt_path_cutter = belt_path_cutter.fuse(current_belt_path_cutter_enlarged)

        belt_deflector = create_box(
            tool_head_mount_belt_deflector_thickness,
            BIG_THING,
            curent_belt_path_cutter_size[2],
        )
        belt_deflector = align(
            belt_deflector, current_belt_path_cutter, Alignment.CENTER
        )
        belt_deflector = align(
            belt_deflector,
            target_profile,
            Alignment.STACK_FRONT,
            stack_gap=-tool_head_mount_belt_deflector_into_profile_distance,
        )

        belt_deflector_trimmer = create_box(
            BIG_THING + 10, BIG_THING + 10, BIG_THING + 10
        )
        belt_deflector_trimmer = align(
            belt_deflector_trimmer, belt_deflector, Alignment.CENTER
        )
        belt_deflector_trimmer = align(
            belt_deflector_trimmer, side_plates, Alignment.BACK
        )
        belt_deflector = belt_deflector.cut(belt_deflector_trimmer)

        belt_deflector = align(
            belt_deflector,
            side_plates,
            clamp_side.stack_alignment,
            stack_gap=tool_head_mount_belt_deflector_belt_clearance,
        )

        bdc_x_size = (
            tool_head_mount_belt_deflector_belt_clearance
            + tool_head_mount_belt_deflector_thickness
            + tool_head_mount_belt_deflector_cage_thickness
        )
        bdc_y_size = 2 * tool_head_mount_belt_deflector_cage_thickness
        bdc_z_size = (
            curent_belt_path_cutter_size[2]
            + 2 * tool_head_mount_belt_deflector_cage_thickness
        )

        belt_deflector_cage = create_box(
            bdc_x_size,
            bdc_y_size,
            bdc_z_size,
        )
        bdc_cutter = create_box(
            bdc_x_size - tool_head_mount_belt_deflector_cage_thickness,
            bdc_y_size - tool_head_mount_belt_deflector_cage_thickness,
            bdc_z_size
            - 2 * tool_head_mount_belt_deflector_cage_thickness
            + 2 * tool_head_mount_belt_path_cutter_clearance,
        )
        bdc_cutter = align(bdc_cutter, belt_deflector_cage, Alignment.CENTER)
        bdc_cutter = align(bdc_cutter, belt_deflector_cage, Alignment.FRONT)
        bdc_cutter = align(bdc_cutter, belt_deflector_cage, clamp_side.opposite)
        belt_deflector_cage = belt_deflector_cage.cut(bdc_cutter)

        belt_deflector_cage = align(
            belt_deflector_cage, belt_deflector, Alignment.CENTER
        )
        belt_deflector_cage = align(
            belt_deflector_cage, belt_deflector, Alignment.STACK_FRONT
        )
        belt_deflector_cage = align(
            belt_deflector_cage, side_plates, clamp_side.stack_alignment
        )

        bcd_belt_path_cutter = create_box(
            tool_head_mount_belt_deflector_belt_clearance,
            BIG_THING,
            curent_belt_path_cutter_size[2]
            + 2 * tool_head_mount_belt_path_cutter_clearance,
        )
        bcd_belt_path_cutter = align(
            bcd_belt_path_cutter, belt_deflector, Alignment.CENTER
        )
        bcd_belt_path_cutter = align(
            bcd_belt_path_cutter,
            belt_deflector,
            clamp_side.opposite.stack_alignment,
        )

        belt_deflector_cage = belt_deflector_cage.cut(bcd_belt_path_cutter)

        if False:

            bdc_size = get_bounding_box_size(belt_deflector_cage)
            belt_deflector_cage_print_helper = create_right_triangle(
                bdc_size[0],
                bdc_size[0],
                bdc_size[1],
                extrusion_direction=(0, 1, 0),
                a_normal=(0, 0, -1),
                b_normal=(clamp_side.sign, 0, 0),
            )
            belt_deflector_cage_print_helper = align(
                belt_deflector_cage_print_helper, belt_deflector_cage, Alignment.CENTER
            )
            belt_deflector_cage_print_helper = align(
                belt_deflector_cage_print_helper,
                belt_deflector_cage,
                Alignment.STACK_TOP,
            )

            print_helper_factor = 0.6
            belt_deflector_print_helper = create_right_triangle(
                bdc_y_size * print_helper_factor,
                bdc_y_size * print_helper_factor,
                tool_head_mount_belt_deflector_thickness,
                extrusion_direction=(1, 0, 0),
                a_normal=(0, 0, -1),
                b_normal=(0, 1, 0),
            )

            belt_deflector_print_helper = align(
                belt_deflector_print_helper, belt_deflector, Alignment.CENTER
            )
            belt_deflector_print_helper = align(
                belt_deflector_print_helper, belt_deflector, Alignment.STACK_TOP
            )
            belt_deflector_print_helper = align(
                belt_deflector_print_helper,
                belt_deflector_cage_print_helper,
                Alignment.STACK_BACK,
            )

        belt_deflectors = belt_deflectors.fuse(belt_deflector)
        belt_deflectors = belt_deflectors.fuse(belt_deflector_cage)
        # belt_deflectors = belt_deflectors.fuse(belt_deflector_cage_print_helper)
        # belt_deflectors = belt_deflectors.fuse(belt_deflector_print_helper)

    side_plates = side_plates.cut(clamp_cutter)

    mount_base_plate = mount_base_plate.cut(clamp_cutter)
    mount_base_plate = mount_base_plate.cut(bases_cutter)

    sprite_extruder = create_sprite_extruder()
    sprite_extruder = rotate(180)(sprite_extruder)

    sprite_extruder = align(sprite_extruder, target_profile, Alignment.TOP)
    sprite_extruder = align(
        sprite_extruder,
        mount_base_plate,
        Alignment.STACK_FRONT,
        stack_gap=tool_head_mount_tool_head_base_plate_clearance,
    )

    sprite_extruder = translate(
        tool_head_mount_tool_head_x_offset, 0, tool_head_mount_tool_head_z_offset
    )(sprite_extruder)

    mount_base_plate = sprite_extruder.use_as_cutter_on(mount_base_plate)

    extruder_cutout = create_filleted_box(
        tool_head_mount_extruder_cutout_width,
        BIG_THING,
        BIG_THING,
        fillet_radius=tool_head_mount_extruder_cutout_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    extruder_cutout = align(extruder_cutout, carriage_mount_plate, Alignment.CENTER)

    extruder_cutout = align(extruder_cutout, sprite_extruder, Alignment.RIGHT)

    extruder_cutout = align(
        extruder_cutout,
        carriage,
        Alignment.STACK_FRONT,
        stack_gap=tool_head_mount_extruder_cutout_carriage_gap,
    )
    carriage_mount_plate = carriage_mount_plate.cut(extruder_cutout)

    tool_head_mount = carriage_mount_plate.fuse(clamps_fused)
    tool_head_mount = tool_head_mount.fuse(belt_deflectors)

    tool_head_mount = tool_head_mount.fuse(mount_base_plate)
    side_plates = side_plates.cut(bases_cutter)
    side_plates = side_plates.cut(belt_path_cutter)

    tool_head_mount = tool_head_mount.fuse(side_plates)
    tool_head_mount = tool_head_mount.fuse(side_plate_stiffeners)

    tool_head_mount = LeaderFollowersCuttersPart(leader=tool_head_mount)
    tool_head_mount.add_named_follower(clamp.leader, "belt_clamp_base")
    tool_head_mount.add_named_follower(
        clamp.get_follower_part_by_name("belt_clamp_base_1"), "belt_clamp_base_1"
    )
    tool_head_mount.add_named_follower(
        clamp.get_follower_part_by_name("belt_clamp_base_2"), "belt_clamp_base_2"
    )

    return tool_head_mount, carriage, sprite_extruder


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    test_axis_length = 150

    lower_axis_profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_2020, length_mm=test_axis_length
    )
    lower_axis_profile = rotate(90, axis=(0, 1, 0))(lower_axis_profile)

    parts.add(
        lower_axis_profile, "lower_axis_profile", flip=False, skip_in_production=True
    )

    rail = create_mgn12h_rail(length_mm=test_axis_length - 20)

    carriages = []
    for i in [-1, 1]:
        carriage = create_mgn12h_carriage()
        carriage = align(carriage, rail, Alignment.CENTER, axes=[0, 1])
        carriage = translate(i * 20, 0, 0)(carriage)
        carriages.append(carriage)

    for i, carriage in enumerate(carriages):
        rail.add_named_follower(carriage, f"carriage_{i+1}")
    rail_with_carriages = rail

    rail_with_carriages = align(
        rail_with_carriages, lower_axis_profile, Alignment.CENTER, axes=[0, 1]
    )
    rail_with_carriages = align(
        rail_with_carriages, lower_axis_profile, Alignment.STACK_TOP
    )

    parts.add(
        rail_with_carriages.leader,
        "rail_with_carriages",
        flip=False,
        skip_in_production=True,
    )

    # Create the part
    tool_head_mount, carriage_1, sprite_extruder_1 = create_tool_head_mount(
        lower_axis_profile
    )

    parts.add(carriage_1, "carriage_1", flip=False, skip_in_production=True)

    show_sprite_extruder = True
    if show_sprite_extruder:
        parts.add(
            sprite_extruder_1, "sprite_extruder", flip=False, skip_in_production=True
        )

        for name, npp in sprite_extruder_1.get_named_non_production_part_items():
            parts.add(npp, name, flip=False, skip_in_production=True)

    # tool_head_mount = align(
    #     tool_head_mount,
    #     carriage_1,
    #     Alignment.CENTER,
    # )
    # tool_head_mount = align(
    #     tool_head_mount,
    #     carriage_1,
    #     Alignment.BACK,
    # )
    # tool_head_mount = align(
    #     tool_head_mount,
    #     carriage_1,
    #     Alignment.TOP,
    # )
    # tool_head_mount = translate(0, 0, tool_head_mount_carriage_mount_plate_thickness)(
    #     tool_head_mount
    # )

    parts.add(
        tool_head_mount,
        "tool_head_mount",
        flip=True,
        # prod_rotation_angle=-45,
        # prod_rotation_axis=(1, 0, 0),
        skip_in_production=False,
    )

    belt_clamp_base_1 = tool_head_mount.get_named_follower("belt_clamp_base_1")
    parts.add(
        belt_clamp_base_1,
        "belt_clamp_base_1",
        flip=False,
        prod_rotation_angle=-90,
        prod_rotation_axis=(0, 1, 0),
    )

    belt_clamp_base_2 = tool_head_mount.get_named_follower("belt_clamp_base_2")
    parts.add(
        belt_clamp_base_2,
        "belt_clamp_base_2",
        flip=False,
        prod_rotation_angle=90,
        prod_rotation_axis=(0, 1, 0),
    )

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        prod_gap=8,
    )

    _logger.info("tool_head_mount created successfully!")


if __name__ == "__main__":
    main()
