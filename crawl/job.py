from dataclasses import dataclass, field


def channels_for(source, job):
    """这次要采的栏目。指定栏目时只采那一个，否则采这个源头的全部。"""
    code = getattr(job, "channel", "") or ""
    if code:
        return (source.channel(code),)
    return tuple(source.channels)


@dataclass
class Job:
    crawler_id: str
    channel: str = ""
    lookback_days: int = 14
    lookback_hours: int = 0
    span: str = ""
    pace: str = "normal"
    page_start: int = 1
    page_end: int = 0
    max_pages: int = 40
    node_id: str = "local-1"

    def __post_init__(self):
        from crawl.window import code_for_hours, hours_of
        if self.pace not in ("calm", "normal"):
            self.pace = "normal"
        if self.span:
            self.lookback_hours = hours_of(self.span)
        elif not self.lookback_hours:
            self.lookback_hours = max(1, int(self.lookback_days or 14)) * 24
        if not self.span:
            self.span = code_for_hours(self.lookback_hours) or "14d"


@dataclass
class JobResult:
    saved: int = 0
    skipped: int = 0
    failed: int = 0
    status: str = "success"
    error: str = ""
    note: str = ""
    channels: list = field(default_factory=list)
