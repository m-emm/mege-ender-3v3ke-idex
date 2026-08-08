from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PRIMARY_BED_MESH = (
    REPO_ROOT / "klipper_setup/klipper_host/klippy/extras/bed_mesh.py"
)
IMAGE_BED_MESH = (
    REPO_ROOT
    / "klipper_setup/image_build/overlays/stage2/99-klipperpi/files"
    / "klipper_host/klippy/extras/bed_mesh.py"
)
UPDATER = REPO_ROOT / "klipper_setup/klipper_config/update_menderpi.sh"
IMAGE_INSTALLER = (
    REPO_ROOT
    / "klipper_setup/image_build/overlays/stage2/99-klipperpi/01-run-chroot.sh"
)


def test_bare_bed_mesh_calibrate_defaults_to_tap_and_keeps_nozzle_coordinates():
    source = PRIMARY_BED_MESH.read_text(encoding="utf-8")

    assert 'probe_method = gcmd.get("METHOD", "tap").lower()' in source
    assert 'method = gcmd.get("METHOD", "tap").lower()' in source
    assert 'self.probe_helper.use_xy_offsets(method != "tap")' in source
    assert 'if method == "rapid_scan" and can_scan:' in source


def test_direct_mesh_zero_reference_is_applied_once_to_an_aliased_matrix():
    source = PRIMARY_BED_MESH.read_text(encoding="utf-8")

    assert "# IDEX-managed override:" in source
    assert "matrices = [self.probed_matrix]" in source
    assert "if self.mesh_matrix is not self.probed_matrix:" in source
    assert "matrices.append(self.mesh_matrix)" in source


def test_tap_bed_mesh_primary_and_image_sources_match_and_are_managed():
    assert PRIMARY_BED_MESH.read_bytes() == IMAGE_BED_MESH.read_bytes()

    updater = UPDATER.read_text(encoding="utf-8")
    assert 'SOURCE_BED_MESH="${SCRIPT_DIR}/../klipper_host/klippy/extras/bed_mesh.py"' in updater
    assert 'BED_MESH_PY="${REMOTE_KLIPPER_DIR}/klippy/extras/bed_mesh.py"' in updater
    assert 'EXPECTED_UPSTREAM_BED_MESH_SHA256=' in updater
    assert 'LEGACY_MANAGED_BED_MESH_SHA256=' in updater
    assert 'PREVIOUS_MANAGED_BED_MESH_SHA256=' in updater

    image_installer = IMAGE_INSTALLER.read_text(encoding="utf-8")
    assert 'require_file "${FILES_DIR}/klipper_host/klippy/extras/bed_mesh.py"' in image_installer
    assert '/opt/klipper/klippy/extras/bed_mesh.py' in image_installer
