import copy
import logging
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401; Keep the materials menu around, in case we want to switch back to other materials
    PROCESS_DATA_PETG_04_HS,
    PROCESS_DATA_PLACF_04_HS,
    PROCESS_DATA_PLAGFHT_04_HS,
)
from mege_ender_3v3ke_idex.designs.nitehawk_holder import (
    create_nitehawk_holder,
    align_holder_to_extruder,
)
from mege_ender_3v3ke_idex.designs.sprite_extruder import create_sprite_extruder
from mege_ender_3v3ke_idex.designs.part_fans import (
    crate_angled_fans,
    crate_part_fan_assembly,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLAGFHT_04_HS)
BIG_THING = 500


def create_tool_head() -> LeaderFollowersCuttersPart:

    sprite_extruder = create_sprite_extruder()

    holder = create_nitehawk_holder()
    holder = rotate(180, axis=(0, 1, 0))(holder)

    holder = align_holder_to_extruder(holder, sprite_extruder)

    retval = sprite_extruder

    retval = retval.merge_except_leader(holder)
    retval.add_named_non_production_part(holder.leader, "nitehawk_holder_leader")

    sprite_extruder_fused = sprite_extruder.leaders_followers_fused()
    retval.add_named_non_production_part(sprite_extruder_fused, "sprite_extruder")

    hotend = sprite_extruder.get_named_non_production_part("hotend")

    fans = crate_part_fan_assembly()

    fans = rotate(-90, axis=(1, 0, 0))(fans)
    hotend_center = get_bounding_box_center(hotend)

    hotend_bbox = get_bounding_box(hotend)

    fans = translate(hotend_center[0], hotend_bbox[0][1], hotend_center[2])(fans)

    retval.add_named_non_production_part(fans, f"part_fans")
    retval.add_named_non_production_part(
        fans.get_named_follower("blower_ducts"), f"part_fan_blower_ducts"
    )

    retval = rotate(90, axis=(1, 0, 0))(retval)
    retval = rotate(180)(retval)

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    toolhead = create_tool_head()

    parts.add(toolhead, "toolhead", flip=False, skip_in_production=True)

    for name, npp in toolhead.get_named_non_production_part_items():
        if name in ["nitehawk_pcb"]:
            continue
        parts.add(npp, name, flip=False, skip_in_production=True)

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
