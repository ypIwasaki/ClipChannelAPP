param(
    [Parameter(Mandatory=$true)][string]$FFmpegBin,
    [string]$Python = 'python',
    [string]$DenoExe,
    [string]$EcapaModel
)

$ErrorActionPreference = 'Stop'
if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') { throw 'Run this script on Windows.' }
$sourceRoot = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '..')).FullName
$bin = (Resolve-Path $FFmpegBin).Path
foreach ($name in @('ffmpeg.exe', 'ffprobe.exe', 'ffplay.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $bin $name) -PathType Leaf)) { throw "Missing $name in $bin" }
}

$root = Join-Path $env:TEMP ('ClipChannelAPP-build-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceRoot 'clipchannel') -Destination $root -Recurse
Copy-Item -LiteralPath (Join-Path $sourceRoot 'clipchannel_windows.py') -Destination $root
Copy-Item -LiteralPath (Join-Path $sourceRoot 'requirements.txt') -Destination $root
$buildEnv = Join-Path $root '.venv-windows-build'
& $Python -m venv $buildEnv
if ($LASTEXITCODE -ne 0) { throw 'Python venv creation failed.' }
$pipPython = Join-Path $buildEnv 'Scripts\python.exe'
& $pipPython -m pip install -r (Join-Path $root 'requirements.txt') 'yt-dlp-ejs==0.8.0' 'pyinstaller>=6,<7'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if ($EcapaModel) {
    & $pipPython -m pip install 'torch==2.8.0+cpu' 'torchaudio==2.8.0+cpu' --index-url 'https://download.pytorch.org/whl/cpu'
    if ($LASTEXITCODE -ne 0) { throw 'PyTorch CPU installation failed.' }
    & $pipPython -m pip install 'speechbrain==1.1.1' 'soundfile==0.14.0'
    if ($LASTEXITCODE -ne 0) { throw 'SpeechBrain installation failed.' }
}

Push-Location $root
try {
    $arguments = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir', '--name', 'ClipChannelAPP',
        '--collect-all', 'sudachidict_core', '--collect-all', 'sudachipy', '--collect-all', 'yt_dlp_ejs')
    if ($EcapaModel) { $arguments += @('--collect-all', 'speechbrain', '--collect-all', 'torch', '--collect-all', 'torchaudio') }
    $arguments += 'clipchannel_windows.py'
    & $pipPython @arguments
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
} finally { Pop-Location }

$out = Join-Path $root 'dist\ClipChannelAPP'
$tools = Join-Path $out 'tools'
New-Item -ItemType Directory -Path $tools -Force | Out-Null
foreach ($name in @('ffmpeg.exe', 'ffprobe.exe', 'ffplay.exe')) {
    Copy-Item -LiteralPath (Join-Path $bin $name) -Destination $tools -Force
}
$ffmpegLicense = Join-Path (Split-Path $bin) 'LICENSE'
if (Test-Path -LiteralPath $ffmpegLicense -PathType Leaf) {
    $licenses = Join-Path $out 'licenses'
    New-Item -ItemType Directory -Path $licenses -Force | Out-Null
    Copy-Item -LiteralPath $ffmpegLicense -Destination (Join-Path $licenses 'FFmpeg-LICENSE') -Force
}
if ($DenoExe) {
    Copy-Item -LiteralPath (Resolve-Path $DenoExe).Path -Destination (Join-Path $tools 'deno.exe') -Force
}
if ($EcapaModel) {
    $model = (Resolve-Path $EcapaModel).Path
    if (-not (Test-Path -LiteralPath (Join-Path $model 'hyperparams.yaml') -PathType Leaf)) { throw 'Missing ECAPA hyperparams.yaml.' }
    $models = Join-Path $out 'models'
    New-Item -ItemType Directory -Path $models -Force | Out-Null
    Copy-Item -LiteralPath $model -Destination (Join-Path $models 'ecapa') -Recurse
}
$destination = Join-Path $sourceRoot 'dist\ClipChannelAPP'
New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
Copy-Item -LiteralPath $out -Destination (Split-Path $destination) -Recurse -Force
Write-Host "Built $destination\ClipChannelAPP.exe"
