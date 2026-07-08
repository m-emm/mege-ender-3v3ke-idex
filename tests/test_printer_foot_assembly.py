import pytest

from assembly_defaults import DEFAULTS, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.printer_foot_assembly import (
    create_printer_foot_assembly,
)
from shellforgepy.simple import get_bounding_box


def _build_foot(*, height, screw_sink):
    kwargs = assembly_kwargs(create_printer_foot_assembly)
    kwargs["printer_foot_height"] = height
    kwargs["printer_foot_mount_screw_sink"] = screw_sink
    return create_printer_foot_assembly(**kwargs)


def _screw_top_protrusion(foot_assembly):
    foot_bbox = get_bounding_box(foot_assembly.leader)
    screw_bbox = get_bounding_box(
        foot_assembly.get_non_production_part_by_name("screw")
    )
    return screw_bbox[1][2] - foot_bbox[1][2]


def test_default_printer_foot_height_and_sink_track_motor_bracket_lowering():
    assert DEFAULTS["printer_foot_height"] - DEFAULTS[
        "printer_foot_base_height"
    ] == pytest.approx(DEFAULTS["y_axis_motor_bracket_lowering"])
    assert DEFAULTS["printer_foot_mount_screw_sink"] - DEFAULTS[
        "printer_foot_base_mount_screw_sink"
    ] == pytest.approx(DEFAULTS["y_axis_motor_bracket_lowering"])


def test_printer_foot_height_and_sink_delta_preserves_screw_top_protrusion():
    base_height = 65.0
    base_sink = 15.5
    lowering = 6.0

    original = _build_foot(height=base_height, screw_sink=base_sink)
    raised = _build_foot(
        height=base_height + lowering,
        screw_sink=base_sink + lowering,
    )

    assert _screw_top_protrusion(raised) == pytest.approx(
        _screw_top_protrusion(original)
    )
