"""Reusable carriage stopper assembly."""

from shellforgepy.simple import *


def _normalize_alignments(alignments):
    normalized_alignments = []
    for alignment in alignments or [Alignment.BOTTOM]:
        if isinstance(alignment, str):
            normalized_alignments.append(getattr(Alignment, alignment.upper()))
            continue
        normalized_alignments.append(alignment)
    return normalized_alignments


def create_carriage_stopper_assembly(
    *,
    stopper_width,
    stopper_length,
    stopper_thickness,
    stopper_fillet_radius,
    mount_screw_size=None,
    mount_screw_length=None,
    no_fillets_at=None,
    BIG_THING=500,
):
    """Create a printable carriage stopper with optional centered mount hardware."""

    normalized_no_fillets_at = _normalize_alignments(no_fillets_at)

    stopper = create_filleted_box(
        stopper_width,
        stopper_length,
        stopper_thickness,
        stopper_fillet_radius,
        no_fillets_at=normalized_no_fillets_at,
    )

    retval = LeaderFollowersCuttersPart(stopper)

    if not mount_screw_size or not mount_screw_length:
        return retval

    mount_screw = create_cylinder_screw(mount_screw_size, mount_screw_length)
    mount_screw = align(mount_screw, stopper, Alignment.CENTER, axes=[0, 1])
    mount_screw = align(mount_screw, stopper, Alignment.TOP)
    mount_screw = translate(
        0,
        0,
        MScrew.from_size(mount_screw_size).cylinder_head_height,
    )(mount_screw)

    mount_screw_cutter = create_cylinder(
        MScrew.from_size(mount_screw_size).clearance_hole_loose / 2,
        max(BIG_THING, 3 * stopper_thickness),
    )
    mount_screw_cutter = align(
        mount_screw_cutter,
        mount_screw,
        Alignment.CENTER,
    )

    retval = LeaderFollowersCuttersPart(retval.leader.cut(mount_screw_cutter))
    retval.add_named_non_production_part(mount_screw, "mount_screw")
    retval.add_named_cutter(mount_screw_cutter, "mount_screw_cutter")
    return retval
