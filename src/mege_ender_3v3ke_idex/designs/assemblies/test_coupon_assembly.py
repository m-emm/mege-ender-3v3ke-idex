"""Simple hardcoded PETG-CF test coupon assembly."""

import logging
import math

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

coupon_length = 40
coupon_width = 40
coupon_height = 2

base_plate_fillet_radius = 3
wall_thickness = 2.5
wall_height = 15
wall_length = 30
wall_spacing = 0


base_plate_thickness = 0.8
base_plate_border = 3

fin_thickness = 0.85
fin_height = 10
fin_length = 30
fin_spacing = 2

overhang_tower_bottom_size = 8
overhang_tower_height = 12
overhang_tower_angle = 55

overhang_tower_top_size = (
    overhang_tower_bottom_size
    + 2 * overhang_tower_height * math.tan(math.radians(90 - overhang_tower_angle))
)

base_feature_width = 4

bridge_length = 15
bridge_depth = 5
bridge_thickness = 1.0
bridge_height = 12


def create_test_coupon_assembly():

    x_wall = create_box(wall_length, wall_thickness, wall_height)

    y_wall = rotate(90)(x_wall)

    y_wall = align(y_wall, x_wall, Alignment.BACK)
    y_wall = align(y_wall, x_wall, Alignment.STACK_RIGHT, stack_gap=wall_spacing)

    coupon_features = y_wall.fuse(x_wall)

    x_fin = create_box(fin_length, fin_thickness, fin_height)

    y_fin = rotate(90)(x_fin)

    y_fin = align(y_fin, x_wall, Alignment.BACK)
    y_fin = align(y_fin, x_wall, Alignment.STACK_LEFT, stack_gap=fin_spacing)

    x_fin = align(x_fin, y_fin, Alignment.LEFT)
    x_fin = align(x_fin, y_fin, Alignment.STACK_FRONT, stack_gap=fin_spacing)

    coupon_features = coupon_features.fuse(y_fin)
    coupon_features = coupon_features.fuse(x_fin)

    overhang_tower = create_pyramid_stump(
        overhang_tower_bottom_size,
        overhang_tower_top_size,
        overhang_tower_bottom_size,
        overhang_tower_top_size,
        overhang_tower_height,
    )

    overhang_tower = align(
        overhang_tower, coupon_features, Alignment.CENTER, axes=[0, 1]
    )
    overhang_tower = align(overhang_tower, coupon_features, Alignment.BOTTOM)
    overhang_tower = align(
        overhang_tower, coupon_features, Alignment.STACK_RIGHT, stack_gap=5
    )

    coupon_features = coupon_features.fuse(overhang_tower)

    bridge = create_box(bridge_length, bridge_depth, bridge_thickness)
    bridge = translate(0, 0, bridge_height)(bridge)

    bridge_towers = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        bridge_tower = create_box(
            bridge_depth, bridge_depth, bridge_height + bridge_thickness
        )
        bridge_tower = align(bridge_tower, bridge, Alignment.CENTER)
        bridge_tower = align(bridge_tower, bridge, Alignment.TOP)
        bridge_tower = align(bridge_tower, bridge, lr.stack_alignment)
        bridge_towers = bridge_towers.fuse(bridge_tower)

    bridge = bridge.fuse(bridge_towers)

    bridge = align(bridge, coupon_features, Alignment.CENTER, axes=[0, 1])
    bridge = align(bridge, coupon_features, Alignment.STACK_LEFT, stack_gap=5)
    bridge = align(bridge, coupon_features, Alignment.BOTTOM)

    coupon_features = coupon_features.fuse(bridge)

    coupon_size = get_bounding_box_size(coupon_features)

    base_plate_size = (
        coupon_size[0] + 2 * base_plate_border,
        coupon_size[1] + 2 * base_plate_border,
        base_plate_thickness,
    )

    _logger.info(f"Base plate size: {base_plate_size}")

    base_plate = create_filleted_box(
        base_plate_size[0],
        base_plate_size[1],
        base_plate_size[2],
        base_plate_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    base_plate = align(base_plate, coupon_features, Alignment.CENTER)
    base_plate = align(base_plate, coupon_features, Alignment.STACK_BOTTOM)

    base_feature = create_filleted_box(
        4 * base_feature_width,
        base_plate_size[1],
        base_plate_thickness,
        base_plate_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    base_feature_cutter = create_filleted_box(
        2 * base_feature_width,
        base_plate_size[1] - 2 * base_feature_width,
        2 * base_plate_thickness,
        base_plate_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    base_feature_cutter = align(base_feature_cutter, base_feature, Alignment.CENTER)

    base_feature = base_feature.cut(base_feature_cutter)

    base_feature = align(base_feature, base_plate, Alignment.CENTER)
    base_feature = align(base_feature, base_plate, Alignment.BOTTOM)
    base_feature = align(
        base_feature,
        base_plate,
        Alignment.STACK_RIGHT,
        stack_gap=-2 * base_feature_width,
    )

    base_plate = base_plate.fuse(base_feature)

    coupon = base_plate.fuse(coupon_features)

    coupon_2 = align(coupon, coupon, Alignment.STACK_RIGHT, stack_gap=10)

    retval = LeaderFollowersCuttersPart(leader=coupon)

    retval.add_named_follower(coupon_2, "coupon_2")

    return retval
