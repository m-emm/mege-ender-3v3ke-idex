import inspect

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
from shellforgepy.simple import create_box, get_volume


def test_tool_head_mount_machined_top_is_carriage_plate_with_mount_holes():
    parameters = inspect.signature(create_tool_head_mount_machined_assembly).parameters
    assert "x_axis_belt_carriage" not in parameters

    carriage = create_x_axis_carriage_assembly()
    sprite_extruder = LeaderFollowersCuttersPart(create_box(10, 10, 10))

    mount = create_tool_head_mount_machined_assembly(
        **assembly_kwargs(
            create_tool_head_mount_machined_assembly,
            carriage=carriage,
            sprite_extruder=sprite_extruder,
            drive_position="top",
        )
    )

    assert isinstance(mount, LeaderFollowersCuttersPart)

    leader_volume = get_volume(mount.leader)
    assert leader_volume > 0

    mount_holes = carriage.get_named_cutter("mount_holes")
    recut_delta = leader_volume - get_volume(mount.leader.cut(mount_holes))
    assert abs(recut_delta) < 0.01


def test_tool_head_mount_machined_records_aluminum_weight_metrics():
    reset_metrics()
    try:
        carriage = create_x_axis_carriage_assembly()
        sprite_extruder = LeaderFollowersCuttersPart(create_box(10, 10, 10))

        mount = create_tool_head_mount_machined_assembly(
            **assembly_kwargs(
                create_tool_head_mount_machined_assembly,
                carriage=carriage,
                sprite_extruder=sprite_extruder,
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
