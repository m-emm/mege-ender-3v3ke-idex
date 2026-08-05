# Klipper Host Extras

This directory contains the active custom Klipper host code installed on
`menderpi`.

- `klippy/extras/heaters.py` is the unmodified upstream file from Klipper commit
  `ca8230d505b7ba7fd225bfa6ed9655bc4520e805`. It is retained so deployment can
  remove the retired boosted-bed patch from an existing printer installation.
- `klipper_config/update_menderpi.sh` restores this upstream file to
  `/opt/klipper/klippy/extras/heaters.py` after checking the remote Klipper
  commit and the current remote file hash.
- The Raspberry Pi image build installs the same file after cloning Klipper.

The active single-SSR bed config remains in
`klipper_config/printer.cfg.template`; this directory owns only Klipper host
behavior, not printer wiring or calibration.
