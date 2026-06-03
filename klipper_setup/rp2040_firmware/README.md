# RP2040 Firmware (Klipper + optional Katapult)

This directory contains scripts to build and flash Klipper firmware for RP2040-based boards (Raspberry Pi Pico, Pico W, etc.).

Two supported workflows:

1) **Direct (no Katapult)**: build `klipper.uf2` and flash in BOOTSEL mass-storage mode. Simple but requires physical access (BOOTSEL button) for updates.
2) **Katapult bootloader**: build+flash Katapult once, then flash Klipper remotely via USB without needing BOOTSEL mode. Recommended for boards that are hard to access.

## Prerequisites

- Python 3
- Build tools: `sudo apt-get install git python3 python3-pip gcc-arm-none-eabi binutils-arm-none-eabi libncurses-dev`
- For flashing: The board should be connected in bootloader mode (hold BOOTSEL while connecting USB)

## Quick Start

### Option A: Direct Flash (Simple, requires BOOTSEL button for updates)

1. Put board in BOOTSEL mode (hold BOOTSEL button while connecting USB)
2. Build Klipper: `./build_rp2040_docker.sh -d`
3. Flash: `./flash_rp2040.sh`

### Option B: Katapult Bootloader (Recommended, enables remote updates)

**Initial setup (one-time):**

1. Navigate to Katapult directory: `cd ../katapult_rp2040`
2. Build Katapult: `./build.sh`
3. Put board in BOOTSEL mode (hold BOOTSEL button while connecting USB)
4. Flash Katapult: `./flash.sh`
5. Verify Katapult is running: `ls /dev/cu.usbmodem*` (should show a device)

**Flash Klipper via Katapult:**

6. Return to this directory: `cd ../rp2040_firmware`
7. Build Klipper for Katapult: `./build_rp2040_docker.sh -k`
8. Flash via Katapult: `./flash_klipper_via_katapult.sh -d /dev/cu.usbmodem1201`

**Future updates:** Just repeat steps 7-8 (no need to touch BOOTSEL button!)

---

### Check what's on your board

```bash
./detect_rp2040.sh
```

This will identify if your RP2040 is in BOOTSEL mode, running Klipper, or running Katapult.

## Detailed Workflow

### Variant A: Direct flash (no Katapult)

Build Klipper UF2:

```bash
./build_rp2040_docker.sh -d
```

This will:
1. Clone/update the Klipper repository
2. Configure for RP2040 (no bootloader offset)
3. Build the firmware
4. Output: `klipper/out/klipper.uf2`

Flash (requires BOOTSEL mode):

```bash
./flash_rp2040.sh
```

### Variant B: Katapult bootloader workflow

#### Step 1 (one-time): Build and flash Katapult

```bash
cd ../katapult_rp2040
./build.sh        # Builds Katapult bootloader
./flash.sh        # Flashes to board (must be in BOOTSEL mode)
cd ../rp2040_firmware
```

After flashing, the board will reboot as a Katapult USB device (e.g., `/dev/cu.usbmodem1201`).

**Verification:** Run `ls /dev/cu.usbmodem*` - you should see a USB device. Check with `system_profiler SPUSBDataType | grep katapult` to confirm.

#### Step 2: Build Klipper for Katapult

```bash
./build_rp2040_docker.sh -k
```

This builds `klipper/out/klipper.bin` with the correct bootloader offset (0x10004000).

For the LDO Nitehawk-36 toolhead board, use the dedicated config:

```bash
SKIP_CLEAN=1 KLIPPER_REF=<host-klipper-commit> ./build_rp2040_docker.sh -c rp2040_config_nitehawk
```

`rp2040_config_nitehawk` keeps the Katapult-safe 16KiB offset and sets the
active-low activity LED startup pin (`!gpio8`). `SKIP_CLEAN=1` preserves any
existing build products and performs an incremental rebuild.

#### Step 3: Flash Klipper via Katapult

```bash
./flash_klipper_via_katapult.sh -d /dev/cu.usbmodem1201
```

Replace `/dev/cu.usbmodem1201` with your actual device path.

**Note:** For future updates, just repeat steps 2-3. No need to reflash Katapult or use BOOTSEL mode!

## Troubleshooting

**Katapult not appearing after flash:**
- Verify the board is a genuine Raspberry Pi Pico/Pico W
- Try the other stage2 bootloader in menuconfig if issues persist
- Check USB cable supports data (not charge-only)

**Can't find device after Katapult flash:**
- Run `ls /dev/cu.usbmodem*` or check USB device info: `system_profiler SPUSBDataType | grep -i katapult`
- Device should show manufacturer as "katapult"

**Katapult crashes (returns to BOOTSEL):**
- This was an issue with old builds. Use the `katapult_rp2040` directory which has the working configuration.

## Notes

- The Katapult build uses `CONFIG_RPXXXX_FLASH_START_0100=y` which auto-sets `FLASH_APPLICATION_ADDRESS=0x10000100`
- Klipper application starts at `LAUNCH_APP_ADDRESS=0x10004000` (16KB offset)
- The `katapult.withclear.uf2` file includes a cleared page at 0x10004000 so Katapult stays in bootloader mode when no Klipper is present

## References

- Klipper: https://github.com/Klipper3d/klipper
- Katapult: https://github.com/Arksine/katapult
- RP2040 datasheet: https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf
