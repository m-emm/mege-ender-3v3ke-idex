"""
X Axis

Usage:
    cd <project_root> && ./run.sh path/to/x_axis.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/x_axis.py
"""

import copy
import logging
import os
from collections import defaultdict
from pathlib import Path

from mege_3devops.process_data.mender3.process_data_08_high_speed import (
    PROCESS_DATA_PLA_08_HS,
)
from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt2_idler, create_gt2_pulley
from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

EXTUDER_STEP_PATH = PROJECT_ROOT / "resources" / "creality_sprite.step.zip"

BIG_THING = 500


PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLA_08_HS)


PROCESS_DATA["process_overrides"].update(
    {
        # ============================================================
        # SINGLE-WALL INTENT
        # ============================================================
        "wall_loops": "1",
        # Make thickness == line width everywhere that could interfere
        "line_width": "0.90",
        "outer_wall_line_width": "0.90",
        "inner_wall_line_width": "0.90",
        "thin_wall_line_width": "0.90",
        "top_surface_line_width": "0.90",
        "gap_fill_line_width": "0.90",
        # If you truly want a pure shell, consider enabling these:
        "bottom_shell_layers": "1",
        "top_shell_layers": "1",
        # ============================================================
        # LAYER HEIGHT — tuned to ~30 mm³/s at outer wall speed
        # ============================================================
        "adaptive_layer_height": "0",
        "layer_height": "0.42",
        "min_layer_height": "0.42",
        "max_layer_height": "0.42",
        # First layer: slightly fatter for adhesion (not too squished)
        "initial_layer_print_height": "0.32",
        "initial_layer_line_width": "1.00",
        # ============================================================
        # SPEEDS — volumetric-flow limited
        # With 0.90*0.42=0.378 mm²:
        # 80 mm/s => ~30.2 mm³/s
        # ============================================================
        "outer_wall_speed": "70",
        "external_perimeter_speed": "70",
        # First layer slower for stick
        "initial_layer_speed": "45",
        "initial_layer_infill_speed": "60",
        # Keep other paths consistent (not too relevant for pure shell)
        "inner_wall_speed": "150",
        "solid_infill_speed": "180",
        "sparse_infill_speed": "180",
        # Avoid slicer "gap fill" games for single-wall shells
        "gap_fill_speed": "180",
        "gap_infill_speed": "180",
        # ============================================================
        # ACCEL / JERK — tall shell stability (avoid ringing/wobble)
        # ============================================================
        "outer_wall_acceleration": "3000",
        "outer_wall_jerk": "6",
        # ============================================================
        # FLOW LIMIT — enforce the regime we designed for
        # ============================================================
        "filament_max_volumetric_speed": "30",
        # ============================================================
        # TEMPERATURE — you need more than 205C at ~30 mm³/s
        # ============================================================
        "nozzle_temperature": "230",
        "nozzle_temperature_initial_layer": "235",
        # ============================================================
        # COOLING — not 100% (helps layer welding on thick beads)
        # ============================================================
        "fan_min_speed": "70",
        "fan_max_speed": "70",
        "overhang_fan_speed": "70",
        "fan_cooling_layer_time": "8",
        "min_layer_time": "4",
        "slow_down_for_layer_cooling": "0",
        # ============================================================
        # BED / ADHESION — keep as you already do (75/75 is fine)
        # ============================================================
        "brim_width": "4",
        "brim_type": "no_brim",  # "outer_and_inner",
        "elefant_foot_compensation": "0.10",
        # ============================================================
        # RETRACTION — big nozzle needs a bit more, but keep it sane
        # ============================================================
        "filament_retraction_length": "1.2",
        "filament_retraction_speed": "40",
        "filament_deretraction_speed": "35",
        # ============================================================
        # OPTIONAL: pressure advance (keep modest for fat beads)
        # ============================================================
        "enable_pressure_advance": "1",
        "pressure_advance": "0.015",
        # ============================================================
        # OVERHANG / BRIDGE — disable overhang slowdown for draft mode
        # Let it print at full 70 mm/s outer_wall_speed throughout.
        # Only slow down for true bridges (extreme overhangs >115mm).
        # ============================================================
        "overhang_1_4_speed": "0",  # Disabled
        "overhang_2_4_speed": "0",  # Disabled - was causing ugly 55-100mm zone
        "overhang_3_4_speed": "0",  # Disabled
        "overhang_4_4_speed": "0",  # Disabled
        "bridge_speed": "35",  # Keep bridges slow when detected
        "enable_support": "0",
        "support_threshold_angle": "23",
    }
)


