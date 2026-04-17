"""Declarative inspection assembly for the x-axis reference stack."""

from shellforgepy.simple import *


def create_x_axis_profiles_rails_carriages_assembly(**_kwargs):
    """Return an empty leader; visualization is composed from dependency assemblies."""

    return LeaderFollowersCuttersPart(leader=create_box(0.1, 0.1, 0.1))
