# RP2040 Firmware (Klipper + optional Katapult)

This directory contains scripts to build and flash Klipper firmware for RP2040-based boards.

Two supported workflows:

1) Direct (no Katapult): build `klipper.uf2` and flash in BOOTSEL mass-storage mode.
2) Katapult bootloader: build+flash Katapult once, then build `klipper.bin` with a bootloader offset and flash via Katapult.

## Prerequisites

- Python 3
- Build tools: `sudo apt-get install git python3 python3-pip gcc-arm-none-eabi binutils-arm-none-eabi libncurses-dev`
- For flashing: The board should be connected in bootloader mode (hold BOOTSEL while connecting USB)

## Usage

### Variant A: Direct flash (no Katapult)

```bash
./build_rp2040_docker.sh -d
```

This will:
1. Clone/update the Klipper repository
2. Configure for RP2040 (no bootloader offset)
3. Build the firmware
4. Output: `klipper/out/klipper.uf2`

Flash:

```bash
./flash_rp2040.sh
```

### Variant B: Katapult bootloader + flash via Katapult

#### Step 1 (one-time): Build Katapult

```bash
./build_katapult_docker.sh
```

Output: `katapult/out/katapult.uf2`

#### Step 2 (one-time): Flash Katapult

Put the board into RP2040 system boot mode (RPI-RP2 drive) and run:

```bash
./flash_katapult.sh
```

#### Step 3: Build Klipper for Katapult

```bash
./build_rp2040_docker.sh -k
```

Output: `klipper/out/klipper.bin`

#### Step 4: Flash Klipper via Katapult

Put the board into Katapult bootloader mode (often a rapid double-reset) and run:

```bash
./flash_klipper_via_katapult.sh -d <device>
```

### Custom Configuration

This repo keeps two Klipper config variants:

- `rp2040_config_direct`: no bootloader offset (produces `klipper.uf2`)
- `rp2040_config`: bootloader offset for Katapult (produces `klipper.bin`)

You can also pass a specific config via:

```bash
./build_rp2040_docker.sh -c rp2040_config_direct
```

## Files

- `build_rp2040_docker.sh` - Build Klipper (Docker; supports direct + Katapult configs)
- `build_katapult_docker.sh` - Build Katapult bootloader (Docker)
- `build_katapult_script_for_in_docker.sh` - In-container Katapult build script
- `flash_rp2040.sh` - Flash Klipper UF2 (direct / BOOTSEL)
- `flash_katapult.sh` - Flash Katapult UF2 (BOOTSEL)
- `flash_klipper_via_katapult.sh` - Flash Klipper BIN via Katapult
- `rp2040_config` - Klipper config for Katapult (bootloader offset)
- `rp2040_config_direct` - Klipper config for direct UF2 flashing
- `klipper/` - Cloned Klipper repository (gitignored)

## References

- https://github.com/Arksine/katapult
