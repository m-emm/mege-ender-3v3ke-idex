#!/bin/bash
set -euo pipefail
trap 'echo "Script $0 failed at line $LINENO" >&2' ERR

cd /work

# Clone if needed
if [ ! -d katapult/.git ]; then
    echo '==> Cloning Katapult repository...'
    git clone https://github.com/Arksine/katapult.git katapult
fi

echo "==> Checking out Katapult ref: ${KATAPULT_REF}"
cd katapult

git fetch --all --tags
git checkout -f "${KATAPULT_REF}"

echo '==> Configuring Katapult...'
# Use the Klipper config as base, but fix bootloader settings for Katapult
# Katapult IS the bootloader, so it should NOT have bootloader offset
cp /work/rp2040_config ./.config

# Get the application address from Klipper config (where Klipper will run)
launch_app_address="$(grep -E '^CONFIG_FLASH_APPLICATION_ADDRESS=' /work/rp2040_config | head -n1 | cut -d= -f2 || true)"
if [[ -z "${launch_app_address}" ]]; then
    launch_app_address="0x10004000"
fi

# Katapult must NOT have the bootloader flag - it IS the bootloader
sed -i 's/^CONFIG_RPXXXX_HAVE_BOOTLOADER=y/# CONFIG_RPXXXX_HAVE_BOOTLOADER is not set/' ./.config

# Katapult starts at 0x100 (after stage2), NOT at the application offset
sed -i 's/^CONFIG_RPXXXX_FLASH_START_4000=y/# CONFIG_RPXXXX_FLASH_START_4000 is not set/' ./.config
sed -i 's/^# CONFIG_RPXXXX_FLASH_START_0100 is not set/CONFIG_RPXXXX_FLASH_START_0100=y/' ./.config

# Fix the flash application address - Katapult needs to know where Klipper will be stored
sed -i "s/^CONFIG_FLASH_APPLICATION_ADDRESS=.*/CONFIG_FLASH_APPLICATION_ADDRESS=${launch_app_address}/" ./.config

# Add Katapult-specific config symbols
if ! grep -qE '^CONFIG_FLASH_START=' ./.config; then
    echo 'CONFIG_FLASH_START=0x10000000' >> ./.config
fi
if ! grep -qE '^CONFIG_LAUNCH_APP_ADDRESS=' ./.config; then
    echo "CONFIG_LAUNCH_APP_ADDRESS=${launch_app_address}" >> ./.config
fi

echo '==> Cleaning previous build...'
make clean

echo '==> Building Katapult...'
make

echo ""
echo "==> Build complete!"
echo "Bootloader UF2: /work/katapult/out/katapult.uf2"
ls -lh /work/katapult/out/katapult.uf2
