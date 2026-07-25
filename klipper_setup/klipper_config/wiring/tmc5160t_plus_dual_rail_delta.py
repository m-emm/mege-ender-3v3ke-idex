"""Generate the TMC5160T Plus dual-rail VIO and ground-star rework delta."""

from __future__ import annotations

import argparse
import hashlib
import tempfile
from pathlib import Path
from typing import Sequence

from mege_circuits.pinout import load_pinout_config, write_svg

from tmc5160t_plus_84dd4cb_delta import (
    CONFIG_PATH,
    DEFAULT_OUTPUT_DIR,
    DeltaPresentation,
    DeltaRenderResult,
    _load_revision_project,
    _render_component_delta_svg,
    _render_wiring_delta_svg,
    analyze_component_deltas,
    analyze_connection_deltas,
)

BASELINE_COMMIT = "ece0565ec180e14dc5bcc4a643de45c2c63c1880"
TARGET_CONFIG_SHA256 = (
    "9153373f1bc5adb09e12643999f812575556269fbccb3ccd3c17ba7204fe1e08"
)
DELTA_IDENTIFIER = "dual-rail-vio-ground-star-after-ece0565"
TOP_DELTA_FILENAME = (
    "rp2040plus_btt_tmc5160t_plus_y_top_discrete_dual_rail_delta.svg"
)
BOTTOM_DELTA_FILENAME = "rp2040plus_btt_tmc5160t_plus_y_bottom_dual_rail_delta.svg"

PRESENTATION = DeltaPresentation(
    identifier=DELTA_IDENTIFIER,
    base_ref=BASELINE_COMMIT,
    component_title=(
        "DUAL-RAIL VIO + GROUND STAR + R6 REMOVAL — COMPONENT SIDE"
    ),
    component_svg_title=(
        "RP2040-Plus / TMC5160T Plus dual-rail VIO + ground star + R6 removal"
    ),
    wiring_title=(
        "DUAL-RAIL VIO + GROUND STAR + R6 REMOVAL — UNDERSIDE / MIRRORED"
    ),
    wiring_svg_title=(
        "Dual-Rail VIO + Ground-Star + R6 Removal Delta — Underside View"
    ),
    bottom_filename=BOTTOM_DELTA_FILENAME,
    removed_component_description="R6 at B02-B19",
    wiring_extra_note=(
        "GROUND REBUILD: install the dim GND-A <-> GND-B hub link. "
        "R6: remove it, leave B02 unused, and retain B19 as VIO_OK."
    ),
)


def _config_sha256() -> str:
    return hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()


def render_tmc5160t_plus_dual_rail_delta(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> DeltaRenderResult:
    """Render deltas from ece0565 to the dual-rail and ground-star design."""
    current_hash = _config_sha256()
    if current_hash != TARGET_CONFIG_SHA256:
        raise ValueError(
            "Current TMC5160T Plus wiring YAML has diverged from the reviewed "
            "dual-rail delta target; update the one-off delta baseline deliberately"
        )

    output_path = Path(output_dir)
    display_project = load_pinout_config(CONFIG_PATH)
    with tempfile.TemporaryDirectory(
        prefix="tmc5160t-dual-rail-delta-"
    ) as temporary_name:
        base_project = _load_revision_project(
            BASELINE_COMMIT,
            temporary_directory=Path(temporary_name),
        )

    component_delta = analyze_component_deltas(base_project, display_project)
    connection_delta = analyze_connection_deltas(base_project, display_project)
    top_path = write_svg(
        _render_component_delta_svg(
            base_project,
            display_project,
            component_delta,
            PRESENTATION,
        ),
        output_path / TOP_DELTA_FILENAME,
    )
    bottom_path = write_svg(
        _render_wiring_delta_svg(
            display_project,
            connection_delta,
            PRESENTATION,
        ),
        output_path / BOTTOM_DELTA_FILENAME,
    )
    print(
        "dual_rail_component_delta="
        f"added:{len(component_delta.added)},"
        f"changed:{len(component_delta.changed)},"
        f"removed:{len(component_delta.removed)},"
        f"unchanged:{len(component_delta.unchanged)}"
    )
    print(
        "dual_rail_connection_delta="
        f"new:{connection_delta.count('new')},"
        f"changed:{connection_delta.count('changed')},"
        f"removed:{len(connection_delta.removed_edges)},"
        f"unchanged:{connection_delta.count('unchanged')}"
    )
    print(top_path)
    print(bottom_path)
    return DeltaRenderResult(
        top_path=top_path,
        bottom_path=bottom_path,
        components=component_delta,
        connections=connection_delta,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the dual-rail and ground-star TMC5160T Plus rework delta."
        )
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for both SVG files.",
    )
    args = parser.parse_args(argv)
    render_tmc5160t_plus_dual_rail_delta(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
