# RP2040 Klipper Firmware

This directory builds Klipper firmware for RP2040-based boards such as Pico,
Pico W, and LDO Nitehawk toolhead boards.

## Operating Policy: Reuse Known-Working Firmware

Firmware building and flashing are exceptional maintenance operations, not
routine Klipper deployment or ordinary printer troubleshooting. Once a board
has known-working firmware, reuse it and its existing firmware artifact.

- Do not automatically build, rebuild, update, or flash MCU firmware.
- A host restart, temporary Klipper startup failure, changed serial
  enumeration, or Katapult-mode appearance does not by itself justify a build
  or flash.
- Diagnose power, USB/serial enumeration, bootloader/application state,
  services, and available known-working artifacts first.
- Build or flash only when the user explicitly requests firmware work, or when
  a verified incompatibility/corruption leaves no suitable known-working
  artifact and the user approves the recovery.

Klipper firmware builds are Docker-only. Do not install or use a native macOS
RP2040/Klipper compiler toolchain here. Native host scripts are kept only for
USB detection and flashing already-built firmware.

Katapult bootloader builds and Katapult BOOTSEL flashing live in
`../katapult_rp2040`. This directory builds Klipper and can flash a Klipper
application directly via BOOTSEL or through an already-installed Katapult
bootloader.

## Prerequisites

- Docker Desktop or Colima for builds
- Python 3 for the optional Katapult flashing helper venv
- A connected RP2040 board when flashing

The local Python venv created by `flash_klipper_via_katapult.sh` installs only
`pyserial` and is a flashing helper, not a build environment.

## Build Klipper

Builds run in Docker and write ignored output under `klipper/out/`.

```bash
cd klipper_setup/rp2040_firmware
./build_rp2040_docker.sh -k
```

Build modes:

- `-k` uses `rp2040_config` and builds `klipper/out/klipper.bin` for boards
  with Katapult at the 16KiB offset.
- `-c rp2040_config_eddy` builds the BTT Eddy USB/Duo Katapult application
  with the W25Q080 `CLKDIV=4` startup setting required by BTT.
- `-d` uses `rp2040_config_direct` and builds `klipper/out/klipper.uf2` for
  direct BOOTSEL flashing without Katapult.
- `-c <config>` uses an explicit config file from this directory.
- `-i` opens an interactive Docker shell for inspection/debugging.

Builds are incremental by default. Existing ignored firmware output should be
reused when it matches the requested `KLIPPER_REF` and config. If the output
does not match, rebuild incrementally in Docker. Use `CLEAN=1` only for rare
clean rebuilds:

```bash
CLEAN=1 ./build_rp2040_docker.sh -k
```

Pin the Klipper source to the host/printer commit when updating an MCU:

```bash
KLIPPER_REF=<host-klipper-commit> ./build_rp2040_docker.sh -k
```

## Nitehawk Klipper Firmware

LDO Nitehawk boards ship with Katapult, so the Klipper application must start
at the 16KiB offset. Use the dedicated config:

```bash
KLIPPER_REF=<host-klipper-commit> ./build_rp2040_docker.sh -c rp2040_config_nitehawk
```

`rp2040_config_nitehawk` sets:

- `CONFIG_FLASH_APPLICATION_ADDRESS=0x10004000`
- `CONFIG_RPXXXX_FLASH_START_4000=y`
- `CONFIG_INITIAL_PINS="!gpio8"`

The output is `klipper/out/klipper.bin`.

## Flash Klipper Directly (BOOTSEL)

Use this only for a no-Katapult/direct firmware image:

```bash
./build_rp2040_docker.sh -d
./flash_rp2040.sh
```

`flash_rp2040.sh` copies `klipper/out/klipper.uf2` to the RP2040 BOOTSEL mass
storage drive. It supports common macOS and Linux mount points:

- `/Volumes/RPI-RP2`
- `/media/$USER/RPI-RP2`
- `/media/RPI-RP2`

## Flash Klipper Via Katapult

Put the board into Katapult bootloader mode first, then flash the built
Klipper binary:

```bash
./flash_klipper_via_katapult.sh -d /dev/cu.usbmodem1201
```

Use `/dev/cu.usbmodem*` on macOS or `/dev/serial/by-id/...` on Linux. You can
override the firmware path if needed:

```bash
./flash_klipper_via_katapult.sh -d /dev/cu.usbmodem1201 -f klipper/out/klipper.bin
```

The script clones Katapult into an ignored local `katapult/` working directory
only so it can run `scripts/flashtool.py`; it does not build Katapult.

## Build Or Flash Katapult

Katapult bootloader work is separate:

```bash
cd ../katapult_rp2040
./build.sh
./flash.sh
```

Use `../katapult_rp2040` for:

- Building `katapult.uf2` and `katapult.withclear.uf2`
- Flashing Katapult to a bare RP2040 in BOOTSEL mode
- Katapult bootloader debugging/menuconfig

Do not use this directory for Katapult builds.

## Detect Board State

```bash
./detect_rp2040.sh
```

This reports BOOTSEL, Katapult, and Klipper USB devices. It is informational;
choose the build and flash commands explicitly after detection.

## Generated Files

The following paths are generated and ignored:

- `klipper/`
- `katapult/`
- `katapult_venv/`
- `saved_firmware/`
- local `*.bin` and `*.uf2` firmware artifacts

Firmware binaries should not be checked into this repository.

## References

- Klipper: https://github.com/Klipper3d/klipper
- Katapult: https://github.com/Arksine/katapult
- RP2040 datasheet: https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf
