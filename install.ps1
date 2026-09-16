# =====================================================================
#  Slideshow Video Creator Pro - one-click installer (fresh Windows)
#
#  Installs everything the app needs on a machine with nothing on it:
#    1. Python 3.12 (if a suitable one is not already present)
#    2. A local virtual environment .venv with the Python packages
#    3. A local FFmpeg (ffmpeg.exe + ffprobe.exe) in .\ffmpeg
#    4. A desktop shortcut to run.bat
#
#  Every step is wrapped so a failure is REPORTED (console + install_log.txt)
#  instead of silently breaking the app. Run it by double-clicking install.bat.
# =====================================================================

#Requires -Version 5.1

$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$AppDir     = $PSScriptRoot
$LogFile    = Join-Path $AppDir 'install_log.txt'
$PyVersion  = '3.12.10'   # last 3.12 with a Windows installer (later 3.12.x are source-only)
$FFmpegUrl  = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
$VenvDir    = Join-Path $AppDir '.venv'
$VenvPy     = Join-Path $VenvDir 'Scripts\python.exe'
$VenvPip    = Join-Path $VenvDir 'Scripts\pip.exe'
$FFmpegDir  = Join-Path $AppDir 'ffmpeg'
$ReqsFile   = Join-Path $AppDir 'requirements.txt'
$RunBat     = Join-Path $AppDir 'run.bat'

$script:Failures = New-Object System.Collections.Generic.List[string]
$script:Warnings = New-Object System.Collections.Generic.List[string]

# ---------------------------------------------------------------- helpers
function Write-Log {
    param([string]$Message)
    try {
        $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        Add-Content -LiteralPath $LogFile -Value "[$stamp] $Message" -Encoding UTF8
    } catch { }
}
function Info  ($m) { Write-Host $m; Write-Log $m }
function OK    ($m) { Write-Host "    OK  $m" -ForegroundColor Green;  Write-Log "OK: $m" }
function Warn  ($m) { Write-Host "    !!  $m" -ForegroundColor Yellow; Write-Log "WARNING: $m"; [void]$script:Warnings.Add($m) }
function Err   ($m) { Write-Host "    XX  $m" -ForegroundColor Red;    Write-Log "ERROR: $m";   [void]$script:Failures.Add($m) }
function Head  ($n, $t) { Write-Host ""; Write-Host "==> Step $n : $t" -ForegroundColor Cyan; Write-Log "==> Step $n : $t" }

function Download-File {
    param([string]$Url, [string]$Dest, [string]$Name)
    Info "    Downloading $Name ..."
    Write-Log "Download: $Url -> $Dest"
    if (Test-Path -LiteralPath $Dest) { Remove-Item -LiteralPath $Dest -Force -ErrorAction SilentlyContinue }
    $ok = $false
    try {
        Start-BitsTransfer -Source $Url -Destination $Dest -ErrorAction Stop
        $ok = $true
    } catch {
        Write-Log "BITS transfer failed: $($_.Exception.Message). Trying Invoke-WebRequest..."
    }
    if (-not $ok) {
        $old = $ProgressPreference
        $ProgressPreference = 'SilentlyContinue'
        try {
            Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing -TimeoutSec 900 -ErrorAction Stop
            $ok = $true
        } finally {
            $ProgressPreference = $old
        }
    }
    if (-not $ok -or -not (Test-Path -LiteralPath $Dest)) { throw "Download failed for $Name" }
    $size = (Get-Item -LiteralPath $Dest).Length
    if ($size -le 0) { throw "Downloaded file is empty: $Name" }
    Info ("    Saved {0} ({1:N1} MB)" -f $Name, ($size / 1MB))
}

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Get-Python312 {
    # A python.exe whose version is exactly 3.12, or $null.
    $perUser = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (Test-Path -LiteralPath $perUser) { return $perUser }

    if (Test-Command 'py') {
        try {
            $p = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
            if ($LASTEXITCODE -eq 0 -and $p -and (Test-Path -LiteralPath $p.Trim())) { return $p.Trim() }
        } catch { }
    }

    if (Test-Command 'python') {
        try {
            $exe = (Get-Command python).Source
            $ver = (& $exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null | Select-Object -First 1)
            if ($LASTEXITCODE -eq 0 -and $ver -and $ver.Trim() -eq '3.12') { return $exe }
        } catch { }
    }
    return $null
}

