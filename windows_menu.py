"""Adds or removes the "Convert to" submenu in Windows Explorer.

    python windows_menu.py install
    python windows_menu.py uninstall

Everything goes under HKEY_CURRENT_USER, so no administrator rights are needed.
On Windows 11 the menu sits under "Show more options" (or Shift+F10).
"""

import os
import shutil
import sys

import converter

APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Formshift")
CLASSES = r"Software\Classes\SystemFileAssociations"
VERB = "Formshift"


def menu_entries():
    """(source extension, [(target extension, label), ...]) for every known type."""
    for ext, cat in sorted(converter.EXTENSION_CATEGORY.items()):
        same = converter.EXTENSION_ALIASES.get(ext, ext)
        yield ext, [(t, label) for t, label in converter.TARGETS[cat] if t != same]


def command_for(target, backend, pythonw):
    return f'"{pythonw}" "{backend}" --to {target} "%1"'


def pythonw_path():
    candidate = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return candidate if os.path.exists(candidate) else sys.executable


def delete_tree(winreg, root, path):
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS)
    except FileNotFoundError:
        return
    with key:
        while True:
            try:
                child = winreg.EnumKey(key, 0)
            except OSError:
                break
            delete_tree(winreg, root, f"{path}\\{child}")
    winreg.DeleteKey(root, path)


def install():
    import winreg

    os.makedirs(APP_DIR, exist_ok=True)
    backend = os.path.join(APP_DIR, "converter.py")
    shutil.copy2(os.path.join(os.path.dirname(os.path.abspath(__file__)), "converter.py"),
                 backend)
    pythonw = pythonw_path()

    hkcu = winreg.HKEY_CURRENT_USER
    for ext, targets in menu_entries():
        base = f"{CLASSES}\\.{ext}\\shell\\{VERB}"
        delete_tree(winreg, hkcu, base)
        with winreg.CreateKey(hkcu, base) as key:
            winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, "Convert to")
            winreg.SetValueEx(key, "SubCommands", 0, winreg.REG_SZ, "")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, "imageres.dll,-5302")
        # Explorer sorts submenu entries by key name, so prefix with the position.
        for i, (target, label) in enumerate(targets):
            item = f"{base}\\shell\\{i:02d}{target}"
            with winreg.CreateKey(hkcu, item) as key:
                winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, label)
            with winreg.CreateKey(hkcu, f"{item}\\command") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ,
                                  command_for(target, backend, pythonw))
    print(f"Registered \"Convert to\" for {len(converter.EXTENSION_CATEGORY)} file types.")


def uninstall():
    import winreg

    for ext, _ in menu_entries():
        delete_tree(winreg, winreg.HKEY_CURRENT_USER, f"{CLASSES}\\.{ext}\\shell\\{VERB}")
    shutil.rmtree(APP_DIR, ignore_errors=True)
    print("Removed.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("install", "uninstall"):
        sys.exit(__doc__)
    install() if sys.argv[1] == "install" else uninstall()
