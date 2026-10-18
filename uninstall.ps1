# Removes the "Convert to" menu and everything install.ps1 downloaded.
$ErrorActionPreference = "Stop"
$root = "$env:LOCALAPPDATA\Formshift"
$python = "$root\tools\python\python.exe"
if (-not (Test-Path $python)) {
    # Installed by an older version of install.ps1, which used the system Python.
    $python = (& py -3 -c "import sys; print(sys.executable)").Trim()
}
& $python "$PSScriptRoot\windows_menu.py" uninstall
Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Removed $root."
