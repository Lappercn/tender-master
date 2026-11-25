"""国网附件不在页面链接上。按栏目查出全部文件地址，一条都不漏。"""
import json
import logging
from urllib.parse import quote, urlparse

from collect.sources.sgcc_ecp.constants import (
    CHANGE_BID_API,
    DELAY_BID_API,
    DOWNLOAD_BID,
    DOWNLOAD_FILE,
    DOWNLOAD_WIN,
    DOWNLOAD_WIN_FILE,
    FILE_API,
    NOTICE_BID_API,
    WIN_API,
    WIN_FILE_API,
)

logger = logging.getLogger("sgcc_ecp.attachments")
INVITE = "招标邀请书"


def resolve_attachments(current_url, post=None):
    kind, notice_id = split_route(current_url)
    if not notice_id:
        return _none("页面地址里没有公告编号")
    ask = post or _post
    try:
        if kind in ("doc-spec", "doc-com"):
            return _from_file_list(ask(FILE_API, notice_id))
        if kind == "doci-bid":
            return _from_bid(ask(NOTICE_BID_API, notice_id))
        if kind == "doci-change":
            return _from_change(ask(CHANGE_BID_API, notice_id))
        if kind == "doci-delay":
            return _from_delay(ask(DELAY_BID_API, notice_id))
        if kind == "doci-win":
            return _from_win(ask(WIN_API, notice_id), notice_id, ask)
    except Exception as exc:
        logger.warning("查询附件失败 %s %s：%s", kind, notice_id, exc)
        return _none(f"查询附件失败：{exc}"[:80], retry=True)
    return _none("这个栏目没有单独的附件接口")


def attachment_urls(current_url, content=""):
    return resolve_attachments(current_url)["urls"]


def split_route(current_url):
    parts = [item for item in urlparse(current_url or "").fragment.split("/") if item]
    if len(parts) >= 3 and parts[0] == "doc" and "_" in parts[2]:
        notice_id = parts[2].split("_", 1)[0]
        if notice_id.isdigit():
            return parts[1], notice_id
    return "", ""


def notice_id_from_url(current_url):
    return split_route(current_url)[1]


def _from_file_list(body):
    files = ((body or {}).get("resultValue") or {}).get("files") or []
    urls = []
    for item in files:
        file_id = (item or {}).get("firstPageFileId")
        if file_id:
            urls.append(DOWNLOAD_FILE.format(file_id=file_id))
    return _pack(urls)


def _from_bid(body):
    value = (body or {}).get("resultValue") or {}
    notice = value.get("notice") or {}
    if notice.get("NOTICE_TYPE_NAME") == INVITE:
        return _none("招标邀请书需要登录后才能下载")
    if not _flag(value.get("fileFlag")):
        return _none("无招标文件")
    return _bid_pack(notice)


def _from_change(body):
    value = (body or {}).get("resultValue") or {}
    urls = []
    if _flag(value.get("oriFileFlag")):
        urls.extend(_bid_pack(value.get("origNotice") or {})["urls"])
    return _pack(urls)


def _from_delay(body):
    value = (body or {}).get("resultValue") or {}
    urls = []
    if _flag(value.get("delayFileFlag")):
        urls.extend(_bid_pack(value.get("delaynotice") or {})["urls"])
    if _flag(value.get("fileFlag")):
        urls.extend(_bid_pack(value.get("notice") or {})["urls"])
    return _pack(urls)


def _from_win(body, notice_id, ask):
    value = (body or {}).get("resultValue") or {}
    notice = value.get("notice") or {}
    if str(notice.get("HIDE_FLAG") or "") == "100038002":
        return _none("无招标文件")
    if not _flag(value.get("fileFlag")):
        return _none("无招标文件")
    urls = []
    win_id = notice.get("PURPRJ_NOTICE_ID") or ""
    if win_id:
        urls.append(DOWNLOAD_WIN.format(notice_id=win_id))
    listed = ((ask(WIN_FILE_API, notice_id) or {}).get("resultValue") or {}).get("files") or []
    for item in listed:
        path = (item or {}).get("FILE_PATH") or ""
        name = (item or {}).get("FILE_NAME") or ""
        if path and name:
            urls.append(DOWNLOAD_WIN_FILE.format(file_path=quote(path, safe=""), file_name=quote(name, safe="")))
    return _pack(urls)


def _bid_pack(notice):
    notice_id = (notice or {}).get("ONLINE_BID_NOTICE_ID") or ""
    if not notice_id:
        return _none("查询附件失败：没有公告编号", retry=True)
    det = (notice or {}).get("PURPRJ_NOTICE_DET_ID") or ""
    return _pack([DOWNLOAD_BID.format(notice_id=notice_id, notice_det_id=det)])


def _pack(urls):
    unique = []
    seen = set()
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    if not unique:
        return _none("无招标文件")
    return {"urls": unique, "hasFile": True, "note": f"有招标文件 {len(unique)} 个", "retry": False}


def _none(note, retry=False):
    return {"urls": [], "hasFile": False, "note": note, "retry": retry}


def _flag(value):
    return str(value).strip().lower() in {"1", "true"}


def _post(url, notice_id):
    import requests
    response = requests.post(
        url,
        data=json.dumps(str(notice_id)),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": "https://ecp.sgcc.com.cn/ecp2.0/portal/",
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()
