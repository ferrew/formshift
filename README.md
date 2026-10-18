# nautilus-file-converter

Adds a **Convert to** submenu to the right-click menu in GNOME Files (Nautilus).
Pick a format and the converted file appears next to the original.

The menu only offers formats that fit the selection:

| Selected file | Can become |
|---|---|
| Image (png, jpg, heic, svg, ...) | PNG, JPEG, WebP, AVIF, GIF, TIFF, BMP, ICO, PDF |
| Video | MP4, MKV, WebM, MOV, AVI, animated GIF, MP3 or M4A (audio only) |
| Audio | MP3, M4A, Ogg Vorbis, Opus, FLAC, WAV |
| Text document (docx, doc, odt, rtf, md, txt, html) | PDF, DOCX, ODT, RTF, HTML, TXT |
| Spreadsheet (xlsx, xls, ods, csv) | XLSX, ODS, CSV, PDF, HTML |
| Presentation (pptx, ppt, odp) | PPTX, ODP, PDF |
| PDF | PNG or JPEG (one image per page), TXT |

When several files are selected, only formats that work for all of them are shown.

## Behaviour

- Originals are never touched. If `photo.png` already exists, the output is `photo (2).png`.
- Conversions run in a separate process, so Files stays responsive. A desktop
  notification shows progress (with a percentage for audio and video) and the result.
- Unfinished output is written to a hidden temporary file, so a failed or
  interrupted conversion never leaves a broken file behind.
- Office conversions use a private LibreOffice profile, so they work while
  LibreOffice is open.

## Install

Tested on Ubuntu 26.04 with Nautilus 50.

```bash
git clone https://github.com/ferrew/nautilus-file-converter.git
cd nautilus-file-converter
./install.sh
```

`install.sh` installs whatever is missing from `python3-nautilus`, `ffmpeg`,
`imagemagick`, `libreoffice`, `poppler-utils` and `libnotify-bin` (this asks for
your password), copies the extension into `~/.local/share`, and restarts Files.

To remove it, run `./uninstall.sh`.

## Command line

The backend works on its own too:

```bash
python3 converter.py --to webp *.png
```

## How it works

- `file_converter_menu.py` is the Nautilus extension. It builds the menu and
  starts the backend.
- `converter.py` holds the format table and does the conversions with ImageMagick,
  ffmpeg, LibreOffice (headless) and poppler.

Adding a format means adding an entry to `TARGETS` in `converter.py`, plus encoder
arguments in `VIDEO_ARGS` for audio and video formats.

## License

GPL-3.0. See [LICENSE](LICENSE).
