# Klipper Pi Image Build (pi-gen)

This folder builds a reproducible Raspberry Pi OS (64‑bit Bookworm) image with Klipper, Moonraker, Mainsail, KlipperScreen, and BTT PiTFT43 support.

## Prereqs (macOS)
- Docker Desktop (or Colima)
- Homebrew packages: `git jq coreutils gnu-sed`
- `diskutil` (macOS default) for flashing helper

## One-time setup
```bash
cd klipper_setup/image_build
./scripts/setup_pigen_submodule.sh
```

## Configure
1) Copy the template and edit:
```bash
cp klipper_setup/image_build/build.env.example klipper_setup/image_build/secrets/build.env
```
2) Put your SSH public key in `klipper_setup/image_build/secrets/authorized_keys` (one or more lines).
3) Adjust `build.env` values (hostname, locale, pins, etc.).

## Build
```bash
cd klipper_setup/image_build
./scripts/build_image.sh
```
Artifacts land in `klipper_setup/image_build/out/` with a timestamped image and a per-image manifest file.
`klipper_setup/image_build/out/manifest.txt` is a symlink pointing at the newest manifest.
The build also updates a symlink `klipper_setup/image_build/out/latest` pointing at the newest artifact.

## Flash (macOS)
1) Find the target disk:
```bash
./scripts/list_targets.sh
```
2) Flash (replace `/dev/diskN` and image path):
```bash
./scripts/flash_sd.sh out/<image>.img.xz /dev/diskN
```

Tip: you can omit the image path and it will pick the newest artifact from `out/`:
```bash
./scripts/flash_sd.sh /dev/diskN
```

Or explicitly use the symlink:
```bash
./scripts/flash_sd.sh out/latest /dev/diskN
```

## After boot (Milestone checks)
- `ssh <USER>@<HOSTNAME>.local` works with your key.
- `systemctl status klipper moonraker klipperscreen nginx` all green.
- PiTFT43 shows KlipperScreen UI.
- Mainsail reachable at `http://<hostname>.local/`.

## Files you may want to customize
- `overlays/stage2/99-klipperpi/files/printer.cfg` — replace with your real printer config.
- `overlays/stage2/99-klipperpi/files/moonraker.conf` — extend to match your setup.
- `overlays/stage2/99-klipperpi/files/pitft43.conf` — adjust rotation if you mount the screen differently.

## Notes
- Secrets and machine-specific files live in `klipper_setup/image_build/secrets/` (git-ignored).
- pi-gen submodule, work dirs, and deploy outputs are ignored via `.gitignore`.

## RP2040 Firmware (Klipper / Katapult)

This repo also includes Dockerized scripts to build and flash RP2040 firmware:

- Direct (no Katapult): build `klipper.uf2` and flash via BOOTSEL.
- With Katapult: build+flash Katapult once, then build `klipper.bin` with a bootloader offset and flash via Katapult.

See: `klipper_setup/rp2040_firmware/README.md`
