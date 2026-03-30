"""Shared helpers for declarative z-axis assemblies."""

from shellforgepy.simple import Alignment


def coerce_side_alignment(side):
    """Convert a public side parameter into the matching left/right alignment."""

    if isinstance(side, Alignment):
        alignment = side
    else:
        try:
            alignment = Alignment[str(side).strip().upper()]
        except KeyError as exc:
            raise ValueError(f"Unsupported z-axis side '{side}'") from exc

    if alignment not in {Alignment.LEFT, Alignment.RIGHT}:
        raise ValueError(f"Unsupported z-axis side '{side}'")

    return alignment
