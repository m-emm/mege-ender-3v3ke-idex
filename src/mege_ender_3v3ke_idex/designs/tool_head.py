import copy
import logging
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401; Keep the materials menu around, in case we want to switch back to other materials
    PROCESS_DATA_PETG_04_HS,
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLA_04_HS,
    PROCESS_DATA_PLACF_04_HS,
    PROCESS_DATA_PLAGFHT_04_HS,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.nitehawk_holder import (
    align_holder_to_extruder,
    create_nitehawk_holder,
)
from mege_ender_3v3ke_idex.designs.part_fans import (
    align_fans_to_sprite_extruder,
    create_part_fan_assembly,
)
from mege_ender_3v3ke_idex.designs.sprite_extruder import create_sprite_extruder
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

# PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLAGFHT_04_HS)
PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF_04_HS)

PROCESS_DATA["process_overrides"].update(
    {
        "enable_support": "1",
        "support_threshold_angle": "30",
        "brim_type": "no_brim",
        "support_on_build_plate_only": "1",
        "support_critical_regions_only": "1",
        "support_top_z_distance": "0.3",
        "support_interface_spacing": "0.8",
        "fan_min_speed": "10",
        "fan_max_speed": "25",
        "external_perimeter_speed": "75",
        "outer_wall_speed": "75",
        "sparse_infill_density": "85%",
        # "support_type": "tree(auto)",
        # "support_style": "tree_slim",
        # "wall_loops": "3",
        # "sparse_infill_density": "85%",  # PLAGFHT is very brittle and needs more strength
        # # Inter-layer adhesion / brittleness tuning
        # "nozzle_temperature": "235",
        # "fan_min_speed": "45",
        # "fan_max_speed": "65",
        # "overhang_fan_speed": "80",
        # "filament_max_volumetric_speed": "18",
        # "outer_wall_speed": "85",
        # "inner_wall_speed": "150",
        # "sparse_infill_speed": "150",
        # "internal_solid_infill_speed": "150",
        # "filament_flow_ratio": "1.01",
        # "infill_wall_overlap": "28%",
    }
)


BIG_THING = 500


