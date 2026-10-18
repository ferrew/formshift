#!/usr/bin/env python3
"""Format table and conversion backend for the Nautilus "Convert to" menu.

Imported by the Nautilus extension to decide which formats to offer, and run
as a separate process to do the actual conversion so Nautilus never blocks:

    converter.py --to png photo.heic scan.tiff
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402

# Target formats per category, in menu order: (extension, menu label).
TARGETS = {
    "image": [
        ("png", "PNG"), ("jpg", "JPEG"), ("webp", "WebP"), ("avif", "AVIF"),
        ("gif", "GIF"), ("tiff", "TIFF"), ("bmp", "BMP"), ("ico", "ICO (icon)"),
        ("pdf", "PDF"),
    ],
    "video": [
        ("mp4", "MP4 (H.264)"), ("mkv", "MKV"), ("webm", "WebM (VP9)"),
        ("mov", "MOV"), ("avi", "AVI"), ("gif", "Animated GIF"),
        ("mp3", "MP3 (audio only)"), ("m4a", "M4A (audio only)"),
    ],
    "audio": [
        ("mp3", "MP3"), ("m4a", "M4A (AAC)"), ("ogg", "Ogg Vorbis"),
        ("opus", "Opus"), ("flac", "FLAC"), ("wav", "WAV"),
    ],
    "document": [
        ("pdf", "PDF"), ("docx", "Word (DOCX)"), ("odt", "OpenDocument (ODT)"),
        ("rtf", "RTF"), ("html", "HTML"), ("txt", "Plain text"),
    ],
    "spreadsheet": [
        ("xlsx", "Excel (XLSX)"), ("ods", "OpenDocument (ODS)"),
        ("csv", "CSV"), ("pdf", "PDF"), ("html", "HTML"),
    ],
    "presentation": [
        ("pptx", "PowerPoint (PPTX)"), ("odp", "OpenDocument (ODP)"),
        ("pdf", "PDF"),
    ],
    "pdf": [
        ("png", "PNG (one per page)"), ("jpg", "JPEG (one per page)"),
        ("txt", "Plain text"),
    ],
}

DOCUMENT_MIMES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.oasis.opendocument.text",
    "application/rtf",
    "text/rtf",
    "text/plain",
    "text/markdown",
    "text/html",
}
SPREADSHEET_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.oasis.opendocument.spreadsheet",
    "text/csv",
}
PRESENTATION_MIMES = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
    "application/vnd.oasis.opendocument.presentation",
}

# LibreOffice needs explicit filters for some targets.
OFFICE_FILTERS = {
    "txt": "txt:Text (encoded):UTF8",
    "csv": "csv:Text - txt - csv (StarCalc):44,34,76",
    "html": "html",
}

EXTENSION_ALIASES = {"jpeg": "jpg", "tif": "tiff", "htm": "html", "mpeg4": "mp4"}


def category(mime):
    if mime == "application/pdf":
        return "pdf"
    if mime in DOCUMENT_MIMES:
        return "document"
    if mime in SPREADSHEET_MIMES:
        return "spreadsheet"
    if mime in PRESENTATION_MIMES:
        return "presentation"
    for prefix in ("image", "video", "audio"):
        if mime.startswith(prefix + "/"):
            return prefix
    return None


def extension_of(path):
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    return EXTENSION_ALIASES.get(ext, ext)


def targets_for(files):
    """Formats every file in `files` (a list of (path, mime)) can become.

    A format is hidden only when all files already have it.
    """
    common = None
    for _, mime in files:
        cat = category(mime)
        if cat is None:
            return []
        formats = TARGETS[cat]
        if common is None:
            common = list(formats)
        else:
            keep = {ext for ext, _ in formats}
            common = [(ext, label) for ext, label in common if ext in keep]
    if not common:
        return []
    exts = {extension_of(path) for path, _ in files}
    return [(ext, label) for ext, label in common if exts != {ext}]


def mime_of(path):
    info = Gio.File.new_for_path(path).query_info(
        "standard::content-type", Gio.FileQueryInfoFlags.NONE, None
    )
    return info.get_content_type()


def free_path(directory, stem, ext):
    candidate = os.path.join(directory, f"{stem}.{ext}")
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{stem} ({n}).{ext}")
        n += 1
    return candidate


class ConversionError(Exception):
    pass


def run(cmd, **kwargs):
    proc = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        raise ConversionError("\n".join(tail) or f"{cmd[0]} failed")
    return proc


class Notifier:
    """One desktop notification, updated in place."""

    def __init__(self):
        self.id = None
        self.last_update = 0.0

    def show(self, summary, body="", urgency="normal", throttle=False):
        if throttle and time.monotonic() - self.last_update < 1.5:
            return
        self.last_update = time.monotonic()
        cmd = ["notify-send", "--app-name=File Converter", "--print-id",
               "--icon=document-save-as", f"--urgency={urgency}"]
        if self.id:
            cmd.append(f"--replace-id={self.id}")
        cmd += [summary, body]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
            self.id = out or self.id
        except FileNotFoundError:
            pass


# --- converters -------------------------------------------------------------
# Each takes (src, dst, ext, progress) and writes dst, raising ConversionError.


def convert_image(src, dst, ext, progress):
    keeps_frames = ext in ("gif", "webp", "tiff", "pdf")
    cmd = ["magick", src if keeps_frames else f"{src}[0]", "-auto-orient"]
    if ext in ("jpg", "bmp"):
        cmd += ["-background", "white", "-alpha", "remove", "-alpha", "off"]
    if ext == "jpg":
        cmd += ["-quality", "92"]
    if ext == "ico":
        cmd += ["-resize", "256x256>", "-define", "icon:auto-resize=256,128,64,48,32,16"]
    run(cmd + [dst])


VIDEO_ARGS = {
    "mp4": ["-c:v", "libx264", "-crf", "23", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"],
    "mkv": ["-c:v", "libx264", "-crf", "23", "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
            "-sn"],
    "mov": ["-c:v", "libx264", "-crf", "23", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k"],
    "webm": ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1",
             "-c:a", "libopus", "-b:a", "128k"],
    "avi": ["-c:v", "mpeg4", "-q:v", "4", "-c:a", "libmp3lame", "-q:a", "3"],
    "gif": ["-vf", "fps=12,scale='min(640,iw)':-2:flags=lanczos,split[a][b];"
                   "[a]palettegen[p];[b][p]paletteuse", "-an"],
    "mp3": ["-vn", "-c:a", "libmp3lame", "-q:a", "2"],
    "m4a": ["-vn", "-c:a", "aac", "-b:a", "192k"],
    "ogg": ["-vn", "-c:a", "libvorbis", "-q:a", "6"],
    "opus": ["-vn", "-c:a", "libopus", "-b:a", "128k"],
    "flac": ["-vn", "-c:a", "flac"],
    "wav": ["-vn", "-c:a", "pcm_s16le"],
}


def duration_us(src):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", src],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip()) * 1_000_000
    except ValueError:
        return None


def convert_media(src, dst, ext, progress):
    total = duration_us(src)
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", src,
           *VIDEO_ARGS[ext], "-progress", "pipe:1", "-nostats", dst]
    # stderr goes to a file so a chatty ffmpeg can never fill the pipe and stall.
    with tempfile.TemporaryFile("w+") as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True)
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and total and value.isdigit():
                progress(min(int(value) / total, 1.0))
        if proc.wait() != 0:
            err.seek(0)
            tail = err.read().strip().splitlines()[-3:]
            raise ConversionError("\n".join(tail) or "ffmpeg failed")


def convert_office(src, dst, ext, progress):
    with tempfile.TemporaryDirectory(prefix="fileconv-") as tmp:
        # A private profile lets headless LibreOffice run while the user has it open.
        profile = Gio.File.new_for_path(os.path.join(tmp, "profile")).get_uri()
        outdir = os.path.join(tmp, "out")
        run(["soffice", f"-env:UserInstallation={profile}", "--headless",
             "--convert-to", OFFICE_FILTERS.get(ext, ext), "--outdir", outdir, src])
        produced = os.listdir(outdir) if os.path.isdir(outdir) else []
        if not produced:
            raise ConversionError("LibreOffice produced no output")
        shutil.move(os.path.join(outdir, produced[0]), dst)


def convert_pdf(src, dst, ext, progress):
    if ext == "txt":
        run(["pdftotext", "-layout", src, dst])
        return
    pages = 1
    for line in run(["pdfinfo", src]).stdout.splitlines():
        if line.startswith("Pages:"):
            pages = int(line.split()[1])
    fmt = "-png" if ext == "png" else "-jpeg"
    if pages == 1:
        run(["pdftoppm", fmt, "-r", "150", "-singlefile", src, dst[: -len(ext) - 1]])
        return
    # Several pages: write name-1.png, name-2.png, ... next to the final name.
    prefix = dst[: -len(ext) - 1]
    run(["pdftoppm", fmt, "-r", "150", src, prefix])


CONVERTERS = {
    "image": convert_image,
    "video": convert_media,
    "audio": convert_media,
    "document": convert_office,
    "spreadsheet": convert_office,
    "presentation": convert_office,
    "pdf": convert_pdf,
}


def convert(src, ext, progress=lambda fraction: None):
    """Convert one file; returns the output path."""
    cat = category(mime_of(src))
    if cat is None or ext not in {e for e, _ in TARGETS[cat]}:
        raise ConversionError(f"Can't convert this file to {ext.upper()}")
    directory = os.path.dirname(os.path.abspath(src))
    stem = os.path.splitext(os.path.basename(src))[0]
    dst = free_path(directory, stem, ext)

    if cat == "pdf" and ext != "txt":
        # pdftoppm names its own outputs; no temp-rename step.
        CONVERTERS[cat](src, dst, ext, progress)
        return dst

    # Write to a hidden temp name so a half-done file never looks finished.
    tmp = os.path.join(directory, f".{stem}.converting.{ext}")
    try:
        CONVERTERS[cat](src, tmp, ext, progress)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return dst


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", required=True, help="target extension, e.g. png")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    ext = args.to.lower()

    notifier = Notifier()
    done, failed = [], []
    for i, src in enumerate(args.files, 1):
        name = os.path.basename(src)
        counter = f" ({i}/{len(args.files)})" if len(args.files) > 1 else ""
        notifier.show(f"Converting to {ext.upper()}{counter}", name)

        def progress(fraction, name=name, counter=counter):
            notifier.show(f"Converting to {ext.upper()}{counter}",
                          f"{name}: {fraction:.0%}", throttle=True)

        try:
            convert(src, ext, progress)
            done.append(name)
        except (ConversionError, OSError) as exc:
            failed.append(f"{name}: {exc}")
            print(f"{src}: {exc}", file=sys.stderr)

    if failed:
        notifier.show(f"{len(failed)} of {len(args.files)} conversions failed",
                      "\n".join(failed), urgency="critical")
    elif len(done) == 1:
        notifier.show(f"Converted to {ext.upper()}", done[0])
    else:
        notifier.show(f"Converted {len(done)} files to {ext.upper()}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
