# Klipper Raspberry Pi OS Image (pi-gen, reproducible)

Goal: reproducibly build a Raspberry Pi OS 64-bit Bookworm image that boots with:
- system Python + venv tooling ready
- SSH enabled, password logins disabled, your public key preinstalled
- Avahi/Bonjour advertising `<hostname>.local`
- Klipper + Moonraker + **Mainsail (required)** enabled via systemd
- **KlipperScreen** preinstalled and enabled for the local display
- Known-good `printer.cfg` / `moonraker.conf` preloaded
- BTT PiTFT43 DSI/DPI 800×480 capacitive touchscreen supported at first boot

Root path in this repo: `klipper_setup/` (already present).

---

## Host requirements (macOS, Apple Silicon)
- Docker Desktop (or Colima; Docker Desktop simplest for pi-gen)
- Homebrew
- Helpful brew packages: `git`, `coreutils`, `jq`, `gnu-sed`
- Install example: `brew install git jq coreutils gnu-sed`

Build happens inside pi-gen’s Docker flow; no extra VM needed.

---

## Directory map (inside `klipper_setup/`)
```
klipper_setup/
  image_build/
    pi-gen/                 # pi-gen submodule, arm64 branch, pinned commit
    overlays/
      stage2/
        99-klipperpi/
          00-packages
          00-run-chroot.sh
          files/
            authorized_keys
            sshd_hardening.conf
            avahi-daemon.conf
            hostname
            klipper.service
            moonraker.service
            nginx-mainsail.conf   # required (Mainsail)
            klipperscreen.service
            printer.cfg
            moonraker.conf
            Xwrapper.config       # allow X11 for KlipperScreen
            pitft43.conf          # display/touch config.txt fragment
    secrets/                # ignored by git
      authorized_keys       # source key file copied into overlay
      build.env             # build pins + host settings
    out/                    # build artifacts + manifest
    scripts/
      setup_pigen_submodule.sh
      render_overlay.sh
      build_image.sh
      list_targets.sh
      flash_sd.sh
```

Design rules:
- Everything that touches the image lives as plain files in git.
- Secrets or machine-specific bits stay under `image_build/secrets/`.
- pi-gen is pinned to a specific commit for reproducibility.

---

## Build parameters
`image_build/secrets/build.env` (no secrets required; can be tracked if you want):
```
IMG_NAME=klipperpi-idex
RELEASE=bookworm
TIMEZONE=Europe/Zurich
LOCALE=en_GB.UTF-8
HOSTNAME=klipperpi
USERNAME=pi
KLIPPER_COMMIT=<git-sha>
MOONRAKER_COMMIT=<git-sha>
MAINSAIL_VERSION=<semver-or-tag>
KLIPPERSCREEN_COMMIT=<git-sha>
```
Pins live here so rebuilds stay deterministic. Wi-Fi credentials intentionally excluded.

---

## pi-gen integration
- `scripts/setup_pigen_submodule.sh`: add submodule at `image_build/pi-gen`, checkout `arm64`, pin commit (record hash in manifest). Run once after clone or when updating pins.
- `scripts/render_overlay.sh`: copy overlay into pi-gen, render `pi-gen/config` from `build.env`, drop `authorized_keys` into overlay files.
- `scripts/build_image.sh`: calls render, then `cd pi-gen && ./build-docker.sh`; copies latest `.img.xz` to `image_build/out/<IMG_NAME>-<date>.img.xz` and writes `out/manifest.txt` (pi-gen commit, pins, build timestamp).
 - A quickstart is in `klipper_setup/README.md`; example config in `klipper_setup/image_build/build.env.example`.

---

## What to track vs keep local
- Track: scripts, overlay stage files, unit files, hardening configs, and pin files (or a tracked `pins.env`).
- Do not track: `image_build/secrets/*` (authorized_keys, future Wi‑Fi credentials).
- Policy: if you decide to commit public keys, keep the policy explicit in this doc to avoid surprises.

---

## Overlay contents
### 00-packages
Install base + UI tooling:
- python3, python3-venv, python3-pip, python3-dev
- git, curl, unzip, build-essential
- avahi-daemon
- network-manager (optional but helpful)
- nginx (Mainsail is required, served locally)
- X stack for KlipperScreen: xserver-xorg, xserver-xorg-input-libinput, xserver-xorg-input-evdev, xinit, x11-xserver-utils, xserver-xorg-legacy
- fonts: fonts-dejavu, fonts-noto, fonts-noto-cjk (UI legibility)

