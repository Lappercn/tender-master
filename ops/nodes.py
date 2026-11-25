"""节点配置。不写 nodes.json 时，本机同时当主节点、采集节点和存储节点。"""
import json
import os

import config


def local_node(node_id=None):
    return {
        "node_id": node_id or config.NODE_ID or "local-1",
        "roles": ["master", "worker", "storage"],
        "accept": ["*"],
        "headless": None,
        "browser": None,
        "fingerprint": None,
        "user_agent": None,
        "window": None,
    }


def load_nodes(path=None):
    path = path if path is not None else config.NODE_FILE
    if not path:
        default_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nodes.json")
        path = default_path if os.path.exists(default_path) else ""
    if not path or not os.path.exists(path):
        return [local_node()]
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    nodes = data.get("nodes") or []
    if not nodes:
        raise ValueError("nodes.json 里没有节点")
    cleaned = []
    for item in nodes:
        node = local_node(item.get("node_id"))
        node.update(item)
        node["roles"] = list(item.get("roles") or node["roles"])
        if "accept" in item:
            node["accept"] = list(item.get("accept") or [])
        if not node["node_id"]:
            raise ValueError("节点缺少 node_id")
        cleaned.append(node)
    return cleaned


def find_node(nodes, node_id):
    for node in nodes:
        if node["node_id"] == node_id:
            return node
    raise KeyError(f"没有这个节点：{node_id}")


def is_worker(node):
    return "worker" in node.get("roles", [])


def node_accepts(node, crawler_id):
    accept = node.get("accept") or []
    return "*" in accept or crawler_id in accept
