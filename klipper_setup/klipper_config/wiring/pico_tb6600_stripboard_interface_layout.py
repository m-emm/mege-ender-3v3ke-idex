"""Render a first stripboard-row projection of the TB6600 interface schematic."""

from pathlib import Path

from mege_ender_3v3ke_idex.circuit_schematics.simple import (
    assign_schema_nets_to_stripboard,
    compact_sparse_stripboard_rows,
    compact_stripboard_connections_left,
    render_stripboard_overlay,
)
from pico_tb6600_stripboard_interface_schematic import (
    create_schema_for_tb6600_interface,
)


DIAGRAM_DIR = Path(__file__).with_name("diagrams")
SVG_FILE = DIAGRAM_DIR / "pico_tb6600_stripboard_interface_stripboard.svg"
PNG_FILE = DIAGRAM_DIR / "pico_tb6600_stripboard_interface_stripboard.png"


def create_stripboard_projection():
    schema = create_schema_for_tb6600_interface()
    assignment = assign_schema_nets_to_stripboard(schema)
    assignment = compact_sparse_stripboard_rows(assignment)
    assignment = compact_stripboard_connections_left(schema, assignment, strict=True)
    return schema, assignment


def main():
    DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)
    schema, assignment = create_stripboard_projection()
    for output_file in (SVG_FILE, PNG_FILE):
        render_stripboard_overlay(
            assignment.stripboard,
            assignment,
            schema,
            file=output_file,
        )
        print(f"Wrote {output_file}")


if __name__ == "__main__":
    main()
