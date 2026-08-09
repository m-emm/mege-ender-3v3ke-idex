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

    assert "'_BED_MESH_CALIBRATE_NATIVE'" in source
    assert 'probe_method = gcmd.get("METHOD", "tap").lower()' in source
    assert 'method = gcmd.get("METHOD", "tap").lower()' in source
    assert 'self.probe_helper.use_xy_offsets(method != "tap")' in source
    assert 'if method == "rapid_scan" and can_scan:' in source


def test_generated_mesh_commands_route_through_idex_tap_macro():
    config = (REPO_ROOT / "klipper_setup/klipper_config/printer.cfg").read_text(
        encoding="utf-8"
    )

    assert "[gcode_macro BED_MESH_IDEX_CALIBRATE]" in config
    assert "T0\n    _BED_MESH_CALIBRATE_NATIVE" in config
    assert "METHOD=tap" in config
    assert "TAP_THRESHOLD={threshold}" in config
    assert "[gcode_macro BED_MESH_CALIBRATE]" in config
    assert "BED_MESH_IDEX_CALIBRATE\n" in config
    assert "PROFILE=tap_7x7 METHOD=tap" in config
    assert "SAMPLES=1" in config
    assert "horizontal_move_z: 5.000" in config
    assert "probe_count: 7,7" in config


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
    assert 'Remote bed_mesh.py sha256 ${current_bed_mesh_sha}; replacing it with the managed local source.' in updater
    assert 'remote bed_mesh.py has unexpected sha256' not in updater
    assert 'deadline = time.monotonic() + 60.0' in updater
    assert 'state") != "startup"' in updater

    image_installer = IMAGE_INSTALLER.read_text(encoding="utf-8")
    assert 'require_file "${FILES_DIR}/klipper_host/klippy/extras/bed_mesh.py"' in image_installer
    assert '/opt/klipper/klippy/extras/bed_mesh.py' in image_installer
