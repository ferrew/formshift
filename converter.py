#!/usr/bin/env python3
"""Formshift: format table and conversion backend for the "Convert to" menu.

The platform integrations (Nautilus, Windows Explorer, macOS Finder) import
this to decide which formats to offer, and run it as a separate process to do
the conversion so the file manager never blocks:

    converter.py --to png photo.heic scan.tiff
    converter.py --choose clip.mov        # ask for the format in a dialog (macOS)
"""

import argparse
import base64
import glob
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

try:
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio
except (ImportError, ValueError):
    Gio = None

WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"

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

# Source file extensions per category. Windows and macOS menus are registered
# per extension; Linux falls back to the MIME type for anything not listed.
EXTENSIONS = {
    "image": "png jpg jpeg webp avif gif tif tiff bmp ico heic heif svg",
    "video": "mp4 m4v mkv webm mov avi wmv flv mpg mpeg 3gp",
    "audio": "mp3 m4a aac ogg oga opus flac wav wma aif aiff",
    "document": "docx doc odt rtf txt md html htm",
    "spreadsheet": "xlsx xls ods csv",
    "presentation": "pptx ppt odp",
    "pdf": "pdf",
}
EXTENSION_CATEGORY = {
    ext: cat for cat, exts in EXTENSIONS.items() for ext in exts.split()
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

EXTENSION_ALIASES = {"jpeg": "jpg", "tif": "tiff", "htm": "html", "aiff": "aif"}

# The installers put tools here on Windows and macOS instead of installing
# them system-wide.
if WINDOWS:
    PRIVATE_TOOLS = os.path.expandvars(r"%LOCALAPPDATA%\Formshift\tools")
else:
    PRIVATE_TOOLS = os.path.expanduser("~/Library/Application Support/Formshift/tools")

# Where tools live when they are not on PATH, which is common for programs
# started from Finder or Explorer.
EXTRA_TOOL_DIRS = {
    "darwin": [
        "/opt/homebrew/bin", "/usr/local/bin",
        f"{PRIVATE_TOOLS}/LibreOffice.app/Contents/MacOS",
        "/Applications/LibreOffice.app/Contents/MacOS",
    ],
    "win32": [
        rf"{PRIVATE_TOOLS}\ffmpeg\bin",
        rf"{PRIVATE_TOOLS}\imagemagick",
        rf"{PRIVATE_TOOLS}\poppler\Library\bin",
        rf"{PRIVATE_TOOLS}\libreoffice\program",
        rf"{PRIVATE_TOOLS}\libreoffice\*\program",
        os.path.expandvars(r"%ProgramFiles%\LibreOffice\program"),
        os.path.expandvars(r"%ProgramFiles%\ImageMagick-*"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*\*\bin"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*\*\Library\bin"),
    ],
}

# Keep console windows from flashing up for every tool on Windows.
NO_WINDOW = {"creationflags": 0x08000000} if WINDOWS else {}


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


def category_of(path, mime=None):
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    if ext in EXTENSION_CATEGORY:
        return EXTENSION_CATEGORY[ext]
    if mime is None and Gio is not None and os.path.exists(path):
        mime = Gio.File.new_for_path(path).query_info(
            "standard::content-type", Gio.FileQueryInfoFlags.NONE, None
        ).get_content_type()
    return category(mime) if mime else None


def targets_for(files):
    """Formats every file in `files` (a list of (path, mime or None)) can become.

    A format is hidden only when all files already have it.
    """
    common = None
    for path, mime in files:
        cat = category_of(path, mime)
        if cat is None:
            return []
        keep = {ext for ext, _ in TARGETS[cat]}
        common = TARGETS[cat] if common is None else [t for t in common if t[0] in keep]
    if not common:
        return []
    exts = {extension_of(path) for path, _ in files}
    return [(ext, label) for ext, label in common if exts != {ext}]


def tool(name):
    found = shutil.which(name)
    if not found:
        dirs = [d for pattern in EXTRA_TOOL_DIRS.get(sys.platform, [])
                for d in glob.glob(pattern)]
        found = shutil.which(name, path=os.pathsep.join(dirs))
    if not found:
        raise ConversionError(f"{name} is not installed")
    return found


# The tool each category needs; used to only offer what this machine can do.
CATEGORY_TOOL = {
    "image": "magick", "video": "ffmpeg", "audio": "ffmpeg",
    "document": "soffice", "spreadsheet": "soffice", "presentation": "soffice",
    "pdf": "pdftoppm",
}


def available(cat):
    try:
        tool(CATEGORY_TOOL[cat])
        return True
    except ConversionError:
        return False


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
    cmd = [tool(cmd[0]), *cmd[1:]]
    proc = subprocess.run(cmd, capture_output=True, text=True, **NO_WINDOW, **kwargs)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        raise ConversionError("\n".join(tail) or f"{os.path.basename(cmd[0])} failed")
    return proc


# --- notifications ----------------------------------------------------------


def applescript_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def xml_escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


WINDOWS_TOAST = """
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('{xml}')
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$toast.Tag = '{tag}'
$toast.Group = 'Formshift'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app}').Show($toast)
"""
# Windows only shows toasts from registered apps; PowerShell is always registered.
POWERSHELL_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


class Notifier:
    """One desktop notification, updated in place where the platform allows."""

    def __init__(self):
        self.id = None
        self.last_update = 0.0

    def show(self, summary, body="", urgency="normal", throttle=False, final=False):
        if throttle:
            if MACOS:  # macOS can't replace a notification, so skip progress spam
                return
            if time.monotonic() - self.last_update < (4 if WINDOWS else 1.5):
                return
        self.last_update = time.monotonic()
        try:
            if WINDOWS:
                self._windows(summary, body, silent=throttle, wait=final)
            elif MACOS:
                script = (f"display notification {applescript_string(body)} "
                          f"with title \"Formshift\" "
                          f"subtitle {applescript_string(summary)}")
                subprocess.run(["osascript", "-e", script], capture_output=True)
            else:
                self._linux(summary, body, urgency)
        except (FileNotFoundError, OSError):
            pass

    def _linux(self, summary, body, urgency):
        cmd = ["notify-send", "--app-name=Formshift", "--print-id",
               "--icon=document-save-as", f"--urgency={urgency}"]
        if self.id:
            cmd.append(f"--replace-id={self.id}")
        out = subprocess.run(cmd + [summary, body], capture_output=True, text=True)
        self.id = out.stdout.strip() or self.id

    def _windows(self, summary, body, silent, wait):
        audio = '<audio silent="true"/>' if silent else ""
        xml = ('<toast><visual><binding template="ToastGeneric">'
               f"<text>{xml_escape(summary)}</text><text>{xml_escape(body)}</text>"
               f"</binding></visual>{audio}</toast>")
        script = WINDOWS_TOAST.format(xml=xml.replace("'", "''"),
                                      tag=f"fc{os.getpid()}", app=POWERSHELL_APP_ID)
        encoded = base64.b64encode(script.encode("utf-16-le")).decode()
        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
        proc = subprocess.Popen(cmd, **NO_WINDOW)
        if wait:
            proc.wait()


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
        [tool("ffprobe"), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", src],
        capture_output=True, text=True, **NO_WINDOW,
    )
    try:
        return float(proc.stdout.strip()) * 1_000_000
    except ValueError:
        return None


def convert_media(src, dst, ext, progress):
    total = duration_us(src)
    cmd = [tool("ffmpeg"), "-hide_banner", "-nostdin", "-y", "-i", src,
           *VIDEO_ARGS[ext], "-progress", "pipe:1", "-nostats", dst]
    # stderr goes to a file so a chatty ffmpeg can never fill the pipe and stall.
    with tempfile.TemporaryFile("w+") as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True,
                                **NO_WINDOW)
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and total and value.isdigit():
                progress(min(int(value) / total, 1.0))
        if proc.wait() != 0:
            err.seek(0)
            tail = err.read().strip().splitlines()[-3:]
            raise ConversionError("\n".join(tail) or "ffmpeg failed")


