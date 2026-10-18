# Installs the "Convert to" right-click menu for Windows Explorer.
# Run from PowerShell:  powershell -ExecutionPolicy Bypass -File install.ps1
#
# Nothing is installed system-wide: Python and the conversion tools are
# downloaded and unpacked into %LOCALAPPDATA%\Formshift, without installers,
# admin rights or Start menu entries. Add -NoDocuments to skip LibreOffice
# (about 350 MB), which is only needed for office documents.
param([switch]$NoDocuments)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # the progress bar slows downloads to a crawl in PowerShell 5
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$PythonVersion = "3.13.16"
$root = "$env:LOCALAPPDATA\Formshift"
$tools = "$root\tools"
$tmp = Join-Path $env:TEMP "formshift-setup"
New-Item -ItemType Directory -Force $tools, $tmp | Out-Null

function Get-File($url, $name) {
    $path = Join-Path $tmp $name
    Write-Host "Downloading $name"
    Invoke-WebRequest -Uri $url -OutFile $path -UseBasicParsing
    return $path
}

function Get-GitHubAsset($repo, $pattern) {
    $release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest"
    $asset = $release.assets | Where-Object { $_.name -like $pattern } | Select-Object -First 1
    if (-not $asset) { throw "No download matching $pattern in $repo" }
    return Get-File $asset.browser_download_url $asset.name
}

function Expand-Into($archive, $dest) {
    $stage = Join-Path $tmp ("unpack-" + [IO.Path]::GetFileNameWithoutExtension($archive))
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
    if ($archive -like "*.7z") {
        $sevenZip = Join-Path $tmp "7zr.exe"
        if (-not (Test-Path $sevenZip)) { Get-File "https://www.7-zip.org/a/7zr.exe" "7zr.exe" | Out-Null }
        & $sevenZip x $archive "-o$stage" -y | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not unpack $archive" }
    } else {
        Expand-Archive $archive $stage -Force
    }
    # Most archives wrap everything in one top-level folder; drop it.
    $items = @(Get-ChildItem $stage)
    $source = if ($items.Count -eq 1 -and $items[0].PSIsContainer) { $items[0].FullName } else { $stage }
    Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
    Move-Item $source $dest
}

function Test-Tool($cmd, $privatePath) {
    return (Test-Path $privatePath) -or [bool](Get-Command $cmd -ErrorAction SilentlyContinue)
}

# Python, always a private copy so the system Python (if any) doesn't matter.
if (-not (Test-Path "$tools\python\pythonw.exe")) {
    $zip = Get-File "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" "python.zip"
    Expand-Into $zip "$tools\python"
}

if (-not (Test-Tool "ffmpeg" "$tools\ffmpeg\bin\ffmpeg.exe")) {
    $zip = Get-File "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" "ffmpeg.zip"
    Expand-Into $zip "$tools\ffmpeg"
}

if (-not (Test-Tool "magick" "$tools\imagemagick\magick.exe")) {
    $archive = Get-GitHubAsset "ImageMagick/ImageMagick" "ImageMagick-*-portable-Q16-x64.7z"
    Expand-Into $archive "$tools\imagemagick"
}

if (-not (Test-Tool "pdftoppm" "$tools\poppler\Library\bin\pdftoppm.exe")) {
    $zip = Get-GitHubAsset "oschwartz10612/poppler-windows" "Release-*.zip"
    Expand-Into $zip "$tools\poppler"
}

$officeInstalled = (Test-Path "$env:ProgramFiles\LibreOffice\program\soffice.exe") -or
                   (Test-Path "$tools\libreoffice")
if (-not $NoDocuments -and -not $officeInstalled) {
    $index = (Invoke-WebRequest "https://download.documentfoundation.org/libreoffice/stable/" -UseBasicParsing).Content
    $version = [regex]::Matches($index, 'href="(\d+(?:\.\d+)+)/"') |
        ForEach-Object { $_.Groups[1].Value } | Sort-Object { [version]$_ } | Select-Object -Last 1
    $msi = Get-File "https://download.documentfoundation.org/libreoffice/stable/$version/win/x86_64/LibreOffice_${version}_Win_x86-64.msi" "libreoffice.msi"
    # An administrative install (/a) only unpacks the files; nothing gets registered.
    Write-Host "Unpacking LibreOffice $version (this takes a few minutes)"
    $proc = Start-Process msiexec.exe -Wait -PassThru -ArgumentList @(
        "/a", "`"$msi`"", "/qn", "TARGETDIR=`"$tools\libreoffice`"")
    if ($proc.ExitCode -ne 0) {
        Write-Warning "Unpacking LibreOffice failed (msiexec exit code $($proc.ExitCode)); office documents will be skipped."
        Remove-Item "$tools\libreoffice" -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

& "$tools\python\python.exe" "$PSScriptRoot\windows_menu.py" install
if ($LASTEXITCODE -ne 0) { throw "Registering the menu failed" }
Write-Host "Done. Right-click a file in Explorer (on Windows 11: Show more options) to see ""Convert to""."
