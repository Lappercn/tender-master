"""节点监控的用户接口。本机配置和进程数量来自运行管理的应用服务。"""
from fastapi import APIRouter

from collect.application.sessions import running_sources
from ops.application.machine import browser_process_count, host_snapshot
from ops.nodes import load_nodes

router = APIRouter(prefix="/admin/nodes", include_in_schema=False)

ROLE_NAMES = {"master": "主节点", "worker": "采集", "storage": "存储"}


@router.get("/")
def nodes():
    running = running_sources()
    return {
        "host": host_snapshot(),
        "browsers": browser_process_count(),
        "crawlers": running,
        "crawlerCount": len(running),
        "nodes": [_node(item) for item in load_nodes()],
    }


def _node(item):
    roles = [ROLE_NAMES.get(role, role) for role in item.get("roles") or []]
    accept = item.get("accept") or []
    return {
        "id": item.get("node_id"),
        "roles": roles,
        "accept": "全部源头" if "*" in accept else "、".join(accept) or "不接采集",
    }
