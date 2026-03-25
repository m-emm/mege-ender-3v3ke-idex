"""
Print Bed Undercarriage

Usage:
    cd <project_root> && ./run.sh path/to/print_bed_undercarriage.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/print_bed_undercarriage.py
"""

import copy
import logging
import math
import os

import numpy as np
from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt_belt_clamp
from mege_ender_3v3ke_idex.designs.hollow_profiles import (
    create_hollow_profile,
    create_hollow_profile_ring,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.metrics_collector import (
    Material,
    log_metrics_report,
    record_length_metric,
    record_weight_metric,
    reset_metrics,
)
from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12ca_carriage
from mege_ender_3v3ke_idex.designs.print_bed import (
    Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
    create_print_bed,
)
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (  # noqa: F401
    create_four_screws_mount_assembly,
    create_screw_mount_assembly,
)
from shellforgepy.simple import *

print_bed_undercarriage_profiles_height = 30
print_bed_undercarriage_profiles_width = 12
print_bed_undercarriage_profiles_wall = 1.8

print_bed_undercarriage_central_annulus_diameter = 90

print_bed_undercarriage_mount_tower_annulus_diameter = 110


print_bed_undercarriage_bed_mount_annulus_diameter = 60

print_bed_mount_tower_size = 20
print_bed_mount_tower_height = print_bed_undercarriage_profiles_height
print_bed_mount_tower_clearance = 0.2
print_bed_mount_tower_screw_size = "M5"
print_bed_mount_tower_screw_length = 10

print_bed_undercarriage_mount_tower_holder_size = 30
print_bed_undercarriage_mount_tower_holder_fillet_radius = 5
print_bed_undercarriage_mount_tower_holder_mount_screw_size = "M5"

print_bed_undercarriage_num_dovetails_per_side = 3
print_bed_undercarriage_dovetail_width = 10

print_bed_undercarriage_dovetail_clearance = 0.2
print_bed_undercarriage_dovetail_parts_clearance = 0.05
print_bed_undercarriage_dovetail_box_size_y = 2 * print_bed_undercarriage_profiles_wall

print_bed_undercarriage_outside_flange_size = 15
print_bed_undercarriage_joining_screw_size = "M3"
print_bed_undercarriage_joining_screw_length = 14
print_bed_undercarriage_joining_screw_nut_clearance = 0.2
print_bed_undercarriage_joining_screw_cylinder_head_clearance = 0.5
print_bed_undercarriage_joining_screw_inset = 5

print_bed_undercarriage_belt_clamp_base_thickness = 5
print_bed_undercarriage_belt_clamp_clamp_thickness = (
    print_bed_undercarriage_profiles_width * 0.4
)

print_bed_undercarriage_belt_clamp_clamp_length = 30
print_bed_undercarriage_belt_clamp_x_offset = 0.5

print_bed_undercarriage_dovetail_front_clearance = 0.2

print_bed_undercarriage_carriage_mount_plate_thickness = 5
print_bed_undercarriage_carriage_mount_plate_oversize = 4
print_bed_undercarriage_belt_clamp_screw_hole_border = 4
print_bed_undercarriage_torsion_rib_size = 7
print_bed_undercarriage_torsion_rib_height = 52
print_bed_undercarriage_torsion_rib_fillet_radius = 1.5


print_bed_undercarriage_torsion_screw_size = "M3"
print_bed_undercarriage_torsion_screw_length = 50

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"


PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF_04_HS)
PROCESS_DATA["process_overrides"].update(
    {
        "brim_type": "no_brim",
        "enable_support": "1",
        "support_object_first_layer_gap": 0.8,
        # "external_perimeter_speed": "75",
        # "fan_max_speed": "25",
        # "fan_min_speed": "10",
        # "outer_wall_speed": "75",
        "sparse_infill_density": "75%",
        "support_critical_regions_only": "1",
        "support_interface_spacing": "0.8",
        "support_object_xy_distance": "1.0",
        "support_on_build_plate_only": "1",
        "support_threshold_angle": "30",
        "support_top_z_distance": "0.3",
        "wall_loops": "3",
    }
)


