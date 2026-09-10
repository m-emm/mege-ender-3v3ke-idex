import ast
import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "klipper_setup"
HOST_ROOT = SETUP / "klipper_host"
RUNTIME_ROOT = SETUP / "runtime_helpers"
OVERLAY_DUPLICATE_ROOT = (
    SETUP / "image_build/overlays/stage2/99-klipperpi/files/klipper_host"
)
UPDATER = SETUP / "klipper_config/update_menderpi.sh"
IMAGE_STAGE = SETUP / "image_build/overlays/stage2/99-klipperpi"


def manifest(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        result[path.relative_to(root).as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


def test_custom_klipper_files_have_one_tracked_source():
    assert not list(OVERLAY_DUPLICATE_ROOT.rglob("*.py"))
    assert (HOST_ROOT / "klippy/extras/probe.py").is_file()
    assert (HOST_ROOT / "klippy/extras/probe_eddy_current.py").is_file()
    for path in HOST_ROOT.rglob("*.py"):
        if "__pycache__" not in path.parts:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_runtime_bundle_is_destination_shaped_and_unique():
    runtime_paths = set(manifest(RUNTIME_ROOT))
    assert {
        "multi_head_zero_probe/run_multi_head_zero_contact_map.py",
        "resonance/run_resonance_plot.py",
    } <= runtime_paths
    assert all(path.endswith(".py") for path in runtime_paths)


def test_shared_pin_and_recursive_install_order_are_declared():
    assert (SETUP / "KLIPPER_COMMIT").read_text().strip() == (
        "ca8230d505b7ba7fd225bfa6ed9655bc4520e805"
    )
    updater = UPDATER.read_text(encoding="utf-8")
    image_installer = (IMAGE_STAGE / "01-run-chroot.sh").read_text(encoding="utf-8")
    image_stage = (IMAGE_STAGE / "00-run.sh").read_text(encoding="utf-8")
    renderer = (SETUP / "image_build/scripts/render_overlay.sh").read_text(
        encoding="utf-8"
    )
    assert 'SOURCE_HOST_ROOT="$SETUP_DIR/klipper_host"' in updater
    assert 'SOURCE_RUNTIME_HELPERS="$SETUP_DIR/runtime_helpers"' in updater
    assert '"$SOURCE_HOST_ROOT" "$SOURCE_RUNTIME_HELPERS"' in updater
    assert '"$HOST_OVERLAY/" "$REMOTE_KLIPPER_DIR/"' in updater
    assert '"$RUNTIME_HELPERS/" "$REMOTE_CONFIG_DIR/"' in updater
    assert '"${FILES_DIR}/klipper_host/klippy/" /opt/klipper/' in image_installer
    assert '"${FILES_DIR}/runtime_helpers/." "${CONFIG_DIR}/"' in image_installer
    assert "KLIPPER_COMMIT" in image_stage
    assert "RUNTIME_HELPERS_SRC" in renderer


def test_deployment_script_has_valid_shell_syntax():
    subprocess.run(["bash", "-n", str(UPDATER)], check=True)
