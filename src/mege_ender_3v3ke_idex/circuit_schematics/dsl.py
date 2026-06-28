"""Minimal alignment-first schematic DSL.

The DSL keeps the electrical graph separate from the drawn layout:

- ``Net`` is the logical electrical node.
- ``NodeView`` is a placed visual representation of a net.
- ``Element`` stores stable terminal view ids and net names.
- ``WireSegment`` draws a conductor between two views of the same net.
"""

from __future__ import annotations

import copy
import html
import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import schemdraw
import schemdraw.elements as elm

TWO_TERMINAL_WIDTH = 0.8
TWO_TERMINAL_HEIGHT = 2.0
ZENER_HEIGHT = 1.25
FET_DX = 0.8333333333333333
FET_Y = 0.8333333333333333
BJT_X = 0.752
BJT_Y = 0.697
DEFAULT_ELEMENT_BBOX_PADDING = 0.35
LABEL_GAP = 0.16
EPS = 1e-9
STRIPBOARD_BOARD_MARGIN = 0.5
STRIPBOARD_STRIP_INSET = 0.25
STRIPBOARD_STRIP_HEIGHT = 0.55
STRIPBOARD_HOLE_RADIUS = 0.22
STRIPBOARD_STROKE_WIDTH = 0.035
STRIPBOARD_BOARD_FILL = "#f7e48b"
STRIPBOARD_BOARD_STROKE = "#e6ca70"
STRIPBOARD_STRIP_FILL = "#d98b61"
STRIPBOARD_STRIP_STROKE = "#b66d47"
STRIPBOARD_HOLE_FILL = "#fbfbfb"
STRIPBOARD_HOLE_STROKE = "#333333"
STRIPBOARD_OVERLAY_NODE_FILL = "#2563eb"
STRIPBOARD_OVERLAY_TERMINAL_FILL = "#111827"
STRIPBOARD_OVERLAY_ELEMENT_STROKE = "#1f2937"
STRIPBOARD_OVERLAY_TEXT_FILL = "#b91c1c"
STRIPBOARD_OVERLAY_TEXT_HALO = "#ffffff"
STRIPBOARD_OVERLAY_STROKE_WIDTH = 0.045
STRIPBOARD_OVERLAY_NODE_RADIUS = 0.14
STRIPBOARD_OVERLAY_TERMINAL_RADIUS = 0.09
STRIPBOARD_OVERLAY_ELEMENT_LABEL_SIZE = 0.42
STRIPBOARD_OVERLAY_NODE_LABEL_SIZE = 0.36
STRIPBOARD_OVERLAY_NET_LABEL_SIZE = 0.42
STRIPBOARD_OVERLAY_NET_LABEL_MARGIN = 3.1


class NodeType(Enum):
    DOT = auto()
    GROUND = auto()


class ElementType(Enum):
    WIRE = auto()
    RESISTOR = auto()
    FUSE = auto()
    CAPACITOR = auto()
    PMOS = auto()
    BJT_NPN = auto()
    ZENER = auto()


Dot = NodeType.DOT
Ground = NodeType.GROUND
Resistor = ElementType.RESISTOR
Fuse = ElementType.FUSE
Capacitor = ElementType.CAPACITOR
PMos = ElementType.PMOS
BjtNpn = ElementType.BJT_NPN
Wire = ElementType.WIRE
Zener = ElementType.ZENER


class Alignment(Enum):
    LEFT = auto()
    RIGHT = auto()
    TOP = auto()
    BOTTOM = auto()
    CENTER = auto()
    TOP_CENTER = auto()
    BOTTOM_CENTER = auto()
    LEFT_CENTER = auto()
    RIGHT_CENTER = auto()
    STACK_LEFT = auto()
    STACK_RIGHT = auto()
    STACK_TOP = auto()
    STACK_BOTTOM = auto()


class Direction(Enum):
    HORIZONTAL = auto()
    VERTICAL = auto()


@dataclass(frozen=True)
class Net:
    name: str


@dataclass(frozen=True)
class Stripboard:
    width_pitches: int
    height_pitches: int
    strip_direction: Direction = Direction.HORIZONTAL
    pitch_mm: float = 2.54

    def __post_init__(self):
        _validate_positive_integer(self.width_pitches, "width_pitches")
        _validate_positive_integer(self.height_pitches, "height_pitches")
        if self.strip_direction not in (Direction.HORIZONTAL, Direction.VERTICAL):
            raise ValueError("strip_direction must be Direction.HORIZONTAL or VERTICAL.")
        if not isinstance(self.pitch_mm, (int, float)) or isinstance(
            self.pitch_mm, bool
        ):
            raise TypeError("pitch_mm must be a positive number.")
        if self.pitch_mm <= 0:
            raise ValueError("pitch_mm must be positive.")
        object.__setattr__(self, "pitch_mm", float(self.pitch_mm))


@dataclass(frozen=True)
class SchemaTerminalVisualization:
    element_name: str
    terminal_name: str
    view_name: str
    net_name: str
    position: tuple[float, float]


@dataclass(frozen=True)
class SchemaNetVisualization:
    net_name: str
    node_views: tuple[NodeView, ...]
    terminal_points: tuple[SchemaTerminalVisualization, ...]
    representative_y: float
    x_min: float
    x_max: float


@dataclass(frozen=True)
class StripboardNetAssignment:
    stripboard: Stripboard
    net_visualizations: tuple[SchemaNetVisualization, ...]
    net_rows: dict[str, int]
    x_offset: int
    column_pitch: float
    left_margin_pitches: int
    right_margin_pitches: int


@dataclass
class ElementSpec:
    terminals: tuple[str, ...]
    local_anchors: dict[str, tuple[float, float]]
    local_bbox: list[list[float]]
    schemdraw_factory: Callable[[], object]
    positional_terminals: tuple[str, ...] = ()
    bbox_padding: float = DEFAULT_ELEMENT_BBOX_PADDING


def _two_terminal_spec(factory, height=TWO_TERMINAL_HEIGHT):
    half_width = TWO_TERMINAL_WIDTH / 2.0
    half_height = height / 2.0
    return ElementSpec(
        terminals=("start", "end"),
        local_anchors={
            "start": (0.0, half_height),
            "end": (0.0, -half_height),
        },
        local_bbox=[[-half_width, -half_height], [half_width, half_height]],
        schemdraw_factory=factory,
        positional_terminals=("start", "end"),
    )


ELEMENT_SPECS = {
    Wire: _two_terminal_spec(elm.Line),
    Resistor: _two_terminal_spec(elm.Resistor),
    Fuse: _two_terminal_spec(elm.Fuse),
    Capacitor: _two_terminal_spec(elm.Capacitor),
    Zener: _two_terminal_spec(elm.Zener, height=ZENER_HEIGHT),
    PMos: ElementSpec(
        terminals=("source", "gate", "drain"),
        local_anchors={
            "source": (0.0, FET_Y),
            "gate": (-FET_DX, FET_Y - 0.5),
            "drain": (0.0, -FET_Y),
        },
        local_bbox=[[-FET_DX, -FET_Y], [0.35, FET_Y]],
        schemdraw_factory=lambda: elm.PMos(diode=True),
    ),
    BjtNpn: ElementSpec(
        terminals=("base", "collector", "emitter"),
        local_anchors={
            "base": (-BJT_X, 0.0),
            "collector": (0.0, BJT_Y),
            "emitter": (0.0, -BJT_Y),
        },
        local_bbox=[[-BJT_X, -0.72], [0.35, BJT_Y]],
        schemdraw_factory=lambda: elm.BjtNpn(circle=True),
    ),
}


@dataclass
class NodeView:
    node_type: NodeType
    name: str
    net: Net
    label: str | None = None
    kind: str | None = None
    label_loc: str = "right"
    position: tuple[float, float] = (0.0, 0.0)
    placement_explicit: bool = False
    rail_direction: Direction | None = None
    rail_length: float | None = None
    rail_anchor: Alignment = Alignment.CENTER

    def get_bounding_box(self):
        if self.rail_direction is not None:
            start, end = _rail_endpoints(self)
            return [
                [min(start[0], end[0]), min(start[1], end[1])],
                [max(start[0], end[0]), max(start[1], end[1])],
            ]
        return [
            [self.position[0], self.position[1]],
            [self.position[0], self.position[1]],
        ]


