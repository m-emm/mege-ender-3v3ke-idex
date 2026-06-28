"""Minimal alignment-first schematic DSL.

This module intentionally keeps the public surface small: typed node/element
tokens, pure placement helpers, schema creation from elements, and SVG
rendering through Schemdraw.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto

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


class NodeType(Enum):
    DOT = auto()
    GROUND = auto()


class ElementType(Enum):
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
class Node:
    node_type: NodeType
    name: str
    label: str | None = None
    kind: str | None = None
    label_loc: str = "right"
    position: tuple[float, float] = (0.0, 0.0)
    placement_explicit: bool = False

    def get_bounding_box(self):
        return [
            [self.position[0], self.position[1]],
            [self.position[0], self.position[1]],
        ]


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
class Element:
    element_type: ElementType
    name: str
    value: str | None
    terminal_nodes: dict[str, Node]
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
class Schema:
    nodes: list[Node]
    elements: list[Element]

    def get_bounding_box(self):
        boxes = [
            *[element.get_bounding_box() for element in self.elements],
            *[node.get_bounding_box() for node in self.nodes],
        ]
        if not boxes:
            return [[0.0, 0.0], [0.0, 0.0]]
        return [
            [min(box[0][0] for box in boxes), min(box[0][1] for box in boxes)],
            [max(box[1][0] for box in boxes), max(box[1][1] for box in boxes)],
        ]


def create_node(node_type, name, label=None, kind=None, **kwargs):
    if node_type not in (Dot, Ground):
        raise ValueError("Only Dot and Ground nodes are supported in this DSL.")
    if kwargs:
        raise TypeError(f"Unsupported node arguments: {sorted(kwargs)}")
    return Node(
        node_type=node_type,
        name=name,
        label=label,
        kind=kind,
    )


def create_element(
    element_type, name, value=None, *nodes, label_loc="auto", **terminal_nodes
):
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

    terminal_nodes = _validate_terminal_nodes(element_type, terminal_nodes)
    return Element(
        element_type=element_type,
        name=name,
        value=value,
        terminal_nodes=terminal_nodes,
        label_loc=label_loc,
    )


def create_schema(nodes, elements):
    schema_nodes = list(nodes)
    schema_elements = list(elements)
    _validate_schema_items(schema_nodes, schema_elements)
    return Schema(nodes=schema_nodes, elements=schema_elements)


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


def align_translation(part, to, alignment, axes=None, stack_gap=0):
    dx, dy = _alignment_delta(part, to, alignment, axes=axes, stack_gap=stack_gap)
    return translate(dx, dy)


def align(part, to, alignment, axes=None, stack_gap=0):
    target = part.owner if isinstance(part, Anchor) else part
    return align_translation(part, to, alignment, axes=axes, stack_gap=stack_gap)(
        target
    )


def modify_label_alignment(element, alignment):
    modified = copy.deepcopy(element)
    modified.label_loc = _label_loc_from_alignment(alignment)
    return modified


def render_schemdraw(schema, file, show=False):
    node_points = _schema_node_points(schema)

    with schemdraw.Drawing(file=file, show=show) as drawing:
        drawing.config(unit=2.0, inches_per_unit=0.55, fontsize=10)

        for element in schema.elements:
            for anchor_name, node in element.terminal_nodes.items():
                terminal = element.anchor_position(anchor_name)
                node_point = node_points[node.name][0]
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
            drawing.add(elm.Label(label).at(_element_label_position(element)))

        for node_name in sorted(node_points):
            point, node, terminal_count = node_points[node_name]
            if not _should_render_node(node, terminal_count):
                continue
            if node.node_type is Ground:
                ground = elm.Ground().at(point)
                if node.label:
                    ground = ground.label(node.label, loc=node.label_loc)
                drawing.add(ground)
            else:
                dot = elm.Dot().at(point)
                if node.label:
                    dot = dot.label(node.label, loc=node.label_loc)
                drawing.add(dot)


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
    if isinstance(obj, Node):
        obj.position = _add_points(obj.position, vector)
        obj.placement_explicit = True
    elif isinstance(obj, Element):
        obj.position = _add_points(obj.position, vector)
    elif isinstance(obj, Schema):
        obj.nodes = [translate(*vector)(node) for node in obj.nodes]
        obj.elements = [translate(*vector)(element) for element in obj.elements]
    else:
        raise TypeError(f"Cannot translate {type(obj).__name__}")


def _rotate_in_place(obj, angle, center):
    if isinstance(obj, Node):
        if center is not None:
            obj.position = _rotate_around(obj.position, angle, _point(center))
            obj.placement_explicit = True
    elif isinstance(obj, Element):
        if center is not None:
            obj.position = _rotate_around(obj.position, angle, _point(center))
        obj.angle += angle
    elif isinstance(obj, Schema):
        obj.nodes = [rotate(angle, center=center)(node) for node in obj.nodes]
        obj.elements = [
            rotate(angle, center=center)(element) for element in obj.elements
        ]
    else:
        raise TypeError(f"Cannot rotate {type(obj).__name__}")


def _schema_node_points(schema):
    nodes_by_name = _nodes_by_name(schema.nodes)
    terminal_points_by_node = {}
    used_node_names = set()
    for element in schema.elements:
        for anchor_name, node in element.terminal_nodes.items():
            if node.name not in nodes_by_name:
                raise ValueError(
                    f"Element {element.name!r} refers to node {node.name!r}, "
                    "but that node is missing from the schema node list."
                )
            used_node_names.add(node.name)
            terminal_points_by_node.setdefault(node.name, []).append(
                element.anchor_position(anchor_name)
            )

    return {
        name: (
            _resolved_node_position(node, terminal_points_by_node[name]),
            node,
            len(terminal_points_by_node[name]),
        )
        for name, node in nodes_by_name.items()
        if name in used_node_names
    }


def _resolved_node_position(node, terminal_points):
    if node.placement_explicit:
        return node.position
    if len(terminal_points) > 2:
        return _median_point(terminal_points)
    return _average_points(terminal_points)


def _should_render_node(node, terminal_count):
    if node.node_type is Ground:
        return True
    if node.label:
        return True
    return terminal_count > 2


def _validate_schema_items(nodes, elements):
    for node in nodes:
        if not isinstance(node, Node):
            raise TypeError(
                f"Schema nodes must be Node objects, got {type(node).__name__}."
            )
    for element in elements:
        if not isinstance(element, Element):
            raise TypeError(
                f"Schema elements must be Element objects, got {type(element).__name__}."
            )
    _nodes_by_name(nodes)


def _nodes_by_name(nodes):
    nodes_by_name = {}
    for node in nodes:
        if node.name in nodes_by_name:
            raise ValueError(f"Duplicate schema node name: {node.name!r}")
        nodes_by_name[node.name] = node
    return nodes_by_name


def _schemdraw_element(element):
    spec = _element_spec(element)
    placed = spec.schemdraw_factory()
    if spec.positional_terminals == ("start", "end"):
        return placed.endpoints(element.start.point(), element.end.point())
    return placed.theta(element.angle).anchor("center").at(element.position)


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


def _validate_terminal_nodes(element_type, terminal_nodes):
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
    for terminal, node in terminal_nodes.items():
        if not isinstance(node, Node):
            raise TypeError(f"Terminal {terminal!r} must be connected to a Node.")
    return {terminal: terminal_nodes[terminal] for terminal in spec.terminals}


def _get_bounding_box(obj, padded=True):
    if isinstance(obj, Anchor):
        return obj.get_bounding_box()
    if isinstance(obj, Element):
        if padded:
            return obj.get_bounding_box()
        return _element_visual_bounding_box(obj)
    if isinstance(obj, Schema) and not padded:
        return _schema_visual_bounding_box(obj)
    if isinstance(obj, (Node, Schema)):
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
    boxes = [
        *[_element_visual_bounding_box(element) for element in schema.elements],
        *[node.get_bounding_box() for node in schema.nodes],
    ]
    if not boxes:
        return [[0.0, 0.0], [0.0, 0.0]]
    return [
        [min(box[0][0] for box in boxes), min(box[0][1] for box in boxes)],
        [max(box[1][0] for box in boxes), max(box[1][1] for box in boxes)],
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


def _point(value):
    return (float(value[0]), float(value[1]))


def _add_points(a, b):
    return (float(a[0]) + float(b[0]), float(a[1]) + float(b[1]))


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
