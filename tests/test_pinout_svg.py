from xml.etree import ElementTree as ET

from mege_ender_3v3ke_idex.pinout.svg import generate_routed_svg


def _viewbox_width(svg_content: str) -> int:
    root = ET.fromstring(svg_content)
    return int(root.attrib["viewBox"].split()[2])


def test_generate_routed_svg_reserves_right_margin_for_annotations():
    pin_positions = {
        "LEFT": (0.0, 0.0),
        "RIGHT": (6.0, 0.0),
    }
    connections = [{"from": "LEFT", "to": "RIGHT", "type": "data"}]

    svg_without_notes = generate_routed_svg(
        pin_positions,
        connections,
        {},
        flip_x=False,
    )
    svg_with_notes = generate_routed_svg(
        pin_positions,
        connections,
        {},
        flip_x=False,
        version_label="Example version label",
        notes_text="A much longer annotation line that needs reserved width.",
    )

    assert _viewbox_width(svg_with_notes) > _viewbox_width(svg_without_notes)
    assert "A much longer annotation line that needs reserved width." in svg_with_notes