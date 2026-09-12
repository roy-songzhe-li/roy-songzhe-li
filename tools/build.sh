#!/usr/bin/env bash
# Rebuild the approved portrait and CRT GIF. Requires chafa, ffmpeg, and Python 3.10-3.12.
set -euo pipefail

TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$TOOLS")"
WORK="$TOOLS/build"
VENV="$TOOLS/.venv"

for dependency in chafa ffmpeg; do
  command -v "$dependency" >/dev/null 2>&1 || { echo "Missing dependency: $dependency" >&2; exit 1; }
done

pick_python() {
  for candidate in python3.12 python3.11 python3.10 python3; do
    command -v "$candidate" >/dev/null 2>&1 && { echo "$candidate"; return; }
  done
  echo "No Python 3 interpreter found" >&2
  exit 1
}

mkdir -p "$WORK"
[ -d "$VENV" ] || "$(pick_python)" -m venv "$VENV"
"$VENV/bin/pip" install -q -r "$TOOLS/requirements.txt"
"$VENV/bin/python" "$TOOLS/build_avatar.py" "$REPO/assets/avatar-source.png" "$REPO/assets/avatar-pixel.png"
"$VENV/bin/python" "$TOOLS/build_screen.py" "$REPO/assets/avatar-pixel.png" "$WORK/swatch.png" "$WORK/screen.png"
"$VENV/bin/python" "$TOOLS/build_crt.py" "$WORK/screen.png" "$REPO/assets/crt-profile.gif"

echo "Done -> $REPO/assets/crt-profile.gif"
