"""开放查询的应用服务。只组装用例，公告怎么匹配写在查询规则里。"""
from serve.domain.nets import all_nets, require_open


def describe_nets(source_names):
    rows = []
    for item in all_nets():
        rows.append({
            "id": item.id,
            "name": item.name,
            "summary": item.summary,
            "open": item.open,
            "path": item.path,
            "sources": [
                {"id": source_id, "name": source_names.get(source_id, source_id)}
                for source_id in item.source_ids
            ],
        })
    return rows


def search_net(store, net_id, text="", notice_type="", area="", source_id="", page=1, size=20):
    net = require_open(net_id)
    if source_id and source_id not in net.source_ids:
        raise ValueError("这个源头不在这张网的查询范围里")
    if not store.online:
        raise RuntimeError(store.reason or "存储未连通")
    page = max(1, int(page or 1))
    size = min(50, max(1, int(size or 20)))
    source_ids = (source_id,) if source_id else net.source_ids
    total = 0
    rows = []
    fetch = page * size
    for one in source_ids:
        found = store.search_notices(one, text, notice_type, area, 1, fetch)
        total += found["total"]
        rows.extend(found["items"])
    rows.sort(key=lambda item: item.get("createTime") or "", reverse=True)
    start = (page - 1) * size
    return {
        "net": net.id,
        "netName": net.name,
        "page": page,
        "size": size,
        "total": total,
        "items": [_view(item) for item in rows[start:start + size]],
    }


def read_notice(store, net_id, content_id, source_id=""):
    net = require_open(net_id)
    if not store.online:
        raise RuntimeError(store.reason or "存储未连通")
    source_ids = (source_id,) if source_id else net.source_ids
    if source_id and source_id not in net.source_ids:
        raise ValueError("这个源头不在这张网的查询范围里")
    for one in source_ids:
        found = store.get_notice(one, content_id)
        if found:
            found.pop("_id", None)
            found["hasRawHtml"] = bool((found.get("detail") or "").strip())
            found.pop("detail", None)
            found["files"] = public_files(content_id, found.get("files"))
            return found
    return None


def public_files(content_id, files):
    """对外只给本站下载地址。对方网站上的原链接留在库里，不拿给演练场。"""
    rows = []
    for item in files or []:
        if not isinstance(item, dict):
            continue
        if not (item.get("url") or item.get("name") or item.get("ok") or item.get("error")):
            continue
        key = item.get("key") or ""
        row = {
            "key": key,
            "name": item.get("name") or "",
            "size": int(item.get("size") or 0),
            "ok": bool(item.get("ok")),
            "error": item.get("error") or "",
            "path": item.get("path") or "",
            "sourceUrl": item.get("url") or "",
        }
        if row["ok"] and key:
            row["download"] = f"/api/nets/power-grid/notices/{content_id}/files/{key}"
        rows.append(row)
    return rows


def _view(item):
    item = dict(item)
    item.pop("_id", None)
    item.pop("detail", None)
    item.pop("detailText", None)
    return item
