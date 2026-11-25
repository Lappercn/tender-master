"""开放查询用的条件。用户输入按模糊包含处理，不当成正则。"""
import re


def notice_filter(text="", notice_type="", area=""):
    query = {}
    if notice_type:
        query["noticeType"] = notice_type.strip()
    if area:
        query["area"] = area.strip()
    keyword = (text or "").strip()
    if keyword:
        safe = re.escape(keyword)
        query["$or"] = [
            {"title": {"$regex": safe, "$options": "i"}},
            {"purchaser": {"$regex": safe, "$options": "i"}},
            {"projectCode": {"$regex": safe, "$options": "i"}},
            {"briefText": {"$regex": safe, "$options": "i"}},
        ]
    return query


LIST_FIELDS = (
    "contentId", "crawlerId", "source", "title", "noticeType", "area",
    "createTime", "url", "purchaser", "budget", "projectCode", "category", "hasAnnex",
)
