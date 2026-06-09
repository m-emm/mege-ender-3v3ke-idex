import inspect

import pytest
from assembly_defaults import assembly_kwargs
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
from shellforgepy.simple import get_bounding_box, get_bounding_box_center, get_volume


def _local_xy_center(cutter, plate_bbox):
    center = get_bounding_box_center(cutter)
    return (
        center[0] - plate_bbox[0][0],
        center[1] - plate_bbox[0][1],
    )


def test_tool_head_mount_machined_top_is_carriage_plate_with_mount_holes():
    parameters = inspect.signature(create_tool_head_mount_machined_assembly).parameters
    assert "x_axis_belt_carriage" not in parameters
    assert "sprite_extruder" not in parameters

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

    expected_sprite_hole_centers = [
        (5.0, 5.0),
        (5.0, 44.7),
        (5.0, 56.5),
        (75.0, 5.0),
        (75.0, 44.7),
        (75.0, 56.5),
    ]
    actual_sprite_hole_centers = sorted(
        _local_xy_center(cutter, plate_bbox)
        for name, cutter in mount.get_named_cutter_items()
        if name.startswith("sprite_mount_hole_")
    )
    assert actual_sprite_hole_centers == pytest.approx(
        sorted(expected_sprite_hole_centers)
    )

    expected_carriage_hole_centers = [
        (12.7, 61.7),
        (12.7, 81.7),
        (32.7, 61.7),
        (32.7, 81.7),
        (47.3, 61.7),
        (47.3, 81.7),
        (67.3, 61.7),
        (67.3, 81.7),
    ]
    actual_carriage_hole_centers = sorted(
        _local_xy_center(cutter, plate_bbox)
        for name, cutter in mount.get_named_cutter_items()
        if name.startswith("carriage_mount_hole_")
    )
    assert actual_carriage_hole_centers == pytest.approx(
        sorted(expected_carriage_hole_centers)
    )

    leader_volume = get_volume(mount.leader)
    assert leader_volume > 0
    assert leader_volume == pytest.approx(21462.798452061026, abs=0.01)

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
