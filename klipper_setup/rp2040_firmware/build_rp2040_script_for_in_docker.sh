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


if [[ "${CLEAN:-0}" == "1" ]]; then
    echo "==> Cleaning previous build (CLEAN=1)..."
    make clean
else
    echo "==> Preserving previous build output for incremental Docker build."
fi

echo '==> Configuring for RP2040...'
: "${KLIPPER_CONFIG_FILE:=rp2040_config}"
cp "/work/${KLIPPER_CONFIG_FILE}" ./.config
: "${EXPECTED_FIRMWARE:=}"
if [[ -z "${EXPECTED_FIRMWARE}" ]]; then
    if grep -qE '^CONFIG_RPXXXX_HAVE_BOOTLOADER=y' ./.config; then
        EXPECTED_FIRMWARE="klipper.bin"
    else
        EXPECTED_FIRMWARE="klipper.uf2"
    fi
fi

case "${EXPECTED_FIRMWARE}" in
    klipper.bin)
        rm -f /work/klipper/out/klipper.uf2
        ;;
    klipper.uf2)
        rm -f /work/klipper/out/klipper.bin
        ;;
    *)
        echo "ERROR: Unexpected EXPECTED_FIRMWARE=${EXPECTED_FIRMWARE}" >&2
        exit 2
        ;;
esac

echo "==> Building firmware..."

make


echo ""
echo "==> Build complete!"
if [[ "${EXPECTED_FIRMWARE}" == "klipper.bin" && -f /work/klipper/out/klipper.bin ]]; then
    echo "Firmware (Katapult): /work/klipper/out/klipper.bin"
    ls -lh /work/klipper/out/klipper.bin
elif [[ "${EXPECTED_FIRMWARE}" == "klipper.uf2" && -f /work/klipper/out/klipper.uf2 ]]; then
    echo "Firmware (direct): /work/klipper/out/klipper.uf2"
    ls -lh /work/klipper/out/klipper.uf2
else
    echo "ERROR: Expected /work/klipper/out/${EXPECTED_FIRMWARE}, but it was not found" >&2
    ls -lh /work/klipper/out >&2 || true
    exit 1
fi
