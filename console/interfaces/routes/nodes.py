"""分布式节点与集群任务调度的管理台接口。"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ops.application import cluster
from ops.storage import CollectStore

router = APIRouter(prefix="/admin/nodes", include_in_schema=False)


class NodeConfigBody(BaseModel):
    node_id: str
    roles: list[str] = Field(default_factory=lambda: ["worker"])
    accept: list[str] = Field(default_factory=lambda: ["*"])
    headless: bool = True
    browser: str = "undetected"
    fingerprint: str = "fixed"


class DispatchBody(BaseModel):
    lookbackDays: int = 14
    maxPages: int = 40


class DaemonBody(BaseModel):
    role: str
    nodeId: str = ""


class BreakerResetBody(BaseModel):
    nodeId: str
    crawlerId: str = ""


class ScheduleBody(BaseModel):
    crawlerId: str
    intervalMinutes: int | None = None
    lookbackDays: int | None = None
    enabled: bool | None = None


def _store(request: Request):
    store = getattr(request.app.state, "store", None)
    if store is None:
        store = CollectStore(request.app.state.node_id)
        request.app.state.store = store
    return store


def _fail(exc):
    text = exc.args[0] if getattr(exc, "args", None) else str(exc) or "操作失败"
    if isinstance(exc, KeyError):
        raise HTTPException(404, text) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(400, text) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(503, text) from exc
    raise exc


@router.get("/")
def nodes(request: Request):
    return cluster.cluster_snapshot(_store(request), request.app.state.node_id)


@router.post("/config")
def save_node(body: NodeConfigBody):
    try:
        return cluster.save_node_config(body.model_dump())
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)


@router.delete("/config/{node_id}")
def delete_node(node_id: str):
    try:
        return cluster.remove_node_config(node_id)
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)


@router.post("/dispatch")
def dispatch(body: DispatchBody, request: Request):
    try:
        return cluster.dispatch_tasks(_store(request), body.lookbackDays, body.maxPages)
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)


@router.post("/recover")
def recover(request: Request):
    try:
        return cluster.recover_expired_tasks(_store(request))
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)


@router.post("/tasks/clear")
def clear_tasks(request: Request, status: str = ""):
    try:
        return cluster.clear_queue_tasks(_store(request), status)
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)


@router.post("/work-once")
def work_once(request: Request, nodeId: str = ""):
    try:
        return cluster.run_worker_once(nodeId or request.app.state.node_id)
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)


@router.post("/breaker/reset")
def reset_breaker(body: BreakerResetBody, request: Request):
    try:
        return cluster.reset_node_breaker(_store(request), body.nodeId, body.crawlerId)
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)


@router.put("/schedules")
def update_schedule(body: ScheduleBody, request: Request):
    try:
        return cluster.update_schedule(
            _store(request),
            body.crawlerId,
            body.intervalMinutes,
            body.lookbackDays,
            body.enabled,
        )
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)


@router.post("/daemons/start")
def start_daemon(body: DaemonBody, request: Request):
    try:
        return cluster.start_daemon(body.role, body.nodeId or request.app.state.node_id)
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)


@router.post("/daemons/stop")
def stop_daemon(body: DaemonBody, request: Request):
    try:
        return cluster.stop_daemon(body.role, body.nodeId or request.app.state.node_id)
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)
