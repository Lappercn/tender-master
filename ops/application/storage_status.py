"""采集库现在的样子：连没连上、存在哪个库、有多少条、每天新插入多少。"""
import datetime
import time

from ops.storage import CollectStore

_CACHE = {}


def overview(node_id, days=14):
    cached = _CACHE.get(node_id)
    now = time.time()
    if cached and now - cached["at"] < 5:
        return cached["body"]
    raw = CollectStore(node_id).status(days)
    body = dict(raw)
    body["days"] = fill_days(raw.get("insertedByDay") or {}, raw.get("collectedByDay") or {}, days)
    body.pop("insertedByDay", None)
    body.pop("collectedByDay", None)
    _CACHE[node_id] = {"at": now, "body": body}
    return body


def fill_days(inserted, collected, days=14, today=None):
    today = today or datetime.date.today()
    rows = []
    for offset in range(days):
        day = (today - datetime.timedelta(days=offset)).isoformat()
        rows.append({
            "day": day,
            "inserted": int(inserted.get(day) or 0),
            "collected": int(collected.get(day) or 0),
        })
    return rows
