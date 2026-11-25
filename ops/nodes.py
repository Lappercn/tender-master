"""节点配置。不写 nodes.json 时，本机同时当主节点、采集节点和存储节点。"""
import json
import os
import re

import config

VALID_ROLES = ("master", "worker", "storage")
NODE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}$")


def default_node_file():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nodes.json")


def local_node(node_id=None):
    return {
        "node_id": node_id or config.NODE_ID or "local-1",
        "roles": ["master", "worker", "storage"],
        "accept": ["*"],
        "headless": True if config.CRAWL_HEADLESS else False,
        "browser": config.CRAWL_BROWSER or "undetected",
        "fingerprint": config.CRAWL_FINGERPRINT or "fixed",
        "user_agent": None,
        "window": None,
    }


def normalize_node(item):
    raw_id = str((item or {}).get("node_id") or (item or {}).get("id") or "").strip()
    if not raw_id:
        raise ValueError("节点缺少 node_id")
    if not NODE_ID_PATTERN.fullmatch(raw_id):
        raise ValueError(f"节点编号不合法：{raw_id}")
    base = local_node(raw_id)
    base.update(item or {})
    base["node_id"] = raw_id
    roles = [r for r in (item.get("roles") or base["roles"]) if r in VALID_ROLES]
    if not roles:
        raise ValueError("节点至少需要一个职责（master / worker / storage）")
    base["roles"] = roles
    if "accept" in (item or {}):
        accept = [str(a).strip() for a in (item.get("accept") or []) if str(a).strip()]
        base["accept"] = ["*"] if "*" in accept else accept
    if base.get("browser") not in ("undetected", "selenium", None):
        base["browser"] = "undetected"
    if base.get("fingerprint") not in ("fixed", "rotate", None):
        base["fingerprint"] = "fixed"
    if base.get("headless") is not None:
        base["headless"] = bool(base["headless"])
    return base


def load_nodes(path=None):
    path = path if path is not None else config.NODE_FILE
    if not path:
        candidate = default_node_file()
        path = candidate if os.path.exists(candidate) else ""
    if not path or not os.path.exists(path):
        return [local_node()]
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    nodes = data.get("nodes") or []
    if not nodes:
        raise ValueError("nodes.json 里没有节点")
    return [normalize_node(item) for item in nodes]


def save_nodes(nodes, path=None):
    target = path or config.NODE_FILE or default_node_file()
    cleaned = [normalize_node(item) for item in (nodes or [])]
    if not cleaned:
        raise ValueError("至少需要保留一个节点")
    seen = set()
    for node in cleaned:
        if node["node_id"] in seen:
            raise ValueError(f"重复的节点编号：{node['node_id']}")
        seen.add(node["node_id"])
    with open(target, "w", encoding="utf-8") as handle:
        json.dump({"nodes": cleaned}, handle, ensure_ascii=False, indent=2)
    return cleaned


def upsert_node(payload, path=None):
    node = normalize_node(payload)
    current = load_nodes(path)
    replaced = False
    out = []
    for item in current:
        if item["node_id"] == node["node_id"]:
            out.append(node)
            replaced = True
        else:
            out.append(item)
    if not replaced:
        out.append(node)
    return save_nodes(out, path)


def delete_node(node_id, path=None):
    current = load_nodes(path)
    remaining = [item for item in current if item["node_id"] != node_id]
    if len(remaining) == len(current):
        raise KeyError(f"没有这个节点：{node_id}")
    if not remaining:
        raise ValueError("不能删除最后一个节点")
    return save_nodes(remaining, path)


def find_node(nodes, node_id):
    for node in nodes:
        if node["node_id"] == node_id:
            return node
    raise KeyError(f"没有这个节点：{node_id}")


def is_worker(node):
    return "worker" in node.get("roles", [])


def is_master(node):
    return "master" in node.get("roles", [])


def node_accepts(node, crawler_id):
    accept = node.get("accept") or []
    return "*" in accept or crawler_id in accept
