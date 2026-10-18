"""Adds or removes the "Convert to…" Quick Action in the macOS Finder.

    python3 macos_menu.py install
    python3 macos_menu.py uninstall

The Quick Action shows up when you right-click files in Finder (under
Quick Actions on some macOS versions) and asks which format to convert to.
"""

import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import uuid

APP_DIR = os.path.expanduser("~/Library/Application Support/FileConverter")
WORKFLOW = os.path.expanduser("~/Library/Services/Convert to….workflow")
FINDER = "/System/Library/CoreServices/Finder.app"
SHELL_ACTION = "/System/Library/Automator/Run Shell Script.action"


def shell_script(python, backend):
    return (
        'export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"\n'
        f'{shlex.quote(python)} {shlex.quote(backend)} --choose "$@"\n'
    )


def info_plist():
    return {
        "NSServices": [{
            "NSMenuItem": {"default": "Convert to…"},
            "NSMessage": "runWorkflowAsService",
            "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
            "NSSendFileTypes": ["public.item"],
            "NSIconName": "NSActionTemplate",
        }]
    }


def document_wflow(script):
    ids = {k: str(uuid.uuid4()).upper() for k in ("input", "output", "action")}
    action = {
        "AMAccepts": {"Container": "List", "Optional": True,
                      "Types": ["com.apple.cocoa.string"]},
        "AMActionVersion": "2.0.3",
        "AMApplication": ["Automator"],
        "AMParameterProperties": {k: {} for k in (
            "COMMAND_STRING", "CheckedForUserDefaultShell", "inputMethod", "shell", "source")},
        "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
        "ActionBundlePath": SHELL_ACTION,
        "ActionName": "Run Shell Script",
        "ActionParameters": {
            "COMMAND_STRING": script,
            "CheckedForUserDefaultShell": True,
            "inputMethod": 1,  # pass the selected files as arguments
            "shell": "/bin/bash",
            "source": "",
        },
        "BundleIdentifier": "com.apple.RunShellScript",
        "CFBundleVersion": "2.0.3",
        "CanShowSelectedItemsWhenRun": False,
        "CanShowWhenRun": True,
        "Category": ["AMCategoryUtilities"],
        "Class Name": "RunShellScriptAction",
        "InputUUID": ids["input"],
        "Keywords": ["Shell", "Script", "Command", "Run", "Unix"],
        "OutputUUID": ids["output"],
        "UUID": ids["action"],
        "UnlocalizedApplications": ["Automator"],
        "isViewVisible": 1,
        "location": "309.000000:253.000000",
        "nibPath": f"{SHELL_ACTION}/Contents/Resources/Base.lproj/main.nib",
    }
    return {
        "AMApplicationBuild": "523",
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "actions": [{"action": action, "isViewVisible": 1}],
        "connectors": {},
        "workflowMetaData": {
            "applicationBundleID": "com.apple.finder",
            "applicationBundleIDsByPath": {FINDER: "com.apple.finder"},
            "applicationPath": FINDER,
            "applicationPaths": [FINDER],
            "inputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "outputTypeIdentifier": "com.apple.Automator.nothing",
            "presentationMode": 15,
            "processesInput": False,
            "serviceApplicationBundleID": "com.apple.finder",
            "serviceApplicationPath": FINDER,
            "serviceInputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceProcessesInput": False,
            "systemImageName": "NSActionTemplate",
            "useAutomaticInputType": False,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    }


def write_workflow(path, python, backend):
    contents = os.path.join(path, "Contents")
    os.makedirs(contents, exist_ok=True)
    with open(os.path.join(contents, "Info.plist"), "wb") as f:
        plistlib.dump(info_plist(), f)
    with open(os.path.join(contents, "document.wflow"), "wb") as f:
        plistlib.dump(document_wflow(shell_script(python, backend)), f)


def refresh_services():
    pbs = "/System/Library/CoreServices/pbs"
    if os.path.exists(pbs):
        subprocess.run([pbs, "-update"], check=False)


def install():
    os.makedirs(APP_DIR, exist_ok=True)
    backend = os.path.join(APP_DIR, "converter.py")
    shutil.copy2(os.path.join(os.path.dirname(os.path.abspath(__file__)), "converter.py"),
                 backend)
    shutil.rmtree(WORKFLOW, ignore_errors=True)
    write_workflow(WORKFLOW, sys.executable, backend)
    refresh_services()
    print("Installed the \"Convert to…\" Quick Action.")


def uninstall():
    shutil.rmtree(WORKFLOW, ignore_errors=True)
    shutil.rmtree(APP_DIR, ignore_errors=True)
    refresh_services()
    print("Removed.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("install", "uninstall"):
        sys.exit(__doc__)
    install() if sys.argv[1] == "install" else uninstall()
