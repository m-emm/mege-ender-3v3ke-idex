#!/usr/bin/env bash
# Render overlays, build the image via pi-gen/docker, and copy artifacts + manifest to image_build/out.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_BUILD_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${IMAGE_BUILD_DIR}/out"
PIGEN_DIR="${IMAGE_BUILD_DIR}/pi-gen"

timestamp() { date -u +"%Y-%m-%dT%H-%M-%SZ"; }

# Setup logging
mkdir -p "${OUT_DIR}"
LOG_FILE="${OUT_DIR}/build-$(timestamp).log"
exec > >(tee -a "${LOG_FILE}") 2>&1
echo "==> Build started at $(date)"
echo "==> Logging to ${LOG_FILE}"

echo "==> Step 1: ensure pi-gen checkout"
"${SCRIPT_DIR}/setup_pigen_submodule.sh"

echo "==> Step 2: render overlay"
"${SCRIPT_DIR}/render_overlay.sh"

if [ ! -x "${PIGEN_DIR}/build-docker.sh" ]; then
  echo "pi-gen build-docker.sh not found. setup_pigen_submodule.sh may have failed." >&2
  exit 1
fi

echo "==> Step 3: run pi-gen build (docker)"
pushd "${PIGEN_DIR}" >/dev/null
./build-docker.sh
popd >/dev/null

mkdir -p "${OUT_DIR}"

LATEST_IMG="$(ls -1t "${PIGEN_DIR}"/deploy/*.img* "${PIGEN_DIR}"/deploy/*.zip 2>/dev/null | head -n 1 || true)"
if [ -z "${LATEST_IMG}" ]; then
  echo "No image found in ${PIGEN_DIR}/deploy. Build may have failed." >&2
  exit 1
fi

STAMP="$(timestamp)"
IMG_BASENAME="$(basename "${LATEST_IMG}")"
case "${IMG_BASENAME}" in
  *.img.xz)
    BASE_NO_EXT="${IMG_BASENAME%.img.xz}"
    DEST_IMG="${OUT_DIR}/${BASE_NO_EXT}-${STAMP}.img.xz"
    ;;
  *.img)
    BASE_NO_EXT="${IMG_BASENAME%.img}"
    DEST_IMG="${OUT_DIR}/${BASE_NO_EXT}-${STAMP}.img"
    ;;
  *.zip)
    BASE_NO_EXT="${IMG_BASENAME%.zip}"
    DEST_IMG="${OUT_DIR}/${BASE_NO_EXT}-${STAMP}.zip"
    ;;
  *)
    BASE_NO_EXT="${IMG_BASENAME}"
    DEST_IMG="${OUT_DIR}/${BASE_NO_EXT}-${STAMP}"
    ;;
esac

echo "==> Copying ${IMG_BASENAME} -> ${DEST_IMG}"
cp "${LATEST_IMG}" "${DEST_IMG}"

echo "==> Updating latest symlink"
ln -sfn "$(basename "${DEST_IMG}")" "${OUT_DIR}/latest"
case "${DEST_IMG}" in
  *.img.xz)
    ln -sfn "$(basename "${DEST_IMG}")" "${OUT_DIR}/latest.img.xz"
    ;;
  *.img)
    ln -sfn "$(basename "${DEST_IMG}")" "${OUT_DIR}/latest.img"
    ;;
  *.zip)
    ln -sfn "$(basename "${DEST_IMG}")" "${OUT_DIR}/latest.zip"
    ;;
esac

echo "==> Writing manifest"
PIGEN_COMMIT="$(git -C "${PIGEN_DIR}" rev-parse HEAD 2>/dev/null || echo 'unknown')"

# One manifest per artifact (so older manifests are preserved).
MANIFEST_PATH="${OUT_DIR}/$(basename "${DEST_IMG}").manifest.txt"
cat > "${MANIFEST_PATH}" <<EOF
build_timestamp=${STAMP}
pigen_commit=${PIGEN_COMMIT}
source_image=${IMG_BASENAME}
copied_image=$(basename "${DEST_IMG}")
EOF

if [ -f "${IMAGE_BUILD_DIR}/secrets/build.env" ]; then
  echo "" >> "${MANIFEST_PATH}"
  echo "# build.env snapshot" >> "${MANIFEST_PATH}"
  cat "${IMAGE_BUILD_DIR}/secrets/build.env" >> "${MANIFEST_PATH}"
fi

# Convenience symlinks to the newest manifest.
ln -sfn "$(basename "${MANIFEST_PATH}")" "${OUT_DIR}/manifest.txt"
ln -sfn "$(basename "${MANIFEST_PATH}")" "${OUT_DIR}/latest.manifest.txt"

echo "Build complete. Artifacts in ${OUT_DIR}"
echo "==> Build finished at $(date)"
echo "==> Full log available at ${LOG_FILE}"
