"""库表命名。三个库不变。同一张网的公告进同一张表，旧的按站点表仍能查。"""
import datetime
import re

import config

CRAWLER_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def check_crawler_id(crawler_id):
    if not CRAWLER_ID.fullmatch(crawler_id or ""):
        raise ValueError(f"爬虫编号不合法：{crawler_id}")
    return crawler_id


def net_key(crawler_id):
    check_crawler_id(crawler_id)
    from collect.sources.registry import source_map
    source = source_map().get(crawler_id)
    key = getattr(source, "net", "") if source else ""
    key = (key or crawler_id).replace("-", "_")
    if not CRAWLER_ID.fullmatch(key):
        raise ValueError(f"公告表编号不合法：{key}")
    return key


def notice_collection(crawler_id, when=None, shard=None):
    return _names(net_key(crawler_id), when, shard)[0]


def notice_collections(crawler_id, when=None, shard=None):
    """查找顺序。第一张是现在写入的表，后面是这个源头以前的表。"""
    names = []
    for name, _extra in read_scopes(crawler_id, when=when, shard=shard, bind_source=False):
        if name not in names:
            names.append(name)
    return names


def read_scopes(crawler_id, when=None, shard=None, bind_source=True):
    check_crawler_id(crawler_id)
    shared = net_key(crawler_id)
    scopes = []
    for name in _names(shared, when, shard):
        extra = {"crawlerId": crawler_id} if bind_source and shared != crawler_id else {}
        scopes.append((name, extra))
    if shared != crawler_id:
        for name in _names(crawler_id, when, shard):
            if name not in {item[0] for item in scopes}:
                scopes.append((name, {}))
    return scopes


def _names(key, when, shard):
    shard = shard if shard is not None else config.NOTICE_SHARD
    base = f"notices_{key}"
    if shard == "crawler":
        return [base]
    if shard != "month":
        raise ValueError(f"未知分表方式：{shard}")
    when = when or datetime.date.today()
    current = f"{base}_{when.strftime('%Y%m')}"
    previous_day = when.replace(day=1) - datetime.timedelta(days=1)
    previous = f"{base}_{previous_day.strftime('%Y%m')}"
    if previous == current:
        return [current]
    return [current, previous]


def database_names():
    return {
        "collect": config.COLLECT_DB,
        "process": config.PROCESS_DB,
        "serve": config.SERVE_DB,
    }