Node = NodeView


@dataclass
class Anchor:
    owner: object
    name: str

    @property
    def position(self):
        return self.owner.anchor_position(self.name)

    def get_bounding_box(self):
        x, y = self.position
        return [[x, y], [x, y]]

    def point(self):
        return self.position


@dataclass
class ReferencePoint:
    owner: object
    subject: object
    alignment: Alignment

    @property
    def position(self):
        return _aligned_point(self.subject, self.alignment)

    def get_bounding_box(self):
        x, y = self.position
        return [[x, y], [x, y]]

    def point(self):
        return self.position


@dataclass
class Element:
    element_type: ElementType
    name: str
    value: str | None
    terminal_views: dict[str, str]
    terminal_nets: dict[str, str]
    label_loc: str = "auto"
    position: tuple[float, float] = (0.0, 0.0)
    angle: float = 0.0

    def __getattr__(self, name):
        element_type = self.__dict__.get("element_type")
        spec = ELEMENT_SPECS.get(element_type)
        if spec is not None and name in spec.terminals:
            return Anchor(self, name)
        raise AttributeError(name)

    def anchor(self, name):
        if name not in _element_spec(self).terminals:
            raise KeyError(f"Unknown anchor {name!r} for {self.name}")
        return Anchor(self, name)

    def local_anchor(self, name):
        try:
            return _element_spec(self).local_anchors[name]
        except KeyError as error:
            raise KeyError(f"Unknown anchor {name!r} for {self.name}") from error

    def anchor_position(self, name):
        return _add_points(
            self.position, _rotate_point(self.local_anchor(name), self.angle)
        )

    def get_bounding_box(self):
        spec = _element_spec(self)
        corners = _box_corners(_padded_box(spec.local_bbox, spec.bbox_padding))
        points = [
            _add_points(self.position, _rotate_point(corner, self.angle))
            for corner in corners
        ]
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return [[min(xs), min(ys)], [max(xs), max(ys)]]


@dataclass
class WireSegment:
    start_view: str
    end_view: str
    net_name: str
    name: str = ""

    @property
    def position(self):
        return (0.0, 0.0)


@dataclass
class Schema:
    nets: list[Net]
    node_views: list[NodeView]
    elements: list[Element]
    wires: list[WireSegment]

    @property
    def nodes(self):
        return self.node_views

    def get_bounding_box(self):
        node_views_by_name = _node_views_by_name(self.node_views)
        boxes = [
            *[element.get_bounding_box() for element in self.elements],
            *[node.get_bounding_box() for node in self.node_views],
            *[_wire_bounding_box(wire, node_views_by_name) for wire in self.wires],
        ]
        if not boxes:
            return [[0.0, 0.0], [0.0, 0.0]]
        return [
            [min(box[0][0] for box in boxes), min(box[0][1] for box in boxes)],
            [max(box[1][0] for box in boxes), max(box[1][1] for box in boxes)],
        ]


def create_net(name):
    return Net(name=str(name))


def create_stripboard(
    width_pitches,
    height_pitches,
    strip_direction=Direction.HORIZONTAL,
    pitch_mm=2.54,
):
    return Stripboard(
        width_pitches=width_pitches,
        height_pitches=height_pitches,
        strip_direction=strip_direction,
        pitch_mm=pitch_mm,
    )


def create_node(
    node_type,
    name,
    label=None,
    kind=None,
    label_alignment=None,
    net=None,
    **kwargs,
):
    if node_type not in (Dot, Ground):
        raise ValueError("Only Dot and Ground node views are supported in this DSL.")
    if kwargs:
        raise TypeError(f"Unsupported node arguments: {sorted(kwargs)}")
    label_loc = "right"
    if label_alignment is not None:
        label_loc = _label_loc_from_alignment(label_alignment)
    return NodeView(
        node_type=node_type,
        name=name,
        net=_coerce_net(net, default_name=name),
        label=label,
        kind=kind,
        label_loc=label_loc,
    )


def create_rail(node, direction, length, anchor=Alignment.CENTER):
    if not isinstance(node, NodeView):
        raise TypeError("create_rail expects a NodeView.")
    if direction not in (Direction.HORIZONTAL, Direction.VERTICAL):
        raise ValueError("Rail direction must be HORIZONTAL or VERTICAL.")
    if length <= 0:
        raise ValueError("Rail length must be positive.")
    if anchor not in {
        Alignment.CENTER,
        Alignment.LEFT,
        Alignment.RIGHT,
        Alignment.TOP,
        Alignment.BOTTOM,
    }:
        raise ValueError("Rail anchor must be CENTER, LEFT, RIGHT, TOP, or BOTTOM.")

    modified = copy.deepcopy(node)
    modified.rail_direction = direction
    modified.rail_length = float(length)
    modified.rail_anchor = anchor
    return modified


def create_element(
    element_type, name, value=None, *nodes, label_loc="auto", **terminal_nodes
):
    if element_type is Wire:
        return _create_wire_from_element_args(name, nodes, terminal_nodes)

    spec = _spec_for_type(element_type)
    if nodes and terminal_nodes:
        raise TypeError("Use either positional nodes or named terminal nodes.")
    if nodes:
        if len(nodes) != len(spec.positional_terminals):
            raise TypeError(
                f"{element_type.name} expects named terminals: "
                f"{', '.join(spec.terminals)}"
            )
        terminal_nodes = dict(zip(spec.positional_terminals, nodes))

    terminal_nodes = _validate_terminal_views(element_type, terminal_nodes)
    return Element(
        element_type=element_type,
        name=name,
        value=value,
        terminal_views={
            terminal: node_view.name for terminal, node_view in terminal_nodes.items()
        },
        terminal_nets={
            terminal: node_view.net.name
            for terminal, node_view in terminal_nodes.items()
        },
        label_loc=label_loc,
    )


def create_wire(start, end, name=""):
    if not isinstance(start, NodeView) or not isinstance(end, NodeView):
        raise TypeError("create_wire endpoints must be NodeView objects.")
    if start.net.name != end.net.name:
        raise ValueError(
            f"Wire endpoints must be views of the same net: "
            f"{start.name!r} is {start.net.name!r}, "
            f"{end.name!r} is {end.net.name!r}."
        )
    return WireSegment(
        start_view=start.name,
        end_view=end.name,
        net_name=start.net.name,
        name=name,
    )


def create_schema(node_views, elements, wires=None):
    schema_node_views = list(node_views)
    schema_elements = []
    schema_wires = list(wires or [])
    for item in elements:
        if isinstance(item, WireSegment):
            schema_wires.append(item)
        else:
            schema_elements.append(item)

    nets = _validate_schema_items(schema_node_views, schema_elements, schema_wires)
    return Schema(
        nets=nets,
        node_views=schema_node_views,
        elements=schema_elements,
        wires=schema_wires,
    )


def get_schema_net_visualizations(schema):
    if not isinstance(schema, Schema):
        raise TypeError("get_schema_net_visualizations expects a Schema object.")

    node_views_by_name = _node_views_by_name(schema.node_views)
    node_points = _schema_node_points(schema, node_views_by_name)
    visual_nodes_by_net = {net.name: [] for net in schema.nets}
    terminals_by_net = {net.name: [] for net in schema.nets}

    for node_view in schema.node_views:
        point = node_points.get(node_view.name, (node_view.position,))[0]
        visual_node = copy.deepcopy(node_view)
        visual_node.position = point
        visual_node.placement_explicit = True
        visual_nodes_by_net.setdefault(node_view.net.name, []).append(visual_node)

    for element in schema.elements:
        for terminal_name, view_name in element.terminal_views.items():
            net_name = element.terminal_nets[terminal_name]
            terminals_by_net.setdefault(net_name, []).append(
                SchemaTerminalVisualization(
                    element_name=element.name,
                    terminal_name=terminal_name,
                    view_name=view_name,
                    net_name=net_name,
                    position=element.anchor_position(terminal_name),
                )
            )

    visualizations = []
    for net in schema.nets:
        node_views = tuple(visual_nodes_by_net.get(net.name, ()))
        terminal_points = tuple(terminals_by_net.get(net.name, ()))
        points = [
            *[node_view.position for node_view in node_views],
            *[terminal.position for terminal in terminal_points],
        ]
        if not points:
            continue
        visualizations.append(
            SchemaNetVisualization(
                net_name=net.name,
                node_views=node_views,
                terminal_points=terminal_points,
                representative_y=_median(point[1] for point in points),
                x_min=min(point[0] for point in points),
                x_max=max(point[0] for point in points),
            )
        )

    return tuple(
        sorted(
            visualizations,
            key=lambda visualization: (
                visualization.representative_y,
                visualization.net_name,
            ),
        )
    )


