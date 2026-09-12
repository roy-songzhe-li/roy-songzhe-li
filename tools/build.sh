#!/usr/bin/env bash
# Rebuild assets/crt-profile.gif from scratch. Needs python3 and ffmpeg on PATH.
set -euo pipefail

USERNAME="roy-songzhe-li"
TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$TOOLS")"
WORK="$TOOLS/build"
VENV="$TOOLS/.venv"

# gifos pins Pillow ^10, which has no wheels for the newest CPython, so prefer a known-good one.
pick_python() {
  for candidate in python3.12 python3.11 python3.10 python3; do
    command -v "$candidate" >/dev/null 2>&1 && { echo "$candidate"; return; }
  done
  echo "no python3 found" >&2
  exit 1
}

mkdir -p "$WORK"
[ -d "$VENV" ] || "$(pick_python)" -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$TOOLS/requirements.txt"

curl -sSfL -o "$WORK/avatar-source.png" "https://github.com/$USERNAME.png?size=800"
"$VENV/bin/python" "$TOOLS/build_avatar.py" "$WORK/avatar-source.png" "$REPO/assets/avatar-pixel.png"
"$VENV/bin/python" "$TOOLS/build_screen.py" "$REPO/assets/avatar-pixel.png" "$WORK/swatch.png" "$WORK/screen.png"
"$VENV/bin/python" "$TOOLS/build_crt.py" "$WORK/screen.png" "$REPO/assets/crt-profile.gif"

echo "done -> $REPO/assets/crt-profile.gif"
