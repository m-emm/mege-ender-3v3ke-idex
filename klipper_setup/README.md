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
3) Optional Wi-Fi: create `/Users/mege/.config/klipperpi-idex/wifi.env` or
   `klipper_setup/image_build/secrets/wifi.env`:
```bash
WIFI_SSIDS=("office-ssid" "basement-ssid")
WIFI_PASSWORD="your-password"
```
The image disables onboard Wi-Fi and leaves these profiles unbound, so the USB
Wi-Fi dongle is discovered as `wlan0`.
4) Adjust `build.env` values (hostname, locale, pins, etc.).

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
- If Wi-Fi was configured, `nmcli -t -f DEVICE,STATE,CONNECTION dev` shows
  `wlan0` connected to a `klipperpi-wifi-*` profile.
- `lsusb -t` shows USB-A devices on the Raspberry Pi 4
  `Driver=xhci_hcd` buses.
- `systemctl status klipper moonraker nginx lightdm` all green.
- PiTFT43 shows KlipperScreen UI.
- Mainsail reachable at `http://<hostname>.local/`.

## Files you may want to customize
- `overlays/stage2/99-klipperpi/files/printer.cfg` — replace with your real printer config.
- `overlays/stage2/99-klipperpi/files/moonraker.conf` — extend to match your setup.
- `overlays/stage2/99-klipperpi/files/pitft43.conf` — adjust rotation if you mount the screen differently.
- `../klipper_host/klippy/extras/heaters.py` — custom Klipper host patch
  installed into `/opt/klipper`; the tracked upstream `heaters.py` baseline
  removes the retired boosted-heatbed extension during deployment.

## Raspberry Pi 4 USB and Wi-Fi note
The Raspberry Pi 4 USB-A ports use the VL805 xHCI controller. Do not add the
Raspberry Pi 3 `dtoverlay=dwc2,dr_mode=host` workaround or the obsolete
`max_usb_current=1` setting. The image keeps onboard Wi-Fi disabled so the
external USB Wi-Fi dongle is the only wireless interface, and it masks
ModemManager so it cannot probe MCU serial ports.

### Required cold-boot USB topology

Keep the two UVC cameras on different hubs. Cold boot repeatedly failed when
both cameras were connected directly to the Raspberry Pi, regardless of the
industrial hub arrangement. The following split topology cold-booted
successfully and was verified live on 2026-07-29:

| Linux USB path | Required connection |
| --- | --- |
| `1-1.1` | Vimicro `0458:6006` nozzle camera, connected directly to the Pi |
| `1-1.2` | Empty |
| `1-1.3` | Ralink RT5370 `148f:5370` Wi-Fi dongle, connected directly to the Pi |
| `1-1.4` | Industrial seven-port hub `1a40:0201`, connected directly to the Pi |
| `1-1.4.2` | Aukey `1bcf:0215` printer camera, connected to industrial-hub port 2 |

Do not move the Aukey camera back to a direct Pi port without repeating a full
cold-boot test. The direct Pi path numbers above are the Linux topology reported
by `lsusb -t`; label the physical sockets/cables to preserve the working
mapping.

The remaining industrial-hub ports retain the printer MCU wiring:

| Industrial-hub port | Device |
| --- | --- |
| 1 | `x_pico`, RP2040 `E66368254F174333` |
| 2 | Aukey printer camera |
| 3 | `y_pico`, RP2040 `DE62A87557907227` |
| 4 | `eddy`, RP2040 `504434040889101C` |
| 5 | `right_nitehawk`, RP2040 `3232323236198418` behind its internal hub |
| 6 | `left_nitehawk`, RP2040 `30333938340637C1` behind its internal hub |
| 7 | Main `mcu`, RP2040 `E6633861A3673038` |

After a cold boot, verify the topology with `lsusb -t`, check that all six
`/dev/serial/by-id/usb-Klipper_rp2040_*` links exist, and confirm that
`menderpi-wlan-ready.service` is active. The WLAN-ready guard delays Klipper,
Moonraker, and the camera framebuffer services until `wlan0` has a global IPv4
address; it does not make an arbitrary camera topology cold-boot safe.

The first boot also enables `klipperpi-expand-rootfs.service`, a one-shot
service that grows the root partition/filesystem before Klipper starts. Without
that, Klipper may run out of space while compiling its host C helper module on a
freshly flashed card.

## Notes
- Secrets and machine-specific files live in `klipper_setup/image_build/secrets/` (git-ignored).
- pi-gen submodule, work dirs, and deploy outputs are ignored via `.gitignore`.

## RP2040 Firmware (Klipper / Katapult)

This repo also includes Dockerized RP2040 firmware builders and native flashing
helpers:

- Firmware work is exceptional maintenance, not routine printer configuration
  or business workflow. Reuse known-working MCU firmware and existing firmware
  artifacts; do not rebuild or reflash merely because Klipper restarted, is
  temporarily unavailable, or an MCU enumerates as Katapult.
- Do not automatically build or flash firmware. Diagnose power, USB/serial
  enumeration, bootloader/application state, and services first. Build or flash
  only when explicitly requested, or after a verified firmware problem and
  user approval.
- Klipper firmware builds are Docker-only; do not use a native macOS compiler
  toolchain for RP2040 firmware.
- Direct (no Katapult): build `klipper.uf2` in Docker and flash via BOOTSEL.
- With Katapult: build/flash the Katapult bootloader in
  `katapult_rp2040`, then build `klipper.bin` with a bootloader offset and
  flash the Klipper application via Katapult.

See: `klipper_setup/rp2040_firmware/README.md`