def assign_schema_nets_to_stripboard(
    schema,
    left_margin_pitches=1,
    right_margin_pitches=1,
    column_pitch=1.0,
):
    _validate_nonnegative_integer(left_margin_pitches, "left_margin_pitches")
    _validate_nonnegative_integer(right_margin_pitches, "right_margin_pitches")
    if not isinstance(column_pitch, (int, float)) or isinstance(column_pitch, bool):
        raise TypeError("column_pitch must be a positive number.")
    if column_pitch <= 0:
        raise ValueError("column_pitch must be positive.")

    net_visualizations = get_schema_net_visualizations(schema)
    if not net_visualizations:
        return StripboardNetAssignment(
            stripboard=create_stripboard(1, 1),
            net_visualizations=(),
            net_rows={},
            x_offset=left_margin_pitches,
            column_pitch=float(column_pitch),
            left_margin_pitches=left_margin_pitches,
            right_margin_pitches=right_margin_pitches,
        )

    min_col = math.floor(
        min(visualization.x_min for visualization in net_visualizations) / column_pitch
    )
    max_col = math.ceil(
        max(visualization.x_max for visualization in net_visualizations) / column_pitch
    )
    board_width = (
        max_col
        - min_col
        + 1
        + left_margin_pitches
        + right_margin_pitches
    )
    board_height = len(net_visualizations)
    x_offset = left_margin_pitches - min_col

    board_visualizations = tuple(reversed(net_visualizations))

    return StripboardNetAssignment(
        stripboard=create_stripboard(board_width, board_height),
        net_visualizations=board_visualizations,
        net_rows={
            visualization.net_name: row
            for row, visualization in enumerate(board_visualizations)
        },
        x_offset=x_offset,
        column_pitch=float(column_pitch),
        left_margin_pitches=left_margin_pitches,
        right_margin_pitches=right_margin_pitches,
    )


def snap_schema_to_stripboard(schema, assignment, column_pitch=None):
    if not isinstance(schema, Schema):
        raise TypeError("snap_schema_to_stripboard expects a Schema object.")
    if not isinstance(assignment, StripboardNetAssignment):
        raise TypeError("assignment must be a StripboardNetAssignment.")

    pitch = assignment.column_pitch if column_pitch is None else column_pitch
    if not isinstance(pitch, (int, float)) or isinstance(pitch, bool):
        raise TypeError("column_pitch must be a positive number.")
    if pitch <= 0:
        raise ValueError("column_pitch must be positive.")

    snapped = copy.deepcopy(schema)
    for node_view in snapped.node_views:
        if node_view.net.name not in assignment.net_rows:
            continue
        node_view.position = _snap_schema_point_to_stripboard(
            node_view.position,
            node_view.net.name,
            assignment,
            pitch,
        )
        node_view.placement_explicit = True

    for element in snapped.elements:
        translations = []
        for terminal_name, net_name in element.terminal_nets.items():
            if net_name not in assignment.net_rows:
                continue
            source = element.anchor_position(terminal_name)
            target = _snap_schema_point_to_stripboard(
                source,
                net_name,
                assignment,
                pitch,
            )
            translations.append((target[0] - source[0], target[1] - source[1]))
        if translations:
            element.position = _add_points(
                element.position,
                (
                    _median(delta[0] for delta in translations),
                    _median(delta[1] for delta in translations),
                ),
            )

    return snapped


def translate(x, y):
    def retval(obj):
        moved = copy.deepcopy(obj)
        _translate_in_place(moved, (float(x), float(y)))
        return moved

    return retval


def rotate(angle, center=None):
    def retval(obj):
        rotated = copy.deepcopy(obj)
        _rotate_in_place(rotated, float(angle), center)
        return rotated

    return retval


def point_at(obj, alignment):
    if alignment not in {
        Alignment.CENTER,
        Alignment.LEFT,
        Alignment.RIGHT,
        Alignment.TOP,
        Alignment.BOTTOM,
        Alignment.TOP_CENTER,
        Alignment.BOTTOM_CENTER,
        Alignment.LEFT_CENTER,
        Alignment.RIGHT_CENTER,
    }:
        raise ValueError(
            "point_at alignment must be CENTER, LEFT, RIGHT, TOP, BOTTOM, "
            "TOP_CENTER, BOTTOM_CENTER, LEFT_CENTER, or RIGHT_CENTER."
        )
    owner = obj.owner if isinstance(obj, (Anchor, ReferencePoint)) else obj
    return ReferencePoint(owner, obj, alignment)


def align_translation(part, to, alignment, axes=None, stack_gap=0):
    dx, dy = _alignment_delta(part, to, alignment, axes=axes, stack_gap=stack_gap)
    return translate(dx, dy)


def align(part, to, alignment, axes=None, stack_gap=0):
    target = part.owner if isinstance(part, (Anchor, ReferencePoint)) else part
    return align_translation(part, to, alignment, axes=axes, stack_gap=stack_gap)(
        target
    )


def modify_label_alignment(element, alignment):
    modified = copy.deepcopy(element)
    modified.label_loc = _label_loc_from_alignment(alignment)
    return modified


def render_schemdraw(schema, file, show=False):
    node_views_by_name = _node_views_by_name(schema.node_views)
    node_points = _schema_node_points(schema, node_views_by_name)
    rail_taps = {
        name: []
        for name, (_, node_view, _) in node_points.items()
        if _is_rail(node_view)
    }

    with schemdraw.Drawing(file=file, show=show) as drawing:
        drawing.config(unit=2.0, inches_per_unit=0.55, fontsize=10)

        for wire in schema.wires:
            start, end = _wire_endpoints(wire, node_points, node_views_by_name)
            _record_wire_rail_taps(wire, node_views_by_name, rail_taps, start, end)
            _add_wire(drawing, start, end, direct=True)

        for element in schema.elements:
            for anchor_name, view_name in element.terminal_views.items():
                node_view = node_views_by_name[view_name]
                terminal = element.anchor_position(anchor_name)
                node_point = _node_connection_point(
                    node_view,
                    node_points[node_view.name][0],
                    terminal,
                )
                if _is_rail(node_view):
                    rail_taps[node_view.name].append(node_point)
                _add_wire(
                    drawing,
                    terminal,
                    node_point,
                    direct=_prefers_direct_terminal_wire(element),
                )

        for element in schema.elements:
            label = (
                element.name
                if element.value is None
                else f"{element.name}\n{element.value}"
            )
            drawing.add(_schemdraw_element(element))
            if label:
                drawing.add(elm.Label(label).at(_element_label_position(element)))

        for node_name in sorted(node_points):
            point, node_view, terminal_count = node_points[node_name]
            if _is_rail(node_view):
                drawing.add(elm.Line().endpoints(*_rail_endpoints(node_view)))
            if _should_render_node(node_view, terminal_count):
                if node_view.node_type is Ground:
                    ground = elm.Ground().at(point)
                    if node_view.label:
                        ground = ground.label(node_view.label, loc=node_view.label_loc)
                    drawing.add(ground)
                else:
                    dot = elm.Dot().at(point)
                    if node_view.label:
                        dot = dot.label(node_view.label, loc=node_view.label_loc)
                    drawing.add(dot)
            if _is_rail(node_view):
                for tap in _unique_points(rail_taps.get(node_name, [])):
                    drawing.add(elm.Dot().at(tap))

    if Path(file).suffix == ".svg":
        _strip_trailing_whitespace(file)