### 00-run-chroot.sh (runs inside target rootfs)
1) Set hostname, locale, timezone from `build.env`.
2) Enable SSH, apply `files/sshd_hardening.conf` (password auth off, no root login).
3) Install `files/authorized_keys` for `${USERNAME}` (default `pi`).
4) Enable Avahi so `<hostname>.local` resolves.
5) Create `/opt/klipper` and `/opt/moonraker` venvs; clone pinned commits; `pip install -r requirements.txt` in each.
6) Deploy Mainsail: fetch pinned release tarball, unpack to `/var/www/mainsail`, configure nginx from `files/nginx-mainsail.conf`, enable nginx.
7) Install KlipperScreen: clone pinned commit to `/opt/klipperscreen`, run installer with X11 backend; install `files/klipperscreen.service`; set `/etc/X11/Xwrapper.config` from overlay to allow service start on vt1.
8) Install systemd units from `files/*.service`; `systemctl enable ssh avahi-daemon klipper moonraker nginx klipperscreen`.
9) Place configs into `/home/${USERNAME}/printer_data/config/printer.cfg` and `moonraker.conf` (matching modern Moonraker layout).
10) Ensure permissions: `${USERNAME}:${USERNAME}` owns `/home/${USERNAME}/printer_data` tree.

We deliberately avoid helper installers (no KIAUH) to keep the build explicit and reproducible.

---

## Services and config locations
- Config: `/home/pi/printer_data/config/printer.cfg` and `moonraker.conf` (adjust user if changed).
- Units: `klipper.service`, `moonraker.service`, `nginx.service`, `klipperscreen.service`.
- Avahi: `files/avahi-daemon.conf`, enabled via systemd.
- SSH hardening: `files/sshd_hardening.conf` included from `sshd_config.d/`.
- Display: `files/pitft43.conf` appended to `/boot/config.txt` during image build.

---

## Script usage (happy path)
1) `./scripts/setup_pigen_submodule.sh`
2) Edit `image_build/secrets/build.env` and drop your public key into `image_build/secrets/authorized_keys`.
3) `./scripts/build_image.sh`
   - Outputs compressed image to `image_build/out/` and manifest with pin info.
4) `./scripts/list_targets.sh` (choose `/dev/diskN` that matches policy).
5) `./scripts/flash_sd.sh image_build/out/<IMG_NAME>-<date>.img.xz /dev/diskN`

---

## BTT PiTFT43 (DSI/DPI) support
- Add overlay fragment `files/pitft43.conf` that gets appended to `/boot/config.txt`:
  ```
  dtoverlay=vc4-kms-dpi-generic
  dtparam=rgb666-padhi,clock-frequency=32000000
  dtparam=hactive=800,hfp=16,hsync=1,hbp=46
  dtparam=vactive=480,vfp=7,vsync=3,vbp=23
  dtparam=backlight-gpio=19
  dtparam=rotate=0
  dtoverlay=gt911_btt_tft43_dip
  dtparam=rotate_0
  ```
- During build, fetch touch overlay:  
  `wget https://raw.githubusercontent.com/bigtreetech/TFT43-DIP/master/gt911_btt_tft43_dip.dtbo -O /boot/overlays/gt911_btt_tft43_dip.dtbo`
- X11 touch calibration: rely on libinput defaults; rotation follows `rotate_` dtparam. If rotation changes, adjust both `dtparam=rotate=<0|90|180|270>` and `dtparam=rotate_<same>` for touch.
- KlipperScreen uses X11 on vt1; no desktop required.

---

## Milestones / verification
- Milestone 1 (boot): reach console, `ssh pi@<hostname>.local` with key; `python3 -V` works; Avahi resolves.
- Milestone 2 (services): `systemctl status klipper moonraker klipperscreen` green; configs present under `printer_data/config`; KlipperScreen shows UI on PiTFT43.
- Milestone 3 (web): Mainsail served via nginx; Moonraker reachable over LAN.

---

## Wi-Fi (explicitly out of scope for now)
NetworkManager provisioning changed in Bookworm. Add a `connections/` overlay later if you want baked Wi-Fi; keep it separate to stay reproducible.

---

## Next actions
- Implement the scripts and overlay files listed above following the pinned commit workflow.
- Run the first Milestone 1 build, boot, and verify SSH/Avahi.
- Then pin Klipper/Moonraker versions, add Mainsail (if wanted), and wire in config generation from the CAD stack.
