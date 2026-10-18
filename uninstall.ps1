# Removes the "Convert to" menu. The converter tools (ffmpeg etc.) stay installed.
$ErrorActionPreference = "Stop"
$python = (& py -3 -c "import sys; print(sys.executable)").Trim()
& $python "$PSScriptRoot\windows_menu.py" uninstall
