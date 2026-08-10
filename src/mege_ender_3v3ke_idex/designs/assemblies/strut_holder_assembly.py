"""Simple strut holder assembly."""

from shellforgepy.simple import *


def create_strut_holder_assembly():
    """Create the initial 40 x 80 x 5 mm strut holder blank."""

    return LeaderFollowersCuttersPart(leader=create_box(40, 80, 5))
