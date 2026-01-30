#!/usr/bin/env bash
# List external, physical disks suitable for flashing on macOS.
set -euo pipefail

if ! command -v diskutil >/dev/null 2>&1; then
  echo "diskutil not found (macOS only script)." >&2
  exit 1
fi

echo "External, physical disks:"
DISKS=$(diskutil list external physical | awk '/^\/dev\// {print $1}')

if [ -z "${DISKS}" ]; then
  echo "  (none found)"
  exit 0
fi

for d in ${DISKS}; do
  echo "---- ${d} ----"
  diskutil info "${d}" | awk '
    /Device Node/ ||
    /Device Identifier/ ||
    /Device Model/ ||
    /Media Name/ ||
    /Protocol/ ||
    /Total Size/ ||
    /Disk Size/ ||
    /Removable Media/ ||
    /Virtual:/ ||
    /Solid State/ ||
    /Device Location/ ||
    /Volume Name/ {print}'
done
