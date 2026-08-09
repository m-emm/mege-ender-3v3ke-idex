import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = REPO_ROOT / "scripts" / "generate_bed_y_fiducials.py"
    spec = importlib.util.spec_from_file_location("bed_y_fiducial_generator_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_patch_contains_the_reserved_aruco_locator():
    module = _module()
    svg = module._standalone_svg()

    assert 'id="aruco-locator" data-marker-id="42"' in svg
    assert 'class="locator-quiet-zone"' in svg
    assert 'class="locator-marker"' in svg
    assert module.LOCATOR_DATA_MATRIX == ("1100", "1101", "0111", "0011")


def test_manifest_records_locator_geometry_and_file_hashes(tmp_path):
    module = _module()
    standalone = tmp_path / "patch.svg"
    a4 = tmp_path / "patch_a4.svg"
    pdf = tmp_path / "patch.pdf"
    manifest_path = tmp_path / "patch.json"
    standalone.write_text("standalone", encoding="utf-8")
    a4.write_text("a4", encoding="utf-8")
    pdf.write_bytes(b"pdf")

    module._write_manifest(manifest_path, standalone, a4, pdf)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 2
    assert manifest["locator"] == {
        "kind": "aruco",
        "dictionary": "DICT_4X4_50",
        "marker_id": 42,
        "marker_side_mm": 3.8,
        "quiet_zone_side_mm": 4.6,
        "data_matrix_black_bits": ["1100", "1101", "0111", "0011"],
    }
    assert set(manifest["files"]) == {"patch.svg", "patch_a4.svg", "patch.pdf"}
