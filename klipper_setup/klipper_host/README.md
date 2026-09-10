# Klipper Host Extras

This directory is the sole source for the custom Klipper host overlay installed
on `menderpi` and in the Raspberry Pi image.

The deployment order is explicit: the pinned upstream Klipper checkout is
created first, then this directory is recursively overlaid onto `/opt/klipper`.
Files in this directory take precedence over the upstream checkout; unmanaged
upstream files are preserved.

The shared upstream revision is recorded once in `../KLIPPER_COMMIT` and is
used by both the image build and `klipper_config/update_menderpi.sh`.

- `klippy/extras/heaters.py` is the unmodified upstream file from Klipper commit
  `ca8230d505b7ba7fd225bfa6ed9655bc4520e805`. It is retained so deployment can
  remove the retired boosted-bed patch from an existing printer installation.
- `klipper_config/update_menderpi.sh` and the image build apply this complete
  directory recursively after checking the pinned Klipper commit.

The active single-SSR bed config remains in
`klipper_config/printer.cfg.template`; this directory owns only Klipper host
behavior, not printer wiring or calibration.
