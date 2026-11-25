"""公告的增删改。标题、原文和指纹不能改。"""
from collect.sources.registry import get_source
from crawl.identity import content_id
from crawl.record import build_notice

EDITABLE = ("noticeType", "area", "purchaser", "projectCode", "projectStatus", "budget", "category")


def editable_patch(fields):
    patch = {}
    for key in EDITABLE:
        if key in fields and fields[key] is not None:
            patch[key] = str(fields[key]).strip()
    return patch


def create_notice(store, node_id, body):
    source = get_source(body["sourceId"])
    title = (body.get("title") or "").strip()
    url = (body.get("url") or "").strip()
    create_time = (body.get("createTime") or "").strip()
    if not title or not url or len(create_time) < 10:
        raise ValueError("标题、链接和日期都要填")
    if not url.startswith("http"):
        raise ValueError("链接要以 http 开头")
    channel_code = (body.get("channel") or "").strip()
    if channel_code:
        channel = source.channel(channel_code)
        channel_id, channel_label = channel.code, channel.name
    else:
        channel_id, channel_label = "manual", "补录"
    doc = build_notice(
        crawler_id=source.id,
        source=source.name,
        title=title,
        url=url,
        content_id=content_id(title),
        create_time=create_time[:10],
        channel_id=channel_id,
        channel_label=channel_label,
        node_id=node_id,
        detail_text=body.get("detailText") or "",
        detail_html="",
        file_urls=[],
        site_notice_id=(body.get("siteNoticeId") or "").strip(),
        project_code=(body.get("projectCode") or "").strip(),
    )
    outcome = store.save_notice(source.id, doc)
    if outcome == "duplicate":
        raise ValueError("同样标题的公告已经有了")
    doc.pop("detail", None)
    return {"outcome": outcome, "item": doc}


def change_notice(store, source_id, content_id_value, fields):
    get_source(source_id)
    found = store.update_notice(source_id, content_id_value, editable_patch(fields))
    if not found:
        raise KeyError("没有这条公告")
    return found


def remove_notice(store, source_id, content_id_value):
    get_source(source_id)
    if not store.delete_notice(source_id, content_id_value):
        raise KeyError("没有这条公告")
    return {"ok": True}