function Invoke-Pip {
    param([string[]]$PipArgs)
    & $VenvPy -m pip @PipArgs --disable-pip-version-check
    return $LASTEXITCODE
}

# ====================================================================
Write-Host ""
Write-Host "===================================================" -ForegroundColor White
Write-Host "  Slideshow Video Creator Pro - Installer" -ForegroundColor White
Write-Host "===================================================" -ForegroundColor White
Write-Host "Folder: $AppDir"
Set-Content -LiteralPath $LogFile -Value "Install started $(Get-Date)" -Encoding UTF8
Write-Log "AppDir=$AppDir"
Write-Log "PowerShell=$($PSVersionTable.PSVersion)  OS=$([Environment]::OSVersion.VersionString)  Arch=$env:PROCESSOR_ARCHITECTURE 64bit=$([Environment]::Is64BitOperatingSystem)"

# ------------------------------------------------- Step 0: sanity checks
Head 0 'Checking the machine'
$abort = $false
if (-not [Environment]::Is64BitOperatingSystem) {
    Err 'Windows is 32-bit. The app needs 64-bit Windows 10/11.'
    $abort = $true
}
try {
    $probe = Join-Path $AppDir ('.write_test_' + [guid]::NewGuid().ToString('N'))
    Set-Content -LiteralPath $probe -Value 'x' -Encoding ASCII
    Remove-Item -LiteralPath $probe -Force
    OK 'Folder is writable'
} catch {
    Err "Cannot write to the app folder. Move the folder to Desktop or Documents and run again."
    $abort = $true
}
if (-not (Test-Path -LiteralPath $ReqsFile)) {
    Err "requirements.txt not found next to install.ps1."
    $abort = $true
}
if ($abort) {
    Write-Host ""
    Write-Host "Cannot continue. See below." -ForegroundColor Red
    Write-Host "Log: $LogFile"
    exit 1
}

# ------------------------------------------------- Step 1: internet check
Head 1 'Checking internet connection'
$online = $false
foreach ($test in @('https://pypi.org', 'https://www.python.org')) {
    try {
        Invoke-WebRequest -Uri $test -Method Head -UseBasicParsing -TimeoutSec 20 | Out-Null
        $online = $true
        break
    } catch { }
}
if ($online) { OK 'Internet is available' }
else {
    Err 'No internet connection. Connect to the internet and run the installer again.'
    Write-Host ""
    Write-Host "Cannot continue without internet." -ForegroundColor Red
    Write-Host "Log: $LogFile"
    exit 1
}

# ------------------------------------------------- Step 2: Python
Head 2 "Python $PyVersion"
$python = Get-Python312
if ($python) {
    OK "Found existing Python 3.12: $python"
} else {
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
    $url = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-$arch.exe"
    $installer = Join-Path $env:TEMP "python-$PyVersion-$arch.exe"
    try {
        Download-File -Url $url -Dest $installer -Name "Python $PyVersion"
        Info '    Installing Python (per-user, no admin needed)...'
        $pyArgs = @(
            '/quiet',
            'InstallAllUsers=0',
            'PrependPath=1',
            'Include_test=0',
            'Include_tcltk=1',
            'Include_pip=1',
            'Include_launcher=1',
            'InstallLauncherAllUsers=0'
        )
        $proc = Start-Process -FilePath $installer -ArgumentList $pyArgs -Wait -PassThru
        if ($proc.ExitCode -ne 0 -and $proc.ExitCode -ne 3010) { throw "Python installer exit code $($proc.ExitCode)" }
        $python = Get-Python312
        if (-not $python) { throw 'Python installed, but python.exe was not found afterwards.' }
        OK "Python installed: $python"
    } catch {
        Err "Python installation failed: $($_.Exception.Message)"
        if (Test-Command 'winget') {
            Info '    Trying winget as a fallback...'
            try {
                & winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
                $python = Get-Python312
                if ($python) { OK "Python installed via winget: $python" }
                else { Err 'winget finished but Python 3.12 was still not found.' }
            } catch { Err "winget fallback failed: $($_.Exception.Message)" }
        } else {
            Warn 'winget is not available for a fallback. Install Python 3.12 manually from https://www.python.org/downloads/windows/'
        }
    }
}

