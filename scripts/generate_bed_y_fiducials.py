#!/usr/bin/env python3
"""Generate a true-scale four-fiducial patch and printable A4 PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree


A4_WIDTH_MM = 210.0
A4_HEIGHT_MM = 297.0

PATCH_SIZE_MM = 14.0
FIDUCIAL_SPACING_MM = 8.0
FIDUCIAL_DIAMETER_MM = 3.0

LOCATOR_MARKER_ID = 42
LOCATOR_MARKER_SIDE_MM = 3.8
LOCATOR_QUIET_ZONE_MM = 4.6
LOCATOR_DATA_MATRIX = (
    "1100",
    "1101",
    "0111",
    "0011",
)

OUTER_RING_STROKE_MM = 0.30
OUTER_RING_RADIUS_MM = (FIDUCIAL_DIAMETER_MM - OUTER_RING_STROKE_MM) / 2.0
INNER_RING_RADIUS_MM = 0.75
INNER_RING_STROKE_MM = 0.25
CENTER_DOT_RADIUS_MM = 0.20

PATCH_X_MM = 30.0
PATCH_Y_MM = 30.0

ARTIFACT_STEM = "bed_y_four_fiducials"


def _locator_svg(indent: str) -> str:
    center = PATCH_SIZE_MM / 2.0
    quiet_x = center - LOCATOR_QUIET_ZONE_MM / 2.0
    quiet_y = center - LOCATOR_QUIET_ZONE_MM / 2.0
    marker_x = center - LOCATOR_MARKER_SIDE_MM / 2.0
    marker_y = center - LOCATOR_MARKER_SIDE_MM / 2.0
    cell = LOCATOR_MARKER_SIDE_MM / 6.0
    cells = []
    for row, bits in enumerate(LOCATOR_DATA_MATRIX, start=1):
        for column, bit in enumerate(bits, start=1):
            if bit == "0":
                cells.append(
                    (
                        f'{indent}  <rect x="{marker_x + column * cell:g}" '
                        f'y="{marker_y + row * cell:g}" width="{cell:g}" '
                        f'height="{cell:g}" fill="#ffffff"/>'
                    )
                )
    return "\n".join(
        (
            f'{indent}<g id="aruco-locator" data-marker-id="{LOCATOR_MARKER_ID}" '
            'shape-rendering="crispEdges">',
            (
                f'{indent}  <rect class="locator-quiet-zone" '
                f'x="{quiet_x:g}" y="{quiet_y:g}" '
                f'width="{LOCATOR_QUIET_ZONE_MM:g}" '
                f'height="{LOCATOR_QUIET_ZONE_MM:g}" fill="#ffffff"/>'
            ),
            (
                f'{indent}  <rect class="locator-marker" '
                f'x="{marker_x:g}" y="{marker_y:g}" '
                f'width="{LOCATOR_MARKER_SIDE_MM:g}" '
                f'height="{LOCATOR_MARKER_SIDE_MM:g}" fill="#000000"/>'
            ),
            *cells,
            f"{indent}</g>",
        )
    )


def _fiducial_centers() -> tuple[tuple[str, float, float], ...]:
    low = (PATCH_SIZE_MM - FIDUCIAL_SPACING_MM) / 2.0
    high = low + FIDUCIAL_SPACING_MM
    return (
        ("top_left", low, low),
        ("top_right", high, low),
        ("bottom_left", low, high),
        ("bottom_right", high, high),
    )


def _fiducial_svg(cx: float, cy: float, fiducial_id: str, indent: str) -> str:
    return "\n".join(
        (
            f'{indent}<g id="{fiducial_id}" class="fiducial">',
            (
                f'{indent}  <circle class="outer-ring" cx="{cx:g}" cy="{cy:g}" '
                f'r="{OUTER_RING_RADIUS_MM:g}" fill="none" stroke="#ffffff" '
                f'stroke-width="{OUTER_RING_STROKE_MM:g}"/>'
            ),
            (
                f'{indent}  <circle class="inner-ring" cx="{cx:g}" cy="{cy:g}" '
                f'r="{INNER_RING_RADIUS_MM:g}" fill="none" stroke="#ffffff" '
                f'stroke-width="{INNER_RING_STROKE_MM:g}"/>'
            ),
            (
                f'{indent}  <circle class="center-dot" cx="{cx:g}" cy="{cy:g}" '
                f'r="{CENTER_DOT_RADIUS_MM:g}" fill="#ffffff"/>'
            ),
            f"{indent}</g>",
        )
    )


def _patch_body(indent: str = "  ") -> str:
    fiducials = "\n".join(
        _fiducial_svg(cx, cy, fiducial_id, indent)
        for fiducial_id, cx, cy in _fiducial_centers()
    )
    return "\n".join(
        (
            (
                f'{indent}<rect id="black-background" x="0" y="0" '
                f'width="{PATCH_SIZE_MM:g}" height="{PATCH_SIZE_MM:g}" '
                'fill="#000000"/>'
            ),
            _locator_svg(indent),
            fiducials,
        )
    )


def _standalone_svg() -> str:
    return "\n".join(
        (
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                '<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{PATCH_SIZE_MM:g}mm" height="{PATCH_SIZE_MM:g}mm" '
                f'viewBox="0 0 {PATCH_SIZE_MM:g} {PATCH_SIZE_MM:g}" '
                'shape-rendering="geometricPrecision">'
            ),
            "  <title>Bed Y four-fiducial patch</title>",
            (
                "  <desc>Four 3 mm concentric-circle fiducials on an 8 mm square "
                "with a centered ArUco-compatible locator.</desc>"
            ),
            _patch_body(),
            "</svg>",
            "",
        )
    )


def _crop_marks_svg() -> str:
    x0 = PATCH_X_MM
    y0 = PATCH_Y_MM
    x1 = x0 + PATCH_SIZE_MM
    y1 = y0 + PATCH_SIZE_MM
    gap = 0.7
    length = 2.5
    segments = (
        (x0 - length, y0, x0 - gap, y0),
        (x0, y0 - length, x0, y0 - gap),
        (x1 + gap, y0, x1 + length, y0),
        (x1, y0 - length, x1, y0 - gap),
        (x0 - length, y1, x0 - gap, y1),
        (x0, y1 + gap, x0, y1 + length),
        (x1 + gap, y1, x1 + length, y1),
        (x1, y1 + gap, x1, y1 + length),
    )
    lines = [
        (
            f'    <line x1="{x_start:g}" y1="{y_start:g}" '
            f'x2="{x_end:g}" y2="{y_end:g}"/>'
        )
        for x_start, y_start, x_end, y_end in segments
    ]
    return "\n".join(
        (
            '  <g id="crop-marks" stroke="#000000" stroke-width="0.2">',
            *lines,
            "  </g>",
        )
    )


def _calibration_rulers_svg() -> str:
    ruler_x = PATCH_X_MM
    ruler_50_y = 72.0
    ruler_8_y = 86.0
    return "\n".join(
        (
            '  <g id="calibration-rulers" fill="none" stroke="#000000">',
            (
                f'    <path d="M {ruler_x:g} {ruler_50_y:g} '
                f'h 50 m -50 -2 v 4 m 50 -4 v 4" stroke-width="0.35"/>'
            ),
            (
                f'    <path d="M {ruler_x:g} {ruler_8_y:g} '
                f'h 8 m -8 -1.5 v 3 m 8 -3 v 3" stroke-width="0.25"/>'
            ),
            "  </g>",
            (
                f'  <text x="{ruler_x + 25:g}" y="{ruler_50_y + 5:g}" '
                'font-family="Arial, sans-serif" font-size="3" '
                'text-anchor="middle">50 mm print-scale check</text>'
            ),
            (
                f'  <text x="{ruler_x + 4:g}" y="{ruler_8_y + 5:g}" '
                'font-family="Arial, sans-serif" font-size="3" '
                'text-anchor="middle">8 mm</text>'
            ),
        )
    )


def _a4_sheet_svg() -> str:
    return "\n".join(
        (
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                '<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{A4_WIDTH_MM:g}mm" height="{A4_HEIGHT_MM:g}mm" '
                f'viewBox="0 0 {A4_WIDTH_MM:g} {A4_HEIGHT_MM:g}" '
                'shape-rendering="geometricPrecision">'
            ),
            "  <title>1:1 bed Y fiducial print sheet</title>",
            (
                f'  <rect width="{A4_WIDTH_MM:g}" height="{A4_HEIGHT_MM:g}" '
                'fill="#ffffff"/>'
            ),
            (
                f'  <svg id="fiducial-patch" x="{PATCH_X_MM:g}" y="{PATCH_Y_MM:g}" '
                f'width="{PATCH_SIZE_MM:g}" height="{PATCH_SIZE_MM:g}" '
                f'viewBox="0 0 {PATCH_SIZE_MM:g} {PATCH_SIZE_MM:g}" '
                'preserveAspectRatio="none">'
            ),
            _patch_body(indent="    "),
            "  </svg>",
            _crop_marks_svg(),
            (
                f'  <text x="{PATCH_X_MM:g}" y="{PATCH_Y_MM + PATCH_SIZE_MM + 7:g}" '
                'font-family="Arial, sans-serif" font-size="4" font-weight="700">'
                "Bed Y fiducials - 1:1</text>"
            ),
            (
                f'  <text x="{PATCH_X_MM:g}" y="{PATCH_Y_MM + PATCH_SIZE_MM + 12:g}" '
                'font-family="Arial, sans-serif" font-size="3">'
                "Four 3 mm markers; centers form an 8 x 8 mm square; centered "
                "locator ID 42.</text>"
            ),
            (
                f'  <text x="{PATCH_X_MM:g}" y="{PATCH_Y_MM + PATCH_SIZE_MM + 17:g}" '
                'font-family="Arial, sans-serif" font-size="3">'
                "Print at 100% / actual size. Disable fit-to-page and scaling.</text>"
            ),
            _calibration_rulers_svg(),
            "</svg>",
            "",
        )
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    ElementTree.parse(path)


def _render_pdf(a4_svg_path: Path, pdf_path: Path) -> None:
    converter = shutil.which("rsvg-convert")
    if converter is None:
        raise RuntimeError(
            "rsvg-convert is required; install it with `brew install librsvg`."
        )
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_pdf = Path(temporary_directory) / pdf_path.name
        result = subprocess.run(
            (
                converter,
                "-f",
                "pdf",
                "--page-width",
                f"{A4_WIDTH_MM:g}mm",
                "--page-height",
                f"{A4_HEIGHT_MM:g}mm",
                "-o",
                str(temporary_pdf),
                str(a4_svg_path),
            ),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "rsvg-convert failed: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        temporary_pdf.replace(pdf_path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(
    manifest_path: Path,
    standalone_svg_path: Path,
    a4_svg_path: Path,
    pdf_path: Path,
) -> None:
    manifest = {
        "schema_version": 2,
        "artifact": "bed_y_four_fiducials",
        "coordinate_units": "mm",
        "patch": {
            "width_mm": PATCH_SIZE_MM,
            "height_mm": PATCH_SIZE_MM,
            "background": "black",
        },
        "fiducials": {
            "count": 4,
            "style": "white concentric circles on black",
            "outer_diameter_mm": FIDUCIAL_DIAMETER_MM,
            "center_spacing_x_mm": FIDUCIAL_SPACING_MM,
            "center_spacing_y_mm": FIDUCIAL_SPACING_MM,
            "centers_xy_mm": {
                fiducial_id: [cx, cy] for fiducial_id, cx, cy in _fiducial_centers()
            },
        },
        "locator": {
            "kind": "aruco",
            "dictionary": "DICT_4X4_50",
            "marker_id": LOCATOR_MARKER_ID,
            "marker_side_mm": LOCATOR_MARKER_SIDE_MM,
            "quiet_zone_side_mm": LOCATOR_QUIET_ZONE_MM,
            "data_matrix_black_bits": list(LOCATOR_DATA_MATRIX),
        },
        "pdf": {
            "page": "A4 portrait",
            "width_mm": A4_WIDTH_MM,
            "height_mm": A4_HEIGHT_MM,
            "print_instruction": (
                "Print at 100% / actual size; disable fit-to-page and scaling."
            ),
        },
        "files": {
            standalone_svg_path.name: _sha256(standalone_svg_path),
            a4_svg_path.name: _sha256(a4_svg_path),
            pdf_path.name: _sha256(pdf_path),
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def generate(output_directory: Path) -> tuple[Path, Path, Path, Path]:
    standalone_svg_path = output_directory / f"{ARTIFACT_STEM}.svg"
    a4_svg_path = output_directory / f"{ARTIFACT_STEM}_a4.svg"
    pdf_path = output_directory / f"{ARTIFACT_STEM}_a4.pdf"
    manifest_path = output_directory / f"{ARTIFACT_STEM}.json"

    _write_text(standalone_svg_path, _standalone_svg())
    _write_text(a4_svg_path, _a4_sheet_svg())
    _render_pdf(a4_svg_path, pdf_path)
    _write_manifest(
        manifest_path,
        standalone_svg_path,
        a4_svg_path,
        pdf_path,
    )
    return standalone_svg_path, a4_svg_path, pdf_path, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("resources/vision_fiducials"),
    )
    args = parser.parse_args()

    for artifact_path in generate(args.output_directory):
        print(artifact_path.resolve())


if __name__ == "__main__":
    main()
