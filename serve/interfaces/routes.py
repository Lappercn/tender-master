"""开放查询的用户接口。Swagger 只展示这一层，管理操作不进这份文档。"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from collect.sources.registry import load_sources
from crawl.files import file_key as digest_file
from crawl.files import locate_file
from serve.application.query import describe_nets, read_notice, search_net
from serve.domain.nets import require_open

router = APIRouter(tags=["开放查询"])


def _store(request):
    store = getattr(request.app.state, "store", None)
    if store is None:
        from ops.storage import CollectStore
        store = CollectStore(request.app.state.node_id)
        request.app.state.store = store
    return store


def _fail(exc):
    if isinstance(exc, KeyError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(400, str(exc)) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(503, str(exc)) from exc
    raise exc


@router.get("/api/nets", summary="六张网有哪些开放查询")
def list_nets():
    names = {item.id: item.name for item in load_sources()}
    return {"items": describe_nets(names)}


@router.get("/api/nets/power-grid/notices", summary="查询新型电网公告")
def grid_notices(
    request: Request,
    q: str = Query("", description="关键词。按标题、采购人、项目编号、摘要做包含查询，不会当成正则。"),
    noticeType: str = Query("", description="公告类型，例如招标公告。空着表示不限。"),
    area: str = Query("", description="地区，例如广东。空着表示不限。"),
    source: str = Query("", description="采集源头编号。空着则国家电网和南方电网一起查。"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
):
    try:
        return search_net(_store(request), "power-grid", q, noticeType, area, source, page, size)
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)


@router.get("/api/nets/power-grid/notices/{content_id}", summary="查看一条新型电网公告")
def grid_notice(content_id: str, request: Request, source: str = Query("", description="知道源头时带上，查找更快。")):
    try:
        found = read_notice(_store(request), "power-grid", content_id, source)
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)
    if not found:
        raise HTTPException(404, "没有这条公告")
    return found


@router.get("/api/nets/power-grid/notices/{content_id}/files/{file_key}", summary="下载公告附件")
def grid_file(content_id: str, file_key: str, request: Request, source: str = Query("", description="知道源头时带上。")):
    try:
        net = require_open("power-grid")
        if source and source not in net.source_ids:
            raise ValueError("这个源头不在这张网的查询范围里")
        source_ids = (source,) if source else net.source_ids
        store = _store(request)
        for one in source_ids:
            found = store.get_notice(one, content_id)
            if not found:
                continue
            for item in found.get("files") or []:
                key = item.get("key") or (digest_file(item.get("url") or "") if item.get("url") else "")
                if key != file_key:
                    continue
                path = locate_file(item)
                if path is None:
                    raise HTTPException(404, "附件还没有下载到本地")
                return FileResponse(path, filename=item.get("name") or path.name)
        raise HTTPException(404, "没有这个附件")
    except (KeyError, ValueError, RuntimeError) as exc:
        _fail(exc)
