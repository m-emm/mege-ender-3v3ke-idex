import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRAMEBUFFER_PATH = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
    / "vision_framebuffer.py"
)


def _load():
    name = f"vision_framebuffer_test_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(name, FRAMEBUFFER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_startup_clears_only_transient_framebuffer_files(tmp_path):
    module = _load()
    run_dir = tmp_path / "preview"
    ring_dir = run_dir / "ring"
    ring_dir.mkdir(parents=True)
    (ring_dir / "old.jpg").write_bytes(b"old")
    (ring_dir / "old.json").write_text("{}")
    (run_dir / ".capture.jpg.tmp").write_bytes(b"partial")
    (run_dir / "latest.jpg").write_bytes(b"old")
    (run_dir / "latest.json").write_text("{}")
    profile_request = run_dir / "profile_request.json"
    profile_request.write_text('{"profile": "analysis"}')

    module.clear_runtime_framebuffer(run_dir, ring_dir)

    assert list(ring_dir.iterdir()) == []
    assert not (run_dir / ".capture.jpg.tmp").exists()
    assert not (run_dir / "latest.jpg").exists()
    assert not (run_dir / "latest.json").exists()
    assert profile_request.is_file()
