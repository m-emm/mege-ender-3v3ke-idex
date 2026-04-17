"""Declarative extruders scene assembly."""

from shellforgepy.simple import *


def create_extruders_assembly(**_kwargs):
    """Return an empty leader; visualization is composed from dependency assemblies."""

    return LeaderFollowersCuttersPart(leader=create_box(0.1, 0.1, 0.1))
