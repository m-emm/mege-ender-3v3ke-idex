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
    assign_schema_nets_to_stripboard,
    compact_sparse_stripboard_rows,
    get_schema_net_visualizations,
    point_at,
    render_schemdraw,
    render_stripboard,
    render_stripboard_overlay,
    rotate,
    snap_schema_to_stripboard,
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


def _create_stripboard_mapping_schema():
    top_net = create_net("top")
    middle_net = create_net("middle")
    low_net = create_net("low")

    top = create_node(Dot, "top", net=top_net, label="TOP")
    middle = translate(2, -2)(create_node(Dot, "middle", net=middle_net))
    low = translate(4, -4)(create_node(Dot, "low", net=low_net, label="LOW"))

    r1 = translate(0, -1)(create_element(Resistor, "R1", "1k", top, middle))
    r2 = translate(4, -3)(create_element(Resistor, "R2", "2k", middle, low))

    return create_schema([top, middle, low], [r1, r2])


def _create_sparse_stripboard_schema():
    dense_net = create_net("dense")
    sparse_a_net = create_net("sparse_a")
    sparse_b_net = create_net("sparse_b")
    sparse_c_net = create_net("sparse_c")

    dense_nodes = [
        translate(column, 0)(create_node(Dot, f"dense_{column}", net=dense_net))
        for column in range(9)
    ]
    sparse_a = translate(0, -2)(
        create_node(Dot, "sparse_a", net=sparse_a_net, label="A")
    )
    sparse_b = translate(4, -4)(
        create_node(Dot, "sparse_b", net=sparse_b_net, label="B")
    )
    sparse_c = translate(8, -6)(
        create_node(Dot, "sparse_c", net=sparse_c_net, label="C")
    )

    return create_schema([*dense_nodes, sparse_a, sparse_b, sparse_c], [])


def test_get_schema_net_visualizations_sorts_nets_by_representative_y():
    schema = _create_stripboard_mapping_schema()

    visualizations = get_schema_net_visualizations(schema)

    assert [visualization.net_name for visualization in visualizations] == [
        "low",
        "middle",
        "top",
    ]
    middle = visualizations[1]
    assert [node.name for node in middle.node_views] == ["middle"]
    assert {
        (terminal.element_name, terminal.terminal_name)
        for terminal in middle.terminal_points
    } == {("R1", "end"), ("R2", "start")}
    assert middle.representative_y == pytest.approx(-2.0)


def test_get_schema_net_visualizations_includes_unconnected_views():
    loose_net = create_net("loose")
    loose = translate(3, 2)(create_node(Dot, "loose", net=loose_net))
    schema = create_schema([loose], [])

    visualizations = get_schema_net_visualizations(schema)

    assert [visualization.net_name for visualization in visualizations] == ["loose"]
    assert visualizations[0].node_views[0].position == (3.0, 2.0)
    assert visualizations[0].terminal_points == ()


def test_assign_schema_nets_to_stripboard_uses_one_row_per_net():
    schema = _create_stripboard_mapping_schema()

    assignment = assign_schema_nets_to_stripboard(schema)

    assert assignment.stripboard.height_pitches == 3
    assert assignment.net_rows == {"top": 0, "middle": 1, "low": 2}
    assert [
        visualization.net_name for visualization in assignment.net_visualizations
    ] == ["top", "middle", "low"]
    assert assignment.used_source_columns == (0, 2, 4)
    assert assignment.column_map == {0: 1, 2: 2, 4: 3}
    assert assignment.stripboard.width_pitches == 5


def test_compact_sparse_stripboard_rows_merges_only_sparse_rows():
    schema = _create_sparse_stripboard_schema()
    assignment = assign_schema_nets_to_stripboard(schema)

    compacted = compact_sparse_stripboard_rows(assignment)

    assert assignment.stripboard.height_pitches == 4
    assert compacted.stripboard.height_pitches == 3
    assert compacted.stripboard.width_pitches == assignment.stripboard.width_pitches
    assert compacted.net_rows == {
        "dense": 0,
        "sparse_a": 1,
        "sparse_b": 1,
        "sparse_c": 2,
    }

    dense_run = next(run for run in compacted.net_runs if run.net_name == "dense")
    assert dense_run.compacted is False
    assert dense_run.start_col == 0
    assert dense_run.end_col == compacted.stripboard.width_pitches - 1

    sparse_runs = [run for run in compacted.net_runs if run.compacted]
    assert [(run.net_name, run.row, run.start_col, run.end_col) for run in sparse_runs] == [
        ("sparse_a", 1, 1, 4),
        ("sparse_b", 1, 6, 9),
        ("sparse_c", 2, 1, 4),
    ]
    assert len(compacted.cuts) == 1
    assert (compacted.cuts[0].row, compacted.cuts[0].col) == (1, 5)


