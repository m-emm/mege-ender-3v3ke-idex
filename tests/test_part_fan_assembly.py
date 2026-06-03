import inspect
from pathlib import Path

import pytest

pytest.importorskip("cadquery")

from assembly_defaults import DEFAULTS
from mege_ender_3v3ke_idex.designs.assemblies.part_fan_assembly import (
    _blower_feeder_ring_path_metrics,
    _blower_nozzle_tip_scales,
    create_part_fan_assembly,
)


def _current_blower_path_kwargs():
    return {
        "num_blowers": DEFAULTS["num_blowers"],
        "feeder_ring_inner_diameter": DEFAULTS["feeder_ring_inner_diameter"],
        "blowers_nozzle_center_distance": DEFAULTS[
            "blowers_nozzle_center_distance"
        ],
        "feeder_ring_width": DEFAULTS["feeder_ring_width"],
        "feeder_ring_wall": DEFAULTS["feeder_ring_wall"],
        "blowers_down_angle": DEFAULTS["blowers_down_angle"],
        "blowers_duct_diameter": DEFAULTS["blowers_duct_diameter"],
        "blower_center_offset": DEFAULTS["blower_center_offset"],
        "feeder_ring_rotation_angle": DEFAULTS["feeder_ring_rotation_angle"],
    }


def test_blower_feeder_ring_path_metrics_match_current_geometry():
    metrics = _blower_feeder_ring_path_metrics(**_current_blower_path_kwargs())

    assert [metric["fan_entry_angle_degrees"] for metric in metrics] == pytest.approx(
        [143.91, 143.91, 143.91],
        abs=0.01,
    )
    assert [metric["nozzle_tip_angle_degrees"] for metric in metrics] == pytest.approx(
        [10.39, 130.39, 250.39],
        abs=0.01,
    )
    assert [metric["path_angle_degrees"] for metric in metrics] == pytest.approx(
        [133.52, 13.52, 106.48],
        abs=0.01,
    )
    assert [metric["path_length"] for metric in metrics] == pytest.approx(
        [57.67, 5.84, 46.00],
        abs=0.05,
    )


def test_blower_nozzle_tip_scales_increase_with_path_length():
    scales = _blower_nozzle_tip_scales(**_current_blower_path_kwargs())

    assert scales == pytest.approx([0.75, 0.25, 0.63], abs=0.01)
    assert scales[1] < scales[2] < scales[0]
    assert all(0.25 <= scale <= 0.75 for scale in scales)


def test_part_fan_clearance_is_declarative_parameter():
    assert "part_fan_clearance" in inspect.signature(
        create_part_fan_assembly
    ).parameters

    assembly_yaml = Path("assembling/assemblies/part_fan_assembly.yaml").read_text()
    defaults_yaml = Path(
        "assembling/assemblies", "idex" + "_parameters.yaml"
    ).read_text()

    assert "part_fan_clearance:" in assembly_yaml
    assert "part_fan_clearance: 0.8" in defaults_yaml
