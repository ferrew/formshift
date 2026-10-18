# Installs the "Convert to" right-click menu for Windows Explorer.
# Run from PowerShell:  powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"

function Find-Python {
    # The WindowsApps "python" is only a Microsoft Store shortcut, so ask the py launcher.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $path = (& py -3 -c "import sys; print(sys.executable)" 2>$null)
        if ($LASTEXITCODE -eq 0 -and $path) { return $path.Trim() }
    }
    return $null
}

function Install-Package($id) {
    Write-Host "Installing $id"
    winget install --id $id -e --accept-package-agreements --accept-source-agreements
}

if (-not (Find-Python)) { Install-Package "Python.Python.3.13" }

# command -> winget package that provides it
$needs = [ordered]@{
    "ffmpeg"   = "Gyan.FFmpeg"
    "magick"   = "ImageMagick.ImageMagick"
    "pdftoppm" = "oschwartz10612.Poppler"
}
foreach ($cmd in $needs.Keys) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Install-Package $needs[$cmd] }
}
if (-not (Test-Path "$env:ProgramFiles\LibreOffice\program\soffice.exe")) {
    Install-Package "TheDocumentFoundation.LibreOffice"
}

# Pick up PATH changes made by the installers above.
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [Environment]::GetEnvironmentVariable("Path", "User")

$python = Find-Python
if (-not $python) { throw "Python was installed but can't be found yet. Open a new PowerShell window and run this again." }
& $python "$PSScriptRoot\windows_menu.py" install
Write-Host "Done. Right-click a file in Explorer (on Windows 11: Show more options) to see ""Convert to""."
