"""分布式节点与集群任务的运维应用服务。整合配置节点、在线心跳、熔断状态、任务队列与后台守护进程。"""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import config
from collect.application.sessions import running_sources
from collect.infrastructure.process_guard import kill_tree
from collect.sources.registry import load_sources, source_map
from crawl.catalog import SPECS
from ops.application.machine import browser_process_count, host_snapshot
from ops.nodes import delete_node, find_node, load_nodes, upsert_node
from ops.plan import default_jobs
from ops.storage import CollectStore
from ops.tasks import TaskQueue, safe_queue, utcnow

ROOT = Path(__file__).resolve().parents[2]
DAEMONS = ROOT / "runtime" / "daemons"
LOGS = ROOT / "runtime" / "logs"
CREATE_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
ROLE_NAMES = {"master": "主节点", "worker": "采集", "storage": "存储"}
ONLINE_SECONDS = 180


def cluster_snapshot(store=None, node_id=None):
    current_id = node_id or config.NODE_ID or "local-1"
    store = store or CollectStore(current_id)
    queue = safe_queue(store)
    configured = load_nodes()
    known_sources = source_map()
    heartbeats = {}
    breakers = {}
    task_counts = {}
    tasks = []
    schedules = []
    if queue:
        try:
            queue.seed_schedules(SPECS)
            for row in queue.list_nodes():
                heartbeats[row["_id"]] = row
            breakers = queue.list_breakers()
            task_counts = queue.counts()
            tasks = queue.list_tasks(limit=30)
            for item in queue.schedule_map().values():
                last = item.get("lastEnqueuedAt")
                if isinstance(last, datetime.datetime):
                    last_str = last.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                else:
                    last_str = ""
                schedules.append({
                    "crawlerId": item.get("crawlerId") or item.get("_id"),
                    "label": item.get("label") or item.get("_id"),
                    "intervalMinutes": int(item.get("intervalMinutes") or 60),
                    "lookbackDays": int(item.get("lookbackDays") or 14),
                    "enabled": bool(item.get("enabled", True)),
                    "lastEnqueuedAt": last_str,
                })
        except Exception:
            pass

    now = utcnow()
    nodes_out = []
    seen_ids = set()
    for item in configured:
        nid = item.get("node_id")
        seen_ids.add(nid)
        hb = heartbeats.get(nid) or {}
        nodes_out.append(_format_node(item, hb, breakers.get(nid) or {}, known_sources, current_id, now))

    for nid, hb in heartbeats.items():
        if nid in seen_ids:
            continue
        synthetic = {
            "node_id": nid,
            "roles": hb.get("roles") or ["worker"],
            "accept": hb.get("accept") or ["*"],
            "headless": True,
            "browser": "undetected",
            "fingerprint": "fixed",
        }
        nodes_out.append(_format_node(synthetic, hb, breakers.get(nid) or {}, known_sources, current_id, now, configured=False))

    running = running_sources()
    return {
        "currentNodeId": current_id,
        "storageOnline": store.online,
        "storageReason": store.reason,
        "host": host_snapshot(),
        "browsers": browser_process_count(),
        "crawlers": running,
        "crawlerCount": len(running),
        "daemons": daemon_status(current_id),
        "nodes": nodes_out,
        "taskCounts": task_counts,
        "tasks": tasks,
        "schedules": schedules,
        "sources": [{"id": s.id, "name": s.name, "netName": s.net_name} for s in load_sources()],
    }


def _format_node(item, hb, breaker_snap, known_sources, current_id, now, configured=True):
    nid = item.get("node_id")
    raw_roles = list(item.get("roles") or [])
    roles_label = [ROLE_NAMES.get(role, role) for role in raw_roles]
    accept_list = list(item.get("accept") or [])
    if "*" in accept_list:
        accept_label = "全部源头"
    elif not accept_list:
        accept_label = "不接采集"
    else:
        accept_label = "、".join(known_sources[s].name if s in known_sources else s for s in accept_list)

    last_seen = hb.get("lastSeen")
    last_seen_str = ""
    online = False
    if isinstance(last_seen, datetime.datetime):
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=datetime.timezone.utc)
        online = (now - last_seen).total_seconds() <= ONLINE_SECONDS
        last_seen_str = last_seen.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    elif nid == current_id:
        online = True
        last_seen_str = "本机当前节点"

    open_until = breaker_snap.get("openUntil") or {}
    failures = breaker_snap.get("failures") or {}
    active_breakers = []
    for cid, until_iso in open_until.items():
        if not until_iso:
            continue
        try:
            moment = datetime.datetime.fromisoformat(until_iso.replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=datetime.timezone.utc)
            if moment > now:
                cname = known_sources[cid].name if cid in known_sources else cid
                active_breakers.append({
                    "crawlerId": cid,
                    "crawlerName": cname,
                    "until": moment.astimezone().strftime("%H:%M:%S"),
                    "failures": int(failures.get(cid) or 0),
                })
        except ValueError:
            continue

    return {
        "id": nid,
        "isLocal": nid == current_id,
        "configured": configured,
        "roles": roles_label,
        "rawRoles": raw_roles,
        "accept": accept_label,
        "rawAccept": accept_list,
        "headless": item.get("headless") is not False,
        "browser": item.get("browser") or "undetected",
        "fingerprint": item.get("fingerprint") or "fixed",
        "status": "在线" if online else ("离线" if last_seen_str else "待命"),
        "online": online,
        "mode": hb.get("mode") or "",
        "lastSeen": last_seen_str or "—",
        "breakers": active_breakers,
        "failureCounts": failures,
    }


