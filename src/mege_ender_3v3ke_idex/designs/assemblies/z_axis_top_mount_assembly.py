"""Declarative single-side z-axis top-mount assembly."""

from mege_ender_3v3ke_idex.designs.z_axis import create_top_mount


def create_z_axis_top_mount_assembly(
    *,
    z_axis_profile,
    guide_rod,
    threaded_rod,
    context=None,
):
    """Create the top rod clamp and profile mount for one z-axis side."""

    del context

    return create_top_mount(
        guide_rod,
        threaded_rod,
        z_axis_profile,
    )