def render_stripboard(stripboard, file, scale=32):
    if not isinstance(stripboard, Stripboard):
        raise TypeError("render_stripboard expects a Stripboard object.")
    if stripboard.strip_direction is not Direction.HORIZONTAL:
        raise NotImplementedError("Only horizontal stripboards are supported for now.")

    path = Path(file)
    suffix = path.suffix.lower()
    if suffix == ".svg":
        _render_stripboard_svg(stripboard, path, scale=scale)
    elif suffix == ".png":
        _render_stripboard_png(stripboard, path, scale=scale)
    else:
        raise ValueError("Stripboard output file must end in .svg or .png.")


def render_stripboard_overlay(stripboard, assignment, schema, file, scale=32):
    if not isinstance(stripboard, Stripboard):
        raise TypeError("render_stripboard_overlay expects a Stripboard object.")
    if not isinstance(assignment, StripboardNetAssignment):
        raise TypeError("assignment must be a StripboardNetAssignment.")
    if not isinstance(schema, Schema):
        raise TypeError("schema must be a Schema.")
    if stripboard.strip_direction is not Direction.HORIZONTAL:
        raise NotImplementedError("Only horizontal stripboards are supported for now.")
    if (
        stripboard.width_pitches != assignment.stripboard.width_pitches
        or stripboard.height_pitches != assignment.stripboard.height_pitches
        or stripboard.strip_direction is not assignment.stripboard.strip_direction
    ):
        raise ValueError("stripboard must match assignment.stripboard dimensions.")

    path = Path(file)
    suffix = path.suffix.lower()
    if suffix == ".svg":
        _render_stripboard_overlay_svg(stripboard, assignment, schema, path, scale)
    elif suffix == ".png":
        _render_stripboard_overlay_png(stripboard, assignment, schema, path, scale)
    else:
        raise ValueError("Stripboard overlay output file must end in .svg or .png.")


def _render_stripboard_svg(stripboard, path, scale):
    scale = _validate_render_scale(scale)
    width, height = _stripboard_size(stripboard)
    width_px = width * scale
    height_px = height * scale

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width_px:.0f}" height="{height_px:.0f}" '
            f'viewBox="0 0 {width:.3f} {height:.3f}">'
        ),
        "  <title>Stripboard</title>",
        (
            f'  <rect class="board" x="0" y="0" width="{width:.3f}" '
            f'height="{height:.3f}" fill="{STRIPBOARD_BOARD_FILL}" '
            f'stroke="{STRIPBOARD_BOARD_STROKE}" '
            f'stroke-width="{STRIPBOARD_STROKE_WIDTH:.3f}"/>'
        ),
    ]

    for row in range(stripboard.height_pitches):
        x, y, strip_width, strip_height = _stripboard_strip_rect(stripboard, row)
        lines.append(
            f'  <rect class="copper-strip" data-row="{row}" '
            f'x="{x:.3f}" y="{y:.3f}" width="{strip_width:.3f}" '
            f'height="{strip_height:.3f}" fill="{STRIPBOARD_STRIP_FILL}" '
            f'stroke="{STRIPBOARD_STRIP_STROKE}" '
            f'stroke-width="{STRIPBOARD_STROKE_WIDTH:.3f}"/>'
        )

    for col, row, x, y in _stripboard_holes(stripboard):
        lines.append(
            f'  <circle class="hole" data-col="{col}" data-row="{row}" '
            f'cx="{x:.3f}" cy="{y:.3f}" r="{STRIPBOARD_HOLE_RADIUS:.3f}" '
            f'fill="{STRIPBOARD_HOLE_FILL}" stroke="{STRIPBOARD_HOLE_STROKE}" '
            f'stroke-width="{STRIPBOARD_STROKE_WIDTH:.3f}"/>'
        )

    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _render_stripboard_png(stripboard, path, scale):
    scale = _validate_render_scale(scale)
    try:
        from PIL import Image, ImageDraw
    except ImportError as error:
        raise RuntimeError("Pillow is required to render stripboard PNG files.") from error

    width, height = _stripboard_size(stripboard)
    image_width = max(1, int(round(width * scale)))
    image_height = max(1, int(round(height * scale)))
    image = Image.new("RGB", (image_width, image_height), "white")
    draw = ImageDraw.Draw(image)

    draw.rectangle(
        _px_rect(0, 0, width, height, scale),
        fill=STRIPBOARD_BOARD_FILL,
        outline=STRIPBOARD_BOARD_STROKE,
        width=_px_stroke(scale),
    )

    for row in range(stripboard.height_pitches):
        strip_rect = _stripboard_strip_rect(stripboard, row)
        draw.rectangle(
            _px_rect(*strip_rect, scale),
            fill=STRIPBOARD_STRIP_FILL,
            outline=STRIPBOARD_STRIP_STROKE,
            width=_px_stroke(scale),
        )

    radius = STRIPBOARD_HOLE_RADIUS
    for _, _, x, y in _stripboard_holes(stripboard):
        draw.ellipse(
            _px_rect(x - radius, y - radius, radius * 2, radius * 2, scale),
            fill=STRIPBOARD_HOLE_FILL,
            outline=STRIPBOARD_HOLE_STROKE,
            width=_px_stroke(scale),
        )

    image.save(path)


