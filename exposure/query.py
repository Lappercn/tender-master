"""对外查询。现在是程序接口，后面可以套一层 HTTP，不必改采集。"""


class CollectQuery:
    def __init__(self, store, queue=None):
        self.store = store
        self.queue = queue

    def summary(self):
        return {
            "online": self.store.online,
            "reason": self.store.reason,
            "counts": self.store.counts() if self.store.online else {},
            "tasks": self.queue.counts() if self.queue else {},
            "runs": self.store.recent_runs(limit=8),
            "nodes": [_node(item) for item in (self.queue.list_nodes() if self.queue else [])],
        }


def _node(item):
    return {
        "nodeId": item.get("_id"),
        "roles": item.get("roles") or [],
        "accept": item.get("accept") or [],
        "mode": item.get("mode"),
        "status": item.get("status"),
        "lastSeen": item.get("lastSeen"),
    }
