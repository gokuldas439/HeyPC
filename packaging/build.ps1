# Builds build\installer\HeyPC-Setup.exe from the source and the models folder.
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

& $python -c "from heypc.tray import draw_icon; draw_icon(256).save('packaging/heypc.ico', sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])"
if ($LASTEXITCODE -ne 0) { throw "icon failed" }

& $python -m PyInstaller --noconfirm --clean --windowed --onedir --name HeyPC `
    --icon (Join-Path $root "packaging\heypc.ico") `
    --distpath build\dist --workpath build\work --specpath build `
    --paths $root `
    --collect-all sherpa_onnx --collect-binaries onnxruntime --collect-data openwakeword `
    --collect-all kokoro_onnx --collect-all espeakng_loader --collect-all phonemizer --collect-all language_tags --collect-all segments `
    --collect-all edge_tts --collect-all soundfile --collect-binaries _soundfile_data --collect-data certifi `
    --hidden-import pystray._win32 --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 `
    --hidden-import heypc.main --hidden-import heypc.settings_ui --hidden-import heypc.setup_ui --hidden-import heypc.download_ui --hidden-import heypc.tray `
    packaging\launch.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

& $compiler packaging\heypc.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Output "Installer: $(Join-Path $root 'build\installer\HeyPC-Setup.exe')"