motor_size = 42.3
axis_profile_length = 500
rail_length = 450
axis_profile_pitch = 40
motor_y_offset = 11

z_axis_guide_distance = 256

motor_x_offset = z_axis_guide_distance / 2 - 60
x_axis_motor_axle_length = 14

idler_gap = 2


motor_mount_plate_size = 50
motor_mount_plate_depth = motor_size + motor_y_offset

motor_mount_plate_thickness = 6
motor_mount_plate_fillet_radius = 2
motor_mount_axle_clearance = 0.3
motor_mount_boss_clearance = 0.6
motor_mount_boss_clearance_z = 4

idler_mount_diameter = 4
idler_mount_thickness = 1
idler_mount_axle_clearance = 0.1
idler_mount_axle_diameter = MScrew.from_size("M3").clearance_hole_normal
axle_screw_size = "M3"
axcle_screw_nut_hole_depth = 4
axle_screw_nut_slack = 0.4

mount_shield_width = 17
mount_shield_depth = 6
mount_shield_fillet_radius = 1
mount_shield_oversize_z = 0

mount_plate_connector_length = (
    z_axis_guide_distance - 2 * motor_x_offset - motor_size + 8
)
mount_plate_connector_depth = 22

mount_plate_link_width = mount_plate_connector_length * 0.8
mount_plate_connector_link_thickness = 6

flange_thickness = 5
flange_depth = 22
bevel_depth = flange_depth * 0.8
idler_screw_size = "M3"
idler_screw_head_clearance = 0.3
mount_flange_screw_hole_inset = 10

axis_holder_width = mount_plate_connector_length
axis_holder_depth = ExtrusionProfileType.PROFILE_2020.grid_pitch_mm + flange_depth
axis_holder_thickness = 6
axis_holder_fillet_radius = 1

nut_cutter_offset_z = 2

link_screw_size = "M5"
link_screw_length = 80


def create_z_axis():
    """Create the x_axis part."""

    # # resources/ender3top_only.step

    # step_file_path = PROJECT_ROOT / "resources" / "zaxis_only.step"

    # ender_part = import_solid_from_step(step_file_path)

    # ender_part = rotate(90, axis=(1, 0, 0))(ender_part)

    guide_width = 40
    guide_thickness = 2
    guide_length = 350

    guide1 = create_box(guide_width, guide_thickness, guide_length)
    guide2 = create_box(guide_width, guide_thickness, guide_length)
    guide2 = align(
        guide2, guide1, Alignment.STACK_RIGHT, stack_gap=z_axis_guide_distance
    )

    z_guides = guide1.fuse(guide2)

    # z_guides = align(z_guides, ender_part, Alignment.CENTER)

    # ender_part = ender_part.fuse(guides)

    return z_guides


def create_mgn12h_carriage():
    """Create the MGN12H carriage part."""

    width = 27
    length = 45.4
    screw_hole_pitch = 20
    height = 10
    screw_hole_depth = 3.5
    screw_hole_diameter = 3
    h1 = 3.4

    carriage = create_box(length, width, height)

    holes = PartCollector()
    for x in [-screw_hole_pitch / 2, screw_hole_pitch / 2]:
        for y in [-width / 2 + 4, width / 2 - 4]:
            hole = create_cylinder(screw_hole_diameter / 2, height)
            hole = translate(x, y, 0)(hole)
            holes = holes.fuse(hole)

    holes = align(holes, carriage, Alignment.CENTER)
    holes = align(holes, carriage, Alignment.STACK_TOP, stack_gap=-screw_hole_depth)

    carriage = carriage.cut(holes)

    carriage = translate(0, 0, h1)(carriage)

    return carriage