def save_node_config(payload):
    upsert_node(payload)
    return {"ok": True, "message": f"节点 {payload.get('node_id') or payload.get('id')} 配置已保存"}


def remove_node_config(node_id):
    delete_node(node_id)
    return {"ok": True, "message": f"节点 {node_id} 已移除"}


def dispatch_tasks(store, lookback_days=None, max_pages=None):
    queue = TaskQueue(store)
    nodes = load_nodes()
    jobs = default_jobs(
        nodes,
        int(lookback_days or config.CRAWL_LOOKBACK_DAYS),
        int(max_pages or config.CRAWL_MAX_PAGES),
    )
    created = 0
    for job in jobs:
        if queue.enqueue(job, "console"):
            created += 1
    return {
        "ok": True,
        "created": created,
        "total": len(jobs),
        "message": f"已向集群队列派发 {created} 个新栏目任务（共 {len(jobs)} 个栏目，排队中不重复投入）",
    }


def recover_expired_tasks(store):
    queue = TaskQueue(store)
    recovered = queue.recover()
    return {"ok": True, "recovered": recovered, "message": f"已检查并回收 {recovered} 条失联超时任务"}


def clear_queue_tasks(store, status=""):
    queue = TaskQueue(store)
    removed = queue.clear_tasks(status)
    return {"ok": True, "removed": removed, "message": f"已清理 {removed} 条任务记录"}


def reset_node_breaker(store, node_id, crawler_id=""):
    queue = TaskQueue(store)
    queue.clear_breaker(node_id, crawler_id)
    return {"ok": True, "message": f"已解除节点 {node_id} 的熔断冷却"}


def update_schedule(store, crawler_id, interval_minutes=None, lookback_days=None, enabled=None):
    queue = TaskQueue(store)
    queue.seed_schedules(SPECS)
    queue.set_schedule(crawler_id, interval_minutes, enabled, lookback_days)
    return {"ok": True, "message": "调度计划已更新"}


def run_worker_once(node_id=None):
    target_node = node_id or config.NODE_ID or "local-1"
    nodes = load_nodes()
    find_node(nodes, target_node)
    command = [
        sys.executable,
        str(ROOT / "manage.py"),
        "--node",
        target_node,
        "work",
        "--once",
    ]
    LOGS.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    with open(LOGS / f"worker_{target_node}.log", "a", encoding="utf-8") as handle:
        proc = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=CREATE_GROUP,
        )
    return {"ok": True, "pid": proc.pid, "message": f"节点 {target_node} 已在后台拉起单次领任务进程 ({proc.pid})"}


def daemon_status(node_id=None):
    target_node = node_id or config.NODE_ID or "local-1"
    out = {}
    for role in ("master", "work"):
        info = _read_daemon(role, target_node)
        pid = info.get("pid")
        alive = bool(pid and _alive(pid))
        out[role] = {
            "role": role,
            "nodeId": target_node,
            "running": alive,
            "pid": int(pid) if alive else None,
        }
    return out


def start_daemon(role, node_id=None):
    if role not in ("master", "work"):
        raise ValueError("守护进程角色只能是 master 或 work")
    target_node = node_id or config.NODE_ID or "local-1"
    nodes = load_nodes()
    find_node(nodes, target_node)
    current = daemon_status(target_node).get(role) or {}
    if current.get("running"):
        return {"ok": False, "message": f"{role} 守护进程已经在运行（PID {current['pid']}）"}
    command = [
        sys.executable,
        str(ROOT / "manage.py"),
        "--node",
        target_node,
        role,
    ]
    LOGS.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    with open(LOGS / f"daemon_{role}_{target_node}.log", "a", encoding="utf-8") as handle:
        proc = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=CREATE_GROUP,
        )
    DAEMONS.mkdir(parents=True, exist_ok=True)
    _daemon_path(role, target_node).write_text(
        json.dumps({"pid": proc.pid, "role": role, "nodeId": target_node}),
        encoding="utf-8",
    )
    label = "主节点定时调度器" if role == "master" else "采集工作节点守护进程"
    return {"ok": True, "pid": proc.pid, "message": f"{label}已启动（PID {proc.pid}）"}


def stop_daemon(role, node_id=None):
    if role not in ("master", "work"):
        raise ValueError("守护进程角色只能是 master 或 work")
    target_node = node_id or config.NODE_ID or "local-1"
    info = _read_daemon(role, target_node)
    pid = info.get("pid")
    if pid:
        kill_tree(pid)
    path = _daemon_path(role, target_node)
    if path.is_file():
        path.unlink()
    label = "主节点定时调度器" if role == "master" else "采集工作节点守护进程"
    return {"ok": True, "message": f"{label}已关闭"}


def _daemon_path(role, node_id):
    return DAEMONS / f"{role}_{node_id}.json"


def _read_daemon(role, node_id):
    path = _daemon_path(role, node_id)
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
        capture_output=True,
        text=True,
        check=False,
    )
    return str(int(pid)) in (result.stdout or "")
