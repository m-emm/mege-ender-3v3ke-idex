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


if [[ "${SKIP_CLEAN:-0}" == "1" ]]; then
    echo "==> Preserving previous build output (SKIP_CLEAN=1)."
else
    echo "==> Cleaning previous build..."
    make clean
fi

echo '==> Configuring for RP2040...'
: "${KLIPPER_CONFIG_FILE:=rp2040_config}"
cp "/work/${KLIPPER_CONFIG_FILE}" ./.config

echo "==> Building firmware..."

make


echo ""
echo "==> Build complete!"
if [[ -f /work/klipper/out/klipper.bin ]]; then
    echo "Firmware (Katapult): /work/klipper/out/klipper.bin"
    ls -lh /work/klipper/out/klipper.bin
elif [[ -f /work/klipper/out/klipper.uf2 ]]; then
    echo "Firmware (direct): /work/klipper/out/klipper.uf2"
    ls -lh /work/klipper/out/klipper.uf2
else
    echo "ERROR: No expected firmware output found in /work/klipper/out" >&2
    ls -lh /work/klipper/out >&2 || true
    exit 1
fi