def _render_stripboard_overlay_svg(stripboard, assignment, schema, path, scale):
    scale = _validate_render_scale(scale)
    width, height = _stripboard_size(stripboard)
    label_margin = STRIPBOARD_OVERLAY_NET_LABEL_MARGIN
    width_px = (width + label_margin) * scale
    height_px = height * scale

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width_px:.0f}" height="{height_px:.0f}" '
            f'viewBox="{-label_margin:.3f} 0 '
            f'{width + label_margin:.3f} {height:.3f}">'
        ),
        "  <title>Stripboard Schematic Overlay</title>",
        (
            f'  <rect class="board" x="0" y="0" width="{width:.3f}" '
            f'height="{height:.3f}" fill="{STRIPBOARD_BOARD_FILL}" '
            f'stroke="{STRIPBOARD_BOARD_STROKE}" '
            f'stroke-width="{STRIPBOARD_STROKE_WIDTH:.3f}"/>'
        ),
    ]

    for row in range(stripboard.height_pitches):
        x, y, strip_width, strip_height = _stripboard_strip_rect(stripboard, row)
        net_name = _stripboard_row_net_name(assignment, row)
        if net_name:
            lines.append(
                f'  <text class="overlay-net-label" '
                f'data-row="{row}" data-net="{_svg_attr(net_name)}" '
                f'x="-0.180" y="{STRIPBOARD_BOARD_MARGIN + row + 0.135:.3f}" '
                f'font-size="{STRIPBOARD_OVERLAY_NET_LABEL_SIZE:.3f}" '
                f'font-weight="700" text-anchor="end" '
                f'fill="{STRIPBOARD_OVERLAY_TEXT_FILL}" '
                f'stroke="{STRIPBOARD_OVERLAY_TEXT_HALO}" stroke-width="0.075" '
                f'paint-order="stroke">'
                f'{_svg_text(net_name)}</text>'
            )
        lines.append(
            f'  <rect class="copper-strip" data-row="{row}" '
            f'data-net="{_svg_attr(net_name)}" '
            f'x="{x:.3f}" y="{y:.3f}" width="{strip_width:.3f}" '
            f'height="{strip_height:.3f}" fill="{STRIPBOARD_STRIP_FILL}" '
            f'stroke="{STRIPBOARD_STRIP_STROKE}" '
            f'stroke-width="{STRIPBOARD_STROKE_WIDTH:.3f}"/>'
        )

    for col, row, x, y in _stripboard_holes(stripboard):
        lines.append(
            f'  <circle class="hole" data-col="{col}" data-row="{row}" '
            f'cx="{x:.3f}" cy="{y:.3f}" r="{STRIPBOARD_HOLE_RADIUS:.3f}" '
            f'fill="{STRIPBOARD_HOLE_FILL}" stroke="{STRIPBOARD_HOLE_STROKE}" '
            f'stroke-width="{STRIPBOARD_STROKE_WIDTH:.3f}"/>'
        )

    for element_overlay in _stripboard_overlay_elements(schema, assignment):
        positions = element_overlay["positions"]
        center = element_overlay["center"]
        if len(positions) == 2:
            start, end = positions
            lines.append(
                f'  <line class="overlay-element" '
                f'data-element="{_svg_attr(element_overlay["name"])}" '
                f'x1="{start[0]:.3f}" y1="{start[1]:.3f}" '
                f'x2="{end[0]:.3f}" y2="{end[1]:.3f}" '
                f'stroke="{STRIPBOARD_OVERLAY_ELEMENT_STROKE}" '
                f'stroke-width="{STRIPBOARD_OVERLAY_STROKE_WIDTH:.3f}"/>'
            )
        else:
            for position in positions:
                lines.append(
                    f'  <line class="overlay-element" '
                    f'data-element="{_svg_attr(element_overlay["name"])}" '
                    f'x1="{center[0]:.3f}" y1="{center[1]:.3f}" '
                    f'x2="{position[0]:.3f}" y2="{position[1]:.3f}" '
                    f'stroke="{STRIPBOARD_OVERLAY_ELEMENT_STROKE}" '
                    f'stroke-width="{STRIPBOARD_OVERLAY_STROKE_WIDTH:.3f}"/>'
                )
        lines.append(
            f'  <text class="overlay-element-label" '
            f'x="{center[0]:.3f}" y="{center[1] - 0.18:.3f}" '
            f'font-size="{STRIPBOARD_OVERLAY_ELEMENT_LABEL_SIZE:.3f}" '
            f'font-weight="700" text-anchor="middle" '
            f'fill="{STRIPBOARD_OVERLAY_TEXT_FILL}" '
            f'stroke="{STRIPBOARD_OVERLAY_TEXT_HALO}" stroke-width="0.075" '
            f'paint-order="stroke">'
            f'{_svg_text(element_overlay["label"])}</text>'
        )

    for terminal in _stripboard_overlay_terminals(schema, assignment):
        x, y = terminal["position"]
        lines.append(
            f'  <circle class="overlay-terminal" '
            f'data-net="{_svg_attr(terminal["net_name"])}" '
            f'data-element="{_svg_attr(terminal["element_name"])}" '
            f'data-terminal="{_svg_attr(terminal["terminal_name"])}" '
            f'cx="{x:.3f}" cy="{y:.3f}" '
            f'r="{STRIPBOARD_OVERLAY_TERMINAL_RADIUS:.3f}" '
            f'fill="{STRIPBOARD_OVERLAY_TERMINAL_FILL}"/>'
        )

    for marker in _stripboard_overlay_node_markers(schema, assignment):
        x, y = marker["position"]
        lines.append(
            f'  <circle class="overlay-node" '
            f'data-net="{_svg_attr(marker["net_name"])}" '
            f'data-node="{_svg_attr(marker["node_name"])}" '
            f'cx="{x:.3f}" cy="{y:.3f}" '
            f'r="{STRIPBOARD_OVERLAY_NODE_RADIUS:.3f}" '
            f'fill="{STRIPBOARD_OVERLAY_NODE_FILL}"/>'
        )
        if marker["label"]:
            lines.append(
                f'  <text class="overlay-node-label" '
                f'x="{x + 0.18:.3f}" y="{y - 0.16:.3f}" '
                f'font-size="{STRIPBOARD_OVERLAY_NODE_LABEL_SIZE:.3f}" '
                f'font-weight="700" fill="{STRIPBOARD_OVERLAY_TEXT_FILL}" '
                f'stroke="{STRIPBOARD_OVERLAY_TEXT_HALO}" stroke-width="0.070" '
                f'paint-order="stroke">'
                f'{_svg_text(marker["label"])}</text>'
            )

    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _render_stripboard_overlay_png(stripboard, assignment, schema, path, scale):
    scale = _validate_render_scale(scale)
    try:
        from PIL import Image, ImageDraw
    except ImportError as error:
        raise RuntimeError(
            "Pillow is required to render stripboard overlay PNG files."
        ) from error

    width, height = _stripboard_size(stripboard)
    label_margin = STRIPBOARD_OVERLAY_NET_LABEL_MARGIN
    image_width = max(1, int(round((width + label_margin) * scale)))
    image_height = max(1, int(round(height * scale)))
    image = Image.new("RGB", (image_width, image_height), "white")
    draw = ImageDraw.Draw(image)
    board_image = Image.new(
        "RGB",
        (
            max(1, int(round(width * scale))),
            image_height,
        ),
        "white",
    )
    _draw_stripboard_base_png(ImageDraw.Draw(board_image), stripboard, scale)
    image.paste(board_image, (int(round(label_margin * scale)), 0))

    element_font = _overlay_png_font(scale, STRIPBOARD_OVERLAY_ELEMENT_LABEL_SIZE)
    node_font = _overlay_png_font(scale, STRIPBOARD_OVERLAY_NODE_LABEL_SIZE)
    net_font = _overlay_png_font(scale, STRIPBOARD_OVERLAY_NET_LABEL_SIZE)

    for row in range(stripboard.height_pitches):
        net_name = _stripboard_row_net_name(assignment, row)
        if not net_name:
            continue
        draw.text(
            _px_point(
                (
                    label_margin - 0.2 - len(net_name) * 0.18,
                    STRIPBOARD_BOARD_MARGIN + row - 0.22,
                ),
                scale,
            ),
            net_name,
            fill=STRIPBOARD_OVERLAY_TEXT_FILL,
            font=net_font,
        )

    element_width = _px_overlay_stroke(scale)
    for element_overlay in _stripboard_overlay_elements(schema, assignment):
        positions = element_overlay["positions"]
        center = element_overlay["center"]
        if len(positions) == 2:
            draw.line(
                [
                    _px_point(_offset_point(positions[0], label_margin, 0), scale),
                    _px_point(_offset_point(positions[1], label_margin, 0), scale),
                ],
                fill=STRIPBOARD_OVERLAY_ELEMENT_STROKE,
                width=element_width,
            )
        else:
            for position in positions:
                draw.line(
                    [
                        _px_point(_offset_point(center, label_margin, 0), scale),
                        _px_point(_offset_point(position, label_margin, 0), scale),
                    ],
                    fill=STRIPBOARD_OVERLAY_ELEMENT_STROKE,
                    width=element_width,
                )
        draw.text(
            _px_point(
                _offset_point((center[0] - 0.25, center[1] - 0.42), label_margin, 0),
                scale,
            ),
            element_overlay["label"],
            fill=STRIPBOARD_OVERLAY_TEXT_FILL,
            font=element_font,
        )

    for terminal in _stripboard_overlay_terminals(schema, assignment):
        _draw_px_circle(
            draw,
            _offset_point(terminal["position"], label_margin, 0),
            STRIPBOARD_OVERLAY_TERMINAL_RADIUS,
            scale,
            fill=STRIPBOARD_OVERLAY_TERMINAL_FILL,
        )

    for marker in _stripboard_overlay_node_markers(schema, assignment):
        _draw_px_circle(
            draw,
            _offset_point(marker["position"], label_margin, 0),
            STRIPBOARD_OVERLAY_NODE_RADIUS,
            scale,
            fill=STRIPBOARD_OVERLAY_NODE_FILL,
        )
        if marker["label"]:
            x, y = marker["position"]
            draw.text(
                _px_point((x + label_margin + 0.18, y - 0.35), scale),
                marker["label"],
                fill=STRIPBOARD_OVERLAY_TEXT_FILL,
                font=node_font,
            )

    image.save(path)


