"""本机状态。给管理台看配置、内存和已经拉起的浏览器数量。"""
import os
import platform
import socket
import subprocess
import time

_CACHE = {"at": 0.0, "browsers": 0}


def host_snapshot():
    memory = _memory()
    return {
        "hostname": socket.gethostname(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor() or platform.machine(),
        "cpuCount": os.cpu_count() or 0,
        "python": platform.python_version(),
        "memory": memory,
    }


def browser_process_count():
    now = time.time()
    if now - _CACHE["at"] < 5:
        return _CACHE["browsers"]
    count = _count_marked()
    _CACHE["at"] = now
    _CACHE["browsers"] = count
    return count


def _memory():
    if os.name != "nt":
        return {"total": 0, "used": 0, "available": 0, "percent": 0}
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    total = int(status.ullTotalPhys)
    available = int(status.ullAvailPhys)
    return {
        "total": total,
        "used": total - available,
        "available": available,
        "percent": int(status.dwMemoryLoad),
    }


def _count_marked():
    if os.name != "nt":
        return 0
    script = (
        "(Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -and $_.CommandLine -like '*six-chrome-*' }).Count"
    )
    try:
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", script],
            stderr=subprocess.DEVNULL,
            timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    text = output.decode(errors="replace").strip()
    return int(text) if text.isdigit() else 0
