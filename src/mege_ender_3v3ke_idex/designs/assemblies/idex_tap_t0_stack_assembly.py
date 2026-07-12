"""Focused inspection scene for the T0 Tap fixed frame, rail, and shuttle."""

from shellforgepy.simple import *


def create_idex_tap_t0_stack_assembly(**_kwargs):
    """Return a tiny placeholder; visualization is sourced from dependencies."""

    return LeaderFollowersCuttersPart(leader=create_box(0.1, 0.1, 0.1))
