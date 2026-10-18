#!/usr/bin/env bash
# Installs the "Convert to" right-click menu for Nautilus (GNOME Files).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
backend="$HOME/.local/share/nautilus-file-converter"
extensions="$HOME/.local/share/nautilus-python/extensions"

# command -> package that provides it
declare -A needs=(
    [ffmpeg]=ffmpeg [magick]=imagemagick [soffice]=libreoffice
    [pdftoppm]=poppler-utils [notify-send]=libnotify-bin
)
missing=()
dpkg -s python3-nautilus >/dev/null 2>&1 || missing+=(python3-nautilus)
for cmd in "${!needs[@]}"; do
    command -v "$cmd" >/dev/null || missing+=("${needs[$cmd]}")
done
if ((${#missing[@]})); then
    echo "Installing: ${missing[*]}"
    sudo apt-get install -y "${missing[@]}"
fi

mkdir -p "$backend" "$extensions"
install -m 755 "$here/converter.py" "$backend/converter.py"
install -m 644 "$here/file_converter_menu.py" "$extensions/file_converter_menu.py"

nautilus -q 2>/dev/null || true
echo "Installed. Open Files and right-click a file to see \"Convert to\"."