if (-not $python) {
    Write-Host ""
    Write-Host "Python is required - cannot install the app's packages." -ForegroundColor Red
    Write-Host "Log: $LogFile"
    exit 1
}

# ------------------------------------------------- Step 3: virtual environment
Head 3 'Python virtual environment (.venv)'
$venvOk = $false
if (Test-Path -LiteralPath $VenvPy) {
    try {
        & $VenvPy -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) { $venvOk = $true }
    } catch { }
    if ($venvOk) {
        OK 'Existing .venv found and works'
    } else {
        Warn 'Existing .venv does not work (maybe copied from another PC). Recreating it...'
        Remove-Item -LiteralPath $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
if (-not $venvOk) {
    try {
        Info '    Creating .venv ...'
        & $python -m venv $VenvDir
        if (-not (Test-Path -LiteralPath $VenvPy)) { throw 'venv creation did not produce python.exe' }
        OK '.venv created'
    } catch {
        Err "Could not create the virtual environment: $($_.Exception.Message)"
    }
}

# ------------------------------------------------- Step 4: pip packages
Head 4 'Python packages (requirements.txt)'
if (Test-Path -LiteralPath $VenvPy) {
    $code = Invoke-Pip @('install', '--upgrade', 'pip', 'setuptools', 'wheel')
    if ($code -ne 0) { Warn "Could not upgrade pip (exit $code). Continuing." }

    $packages = @(Get-Content -LiteralPath $ReqsFile |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith('#') })

    $code = Invoke-Pip (@('install') + $packages)
    if ($code -eq 0) {
        OK "All $($packages.Count) packages installed"
    } else {
        Warn "Batch install failed (exit $code). Checking each package so the exact failure is reported..."
        $failed = @()
        foreach ($pkg in $packages) {
            $c = Invoke-Pip @('install', $pkg)
            if ($c -eq 0) { OK $pkg }
            else { Err "Package could not be installed: $pkg"; $failed += $pkg }
        }
        if ($failed.Count -eq 0) { OK 'All packages ended up installing on the second pass' }
    }

    # Final import check so a half-installed environment is caught now.
    Info '    Verifying imports...'
    & $VenvPy -c "import PIL, numpy, moviepy, tkinter, tkinterdnd2; import cv2, onnxruntime"
    if ($LASTEXITCODE -eq 0) { OK 'Core imports work' }
    else { Warn 'Some packages failed to import (see the messages above). The app may not start.' }
} else {
    Err 'Skipping packages because .venv is missing.'
}

