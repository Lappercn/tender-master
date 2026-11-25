"""采集的应用服务。启动、关闭、浏览器配置和日志都从这里走，页面不直接碰进程。"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import config
from collect.infrastructure.process_guard import forget, kill_tree, pids_with_marker, read
from collect.sources.registry import get_source, load_sources

ROOT = Path(__file__).resolve().parents[2]
SESSIONS = ROOT / "runtime" / "sessions"
PROFILES = ROOT / "runtime" / "profiles"
LOGS = ROOT / "runtime" / "logs"
CREATE_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
_HANDLES = {}


def list_views():
    return [_view(item) for item in load_sources()]


def browser_profile(source_id):
    get_source(source_id)
    saved = _read_json(PROFILES / f"{source_id}.json")
    profile = _defaults()
    for key in profile:
        if key in saved:
            profile[key] = saved[key]
    return profile


def save_browser(source_id, headless, browser, fingerprint, span="14d", pace="normal"):
    get_source(source_id)
    profile = browser_profile(source_id)
    profile["headless"] = bool(headless)
    profile["browser"] = browser if browser in ("undetected", "selenium") else "undetected"
    profile["fingerprint"] = fingerprint if fingerprint in ("fixed", "rotate") else "fixed"
    profile["span"] = _span(span)
    profile["pace"] = pace if pace in ("calm", "normal") else "normal"
    _write_profile(source_id, profile)
    return profile


def apply_collect(span, pace):
    saved = []
    for source in load_sources():
        profile = browser_profile(source.id)
        profile["span"] = _span(span)
        profile["pace"] = pace if pace in ("calm", "normal") else profile.get("pace") or "normal"
        _write_profile(source.id, profile)
        saved.append(source.id)
    return {"ok": True, "span": _span(span), "pace": pace if pace in ("calm", "normal") else "normal", "sources": saved}


def start(source_id):
    get_source(source_id)
    if running_pid(source_id):
        return {"ok": False, "message": "这个源头已经在采集"}
    profile = browser_profile(source_id)
    command = [
        sys.executable, str(ROOT / "manage.py"), "run", source_id,
        "--headless", "1" if profile["headless"] else "0",
        "--browser", profile["browser"],
        "--fingerprint", profile["fingerprint"],
        "--span", profile["span"],
        "--pace", profile["pace"],
    ]
    handle = _open_log(source_id)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=handle,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=CREATE_GROUP,
    )
    SESSIONS.mkdir(parents=True, exist_ok=True)
    (SESSIONS / f"{source_id}.json").write_text(
        json.dumps({"pid": process.pid, "sourceId": source_id}),
        encoding="utf-8",
    )
    return {"ok": True, "message": "已启动", "pid": process.pid}


def stop(source_id):
    get_source(source_id)
    record = read(source_id)
    session = _session(source_id)
    kill_tree(session.get("pid"))
    kill_tree(record.get("pythonPid"))
    seen = set()
    for pid in list(record.get("pids") or []) + pids_with_marker(record.get("marker") or ""):
        if pid in seen:
            continue
        seen.add(pid)
        kill_tree(pid)
    forget(source_id)
    path = SESSIONS / f"{source_id}.json"
    if path.is_file():
        path.unlink()
    handle = _HANDLES.pop(source_id, None)
    if handle:
        handle.close()
    return {"ok": True, "message": "已关闭，并清理了这次拉起的浏览器"}


def read_log(source_id, limit=400):
    get_source(source_id)
    path = LOGS / f"{source_id}.log"
    if not path.is_file():
        return ""
    text = path.read_bytes()[-200000:].decode("utf-8", errors="replace")
    return "\n".join(text.splitlines()[-limit:])


def running_sources():
    rows = []
    for item in load_sources():
        pid = running_pid(item.id)
        if pid:
            rows.append({"id": item.id, "name": item.name, "pid": pid})
    return rows


def running_pid(source_id):
    for pid in (_session(source_id).get("pid"), read(source_id).get("pythonPid")):
        if pid and _alive(pid):
            return int(pid)
    return None


def _view(source):
    pid = running_pid(source.id)
    return {
        "id": source.id,
        "name": source.name,
        "running": bool(pid),
        "pid": pid,
        "browser": browser_profile(source.id),
        "channels": [{"code": channel.code, "name": channel.name} for channel in source.channels],
        "net": source.net,
        "netName": source.net_name,
    }


def _defaults():
    browser = config.CRAWL_BROWSER if config.CRAWL_BROWSER in ("undetected", "selenium") else "undetected"
    fingerprint = config.CRAWL_FINGERPRINT if config.CRAWL_FINGERPRINT in ("fixed", "rotate") else "fixed"
    return {"headless": bool(config.CRAWL_HEADLESS), "browser": browser, "fingerprint": fingerprint, "span": "14d", "pace": "normal"}


def _span(code):
    from crawl.window import hours_of
    try:
        hours_of(code)
    except ValueError:
        return "14d"
    return code


def _write_profile(source_id, profile):
    PROFILES.mkdir(parents=True, exist_ok=True)
    (PROFILES / f"{source_id}.json").write_text(
        json.dumps(profile, ensure_ascii=False),
        encoding="utf-8",
    )


def _open_log(source_id):
    LOGS.mkdir(parents=True, exist_ok=True)
    handle = open(LOGS / f"{source_id}.log", "a", encoding="utf-8")
    handle.write(f"\n---- {datetime.now():%Y-%m-%d %H:%M:%S} 启动 ----\n")
    handle.flush()
    old = _HANDLES.get(source_id)
    if old:
        old.close()
    _HANDLES[source_id] = handle
    return handle


def _session(source_id):
    return _read_json(SESSIONS / f"{source_id}.json")


def _read_json(path):
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _alive(pid):
    if os.name != "nt":
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {int(pid)}"],
        capture_output=True, text=True, check=False,
    )
    return str(int(pid)) in (result.stdout or "")
