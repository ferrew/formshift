"""Nautilus extension: adds a "Convert to" submenu to the file context menu.

The conversion itself runs in a separate process (converter.py) so Nautilus
stays responsive; progress and results show up as desktop notifications.
"""

import os
import subprocess
import sys

import gi

gi.require_version("Nautilus", "4.0")
from gi.repository import GObject, Nautilus  # noqa: E402

BACKEND_DIR = os.path.expanduser("~/.local/share/nautilus-file-converter")
sys.path.insert(0, BACKEND_DIR)
import converter  # noqa: E402


class FileConverterMenu(GObject.GObject, Nautilus.MenuProvider):
    def get_file_items(self, files):
        selected = []
        for f in files:
            if f.is_directory() or f.get_uri_scheme() != "file":
                return []
            path = f.get_location().get_path()
            if path is None:
                return []
            selected.append((path, f.get_mime_type()))

        targets = converter.targets_for(selected)
        if not targets:
            return []

        top = Nautilus.MenuItem(name="FileConverter::Top", label="Convert to")
        submenu = Nautilus.Menu()
        top.set_submenu(submenu)
        paths = [path for path, _ in selected]
        for ext, label in targets:
            item = Nautilus.MenuItem(name=f"FileConverter::{ext}", label=label)
            item.connect("activate", self._convert, ext, paths)
            submenu.append_item(item)
        return [top]

    def _convert(self, _item, ext, paths):
        subprocess.Popen(
            ["/usr/bin/python3", os.path.join(BACKEND_DIR, "converter.py"),
             "--to", ext, *paths],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )
