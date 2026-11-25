"""启动管理台。同一进程里带开放查询和 Swagger。"""
import logging

logger = logging.getLogger("console")


def serve(host, port, node_id="local-1"):
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("还没有安装 FastAPI。在 data-foundation 下执行：pip install fastapi uvicorn") from exc
    from console.interfaces.app import create_app
    logger.info("管理台：http://%s:%s/", host, port)
    logger.info("Swagger：http://%s:%s/docs", host, port)
    uvicorn.run(create_app(node_id), host=host, port=port, log_level="info")
