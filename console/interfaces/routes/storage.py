"""数据库状态和采集记录。页面不直接查库。"""
from fastapi import APIRouter, Query, Request

from ops.application.storage_status import overview

router = APIRouter(prefix="/admin/storage", include_in_schema=False)


def _store(request):
    store = getattr(request.app.state, "store", None)
    if store is None:
        from ops.storage import CollectStore
        store = CollectStore(request.app.state.node_id)
        request.app.state.store = store
    return store


@router.get("/")
def storage(request: Request):
    return overview(request.app.state.node_id)


@router.get("/runs")
def runs(
    request: Request,
    crawler: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
):
    return _store(request).page_runs(crawler, page, size)
