# Klipper Host Patch

This directory contains the active custom Klipper host code installed on
`menderpi`.

- `klippy/extras/heaters.py` is based on Klipper commit
  `ca8230d505b7ba7fd225bfa6ed9655bc4520e805`.
- The active change is optional boosted-bed output support for `[heater_bed]`.
- `klipper_config/update_menderpi.sh` installs this file to
  `/opt/klipper/klippy/extras/heaters.py` after checking the remote Klipper
  commit and the current remote file hash.
- The Raspberry Pi image build installs the same file after cloning Klipper.

The boosted bed config remains in `klipper_config/printer.cfg.template`; this
directory owns only Klipper host behavior, not printer wiring or calibration.
