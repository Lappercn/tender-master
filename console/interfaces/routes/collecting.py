"""采集管理的用户接口。命令走应用服务，不在这里写进程和浏览器细节。"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from collect.application import sessions
from collect.sources.registry import get_source
from crawl.runtime import pace_choices
from crawl.window import span_choices
from ops.storage import CollectStore

router = APIRouter(prefix="/admin/sources", include_in_schema=False)


class BrowserBody(BaseModel):
    headless: bool = True
    browser: str = "undetected"
    fingerprint: str = "fixed"
    span: str = "14d"
    pace: str = "normal"


class CollectBody(BaseModel):
    span: str = "14d"
    pace: str = "normal"


def _missing(exc):
    raise HTTPException(404, str(exc)) from exc


@router.get("/")
def sources():
    return {"items": sessions.list_views(), "spans": span_choices(), "paces": pace_choices()}


@router.post("/apply")
def apply_collect(body: CollectBody):
    return sessions.apply_collect(body.span, body.pace)


@router.post("/{source_id}/start")
def start(source_id: str):
    try:
        return sessions.start(source_id)
    except KeyError as exc:
        _missing(exc)


@router.post("/{source_id}/stop")
def stop(source_id: str):
    try:
        return sessions.stop(source_id)
    except KeyError as exc:
        _missing(exc)


@router.get("/{source_id}/browser")
def browser(source_id: str):
    try:
        return sessions.browser_profile(source_id)
    except KeyError as exc:
        _missing(exc)


@router.put("/{source_id}/browser")
def save_browser(source_id: str, body: BrowserBody):
    try:
        return sessions.save_browser(source_id, body.headless, body.browser, body.fingerprint, body.span, body.pace)
    except KeyError as exc:
        _missing(exc)


@router.get("/{source_id}/logs")
def logs(source_id: str):
    try:
        return {"text": sessions.read_log(source_id)}
    except KeyError as exc:
        _missing(exc)


@router.get("/{source_id}/progress")
def progress(source_id: str, request: Request):
    try:
        get_source(source_id)
    except KeyError as exc:
        _missing(exc)
    store = getattr(request.app.state, "store", None)
    if store is None:
        store = CollectStore(request.app.state.node_id)
        request.app.state.store = store
    return {"items": store.list_progress(source_id)}
