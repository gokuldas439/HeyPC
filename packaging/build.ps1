# Builds build\installer\Jarvis-Setup.exe from the source and the models folder.
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"
$compiler = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $compiler) { throw "Inno Setup 6 is required: winget install JRSoftware.InnoSetup" }

& $python -c "from jarvis.tray import draw_icon; draw_icon(256).save('packaging/jarvis.ico', sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])"
if ($LASTEXITCODE -ne 0) { throw "icon failed" }

& $python -m PyInstaller --noconfirm --clean --windowed --onedir --name Jarvis `
    --icon (Join-Path $root "packaging\jarvis.ico") `
    --distpath build\dist --workpath build\work --specpath build `
    --paths $root `
    --collect-all sherpa_onnx --collect-binaries onnxruntime --collect-data openwakeword `
    --collect-all kokoro_onnx --collect-all espeakng_loader --collect-all phonemizer --collect-all language_tags --collect-all segments `
    --collect-all edge_tts --collect-all soundfile --collect-binaries _soundfile_data --collect-data certifi `
    --hidden-import pystray._win32 --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 `
    --hidden-import jarvis.main --hidden-import jarvis.settings_ui --hidden-import jarvis.setup_ui --hidden-import jarvis.tray `
    packaging\launch.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

& $compiler packaging\jarvis.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Output "Installer: $(Join-Path $root 'build\installer\Jarvis-Setup.exe')"