def _draw_stripboard_base_png(draw, stripboard, scale):
    width, height = _stripboard_size(stripboard)
    draw.rectangle(
        _px_rect(0, 0, width, height, scale),
        fill=STRIPBOARD_BOARD_FILL,
        outline=STRIPBOARD_BOARD_STROKE,
        width=_px_stroke(scale),
    )

    for row in range(stripboard.height_pitches):
        strip_rect = _stripboard_strip_rect(stripboard, row)
        draw.rectangle(
            _px_rect(*strip_rect, scale),
            fill=STRIPBOARD_STRIP_FILL,
            outline=STRIPBOARD_STRIP_STROKE,
            width=_px_stroke(scale),
        )

    radius = STRIPBOARD_HOLE_RADIUS
    for _, _, x, y in _stripboard_holes(stripboard):
        draw.ellipse(
            _px_rect(x - radius, y - radius, radius * 2, radius * 2, scale),
            fill=STRIPBOARD_HOLE_FILL,
            outline=STRIPBOARD_HOLE_STROKE,
            width=_px_stroke(scale),
        )


def _stripboard_size(stripboard):
    return float(stripboard.width_pitches), float(stripboard.height_pitches)


def _stripboard_strip_rect(stripboard, row):
    y = STRIPBOARD_BOARD_MARGIN + row - STRIPBOARD_STRIP_HEIGHT / 2.0
    x = STRIPBOARD_STRIP_INSET
    width = stripboard.width_pitches - 2 * STRIPBOARD_STRIP_INSET
    return x, y, width, STRIPBOARD_STRIP_HEIGHT


def _stripboard_holes(stripboard):
    for row in range(stripboard.height_pitches):
        for col in range(stripboard.width_pitches):
            yield (
                col,
                row,
                STRIPBOARD_BOARD_MARGIN + col,
                STRIPBOARD_BOARD_MARGIN + row,
            )


def _stripboard_overlay_node_markers(schema, assignment):
    node_views_by_name = _node_views_by_name(schema.node_views)
    node_points = _schema_node_points(schema, node_views_by_name)
    markers = []
    for node_view in schema.node_views:
        if node_view.net.name not in assignment.net_rows:
            continue
        point = node_points.get(node_view.name, (node_view.position,))[0]
        markers.append(
            {
                "node_name": node_view.name,
                "net_name": node_view.net.name,
                "label": node_view.label,
                "position": _snap_schema_point_to_stripboard(
                    point,
                    node_view.net.name,
                    assignment,
                    assignment.column_pitch,
                ),
            }
        )
    return markers


def _stripboard_overlay_terminals(schema, assignment):
    terminals = []
    for element in schema.elements:
        for terminal_name, net_name in element.terminal_nets.items():
            if net_name not in assignment.net_rows:
                continue
            terminals.append(
                {
                    "element_name": element.name,
                    "terminal_name": terminal_name,
                    "net_name": net_name,
                    "position": _snap_schema_point_to_stripboard(
                        element.anchor_position(terminal_name),
                        net_name,
                        assignment,
                        assignment.column_pitch,
                    ),
                }
            )
    return terminals


def _stripboard_overlay_elements(schema, assignment):
    overlays = []
    for element in schema.elements:
        positions = []
        for terminal_name, net_name in element.terminal_nets.items():
            if net_name not in assignment.net_rows:
                continue
            positions.append(
                _snap_schema_point_to_stripboard(
                    element.anchor_position(terminal_name),
                    net_name,
                    assignment,
                    assignment.column_pitch,
                )
            )
        if not positions:
            continue
        label = element.name if element.value is None else f"{element.name} {element.value}"
        overlays.append(
            {
                "name": element.name,
                "label": label,
                "positions": positions,
                "center": _average_points(positions),
            }
        )
    return overlays


def _snap_schema_point_to_stripboard(point, net_name, assignment, column_pitch):
    column = _snap_schema_x_to_column(point[0], assignment, column_pitch)
    row = assignment.net_rows[net_name]
    return (STRIPBOARD_BOARD_MARGIN + column, STRIPBOARD_BOARD_MARGIN + row)


def _snap_schema_x_to_column(x, assignment, column_pitch):
    column = int(round(x / column_pitch)) + assignment.x_offset
    return int(_clamp(column, 0, assignment.stripboard.width_pitches - 1))


def _stripboard_row_net_name(assignment, row):
    for net_name, net_row in assignment.net_rows.items():
        if net_row == row:
            return net_name
    return ""


def _svg_attr(value):
    return html.escape(str(value), quote=True)


def _svg_text(value):
    return html.escape(str(value), quote=False)


def _px_rect(x, y, width, height, scale):
    return (
        int(round(x * scale)),
        int(round(y * scale)),
        int(round((x + width) * scale)),
        int(round((y + height) * scale)),
    )


def _px_point(point, scale):
    return (int(round(point[0] * scale)), int(round(point[1] * scale)))


def _px_stroke(scale):
    return max(1, int(round(STRIPBOARD_STROKE_WIDTH * scale)))


def _px_overlay_stroke(scale):
    return max(1, int(round(STRIPBOARD_OVERLAY_STROKE_WIDTH * scale)))


def _draw_px_circle(draw, center, radius, scale, fill):
    draw.ellipse(
        _px_rect(
            center[0] - radius,
            center[1] - radius,
            radius * 2,
            radius * 2,
            scale,
        ),
        fill=fill,
    )


def _overlay_png_font(scale, size_units):
    try:
        from PIL import ImageFont
    except ImportError:
        return None

    size_px = max(10, int(round(size_units * scale)))
    for font_name in (
        "DejaVuSans-Bold.ttf",
        "Arial Bold.ttf",
        "Arial.ttf",
    ):
        try:
            return ImageFont.truetype(font_name, size_px)
        except OSError:
            pass
    return ImageFont.load_default()


def _validate_positive_integer(value, name):
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be a positive integer.")
    if value <= 0:
        raise ValueError(f"{name} must be positive.")


def _validate_nonnegative_integer(value, name):
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be a non-negative integer.")
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")


def _validate_render_scale(scale):
    if not isinstance(scale, (int, float)) or isinstance(scale, bool):
        raise TypeError("scale must be a positive number.")
    if scale <= 0:
        raise ValueError("scale must be positive.")
    return float(scale)


def _create_wire_from_element_args(name, nodes, terminal_nodes):
    if nodes and terminal_nodes:
        raise TypeError("Use either positional nodes or named wire endpoints.")
    if nodes:
        if len(nodes) != 2:
            raise TypeError("Wire expects two positional endpoint views.")
        return create_wire(nodes[0], nodes[1], name=name)
    provided = set(terminal_nodes)
    if provided != {"start", "end"}:
        raise TypeError("Wire expects start and end endpoint views.")
    return create_wire(terminal_nodes["start"], terminal_nodes["end"], name=name)


def _coerce_net(net, default_name):
    if net is None:
        return create_net(default_name)
    if isinstance(net, Net):
        return net
    if isinstance(net, str):
        return create_net(net)
    raise TypeError("net must be a Net, a net name string, or None.")


