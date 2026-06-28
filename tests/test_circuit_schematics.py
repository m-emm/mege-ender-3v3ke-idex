from mege_ender_3v3ke_idex.circuit_schematics.examples.voltage_divider import (
    create_voltage_divider,
)
from mege_ender_3v3ke_idex.circuit_schematics.simple import (
    Alignment,
    Direction,
    Dot,
    Resistor,
    Wire,
    align,
    create_element,
    create_node,
    create_rail,
    create_schema,
    point_at,
    render_schemdraw,
    rotate,
    translate,
)


def test_voltage_divider_schema_has_expected_shape():
    schema = create_voltage_divider()

    assert [node.name for node in schema.nodes] == ["vcc", "midpoint", "gnd"]
    assert [element.name for element in schema.elements] == ["R1", "R2"]
    assert schema.elements[0].terminal_nodes["start"].name == "vcc"
    assert schema.elements[0].terminal_nodes["end"].name == "midpoint"


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
    vcc = create_node(Dot, "vcc", label="+5V")
    pul_plus = create_node(Dot, "pul_plus", label="PUL+")
    pul_plus = translate(4, 0)(pul_plus)
    feed = create_element(Wire, "", None, vcc, pul_plus)
    schema = create_schema([vcc, pul_plus], [feed])
    outfile = tmp_path / "wire.svg"

    assert feed.position == (0.0, 0.0)
    assert feed.get_bounding_box() == [[0.0, 0.0], [4.0, 0.0]]

    render_schemdraw(schema, file=outfile)

    svg = outfile.read_text(encoding="utf-8")
    assert "<svg" in svg
    assert "PUL+" in svg
    assert ">W<" not in svg


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
    rail = create_node(Dot, "rail", label="+5V", label_alignment=Alignment.LEFT)
    rail = translate(0, 4)(rail)
    rail = create_rail(rail, Direction.VERTICAL, 8, anchor=Alignment.TOP)

    tap = create_node(Dot, "tap", label="PUL+")
    tap = translate(4, 1)(tap)

    feed = create_element(Wire, "", None, rail, tap)
    schema = create_schema([rail, tap], [feed])
    outfile = tmp_path / "rail.svg"

    render_schemdraw(schema, file=outfile)

    svg = outfile.read_text(encoding="utf-8")
    assert "<svg" in svg
    assert "+5V" in svg
    assert "PUL+" in svg


def test_create_schema_rejects_duplicate_node_names():
    node_a = create_node(Dot, "same")
    node_b = create_node(Dot, "same")

    try:
        create_schema([node_a, node_b], [])
    except ValueError as error:
        assert "Duplicate schema node name" in str(error)
    else:
        raise AssertionError("duplicate node names should be rejected")
