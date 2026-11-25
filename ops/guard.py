"""连续失败后暂停该爬虫，冷却结束允许再试一次。"""
import datetime


class Breaker:
    def __init__(self, limit=3, cooldown_seconds=900):
        self.limit = limit
        self.cooldown = datetime.timedelta(seconds=cooldown_seconds)
        self.failures = {}
        self.open_until = {}

    def allow(self, key, at):
        until = self.open_until.get(key)
        return not until or at >= until

    def success(self, key):
        self.failures[key] = 0
        self.open_until.pop(key, None)

    def failure(self, key, at):
        count = self.failures.get(key, 0) + 1
        self.failures[key] = count
        if count >= self.limit:
            self.open_until[key] = at + self.cooldown
        return count

    def snapshot(self):
        return {
            "failures": dict(self.failures),
            "openUntil": {key: value.isoformat() for key, value in self.open_until.items()},
        }

    def restore(self, data):
        data = data or {}
        self.failures = {key: int(value) for key, value in (data.get("failures") or {}).items()}
        self.open_until = {}
        for key, value in (data.get("openUntil") or {}).items():
            if not value:
                continue
            text = value.replace("Z", "+00:00")
            moment = datetime.datetime.fromisoformat(text)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=datetime.timezone.utc)
            self.open_until[key] = moment
