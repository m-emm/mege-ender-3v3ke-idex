from mege_ender_3v3ke_idex.circuit_schematics.examples.voltage_divider import (
    create_voltage_divider,
)
from mege_ender_3v3ke_idex.circuit_schematics.simple import (
    Alignment,
    Dot,
    Resistor,
    Wire,
    align,
    create_element,
    create_node,
    create_schema,
    render_schemdraw,
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
    feed = create_element(Wire, "", None, vcc, pul_plus)
    schema = create_schema([vcc, pul_plus], [feed])
    outfile = tmp_path / "wire.svg"

    render_schemdraw(schema, file=outfile)

    svg = outfile.read_text(encoding="utf-8")
    assert "<svg" in svg
    assert "PUL+" in svg
    assert ">W<" not in svg


def test_create_schema_rejects_duplicate_node_names():
    node_a = create_node(Dot, "same")
    node_b = create_node(Dot, "same")

    try:
        create_schema([node_a, node_b], [])
    except ValueError as error:
        assert "Duplicate schema node name" in str(error)
    else:
        raise AssertionError("duplicate node names should be rejected")