def _alignment_delta(part, to, alignment, axes=None, stack_gap=0):
    if axes is not None and alignment is not Alignment.CENTER:
        raise ValueError("Axis-restricted alignment is only supported for CENTER.")

    use_padded_boxes = _uses_padded_alignment_boxes(alignment)
    moving_box = _get_bounding_box(part, padded=use_padded_boxes)
    target_box = _get_bounding_box(to, padded=use_padded_boxes)
    moving_center = _box_center(moving_box)
    target_center = _box_center(target_box)
    moving_width = moving_box[1][0] - moving_box[0][0]
    moving_height = moving_box[1][1] - moving_box[0][1]

    if alignment is Alignment.CENTER:
        dx = target_center[0] - moving_center[0]
        dy = target_center[1] - moving_center[1]
    elif alignment is Alignment.LEFT:
        dx, dy = target_box[0][0] - moving_box[0][0], 0.0
    elif alignment is Alignment.RIGHT:
        dx, dy = target_box[1][0] - moving_box[1][0], 0.0
    elif alignment is Alignment.TOP:
        dx, dy = 0.0, target_box[1][1] - moving_box[1][1]
    elif alignment is Alignment.BOTTOM:
        dx, dy = 0.0, target_box[0][1] - moving_box[0][1]
    elif alignment is Alignment.TOP_CENTER:
        dx, dy = 0.0, target_center[1] - moving_box[1][1]
    elif alignment is Alignment.BOTTOM_CENTER:
        dx, dy = 0.0, target_center[1] - moving_box[0][1]
    elif alignment is Alignment.LEFT_CENTER:
        dx, dy = target_center[0] - moving_box[0][0], 0.0
    elif alignment is Alignment.RIGHT_CENTER:
        dx, dy = target_center[0] - moving_box[1][0], 0.0
    elif alignment is Alignment.STACK_LEFT:
        dx, dy = target_box[0][0] - moving_box[0][0] - moving_width - stack_gap, 0.0
    elif alignment is Alignment.STACK_RIGHT:
        dx, dy = target_box[1][0] - moving_box[1][0] + moving_width + stack_gap, 0.0
    elif alignment is Alignment.STACK_TOP:
        dx, dy = 0.0, target_box[1][1] - moving_box[1][1] + moving_height + stack_gap
    elif alignment is Alignment.STACK_BOTTOM:
        dx, dy = 0.0, target_box[0][1] - moving_box[0][1] - moving_height - stack_gap
    else:
        raise ValueError(f"Unknown alignment: {alignment}")

    if axes is None:
        return dx, dy
    return (dx if "x" in axes else 0.0, dy if "y" in axes else 0.0)


def _uses_padded_alignment_boxes(alignment):
    return alignment in {
        Alignment.STACK_LEFT,
        Alignment.STACK_RIGHT,
        Alignment.STACK_TOP,
        Alignment.STACK_BOTTOM,
    }


def _translate_in_place(obj, vector):
    if isinstance(obj, NodeView):
        obj.position = _add_points(obj.position, vector)
        obj.placement_explicit = True
    elif isinstance(obj, Element):
        obj.position = _add_points(obj.position, vector)
    elif isinstance(obj, Schema):
        obj.node_views = [translate(*vector)(node) for node in obj.node_views]
        obj.elements = [translate(*vector)(element) for element in obj.elements]
    else:
        raise TypeError(f"Cannot translate {type(obj).__name__}")


def _rotate_in_place(obj, angle, center):
    if isinstance(obj, NodeView):
        if center is not None:
            obj.position = _rotate_around(obj.position, angle, _point(center))
            obj.placement_explicit = True
    elif isinstance(obj, Element):
        if center is not None:
            obj.position = _rotate_around(obj.position, angle, _point(center))
        obj.angle += angle
    elif isinstance(obj, Schema):
        obj.node_views = [rotate(angle, center=center)(node) for node in obj.node_views]
        obj.elements = [
            rotate(angle, center=center)(element) for element in obj.elements
        ]
    else:
        raise TypeError(f"Cannot rotate {type(obj).__name__}")


def _schema_node_points(schema, node_views_by_name):
    terminal_points_by_node = {}
    used_node_names = set()

    for wire in schema.wires:
        for view_name in (wire.start_view, wire.end_view):
            used_node_names.add(view_name)
            node_view = node_views_by_name[view_name]
            terminal_points_by_node.setdefault(view_name, []).append(node_view.position)

    for element in schema.elements:
        for anchor_name, view_name in element.terminal_views.items():
            used_node_names.add(view_name)
            terminal_points_by_node.setdefault(view_name, []).append(
                element.anchor_position(anchor_name)
            )

    return {
        name: (
            _resolved_node_position(node_view, terminal_points_by_node[name]),
            node_view,
            len(terminal_points_by_node[name]),
        )
        for name, node_view in node_views_by_name.items()
        if name in used_node_names
    }


def _resolved_node_position(node_view, terminal_points):
    if _is_rail(node_view):
        return node_view.position
    if node_view.placement_explicit:
        return node_view.position
    if len(terminal_points) > 2:
        return _median_point(terminal_points)
    return _average_points(terminal_points)


def _should_render_node(node_view, terminal_count):
    if _is_rail(node_view):
        return bool(node_view.label) or node_view.node_type is Ground
    if node_view.node_type is Ground:
        return True
    if node_view.label:
        return True
    return terminal_count > 2


def _validate_schema_items(node_views, elements, wires):
    for node_view in node_views:
        if not isinstance(node_view, NodeView):
            raise TypeError(
                "Schema node_views must be NodeView objects, "
                f"got {type(node_view).__name__}."
            )
    node_views_by_name = _node_views_by_name(node_views)
    nets_by_name = _nets_by_name(node_views)

    for element in elements:
        if not isinstance(element, Element):
            raise TypeError(
                f"Schema elements must be Element objects, got {type(element).__name__}."
            )
        for terminal, view_name in element.terminal_views.items():
            node_view = _require_view(node_views_by_name, view_name, element.name)
            expected_net = element.terminal_nets[terminal]
            if node_view.net.name != expected_net:
                raise ValueError(
                    f"Element {element.name!r} terminal {terminal!r} refers to "
                    f"view {view_name!r} as net {expected_net!r}, but the schema "
                    f"view is on net {node_view.net.name!r}."
                )

    for wire in wires:
        if not isinstance(wire, WireSegment):
            raise TypeError(
                f"Schema wires must be WireSegment objects, got {type(wire).__name__}."
            )
        start = _require_view(node_views_by_name, wire.start_view, wire.name or "wire")
        end = _require_view(node_views_by_name, wire.end_view, wire.name or "wire")
        if start.net.name != end.net.name:
            raise ValueError(
                f"Wire {wire.name!r} endpoints are on different nets: "
                f"{start.net.name!r} and {end.net.name!r}."
            )
        if wire.net_name != start.net.name:
            raise ValueError(
                f"Wire {wire.name!r} was created for net {wire.net_name!r}, "
                f"but its schema endpoints are on {start.net.name!r}."
            )

    return list(nets_by_name.values())


def _require_view(node_views_by_name, view_name, owner_name):
    try:
        return node_views_by_name[view_name]
    except KeyError as error:
        raise ValueError(
            f"{owner_name!r} refers to node view {view_name!r}, "
            "but that view is missing from the schema."
        ) from error


def _node_views_by_name(node_views):
    node_views_by_name = {}
    for node_view in node_views:
        if node_view.name in node_views_by_name:
            raise ValueError(f"Duplicate node view name: {node_view.name!r}")
        node_views_by_name[node_view.name] = node_view
    return node_views_by_name


def _nets_by_name(node_views):
    nets_by_name = {}
    for node_view in node_views:
        nets_by_name.setdefault(node_view.net.name, node_view.net)
    return nets_by_name


def _schemdraw_element(element):
    spec = _element_spec(element)
    placed = spec.schemdraw_factory()
    if spec.positional_terminals == ("start", "end"):
        return placed.endpoints(element.start.point(), element.end.point())
    return placed.theta(element.angle).anchor("center").at(element.position)


def _is_rail(node_view):
    return node_view.rail_direction is not None


def _wire_endpoints(wire, node_points, node_views_by_name):
    start_view = node_views_by_name[wire.start_view]
    end_view = node_views_by_name[wire.end_view]
    start_point = _node_connection_point(
        start_view,
        node_points[start_view.name][0],
        node_points[end_view.name][0],
    )
    end_point = _node_connection_point(
        end_view,
        node_points[end_view.name][0],
        start_point,
    )
    return start_point, end_point


def _record_wire_rail_taps(wire, node_views_by_name, rail_taps, start, end):
    start_view = node_views_by_name[wire.start_view]
    end_view = node_views_by_name[wire.end_view]
    if _is_rail(start_view):
        rail_taps[start_view.name].append(start)
    if _is_rail(end_view):
        rail_taps[end_view.name].append(end)


def _node_connection_point(node_view, resolved_point, terminal_point):
    if not _is_rail(node_view):
        return resolved_point
    return _project_point_to_rail(node_view, terminal_point)


