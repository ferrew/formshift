#!/usr/bin/env bash
set -euo pipefail
rm -f "$HOME/.local/share/nautilus-python/extensions/file_converter_menu.py"
rm -rf "$HOME/.local/share/nautilus-file-converter"
nautilus -q 2>/dev/null || true
echo "Removed."
