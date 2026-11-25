"""公告维护和采集记录。不出现在对外 Swagger 里。"""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ops.application.notices import change_notice, create_notice, remove_notice
from serve.application.query import read_notice, search_net

router = APIRouter(prefix="/admin/notices", include_in_schema=False)


class NoticeBody(BaseModel):
    sourceId: str
    title: str
    url: str
    createTime: str
    detailText: str = ""
    channel: str = ""
    projectCode: str = ""
    siteNoticeId: str = ""


class NoticePatch(BaseModel):
    noticeType: str | None = None
    area: str | None = None
    purchaser: str | None = None
    projectCode: str | None = None
    projectStatus: str | None = None
    budget: str | None = None
    category: str | None = None


def _store(request):
    store = getattr(request.app.state, "store", None)
    if store is None:
        from ops.storage import CollectStore
        store = CollectStore(request.app.state.node_id)
        request.app.state.store = store
    return store


def _fail(exc):
    text = exc.args[0] if getattr(exc, "args", None) else "操作没有完成"
    if isinstance(exc, KeyError):
        raise HTTPException(404, text) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(400, text) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(503, text) from exc
    raise exc


@router.get("/")
def notices(
    request: Request,
    net: str = "",
    q: str = "",
    noticeType: str = "",
    area: str = "",
    source: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
):
    try:
        return search_net(_store(request), net or "all", q, noticeType, area, source, page, size)
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)


@router.get("/{source_id}/{content_id}")
def notice(source_id: str, content_id: str, request: Request):
    try:
        found = read_notice(_store(request), "all", content_id, source_id)
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)
    if not found:
        raise HTTPException(404, "没有这条公告")
    return found


@router.post("/")
def add_notice(body: NoticeBody, request: Request):
    try:
        return create_notice(_store(request), request.app.state.node_id, body.model_dump())
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)


@router.put("/{source_id}/{content_id}")
def edit_notice(source_id: str, content_id: str, body: NoticePatch, request: Request):
    try:
        return change_notice(_store(request), source_id, content_id, body.model_dump())
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)


@router.delete("/{source_id}/{content_id}")
def drop_notice(source_id: str, content_id: str, request: Request):
    try:
        return remove_notice(_store(request), source_id, content_id)
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)
