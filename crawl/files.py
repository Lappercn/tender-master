"""附件按标讯存放。一条公告一个目录，文件用原始地址区分，不按文件名去重。"""
import hashlib
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "files"
MAX_BYTES = 30 * 1024 * 1024
_GENERIC_NAMES = {"download", "downLoad", "downLoadBid", "downLoadWin", "downLoadWinFile", "附件"}


def file_key(url):
    """同一条公告里，同一个下载地址只算一个文件。"""
    return hashlib.sha256((url or "").strip().encode("utf-8")).hexdigest()[:16]


def files_settled(existing):
    """附件已经处理完才跳过。没查过、下载失败的，下次还要再试。过大的文件不再反复下。"""
    if not existing or not isinstance(existing.get("files"), list):
        return False
    items = existing["files"]
    if any(not item.get("ok") and not _permanent(item) for item in items):
        return False
    done = set()
    for item in items:
        if item.get("url") and (item.get("ok") or _permanent(item)):
            done.add(item["url"])
    urls = [url for url in (existing.get("fileUrl") or []) if url]
    return all(url in done for url in urls)


def store_files(net, crawler_id, content_id, urls, fetch=None, existing=None):
    saved = []
    folder = FILES / _part(net) / _part(crawler_id) / _part(content_id)
    seen = set()
    ready = {}
    for item in existing or []:
        if _reusable(item):
            ready[item["url"]] = dict(item)
    for url in urls or []:
        url = (url or "").strip()
        if not url or url in seen or url.startswith("javascript:"):
            continue
        seen.add(url)
        if url in ready:
            saved.append(ready[url])
            continue
        item = {"key": file_key(url), "name": _filename(url), "url": url, "path": "", "size": 0, "ok": False, "error": ""}
        try:
            payload = (fetch or _download)(url)
            data, given_name = _unpack(payload)
            if given_name:
                item["name"] = _safe_name(given_name)
            if _useless(data):
                item["error"] = "对方没有返回文件"
            elif len(data) > MAX_BYTES:
                item["error"] = "文件过大，只保留原地址"
            else:
                folder.mkdir(parents=True, exist_ok=True)
                target = _unique(folder, item["name"])
                target.write_bytes(data)
                item["name"] = target.name
                item["path"] = _relative(target)
                item["size"] = len(data)
                item["ok"] = True
        except Exception as exc:
            item["error"] = str(exc)[:200]
        saved.append(item)
    return saved


def locate_file(item):
    """只认落在附件目录里的文件，避免路径被带出目录。"""
    raw = (item or {}).get("path") or ""
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    try:
        path = path.resolve()
        root = FILES.resolve()
    except OSError:
        return None
    if path != root and root not in path.parents:
        return None
    if not path.is_file():
        return None
    return path


def _download(url):
    import requests
    parsed = urlparse(url)
    referer = f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else url
    response = requests.get(
        url,
        timeout=60,
        headers={"User-Agent": "Mozilla/5.0", "Referer": referer},
    )
    response.raise_for_status()
    return response.content, _disposition_name(response.headers.get("Content-Disposition"))


def _unpack(payload):
    if isinstance(payload, tuple):
        data = payload[0] if payload else b""
        name = payload[1] if len(payload) > 1 else ""
        return data or b"", name or ""
    return payload or b"", ""


def _useless(data):
    if not data:
        return True
    if data.startswith(b"PK\x05\x06"):
        return True
    head = data[:80].lstrip().lower()
    return head.startswith(b"<html") or head.startswith(b"<!doctype") or head.startswith(b"<script")


def _reusable(item):
    if not item.get("url"):
        return False
    if _permanent(item):
        return True
    if not item.get("ok"):
        return False
    return locate_file(item) is not None


def _permanent(item):
    return "文件过大" in (item.get("error") or "")


def _disposition_name(header):
    if not header:
        return ""
    import re
    matched = re.search(r"filename\*=UTF-8''([^;]+)", header, flags=re.I)
    if not matched:
        matched = re.search(r'filename="?([^";]+)"?', header, flags=re.I)
    if not matched:
        return ""
    name = unquote(matched.group(1).strip())
    try:
        name = name.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return _safe_name(name)


def _filename(url):
    name = _safe_name(unquote(Path(urlparse(url).path).name))
    if name.lower() in {item.lower() for item in _GENERIC_NAMES}:
        return "附件"
    return name or "附件"


def _safe_name(name):
    text = "".join(ch for ch in str(name or "") if ch not in '\\/:*?"<>|').strip().strip(".")
    return text or "附件"


def _unique(folder, name):
    target = folder / name
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    cursor = 2
    while True:
        candidate = folder / f"{stem}-{cursor}{suffix}"
        if not candidate.exists():
            return candidate
        cursor += 1


def _relative(target):
    try:
        return target.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return target.resolve().as_posix()


def _part(value):
    text = "".join(ch for ch in str(value or "") if ch.isalnum() or ch in ("-", "_"))
    return text or "unknown"
