"""
Extruder

Usage:
    cd <project_root> && ./run.sh path/to/extruder.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/extruder.py
"""

import logging
import os
import tempfile
import zipfile
from pathlib import Path

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

# Optional slicer process overrides
PROCESS_DATA = {
    "filament": "FilamentPLAMegeMaster",
    "process_overrides": {
        "nozzle_diameter": "0.6",
        "layer_height": "0.2",
    },
}

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

EXTUDER_STEP_PATH = PROJECT_ROOT / "resources" / "creality_sprite.step.zip"


def create_extruder():
    """Create the extruder part."""

    with tempfile.TemporaryDirectory() as tempdir:

        with zipfile.ZipFile(EXTUDER_STEP_PATH, "r") as zip_ref:
            zip_ref.extractall(tempdir)

        step_file_path = Path(tempdir) / "creality_sprite.step"

        extruder_part = import_solid_from_step(step_file_path)
    return extruder_part


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    part = create_extruder()
    parts.add(part, "extruder", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("extruder created successfully!")


if __name__ == "__main__":
    main()
