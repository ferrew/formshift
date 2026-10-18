# File Converter

Adds **Convert to** to the right-click menu of your file manager: GNOME Files
(Nautilus) on Linux, Explorer on Windows and Finder on macOS. Pick a format and
the converted file appears next to the original.

Only formats that fit the selected file are offered:

| Selected file | Can become |
|---|---|
| Image (png, jpg, heic, svg, ...) | PNG, JPEG, WebP, AVIF, GIF, TIFF, BMP, ICO, PDF |
| Video | MP4, MKV, WebM, MOV, AVI, animated GIF, MP3 or M4A (audio only) |
| Audio | MP3, M4A, Ogg Vorbis, Opus, FLAC, WAV |
| Text document (docx, doc, odt, rtf, md, txt, html) | PDF, DOCX, ODT, RTF, HTML, TXT |
| Spreadsheet (xlsx, xls, ods, csv) | XLSX, ODS, CSV, PDF, HTML |
| Presentation (pptx, ppt, odp) | PPTX, ODP, PDF |
| PDF | PNG or JPEG (one image per page), TXT |

## Behaviour

- Originals are never touched. If `photo.png` already exists, the output is `photo (2).png`.
- Conversions run in a separate process, so the file manager stays responsive.
  A notification reports the result; on Linux and Windows it also shows progress
  for audio and video.
- Output is written to a temporary file first, so a failed or interrupted
  conversion never leaves a broken file behind.
- Office conversions use a private LibreOffice profile, so they work while
  LibreOffice is open.

## Install

The conversions are done by [ffmpeg](https://ffmpeg.org), [ImageMagick](https://imagemagick.org),
[LibreOffice](https://www.libreoffice.org) and [Poppler](https://poppler.freedesktop.org).
The install scripts add whichever of these are missing.

### Linux (Ubuntu, GNOME Files)

Tested on Ubuntu 26.04 with Nautilus 50.

```bash
git clone https://github.com/ferrew/nautilus-file-converter.git
cd nautilus-file-converter
./install.sh
```

Missing packages are installed with `apt`, which asks for your password.

### Windows 10 and 11

In PowerShell:

```powershell
git clone https://github.com/ferrew/nautilus-file-converter.git
cd nautilus-file-converter
powershell -ExecutionPolicy Bypass -File install.ps1
```

Missing tools are installed with `winget`. The menu is registered for your user
only, so no administrator rights are needed for that part.

On Windows 11, **Convert to** is in the classic menu: right-click, then
**Show more options** (or press Shift+F10). Explorer starts one conversion per
file and hides the menu when more than 15 files are selected.

### macOS

Needs [Homebrew](https://brew.sh).

```bash
git clone https://github.com/ferrew/nautilus-file-converter.git
cd nautilus-file-converter
./install.sh
```

Right-click files in Finder and choose **Quick Actions > Convert to…**. A dialog
asks which format to convert to. If the action doesn't show up, enable it in
System Settings > General > Login Items & Extensions > Finder.

### Uninstall

Run `./uninstall.sh` (Linux, macOS) or `uninstall.ps1` (Windows). The conversion
tools stay installed.

## Command line

The converter also works on its own:

```bash
python3 converter.py --to webp *.png
```

## How it works

- `converter.py` holds the format table and does the conversions. It is the only
  part shared by all platforms.
- `file_converter_menu.py` is the Nautilus extension.
- `windows_menu.py` writes the Explorer submenu to the registry under
  `HKEY_CURRENT_USER`.
- `macos_menu.py` generates the Finder Quick Action in `~/Library/Services`.

To add a format, add it to `TARGETS` in `converter.py`, plus encoder arguments in
`VIDEO_ARGS` for audio and video. To accept a new source type, add its extension
to `EXTENSIONS`. Rerun the installer afterwards.

## License

GPL-3.0. See [LICENSE](LICENSE).
