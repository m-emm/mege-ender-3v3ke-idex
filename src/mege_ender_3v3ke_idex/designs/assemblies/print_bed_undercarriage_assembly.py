"""Declarative print bed undercarriage assembly."""

import logging
import math

import numpy as np
from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt_belt_clamp
from mege_ender_3v3ke_idex.designs.hollow_profiles import (
    create_hollow_profile,
    create_hollow_profile_ring,
)
from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12ca_carriage
from mege_ender_3v3ke_idex.designs.print_bed import Y_AXIS_MOVING_MASS_ASSEMBLY_ID
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
    create_screw_mount_assembly,
)
from shellforgepy.metrics import Material, record_length_metric, record_weight_metric
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


def _create_print_bed_adjustment_wheel(
    screw_size,
    *,
    total_diameter,
    hub_diameter,
    hub_thickness,
    outer_disc_thickness,
    grip_diameter,
    grip_count,
    nut_pocket_slack,
):
    mount_screw = MScrew.from_size(screw_size)
    if total_diameter <= grip_diameter:
        raise ValueError(
            "print_bed_adjustment_wheel_total_diameter must exceed grip diameter"
        )
    if hub_thickness <= mount_screw.nut_thickness:
        raise ValueError(
            "print_bed_adjustment_wheel_hub_thickness must exceed nut thickness"
        )
    if grip_count < 1:
        raise ValueError("print_bed_adjustment_wheel_grip_count must be positive")

    outer_disc_diameter = total_diameter - grip_diameter

    outer_disc = create_cylinder(
        outer_disc_diameter / 2,
        outer_disc_thickness,
    )
    center_disc = create_cylinder(
        hub_diameter / 2,
        hub_thickness,
    )
    center_disc = align(center_disc, outer_disc, Alignment.CENTER, axes=[0, 1])
    center_disc = align(center_disc, outer_disc, Alignment.BOTTOM)

    grips = PartCollector()
    outer_disc_center = get_bounding_box_center(outer_disc)
    for i in range(grip_count):
        current_grip = create_cylinder(
            grip_diameter / 2,
            outer_disc_thickness,
        )
        current_grip = align(current_grip, outer_disc, Alignment.CENTER)
        current_grip = align(
            current_grip,
            outer_disc,
            Alignment.EDGE_RIGHT,
        )
        current_grip = rotate(
            i * 360 / grip_count,
            center=outer_disc_center,
        )(current_grip)
        grips = grips.fuse(current_grip)

    adjustment_wheel = outer_disc.fuse(grips)

    # adjustment_wheel = apply_fillet_by_alignment(
    #     adjustment_wheel, 0.5, fillets_at= [Alignment.BOTTOM, Alignment.TOP]
    # )

    adjustment_wheel = adjustment_wheel.fuse(center_disc)

    nut_pocket = create_nut(
        screw_size,
        slack=nut_pocket_slack,
        no_hole=True,
    )
    nut_pocket = align(nut_pocket, adjustment_wheel, Alignment.CENTER, axes=[0, 1])
    nut_pocket = align(nut_pocket, adjustment_wheel, Alignment.BOTTOM)

    screw_hole = create_cylinder(
        mount_screw.get_clearance_hole_diameter(clearance_type="loose") / 2,
        hub_thickness,
    )
    screw_hole = align(screw_hole, adjustment_wheel, Alignment.CENTER, axes=[0, 1])
    screw_hole = align(screw_hole, adjustment_wheel, Alignment.BOTTOM)

    adjustment_wheel = adjustment_wheel.cut(nut_pocket)
    adjustment_wheel = adjustment_wheel.cut(screw_hole)

    nut = create_nut(screw_size)
    nut = align(nut, adjustment_wheel, Alignment.CENTER, axes=[0, 1])
    nut = align(nut, adjustment_wheel, Alignment.BOTTOM)

    return adjustment_wheel, nut