def create_mgn12h_rail(length_mm: float):
    """Create the MGN12H rail part."""

    width = 12
    height = 8.5
    hole_pitch = 40
    top_hole_diameter = 8
    bottom_hole_diameter = 4.5
    top_hole_depth = 4.5

    rail = create_box(length_mm, width, height)

    num_holes = int(length_mm // hole_pitch)

    holes = PartCollector()
    for i in range(num_holes):
        x = i * hole_pitch
        # Top hole
        top_hole = create_cylinder(top_hole_diameter / 2, top_hole_depth)
        top_hole = translate(x, 0, 0)(top_hole)
        top_hole = align(top_hole, rail, Alignment.TOP)

        holes = holes.fuse(top_hole)
        # Bottom hole
        bottom_hole = create_cylinder(bottom_hole_diameter / 2, height)
        bottom_hole = translate(x, 0, 0)(bottom_hole)
        bottom_hole = align(bottom_hole, rail, Alignment.BOTTOM)
        holes = holes.fuse(bottom_hole)

    holes = align(holes, rail, Alignment.CENTER, axes=[0, 1])

    rail = rail.cut(holes)

    return rail


def create_motor_with_mount():

    motor = create_nema_composite(
        axle_length=x_axis_motor_axle_length,
        axle_clearance=motor_mount_axle_clearance,
        boss_clearance=motor_mount_boss_clearance,
        boss_clearance_z=motor_mount_boss_clearance_z,
    )

    mount_plate = create_filleted_box(
        motor_mount_plate_size,
        motor_mount_plate_depth,
        motor_mount_plate_thickness,
        motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )

    mount_plate = align(mount_plate, motor, Alignment.CENTER)
    mount_plate = align(mount_plate, motor, Alignment.STACK_TOP)
    mount_plate = align(mount_plate, motor, Alignment.BACK)
    mount_plate = translate(0, 0, -2.2)(mount_plate)

    mount_plate = motor.use_as_cutter_on(mount_plate)

    return motor, mount_plate


def create_idlers_for_motor(
    pulley,
    motor,
    profile_to_align,
    mount_plate,
    mount_plate_limit_cutter,
    vertical_alignment,
):
    """Build idlers, their bases, and return updated mount plate for one motor side.

    ``stack_face`` is Alignment.TOP for the top motor and Alignment.BOTTOM for the
    bottom motor, matching the existing orientation logic in create_x_axis.
    """

    idlers = PartCollector()
    idler_mount_bases = PartCollector()

    idler_axle_cutters = []
    for idler_alignment in (Alignment.LEFT, Alignment.RIGHT):

        idler = create_gt2_idler(num_teeth=16)

        idler = align(
            idler,
            pulley,
            vertical_alignment,
        )
        idler = align(idler, motor.leader, idler_alignment)
        idler = align(
            idler, profile_to_align, Alignment.STACK_BACK, stack_gap=idler_gap
        )
        idlers = idlers.fuse(idler)

        idler_axle_cutter = create_cylinder(
            idler_mount_axle_diameter / 2 + idler_mount_axle_clearance, 100
        )
        idler_axle_cutter = align(idler_axle_cutter, idler, Alignment.CENTER)
        mount_plate = mount_plate.cut(idler_axle_cutter)

        idler_mount_base = create_cylinder(idler_mount_diameter / 2, 100)
        idler_mount_base = align(idler_mount_base, idler, Alignment.CENTER)
        idler_mount_base = align(
            idler_mount_base,
            idler,
            vertical_alignment.opposite.stack_alignment,
        )

        idler_mount_base = idler_mount_base.cut(mount_plate_limit_cutter)

        idler_mount_base_size = get_bounding_box_size(idler_mount_base)
        idler_mount_pillar = create_box(
            idler_mount_base_size[0], BIG_THING, idler_mount_base_size[2] * 0.6
        )

        idler_mount_pillar = align(
            idler_mount_pillar, idler_mount_base, Alignment.CENTER
        )
        idler_mount_pillar = align(
            idler_mount_pillar,
            idler_mount_base,
            vertical_alignment.opposite,
        )
        idler_mount_pillar = align(
            idler_mount_pillar,
            idler_mount_base,
            Alignment.STACK_FRONT,
            stack_gap=-idler_mount_diameter / 2,
        )

        idler_mount_pillar_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
        idler_mount_pillar_cutter = align(
            idler_mount_pillar_cutter, mount_plate, Alignment.CENTER
        )
        idler_mount_pillar_cutter = align(
            idler_mount_pillar_cutter, mount_plate, Alignment.CENTER
        )
        idler_mount_pillar_cutter = align(
            idler_mount_pillar_cutter, mount_plate, Alignment.STACK_FRONT
        )

        idler_mount_pillar = idler_mount_pillar.cut(idler_mount_pillar_cutter)

        idler_mount_base = idler_mount_base.fuse(idler_mount_pillar)

        idler_mount_base = idler_mount_base.cut(idler_axle_cutter)

        idler_mount_bases = idler_mount_bases.fuse(idler_mount_base)

        idler_screw_nut_cutter = create_nut(
            axle_screw_size,
            height=axcle_screw_nut_hole_depth,
            slack=axle_screw_nut_slack,
        )
        idler_screw_nut_cutter = rotate(30)(idler_screw_nut_cutter)
        idler_screw_nut_cutter = align(idler_screw_nut_cutter, idler, Alignment.CENTER)
        idler_screw_nut_cutter = align(
            idler_screw_nut_cutter,
            mount_plate,
            vertical_alignment.opposite,
        )
        mount_plate = mount_plate.cut(idler_screw_nut_cutter)
        idler_axle_cutters.append(idler_axle_cutter)

    return idlers, idler_mount_bases, mount_plate, idler_axle_cutters


def _create_motor_stack(side, lower_axis_profile, top_axis_profile):
    """Build one motor + mount assembly (idler bases, shield, connector) for a side."""

    vertical_aligment_map = {
        Alignment.LEFT: Alignment.BOTTOM,
        Alignment.RIGHT: Alignment.TOP,
    }

    vertical_alignment = vertical_aligment_map[side]

    motor, mount_plate = create_motor_with_mount()
    motor.add_named_follower(mount_plate, "mount_plate")

    if side == Alignment.LEFT:
        motor.rotate((0, 0, 0), (0, 1, 0), 180)

    profile_to_align = (
        lower_axis_profile if side == Alignment.LEFT else top_axis_profile
    )

    motor = align(motor, profile_to_align, Alignment.CENTER)
    motor = align(motor, profile_to_align, Alignment.STACK_BACK)
    motor = align(
        motor,
        profile_to_align,
        Alignment.STACK_TOP if side == Alignment.LEFT else Alignment.STACK_BOTTOM,
    )
    motor.translate((side.sign * motor_x_offset, motor_y_offset, 0))

    axle = motor.get_follower_part_by_name("axle")
    mount_plate = motor.get_follower_part_by_name("mount_plate")

    pulley = create_gt2_pulley(num_teeth=20, belt_width=6)
    if side == Alignment.LEFT:
        pulley = rotate(180, axis=(0, 1, 0))(pulley)
    pulley = align(pulley, axle, Alignment.CENTER)
    pulley = align(pulley, axle, vertical_alignment)

    mount_plate_limit_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    mount_plate_limit_cutter = align(
        mount_plate_limit_cutter, mount_plate, Alignment.CENTER
    )
    mount_plate_limit_cutter = align(
        mount_plate_limit_cutter,
        mount_plate,
        vertical_alignment,
    )

    idlers, idler_mount_bases, mount_plate, idler_axle_cutters = (
        create_idlers_for_motor(
            pulley=pulley,
            motor=motor,
            profile_to_align=profile_to_align,
            mount_plate=mount_plate,
            mount_plate_limit_cutter=mount_plate_limit_cutter,
            vertical_alignment=vertical_alignment,
        )
    )

    mount_shield = create_filleted_box(
        mount_shield_width,
        mount_shield_depth,
        BIG_THING,
        mount_shield_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.TOP, Alignment.BOTTOM],
    )

    mount_shield = align(mount_shield, mount_plate, Alignment.CENTER)
    mount_shield = align(mount_shield, mount_plate, Alignment.FRONT)
    mount_shield = align(
        mount_shield,
        profile_to_align,
        vertical_alignment,
    )
    mount_shield = translate(0, 0, side.sign * mount_shield_oversize_z)(mount_shield)
    mount_shield = mount_shield.cut(mount_plate_limit_cutter)

    mount_shield_mount_screw_hole_cutter = create_cylinder(
        MScrew.from_size("M5").clearance_hole_normal / 2,
        BIG_THING,
        direction=(0, 1, 0),
    )
    mount_shield_mount_screw_hole_cutter = align(
        mount_shield_mount_screw_hole_cutter, mount_shield, Alignment.CENTER
    )
    mount_shield_mount_screw_hole_cutter = align(
        mount_shield_mount_screw_hole_cutter,
        profile_to_align,
        Alignment.CENTER,
        axes=[2],
    )
    mount_shield = mount_shield.cut(mount_shield_mount_screw_hole_cutter)

    mount_plate_connector = create_filleted_box(
        mount_plate_connector_length,
        mount_plate_connector_depth,
        motor_mount_plate_thickness,
        fillet_radius=motor_mount_plate_fillet_radius,
        no_fillets_at=[
            Alignment.BOTTOM,
            Alignment.TOP,
            side,
        ],
    )

    mount_plate_connector = align(mount_plate_connector, mount_plate, Alignment.CENTER)
    mount_plate_connector = align(mount_plate_connector, mount_plate, Alignment.FRONT)
    mount_plate_connector = align(
        mount_plate_connector,
        mount_plate,
        side.opposite.stack_alignment,
    )
    mount_plate_connector = translate(
        side.sign * motor_mount_plate_fillet_radius, 0, 0
    )(mount_plate_connector)

    mount_flange = create_filleted_box(
        mount_plate_connector_length + motor_mount_plate_size,
        flange_depth,
        flange_thickness,
        fillet_radius=mount_shield_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.FRONT],
    )

    mount_flange = align(mount_flange, mount_plate_connector, Alignment.CENTER)
    mount_flange = align(mount_flange, mount_plate, side)
    mount_flange = align(mount_flange, mount_plate_connector, Alignment.FRONT)
    mount_flange = align(mount_flange, profile_to_align, vertical_alignment)

    nut_cutters = []
    for screw_hole_alignment in (Alignment.LEFT, Alignment.RIGHT):

        nut_cutter = create_hidden_nut_pocket_cutter(
            "M3", bottom_cutter_length=3, top_cutter_length=100, slack=0.3
        )

        if vertical_alignment == Alignment.BOTTOM:
            nut_cutter = rotate(180, axis=(0, 1, 0))(nut_cutter)

        nut_cutter = align(nut_cutter, mount_flange, Alignment.CENTER)
        nut_cutter = align(nut_cutter, mount_plate_connector, screw_hole_alignment)
        nut_cutter = translate(
            -screw_hole_alignment.sign * mount_flange_screw_hole_inset,
            0,
            -side.sign * nut_cutter_offset_z,
        )(nut_cutter)

        nut_cutters.append(nut_cutter)
        mount_flange = nut_cutter.use_as_cutter_on(mount_flange)

    for idler_axle_cutter in idler_axle_cutters:
        mount_flange = mount_flange.cut(idler_axle_cutter)

        idler_screw_spec = MScrew.from_size(idler_screw_size)
        cylinder_head_cutter = create_cylinder(
            idler_screw_spec.cylinder_head_diameter / 2 + idler_screw_head_clearance,
            idler_screw_spec.cylinder_head_height + 2 * idler_screw_head_clearance,
        )
        cylinder_head_cutter = align(
            cylinder_head_cutter, idler_axle_cutter, Alignment.CENTER
        )
        cylinder_head_cutter = align(
            cylinder_head_cutter, mount_flange, vertical_alignment
        )
        mount_flange = mount_flange.cut(cylinder_head_cutter)

    mount_flange_bevel = create_right_triangle(
        bevel_depth,
        bevel_depth,
        thickness=mount_plate_connector_length - 2 * motor_mount_plate_fillet_radius,
        extrusion_direction=(side.sign, 0, 0),
        a_normal=(0, 0, vertical_alignment.sign),
        b_normal=(0, -1, 0),
    )

    mount_flange_bevel = align(
        mount_flange_bevel, mount_plate_connector, Alignment.CENTER
    )
    mount_flange_bevel = align(mount_flange_bevel, mount_flange, Alignment.BACK)

    mount_flange_bevel_flange_side = align(
        mount_flange_bevel, mount_flange, vertical_alignment.opposite.stack_alignment
    )

    for nut_cutter in nut_cutters:
        mount_flange_bevel_flange_side = nut_cutter.use_as_cutter_on(
            mount_flange_bevel_flange_side
        )

    mount_flange = mount_flange.fuse(mount_flange_bevel_flange_side)

    mount_plate = mount_plate.fuse(mount_plate_connector)
    mount_plate = mount_plate.fuse(idler_mount_bases)
    mount_plate = mount_plate.fuse(mount_flange)

    # sync follower with the modified mount plate geometry
    motor.followers[motor.get_follower_index_by_name("mount_plate")] = mount_plate

    motor_visual = PartCollector()
    motor_visual.fuse(motor.leader)
    motor_visual.fuse(axle)
    motor_visual.fuse(pulley)
    motor_visual.fuse(idlers)

    motor_name = f"motor_{side.name.lower()}"

    axis_holding_counter_flange = create_filleted_box(
        axis_holder_width,
        axis_holder_depth,
        axis_holder_thickness,
        axis_holder_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    axis_holding_counter_flange = align(
        axis_holding_counter_flange, mount_flange, side.opposite
    )
    axis_holding_counter_flange = align(
        axis_holding_counter_flange, mount_flange, vertical_alignment.stack_alignment
    )
    axis_holding_counter_flange = align(
        axis_holding_counter_flange, mount_flange, Alignment.BACK
    )

    for nut_cutter in nut_cutters:
        axis_holding_counter_flange = nut_cutter.use_as_cutter_on(
            axis_holding_counter_flange
        )

        profile_mount_screw_hole_cutter = create_cylinder(
            MScrew.from_size("M5").clearance_hole_normal / 2,
            BIG_THING,
        )
        profile_mount_screw_hole_cutter = align(
            profile_mount_screw_hole_cutter,
            axis_holding_counter_flange,
            Alignment.CENTER,
        )
        profile_mount_screw_hole_cutter = align(
            profile_mount_screw_hole_cutter, nut_cutter, Alignment.CENTER, axes=[0]
        )
        profile_mount_screw_hole_cutter = align(
            profile_mount_screw_hole_cutter,
            profile_to_align,
            Alignment.CENTER,
            axes=[1],
        )
        axis_holding_counter_flange = axis_holding_counter_flange.cut(
            profile_mount_screw_hole_cutter
        )

    return (
        mount_plate,
        mount_plate_connector,
        mount_shield,
        motor_visual.part,
        motor_name,
        axis_holding_counter_flange,
    )


def create_x_axis():
    """Create the x_axis assembly as a composite part.

    Leader: printable mount-plate assembly (including shields/link/idler bases).
    Non-production parts: axis frame and both motor hardware stacks.
    """

    lower_axis_profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_2020, length_mm=axis_profile_length
    )
    lower_axis_profile = rotate(90, axis=(0, 1, 0))(lower_axis_profile)

    top_axis_profile = translate(0, 0, axis_profile_pitch)(lower_axis_profile)
    axis_profiles = lower_axis_profile.fuse(top_axis_profile)

    rail = create_mgn12h_rail(length_mm=rail_length)

    carriages = PartCollector()
    for i in [-1, 1]:
        carriage = create_mgn12h_carriage()
        carriage = align(carriage, rail, Alignment.CENTER, axes=[0, 1])
        carriage = translate(i * 50, 0, 0)(carriage)
        carriages = carriages.fuse(carriage)

    rail_with_carriages = rail.fuse(carriages)
    rail_with_carriages = align(
        rail_with_carriages, lower_axis_profile, Alignment.CENTER, axes=[0, 1]
    )
    rail_with_carriages = align(
        rail_with_carriages, lower_axis_profile, Alignment.STACK_TOP
    )

    axis_frame = axis_profiles.fuse(rail_with_carriages)

    mount_plates = PartCollector()
    mount_shields = PartCollector()
    mount_plate_connectors = PartCollector()

    non_production_parts = [axis_frame]
    non_production_names = ["axis_frame"]

    axis_holding_counter_flanges = {}

    final_mount_plates_by_side = defaultdict(PartCollector)

    for side in (Alignment.LEFT, Alignment.RIGHT):
        (
            mount_plate,
            mount_plate_connector,
            mount_shield,
            motor_visual_part,
            motor_name,
            axis_holding_counter_flange,
        ) = _create_motor_stack(side, lower_axis_profile, top_axis_profile)

        mount_plate_connectors = mount_plate_connectors.fuse(mount_plate_connector)
        mount_shields = mount_shields.fuse(mount_shield)
        non_production_parts.append(motor_visual_part)
        non_production_names.append(motor_name)
        mount_plates = mount_plates.fuse(mount_plate)
        axis_holding_counter_flanges[
            f"axis_holding_counter_flange_{side.name.lower()}"
        ] = axis_holding_counter_flange

        final_mount_plates_by_side[side] = mount_plate.fuse(mount_shield)

    mount_plate_connectors_size = get_bounding_box_size(mount_plate_connectors)

    mount_plate_link = create_box(
        mount_plate_link_width,
        mount_plate_connector_link_thickness,
        mount_plate_connectors_size[2],
    )

    mount_plate_link = align(mount_plate_link, mount_plate_connectors, Alignment.CENTER)

    mount_plate_link = align(mount_plate_link, mount_plate_connectors, Alignment.BACK)

    bevel_size = (mount_plate_connectors_size[2] - 2 * motor_mount_plate_thickness) / 2
    mount_plate_link_bevels = PartCollector()
    for m in [-1, 1]:

        mount_plate_link_bevel = create_right_triangle(
            bevel_size,
            bevel_size,
            mount_plate_link_width,
            extrusion_direction=(1, 0, 0),
            a_normal=(0, 0, m),
            b_normal=(0, -1, 0),
        )
        mount_plate_link_bevel = align(
            mount_plate_link_bevel, mount_plate_link, Alignment.CENTER
        )
        mount_plate_link_bevel = align(
            mount_plate_link_bevel, mount_plate_link, Alignment.STACK_FRONT
        )
        mount_plate_link_bevel = align(
            mount_plate_link_bevel,
            mount_plate_link,
            Alignment.STACK_TOP if m == 1 else Alignment.STACK_BOTTOM,
            stack_gap=-motor_mount_plate_thickness - bevel_size,
        )

        mount_plate_link_bevels = mount_plate_link_bevels.fuse(mount_plate_link_bevel)

    mount_plate_link = mount_plate_link.fuse(mount_plate_link_bevels)

    mount_plate_link_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    mount_plate_link_cutter = align(
        mount_plate_link_cutter, axis_frame, Alignment.CENTER
    )

    mount_plate_link_cutter_center = get_bounding_box_center(mount_plate_link_cutter)
    mount_plate_link_cutters = cut_in_two(
        mount_plate_link_cutter,
        cut_point=mount_plate_link_cutter_center,
        cut_normal=(0, 0, 1),
    )

    for i, side in enumerate([Alignment.LEFT, Alignment.RIGHT]):
        current_mount_plate_link = mount_plate_link.cut(mount_plate_link_cutters[i])
        final_mount_plates_by_side[side] = final_mount_plates_by_side[side].fuse(
            current_mount_plate_link
        )

    mount_plates = mount_plates.fuse(mount_plate_link)

    retval = LeaderFollowersCuttersPart(
        leader=mount_plates,
        non_production_parts=non_production_parts,
        non_production_names=non_production_names,
    )

    link_screw_hole_cutters = PartCollector()

    for i, side in enumerate([Alignment.LEFT, Alignment.RIGHT]):
        link_screw = create_cylinder_screw(link_screw_size, length=link_screw_length)

        link_screw = align(link_screw, mount_plate_link, Alignment.CENTER)
        link_screw = align(
            link_screw, final_mount_plates_by_side[Alignment.RIGHT], Alignment.TOP
        )
        link_screw = translate(
            side.sign * mount_plate_link_width / 4,
            0,
            MScrew.from_size(link_screw_size).cylinder_head_height
            + axis_holder_thickness,
        )(link_screw)
        retval.add_named_non_production_part(
            link_screw,
            f"link_screw_{i+1}",
        )

        link_screw_hole_cutter = create_cylinder(
            MScrew.from_size(link_screw_size).clearance_hole_normal / 2,
            BIG_THING,
        )
        link_screw_hole_cutter = align(
            link_screw_hole_cutter, link_screw, Alignment.CENTER
        )
        link_screw_hole_cutters = link_screw_hole_cutters.fuse(link_screw_hole_cutter)

    for side in (Alignment.LEFT, Alignment.RIGHT):
        final_mount_plates_by_side[side] = final_mount_plates_by_side[side].cut(
            link_screw_hole_cutters
        )

    for name, part in axis_holding_counter_flanges.items():
        drilled_part = part.cut(link_screw_hole_cutters)

        retval.add_named_follower(drilled_part, name)

    for side in (Alignment.LEFT, Alignment.RIGHT):
        retval.add_named_follower(
            final_mount_plates_by_side[side],
            f"mount_plate_{side.name.lower()}",
        )
    retval.add_named_cutter(link_screw_hole_cutters, "link_screw_holes")

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    if True:
        # Create the part
        z_axis = create_z_axis()
        parts.add(z_axis, "z_axis", flip=False, skip_in_production=True)

        x_axis = create_x_axis()

        x_axis = align(x_axis, z_axis, Alignment.CENTER)
        x_axis = align(x_axis, z_axis, Alignment.STACK_BACK, stack_gap=-28)

        # Non-production references for assembly context
        for name in [
            "axis_frame",
            "motor_left",
            "motor_right",
            "link_screw_1",
            "link_screw_2",
        ]:
            parts.add(
                x_axis.get_non_production_part_by_name(name),
                f"x_axis_{name}",
                flip=False,
                skip_in_production=True,
            )

        for side in [Alignment.RIGHT, Alignment.LEFT]:
            mount_plate_name = f"mount_plate_{side.name.lower()}"
            color_by_side = {
                Alignment.LEFT: (0.8, 0.8, 1.0),
                Alignment.RIGHT: (1.0, 0.8, 0.8),
            }

            mount_plate_of_side = x_axis.get_follower_part_by_name(mount_plate_name)
            parts.add(
                mount_plate_of_side,
                f"x_axis_{mount_plate_name}",
                flip=False,
                skip_in_production=False,
                prod_rotation_angle=90,
                prod_rotation_axis=(1, 0, 0),
                color=color_by_side[side],
            )

        # Printable axis holding counter flanges
        for follower_name in [
            "axis_holding_counter_flange_left",
            "axis_holding_counter_flange_right",
        ]:
            parts.add(
                x_axis.get_follower_part_by_name(follower_name),
                follower_name,
                flip=False,
                skip_in_production=False,
                prod_rotation_angle=0,
                prod_rotation_axis=(1, 0, 0),
                color=(1.0, 0.7, 0.8),
            )

    # motor, plate = create_motor_with_mount()

    # motor_part = motor.leader
    # motor_part = motor_part.fuse(motor.get_follower_part_by_name("axle"))

    # parts.add(
    #     motor_part,
    #     "x_axis_motor",
    #     flip=False,
    #     skip_in_production=True,
    # )

    # plate = translate(0, 0, 4)(plate)
    # parts.add(plate, "x_axis_motor_mount_plate", flip=False, skip_in_production=True)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        prod_gap=4,
    )

    _logger.info("x_axis created successfully!")


if __name__ == "__main__":
    main()
