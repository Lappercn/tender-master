"""采集范围。页面上选最近几小时或几天，列表按时间从新到旧，早于范围就停。"""
import datetime
import re

SPANS = (
    ("1h", "最近 1 小时", 1),
    ("3h", "最近 3 小时", 3),
    ("1d", "最近 1 天", 24),
    ("2d", "最近 2 天", 48),
    ("3d", "最近 3 天", 72),
    ("7d", "最近 7 天", 24 * 7),
    ("14d", "最近 14 天", 24 * 14),
)
_BY_CODE = {code: (label, hours) for code, label, hours in SPANS}
_CLOCK = re.compile(r"\d{1,2}:\d{2}")


def span_choices():
    return [{"code": code, "label": label, "hours": hours} for code, label, hours in SPANS]


def hours_of(code):
    found = _BY_CODE.get(code or "")
    if not found:
        raise ValueError("采集范围不在可选项里")
    return found[1]


def label_of(code):
    found = _BY_CODE.get(code or "")
    return found[0] if found else ""


def code_for_hours(hours):
    for code, _label, value in SPANS:
        if value == int(hours):
            return code
    return ""


def window_bounds(hours, now=None):
    moment = _as_datetime(now) or datetime.datetime.now().replace(microsecond=0)
    start = moment - datetime.timedelta(hours=int(hours))
    return start, moment


def judge_date(date_text, start, end):
    text = (date_text or "").strip()
    moment = _parse_moment(text)
    if moment is None:
        return "skip"
    start_at = _as_datetime(start)
    end_at = _as_datetime(end)
    if start_at is None or end_at is None:
        return "skip"
    if _CLOCK.search(text):
        if moment < start_at:
            return "stop"
        if moment > end_at:
            return "skip"
        return "take"
    day = moment.date()
    if day < start_at.date():
        return "stop"
    if day > end_at.date():
        return "skip"
    return "take"


def outside_detail(text, start, end, hours):
    """列表只有日期时，短范围再看正文里的钟点。没有钟点就保留当天这条。"""
    if int(hours) >= 24:
        return False
    match = re.search(r"(\d{4}-\d{2}-\d{2})[ T](\d{1,2}:\d{2})", text or "")
    if not match:
        return False
    return judge_date(f"{match.group(1)} {match.group(2)}", start, end) == "stop"


def _parse_moment(text):
    head = text[:19].replace("T", " ")
    for pattern, size in (("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        try:
            return datetime.datetime.strptime(head[:size], pattern)
        except ValueError:
            continue
    return None


def _as_datetime(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time.max)
    if isinstance(value, str) and value:
        return _parse_moment(value[:19])
    return None