def test_compacted_sparse_rows_snap_markers_inside_runs_not_cuts():
    schema = _create_sparse_stripboard_schema()
    assignment = compact_sparse_stripboard_rows(
        assign_schema_nets_to_stripboard(schema)
    )

    assert assignment.net_column_maps["sparse_a"] == {0: 2}
    assert assignment.net_column_maps["sparse_b"] == {4: 7}
    assert assignment.net_column_maps["sparse_c"] == {8: 2}

    snapped = snap_schema_to_stripboard(schema, assignment)
    positions = {node.name: node.position for node in snapped.node_views}

    assert positions["sparse_a"] == pytest.approx((2.5, 1.5))
    assert positions["sparse_b"] == pytest.approx((7.5, 1.5))
    assert positions["sparse_c"] == pytest.approx((2.5, 2.5))
    assert all(
        abs(position[0] - 5.5) > 1e-9 or abs(position[1] - 1.5) > 1e-9
        for position in positions.values()
    )


def test_snap_schema_to_stripboard_moves_node_views_onto_rows():
    schema = _create_stripboard_mapping_schema()
    assignment = assign_schema_nets_to_stripboard(schema)

    snapped = snap_schema_to_stripboard(schema, assignment)

    for node_view in snapped.node_views:
        expected_row = assignment.net_rows[node_view.net.name]
        assert node_view.position[1] == pytest.approx(0.5 + expected_row)
        assert (node_view.position[0] - 0.5).is_integer()


def test_render_stripboard_overlay_writes_svg(tmp_path):
    schema = _create_stripboard_mapping_schema()
    assignment = assign_schema_nets_to_stripboard(schema)
    outfile = tmp_path / "overlay.svg"

    render_stripboard_overlay(
        assignment.stripboard,
        assignment,
        schema,
        file=outfile,
    )

    svg = outfile.read_text(encoding="utf-8")
    assert "<svg" in svg
    assert 'class="copper-strip"' in svg
    assert 'class="hole"' in svg
    assert 'class="overlay-net-label"' in svg
    assert 'class="overlay-node"' in svg
    assert ">top</text>" in svg


def test_render_compacted_stripboard_overlay_writes_cuts_and_run_labels(tmp_path):
    schema = _create_sparse_stripboard_schema()
    assignment = compact_sparse_stripboard_rows(
        assign_schema_nets_to_stripboard(schema)
    )
    outfile = tmp_path / "compacted_overlay.svg"

    render_stripboard_overlay(
        assignment.stripboard,
        assignment,
        schema,
        file=outfile,
    )

    svg = outfile.read_text(encoding="utf-8")
    assert 'class="strip-cut"' in svg
    assert 'class="overlay-net-run-label"' in svg
    assert ">sparse_a</text>" in svg


def test_render_stripboard_overlay_writes_png(tmp_path):
    schema = _create_stripboard_mapping_schema()
    assignment = assign_schema_nets_to_stripboard(schema)
    outfile = tmp_path / "overlay.png"

    render_stripboard_overlay(
        assignment.stripboard,
        assignment,
        schema,
        file=outfile,
    )

    assert outfile.exists()
    assert outfile.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_render_compacted_stripboard_overlay_writes_png(tmp_path):
    schema = _create_sparse_stripboard_schema()
    assignment = compact_sparse_stripboard_rows(
        assign_schema_nets_to_stripboard(schema)
    )
    outfile = tmp_path / "compacted_overlay.png"

    render_stripboard_overlay(
        assignment.stripboard,
        assignment,
        schema,
        file=outfile,
    )

    assert outfile.exists()
    assert outfile.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


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
