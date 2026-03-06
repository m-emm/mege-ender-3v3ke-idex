import copy
import logging
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401; Keep the materials menu around, in case we want to switch back to other materials
    PROCESS_DATA_PETG_04_HS,
    PROCESS_DATA_PLA_04_HS,
    PROCESS_DATA_PLACF_04_HS,
    PROCESS_DATA_PLAGFHT_04_HS,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.nitehawk_holder import (
    align_holder_to_extruder,
    create_nitehawk_holder,
)
from mege_ender_3v3ke_idex.designs.part_fans import crate_part_fan_assembly
from mege_ender_3v3ke_idex.designs.sprite_extruder import create_sprite_extruder
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

# PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLAGFHT_04_HS)
PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLAGFHT_04_HS)

PROCESS_DATA["process_overrides"].update(
    {
        "enable_support": "1",
        "support_threshold_angle": "30",
        "brim_type": "outer_and_inner",
        "support_on_build_plate_only": "1",
        "wall_loops": "3",
        "sparse_infill_density": "85%",  # PLAGFHT is very brittle and needs more strength
        # Inter-layer adhesion / brittleness tuning
        "nozzle_temperature": "235",
        "fan_min_speed": "45",
        "fan_max_speed": "65",
        "overhang_fan_speed": "80",
        "filament_max_volumetric_speed": "18",
        "outer_wall_speed": "85",
        "inner_wall_speed": "150",
        "sparse_infill_speed": "150",
        "internal_solid_infill_speed": "150",
        "filament_flow_ratio": "1.01",
        "infill_wall_overlap": "28%",
    }
)


BIG_THING = 500


