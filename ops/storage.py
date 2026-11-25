"""公告入库。Mongo 不通时先写到本机 spool，恢复后再回放。"""
import datetime
import json
import logging
from pathlib import Path

import config
from ops.naming import database_names, notice_collection, read_scopes
from processing.pipeline import load_pipeline

logger = logging.getLogger("ops.storage")
ROOT = Path(__file__).resolve().parents[1]
SPOOL = ROOT / "spool"
FROZEN = {"contentId", "detail", "detailText", "title", "url", "source", "crawlerId"}


def _mongo_errors():
    from pymongo.errors import DuplicateKeyError, PyMongoError
    return DuplicateKeyError, PyMongoError


class CollectStore:
    def __init__(self, node_id):
        self.node_id = node_id
        self.online = False
        self.reason = ""
        self.client = None
        names = database_names()
        try:
            from pymongo import MongoClient
            self.client = MongoClient(config.STORAGE_MONGO_URI, serverSelectionTimeoutMS=3000)
            self.client.admin.command("ping")
            self.collect = self.client[names["collect"]]
            self.process = self.client[names["process"]]
            self.serve = self.client[names["serve"]]
            self.online = True
            self._indexed = set()
            self._ensure_layout()
        except Exception as exc:
            self.online = False
            if isinstance(exc, ModuleNotFoundError):
                self.reason = "没有安装 pymongo。在 data-foundation 目录执行 pip install -r requirements.txt"
            else:
                self.reason = str(exc)
            logger.warning("存储未连通，本次先写本机暂存：%s", self.reason)

    def _ensure_layout(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        for db, role in ((self.collect, "collect"), (self.process, "process"), (self.serve, "serve")):
            db["_meta"].update_one(
                {"_id": "layout"},
                {"$set": {"role": role, "schema": 1, "updatedAt": now}},
                upsert=True,
            )
        self.collect["crawl_runs"].create_index([("crawlerId", 1), ("startedAt", -1)])
        self.collect["crawl_runs"].create_index([("startedAt", -1)])
        self.collect["crawl_progress"].create_index([("crawlerId", 1), ("channel", 1)], unique=True)
        self.collect["crawl_tasks"].create_index([("status", 1), ("availableAt", 1)])
        self.collect["crawl_tasks"].create_index([("crawlerId", 1), ("channel", 1), ("status", 1)])

    def _notices(self, crawler_id, when=None):
        name = notice_collection(crawler_id, when=when)
        column = self.collect[name]
        if name not in self._indexed:
            column.create_index("contentId", unique=True)
            column.create_index("createTime")
            column.create_index("storedAt")
            column.create_index("noticeType")
            self._indexed.add(name)
        return column

    def find_notice(self, crawler_id, content_id, create_time=""):
        if not content_id:
            return None
        if not self.online:
            if content_id in self._spool_ids(crawler_id):
                return {"contentId": content_id}
            return None
        try:
            when = _parse_day(create_time)
            fields = {"contentId": 1, "projectCode": 1, "siteNoticeId": 1, "title": 1, "fileUrl": 1, "files": 1}
            for name, extra in read_scopes(crawler_id, when=when, bind_source=False):
                found = self.collect[name].find_one({"contentId": content_id, **extra}, fields)
                if found:
                    return found
            return None
        except _mongo_errors()[1] as exc:
            self._degrade(exc)
            if content_id in self._spool_ids(crawler_id):
                return {"contentId": content_id}
            return None

    def save_notice(self, crawler_id, doc):
        doc = dict(doc)
        doc["storedBy"] = self.node_id
        doc["storedAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            extra = load_pipeline().on_notice(doc) or {}
            for key in FROZEN | {"storedAt", "storedBy"}:
                extra.pop(key, None)
            doc.update(extra)
        except Exception as exc:
            doc["processStatus"] = "degraded"
            doc["processError"] = str(exc)[:200]
        if self.online:
            duplicate, mongo_error = _mongo_errors()
            try:
                self._notices(crawler_id, _parse_day(doc.get("createTime"))).insert_one(doc)
                return "stored"
            except duplicate:
                return "duplicate"
            except mongo_error as exc:
                self._degrade(exc)
        self._spool(crawler_id, doc)
        return "spooled"

    def write_run(self, record):
        record = dict(record)
        record["nodeId"] = self.node_id
        if self.online:
            try:
                self.collect["crawl_runs"].insert_one(record)
                return
            except _mongo_errors()[1] as exc:
                self._degrade(exc)
        self._append(SPOOL / "runs.jsonl", record)

    def recent_runs(self, crawler_id="", limit=20):
        if not self.online:
            return []
        query = {"crawlerId": crawler_id} if crawler_id else {}
        rows = self.collect["crawl_runs"].find(query).sort("startedAt", -1).limit(limit)
        return [_public(row) for row in rows]

    def counts(self):
        if not self.online:
            return {}
        found = {}
        for name in self.collect.list_collection_names():
            if name.startswith("notices_"):
                found[name] = self.collect[name].estimated_document_count()
        return found

    def status(self, days=14):
        names = database_names()
        body = {
            "online": self.online,
            "reason": "" if self.online else (self.reason or "存储未连通"),
            "current": names["collect"],
            "databases": [
                {"role": "采集库", "name": names["collect"], "holdsNotices": True},
                {"role": "处理库", "name": names["process"], "holdsNotices": False},
                {"role": "查询库", "name": names["serve"], "holdsNotices": False},
            ],
            "noticeCount": 0,
            "collections": [],
            "insertedByDay": {},
            "collectedByDay": {},
            "spoolCount": self._spool_notice_count(),
            "dataBytes": 0,
        }
        if not self.online:
            return body
        try:
            existing = set(self.client.list_database_names())
            for item in body["databases"]:
                item["exists"] = item["name"] in existing
            stats = self.collect.command("dbstats")
            body["dataBytes"] = int(stats.get("dataSize") or 0)
            counts = self.counts()
            body["collections"] = [{"name": name, "count": counts[name]} for name in sorted(counts)]
            body["noticeCount"] = sum(counts.values())
            since = (datetime.date.today() - datetime.timedelta(days=days - 1)).isoformat()
            inserted = {}
            for name in counts:
                for row in self.collect[name].aggregate([
                    {"$match": {"storedAt": {"$gte": since}}},
                    {"$group": {"_id": {"$substrCP": ["$storedAt", 0, 10]}, "count": {"$sum": 1}}},
                ]):
                    if row.get("_id"):
                        inserted[row["_id"]] = inserted.get(row["_id"], 0) + int(row["count"])
            collected = {}
            for row in self.collect["crawl_runs"].aggregate([
                {"$match": {"startedAt": {"$gte": since}}},
                {"$group": {"_id": {"$substrCP": ["$startedAt", 0, 10]}, "saved": {"$sum": "$saved"}}},
            ]):
                if row.get("_id"):
                    collected[row["_id"]] = int(row.get("saved") or 0)
            body["insertedByDay"] = inserted
            body["collectedByDay"] = collected
        except _mongo_errors()[1] as exc:
            self._degrade(exc)
            body["online"] = False
            body["reason"] = self.reason
        return body

    def _spool_notice_count(self):
        if not SPOOL.exists():
            return 0
        total = 0
        for path in SPOOL.glob("notices_*.jsonl"):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    total += sum(1 for line in handle if line.strip())
            except OSError:
                continue
        return total

    def _notice_names(self, source_id):
        if source_id:
            return [name for name, _extra in read_scopes(source_id)]
        if not self.online:
            return []
        return [name for name in self.collect.list_collection_names() if name.startswith("notices_")]

    def search_notices(self, source_id="", text="", notice_type="", area="", page=1, size=20):
        from serve.search import LIST_FIELDS, notice_filter
        if not self.online:
            raise RuntimeError("存储未连通")
        page = max(1, int(page or 1))
        size = min(50, max(1, int(size or 20)))
        query = notice_filter(text, notice_type, area)
        projection = {field: 1 for field in LIST_FIELDS}
        total = 0
        rows = []
        fetch = page * size
        if isinstance(source_id, (list, tuple, set)):
            scopes = self._multi_scopes(source_id)
        elif source_id:
            scopes = read_scopes(source_id)
        else:
            scopes = [(name, {}) for name in self._notice_names("")]
        for name, extra in scopes:
            column = self.collect[name]
            scoped = dict(query)
            scoped.update(extra)
            total += column.count_documents(scoped)
            rows.extend(column.find(scoped, projection).sort("createTime", -1).limit(fetch))
        rows.sort(key=lambda item: item.get("createTime") or "", reverse=True)
        start = (page - 1) * size
        return {"page": page, "size": size, "total": total, "items": [_public(item) for item in rows[start:start + size]]}

    def _multi_scopes(self, source_ids):
        grouped = {}
        order = []
        for sid in source_ids:
            for name, extra in read_scopes(sid):
                if name not in grouped:
                    grouped[name] = []
                    order.append(name)
                grouped[name].append(extra)
        scopes = []
        for name in order:
            extras = grouped[name]
            if any(not e for e in extras):
                scopes.append((name, {}))
            else:
                cids = [e["crawlerId"] for e in extras if "crawlerId" in e]
                if len(cids) == 1:
                    scopes.append((name, {"crawlerId": cids[0]}))
                else:
                    scopes.append((name, {"crawlerId": {"$in": list(dict.fromkeys(cids))}}))
        return scopes

    def get_notice(self, source_id, content_id):
        if not self.online:
            raise RuntimeError("存储未连通")
        for name, extra in read_scopes(source_id):
            found = self.collect[name].find_one({"contentId": content_id, **extra})
            if found:
                found["hasRawHtml"] = bool((found.get("detail") or "").strip())
                found.pop("detail", None)
                if found.get("detailText"):
                    from crawl.text import present_text
                    found["detailText"] = present_text(found["detailText"])
                return _public(found)
        return None

    def attach_files(self, crawler_id, content_id, files, file_urls):
        """只补附件，不动已经入库的标题、正文和来源。"""
        if not self.online or not content_id:
            return False
        patch = {
            "files": list(files or []),
            "fileUrl": list(file_urls or []),
            "hasAnnex": bool(file_urls),
        }
        try:
            for name, extra in read_scopes(crawler_id):
                result = self.collect[name].update_one({"contentId": content_id, **extra}, {"$set": patch})
                if result.matched_count:
                    return True
        except _mongo_errors()[1] as exc:
            self._degrade(exc)
        return False

    def update_notice(self, crawler_id, content_id, patch):
        if not self.online:
            raise RuntimeError(self.reason or "存储未连通")
        if not patch:
            raise ValueError("没有可修改的内容")
        for name, extra in read_scopes(crawler_id):
            result = self.collect[name].update_one({"contentId": content_id, **extra}, {"$set": patch})
            if result.matched_count:
                return self.get_notice(crawler_id, content_id)
        return None

    def delete_notice(self, crawler_id, content_id):
        if not self.online:
            raise RuntimeError(self.reason or "存储未连通")
        for name, extra in read_scopes(crawler_id):
            result = self.collect[name].delete_one({"contentId": content_id, **extra})
            if result.deleted_count:
                return True
        return False

    def page_runs(self, crawler_id="", page=1, size=10):
        page = max(1, int(page or 1))
        size = min(50, max(1, int(size or 10)))
        if not self.online:
            rows = self._spool_runs(crawler_id)
        else:
            query = {"crawlerId": crawler_id} if crawler_id else {}
            column = self.collect["crawl_runs"]
            total = column.count_documents(query)
            cursor = column.find(query).sort("startedAt", -1).skip((page - 1) * size).limit(size)
            return {
                "page": page,
                "size": size,
                "total": total,
                "items": self._with_names([_public(row) for row in cursor]),
            }
        start = (page - 1) * size
        return {"page": page, "size": size, "total": len(rows), "items": self._with_names(rows[start:start + size])}

    def write_progress(self, record):
        record = dict(record)
        record["nodeId"] = self.node_id
        record["updatedAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        key = {"crawlerId": record.get("crawlerId") or "", "channel": record.get("channel") or ""}
        if self.online:
            try:
                self.collect["crawl_progress"].update_one(key, {"$set": record}, upsert=True)
                return
            except _mongo_errors()[1] as exc:
                self._degrade(exc)
        self._append(SPOOL / "progress.jsonl", record)

    def list_progress(self, crawler_id=""):
        if not self.online:
            rows = self._latest_progress(crawler_id)
            return self._with_names(rows)
        query = {"crawlerId": crawler_id} if crawler_id else {}
        rows = list(self.collect["crawl_progress"].find(query).sort("updatedAt", -1))
        return self._with_names([_public(row) for row in rows])

    def _latest_progress(self, crawler_id):
        path = SPOOL / "progress.jsonl"
        if not path.exists():
            return []
        found = {}
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[-2000:]
        except OSError:
            return []
        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if crawler_id and item.get("crawlerId") != crawler_id:
                continue
            found[(item.get("crawlerId"), item.get("channel") or "")] = item
        return list(found.values())

    def _with_names(self, rows):
        from collect.sources.registry import source_map
        from crawl.window import label_of
        known = source_map()
        for row in rows:
            source = known.get(row.get("crawlerId") or "")
            row["crawlerName"] = source.name if source else (row.get("crawlerName") or row.get("crawlerId") or "")
            row["netName"] = row.get("netName") or (getattr(source, "net_name", "") if source else "")
            if row.get("span") and not row.get("spanLabel"):
                row["spanLabel"] = label_of(row["span"])
        return rows

    def _spool_runs(self, crawler_id):
        path = SPOOL / "runs.jsonl"
        if not path.exists():
            return []
        rows = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[-5000:]
        except OSError:
            return []
        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if crawler_id and item.get("crawlerId") != crawler_id:
                continue
            rows.append(item)
        rows.reverse()
        return rows

    def replay(self):
        moved = 0
        if not self.online:
            raise RuntimeError("存储还没连通，先不要回放")
        SPOOL.mkdir(parents=True, exist_ok=True)
        for path in SPOOL.glob("notices_*.jsonl"):
            kept = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                outcome = self.save_notice(item["crawlerId"], item["doc"])
                if outcome == "spooled":
                    kept.append(line)
                else:
                    moved += 1
            if kept:
                path.write_text("\n".join(kept) + "\n", encoding="utf-8")
            else:
                path.rename(path.with_suffix(".done"))
        return moved

    def _degrade(self, exc):
        self.online = False
        self.reason = str(exc)
        logger.warning("存储中途断开，后续改写本机暂存：%s", exc)

    def _spool(self, crawler_id, doc):
        SPOOL.mkdir(parents=True, exist_ok=True)
        self._append(SPOOL / f"notices_{crawler_id}.jsonl", {"crawlerId": crawler_id, "doc": doc})
        with (SPOOL / f"fingerprints_{crawler_id}.txt").open("a", encoding="utf-8") as handle:
            handle.write(doc.get("contentId", "") + "\n")

    def _spool_ids(self, crawler_id):
        path = SPOOL / f"fingerprints_{crawler_id}.txt"
        if not path.exists():
            return set()
        return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}

    @staticmethod
    def _append(path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def _parse_day(value):
    text = str(value or "")[:10]
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def _public(row):
    row = dict(row)
    row["_id"] = str(row.get("_id"))
    return row