# ------------------------------------------------- Step 5: FFmpeg
Head 5 'FFmpeg (ffmpeg.exe + ffprobe.exe)'
$needFF = $true
$sysFF = Test-Command 'ffmpeg'
$sysFP = Test-Command 'ffprobe'
if ($sysFF -and $sysFP) {
    Warn 'FFmpeg is already on PATH - the app will use that one (no download).'
    $needFF = $false
}
$localFFexists = (Test-Path -LiteralPath (Join-Path $FFmpegDir 'ffmpeg.exe')) -and (Test-Path -LiteralPath (Join-Path $FFmpegDir 'ffprobe.exe')) -and (Test-Path -LiteralPath (Join-Path $FFmpegDir 'ffplay.exe'))
if ($localFFexists) {
    OK 'Local ffmpeg folder already present'
    $needFF = $false
}
if ($needFF) {
    $zip = Join-Path $env:TEMP 'ffmpeg-essentials.zip'
    $extract = Join-Path $env:TEMP 'ffmpeg-extract'
    try {
        Download-File -Url $FFmpegUrl -Dest $zip -Name 'FFmpeg (~106 MB)'
        Info '    Extracting ...'
        if (Test-Path -LiteralPath $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
        Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
        $ff = Get-ChildItem -LiteralPath $extract -Recurse -Filter 'ffmpeg.exe'  | Select-Object -First 1
        $fp = Get-ChildItem -LiteralPath $extract -Recurse -Filter 'ffprobe.exe' | Select-Object -First 1
        $fpl = Get-ChildItem -LiteralPath $extract -Recurse -Filter 'ffplay.exe' | Select-Object -First 1
        if (-not $ff -or -not $fp) { throw 'ffmpeg.exe / ffprobe.exe were not found inside the archive.' }
        New-Item -ItemType Directory -Force -Path $FFmpegDir | Out-Null
        Copy-Item -LiteralPath $ff.FullName -Destination (Join-Path $FFmpegDir 'ffmpeg.exe')  -Force
        Copy-Item -LiteralPath $fp.FullName -Destination (Join-Path $FFmpegDir 'ffprobe.exe') -Force
        if ($fpl) { Copy-Item -LiteralPath $fpl.FullName -Destination (Join-Path $FFmpegDir 'ffplay.exe') -Force }
        else { Warn 'ffplay.exe was not in the archive; the in-editor Play button will fall back to the default player.' }
        OK 'FFmpeg installed into .\ffmpeg'
    } catch {
        Err "FFmpeg download/install failed: $($_.Exception.Message)"
        Warn 'Without FFmpeg the app opens but cannot export video. Re-run install.bat, or install FFmpeg manually and add it to PATH.'
    } finally {
        Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $extract -Recurse -Force -ErrorAction SilentlyContinue
    }
}
$localFF = Join-Path $FFmpegDir 'ffmpeg.exe'
if (Test-Path -LiteralPath $localFF) {
    try {
        & $localFF -version | Out-Null
        if ($LASTEXITCODE -eq 0) { OK 'ffmpeg runs' } else { Warn 'ffmpeg exists but did not run correctly' }
    } catch { Warn "Could not run ffmpeg: $($_.Exception.Message)" }
}

# ------------------------------------------------- Step 6: launcher
Head 6 'Launcher and shortcut'
if (Test-Path -LiteralPath $RunBat) {
    OK 'run.bat found'
} else {
    Warn 'run.bat is missing - you can start the app with:  .venv\Scripts\python.exe "slideshow_app v4.py"'
}
try {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut((Join-Path $desktop 'Slideshow Video Creator.lnk'))
    $lnk.TargetPath = $RunBat
    $lnk.WorkingDirectory = $AppDir
    $lnk.Description = 'Slideshow Video Creator Pro'
    $lnk.Save()
    OK 'Desktop shortcut created'
} catch {
    Warn "Could not create a desktop shortcut: $($_.Exception.Message)"
}

# ====================================================================
Write-Host ""
Write-Host "==================== SUMMARY ====================" -ForegroundColor White
Info "Python : $(if ($python) { $python } else { 'NOT INSTALLED' })"
Info "Venv   : $(if (Test-Path -LiteralPath $VenvPy) { $VenvPy } else { 'MISSING' })"
Info "FFmpeg : $(if (Test-Path -LiteralPath (Join-Path $FFmpegDir 'ffmpeg.exe')) { (Join-Path $FFmpegDir 'ffmpeg.exe') } elseif ($sysFF) { 'system PATH' } else { 'MISSING' })"

if ($script:Warnings.Count -gt 0) {
    Write-Host ""
    Write-Host "Warnings:" -ForegroundColor Yellow
    $script:Warnings | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
}
if ($script:Failures.Count -gt 0) {
    Write-Host ""
    Write-Host "Errors:" -ForegroundColor Red
    $script:Failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "Installation finished WITH ERRORS. Read the list above." -ForegroundColor Red
    Write-Host "Full log: $LogFile"
    exit 1
}

Write-Host ""
Write-Host "Installation completed successfully!" -ForegroundColor Green
Write-Host "Start the app with run.bat (or the desktop shortcut)." -ForegroundColor Green
Write-Host "Optional: in the app, Settings -> 'Erase objects (AI model)' downloads the 198 MB model the first time."
Write-Host "Full log: $LogFile"
exit 0
