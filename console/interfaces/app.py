"""管理台的用户接口。页面是独立的 Vue 工程，这里只提供接口，并在构建完成后托管静态文件。"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from console.interfaces.routes.collecting import router as collecting_router
from console.interfaces.routes.nodes import router as nodes_router
from console.interfaces.routes.notices import router as notices_router
from console.interfaces.routes.storage import router as storage_router
from serve.interfaces.app import create_app as create_query_app

DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
API_ROOTS = {"api", "admin", "docs", "redoc", "openapi.json"}


def create_app(node_id):
    app = create_query_app(node_id)
    app.title = "六张网管理台"
    app.include_router(collecting_router)
    app.include_router(nodes_router)
    app.include_router(storage_router)
    app.include_router(notices_router)

    @app.get("/", include_in_schema=False)
    def index():
        return _page("")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend(full_path: str):
        if full_path.split("/", 1)[0] in API_ROOTS:
            raise HTTPException(404, "没有这个页面")
        return _page(full_path)

    return app


def _page(full_path):
    index = DIST / "index.html"
    if not index.is_file():
        return HTMLResponse("前端还没构建。进入 console/web，先 npm install，再 npm run build。", status_code=503)
    if full_path:
        target = (DIST / full_path).resolve()
        try:
            target.relative_to(DIST.resolve())
        except ValueError:
            return FileResponse(index)
        if target.is_file():
            return FileResponse(target)
    return FileResponse(index)
