"""Deprecated runner forwarding to `python -m mege_circuits.pinout`."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
