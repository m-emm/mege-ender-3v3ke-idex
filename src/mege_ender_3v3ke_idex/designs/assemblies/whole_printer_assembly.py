"""Declarative whole-printer scene assembly."""

from shellforgepy.simple import *


def create_whole_printer_assembly(**_kwargs):
    """Return an empty leader; visualization is composed from dependency assemblies."""

    return LeaderFollowersCuttersPart(leader=create_box(0.1, 0.1, 0.1))