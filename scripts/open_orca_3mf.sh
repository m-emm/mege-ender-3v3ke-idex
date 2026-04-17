#!/bin/zsh

set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: $0 <3mf-file> [orca-app-bundle]" >&2
    exit 1
fi

input_path="$1"
orca_app="${2:-${ORCA_APP_BUNDLE:-/Applications/OrcaSlicer 2_3_0.app}}"

if [[ ! -d "$orca_app" ]]; then
    echo "OrcaSlicer app bundle not found: $orca_app" >&2
    exit 1
fi

if [[ "$input_path" = /* ]]; then
    project_path="$input_path"
else
    project_path="$PWD/$input_path"
fi

if [[ ! -f "$project_path" ]]; then
    echo "3MF file not found: $project_path" >&2
    exit 1
fi

project_dir="$(cd "$(dirname "$project_path")" && pwd)"
project_file="$(basename "$project_path")"
project_abs="$project_dir/$project_file"

exec /usr/bin/open -a "$orca_app" "$project_abs"