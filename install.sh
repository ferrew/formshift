#!/usr/bin/env bash
# Installs the "Convert to" right-click menu: Nautilus on Linux, Finder on macOS.
# Windows uses install.ps1 instead.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"

install_macos() {
    if ! command -v brew >/dev/null; then
        echo "Homebrew is needed to install ffmpeg and friends: https://brew.sh" >&2
        exit 1
    fi
    missing=()
    for cmd in ffmpeg:ffmpeg magick:imagemagick pdftoppm:poppler python3:python; do
        command -v "${cmd%%:*}" >/dev/null || missing+=("${cmd##*:}")
    done
    if ((${#missing[@]})); then
        echo "Installing: ${missing[*]}"
        brew install "${missing[@]}"
    fi
    [[ -d /Applications/LibreOffice.app ]] || brew install --cask libreoffice

    python3 "$here/macos_menu.py" install
    echo "Right-click files in Finder and choose \"Convert to…\" (under Quick Actions)."
}

install_linux() {
    local backend="$HOME/.local/share/nautilus-file-converter"
    local extensions="$HOME/.local/share/nautilus-python/extensions"

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
    rm -rf "$extensions/__pycache__"

    nautilus -q 2>/dev/null || true
    echo "Installed. Open Files and right-click a file to see \"Convert to\"."
}

case "$(uname -s)" in
    Darwin) install_macos ;;
    Linux) install_linux ;;
    *) echo "Unsupported system. On Windows, run install.ps1." >&2; exit 1 ;;
esac
