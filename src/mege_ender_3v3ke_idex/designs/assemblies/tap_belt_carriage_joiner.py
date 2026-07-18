"""Join the lower belt-carriage remainder into a fixed Tap frame."""

from shellforgepy.simple import *


def join_tap_with_belt_carriage(*, idex_tap, belt_carriage):
    """Return a Tap whose leader contains belt geometry outside the Tap box."""

    joined_tap = idex_tap.copy()
    tap_bbox = materialize_bounding_box(joined_tap.leader, y_enlargement=5)
    belt_carriage_remainder = belt_carriage.leader.copy().cut(tap_bbox)
    joined_belt_carriage = belt_carriage.copy()
    joined_belt_carriage.leader = belt_carriage_remainder

    for obsolete_thread_inset_name in (
        "left_bridge_thread_inset_thread_inset",
        "right_clamp_thread_inset_thread_inset",
    ):
        obsolete_index = joined_belt_carriage.non_production_indices_by_name.pop(
            obsolete_thread_inset_name,
            None,
        )
        if obsolete_index is None:
            continue
        joined_belt_carriage.non_production_parts.pop(obsolete_index)
        joined_belt_carriage.non_production_indices_by_name = {
            name: index - 1 if index > obsolete_index else index
            for name, index in (
                joined_belt_carriage.non_production_indices_by_name.items()
            )
        }

    joined_tap = joined_tap.fuse(belt_carriage_remainder)
    joined_tap = joined_tap.merge_except_leader(
        joined_belt_carriage.prefixed_copy("belt_carriage")
    )
    joined_tap.add_consumed_part_ref(belt_carriage.part_ref_for_leader())

    return {
        "idex_tap": joined_tap,
        "belt_carriage": joined_belt_carriage,
    }
