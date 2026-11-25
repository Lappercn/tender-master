"""任务队列。一台机器直接 run 时不经过这里；多机时由主节点投入、采集节点领取。"""
import datetime
import uuid

LEASE = datetime.timedelta(seconds=90)
GRACE = datetime.timedelta(seconds=30)


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


class TaskQueue:
    def __init__(self, store):
        if not store.online:
            raise RuntimeError(f"任务队列需要存储连通。当前：{store.reason}")
        self.store = store
        self.tasks = store.collect["crawl_tasks"]
        self.schedules = store.collect["crawl_schedules"]
        self.nodes = store.collect["crawl_nodes"]
        self.breakers = store.collect["crawl_breakers"]

    def seed_schedules(self, specs):
        now = utcnow()
        for spec in specs:
            self.schedules.update_one(
                {"_id": spec.id},
                {"$setOnInsert": {
                    "crawlerId": spec.id,
                    "label": spec.label,
                    "intervalMinutes": spec.interval_minutes,
                    "lookbackDays": 14,
                    "enabled": True,
                    "lastEnqueuedAt": None,
                    "createdAt": now,
                }},
                upsert=True,
            )

    def set_schedule(self, crawler_id, minutes=None, enabled=None, lookback=None):
        changes = {}
        if minutes is not None:
            changes["intervalMinutes"] = int(minutes)
        if enabled is not None:
            changes["enabled"] = bool(enabled)
        if lookback is not None:
            changes["lookbackDays"] = int(lookback)
        if not changes:
            return
        self.schedules.update_one({"_id": crawler_id}, {"$set": changes})

    def schedule_map(self):
        return {item["_id"]: item for item in self.schedules.find()}

    def has_active(self, crawler_id, channel):
        return self.tasks.find_one({
            "crawlerId": crawler_id,
            "channel": channel,
            "status": {"$in": ["pending", "running", "retry_wait"]},
        }) is not None

    def enqueue(self, job, source):
        if self.has_active(job["crawlerId"], job["channel"]):
            return None
        now = utcnow()
        task = {
            "_id": uuid.uuid4().hex,
            "crawlerId": job["crawlerId"],
            "script": job["script"],
            "label": job["label"],
            "channel": job["channel"],
            "channelLabel": job["channelLabel"],
            "lookbackDays": job["lookbackDays"],
            "pageStart": job.get("pageStart", 1),
            "pageEnd": job.get("pageEnd", 0),
            "maxPages": job.get("maxPages", 40),
            "targetNode": job.get("targetNode") or "any",
            "status": "pending",
            "source": source,
            "attempt": 0,
            "maxRetries": 2,
            "availableAt": now,
            "createdAt": now,
            "leaseUntil": None,
            "token": None,
            "nodeId": None,
            "error": "",
            "saved": 0,
            "skipped": 0,
            "failedRows": 0,
        }
        self.tasks.insert_one(task)
        return task["_id"]

    def claim(self, node_id, accept):
        now = utcnow()
        query = {
            "status": {"$in": ["pending", "retry_wait"]},
            "availableAt": {"$lte": now},
            "targetNode": {"$in": [node_id, "any"]},
        }
        if "*" not in accept:
            query["crawlerId"] = {"$in": list(accept)}
        from pymongo import ReturnDocument
        token = uuid.uuid4().hex
        return self.tasks.find_one_and_update(
            query,
            {"$set": {
                "status": "running",
                "nodeId": node_id,
                "token": token,
                "startedAt": now,
                "leaseUntil": now + LEASE,
                "error": "",
            }, "$inc": {"attempt": 1}},
            sort=[("createdAt", 1)],
            return_document=ReturnDocument.AFTER,
        )

    def renew(self, task):
        now = utcnow()
        updated = self.tasks.update_one(
            {"_id": task["_id"], "token": task["token"], "status": "running"},
            {"$set": {"leaseUntil": now + LEASE}},
        )
        return updated.modified_count > 0

    def release(self, task, reason):
        now = utcnow()
        return self.tasks.update_one(
            {"_id": task["_id"], "token": task["token"], "status": "running"},
            {"$set": {
                "status": "pending",
                "token": None,
                "error": reason,
                "availableAt": now + datetime.timedelta(minutes=15),
            }, "$inc": {"attempt": -1}},
        ).modified_count > 0

    def finish(self, task, status, error="", saved=0, skipped=0, failed_rows=0, note=""):
        now = utcnow()
        retry = status == "failed" and task.get("attempt", 1) <= task.get("maxRetries", 2)
        final = "retry_wait" if retry else status
        changes = {
            "status": final,
            "finishedAt": now,
            "error": (error or "")[:500],
            "saved": saved,
            "skipped": skipped,
            "failedRows": failed_rows,
            "note": note,
            "token": None,
        }
        if retry:
            wait = min(900, 30 * (2 ** max(task.get("attempt", 1) - 1, 0)))
            changes["availableAt"] = now + datetime.timedelta(seconds=wait)
        return self.tasks.update_one(
            {"_id": task["_id"], "token": task["token"], "status": "running"},
            {"$set": changes},
        ).modified_count > 0

    def recover(self):
        now = utcnow()
        expired = now - GRACE
        recovered = 0
        for task in self.tasks.find({"status": "running", "leaseUntil": {"$lt": expired}}):
            retry = task.get("attempt", 1) <= task.get("maxRetries", 2)
            status = "retry_wait" if retry else "failed"
            result = self.tasks.update_one(
                {"_id": task["_id"], "status": "running", "leaseUntil": {"$lt": expired}},
                {"$set": {
                    "status": status,
                    "error": "采集节点失联，任务已收回",
                    "finishedAt": now,
                    "availableAt": now,
                    "token": None,
                }},
            )
            recovered += result.modified_count
        return recovered

    def counts(self):
        if not self.store.online:
            return {}
        pipeline = [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
        return {row["_id"]: row["n"] for row in self.tasks.aggregate(pipeline)}

    def heartbeat(self, node, mode):
        now = utcnow()
        self.nodes.update_one(
            {"_id": node["node_id"]},
            {"$set": {
                "roles": node.get("roles") or [],
                "accept": node.get("accept") or [],
                "mode": mode,
                "status": "online",
                "lastSeen": now,
            }},
            upsert=True,
        )

    def list_nodes(self):
        return list(self.nodes.find().sort("_id", 1))

    def load_breaker(self, node_id):
        return self.breakers.find_one({"_id": node_id}) or {}

    def save_breaker(self, node_id, snapshot):
        self.breakers.update_one(
            {"_id": node_id},
            {"$set": {"snapshot": snapshot, "updatedAt": utcnow()}},
            upsert=True,
        )

    def due_schedules(self, now=None):
        now = now or utcnow()
        due = []
        for item in self.schedules.find({"enabled": True}):
            last = item.get("lastEnqueuedAt")
            interval = datetime.timedelta(minutes=int(item.get("intervalMinutes") or 60))
            if last is None or last <= now - interval:
                due.append(item)
        return due

    def mark_enqueued(self, crawler_id):
        self.schedules.update_one({"_id": crawler_id}, {"$set": {"lastEnqueuedAt": utcnow()}})


def safe_queue(store):
    try:
        return TaskQueue(store)
    except (RuntimeError, ModuleNotFoundError):
        return None
