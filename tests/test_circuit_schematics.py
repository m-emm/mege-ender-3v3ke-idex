from mege_ender_3v3ke_idex.circuit_schematics.examples.voltage_divider import (
    create_voltage_divider,
)
from mege_ender_3v3ke_idex.circuit_schematics.simple import (
    Alignment,
    Direction,
    Dot,
    Ground,
    Resistor,
    Stripboard,
    Wire,
    align,
    create_element,
    create_net,
    create_node,
    create_rail,
    create_schema,
    create_stripboard,
    create_wire,
    point_at,
    render_schemdraw,
    render_stripboard,
    rotate,
    translate,
)
import pytest


def test_voltage_divider_schema_has_expected_shape():
    schema = create_voltage_divider()

    assert [node.name for node in schema.node_views] == ["vcc", "midpoint", "gnd"]
    assert [net.name for net in schema.nets] == ["vcc", "midpoint", "gnd"]
    assert [element.name for element in schema.elements] == ["R1", "R2"]
    assert schema.elements[0].terminal_views["start"] == "vcc"
    assert schema.elements[0].terminal_views["end"] == "midpoint"
    assert schema.elements[0].terminal_nets["start"] == "vcc"
    assert schema.elements[0].terminal_nets["end"] == "midpoint"


def test_align_returns_placed_copy_without_mutating_original():
    vcc = create_node(Dot, "vcc", label="+5V")
    midpoint = create_node(Dot, "midpoint", label="OUT")
    resistor = create_element(Resistor, "R1", "10K", vcc, midpoint)

    placed = align(resistor, vcc, Alignment.STACK_BOTTOM)

    assert resistor.position == (0.0, 0.0)
    assert placed.position != resistor.position


def test_render_schemdraw_writes_svg(tmp_path):
    schema = create_voltage_divider()
    outfile = tmp_path / "voltage_divider.svg"

    render_schemdraw(schema, file=outfile)

    assert outfile.exists()
    assert "<svg" in outfile.read_text(encoding="utf-8")


def test_render_schemdraw_writes_png(tmp_path):
    schema = create_voltage_divider()
    outfile = tmp_path / "voltage_divider.png"

    render_schemdraw(schema, file=outfile)

    assert outfile.exists()
    assert outfile.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_wire_element_renders_without_a_label(tmp_path):
    v5 = create_net("v5")
    vcc = create_node(Dot, "vcc", net=v5, label="+5V")
    pul_plus = create_node(Dot, "pul_plus", net=v5, label="PUL+")
    pul_plus = translate(4, 0)(pul_plus)
    feed = create_wire(vcc, pul_plus)
    schema = create_schema([vcc, pul_plus], [feed])
    outfile = tmp_path / "wire.svg"

    assert feed.position == (0.0, 0.0)
    assert schema.wires == [feed]
    assert schema.get_bounding_box() == [[0.0, 0.0], [4.0, 0.0]]

    render_schemdraw(schema, file=outfile)

    svg = outfile.read_text(encoding="utf-8")
    assert "<svg" in svg
    assert "PUL+" in svg
    assert ">W<" not in svg


def test_create_element_wire_compatibility_path():
    v5 = create_net("v5")
    rail = create_node(Dot, "rail", net=v5)
    terminal = create_node(Dot, "terminal", net=v5)

    wire = create_element(Wire, "", None, rail, terminal)

    assert wire.start_view == "rail"
    assert wire.end_view == "terminal"
    assert wire.net_name == "v5"


def test_create_node_accepts_label_alignment():
    vcc = create_node(Dot, "vcc", label="+5V", label_alignment=Alignment.LEFT)

    assert vcc.label_loc == "left"


def test_vertical_rail_bounding_box_and_alignment():
    rail = create_node(Dot, "rail")
    rail = translate(2, 3)(rail)
    rail = create_rail(rail, Direction.VERTICAL, 6, anchor=Alignment.TOP)

    marker = create_node(Dot, "marker")
    marker = align(marker, rail, Alignment.BOTTOM)

    assert rail.get_bounding_box() == [[2.0, -3.0], [2.0, 3.0]]
    assert marker.position == (0.0, -3.0)


def test_point_at_returns_rail_endpoint_points():
    rail = create_node(Dot, "rail")
    rail = translate(2, 3)(rail)
    rail = create_rail(rail, Direction.VERTICAL, 6, anchor=Alignment.TOP)

    assert point_at(rail, Alignment.TOP).position == (2.0, 3.0)
    assert point_at(rail, Alignment.BOTTOM).position == (2.0, -3.0)


def test_align_can_move_owner_by_reference_point():
    start = create_node(Dot, "start")
    end = create_node(Dot, "end")
    end = translate(4, 0)(end)
    resistor = create_element(Resistor, "R1", "1k", start, end)
    resistor = rotate(90)(resistor)

    placed = align(point_at(resistor, Alignment.RIGHT), end, Alignment.CENTER)

    assert point_at(placed, Alignment.RIGHT).position == end.position


def test_point_at_anchor_keeps_anchor_point_and_moves_owner():
    start = create_node(Dot, "start")
    end = create_node(Dot, "end")
    target = translate(4, 0)(create_node(Dot, "target"))
    resistor = create_element(Resistor, "R1", "1k", start, end)
    resistor = rotate(90)(resistor)

    placed = align(point_at(resistor.end, Alignment.CENTER), target, Alignment.CENTER)

    assert placed.end.position == target.position


