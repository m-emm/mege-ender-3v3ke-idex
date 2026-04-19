"""Declarative tool head assembly composed from assembly dependencies."""


def create_tool_head_assembly(
    *,
    sprite_extruder,
    nitehawk_holder,
    part_fans,
):
    """Create the tool head assembly from built subassemblies."""

    return nitehawk_holder.merge_except_leader(part_fans)
