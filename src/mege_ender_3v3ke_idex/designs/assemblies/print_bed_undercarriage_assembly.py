"""Declarative print bed undercarriage assembly."""

import logging
import math

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt_belt_clamp
from mege_ender_3v3ke_idex.designs.hollow_profiles import (
    create_hollow_profile,
    create_hollow_profile_ring,
)
from mege_ender_3v3ke_idex.designs.metrics_collector import (
    Material,
    record_length_metric,
    record_weight_metric,
)
from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12ca_carriage
from mege_ender_3v3ke_idex.designs.print_bed import Y_AXIS_MOVING_MASS_ASSEMBLY_ID
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
    create_screw_mount_assembly,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


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


def create_print_bed_undercarriage_assembly(
    *,
    print_bed,
    damper_left_front,
    damper_left_back,
    damper_right_front,
    damper_right_back,
    print_bed_mount_hole_pitch,
    y_axis_rail_spacing,
    y_axis_carriage_spacing,
    print_bed_undercarriage_profiles_height,
    print_bed_undercarriage_profiles_width,
    print_bed_undercarriage_profiles_wall,
    print_bed_undercarriage_central_annulus_diameter,
    print_bed_undercarriage_mount_tower_annulus_diameter,
    print_bed_mount_tower_size,
    print_bed_mount_tower_height,
    print_bed_mount_tower_clearance,
    print_bed_mount_tower_screw_size,
    print_bed_undercarriage_mount_tower_holder_size,
    print_bed_undercarriage_mount_tower_holder_fillet_radius,
    print_bed_undercarriage_num_dovetails_per_side,
    print_bed_undercarriage_dovetail_width,
    print_bed_undercarriage_dovetail_clearance,
    print_bed_undercarriage_dovetail_parts_clearance,
    print_bed_undercarriage_dovetail_box_size_y,
    print_bed_undercarriage_outside_flange_size,
    print_bed_undercarriage_joining_screw_size,
    print_bed_undercarriage_joining_screw_length,
    print_bed_undercarriage_joining_screw_nut_clearance,
    print_bed_undercarriage_joining_screw_cylinder_head_clearance,
    print_bed_undercarriage_joining_screw_inset,
    print_bed_undercarriage_belt_clamp_base_thickness,
    print_bed_undercarriage_belt_clamp_clamp_thickness,
    print_bed_undercarriage_belt_clamp_clamp_length,
    print_bed_undercarriage_belt_clamp_x_offset,
    print_bed_undercarriage_dovetail_front_clearance,
    print_bed_undercarriage_carriage_mount_plate_thickness,
    print_bed_undercarriage_carriage_mount_plate_oversize,
    print_bed_undercarriage_belt_clamp_screw_hole_border,
    print_bed_undercarriage_torsion_rib_size,
    print_bed_undercarriage_torsion_rib_height,
    print_bed_undercarriage_torsion_rib_fillet_radius,
    print_bed_undercarriage_torsion_screw_size,
    print_bed_undercarriage_torsion_screw_length,
    record_metrics=False,
    context=None,
):
    """Create the print bed undercarriage assembly."""

    big_thing = (context or {}).get("BIG_THING", 500)
    dampers_by_name = {
        "damper_left_front": damper_left_front,
        "damper_left_back": damper_left_back,
        "damper_right_front": damper_right_front,
        "damper_right_back": damper_right_back,
    }

    central_annulus = create_hollow_profile_ring(
        outer_diameter=print_bed_undercarriage_central_annulus_diameter,
        profile_depth=print_bed_undercarriage_profiles_width,
        profile_height=print_bed_undercarriage_profiles_height,
        wall_thickness=print_bed_undercarriage_profiles_wall,
    )
    central_annulus = align(central_annulus, print_bed, Alignment.CENTER)

    annulus_z_aligner = align_translation(
        central_annulus,
        damper_left_front,
        Alignment.STACK_BOTTOM,
    )
    central_annulus = annulus_z_aligner(central_annulus)

    mount_square_placeholder = create_box(
        print_bed_mount_hole_pitch,
        print_bed_mount_hole_pitch,
        1,
    )
    mount_square_placeholder = align(
        mount_square_placeholder,
        central_annulus,
        Alignment.CENTER,
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

    half_diagonal = math.sqrt(2) * print_bed_mount_hole_pitch / 2
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
            print_bed_mount_hole_pitch / 2,
            print_bed_mount_hole_pitch / 2,
            0,
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
    straight_profile_center_wall_length = (
        straight_profile_length
        + print_bed_undercarriage_profiles_width
        + print_bed_undercarriage_profiles_wall
    )
    dovetail_pitch = (
        straight_profile_length + print_bed_undercarriage_profiles_width
    ) / print_bed_undercarriage_num_dovetails_per_side
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
            straight_profile_wall,
            straight_profile,
            Alignment.CENTER,
        )
        straight_profile_wall = align(
            straight_profile_wall,
            straight_profile,
            Alignment.RIGHT,
        )
        straight_profile_wall = translate(
            2 * print_bed_undercarriage_profiles_wall,
            0,
            0,
        )(straight_profile_wall)
        straight_profile = straight_profile.fuse(straight_profile_wall)

        flange_part = create_box(
            flange_part_length,
            print_bed_undercarriage_profiles_width,
            print_bed_undercarriage_profiles_height,
        )
        flange_part = align(flange_part, straight_profile, Alignment.CENTER)
        flange_part = align(flange_part, straight_profile, Alignment.RIGHT)
        flange_part = translate(
            print_bed_undercarriage_outside_flange_size,
            0,
            0,
        )(flange_part)

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
        mount_screw_assembly = mount_screw_assembly.prefixed_copy(
            f"flange_mount_screw_assembly_{i}"
        )

        flange_part = mount_screw_assembly.use_as_cutter_on(flange_part)
        straight_profile = mount_screw_assembly.use_as_cutter_on(straight_profile)

        flange_part_gap_cutter = create_box(
            flange_part_gap_lentgth,
            big_thing,
            big_thing,
        )
        flange_part_gap_cutter = align(
            flange_part_gap_cutter,
            flange_part,
            Alignment.CENTER,
        )
        flange_part_gap_cutter = align(
            flange_part_gap_cutter,
            flange_part,
            Alignment.LEFT,
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
        straight_profile = straight_profile_translator(straight_profile)
        straight_profile = rotate(angle)(straight_profile)
        straight_profiles = straight_profiles.fuse(straight_profile)

    straight_profiles = align(straight_profiles, central_annulus, Alignment.CENTER)
    retval = LeaderFollowersCuttersPart(undercarriage).fuse(straight_profiles)

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
            carriages_fused = carriages_fused.fuse(
                carriage.prefixed_copy(carriage_name)
            )

    carriages_aligner_1 = align_translation(
        carriages_fused,
        central_annulus,
        Alignment.CENTER,
    )
    carriages_fused = carriages_aligner_1(carriages_fused)
    carriages_aligner_2 = align_translation(
        carriages_fused,
        central_annulus,
        Alignment.STACK_BOTTOM,
    )
    carriages_fused = carriages_aligner_2(carriages_fused)

    new_carriages_map = {}
    for name, carriage in carriages_map.items():
        carriage = carriages_aligner_1(carriage)
        carriage = carriages_aligner_2(carriage)
        new_carriages_map[name] = carriage

    mount_plates = PartCollector()
    for carriage in new_carriages_map.values():
        carriage_size = get_bounding_box_size(carriage)
        carriage_mount_plate = create_box(
            carriage_size[0]
            + 2 * print_bed_undercarriage_carriage_mount_plate_oversize,
            carriage_size[1]
            + 2 * print_bed_undercarriage_carriage_mount_plate_oversize,
            print_bed_undercarriage_profiles_height,
        )
        carriage_mount_plate = align(
            carriage_mount_plate,
            carriage,
            Alignment.CENTER,
        )
        carriage_mount_plate = align(
            carriage_mount_plate,
            carriage,
            Alignment.STACK_TOP,
        )
        carriage_mount_plate = carriage.use_as_cutter_on(carriage_mount_plate)
        carriage_mount_plate_size = get_bounding_box_size(carriage_mount_plate)

        inner_cutter = create_box(
            carriage_mount_plate_size[0] - 2 * print_bed_undercarriage_profiles_wall,
            carriage_mount_plate_size[1] - 2 * print_bed_undercarriage_profiles_wall,
            big_thing,
        )
        inner_cutter = align(inner_cutter, carriage_mount_plate, Alignment.CENTER)
        inner_cutter = align(inner_cutter, carriage_mount_plate, Alignment.BOTTOM)
        inner_cutter = translate(
            0,
            0,
            print_bed_undercarriage_carriage_mount_plate_thickness,
        )(inner_cutter)

        carriage_mount_plate = carriage_mount_plate.cut(inner_cutter)
        mount_plates = mount_plates.fuse(carriage_mount_plate)

    retval = retval.fuse(mount_plates)

    for name, npp in dampers_by_name.items():
        mount_tower_name = f"mount_tower_{name.replace('damper_', '', 1)}"
        if record_metrics:
            record_length_metric(
                "extrusion_profile",
                ExtrusionProfileType.PROFILE_2020.value,
                mount_tower_name,
                print_bed_mount_tower_height,
            )

        mount_tower = create_alu_extrusion_profile(
            ExtrusionProfileType.PROFILE_2020,
            length_mm=print_bed_mount_tower_height,
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
            big_thing,
        )
        mount_tower_cutter = align(
            mount_tower_cutter,
            mount_tower_holder,
            Alignment.CENTER,
        )
        mount_tower_holder = mount_tower_holder.cut(mount_tower_cutter)

        for orientation in range(2):
            mount_tower_screw_cutter = create_cylinder(
                MScrew.from_size(print_bed_mount_tower_screw_size).clearance_hole_loose
                / 2,
                big_thing,
            )
            mount_tower_screw_cutter = rotate(90, axis=(0, 1, 0))(
                mount_tower_screw_cutter
            )
            if orientation == 0:
                mount_tower_screw_cutter = rotate(90)(mount_tower_screw_cutter)
            mount_tower_screw_cutter = align(
                mount_tower_screw_cutter,
                mount_tower_holder,
                Alignment.CENTER,
            )
            mount_tower_holder = mount_tower_holder.cut(mount_tower_screw_cutter)

        mount_tower_holder = align(
            mount_tower_holder,
            mount_tower,
            Alignment.CENTER,
        )
        retval = retval.fuse(mount_tower_holder)

    belt_clamp_bases = PartCollector()
    for side in [Alignment.FRONT, Alignment.BACK]:
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
            side.sign
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
            belt_clamp_torsion_rib,
            current_clamp_base,
            Alignment.CENTER,
        )
        belt_clamp_torsion_rib = align(belt_clamp_torsion_rib, retval, Alignment.TOP)
        belt_clamp_torsion_rib = align(
            belt_clamp_torsion_rib,
            current_clamp_base,
            Alignment.STACK_RIGHT,
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
            f"belt_clamp_torsion_screw_{side.name.lower()}",
        )
        belt_clamp_bases = belt_clamp_bases.fuse(belt_clamp_torsion_rib)

        retval.add_named_follower(
            belt_clamp.leader,
            f"belt_clamp_clamp_{side.name.lower()}",
        )
        retval.add_named_cutter(
            belt_clamp.get_follower_part_by_name("belt_path_cutter"),
            f"belt_path_cutter_{side.name.lower()}",
        )

    undercarriage_with_belt_clamps = retval.fuse(belt_clamp_bases)

    left_uc, right_uc = cut_in_two(
        undercarriage_with_belt_clamps,
        cut_normal=(1, 0, 0),
    )
    back_left_uc, front_left_uc = cut_in_two(left_uc, cut_normal=(0, 1, 0))
    back_right_uc, front_right_uc = cut_in_two(right_uc, cut_normal=(0, 1, 0))

    uc_parts = [front_left_uc, front_right_uc, back_right_uc, back_left_uc]

    all_dovetails_fused = PartCollector()
    all_dovetails_list = []
    for i, _ in enumerate(uc_parts):
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
            all_dovetails_fused = all_dovetails_fused.fuse(
                dovetail.prefixed_copy(f"uc_{i}_dovetail_{k}")
            )

    dovetails_aligner = align_translation(
        all_dovetails_fused,
        central_annulus,
        Alignment.CENTER,
    )
    all_dovetails_list = [
        dovetails_aligner(dovetail) for dovetail in all_dovetails_list
    ]

    dovetail_counter = 0
    for i, _ in enumerate(uc_parts):
        previous_uc_index = (i - 1) % len(uc_parts)
        for _ in range(print_bed_undercarriage_num_dovetails_per_side):
            dovetail = all_dovetails_list[dovetail_counter]
            dovetail_counter += 1

            uc_parts[previous_uc_index] = dovetail.use_as_cutter_on(
                uc_parts[previous_uc_index]
            )
            groove_part = dovetail.get_follower_part_by_name("groove_part")
            groove_part = retval.use_as_cutter_on(groove_part)
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
