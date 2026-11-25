"""把采集结果收成一条公告。价格和联系人仍走原来的正则。"""
import datetime

from collect.domain.notice import BIZ_NET, BRIEF_LIMIT, DETAIL_HTML_LIMIT, INDUSTRY, SCHEMA_VERSION
from crawl.extract import (
    annex_names,
    classify_notice,
    extract_agent,
    extract_budget,
    extract_contacts,
    extract_end_time,
    extract_purchase_method,
    extract_purchaser,
    extract_winning,
    guess_area,
    purchaser_from_title,
)


def build_notice(
    *,
    crawler_id,
    source,
    title,
    url,
    content_id,
    create_time,
    channel_id,
    channel_label,
    node_id,
    detail_text,
    detail_html,
    file_urls,
    site_notice_id="",
    project_code="",
    project_status="",
    purchaser_hint="",
    extra=None,
):
    text = detail_text or ""
    budget, budget_label = extract_budget(text)
    purchaser = extract_purchaser(text) or purchaser_hint or purchaser_from_title(title)
    names = annex_names(text)
    html = detail_html or ""
    extra_data = dict(extra or {})
    if len(html) > DETAIL_HTML_LIMIT:
        html = html[:DETAIL_HTML_LIMIT]
        extra_data["detailTruncated"] = True
    found_names = list(extra_data.get("annexNames") or [])
    for name in names:
        if name not in found_names:
            found_names.append(name)
    if found_names:
        extra_data["annexNames"] = found_names
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bidder, amount = extract_winning(text)
    return {
        "contentId": content_id,
        "siteNoticeId": site_notice_id or None,
        "projectCode": project_code or None,
        "projectStatus": project_status or None,
        "crawlerId": crawler_id,
        "script": None,
        "channel": channel_id,
        "title": title,
        "url": url,
        "source": source,
        "createTime": create_time,
        "crawl_time": now,
        "nodeId": node_id,
        "noticeType": classify_notice(title, channel_label),
        "area": guess_area(source, title, purchaser),
        "industry": INDUSTRY,
        "bizNet": BIZ_NET,
        "budget": budget,
        "budget_label": budget_label,
        "tenderEndTime": extract_end_time(text),
        "purchaser": purchaser,
        "agent": extract_agent(text),
        "purchaseMethod": extract_purchase_method(text),
        "winningBidder": bidder,
        "winningAmount": amount,
        "briefText": text[:BRIEF_LIMIT] if text else "",
        "detail": html,
        "detailText": text,
        "hasAnnex": bool(file_urls or names),
        "fileUrl": list(file_urls or []),
        "contacts": extract_contacts(text),
        "keywords": None,
        "highlightedWords": None,
        "tags": None,
        "category": channel_label,
        "onclick": None,
        "schemaVersion": SCHEMA_VERSION,
        "extra": extra_data,
    }