def _record_print_bed_undercarriage_weight_metrics(undercarriage):
    record_weight_metric(
        Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
        Material.PETG_CF,
        get_volume(undercarriage.get_leader_as_part()),
        part_id="print_bed_undercarriage_fused",
    )

    mount_tower_volume_mm3 = 0.0
    for name, part in undercarriage.get_named_non_production_part_items():
        if not name.startswith("mount_tower_"):
            continue
        mount_tower_volume_mm3 += get_volume(part)

    if mount_tower_volume_mm3 > 0:
        record_weight_metric(
            Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
            Material.ALUMINUM,
            mount_tower_volume_mm3,
            part_id="print_bed_mount_towers",
        )


def create_print_bed_undercarriage(print_bed, *, record_metrics=True):
    """Create the print_bed_undercarriage part."""

    central_annulus = create_hollow_profile_ring(
        outer_diameter=print_bed_undercarriage_central_annulus_diameter,
        profile_depth=print_bed_undercarriage_profiles_width,
        profile_height=print_bed_undercarriage_profiles_height,
        wall_thickness=print_bed_undercarriage_profiles_wall,
    )

    central_annulus = align(central_annulus, print_bed, Alignment.CENTER)

    annulus_z_aligner = align_translation(
        central_annulus,
        print_bed.get_non_production_part_by_name("damper_left_front"),
        Alignment.STACK_BOTTOM,
    )

    central_annulus = annulus_z_aligner(central_annulus)
    mount_square_placeholder = create_box(
        print_bed_mount_hole_pitch, print_bed_mount_hole_pitch, 1
    )

    mount_square_placeholder = align(
        mount_square_placeholder, central_annulus, Alignment.CENTER
    )

    outer_frame = PartCollector()

    for alignment, angle in (
        (Alignment.EDGE_FRONT, 0),
        (Alignment.EDGE_RIGHT, 90),
        (Alignment.EDGE_BACK, 180),
        (Alignment.EDGE_LEFT, 270),
    ):
        profile = create_hollow_profile(
            profile_length=print_bed_mount_hole_pitch - print_bed_mount_tower_size,
            prifile_depth=print_bed_undercarriage_profiles_width,
            profile_height=print_bed_undercarriage_profiles_height,
            wall_thickness=print_bed_undercarriage_profiles_wall,
        )

        profile = rotate(angle)(profile)
        profile = align(profile, central_annulus, Alignment.CENTER)
        profile = align(profile, mount_square_placeholder, alignment)
        outer_frame = outer_frame.fuse(profile)

    undercarriage = central_annulus.fuse(outer_frame)

    half_diagonal = math.sqrt(2) * (print_bed_mount_hole_pitch) / 2

    diagonal_profile_length = (
        half_diagonal
        - print_bed_undercarriage_central_annulus_diameter / 2
        - print_bed_undercarriage_mount_tower_annulus_diameter / 2
        + 4 * print_bed_undercarriage_profiles_wall
    )

    diagonal_profiles = PartCollector()
    for i in range(4):
        angle = 45 + i * 90

        profile = create_hollow_profile(
            profile_length=diagonal_profile_length,
            prifile_depth=print_bed_undercarriage_profiles_width,
            profile_height=print_bed_undercarriage_profiles_height,
            wall_thickness=print_bed_undercarriage_profiles_wall,
        )

        profile = translate(
            print_bed_undercarriage_central_annulus_diameter / 2
            - print_bed_undercarriage_profiles_wall,
            -print_bed_undercarriage_profiles_width / 2,
            0,
        )(profile)
        profile = rotate(angle)(profile)
        diagonal_profiles = diagonal_profiles.fuse(profile)

    diagonal_profiles = align(diagonal_profiles, central_annulus, Alignment.CENTER)

    undercarriage = undercarriage.fuse(diagonal_profiles)

    all_mount_annulus = PartCollector()
    for i in range(4):

        angle = i * 90

        mount_annulus = create_hollow_profile_ring(
            outer_diameter=print_bed_undercarriage_mount_tower_annulus_diameter,
            profile_depth=print_bed_undercarriage_profiles_width,
            profile_height=print_bed_undercarriage_profiles_height,
            wall_thickness=print_bed_undercarriage_profiles_wall,
            angle=90,
        )
        mount_annulus = rotate(180)(mount_annulus)

        mount_annulus = translate(
            print_bed_mount_hole_pitch / 2, print_bed_mount_hole_pitch / 2, 0
        )(mount_annulus)

        mount_annulus = rotate(angle)(mount_annulus)

        all_mount_annulus = all_mount_annulus.fuse(mount_annulus)

    all_mount_annulus = align(all_mount_annulus, central_annulus, Alignment.CENTER)
    undercarriage = undercarriage.fuse(all_mount_annulus)

    straight_profile_length = (
        print_bed_mount_hole_pitch / 2
        - print_bed_undercarriage_central_annulus_diameter / 2
        + 2 * print_bed_undercarriage_profiles_wall
    )
    straight_profile_center_wall_length = straight_profile_length

    straight_profile_center_wall_length = (
        straight_profile_length
        + print_bed_undercarriage_profiles_width
        + print_bed_undercarriage_profiles_wall
    )

    dovetail_pitch = (
        straight_profile_length + print_bed_undercarriage_profiles_width
    ) / (print_bed_undercarriage_num_dovetails_per_side)

    flange_part_length = (
        straight_profile_length
        - dovetail_pitch / 2
        + print_bed_undercarriage_outside_flange_size
        + print_bed_undercarriage_profiles_width
    )
    flange_part_gap_lentgth = (
        flange_part_length
        - print_bed_undercarriage_outside_flange_size
        - dovetail_pitch
    )

    straight_profiles = PartCollector()
    mount_screw_assemblies_list = []
    msc_names = set()
    for i in range(4):
        angle = i * 90
        straight_profile = create_hollow_profile(
            profile_length=straight_profile_length,
            prifile_depth=print_bed_undercarriage_profiles_width,
            profile_height=print_bed_undercarriage_profiles_height,
            wall_thickness=print_bed_undercarriage_profiles_wall,
        )

        straight_profile_wall = create_box(
            straight_profile_center_wall_length,
            2 * print_bed_undercarriage_profiles_wall,
            print_bed_undercarriage_profiles_height,
        )
        straight_profile_wall = align(
            straight_profile_wall, straight_profile, Alignment.CENTER
        )
        straight_profile_wall = align(
            straight_profile_wall, straight_profile, Alignment.RIGHT
        )
        straight_profile_wall = translate(
            2 * print_bed_undercarriage_profiles_wall, 0, 0
        )(straight_profile_wall)

        straight_profile = straight_profile.fuse(straight_profile_wall)

        flange_part = create_box(
            flange_part_length,
            print_bed_undercarriage_profiles_width,
            print_bed_undercarriage_profiles_height,
        )
        flange_part = align(flange_part, straight_profile, Alignment.CENTER)
        flange_part = align(flange_part, straight_profile, Alignment.RIGHT)
        flange_part = translate(print_bed_undercarriage_outside_flange_size, 0, 0)(
            flange_part
        )

        mount_screw_assembly = create_four_screws_mount_assembly(
            flange_part,
            screw_size=print_bed_undercarriage_joining_screw_size,
            screw_length=print_bed_undercarriage_joining_screw_length,
            screw_direction=Alignment.FRONT,
            with_nut_cutter=True,
            nut_cutter_clearance=print_bed_undercarriage_joining_screw_nut_clearance,
            cylinder_head_cutter_clearance=print_bed_undercarriage_joining_screw_cylinder_head_clearance,
            width_inset=print_bed_undercarriage_joining_screw_inset,
            length_inset=print_bed_undercarriage_joining_screw_inset,
            clearance_type="loose",
        )

        msc_name = f"flange_mount_screw_assembly_{i}"
        if msc_name in msc_names:
            raise ValueError(f"Duplicate mount screw assembly name: {msc_name}")

        mount_screw_assembly = mount_screw_assembly.prefixed_copy(msc_name)
        msc_names.add(msc_name)

        mount_screw_assemblies_list.append(mount_screw_assembly)

        flange_part = mount_screw_assembly.use_as_cutter_on(flange_part)
        straight_profile = mount_screw_assembly.use_as_cutter_on(straight_profile)

        flange_part_gap_cutter = create_box(
            flange_part_gap_lentgth, BIG_THING, BIG_THING
        )
        flange_part_gap_cutter = align(
            flange_part_gap_cutter, flange_part, Alignment.CENTER
        )
        flange_part_gap_cutter = align(
            flange_part_gap_cutter, flange_part, Alignment.LEFT
        )
        flange_part_gap_cutter = translate(dovetail_pitch, 0, 0)(flange_part_gap_cutter)
        flange_part = flange_part.cut(flange_part_gap_cutter)

        straight_profile = straight_profile.fuse(flange_part)

        straight_profile = LeaderFollowersCuttersPart(straight_profile)
        straight_profile = straight_profile.merge_except_leader(mount_screw_assembly)

        straight_profile_translator = translate(
            print_bed_undercarriage_central_annulus_diameter / 2
            - print_bed_undercarriage_profiles_wall,
            -print_bed_undercarriage_profiles_width / 2,
            0,
        )
        straight_profile, flange_part, mount_screw_assembly = [
            straight_profile_translator(part)
            for part in (straight_profile, flange_part, mount_screw_assembly)
        ]

        rotator = rotate(angle)
        straight_profile, flange_part, mount_screw_assembly = [
            rotator(part)
            for part in (straight_profile, flange_part, mount_screw_assembly)
        ]

        straight_profiles = straight_profiles.fuse(straight_profile)

    straight_profiles = align(straight_profiles, central_annulus, Alignment.CENTER)
    undercarriage = LeaderFollowersCuttersPart(undercarriage)

    undercarriage = undercarriage.fuse(straight_profiles)

    carriages_map = {}
    carriages_fused = PartCollector()

    for fb in [Alignment.FRONT, Alignment.BACK]:
        for lr in [Alignment.LEFT, Alignment.RIGHT]:

            carriage = create_mgn12ca_carriage()
            carriage = rotate(90)(carriage)

            carriage = translate(
                lr.sign * y_axis_rail_spacing / 2,
                fb.sign * y_axis_carriage_spacing / 2,
                0,
            )(carriage)

            carriage_name = f"carriage_{fb.name.lower()}_{lr.name.lower()}"

            carriages_map[carriage_name] = carriage

            carriage = carriage.prefixed_copy(
                f"carriage_{fb.name.lower()}_{lr.name.lower()}"
            )

            carriages_fused = carriages_fused.fuse(carriage)

    carriages_aligner_1 = align_translation(
        carriages_fused, central_annulus, Alignment.CENTER
    )

    carriages_fused = carriages_aligner_1(carriages_fused)
    carriages_aligner_2 = align_translation(
        carriages_fused, central_annulus, Alignment.STACK_BOTTOM
    )
    carriages_fused = carriages_aligner_2(carriages_fused)

    new_carriages_map = {}
    for name, carriage in carriages_map.items():
        carriage = carriages_aligner_1(carriage)
        carriage = carriages_aligner_2(carriage)
        new_carriages_map[name] = carriage

    mount_plates = PartCollector()
    for name, carriage in new_carriages_map.items():

        carriage_size = get_bounding_box_size(carriage)
        carriage_mount_plate = create_box(
            carriage_size[0]
            + 2 * print_bed_undercarriage_carriage_mount_plate_oversize,
            carriage_size[1]
            + 2 * print_bed_undercarriage_carriage_mount_plate_oversize,
            print_bed_undercarriage_profiles_height,
        )
        carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.CENTER)
        carriage_mount_plate = align(
            carriage_mount_plate, carriage, Alignment.STACK_TOP
        )

        carriage_mount_plate = carriage.use_as_cutter_on(carriage_mount_plate)
        carriage_mount_plate_size = get_bounding_box_size(carriage_mount_plate)

        inner_cutter = create_box(
            carriage_mount_plate_size[0] - 2 * print_bed_undercarriage_profiles_wall,
            carriage_mount_plate_size[1] - 2 * print_bed_undercarriage_profiles_wall,
            BIG_THING,
        )
        inner_cutter = align(inner_cutter, carriage_mount_plate, Alignment.CENTER)
        inner_cutter = align(inner_cutter, carriage_mount_plate, Alignment.BOTTOM)
        inner_cutter = translate(
            0, 0, print_bed_undercarriage_carriage_mount_plate_thickness
        )(inner_cutter)

        carriage_mount_plate = carriage_mount_plate.cut(inner_cutter)

        mount_plates = mount_plates.fuse(carriage_mount_plate)

    undercarriage = undercarriage.fuse(mount_plates)

    retval = undercarriage

    # for mount_screw_assembly in mount_screw_assemblies_list:
    #     for name, npp in mount_screw_assembly.get_named_non_production_part_items():
    #         retval.add_named_non_production_part(npp, name)

    for name, npp in print_bed.get_named_non_production_part_items():
        if not name.startswith("damper_"):
            continue

        mount_tower_name = f"mount_tower_{name.replace('damper_', '', 1)}"
        if record_metrics:
            record_length_metric(
                "extrusion_profile",
                ExtrusionProfileType.PROFILE_2020.value,
                mount_tower_name,
                print_bed_mount_tower_height,
            )
        mount_tower = create_alu_extrusion_profile(
            ExtrusionProfileType.PROFILE_2020, length_mm=print_bed_mount_tower_height
        )
        mount_tower = align(mount_tower, npp, Alignment.CENTER)
        mount_tower = align(mount_tower, npp, Alignment.STACK_BOTTOM)

        retval.add_named_non_production_part(mount_tower, mount_tower_name)

        mount_tower_holder = create_filleted_box(
            print_bed_undercarriage_mount_tower_holder_size,
            print_bed_undercarriage_mount_tower_holder_size,
            print_bed_undercarriage_profiles_height,
            fillet_radius=print_bed_undercarriage_mount_tower_holder_fillet_radius,
            no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
        )
        mount_tower_cutter = create_box(
            print_bed_mount_tower_size + 2 * print_bed_mount_tower_clearance,
            print_bed_mount_tower_size + 2 * print_bed_mount_tower_clearance,
            BIG_THING,
        )
        mount_tower_cutter = align(
            mount_tower_cutter, mount_tower_holder, Alignment.CENTER
        )
        mount_tower_holder = mount_tower_holder.cut(mount_tower_cutter)

        for p in [0, 1]:
            mount_tower_screw_cutter = create_cylinder(
                MScrew.from_size(print_bed_mount_tower_screw_size).clearance_hole_loose
                / 2,
                BIG_THING,
            )

            mount_tower_screw_cutter = rotate(90, axis=(0, 1, 0))(
                mount_tower_screw_cutter
            )
            if p == 0:
                mount_tower_screw_cutter = rotate(90)(mount_tower_screw_cutter)

            mount_tower_screw_cutter = align(
                mount_tower_screw_cutter, mount_tower_holder, Alignment.CENTER
            )
            mount_tower_holder = mount_tower_holder.cut(mount_tower_screw_cutter)

        mount_tower_holder = align(mount_tower_holder, mount_tower, Alignment.CENTER)

        retval = retval.fuse(mount_tower_holder)

    belt_clamp_bases = PartCollector()
    for k in [Alignment.FRONT, Alignment.BACK]:

        belt_clamp = create_gt_belt_clamp(
            base_thicknness=print_bed_undercarriage_belt_clamp_base_thickness,
            clamp_thickness=print_bed_undercarriage_belt_clamp_clamp_thickness,
            clamp_length=print_bed_undercarriage_belt_clamp_clamp_length,
            screw_hole_border=print_bed_undercarriage_belt_clamp_screw_hole_border,
        )
        belt_clamp = rotate(90, axis=(1, 0, 0))(belt_clamp)
        belt_clamp = rotate(90)(belt_clamp)
        belt_clamp = align(belt_clamp, central_annulus, Alignment.CENTER)
        belt_clamp = align(belt_clamp, central_annulus, Alignment.STACK_BOTTOM)

        belt_clamp = translate(
            -print_bed_undercarriage_belt_clamp_base_thickness / 2
            + print_bed_undercarriage_belt_clamp_x_offset,
            k.sign
            * (
                print_bed_undercarriage_central_annulus_diameter / 2
                + print_bed_undercarriage_belt_clamp_clamp_length / 2
                - print_bed_undercarriage_profiles_width
            ),
            0,
        )(belt_clamp)

        current_clamp_base = belt_clamp.get_follower_part_by_name("clamp")
        belt_clamp_bases = belt_clamp_bases.fuse(current_clamp_base)

        belt_clamp_torsion_rib = create_filleted_box(
            print_bed_undercarriage_torsion_rib_size,
            print_bed_undercarriage_torsion_rib_size,
            print_bed_undercarriage_torsion_rib_height,
            print_bed_undercarriage_torsion_rib_fillet_radius,
            no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.LEFT],
        )

        belt_clamp_torsion_rib = align(
            belt_clamp_torsion_rib, current_clamp_base, Alignment.CENTER
        )
        belt_clamp_torsion_rib = align(belt_clamp_torsion_rib, retval, Alignment.TOP)
        belt_clamp_torsion_rib = align(
            belt_clamp_torsion_rib, current_clamp_base, Alignment.STACK_RIGHT
        )

        screw_mount_assembly = create_screw_mount_assembly(
            belt_clamp_torsion_rib,
            print_bed_undercarriage_torsion_screw_size,
            print_bed_undercarriage_torsion_screw_length,
            Alignment.TOP,
            flush_with_top=True,
        )
        belt_clamp_torsion_rib = screw_mount_assembly.use_as_cutter_on(
            belt_clamp_torsion_rib
        )

        retval.add_named_non_production_part(
            screw_mount_assembly.get_non_production_part_by_name("screw"),
            f"belt_clamp_torsion_screw_{k.name.lower()}",
        )
        belt_clamp_bases = belt_clamp_bases.fuse(belt_clamp_torsion_rib)

        retval.add_named_follower(
            belt_clamp.leader,
            f"belt_clamp_clamp_{k.name.lower()}",
        )
        retval.add_named_cutter(
            belt_clamp.get_follower_part_by_name("belt_path_cutter"),
            f"belt_path_cutter_{k.name.lower()}",
        )

    undercarriage_with_belt_clamps = retval.fuse(belt_clamp_bases)

    left_uc, right_uc = cut_in_two(undercarriage_with_belt_clamps, cut_normal=(1, 0, 0))

    back_left_uc, front_left_uc = cut_in_two(left_uc, cut_normal=(0, 1, 0))

    back_right_uc, front_right_uc = cut_in_two(right_uc, cut_normal=(0, 1, 0))

    uc_parts = [front_left_uc, front_right_uc, back_right_uc, back_left_uc]

    all_dovetails_fused = PartCollector()
    all_dovetails_list = []
    all_prefixed_dovetails_list = []
    for i, uc in enumerate(uc_parts):
        for k in range(print_bed_undercarriage_num_dovetails_per_side):
            dovetail = create_dovetail_tongue_and_groove(
                dovetail_width=print_bed_undercarriage_dovetail_width,
                length=print_bed_undercarriage_profiles_height,
                box_size_x=1.5 * print_bed_undercarriage_dovetail_width,
                box_size_y=print_bed_undercarriage_dovetail_box_size_y,
                taper_per_side=1.5,
                dovetail_clearance=print_bed_undercarriage_dovetail_clearance,
                parts_clearance=print_bed_undercarriage_dovetail_parts_clearance,
                groove_box_size_y=print_bed_undercarriage_dovetail_box_size_y
                + print_bed_undercarriage_dovetail_front_clearance
                + print_bed_undercarriage_profiles_wall,
                front_wall_clearance=print_bed_undercarriage_dovetail_front_clearance,
            )

            dovetail = translate(
                print_bed_undercarriage_central_annulus_diameter / 2
                + k * dovetail_pitch,
                0,
                0,
            )(dovetail)
            dovetail = rotate(-i * 90)(dovetail)
            all_dovetails_list.append(dovetail)
            dovetail = dovetail.prefixed_copy(f"uc_{i}_dovetail_{k}")
            all_prefixed_dovetails_list.append(dovetail)
            all_dovetails_fused = all_dovetails_fused.fuse(dovetail)

    dovetails_aligner = align_translation(
        all_dovetails_fused,
        central_annulus,
        Alignment.CENTER,
    )

    all_dovetails_list = [
        dovetails_aligner(dovetail) for dovetail in all_dovetails_list
    ]

    dovetail_counter = 0
    uc_dovetailed_parts = []
    for i, uc in enumerate(uc_parts):
        previous_uc_index = (i - 1) % len(uc_parts)

        for k in range(print_bed_undercarriage_num_dovetails_per_side):
            dovetail = all_dovetails_list[dovetail_counter]
            dovetail_counter += 1

            uc_parts[previous_uc_index] = dovetail.use_as_cutter_on(
                uc_parts[previous_uc_index]
            )
            groove_part = dovetail.get_follower_part_by_name("groove_part")
            groove_part = undercarriage.use_as_cutter_on(groove_part)
            uc_parts[previous_uc_index] = uc_parts[previous_uc_index].fuse(groove_part)

            uc_parts[i] = uc_parts[i].fuse(dovetail.leader)

    front_left_uc, front_right_uc, back_right_uc, back_left_uc = uc_parts

    retval.add_named_follower(front_left_uc.leader, "front_left_uc")
    retval.add_named_follower(front_right_uc.leader, "front_right_uc")
    retval.add_named_follower(back_left_uc.leader, "back_left_uc")
    retval.add_named_follower(back_right_uc.leader, "back_right_uc")

    if record_metrics:
        _record_print_bed_undercarriage_weight_metrics(retval)

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    reset_metrics()
    parts = PartList()

    print_bed = create_print_bed()

    # Create the part
    undercarriage = create_print_bed_undercarriage(print_bed)

    # undercarriage = scale(0.33)(undercarriage) # small prototype

    cut_normal = [1, 1, 0]
    # print_bed, _ = cut_in_two(print_bed, cut_normal=cut_normal)
    # undercarriage_cut, _ = cut_in_two(undercarriage, cut_normal=cut_normal)

    # parts.add(print_bed, "print_bed", flip=False, skip_in_production=True)
    # npps_fused = PartCollector()
    for name, npp in print_bed.get_named_non_production_part_items():

        if "foil" in name:
            continue

        parts.add(npp, name, flip=False, skip_in_production=True)
        # npps_fused = npps_fused.fuse(npp)

    # npps_fused, _ = cut_in_two(npps_fused, cut_normal=cut_normal)
    # parts.add(npps_fused, "print_bed_npps", flip=False, skip_in_production=True)

    # parts.add(undercarriage_cut, "print_bed_undercarriage", flip=False)

    uc_center = get_bounding_box_center(undercarriage)

    explosion_factor = 0.001

    # parts.add(
    #     undercarriage, "print_bed_undercarriage", flip=False, skip_in_production=False
    # )

    for name, follower in undercarriage.get_named_follower_items():

        skip_in_production = True

        if name in ("front_left_uc"):
            skip_in_production = False

        follower_center = get_bounding_box_center(follower)

        translation_vector = np.array(follower_center) - np.array(uc_center)
        translation_vector = translation_vector * explosion_factor

        follower = translate(*translation_vector)(follower)

        parts.add(follower, name, flip=True, skip_in_production=skip_in_production)

    for name, npp in undercarriage.get_named_non_production_part_items():
        if "nut" in name:
            continue
        npp_center = get_bounding_box_center(npp)
        translation_vector = np.array(npp_center) - np.array(uc_center)
        translation_vector = translation_vector * explosion_factor
        npp = translate(*translation_vector)(npp)

        parts.add(npp, name, flip=False, skip_in_production=True)

    log_metrics_report(_logger)
    _logger.info(
        "The print bed undercarriage contributes PETG_CF fused structure and aluminum mount towers "
        "to y_axis_moving_mass. Dampers are currently excluded."
    )

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        export_stl=PROD,
        export_individual_parts=False,
    )

    _logger.info("print_bed_undercarriage created successfully!")


if __name__ == "__main__":
    main()
