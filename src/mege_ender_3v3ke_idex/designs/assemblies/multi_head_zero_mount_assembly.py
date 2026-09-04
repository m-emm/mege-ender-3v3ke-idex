"""Mount for the multi-head-zero reference on the print-bed undercarriage."""

from shellforgepy.simple import *


def create_multi_head_zero_mount_assembly(
    *,
    print_bed,
    print_bed_undercarriage,
    multi_head_zero,
):
    """Create the initial bridge behind the multi-head-zero body."""

    _ = print_bed
    _ = print_bed_undercarriage

    multi_head_zero_body_reference = multi_head_zero.get_named_non_production_part(
        "body_reference"
    )

    mount = create_box(25, 40, 25)
    mount = align(mount, multi_head_zero_body_reference, Alignment.CENTER)
    mount = align(mount, multi_head_zero_body_reference, Alignment.TOP)
    mount = align(mount, multi_head_zero_body_reference, Alignment.STACK_BACK)

    return LeaderFollowersCuttersPart(mount)
