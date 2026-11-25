"""开放查询应用。文档在 /docs，这是给调用方看的 Swagger。"""
from fastapi import FastAPI

from serve.interfaces.routes import router


def create_app(node_id):
    app = FastAPI(
        title="六张网开放查询",
        version="1.0.0",
        description=(
            "按六张网提供查询。新型电网只有一个接口，"
            "国家电网和南方电网都从这里查，不按网站拆成两套接口。"
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.node_id = node_id
    app.state.store = None
    app.include_router(router)
    return app
