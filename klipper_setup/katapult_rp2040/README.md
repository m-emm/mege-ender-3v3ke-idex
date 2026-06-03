# Katapult RP2040 Bootloader Builder

Clean, focused environment for building and debugging the Katapult bootloader
for Raspberry Pi Pico/Pico W.

Katapult is separate from normal Klipper firmware builds. Use this directory
only for Katapult bootloader build/flash/debug work. Klipper application
firmware lives in `../rp2040_firmware`.

## Quick Start

```bash
# Build Katapult
./build.sh

# Flash to Pico (hold BOOTSEL button, plug in USB)
./flash.sh
```

## Files

- `build.sh` - Build Katapult in Docker
- `flash.sh` - Flash Katapult to RP2040 via BOOTSEL
- `debug.sh` - Interactive Docker shell for debugging
- `katapult_config` - Katapult configuration (menuconfig format)
- `Dockerfile` - Docker build environment
- `build_in_docker.sh` - Build script (runs inside container)

The generated `katapult/` checkout and `katapult/out/` firmware outputs are
ignored. The build script clones Katapult into that working directory on demand.

## Configuration

The `katapult_config` file contains Katapult settings:
- Starts at `0x10000100` (after stage2 bootloader)
- Application (Klipper) will be at `0x10004000`
- USB communication
- Double-reset button support
- W25Q080 flash chip (standard for Pico/Pico W)

To modify configuration:
```bash
./debug.sh
# Inside container:
cd katapult && make menuconfig KCONFIG_CONFIG=/work/katapult_config
```

## Debugging

If Katapult crashes on boot:
1. Check `katapult/out/autoconf.h` for actual compiled values
2. Verify stage2 bootloader matches your flash chip
3. Test with `./debug.sh` and inspect build output

## Expected Behavior

After flashing Katapult successfully:
- Device reboots and appears as USB device: `ls /dev/cu.usbmodem*` shows a device
- Check with: `system_profiler SPUSBDataType | grep -i katapult` → should show "Manufacturer: katapult"
- Katapult waits in bootloader mode for firmware upload via `flashtool.py` (no application installed yet)
- LED may blink or stay solid (board-specific)

## Next Steps - Flash Klipper

After Katapult is running:

1. Navigate to Klipper firmware directory:
   ```bash
   cd ../rp2040_firmware
   ```

2. Build Klipper with bootloader offset:
   ```bash
   ./build_rp2040_docker.sh -k
   ```

3. Flash Klipper via Katapult:
   ```bash
   ./flash_klipper_via_katapult.sh -d /dev/cu.usbmodem1201
   ```
   (Replace `/dev/cu.usbmodem1201` with your actual device path)

4. For future Klipper updates, just repeat steps 2-3 (no BOOTSEL button needed!)

## Troubleshooting

**Device returns to BOOTSEL immediately:**
- This indicates Katapult is crashing on startup
- The current configuration is tested and working on Pico W
- If you have issues, verify your board is a genuine Raspberry Pi Pico/Pico W
- Check USB cable supports data transfer (not charge-only)

**No USB device appears:**
- Wait 3-5 seconds after flashing for device to enumerate
- Try a different USB port
- Check: `ls /dev/cu.usbmodem*` or `system_profiler SPUSBDataType | grep -i katapult`

**withclear vs regular UF2:**
- `katapult.uf2` - Standard version
- `katapult.withclear.uf2` - Erases application area at 0x10004000 (recommended)
- The `withclear` version ensures Katapult stays in bootloader mode when no Klipper is present

## Configuration Details

Key settings in `katapult_config`:
- `CONFIG_RPXXXX_FLASH_START_0100=y` - Katapult starts at 0x10000100
- `CONFIG_LAUNCH_APP_ADDRESS=0x10004000` - Klipper application address (16KB offset)
- `CONFIG_FLASH_APPLICATION_ADDRESS=0x10000100` - Auto-derived from FLASH_START choice
- `CONFIG_RP2040_STAGE2_FILE="boot2_w25q080.S"` - W25Q080 flash chip (Pico W compatible)
- `CONFIG_ENABLE_DOUBLE_RESET=y` - Re-enter bootloader via double-reset