def create_tool_head() -> LeaderFollowersCuttersPart:

    sprite_extruder = create_sprite_extruder()

    holder = create_nitehawk_holder()

    holder = align_holder_to_extruder(holder, sprite_extruder)

    holder_mount_plates = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        extension = holder_mount_plate_left_extension if lr == Alignment.LEFT else 0

        holder_mount_plate = create_box(
            holder_mount_plate_thickness,
            holder_mount_plate_depth + extension,
            holder_mount_plate_size,
        )

        if lr == Alignment.RIGHT:
            mount_box = create_box(
                holder_mount_plate_spacer,
                holder_mount_plate_size,
                holder_mount_plate_size,
            )
            mount_box = align(mount_box, holder_mount_plate, Alignment.CENTER)
            mount_box = align(mount_box, holder_mount_plate, Alignment.FRONT)
            mount_box = align(mount_box, holder_mount_plate, Alignment.STACK_LEFT)
            holder_mount_plate = holder_mount_plate.fuse(mount_box)

        holder_mount_plate = align(holder_mount_plate, holder, Alignment.CENTER)
        holder_mount_plate = align(holder_mount_plate, sprite_extruder, Alignment.TOP)

        holder_mount_plate = align(
            holder_mount_plate, sprite_extruder, lr.stack_alignment
        )
        holder_mount_plate = align(holder_mount_plate, holder, Alignment.BACK)

        holder_mount_plate = translate(0, 0, -holder_mount_plate_top_offset)(
            holder_mount_plate
        )

        holder_mount_plates = holder_mount_plates.fuse(holder_mount_plate)

    holder = holder.fuse(holder_mount_plates)

    retval = sprite_extruder

    retval = retval.merge_except_leader(holder)

    sprite_extruder_fused = sprite_extruder.leaders_followers_fused()
    retval.add_named_non_production_part(sprite_extruder_fused, "sprite_extruder")

    fans = create_part_fan_assembly()
    fans = align_fans_to_sprite_extruder(fans, sprite_extruder)

    retval = retval.merge_except_leader(fans)
    retval.add_named_non_production_part(fans.leader, f"part_fans")

    parts_to_print = holder.leader  # .fuse(fans.get_named_follower("blower_ducts"))

    side_mount_plate = create_filleted_box(
        tool_head_additional_mount_plate_thickness,
        tool_head_additional_mount_plate_depth,
        tool_head_additional_mount_plate_height,
        tool_head_additional_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT, Alignment.BOTTOM],
    )
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.CENTER)
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.BACK)
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.BOTTOM)

    side_mount_plate = align(
        side_mount_plate,
        sprite_extruder,
        Alignment.STACK_RIGHT,
        stack_gap=tool_head_additional_mount_plate_clearance,
    )

    side_mount_plate = translate(
        0,
        tool_head_additional_mount_plate_depth_offset,
        tool_head_additional_mount_plate_z_offset,
    )(side_mount_plate)

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

    cutout_width = (
        duct_front_mount_plate_width - 2 * duct_front_mount_plate_width_border
    )
    cutout_height = (
        duct_front_mount_plate_height - 2 * duct_front_mount_plate_height_border
    )
    min_cutoout_dimension = min(cutout_width, cutout_height)
    cutout_fillet_radius = min_cutoout_dimension / 4

    duct_front_mount_plate_cutout = create_filleted_box(
        cutout_width,
        cutout_height,
        duct_front_mount_plate_thickness + 10,
        fillet_radius=cutout_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    duct_front_mount_plate_cutout = align(
        duct_front_mount_plate_cutout, duct_front_mount_plate, Alignment.CENTER
    )
    duct_front_mount_plate = duct_front_mount_plate.cut(duct_front_mount_plate_cutout)

    duct_front_mount_plate = rotate(90, axis=(1, 0, 0))(duct_front_mount_plate)

    duct_front_mount_plate = align(
        duct_front_mount_plate, sprite_extruder, Alignment.CENTER
    )
    duct_front_mount_plate = align(
        duct_front_mount_plate, sprite_extruder, Alignment.STACK_FRONT
    )
    duct_front_mount_plate = align(
        duct_front_mount_plate, sprite_extruder, Alignment.BOTTOM
    )

    duct_front_mount_plate = translate(0, 0, duct_front_mount_plate_offset)(
        duct_front_mount_plate
    )

    blower_ducts = blower_ducts.fuse(duct_front_mount_plate)

    duct_front_mount_plate_connector = create_box(
        tool_head_front_mount_plate_connector_width,
        tool_head_front_mount_plate_connector_thickness,
        tool_head_front_mount_plate_connector_height,
    )
    duct_front_mount_plate_connector = align(
        duct_front_mount_plate_connector, duct_front_mount_plate, Alignment.BACK
    )
    duct_front_mount_plate_connector = align(
        duct_front_mount_plate_connector, duct_front_mount_plate, Alignment.STACK_BOTTOM
    )
    duct_front_mount_plate_connector = align(
        duct_front_mount_plate_connector, duct_front_mount_plate, Alignment.LEFT
    )

    blower_ducts = blower_ducts.fuse(duct_front_mount_plate_connector)

    for name, cutter in sprite_extruder.get_named_cutter_items():
        parts_to_print = parts_to_print.cut(cutter)
        blower_ducts = blower_ducts.cut(cutter)

    retval.leader = parts_to_print

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    toolhead = create_tool_head()

    parts.add(
        toolhead,
        "toolhead",
        flip=False,
        skip_in_production=True,
        prod_rotation_angle=-90,
        prod_rotation_axis=(1, 0, 0),
    )

    parts.add(
        toolhead.get_named_follower("blower_ducts"),
        "blower_ducts",
        flip=False,
        skip_in_production=False,
        prod_rotation_angle=50,
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
        export_stl=PROD,
    )

    _logger.info("nitehawk_holder created successfully!")


if __name__ == "__main__":
    main()
