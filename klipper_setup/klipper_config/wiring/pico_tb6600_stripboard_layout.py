"""Render the IDEX-owned verified TB6600 stripboard artifact."""

import logging
from pathlib import Path

from mege_circuits.simple import (
    circuit_from_schema,
    create_stripboard,
    plan_stripboard,
    render_stripboard_layout,
    stripboard_hints_from_schema,
)

_logger = logging.getLogger(__name__)

try:
    from pico_tb6600_stripboard_interface import (
        create_schema_for_tb6600_interface,
        IDEX_KIND_COLOR_MAP,
    )
except ModuleNotFoundError:  # pragma: no cover - import fallback for package use
    from .pico_tb6600_stripboard_interface import (
        create_schema_for_tb6600_interface,
        IDEX_KIND_COLOR_MAP,
    )


DEFAULT_OUTPUT_DIR = Path(__file__).with_name("diagrams")
STRIPBOARD_ARTIFACT_STEM = "pico_tb6600_stripboard_interface_stripboard"
TB6600_PRIORITY_ELEMENTS = ("Q1", "Q2", "Q3")


def create_tb6600_verified_stripboard_plan():
    schema = create_schema_for_tb6600_interface()
    circuit = circuit_from_schema(schema, name="pico_tb6600_stripboard_interface")
    hints = stripboard_hints_from_schema(
        schema,
        priority_element_names=TB6600_PRIORITY_ELEMENTS,
    )
    board = create_stripboard(
        hints.board_width_pitches,
        hints.board_height_pitches,
    )
    layout, report = plan_stripboard(
        circuit,
        board=board,
        hints=hints,
    )
    if not report.ok:
        raise RuntimeError(report.summary())
    return schema, circuit, layout, report


def render_tb6600_stripboard_build(output_dir=None, *, verified_plan=None):
    output_dir = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    if verified_plan is None:
        _schema, circuit, layout, report = create_tb6600_verified_stripboard_plan()
    else:
        _schema, circuit, layout, report = verified_plan
    if not report.ok:
        raise RuntimeError(report.summary())

    svg_file = output_dir / f"{STRIPBOARD_ARTIFACT_STEM}.svg"
    png_file = output_dir / f"{STRIPBOARD_ARTIFACT_STEM}.png"
    for output_file in (svg_file, png_file):
        render_stripboard_layout(
            layout,
            circuit,
            file=output_file,
            kind_color_map=IDEX_KIND_COLOR_MAP,
        )
        _logger.info("Wrote %s", output_file)
    return svg_file, png_file


def main():
    render_tb6600_stripboard_build()


if __name__ == "__main__":
    main()
