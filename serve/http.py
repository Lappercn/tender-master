"""启动开放查询。默认只听本机，Swagger 在 /docs。"""
import logging

logger = logging.getLogger("serve")


def serve(host, port, node_id):
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("还没有安装 FastAPI。在 data-foundation 下执行：pip install fastapi uvicorn") from exc
    from serve.interfaces.app import create_app
    logger.info("开放查询：http://%s:%s/api/nets", host, port)
    logger.info("Swagger：http://%s:%s/docs", host, port)
    uvicorn.run(create_app(node_id), host=host, port=port, log_level="info")
