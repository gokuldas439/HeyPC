"""Controls for the PC itself: lock, power, battery, brightness, Wi-Fi and Bluetooth."""
import ctypes
import subprocess

NO_WINDOW = 0x08000000
SHUTDOWN_DELAY = "5"
BATTERY_UNKNOWN = 255
BRIGHTNESS_STEP = 20
RADIO_NAMES = {"wifi": "WiFi", "bluetooth": "Bluetooth"}
RADIO_SCRIPT = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$generic = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($operation, $type) { $task = $generic.MakeGenericMethod($type).Invoke($null, @($operation)); $task.Wait(-1) | Out-Null; $task.Result }
[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$radio = $radios | Where-Object { $_.Kind -eq '__KIND__' } | Select-Object -First 1
if (-not $radio) { Write-Output 'missing'; exit }
if ('__STATE__') { Await ($radio.SetStateAsync('__STATE__')) ([Windows.Devices.Radios.RadioAccessStatus]) | Write-Output }
else { Write-Output $radio.State }
"""


class _PowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte), ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def _powershell(script: str) -> str:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW, timeout=20,
    )
    return result.stdout.strip()


def lock() -> None:
    ctypes.windll.user32.LockWorkStation()


def sleep_pc() -> None:
    ctypes.windll.powrprof.SetSuspendState(0, 0, 0)


def _shutdown(*flags: str) -> None:
    subprocess.Popen(["shutdown.exe", *flags], creationflags=NO_WINDOW)


def shut_down() -> None:
    _shutdown("/s", "/t", SHUTDOWN_DELAY)


def restart() -> None:
    _shutdown("/r", "/t", SHUTDOWN_DELAY)


def sign_out() -> None:
    _shutdown("/l")


def battery_report() -> str:
    status = _PowerStatus()
    ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))
    if status.BatteryLifePercent == BATTERY_UNKNOWN:
        return "I can't read the battery on this PC."
    charging = " and plugged in" if status.ACLineStatus == 1 else ""
    return f"Battery is at {status.BatteryLifePercent} percent{charging}."


def brightness() -> int | None:
    value = _powershell("(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness | Select-Object -First 1).CurrentBrightness")
    return int(value) if value.isdigit() else None


def set_brightness(percent: int) -> bool:
    percent = max(0, min(percent, 100))
    return _powershell(
        "$m = Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods | Select-Object -First 1; "
        f"Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{{Timeout=[uint32]1; Brightness=[byte]{percent}}} | Out-Null; 'ok'"
    ) == "ok"


def change_brightness(step: int) -> bool:
    current = brightness()
    return current is not None and set_brightness(current + step)


def _radio(kind: str, state: str) -> str:
    return _powershell(RADIO_SCRIPT.replace("__KIND__", RADIO_NAMES[kind]).replace("__STATE__", state))


def radio_state(kind: str) -> str:
    return _radio(kind, "")


def set_radio(kind: str, on: bool) -> bool:
    return _radio(kind, "On" if on else "Off") == "Allowed"
