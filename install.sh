#!/usr/bin/env bash
# Installs the "Convert to" right-click menu: Nautilus on Linux, Finder on macOS.
# Windows uses install.ps1 instead.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"

# Copies LibreOffice.app into Formshift's own folder instead of /Applications,
# so it doesn't show up as an installed app.
install_libreoffice_macos() {
    local tools="$HOME/Library/Application Support/Formshift/tools"
    [[ -d /Applications/LibreOffice.app || -d "$tools/LibreOffice.app" ]] && return
    local base=https://download.documentfoundation.org/libreoffice/stable
    local version arch dir mnt dmg
    version=$(curl -fsSL "$base/" | grep -oE 'href="[0-9.]+/"' | grep -oE '[0-9]+(\.[0-9]+)+' |
        sort -t. -k1,1n -k2,2n -k3,3n | tail -1)
    if [[ "$(uname -m)" == arm64 ]]; then dir=aarch64 arch=aarch64; else dir=x86_64 arch=x86-64; fi
    dmg="$(mktemp -d)/libreoffice.dmg"
    mnt="$(mktemp -d)"
    echo "Downloading LibreOffice $version"
    curl -fL --progress-bar -o "$dmg" "$base/$version/mac/$dir/LibreOffice_${version}_MacOS_${arch}.dmg"
    hdiutil attach -nobrowse -quiet -mountpoint "$mnt" "$dmg"
    mkdir -p "$tools"
    cp -R "$mnt/LibreOffice.app" "$tools/"
    hdiutil detach -quiet "$mnt"
    rm -f "$dmg"
}

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
    install_libreoffice_macos


    python3 "$here/macos_menu.py" install
    echo "Right-click files in Finder and choose \"Convert to…\" (under Quick Actions)."
}

install_linux() {
    local backend="$HOME/.local/share/formshift"
    local extensions="$HOME/.local/share/nautilus-python/extensions"

    # command -> package that provides it
    declare -A needs=(
        [ffmpeg]=ffmpeg [magick]=imagemagick [soffice]=libreoffice-nogui
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
    install -m 644 "$here/nautilus_menu.py" "$extensions/formshift.py"
    # Clean up installs from before the rename.
    rm -rf "$extensions/file_converter_menu.py" "$extensions/__pycache__" \
        "$HOME/.local/share/nautilus-file-converter"

    nautilus -q 2>/dev/null || true
    echo "Installed. Open Files and right-click a file to see \"Convert to\"."
}

case "$(uname -s)" in
    Darwin) install_macos ;;
    Linux) install_linux ;;
    *) echo "Unsupported system. On Windows, run install.ps1." >&2; exit 1 ;;
esac
