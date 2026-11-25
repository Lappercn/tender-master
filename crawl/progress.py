"""采集进度。写在进度表里，不写进公告。"""
import logging

logger = logging.getLogger("crawl.progress")


def mark(store, source, channel_id, label, page, result, message):
    try:
        store.write_progress({
            "crawlerId": source.id,
            "crawlerName": source.name,
            "netName": getattr(source, "net_name", "") or "新型电网",
            "channel": channel_id,
            "channelLabel": label,
            "page": page,
            "saved": result.saved,
            "skipped": result.skipped,
            "failed": result.failed,
            "message": message,
        })
    except Exception:
        logger.info("进度没写上：%s", message)
