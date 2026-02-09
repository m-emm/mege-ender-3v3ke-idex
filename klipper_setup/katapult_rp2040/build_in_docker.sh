#!/bin/bash
# Build script for Katapult (runs inside Docker container)
set -euo pipefail
trap 'echo "Build failed at line $LINENO" >&2' ERR

cd /work

# Clone Katapult if needed
if [ ! -d katapult/.git ]; then
    echo '==> Cloning Katapult repository...'
    git clone https://github.com/Arksine/katapult.git katapult
fi

echo "==> Checking out Katapult ref: ${KATAPULT_REF}"
cd katapult
git fetch --all --tags
git checkout -f "${KATAPULT_REF}"

echo '==> Configuring Katapult for Raspberry Pi Pico (W)...'
make clean
cp /work/katapult_config .config

echo '==> Building Katapult...'
make

echo ""
echo "==> Build complete!"
echo "Bootloader UF2: /work/katapult/out/katapult.uf2"
ls -lh /work/katapult/out/katapult.uf2
ls -lh /work/katapult/out/katapult.withclear.uf2