def _record_print_bed_undercarriage_weight_metrics(undercarriage):
    record_weight_metric(
        Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
        Material.PETG_CF,
        get_volume(undercarriage.get_leader_as_part()),
        part_id="print_bed_undercarriage_fused",
    )

    mount_tower_volume_mm3 = 0.0
    screw_volume_mm3 = 0.0
    for name, part in undercarriage.get_named_non_production_part_items():
        if not name.startswith("mount_tower_"):
            if "screw" in name:
                screw_volume_mm3 += get_volume(part)
            continue
        mount_tower_volume_mm3 += get_volume(part)

    if mount_tower_volume_mm3 > 0:
        record_weight_metric(
            Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
            Material.ALUMINUM,
            mount_tower_volume_mm3,
            part_id="print_bed_mount_towers",
        )

    if screw_volume_mm3 > 0:
        record_weight_metric(
            Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
            Material.STEEL,
            screw_volume_mm3,
            part_id="print_bed_undercarriage_screws",
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
    print_bed_undercarriage_dovetail_profiles_width,
    print_bed_undercarriage_profiles_wall,
    print_bed_undercarriage_central_annulus_diameter,
    print_bed_undercarriage_mount_tower_annulus_diameter,
    print_bed_mount_tower_size,
    print_bed_mount_tower_height,
    print_bed_mount_tower_clearance,
    print_bed_mount_tower_screw_size,
    print_bed_mount_screw_size,
    print_bed_adjustment_wheel_total_diameter,
    print_bed_adjustment_wheel_hub_diameter,
    print_bed_adjustment_wheel_hub_thickness,
    print_bed_adjustment_wheel_outer_disc_thickness,
    print_bed_adjustment_wheel_grip_diameter,
    print_bed_adjustment_wheel_grip_count,
    print_bed_adjustment_wheel_nut_pocket_slack,
    print_bed_undercarriage_mount_tower_holder_size,
    print_bed_undercarriage_mount_tower_holder_fillet_radius,
    print_bed_undercarriage_num_dovetails_per_side,
    print_bed_undercarriage_dovetail_width,
    print_bed_undercarriage_dovetail_clearance,
    print_bed_undercarriage_dovetail_parts_clearance,
    print_bed_undercarriage_dovetail_box_size_y,
    print_bed_undercarriage_dovetail_groove_box_size_x,
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
    print_bed_undercarriage_carriage_mount_plate_x_oversize,
    print_bed_undercarriage_carriage_mount_plate_y_oversize,
    print_bed_undercarriage_belt_clamp_screw_hole_border,
    print_bed_undercarriage_torsion_rib_size,
    print_bed_undercarriage_torsion_rib_height,
    print_bed_undercarriage_torsion_rib_fillet_radius,
    print_bed_undercarriage_torsion_screw_size,
    print_bed_undercarriage_torsion_screw_length,
    print_bed_undercarriage_screw_mount_clearance_type,
    print_bed_undercarriage_profiles_fillet_radius,
    print_bed_undercarriage_carriage_mount_plate_wall,
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
    dampers_center = np.mean(
        [get_bounding_box_center(damper) for damper in dampers_by_name.values()],
        axis=0,
    )

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
    dovetail_pitch = (
        straight_profile_length
        - print_bed_undercarriage_joining_screw_inset
        - print_bed_undercarriage_dovetail_width
    ) / print_bed_undercarriage_num_dovetails_per_side

    straight_profiles = None
    annnulus_center = get_bounding_box_center(central_annulus)

    for i in range(4):
        angle = i * 90
        straight_profile = create_hollow_profile(
            profile_length=straight_profile_length,
            prifile_depth=print_bed_undercarriage_dovetail_profiles_width,
            profile_height=print_bed_undercarriage_profiles_height,
            wall_thickness=print_bed_undercarriage_profiles_wall,
        )
        flange_part = create_box(
            print_bed_undercarriage_outside_flange_size,
            print_bed_undercarriage_dovetail_profiles_width,
            print_bed_undercarriage_profiles_height,
        )
        flange_part = align(flange_part, straight_profile, Alignment.CENTER)
        flange_part = align(flange_part, straight_profile, Alignment.STACK_RIGHT)

        straight_profile = straight_profile.fuse(flange_part)

        straight_profile_size = get_bounding_box_size(straight_profile)

        straight_profile_stand_in = create_box(
            straight_profile_size[0] - print_bed_undercarriage_profiles_width,
            straight_profile_size[1],
            straight_profile_size[2],
        )

        straight_profile_stand_in = align(
            straight_profile_stand_in, straight_profile, Alignment.CENTER
        )
        straight_profile_stand_in = align(
            straight_profile_stand_in, straight_profile, Alignment.RIGHT
        )

        mount_screw_assembly = create_four_screws_mount_assembly(
            straight_profile_stand_in,
            screw_size=print_bed_undercarriage_joining_screw_size,
            screw_length=print_bed_undercarriage_joining_screw_length,
            screw_direction=Alignment.FRONT,
            with_nut_cutter=True,
            nut_cutter_clearance=print_bed_undercarriage_joining_screw_nut_clearance,
            cylinder_head_cutter_clearance=print_bed_undercarriage_joining_screw_cylinder_head_clearance,
            width_inset=print_bed_undercarriage_joining_screw_inset,
            length_inset=print_bed_undercarriage_joining_screw_inset,
            clearance_type=print_bed_undercarriage_screw_mount_clearance_type,
        )

        mount_screw_assembly = mount_screw_assembly.prefixed_copy(
            f"flange_mount_screw_assembly_{i}"
        )

        for name, npp in mount_screw_assembly.get_named_non_production_part_items():
            if "screw" in name:

                screw_hole_tube = create_cylinder(
                    MScrew.from_size(
                        print_bed_undercarriage_joining_screw_size
                    ).cylinder_head_diameter
                    / 2
                    * 1.2,
                    print_bed_undercarriage_dovetail_profiles_width,
                    direction=(0, 1, 0),
                )

                screw_hole_tube = align(screw_hole_tube, npp, Alignment.CENTER)
                screw_hole_tube = align(
                    screw_hole_tube, straight_profile, Alignment.CENTER, axes=[1]
                )
                straight_profile = straight_profile.fuse(screw_hole_tube)

        straight_profile = mount_screw_assembly.use_as_cutter_on(straight_profile)
        straight_profile = LeaderFollowersCuttersPart(straight_profile)
        straight_profile = straight_profile.merge_except_leader(mount_screw_assembly)

        straight_profile_center_wall = create_box(
            straight_profile_size[0],
            print_bed_undercarriage_profiles_wall,
            straight_profile_size[2],
        )
        straight_profile_center_wall = align(
            straight_profile_center_wall, straight_profile, Alignment.CENTER
        )

        straight_profile_center_wall = mount_screw_assembly.use_as_cutter_on(
            straight_profile_center_wall
        )
        straight_profile = straight_profile.fuse(straight_profile_center_wall)

        straight_profile = align(straight_profile, central_annulus, Alignment.CENTER)
        straight_profile = align(
            straight_profile,
            central_annulus,
            Alignment.STACK_RIGHT,
            stack_gap=-print_bed_undercarriage_profiles_width,
        )

        straight_profile = rotate(angle, center=annnulus_center)(straight_profile)
        straight_profiles = (
            straight_profiles.fuse(straight_profile)
            if straight_profiles is not None
            else straight_profile
        )

    straight_profiles = align(straight_profiles, central_annulus, Alignment.CENTER)
    retval = straight_profiles.fuse(undercarriage)

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
            + 2 * print_bed_undercarriage_carriage_mount_plate_x_oversize,
            carriage_size[1]
            + 2 * print_bed_undercarriage_carriage_mount_plate_y_oversize,
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

        inner_cutter = create_filleted_box(
            carriage_mount_plate_size[0]
            - 2 * print_bed_undercarriage_carriage_mount_plate_wall,
            carriage_mount_plate_size[1]
            - 2 * print_bed_undercarriage_carriage_mount_plate_wall,
            big_thing,
            fillet_radius=print_bed_undercarriage_profiles_fillet_radius,
            no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
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

    mount_tower_holder_wall_thickness = (
        print_bed_undercarriage_mount_tower_holder_size
        - (print_bed_mount_tower_size + 2 * print_bed_mount_tower_clearance)
    ) / 2

    for name, npp in dampers_by_name.items():
        position_name = name.replace("damper_", "", 1)
        mount_tower_name = f"mount_tower_{position_name}"
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
        mount_tower_holder = LeaderFollowersCuttersPart(mount_tower_holder)
        mount_tower_holder.add_named_cutter(
            mount_tower_cutter, f"mount_tower_cutter_{name}"
        )

        relative_damper_center = (
            np.asarray(get_bounding_box_center(npp)) - dampers_center
        )
        outer_wall_alignments = [
            (
                Alignment.STACK_LEFT
                if relative_damper_center[0] <= 0
                else Alignment.STACK_RIGHT
            ),
            (
                Alignment.STACK_FRONT
                if relative_damper_center[1] <= 0
                else Alignment.STACK_BACK
            ),
        ]

        for wall_alignment in outer_wall_alignments:

            mount_tower_screw_cutter = create_cylinder(
                MScrew.from_size(print_bed_mount_tower_screw_size).clearance_hole_loose
                / 2,
                big_thing,
                direction=(
                    (1, 0, 0)
                    if wall_alignment in [Alignment.STACK_LEFT, Alignment.STACK_RIGHT]
                    else (0, 1, 0)
                ),
            )
            mount_tower_screw_cutter = align(
                mount_tower_screw_cutter,
                mount_tower_holder,
                Alignment.CENTER,
            )
            mount_tower_screw_cutter = align(
                mount_tower_screw_cutter,
                mount_tower_holder,
                wall_alignment,
                stack_gap=-1.5 * mount_tower_holder_wall_thickness,
            )
            mount_tower_holder = mount_tower_holder.cut(mount_tower_screw_cutter)

        mount_tower_holder = align(
            mount_tower_holder,
            mount_tower,
            Alignment.CENTER,
        )
        mount_tower_holder = align(
            mount_tower_holder,
            retval,
            Alignment.TOP,
        )

        retval = retval.fuse(mount_tower_holder)
        retval = mount_tower_holder.use_as_cutter_on(retval)

        adjustment_wheel, adjustment_wheel_nut = _create_print_bed_adjustment_wheel(
            print_bed_mount_screw_size,
            total_diameter=print_bed_adjustment_wheel_total_diameter,
            hub_diameter=print_bed_adjustment_wheel_hub_diameter,
            hub_thickness=print_bed_adjustment_wheel_hub_thickness,
            outer_disc_thickness=print_bed_adjustment_wheel_outer_disc_thickness,
            grip_diameter=print_bed_adjustment_wheel_grip_diameter,
            grip_count=print_bed_adjustment_wheel_grip_count,
            nut_pocket_slack=print_bed_adjustment_wheel_nut_pocket_slack,
        )
        adjustment_wheel = align(
            adjustment_wheel,
            npp,
            Alignment.CENTER,
            axes=[0, 1],
        )
        adjustment_wheel = align(
            adjustment_wheel,
            mount_tower,
            Alignment.STACK_BOTTOM,
        )
        adjustment_wheel_nut = align(
            adjustment_wheel_nut,
            adjustment_wheel,
            Alignment.CENTER,
            axes=[0, 1],
        )
        adjustment_wheel_nut = align(
            adjustment_wheel_nut,
            adjustment_wheel,
            Alignment.BOTTOM,
        )

        retval.add_named_follower(
            adjustment_wheel,
            f"adjustment_wheel_{position_name}",
        )
        retval.add_named_non_production_part(
            adjustment_wheel_nut,
            f"adjustment_wheel_nut_{position_name}",
        )

    def edge_filter(bbox, v0_point, v1_point):
        v0_point = np.array(v0_point)
        npv1_point = np.array(v1_point)
        edge_center = (v0_point + npv1_point) / 2
        edge_length = np.linalg.norm(npv1_point - v0_point)
        edge_direction = npv1_point - v0_point
        if np.allclose(edge_direction[1], 0) and np.isclose(edge_direction[0], 0):
            if not np.isclose(edge_length, print_bed_undercarriage_profiles_height):
                return False

            return True

        return False

    fillet_edges = filter_edges_by_function(retval.leader, edge_filter)
    retval.leader = apply_fillet_to_edges(
        retval.leader, print_bed_undercarriage_profiles_fillet_radius, fillet_edges
    )

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
            clearance_type=print_bed_undercarriage_screw_mount_clearance_type,
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

    right_uc, left_uc = cut_in_two(
        undercarriage_with_belt_clamps,
        cut_normal=(1, 0, 0),
    )
    back_left_uc, front_left_uc = cut_in_two(left_uc, cut_normal=(0, 1, 0))
    back_right_uc, front_right_uc = cut_in_two(right_uc, cut_normal=(0, 1, 0))

    uc_parts_in_ring_order = [
        front_right_uc,
        front_left_uc,
        back_left_uc,
        back_right_uc,
    ]

    all_dovetails_fused = PartCollector()
    all_dovetails_list = []
    annulus_center = get_bounding_box_center(central_annulus)
    for k in range(print_bed_undercarriage_num_dovetails_per_side):
        dovetail = create_dovetail_tongue_and_groove(
            dovetail_width=print_bed_undercarriage_dovetail_width,
            length=print_bed_undercarriage_profiles_height,
            box_size_x=1.5 * print_bed_undercarriage_dovetail_width,
            box_size_y=print_bed_undercarriage_dovetail_box_size_y,
            taper_per_side=1.5,
            dovetail_clearance=print_bed_undercarriage_dovetail_clearance,
            parts_clearance=print_bed_undercarriage_dovetail_parts_clearance,
            groove_box_size_x=print_bed_undercarriage_dovetail_groove_box_size_x,
            groove_box_size_y=print_bed_undercarriage_dovetail_box_size_y
            + print_bed_undercarriage_dovetail_front_clearance
            + print_bed_undercarriage_profiles_wall,
            front_wall_clearance=print_bed_undercarriage_dovetail_front_clearance,
        )
        dovetail = align(dovetail, None, Alignment.CENTER)
        dovetail = translate(
            k * dovetail_pitch,
            0,
            0,
        )(dovetail)
        all_dovetails_list.append(dovetail)
        all_dovetails_fused = all_dovetails_fused.fuse(
            dovetail.prefixed_copy(f"dovetail_{k}")
        )

    dovetails_aligner = align_translation(
        all_dovetails_fused,
        central_annulus,
        Alignment.CENTER,
    )
    all_dovetails_list = [
        dovetails_aligner(dovetail) for dovetail in all_dovetails_list
    ]
    all_dovetails_fused = dovetails_aligner(all_dovetails_fused)

    dovetail_aligner_2 = align_translation(
        all_dovetails_fused,
        central_annulus,
        Alignment.STACK_RIGHT,
        stack_gap=print_bed_undercarriage_joining_screw_inset
        + print_bed_undercarriage_dovetail_width / 2,
    )
    all_dovetails_list = [
        dovetail_aligner_2(dovetail) for dovetail in all_dovetails_list
    ]
    all_dovetails_fused = dovetail_aligner_2(all_dovetails_fused)

    dovetail_counter = 0
    for i, _ in enumerate(uc_parts_in_ring_order):

        previous_uc_index = (i - 1) % len(uc_parts_in_ring_order)

        for dovetail in all_dovetails_list:

            dovetail = rotate(-i * 90, center=annulus_center)(dovetail)

            dovetail_counter += 1

            uc_parts_in_ring_order[previous_uc_index] = dovetail.use_as_cutter_on(
                uc_parts_in_ring_order[previous_uc_index]
            )
            groove_part = dovetail.get_follower_part_by_name("groove_part")
            groove_part = retval.use_as_cutter_on(groove_part)
            uc_parts_in_ring_order[previous_uc_index] = uc_parts_in_ring_order[
                previous_uc_index
            ].fuse(groove_part)
            uc_parts_in_ring_order[i] = uc_parts_in_ring_order[i].fuse(dovetail.leader)

    front_right_uc, front_left_uc, back_left_uc, back_right_uc = uc_parts_in_ring_order
    retval.add_named_follower(front_left_uc.leader, "front_left_uc")
    retval.add_named_follower(front_right_uc.leader, "front_right_uc")
    retval.add_named_follower(back_left_uc.leader, "back_left_uc")
    retval.add_named_follower(back_right_uc.leader, "back_right_uc")

    if record_metrics:
        _record_print_bed_undercarriage_weight_metrics(retval)

    return retval
