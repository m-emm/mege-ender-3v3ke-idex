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
OUTSIDE_ROOT = IMAGE_STAGE / "files/mege_outside"
INSTALLED_OVERLAY = IMAGE_STAGE / "files/installed_overlay"
INSTALLED_ROOTFS = INSTALLED_OVERLAY / "rootfs"
INSTALLED_DEPLOY = SETUP / "klipper_config/deploy_installed_overlay.sh"


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


def test_mege_outside_client_is_canonical_and_not_enabled_in_the_image():
    expected = {
        "mege-outside-enroll.sh",
        "mege-outside-activate.sh",
        "mege.conf.template",
        "mege-printer-tunnel.service",
    }
    assert {path.name for path in OUTSIDE_ROOT.iterdir()} == expected

    image_installer = (IMAGE_STAGE / "01-run-chroot.sh").read_text(encoding="utf-8")
    updater = UPDATER.read_text(encoding="utf-8")
    unit = (OUTSIDE_ROOT / "mege-printer-tunnel.service").read_text(encoding="utf-8")
    template = (OUTSIDE_ROOT / "mege.conf.template").read_text(encoding="utf-8")

    assert 'SOURCE_OUTSIDE_CLIENT_ROOT="$SETUP_DIR/image_build/overlays/stage2/99-klipperpi/files/mege_outside"' in updater
    assert '"$SOURCE_OUTSIDE_CLIENT_ROOT"' in updater
    assert "wireguard-tools" in image_installer
    assert "mege-outside-enroll" in image_installer
    assert "mege-outside-activate" in image_installer
    assert "systemctl_enable_safe wg-quick@mege" not in image_installer
    assert "systemctl_enable_safe mege-printer-tunnel" not in image_installer
    assert "AllowedIPs = 10.203.71.1/32, fd1c:4436:beaf:1::1/128" in template
    assert "-R 127.0.0.1:17125:127.0.0.1:80" in unit
    assert "AddressFamily=" not in unit
    assert "AAAA-only" in unit
    assert "StrictHostKeyChecking=yes" in unit


def test_mege_outside_scripts_have_valid_shell_syntax():
    for path in (
        OUTSIDE_ROOT / "mege-outside-enroll.sh",
        OUTSIDE_ROOT / "mege-outside-activate.sh",
        IMAGE_STAGE / "01-run-chroot.sh",
    ):
        subprocess.run(["bash", "-n", str(path)], check=True)


def test_installed_overlay_is_used_after_mainsail_and_in_live_deployment():
    image_installer = (IMAGE_STAGE / "01-run-chroot.sh").read_text(encoding="utf-8")
    updater = UPDATER.read_text(encoding="utf-8")
    deployer = INSTALLED_DEPLOY.read_text(encoding="utf-8")
    mainsail_overlay = INSTALLED_ROOTFS / "var/www/mainsail/index.html"
    service_worker_overlay = INSTALLED_ROOTFS / "var/www/mainsail/sw.js"
    nginx_overlay = INSTALLED_ROOTFS / "etc/nginx/sites-available/mainsail"
    overlay_readme = (INSTALLED_OVERLAY / "README.md").read_text(encoding="utf-8")

    assert mainsail_overlay.is_file()
    assert service_worker_overlay.is_file()
    assert nginx_overlay.is_file()
    assert 'wget -q "${MAINSAIL_URL}" -O "${TMP_ZIP}"' in image_installer
    assert 'rmdir /var/www/mainsail/mainsail' in image_installer
    assert '"${FILES_DIR}/installed_overlay/rootfs/" /' in image_installer
    assert image_installer.index('rmdir /var/www/mainsail/mainsail') < image_installer.index(
        '"${FILES_DIR}/installed_overlay/rootfs/" /'
    )
    assert 'crossorigin="use-credentials"' in mainsail_overlay.read_text(encoding="utf-8")
    service_worker = service_worker_overlay.read_text(encoding="utf-8")
    assert r"^\/(calibration|eddy|vision)(?:\/|$)" in service_worker
    assert "index.html" in overlay_readme
    assert "sw.js" in overlay_readme
    assert "v2.9.1" in overlay_readme
    assert "/calibration/" in overlay_readme
    nginx = nginx_overlay.read_text(encoding="utf-8")
    assert nginx.count("proxy_set_header X-Forwarded-For $remote_addr;") == 2
    assert nginx.count("proxy_set_header X-Real-IP $remote_addr;") == 2
    assert 'deploy_installed_overlay.sh" --check' in updater
    assert 'deploy_installed_overlay.sh"' in updater
    assert "--dry-run" in deployer
    assert "--backup-dir=\"$BACKUP_ROOT\"" in deployer
    assert 'sudo -n nginx -t' in deployer
    assert 'sudo -n systemctl reload nginx' in deployer


def test_deployment_script_has_valid_shell_syntax():
    for path in (UPDATER, INSTALLED_DEPLOY, IMAGE_STAGE / "01-run-chroot.sh"):
        subprocess.run(["bash", "-n", str(path)], check=True)


def test_bespoke_mainsail_patch_files_are_gone():
    assert not (IMAGE_STAGE / "files/mainsail_patch").exists()
    assert not (SETUP / "klipper_config/deploy_mainsail_manifest_patch.sh").exists()
    assert "MAINSAIL_PATCHER" not in (IMAGE_STAGE / "01-run-chroot.sh").read_text(
        encoding="utf-8"
    )
