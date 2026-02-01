#!/bin/bash
set -euo pipefail
trap 'echo "Script $0 failed at line $LINENO" >&2' ERR


cd /work

# Clone if needed
if [ ! -d klipper/.git ]; then
    echo '==> Cloning Klipper repository...'
    git clone https://github.com/Klipper3d/klipper.git klipper
fi



echo "==> Checking out Klipper ref: ${KLIPPER_REF}"
cd klipper

git fetch --all --tags
git checkout -f "${KLIPPER_REF}"
git submodule update --init --recursive


echo "==> Cleaning previous build..."

echo '==> Configuring for RP2040...'
cp /work/rp2040_config ./.config

echo "==> Building firmware..."

make


echo ""
echo "==> Build complete!"
echo "Firmware: /work/klipper/out/klipper.uf2"
ls -lh /work/klipper/out/klipper.uf2
