#!/usr/bin/env bash
# Initialize or update a local pi-gen clone on the arm64 branch and optionally pin to a commit.
#
# This intentionally does NOT use git submodules (.gitmodules) because that tends to confuse
# workflows and create noisy git status output. The pi-gen checkout is expected to be ignored
# via .gitignore.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_BUILD_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(git -C "${IMAGE_BUILD_DIR}/../.." rev-parse --show-toplevel 2>/dev/null || pwd)"

SUBMODULE_PATH="${IMAGE_BUILD_DIR}/pi-gen"
PIGEN_URL="${PIGEN_URL:-https://github.com/RPi-Distro/pi-gen.git}"
PIGEN_BRANCH="${PIGEN_BRANCH:-arm64}"
# Optional: pin to a specific commit by exporting PIGEN_COMMIT=<sha>
PIGEN_COMMIT="${PIGEN_COMMIT:-}"

echo "Repo root: ${REPO_ROOT}"
echo "pi-gen target: ${SUBMODULE_PATH}"

if [ -e "${SUBMODULE_PATH}" ] && [ ! -d "${SUBMODULE_PATH}" ]; then
  echo "${SUBMODULE_PATH} exists but is not a directory" >&2
  exit 1
fi

if [ ! -d "${SUBMODULE_PATH}/.git" ]; then
  if [ -d "${SUBMODULE_PATH}" ] && [ -n "$(ls -A "${SUBMODULE_PATH}" 2>/dev/null)" ]; then
    echo "${SUBMODULE_PATH} exists but is not a git repo; please remove it or move it aside." >&2
    exit 1
  fi

  echo "Cloning pi-gen from ${PIGEN_URL} (branch ${PIGEN_BRANCH})"
  rm -rf "${SUBMODULE_PATH}"
  git clone --branch "${PIGEN_BRANCH}" --depth 1 "${PIGEN_URL}" "${SUBMODULE_PATH}"
else
  echo "Updating existing pi-gen clone"
  git -C "${SUBMODULE_PATH}" fetch --prune origin "${PIGEN_BRANCH}"
fi

if [ -n "${PIGEN_COMMIT}" ]; then
  echo "Pinning pi-gen to ${PIGEN_COMMIT}"
  git -C "${SUBMODULE_PATH}" checkout "${PIGEN_COMMIT}"
else
  git -C "${SUBMODULE_PATH}" checkout "${PIGEN_BRANCH}" || true
  git -C "${SUBMODULE_PATH}" reset --hard "origin/${PIGEN_BRANCH}"
fi

git -C "${SUBMODULE_PATH}" submodule update --init --recursive || true

echo -n "pi-gen is now at commit: "
git -C "${SUBMODULE_PATH}" rev-parse --short HEAD
