#!/usr/bin/env bash
# Removes the "Convert to" menu. The converter tools (ffmpeg etc.) stay installed.
set -euo pipefail

if [[ "$(uname -s)" == Darwin ]]; then
    python3 "$(cd "$(dirname "$0")" && pwd)/macos_menu.py" uninstall
    exit
fi

rm -f "$HOME/.local/share/nautilus-python/extensions/formshift.py"
rm -rf "$HOME/.local/share/formshift"
nautilus -q 2>/dev/null || true
echo "Removed."
