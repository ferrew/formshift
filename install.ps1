# Installs the "Convert to" right-click menu for Windows Explorer.
# Run from PowerShell:  powershell -ExecutionPolicy Bypass -File install.ps1
#
# Nothing is installed system-wide: Python and the conversion tools are
# downloaded and unpacked into %LOCALAPPDATA%\Formshift, without installers,
# admin rights or Start menu entries. Add -NoDocuments to skip LibreOffice
# (about 350 MB), which is only needed for office documents. It asks once to
# accept the tools' licenses; -Yes accepts without asking.
param([switch]$NoDocuments, [switch]$Yes)

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

$needPython = -not (Test-Path "$tools\python\pythonw.exe")  # always private, the system Python doesn't matter
$needFfmpeg = -not (Test-Tool "ffmpeg" "$tools\ffmpeg\bin\ffmpeg.exe")
$needMagick = -not (Test-Tool "magick" "$tools\imagemagick\magick.exe")
$needPoppler = -not (Test-Tool "pdftoppm" "$tools\poppler\Library\bin\pdftoppm.exe")
$needOffice = -not $NoDocuments -and -not (
    (Test-Path "$env:ProgramFiles\LibreOffice\program\soffice.exe") -or (Test-Path "$tools\libreoffice"))

$downloads = @(
    @($needPython, "Python", "PSF License", "https://docs.python.org/3/license.html"),
    @($needFfmpeg, "FFmpeg", "GPL-3.0", "https://ffmpeg.org/legal.html"),
    @($needMagick, "ImageMagick", "ImageMagick License", "https://imagemagick.org/script/license.php"),
    @($needMagick, "7-Zip (7zr, to unpack ImageMagick)", "LGPL-2.1", "https://www.7-zip.org/license.txt"),
    @($needPoppler, "Poppler", "GPL-2.0", "https://poppler.freedesktop.org"),
    @($needOffice, "LibreOffice (about 350 MB)", "MPL-2.0", "https://www.libreoffice.org/about-us/licenses/")
) | Where-Object { $_[0] } | ForEach-Object {
    [pscustomobject]@{ Tool = $_[1]; License = $_[2]; Terms = $_[3] }
}

if ($downloads) {
    Write-Host "Formshift will download these tools into $tools`:"
    $downloads | Format-Table -AutoSize | Out-Host
    Write-Host "By continuing you accept their license terms (links above)."
    if (-not $Yes) {
        $answer = Read-Host "Continue? [y/N]"
        if ($answer -notmatch '^(y|yes|j|ja)$') { Write-Host "Cancelled, nothing was downloaded."; exit 1 }
    }
}

if ($needPython) {
    $zip = Get-File "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" "python.zip"
    Expand-Into $zip "$tools\python"
}

if ($needFfmpeg) {
    $zip = Get-File "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" "ffmpeg.zip"
    Expand-Into $zip "$tools\ffmpeg"
}

if ($needMagick) {
    $archive = Get-GitHubAsset "ImageMagick/ImageMagick" "ImageMagick-*-portable-Q16-x64.7z"
    Expand-Into $archive "$tools\imagemagick"
}

if ($needPoppler) {
    $zip = Get-GitHubAsset "oschwartz10612/poppler-windows" "Release-*.zip"
    Expand-Into $zip "$tools\poppler"
}

if ($needOffice) {
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
