import importlib.util
import math
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
FILES = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
)


def _module():
    spec = importlib.util.spec_from_file_location("calib_dao_test", FILES / "calib_dao.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_yaml(path, value):
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def _files(tmp_path):
    priors = tmp_path / "priors.yaml"
    calib = tmp_path / "calib.yaml"
    _write_yaml(
        priors,
        {
            "fiducial_reference_printer_xyz_mm": [166.709424, -24.839235, -0.6],
            "fiducial_origin_xy_mm": [3.0, 3.0],
            "fiducial_spacing_xy_mm": [8.0, 8.0],
            "fiducial_z_mm": -0.6,
        },
    )
    _write_yaml(
        calib,
        {
            "bed_grid_zero": {"x": 113.3, "y": 107.0},
            "tools": {
                "t0": {"x_endstop": -77.6, "y_endstop": -14.8, "z_endstop": 293.7},
                "t1": {"x_endstop": 351.7, "y_endstop": -13.8, "z_endstop": 293.6},
            },
            "unrelated": {"preserved": True},
        },
    )
    return calib, priors


def test_consumer_methods_return_values_and_derived_geometry(tmp_path):
    module = _module()
    calib, priors = _files(tmp_path)
    dao = module.CalibDAO(calib, priors)

    assert dao.fiducial_reference() == [166.709424, -24.839235, -0.6]
    assert dao.fiducial_centers() == [
        [3.0, 3.0],
        [11.0, 3.0],
        [3.0, 11.0],
        [11.0, 11.0],
    ]
    assert dao.fiducial_z() == -0.6
    assert dao.tool_datums()["t1"]["x_endstop"] == 351.7
    assert dao.calib_hash().startswith("sha256:")
    assert dao.priors_hash().startswith("sha256:")


def test_candidate_updates_datums_and_preserves_unrelated_calib(tmp_path):
    module = _module()
    calib, priors = _files(tmp_path)
    dao = module.CalibDAO(calib, priors)
    candidate = tmp_path / "candidate.yaml"

    candidate_hash = dao.write_candidate(
        candidate,
        {
            "t0": {"x": -76.0, "y": -14.0, "z": 294.0},
            "t1": {"x": 350.0, "y": -13.0, "z": 293.0},
        },
    )

    value = yaml.safe_load(candidate.read_text(encoding="utf-8"))
    assert value["tools"]["t0"]["x_endstop"] == -76.0
    assert value["tools"]["t1"]["z_endstop"] == 293.0
    assert value["unrelated"] == {"preserved": True}
    assert value["bed_grid_zero"] == {"x": 113.3, "y": 107.0}
    assert candidate_hash.startswith("sha256:")


def test_methods_validate_only_the_fields_they_consume(tmp_path):
    module = _module()
    calib, priors = _files(tmp_path)
    value = yaml.safe_load(priors.read_text(encoding="utf-8"))
    del value["fiducial_z_mm"]
    _write_yaml(priors, value)
    dao = module.CalibDAO(calib, priors)

    assert dao.fiducial_reference() == [166.709424, -24.839235, -0.6]
    with pytest.raises(ValueError, match="fiducial_z_mm"):
        dao.fiducial_z()


def test_four_fiducial_selection_uses_geometry_without_angle_prior():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(
        "four_fiducials_dao_angle_test", FILES / "vision_four_fiducials.py"
    )
    finder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finder)

    def vector(angle_deg):
        angle = math.radians(angle_deg)
        return [80.0 * math.cos(angle), 80.0 * math.sin(angle)]

    bottom_left = [200.0, 200.0]
    right = vector(-20.0)
    up = vector(-110.0)
    points = [
        [bottom_left[0] + up[0], bottom_left[1] + up[1]],
        [bottom_left[0] + up[0] + right[0], bottom_left[1] + up[1] + right[1]],
        bottom_left,
        [bottom_left[0] + right[0], bottom_left[1] + right[1]],
    ]
    candidates = [
        {"center_px": point, "radius_px": 10.0} for point in points
    ]

    selected = finder.find_four_fiducials(candidates)

    assert len(selected) == 4
