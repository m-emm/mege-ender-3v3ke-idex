import inspect

import pytest
from assembly_defaults import DEFAULTS, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.tool_head_mount_machined_assembly import (
    TOOL_HEAD_MOUNT_MACHINED_METRICS_ID,
    create_tool_head_mount_machined_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.x_axis_carriage_assembly import (
    create_x_axis_carriage_assembly,
)
from shellforgepy.metrics import (
    Material,
    build_metrics_report_lines,
    calculate_mass_kg,
    reset_metrics,
)
from shellforgepy.construct.leader_followers_cutters_part import (
    LeaderFollowersCuttersPart,
)
from shellforgepy.simple import (
    Alignment,
    align,
    create_box,
    get_bounding_box,
    get_bounding_box_center,
    get_volume,
)


def _local_xy_center(cutter, plate_bbox):
    center = get_bounding_box_center(cutter)
    return (
        center[0] - plate_bbox[0][0],
        center[1] - plate_bbox[0][1],
    )


def _recut_delta(part, cutter):
    return get_volume(part) - get_volume(part.cut(cutter))


def test_tool_head_mount_machined_top_is_carriage_plate_with_mount_holes():
    parameters = inspect.signature(create_tool_head_mount_machined_assembly).parameters
    assert "x_axis_belt_carriage" not in parameters
    assert "sprite_extruder" not in parameters
    for removed_parameter in [
        "tool_head_mount_machined_sprite_mount_hole_x_0",
        "tool_head_mount_machined_sprite_mount_hole_x_1",
        "tool_head_mount_machined_sprite_mount_hole_y_0",
        "tool_head_mount_machined_sprite_mount_hole_y_1",
        "tool_head_mount_machined_sprite_mount_hole_y_2",
        "tool_head_mount_machined_carriage_mount_hole_diameter",
        "tool_head_mount_machined_carriage_mount_hole_x_0",
        "tool_head_mount_machined_carriage_mount_hole_x_1",
        "tool_head_mount_machined_carriage_mount_hole_x_2",
        "tool_head_mount_machined_carriage_mount_hole_x_3",
        "tool_head_mount_machined_carriage_mount_hole_y_0",
        "tool_head_mount_machined_carriage_mount_hole_y_1",
        "tool_head_mount_machined_mgn_mount_hole_diameter",
        "tool_head_mount_machined_mgn_mount_hole_pitch",
        "tool_head_mount_machined_mgn_mount_hole_pair_center_x_offset",
        "tool_head_mount_machined_mgn_mount_hole_back_y_inset",
    ]:
        assert removed_parameter not in parameters
        assert removed_parameter not in DEFAULTS

    carriage = create_x_axis_carriage_assembly()

    mount = create_tool_head_mount_machined_assembly(
        **assembly_kwargs(
            create_tool_head_mount_machined_assembly,
            carriage=carriage,
            drive_position="top",
        )
    )

    assert isinstance(mount, LeaderFollowersCuttersPart)

    plate_bbox = get_bounding_box(mount.leader)
    assert (
        plate_bbox[1][0] - plate_bbox[0][0],
        plate_bbox[1][1] - plate_bbox[0][1],
        plate_bbox[1][2] - plate_bbox[0][2],
    ) == pytest.approx((80.0, 85.2, 5.0))

    cutout = mount.get_named_cutter("extruder_cutout")
    cutout_bbox = get_bounding_box(cutout)
    assert (
        cutout_bbox[1][0] - cutout_bbox[0][0],
        cutout_bbox[1][1] - cutout_bbox[0][1],
    ) == pytest.approx((46.3, 53.7))
    assert _local_xy_center(cutout, plate_bbox) == pytest.approx((42.25, 24.85))

    expected_sprite_hole_centers = {
        "hole_drill_LEFT_FRONT": (5.0, 5.0),
        "hole_drill_LEFT_BACK": (5.0, 44.7),
        "hole_drill_LEFT_BACK_extra": (5.0, 56.5),
        "hole_drill_RIGHT_FRONT": (75.0, 5.0),
        "hole_drill_RIGHT_BACK": (75.0, 44.7),
        "hole_drill_RIGHT_BACK_extra": (75.0, 56.5),
    }
    flange_coupon = create_box(80.0, 85.2, 2.0)
    flange_coupon = align(flange_coupon, mount.leader, Alignment.CENTER)
    flange_coupon = align(flange_coupon, mount.leader, Alignment.STACK_BOTTOM)

    for cutter_name, expected_center in expected_sprite_hole_centers.items():
        drill = mount.get_named_cutter(cutter_name)
        drill_bbox = get_bounding_box(drill)
        assert _local_xy_center(drill, plate_bbox) == pytest.approx(expected_center)
        assert drill_bbox[0][2] < plate_bbox[0][2]
        assert drill_bbox[1][2] > plate_bbox[1][2]
        assert _recut_delta(flange_coupon, drill) > 0.01

    leader_volume = get_volume(mount.leader)
    assert leader_volume > 0
    assert leader_volume == pytest.approx(21462.233248610315, abs=0.01)

    mount_holes = carriage.get_named_cutter("mount_holes")
    recut_delta = leader_volume - get_volume(mount.leader.cut(mount_holes))
    assert abs(recut_delta) < 0.01


def test_tool_head_mount_machined_records_aluminum_weight_metrics():
    reset_metrics()
    try:
        carriage = create_x_axis_carriage_assembly()

        mount = create_tool_head_mount_machined_assembly(
            **assembly_kwargs(
                create_tool_head_mount_machined_assembly,
                carriage=carriage,
                drive_position="top",
                record_metrics=True,
            )
        )

        expected_mass_kg = calculate_mass_kg(
            Material.ALUMINUM, get_volume(mount.leader)
        )

        assert build_metrics_report_lines() == [
            "Weight metrics:",
            f"{TOOL_HEAD_MOUNT_MACHINED_METRICS_ID}: {expected_mass_kg:.6f} kg",
            f"  ALUMINUM: {expected_mass_kg:.6f} kg",
            f"  tool_head_mount_machined (ALUMINUM): {expected_mass_kg:.6f} kg",
        ]
    finally:
        reset_metrics()
