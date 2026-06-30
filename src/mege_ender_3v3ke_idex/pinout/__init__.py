"""Compatibility facade for pinout helpers now provided by mege-circuits."""

from warnings import warn

warn(
    "mege_ender_3v3ke_idex.pinout is deprecated; use mege_circuits.pinout instead.",
    DeprecationWarning,
    stacklevel=2,
)

from mege_circuits.pinout import (  # noqa: E402
    DEFAULT_COLOR_MAP,
    PinoutProject,
    analyze_all_connections,
    analyze_connection_violations,
    calculate_projection_score,
    find_optimal_waypoint,
    generate_routed_svg,
    load_pinout_config,
    point_to_line_distance,
    route_problematic_connections,
    write_svg,
)

__all__ = [
    "DEFAULT_COLOR_MAP",
    "PinoutProject",
    "analyze_all_connections",
    "analyze_connection_violations",
    "calculate_projection_score",
    "find_optimal_waypoint",
    "generate_routed_svg",
    "load_pinout_config",
    "point_to_line_distance",
    "route_problematic_connections",
    "write_svg",
]
