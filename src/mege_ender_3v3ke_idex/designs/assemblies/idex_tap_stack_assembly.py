"""Focused inspection scene for a shared Tap toolhead stack."""

from shellforgepy.simple import *


def create_idex_tap_stack_assembly(**_kwargs):
    """Return a tiny placeholder; visualization is sourced from injections."""

    return LeaderFollowersCuttersPart(leader=create_box(0.1, 0.1, 0.1))