def create_tool_head() -> LeaderFollowersCuttersPart:

    sprite_extruder = create_sprite_extruder()

    holder = create_nitehawk_holder()
    # holder = rotate(180, axis=(0, 1, 0))(holder)

    holder = align_holder_to_extruder(holder, sprite_extruder)

    holder_mount_plates = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        extension = holder_mount_plate_left_extension if lr == Alignment.LEFT else 0

        holder_mount_plate = create_box(
            holder_mount_plate_thickness,
            holder_mount_plate_size,
            holder_mount_plate_depth + extension,
        )

        if lr == Alignment.RIGHT:
            mount_box = create_box(
                holder_mount_plate_spacer,
                holder_mount_plate_size,
                holder_mount_plate_size,
            )
            mount_box = align(mount_box, holder_mount_plate, Alignment.CENTER)
            mount_box = align(mount_box, holder_mount_plate, Alignment.BACK)
            mount_box = align(mount_box, holder_mount_plate, Alignment.STACK_LEFT)
            mount_box = align(mount_box, holder_mount_plate, Alignment.TOP)
            holder_mount_plate = holder_mount_plate.fuse(mount_box)

        holder_mount_plate = align(holder_mount_plate, holder, Alignment.CENTER)
        holder_mount_plate = align(holder_mount_plate, sprite_extruder, Alignment.BACK)

        holder_mount_plate = align(
            holder_mount_plate, sprite_extruder, lr.stack_alignment
        )
        holder_mount_plate = align(holder_mount_plate, holder, Alignment.BOTTOM)

        holder_mount_plate = translate(0, -holder_mount_plate_top_offset, 0)(
            holder_mount_plate
        )

        holder_mount_plates = holder_mount_plates.fuse(holder_mount_plate)

    holder = holder.fuse(holder_mount_plates)

    retval = sprite_extruder

    retval = retval.merge_except_leader(holder)

    sprite_extruder_fused = sprite_extruder.leaders_followers_fused()
    retval.add_named_non_production_part(sprite_extruder_fused, "sprite_extruder")

    hotend = sprite_extruder.get_named_non_production_part("hotend")

    fans = crate_part_fan_assembly()

    fans = rotate(-90, axis=(1, 0, 0))(fans)
    hotend_center = get_bounding_box_center(hotend)

    hotend_bbox = get_bounding_box(hotend)

    fans = translate(hotend_center[0], hotend_bbox[0][1], hotend_center[2])(fans)

    retval.add_named_non_production_part(fans, f"part_fans")

    parts_to_print = holder.leader  # .fuse(fans.get_named_follower("blower_ducts"))

    side_mount_plate = create_filleted_box(
        tool_head_additional_mount_plate_thickness,
        tool_head_additional_mount_plate_depth,
        tool_head_additional_mount_plate_height,
        tool_head_additional_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT, Alignment.BOTTOM],
    )
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.CENTER)
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.BOTTOM)

    side_mount_plate = align(
        side_mount_plate,
        sprite_extruder,
        Alignment.STACK_RIGHT,
        stack_gap=tool_head_additional_mount_plate_clearance,
    )

    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.FRONT)
    side_mount_plate = translate(0, tool_head_additional_mount_plate_depth_offset, 0)(
        side_mount_plate
    )

    # parts_to_print = parts_to_print.fuse(side_mount_plate)

    blower_ducts = fans.get_named_follower("blower_ducts")
    blower_ducts = blower_ducts.fuse(side_mount_plate)

    # duct_front_mount_plate_thickness = 3
    # duct_front_mount_plate_width = 41
    # duct_front_mount_plate_height = 15
    duct_front_mount_plate = create_box(
        duct_front_mount_plate_width,
        duct_front_mount_plate_height,
        duct_front_mount_plate_thickness,
    )

    duct_front_mount_plate_cutout = create_filleted_box(
        duct_front_mount_plate_width - 2 * duct_front_mount_plate_width_border,
        duct_front_mount_plate_height - 2 * duct_front_mount_plate_height_border,
        duct_front_mount_plate_thickness + 10,
        fillet_radius=duct_front_mount_plate_height / 4,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    duct_front_mount_plate_cutout = align(
        duct_front_mount_plate_cutout, duct_front_mount_plate, Alignment.CENTER
    )
    duct_front_mount_plate = duct_front_mount_plate.cut(duct_front_mount_plate_cutout)

    duct_front_mount_plate = align(
        duct_front_mount_plate, sprite_extruder, Alignment.CENTER
    )
    duct_front_mount_plate = align(
        duct_front_mount_plate, sprite_extruder, Alignment.STACK_TOP
    )
    duct_front_mount_plate = align(
        duct_front_mount_plate, sprite_extruder, Alignment.FRONT
    )

    duct_front_mount_plate = translate(0, duct_front_mount_plate_offset, 0)(
        duct_front_mount_plate
    )

    blower_ducts = blower_ducts.fuse(duct_front_mount_plate)

    for name, cutter in sprite_extruder.get_named_cutter_items():
        parts_to_print = parts_to_print.cut(cutter)
        blower_ducts = blower_ducts.cut(cutter)

    retval.leader = parts_to_print
    retval.add_named_follower(blower_ducts, "blower_ducts")

    retval = rotate(90, axis=(1, 0, 0))(retval)
    retval = rotate(180)(retval)

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    toolhead = create_tool_head()

    parts.add(
        toolhead,
        "toolhead",
        flip=False,
        skip_in_production=False,
        prod_rotation_angle=45,
        prod_rotation_axis=(0, 1, 0),
    )

    parts.add(
        toolhead.get_named_follower("blower_ducts"),
        "blower_ducts",
        flip=False,
        skip_in_production=False,
        prod_rotation_angle=45,
        prod_rotation_axis=(0, 1, 0),
    )

    for name, npp in toolhead.get_named_non_production_part_items():
        if name in ["nitehawk_pcb"]:
            continue
        parts.add(npp, name, flip=False, skip_in_production=True)

    simulated_part_to_print = create_box(100, 100, 1)
    simulated_part_to_print = translate(-200, 0, -100)(simulated_part_to_print)

    parts.add(
        simulated_part_to_print,
        "simulated_part_to_print",
        flip=False,
        skip_in_production=True,
    )

    # angled_fans = crate_angled_fans()
    # parts.add(angled_fans, "angled_fans", flip=False, skip_in_production=True)

    # center_pillar = create_cylinder(1, 50)
    # parts.add(center_pillar, "center_pillar", flip=False, skip_in_production=True)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("nitehawk_holder created successfully!")


if __name__ == "__main__":
    main()
