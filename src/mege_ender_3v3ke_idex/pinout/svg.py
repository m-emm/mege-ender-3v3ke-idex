"""SVG rendering for pinout diagrams."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

DEFAULT_COLOR_MAP = {
    "power": "red",
    "lv_power": "grey",
    "ground": "black",
    "clock": "blue",
    "data": "gold",
    "default": "gray",
}


def _calculate_bounds(
    pin_positions: dict[str, tuple[float, float]],
    waypoint_solutions: dict[int, dict[str, Any]] | None,
) -> tuple[float, float, float, float]:
    coords = list(pin_positions.values())
    max_x = max(x for x, _ in coords)
    max_y = max(y for _, y in coords)
    min_x = min(x for x, _ in coords)
    min_y = min(y for _, y in coords)

    if waypoint_solutions:
        waypoint_coords = [sol["waypoint"] for sol in waypoint_solutions.values()]
        if waypoint_coords:
            max_x = max(max_x, max(x for x, _ in waypoint_coords))
            max_y = max(max_y, max(y for _, y in waypoint_coords))
            min_x = min(min_x, min(x for x, _ in waypoint_coords))
            min_y = min(min_y, min(y for _, y in waypoint_coords))

    return min_x, min_y, max_x, max_y


def _transform_positions_for_view(
    pin_positions: dict[str, tuple[float, float]],
    waypoint_solutions: dict[int, dict[str, Any]] | None,
    *,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    flip_x: bool,
) -> tuple[dict[str, tuple[float, float]], dict[int, tuple[float, float]]]:
    transformed_pins: dict[str, tuple[float, float]] = {}
    for name, (x, y) in pin_positions.items():
        flipped_y = max_y - y + min_y
        transformed_x = max_x - x + min_x if flip_x else x
        transformed_pins[name] = (transformed_x, flipped_y)

    transformed_waypoints: dict[int, tuple[float, float]] = {}
    if waypoint_solutions:
        for conn_idx, solution in waypoint_solutions.items():
            wp_x, wp_y = solution["waypoint"]
            transformed_wp_y = max_y - wp_y + min_y
            transformed_wp_x = max_x - wp_x + min_x if flip_x else wp_x
            transformed_waypoints[conn_idx] = (transformed_wp_x, transformed_wp_y)

    return transformed_pins, transformed_waypoints


def _add_text(parent: ET.Element, content: str, **attrs: str) -> None:
    text_node = ET.SubElement(parent, "text", attrs)
    text_node.text = content


def generate_routed_svg(
    pin_positions: dict[str, tuple[float, float]],
    connections: list[dict[str, Any]],
    waypoint_solutions: dict[int, dict[str, Any]] | None,
    *,
    flip_x: bool = False,
    version_label: str | None = None,
    notes_text: str | None = None,
    color_map: dict[str, str] | None = None,
) -> str:
    """Generate SVG content for a routed pinout view."""
    if not pin_positions:
        raise ValueError("pin_positions must not be empty")

    merged_color_map = dict(DEFAULT_COLOR_MAP)
    if color_map:
        merged_color_map.update(color_map)

    min_x, min_y, max_x, max_y = _calculate_bounds(pin_positions, waypoint_solutions)
    actual_pin_positions, actual_waypoints = _transform_positions_for_view(
        pin_positions,
        waypoint_solutions,
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
        flip_x=flip_x,
    )

    base_margin = 0.5
    margin_right = base_margin + 3.0
    margin_top = base_margin + 0.5
    margin_left = base_margin + 1.0
    margin_bottom = base_margin
    coord_shift_x = margin_left - min_x
    coord_shift_y = margin_top - min_y

    grid_size = 40
    vb_x = 0
    vb_y = 0
    vb_w = int((max_x - min_x + margin_left + margin_right + 1) * grid_size)
    vb_h = int((max_y - min_y + margin_top + margin_bottom + 1) * grid_size)

    root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": f"{vb_x} {vb_y} {vb_w} {vb_h}",
            "width": "100%",
            "height": "100%",
        },
    )

    for i, connection in enumerate(connections):
        p1 = actual_pin_positions[connection["from"]]
        p2 = actual_pin_positions[connection["to"]]
        kind = str(connection.get("type", connection.get("kind", "default"))).strip()
        explicit_color = connection.get("color")
        color = str(
            explicit_color or merged_color_map.get(kind, merged_color_map["default"])
        )

        x1 = int((p1[0] + coord_shift_x) * grid_size)
        y1 = int((p1[1] + coord_shift_y) * grid_size)
        x2 = int((p2[0] + coord_shift_x) * grid_size)
        y2 = int((p2[1] + coord_shift_y) * grid_size)

        if i in actual_waypoints:
            wx = int((actual_waypoints[i][0] + coord_shift_x) * grid_size)
            wy = int((actual_waypoints[i][1] + coord_shift_y) * grid_size)
            ET.SubElement(
                root,
                "line",
                {
                    "x1": str(x1),
                    "y1": str(y1),
                    "x2": str(wx),
                    "y2": str(wy),
                    "stroke": color,
                    "stroke-width": "2",
                },
            )
            ET.SubElement(
                root,
                "line",
                {
                    "x1": str(wx),
                    "y1": str(wy),
                    "x2": str(x2),
                    "y2": str(y2),
                    "stroke": color,
                    "stroke-width": "2",
                },
            )
            ET.SubElement(
                root,
                "circle",
                {
                    "cx": str(wx),
                    "cy": str(wy),
                    "r": "3",
                    "fill": color,
                    "stroke": "black",
                    "stroke-width": "1",
                },
            )
            continue

        ET.SubElement(
            root,
            "line",
            {
                "x1": str(x1),
                "y1": str(y1),
                "x2": str(x2),
                "y2": str(y2),
                "stroke": color,
                "stroke-width": "2",
            },
        )

    pin_radius = 6
    for name, (x, y) in actual_pin_positions.items():
        cx = int((x + coord_shift_x) * grid_size)
        cy = int((y + coord_shift_y) * grid_size)
        ET.SubElement(
            root,
            "circle",
            {
                "cx": str(cx),
                "cy": str(cy),
                "r": str(pin_radius),
                "fill": "lightgray",
                "stroke": "black",
            },
        )

        has_right_neighbor = any(
            other != name and oy == y and 0 < ox - x <= 2
            for other, (ox, oy) in actual_pin_positions.items()
        )
        has_left_neighbor = any(
            other != name and oy == y and 0 < x - ox <= 2
            for other, (ox, oy) in actual_pin_positions.items()
        )
        has_top_neighbor = any(
            other != name and ox == x and 0 < oy - y <= 2
            for other, (ox, oy) in actual_pin_positions.items()
        )
        has_bottom_neighbor = any(
            other != name and ox == x and 0 < y - oy <= 2
            for other, (ox, oy) in actual_pin_positions.items()
        )

        if not has_right_neighbor and not flip_x:
            _add_text(
                root,
                name,
                x=str(cx + pin_radius + 5),
                y=str(cy + 4),
                **{
                    "font-size": "12px",
                    "font-family": "monospace",
                    "text-anchor": "start",
                },
            )
        elif not has_left_neighbor and flip_x:
            _add_text(
                root,
                name,
                x=str(cx - pin_radius - 5),
                y=str(cy + 4),
                **{
                    "font-size": "12px",
                    "font-family": "monospace",
                    "text-anchor": "end",
                },
            )
        elif not has_left_neighbor:
            _add_text(
                root,
                name,
                x=str(cx - pin_radius - 5),
                y=str(cy + 4),
                **{
                    "font-size": "12px",
                    "font-family": "monospace",
                    "text-anchor": "end",
                },
            )
        elif not has_top_neighbor:
            _add_text(
                root,
                name,
                x=str(cx),
                y=str(cy - pin_radius - 8),
                **{
                    "font-size": "12px",
                    "font-family": "monospace",
                    "text-anchor": "middle",
                },
            )
        elif not has_bottom_neighbor:
            _add_text(
                root,
                name,
                x=str(cx),
                y=str(cy + pin_radius + 16),
                **{
                    "font-size": "12px",
                    "font-family": "monospace",
                    "text-anchor": "middle",
                },
            )
        else:
            angle = -30 if not flip_x else 30
            y_offset = cy - pin_radius - 8
            _add_text(
                root,
                name,
                x=str(cx),
                y=str(y_offset),
                **{
                    "font-size": "11px",
                    "font-family": "monospace",
                    "text-anchor": "middle",
                    "transform": f"rotate({angle},{cx},{y_offset})",
                },
            )

    view_label = "Underside View" if flip_x else "Top View"
    label_x = vb_w - 20
    label_y = 30
    _add_text(
        root,
        view_label,
        x=str(label_x),
        y=str(label_y),
        **{
            "font-size": "16px",
            "font-family": "sans-serif",
            "font-weight": "bold",
            "text-anchor": "end",
            "fill": "darkblue",
        },
    )

    if version_label:
        _add_text(
            root,
            version_label,
            x=str(label_x),
            y=str(label_y + 20),
            **{
                "font-size": "12px",
                "font-family": "sans-serif",
                "text-anchor": "end",
                "fill": "darkgreen",
            },
        )

    if notes_text:
        for i, line in enumerate(notes_text.splitlines()):
            _add_text(
                root,
                line,
                x=str(label_x),
                y=str(label_y + 40 + i * 15),
                **{
                    "font-size": "10px",
                    "font-family": "sans-serif",
                    "text-anchor": "end",
                    "fill": "black",
                },
            )

    return ET.tostring(root, encoding="unicode")


def write_svg(svg_content: str, filename: str | Path) -> Path:
    """Write SVG content to disk."""
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg_content, encoding="utf-8")
    return path
