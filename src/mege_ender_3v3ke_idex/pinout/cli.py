"""Compatibility CLI for the pinout renderer now provided by mege-circuits."""

from __future__ import annotations

from typing import Sequence
from warnings import warn

from mege_circuits.pinout.cli import build_parser as build_parser  # noqa: F401
from mege_circuits.pinout.cli import main as _mege_circuits_pinout_main


def main(argv: Sequence[str] | None = None) -> int:
    warn(
        "mege_ender_3v3ke_idex.pinout is deprecated; use "
        "mege_circuits.pinout or mege-circuits-pinout instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _mege_circuits_pinout_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
