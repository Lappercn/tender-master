"""一条标讯一行采集记录。栏目、结果、标题、附件情况分开，方便后面筛选。"""


def notice_line(channel, outcome, title, note):
    return "标讯 {} | {} | {} | {}".format(
        _cell(channel), _cell(outcome), _cell(title), _cell(note),
    )


def file_note(saved, fallback="无招标文件"):
    rows = list(saved or [])
    if not rows:
        return fallback or "无招标文件"
    ok = [item for item in rows if item.get("ok")]
    bad = [item for item in rows if not item.get("ok")]
    if ok and not bad:
        return f"有招标文件 {len(ok)} 个，下载成功 {len(ok)} 个"
    if ok and bad:
        return f"有招标文件 {len(rows)} 个，下载成功 {len(ok)} 个，失败 {len(bad)} 个"
    reason = bad[0].get("error") or "没有保存"
    return f"有招标文件 {len(bad)} 个，下载失败：{reason}"


def _cell(value):
    return " ".join(str(value or "").split()).replace(" | ", " / ")
