"""Adds or removes the "Convert to" submenu in Windows Explorer.

    python windows_menu.py install
    python windows_menu.py uninstall

Everything goes under HKEY_CURRENT_USER, so no administrator rights are needed.
On Windows 11 the menu sits under "Show more options" (or Shift+F10).
"""

import os
import shutil
import sys

# The embedded Python from install.ps1 doesn't put the script's folder on sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import converter  # noqa: E402

APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Formshift")
CLASSES = r"Software\Classes\SystemFileAssociations"
VERB = "Formshift"


def menu_entries(only_available=False):
    """(source extension, [(target extension, label), ...]) for every known type."""
    for ext, cat in sorted(converter.EXTENSION_CATEGORY.items()):
        if only_available and not converter.available(cat):
            continue
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
    registered = 0
    for ext, _ in menu_entries():
        delete_tree(winreg, hkcu, f"{CLASSES}\\.{ext}\\shell\\{VERB}")
    for ext, targets in menu_entries(only_available=True):
        base = f"{CLASSES}\\.{ext}\\shell\\{VERB}"
        registered += 1
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
    print(f"Registered \"Convert to\" for {registered} file types.")
    missing = sorted({c for c in converter.CATEGORY_TOOL if not converter.available(c)})
    if missing:
        print(f"Skipped (tool not found): {', '.join(missing)}")


def uninstall():
    import winreg

    for ext, _ in menu_entries():
        delete_tree(winreg, winreg.HKEY_CURRENT_USER, f"{CLASSES}\\.{ext}\\shell\\{VERB}")
    # uninstall.ps1 deletes APP_DIR afterwards; the Python running this lives in it.
    print("Removed the menu.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("install", "uninstall"):
        sys.exit(__doc__)
    install() if sys.argv[1] == "install" else uninstall()