def _project_point_to_rail(node_view, point):
    start, end = _rail_endpoints(node_view)
    if node_view.rail_direction is Direction.VERTICAL:
        return (
            start[0],
            _clamp(point[1], min(start[1], end[1]), max(start[1], end[1])),
        )
    return (_clamp(point[0], min(start[0], end[0]), max(start[0], end[0])), start[1])


def _rail_endpoints(node_view):
    x, y = node_view.position
    length = float(node_view.rail_length)
    anchor = node_view.rail_anchor

    if node_view.rail_direction is Direction.HORIZONTAL:
        if anchor is Alignment.LEFT:
            return (x, y), (x + length, y)
        if anchor is Alignment.RIGHT:
            return (x - length, y), (x, y)
        return (x - length / 2.0, y), (x + length / 2.0, y)

    if anchor is Alignment.TOP:
        return (x, y), (x, y - length)
    if anchor is Alignment.BOTTOM:
        return (x, y + length), (x, y)
    return (x, y + length / 2.0), (x, y - length / 2.0)


def _add_wire(drawing, start, end, direct=False):
    if _same_point(start, end):
        return
    if direct:
        drawing.add(elm.Line().endpoints(start, end))
        return
    corner = (start[0], end[1])
    if _same_point(start, corner) or _same_point(corner, end):
        drawing.add(elm.Line().endpoints(start, end))
        return
    drawing.add(elm.Line().endpoints(start, corner))
    drawing.add(elm.Line().endpoints(corner, end))


def _prefers_direct_terminal_wire(element):
    return not _is_axis_aligned(element.angle)


def _is_axis_aligned(angle):
    return min(abs(angle % 90.0), abs(90.0 - (angle % 90.0))) < EPS


def _validate_terminal_views(element_type, terminal_nodes):
    spec = _spec_for_type(element_type)
    provided = set(terminal_nodes)
    expected = set(spec.terminals)
    missing = expected - provided
    unexpected = provided - expected
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing {sorted(missing)}")
        if unexpected:
            details.append(f"unexpected {sorted(unexpected)}")
        raise TypeError(f"{element_type.name} terminal mismatch: {', '.join(details)}")
    for terminal, node_view in terminal_nodes.items():
        if not isinstance(node_view, NodeView):
            raise TypeError(f"Terminal {terminal!r} must connect to a NodeView.")
    return {terminal: terminal_nodes[terminal] for terminal in spec.terminals}


def _get_bounding_box(obj, padded=True):
    if isinstance(obj, (Anchor, ReferencePoint)):
        return obj.get_bounding_box()
    if isinstance(obj, Element):
        if padded:
            return obj.get_bounding_box()
        return _element_visual_bounding_box(obj)
    if isinstance(obj, Schema) and not padded:
        return _schema_visual_bounding_box(obj)
    if isinstance(obj, (NodeView, Schema)):
        return obj.get_bounding_box()
    if obj is None:
        return [[0.0, 0.0], [0.0, 0.0]]
    raise TypeError(f"Cannot get bounding box of {type(obj).__name__}")


def _element_label_position(element):
    box = _element_visual_bounding_box(element)
    center = _box_center(box)
    width = box[1][0] - box[0][0]
    height = box[1][1] - box[0][1]
    loc = element.label_loc
    if loc == "auto":
        loc = "top" if width > height else "right"

    gap = LABEL_GAP
    if loc == "left":
        return (box[0][0] - gap, center[1])
    if loc == "right":
        return (box[1][0] + gap, center[1])
    if loc == "top":
        return (center[0], box[1][1] + gap)
    if loc == "bottom":
        return (center[0], box[0][1] - gap)
    raise ValueError(f"Unknown label_loc: {element.label_loc!r}")


def _label_loc_from_alignment(alignment):
    mapping = {
        Alignment.LEFT: "left",
        Alignment.RIGHT: "right",
        Alignment.TOP: "top",
        Alignment.BOTTOM: "bottom",
    }
    try:
        return mapping[alignment]
    except KeyError as error:
        raise ValueError(
            "Label alignment must be LEFT, RIGHT, TOP, or BOTTOM."
        ) from error


def _element_visual_bounding_box(element):
    corners = _box_corners(_element_spec(element).local_bbox)
    points = [
        _add_points(element.position, _rotate_point(corner, element.angle))
        for corner in corners
    ]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [[min(xs), min(ys)], [max(xs), max(ys)]]


def _schema_visual_bounding_box(schema):
    node_views_by_name = _node_views_by_name(schema.node_views)
    boxes = [
        *[_element_visual_bounding_box(element) for element in schema.elements],
        *[node.get_bounding_box() for node in schema.node_views],
        *[_wire_bounding_box(wire, node_views_by_name) for wire in schema.wires],
    ]
    if not boxes:
        return [[0.0, 0.0], [0.0, 0.0]]
    return [
        [min(box[0][0] for box in boxes), min(box[0][1] for box in boxes)],
        [max(box[1][0] for box in boxes), max(box[1][1] for box in boxes)],
    ]


def _wire_bounding_box(wire, node_views_by_name):
    start = node_views_by_name[wire.start_view].get_bounding_box()
    end = node_views_by_name[wire.end_view].get_bounding_box()
    return [
        [min(start[0][0], end[0][0]), min(start[0][1], end[0][1])],
        [max(start[1][0], end[1][0]), max(start[1][1], end[1][1])],
    ]


def _element_spec(element):
    return _spec_for_type(element.element_type)


def _spec_for_type(element_type):
    try:
        return ELEMENT_SPECS[element_type]
    except KeyError as error:
        raise ValueError(f"Unsupported element type: {element_type}") from error


def _box_corners(box):
    return [
        (box[0][0], box[0][1]),
        (box[0][0], box[1][1]),
        (box[1][0], box[0][1]),
        (box[1][0], box[1][1]),
    ]


def _padded_box(box, padding):
    return [
        [box[0][0] - padding, box[0][1] - padding],
        [box[1][0] + padding, box[1][1] + padding],
    ]


def _box_center(box):
    return ((box[0][0] + box[1][0]) / 2.0, (box[0][1] + box[1][1]) / 2.0)


def _aligned_point(obj, alignment):
    box = _get_bounding_box(obj, padded=False)
    center = _box_center(box)
    if alignment is Alignment.CENTER:
        return center
    if alignment in (Alignment.LEFT, Alignment.LEFT_CENTER):
        return (box[0][0], center[1])
    if alignment in (Alignment.RIGHT, Alignment.RIGHT_CENTER):
        return (box[1][0], center[1])
    if alignment in (Alignment.TOP, Alignment.TOP_CENTER):
        return (center[0], box[1][1])
    if alignment in (Alignment.BOTTOM, Alignment.BOTTOM_CENTER):
        return (center[0], box[0][1])
    raise ValueError(f"Unsupported point alignment: {alignment}")


def _point(value):
    return (float(value[0]), float(value[1]))


def _add_points(a, b):
    return (float(a[0]) + float(b[0]), float(a[1]) + float(b[1]))


def _offset_point(point, dx, dy):
    return (float(point[0]) + float(dx), float(point[1]) + float(dy))


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _unique_points(points):
    unique = []
    for point in points:
        if not any(_same_point(point, existing) for existing in unique):
            unique.append(point)
    return unique


def _strip_trailing_whitespace(path):
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(line.rstrip() for line in lines) + "\n", encoding="utf-8")


def _rotate_point(point, angle):
    radians = math.radians(angle)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return (
        point[0] * cosine - point[1] * sine,
        point[0] * sine + point[1] * cosine,
    )


def _rotate_around(point, angle, center):
    shifted = (point[0] - center[0], point[1] - center[1])
    rotated = _rotate_point(shifted, angle)
    return _add_points(center, rotated)


def _average_points(points):
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def _median_point(points):
    return (
        _median(point[0] for point in points),
        _median(point[1] for point in points),
    )


def _median(values):
    sorted_values = sorted(values)
    middle = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return sorted_values[middle]
    return (sorted_values[middle - 1] + sorted_values[middle]) / 2.0


def _same_point(a, b):
    return abs(a[0] - b[0]) < EPS and abs(a[1] - b[1]) < EPS