def test_render_schemdraw_writes_rail_and_tap(tmp_path):
    v5 = create_net("v5")
    rail = create_node(Dot, "rail", net=v5, label="+5V", label_alignment=Alignment.LEFT)
    rail = translate(0, 4)(rail)
    rail = create_rail(rail, Direction.VERTICAL, 8, anchor=Alignment.TOP)

    tap = create_node(Dot, "tap", net=v5, label="PUL+")
    tap = translate(4, 1)(tap)

    feed = create_wire(rail, tap)
    schema = create_schema([rail, tap], [feed])
    outfile = tmp_path / "rail.svg"

    render_schemdraw(schema, file=outfile)

    svg = outfile.read_text(encoding="utf-8")
    assert "<svg" in svg
    assert "+5V" in svg
    assert "PUL+" in svg


def test_element_stores_terminal_view_names_and_net_names_not_view_objects():
    signal = create_net("signal")
    ground = create_net("ground")
    sig_view = create_node(Dot, "sig_view", net=signal)
    gnd_view = create_node(Ground, "gnd_view", net=ground)

    resistor = create_element(Resistor, "R1", "1k", sig_view, gnd_view)

    assert resistor.terminal_views == {"start": "sig_view", "end": "gnd_view"}
    assert resistor.terminal_nets == {"start": "signal", "end": "ground"}


def test_moving_node_view_after_element_creation_keeps_connectivity():
    signal = create_net("signal")
    ground = create_net("ground")
    sig_view = create_node(Dot, "sig_view", net=signal)
    gnd_view = create_node(Ground, "gnd_view", net=ground)
    resistor = create_element(Resistor, "R1", "1k", sig_view, gnd_view)

    sig_view = translate(4, 0)(sig_view)
    schema = create_schema([sig_view, gnd_view], [resistor])

    assert resistor.terminal_views["start"] == "sig_view"
    assert resistor.terminal_nets["start"] == "signal"
    assert schema.node_views[0].position == (4.0, 0.0)


def test_multiple_node_views_can_represent_the_same_net():
    v5 = create_net("v5")
    rail = create_node(Dot, "v5_rail", net=v5)
    terminal = create_node(Dot, "pul_plus", net=v5)

    schema = create_schema([rail, terminal], [])

    assert [net.name for net in schema.nets] == ["v5"]


def test_create_wire_requires_same_net_views():
    v5 = create_net("v5")
    gnd = create_net("gnd")
    rail = create_node(Dot, "v5_rail", net=v5)
    terminal = create_node(Dot, "pul_plus", net=v5)
    ground = create_node(Ground, "gnd", net=gnd)

    assert create_wire(rail, terminal).net_name == "v5"
    try:
        create_wire(rail, ground)
    except ValueError as error:
        assert "same net" in str(error)
    else:
        raise AssertionError("wires should not connect different nets")


def test_create_schema_rejects_duplicate_node_names():
    node_a = create_node(Dot, "same")
    node_b = create_node(Dot, "same")

    try:
        create_schema([node_a, node_b], [])
    except ValueError as error:
        assert "Duplicate node view name" in str(error)
    else:
        raise AssertionError("duplicate node view names should be rejected")


def test_create_stripboard_has_expected_defaults():
    board = create_stripboard(24, 12)

    assert isinstance(board, Stripboard)
    assert board.width_pitches == 24
    assert board.height_pitches == 12
    assert board.strip_direction is Direction.HORIZONTAL
    assert board.pitch_mm == 2.54


def test_create_stripboard_rejects_invalid_dimensions():
    invalid_sizes = [
        (0, 2),
        (-1, 2),
        (2, 0),
        (2, -1),
        (1.5, 2),
        (True, 2),
        (2, "3"),
    ]

    for width, height in invalid_sizes:
        with pytest.raises((TypeError, ValueError)):
            create_stripboard(width, height)


def test_create_stripboard_rejects_invalid_pitch():
    with pytest.raises((TypeError, ValueError)):
        create_stripboard(4, 3, pitch_mm=0)

    with pytest.raises((TypeError, ValueError)):
        create_stripboard(4, 3, pitch_mm="2.54")


def test_render_stripboard_writes_svg(tmp_path):
    board = create_stripboard(4, 3)
    outfile = tmp_path / "stripboard.svg"

    render_stripboard(board, file=outfile)

    svg = outfile.read_text(encoding="utf-8")
    assert "<svg" in svg
    assert svg.count('class="copper-strip"') == 3
    assert svg.count('class="hole"') == 12


def test_render_stripboard_writes_png(tmp_path):
    board = create_stripboard(4, 3)
    outfile = tmp_path / "stripboard.png"

    render_stripboard(board, file=outfile)

    assert outfile.exists()
    assert outfile.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_render_stripboard_rejects_unsupported_suffix(tmp_path):
    board = create_stripboard(4, 3)

    with pytest.raises(ValueError, match="\\.svg or \\.png"):
        render_stripboard(board, file=tmp_path / "stripboard.pdf")


def test_render_stripboard_vertical_direction_is_not_implemented(tmp_path):
    board = create_stripboard(4, 3, strip_direction=Direction.VERTICAL)

    with pytest.raises(NotImplementedError, match="horizontal"):
        render_stripboard(board, file=tmp_path / "stripboard.svg")
