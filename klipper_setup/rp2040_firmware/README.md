# RP2040 Klipper Firmware Build and Flash

This directory contains scripts to build and flash Klipper firmware for RP2040-based boards (Raspberry Pi Pico).

## Prerequisites

- Python 3
- Build tools: `sudo apt-get install git python3 python3-pip gcc-arm-none-eabi binutils-arm-none-eabi libncurses-dev`
- For flashing: The board should be connected in bootloader mode (hold BOOTSEL while connecting USB)

## Usage

### Build Firmware

```bash
./build_rp2040.sh
```

This will:
1. Clone/update the Klipper repository
2. Configure for RP2040
3. Build the firmware
4. Output: `klipper/out/klipper.uf2`

### Flash Firmware

With the Pico in bootloader mode (hold BOOTSEL button, connect USB):

```bash
./flash_rp2040.sh
```

Or manually copy the file:
```bash
cp klipper/out/klipper.uf2 /media/$USER/RPI-RP2/
```

### Custom Configuration

Edit `rp2040_config` to customize the build configuration before running the build script.

## Files

- `build_rp2040.sh` - Build script
- `flash_rp2040.sh` - Flash script
- `rp2040_config` - Klipper configuration for RP2040
- `klipper/` - Cloned Klipper repository (gitignored)
