"""Declarative standalone x-axis carriage assembly."""

from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12h_carriage
from shellforgepy.simple import *


def create_x_axis_carriage_assembly(**_kwargs):
    """Create one standalone MGN12H carriage assembly."""

    carriage = create_mgn12h_carriage()

    if carriage.cutters:
        carriage.add_named_cutter(carriage.cutters[0], "mount_holes")

    screw_hole_pitch = carriage.additional_data["screw_hole_pitch"]

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            mount_screw = create_complete_screw_assembly(
                "M3",
                length=5,
                with_access_hole=True,
                extra_access_hole_length=5,
                access_hole_clearance=0.8,
            )

            mount_screw = align(
                mount_screw,
                carriage,
                Alignment.CENTER,
            )
            mount_screw = align(mount_screw, carriage, Alignment.TOP)

            mount_screw = translate(
                lr.sign * screw_hole_pitch / 2, fb.sign * screw_hole_pitch / 2, 5
            )(mount_screw)
            mount_screw = mount_screw.prefixed_copy(
                f"mount_screw_{lr.name.lower()}_{fb.name.lower()}"
            )

            carriage = carriage.merge_except_leader(mount_screw)

    return carriage
