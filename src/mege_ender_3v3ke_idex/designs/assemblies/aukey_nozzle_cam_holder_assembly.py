"""Prototype holder plate for the placed Aukey nozzle camera."""

import logging

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


def create_aukey_nozzle_cam_holder_assembly(
    *,
    nozzle_cam,
    y_axis,
    aukey_nozzle_cam_holder_base_plate_margin,
    aukey_nozzle_cam_holder_base_plate_thickness,
    aukey_nozzle_cam_holder_base_plate_fillet_radius,
):
    """Build only the holder plate around the already-placed nozzle camera."""

    y_axis.get_named_non_production_part("profile_right")

    camera_visual = nozzle_cam.leaders_followers_fused()
    for non_production_part in nozzle_cam.non_production_parts:
        camera_visual = camera_visual.fuse(non_production_part)

    camera_visual_size = get_bounding_box_size(camera_visual)
    base_plate = create_filleted_box(
        camera_visual_size[0] + 2 * aukey_nozzle_cam_holder_base_plate_margin,
        camera_visual_size[1] + 2 * aukey_nozzle_cam_holder_base_plate_margin,
        aukey_nozzle_cam_holder_base_plate_thickness,
        fillet_radius=aukey_nozzle_cam_holder_base_plate_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    base_plate = align(base_plate, camera_visual, Alignment.CENTER, axes=[0, 1])
    base_plate = align(base_plate, camera_visual, Alignment.STACK_BOTTOM)

    return LeaderFollowersCuttersPart(leader=base_plate)