def convert_office(src, dst, ext, progress):
    with tempfile.TemporaryDirectory(prefix="formshift-") as tmp:
        # A private profile lets headless LibreOffice run while the user has it open.
        profile = pathlib.Path(tmp, "profile").as_uri()
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
    prefix = dst[: -len(ext) - 1]
    if pages == 1:
        run(["pdftoppm", fmt, "-r", "150", "-singlefile", src, prefix])
    else:
        # Several pages: pdftoppm writes name-1.png, name-2.png, ...
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
    cat = category_of(src)
    if cat is None or ext not in {e for e, _ in TARGETS[cat]}:
        raise ConversionError(f"Can't convert this file to {ext.upper()}")
    directory = os.path.dirname(os.path.abspath(src))
    stem = os.path.splitext(os.path.basename(src))[0]
    dst = free_path(directory, stem, ext)

    if cat == "pdf" and ext != "txt":
        # pdftoppm names its own outputs; no temp-rename step.
        CONVERTERS[cat](src, dst, ext, progress)
        return dst

    # Write to a temp name first so a half-done file never looks finished.
    tmp = os.path.join(directory, f".{stem}.converting.{ext}")
    try:
        CONVERTERS[cat](src, tmp, ext, progress)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return dst


def choose_format(files):
    """Ask which format to convert to (macOS Quick Action). None if cancelled."""
    targets = targets_for([(f, None) for f in files])
    if not targets:
        subprocess.run(["osascript", "-e",
                        'display alert "These files can\'t be converted together."'])
        return None
    labels = ", ".join(applescript_string(label) for _, label in targets)
    script = (f"choose from list {{{labels}}} with title \"Convert to\" "
              f"with prompt \"Convert {len(files)} file(s) to:\" "
              f"default items {{{applescript_string(targets[0][1])}}}")
    out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    picked = out.stdout.strip()
    return next((ext for ext, label in targets if label == picked), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--to", help="target extension, e.g. png")
    group.add_argument("--choose", action="store_true",
                       help="ask for the target format in a dialog (macOS)")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    ext = choose_format(args.files) if args.choose else args.to.lower()
    if ext is None:
        return 0

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
            if sys.stderr:  # None under pythonw.exe
                print(f"{src}: {exc}", file=sys.stderr)

    if failed:
        notifier.show(f"{len(failed)} of {len(args.files)} conversions failed",
                      "\n".join(failed), urgency="critical", final=True)
    elif len(done) == 1:
        notifier.show(f"Converted to {ext.upper()}", done[0], final=True)
    else:
        notifier.show(f"Converted {len(done)} files to {ext.upper()}", final=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
