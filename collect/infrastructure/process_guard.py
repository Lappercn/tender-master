"""浏览器进程。程序退出或页面点关闭时，把这次拉起的 Chrome 一并结束。"""
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime" / "browsers"
MARKER = re.compile(r"six-chrome-[A-Za-z0-9_]+")


def remember(source_id, marker, pids):
    if not source_id:
        return
    RUNTIME.mkdir(parents=True, exist_ok=True)
    payload = {
        "sourceId": source_id,
        "pythonPid": os.getpid(),
        "marker": marker,
        "pids": [int(pid) for pid in pids if pid],
    }
    path = RUNTIME / f"{source_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")


def read(source_id):
    path = RUNTIME / f"{source_id}.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def forget(source_id):
    path = RUNTIME / f"{source_id}.json"
    if path.is_file():
        path.unlink()


def kill_tree(pid):
    if not pid:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.kill(int(pid), 15)
    except OSError:
        return


def pids_with_marker(marker):
    marker = marker if MARKER.fullmatch(marker or "") else ""
    if not marker or os.name != "nt":
        return []
    script = (
        "Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.CommandLine -and $_.CommandLine -like '*{marker}*' }} | "
        "ForEach-Object { $_.ProcessId }"
    )
    flags = subprocess.CREATE_NO_WINDOW
    try:
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", script],
            stderr=subprocess.DEVNULL,
            timeout=20,
            creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [int(line) for line in output.decode(errors="replace").split() if line.isdigit()]


_JOBS = {}


def assign_job(pids):
    """放进 Windows 作业。Python 被系统回收时，作业里的 Chrome 会一起退出。"""
    pids = [int(pid) for pid in pids if pid]
    if os.name != "nt" or not pids:
        return None
    try:
        import win32api
        import win32con
        import win32job
    except ImportError:
        return None
    job = None
    try:
        job = win32job.CreateJobObject(None, "")
        info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
        for pid in pids:
            handle = win32api.OpenProcess(
                win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, int(pid),
            )
            try:
                win32job.AssignProcessToJobObject(job, handle)
            finally:
                win32api.CloseHandle(handle)
        return job
    except Exception:
        if job is not None:
            try:
                info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
                flags = info["BasicLimitInformation"]["LimitFlags"]
                info["BasicLimitInformation"]["LimitFlags"] = flags & ~win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
            except Exception:
                return job
            try:
                win32api.CloseHandle(job)
            except Exception:
                return None
        return None


def hold_job(source_id, pids):
    job = assign_job(pids)
    if job is not None:
        _JOBS[source_id] = job
    return job


def release(source_id):
    record = read(source_id)
    for pid in record.get("pids") or []:
        kill_tree(pid)
    for pid in pids_with_marker(record.get("marker") or ""):
        kill_tree(pid)
    forget(source_id)
    job = _JOBS.pop(source_id, None)
    if job is None:
        return
    try:
        import win32api
        win32api.CloseHandle(job)
    except Exception:
        return
