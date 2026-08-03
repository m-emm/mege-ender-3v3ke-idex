from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from mege_ender_3v3ke_idex.designs.assemblies.pressure_advance_calibration_assembly import (
    CALIBRATION_LAYER_HEIGHT,
    LABEL_PLAQUE_DEPTH,
    LABEL_PLAQUE_HEIGHT,
    LABEL_TEXT_HEIGHT,
    LABEL_TEXT_STROKE_WIDTH,
    PRESSURE_ADVANCE_VALUES,
    STRIP_DEPTH,
    STRIP_GAP,
    STRIP_HEIGHT,
    STRIP_WALL_THICKNESS,
    create_pressure_advance_calibration_assembly,
)
from mege_ender_3v3ke_idex.designs.pressure_advance_gcode_postprocessor import (
    apply_y_banded_pressure_advance,
)
from shellforgepy.simple import get_bounding_box, get_bounding_box_size


def _bands():
    return [
        {"y_min": 10, "y_max": 20, "advance": 0.01, "label": "low"},
        {"y_min": 30, "y_max": 40, "advance": 0.02, "label": "high"},
    ]


def _apply(gcode):
    return apply_y_banded_pressure_advance(
        gcode,
        context=SimpleNamespace(plate_name="fixture"),
        bands=_bands(),
        restore_advance=0.015,
    )


def test_y_banded_pressure_advance_tracks_relative_extrusion_and_purge():
    result = _apply(
        "G90\n"
        "M83\n"
        "G1 X0 Y0\n"
        "G1 X10 Y0 E1\n"
        "G1 X0 Y15\n"
        "G1 X10 Y15 E1\n"
        "G1 X0 Y35\n"
        "G1 X10 Y35 E1\n"
        "; filament end gcode\n"
        "M84\n"
    )

    assert result.count("shellforgepy PA calibration low") == 1
    assert result.count("shellforgepy PA calibration high") == 1
    assert "ADVANCE=0.01 ; shellforgepy PA calibration low" in result
    assert "ADVANCE=0.02 ; shellforgepy PA calibration high" in result
    assert result.index("ADVANCE=0.015") < result.index("; filament end gcode")


def test_y_banded_pressure_advance_tracks_relative_xy_and_absolute_e_resets():
    result = _apply(
        "G90\n"
        "M82\n"
        "G92 E0\n"
        "G1 Y15\n"
        "G1 X10 E1\n"
        "G91\n"
        "G1 Y20\n"
        "G90\n"
        "G92 E0\n"
        "G1 X20 E1\n"
    )

    assert "ADVANCE=0.01" in result
    assert "ADVANCE=0.02" in result


def test_y_banded_pressure_advance_leaves_cross_band_extrusion_untouched():
    result = _apply(
        "G90\n"
        "M83\n"
        "G1 Y15\n"
        "G1 X10 E1\n"
        "G1 Y35 E1 ; cross-band connector\n"
        "G1 X20 E1\n"
    )

    crossing = "G1 Y35 E1 ; cross-band connector"
    assert crossing in result
    assert result.count("shellforgepy PA calibration low") == 1
    assert result.count("shellforgepy PA calibration high") == 1
    assert result.index("shellforgepy PA calibration low") < result.index(crossing)
    assert result.index(crossing) < result.index("shellforgepy PA calibration high")


def test_y_banded_pressure_advance_rejects_extrusion_arcs():
    with pytest.raises(ValueError, match="Unsupported extrusion arc"):
        _apply("G90\nM83\nG1 Y15\nG2 X10 Y15 I5 E1\nG1 Y35\nG1 X10 E1\n")


def test_y_banded_pressure_advance_requires_extrusion_in_every_band():
    with pytest.raises(ValueError, match="high"):
        _apply("G90\nM83\nG1 Y15\nG1 X10 E1\n")


def test_calibration_geometry_and_yaml_bands_stay_consistent():
    assembly = create_pressure_advance_calibration_assembly()
    min_point, _ = get_bounding_box(assembly)
    _, depth, _ = get_bounding_box_size(assembly)
    expected_depth = (
        len(PRESSURE_ADVANCE_VALUES) * STRIP_DEPTH
        + (len(PRESSURE_ADVANCE_VALUES) - 1) * STRIP_GAP
    )
    assert depth == pytest.approx(expected_depth)
    assert min_point[2] == pytest.approx(0.0)
    assert LABEL_PLAQUE_DEPTH == STRIP_DEPTH
    assert LABEL_TEXT_STROKE_WIDTH >= STRIP_WALL_THICKNESS
    assert LABEL_PLAQUE_HEIGHT + LABEL_TEXT_HEIGHT < STRIP_HEIGHT

    repository_dir = Path(__file__).resolve().parents[1]
    resource = yaml.safe_load(
        (
            repository_dir
            / "assembling/assemblies/pressure_advance_calibration_assembly.yaml"
        ).read_text(encoding="utf-8")
    )
    plate = resource["Builder"]["Production"]["arrange"]["plates"][0]
    process_overrides = plate["process_data"]["overrides"]["process_overrides"]
    assert float(process_overrides["layer_height"]) == pytest.approx(
        CALIBRATION_LAYER_HEIGHT
    )
    assert LABEL_PLAQUE_HEIGHT == pytest.approx(CALIBRATION_LAYER_HEIGHT)
    assert LABEL_TEXT_HEIGHT <= 4 * CALIBRATION_LAYER_HEIGHT
    bands = plate["gcode_postprocessor"]["arguments"]["bands"]
    assert len(bands) == len(PRESSURE_ADVANCE_VALUES)
    assert [band["label"] for band in bands] == [
        f"{value:.3f}" for value in PRESSURE_ADVANCE_VALUES
    ]
    for previous, current in zip(bands, bands[1:]):
        assert previous["y_max"] < current["y_min"]
