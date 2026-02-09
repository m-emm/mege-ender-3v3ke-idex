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
# The workspace rp2040_config is primarily a Klipper config. Katapult requires
# additional symbols that Klipper doesn't use.
cp /work/rp2040_config ./.config

launch_app_address="$(grep -E '^CONFIG_FLASH_APPLICATION_ADDRESS=' /work/rp2040_config | head -n1 | cut -d= -f2 || true)"
if [[ -z "${launch_app_address}" ]]; then
    launch_app_address="0x10004000"
fi

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
