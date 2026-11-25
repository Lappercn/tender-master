"""把网页收成可阅读的正文。表格尽量保持行列，对不齐时退回段落。"""
import re
from html.parser import HTMLParser

_NAV = re.compile(r"^\s*上[一1]篇|^\s*下[一1]篇")
_CHROME = re.compile(
    r"^(首页\s*>.*|招标采购\s*>.*|导航菜单|登录|注册|全文检索|智能客服|"
    r"公告文件|变更公告文件|下载公告文件|下载变更公告文件|获取招标文件|获取资格预审文件|"
    r"电子商务平台\(ECP\)|E-Commercial Platform.*|版本：.*|"
    r"联系我们\s*[|｜].*|.*版权所有.*|.*Copyright\s*@.*)$"
)
_SKIP_TAGS = {"script", "style", "noscript"}
_BREAK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "section", "br"}
_SPAN_LIMIT = 8


class _Cell:
    def __init__(self, colspan, rowspan):
        self.parts = []
        self.colspan = _span(colspan)
        self.rowspan = _span(rowspan)


class _Table:
    def __init__(self):
        self.rows = []
        self.current = None
        self.cell = None
        self.notes = []


class _Blocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.out = []
        self.tables = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "table":
            table = _Table()
            if self.tables and self.tables[-1].cell is not None:
                self.tables[-1].cell.parts.append(table)
            else:
                self.out.append(table)
            self.tables.append(table)
            return
        if tag == "tr" and self.tables:
            row = []
            self.tables[-1].rows.append(row)
            self.tables[-1].current = row
            self.tables[-1].cell = None
            return
        if tag in ("td", "th") and self.tables:
            found = dict(attrs)
            cell = _Cell(found.get("colspan"), found.get("rowspan"))
            table = self.tables[-1]
            if table.current is None:
                table.current = []
                table.rows.append(table.current)
            table.current.append(cell)
            table.cell = cell
            return
        if tag in ("td", "th"):
            self._append("\n")
            return
        if tag == "br":
            self._append("\n")
            return
        if tag in _BREAK_TAGS:
            self._append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag == "table" and self.tables:
            self.tables.pop()
            return
        if tag in ("td", "th") and self.tables:
            self.tables[-1].cell = None
            return
        if tag in _BREAK_TAGS or tag in ("td", "th"):
            self._append("\n")

    def handle_data(self, data):
        if not self.skip and data:
            self._append(data)

    def _append(self, text):
        if self.tables:
            table = self.tables[-1]
            if table.cell is not None:
                table.cell.parts.append(text)
            else:
                table.notes.append(text)
            return
        self.out.append(text)


def html_to_text(html):
    raw = html or ""
    if "<" not in raw:
        return present_text(raw)
    parser = _Blocks()
    try:
        parser.feed(raw)
        parser.close()
        return _render(parser.out)
    except Exception:
        return present_text(re.sub(r"<[^>]+>", "\n", raw))


def present_text(text):
    lines = []
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = " ".join(raw.split())
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if _NAV.match(line) or _CHROME.search(line):
            continue
        lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _render(parts):
    chunks = []
    buf = []

    def flush():
        text = present_text("".join(buf))
        buf.clear()
        if text:
            chunks.append(text)

    for part in parts:
        if isinstance(part, _Table):
            flush()
            block = _render_table(part)
            if block:
                chunks.append(block)
        else:
            buf.append(part)
    flush()
    return "\n\n".join(chunks)


def _render_table(table):
    note = present_text("".join(table.notes))
    if _one_column(table):
        body = _read_loose(table)
        return "\n\n".join(part for part in (note, body) if part)
    grid, nested = _grid(table)
    if not grid or _sparse(grid):
        body = _read_loose(table)
        return "\n\n".join(part for part in (note, body) if part)
    blocks = []
    if note:
        blocks.append(note)
    blocks.append(_markdown(grid))
    for item in nested:
        block = _render_table(item)
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _read_loose(table):
    parts = []
    for row in table.rows:
        for cell in row:
            raw, nested = _cell_raw(cell)
            text = present_text(raw)
            if text:
                parts.append(text)
            for item in nested:
                block = _render_table(item)
                if block:
                    parts.append(block)
    return "\n\n".join(parts)


def _grid(table):
    occupied = set()
    placed = {}
    nested = []
    max_c = 0
    max_r = 0
    for r, row in enumerate(table.rows):
        c = 0
        for cell in row:
            while (r, c) in occupied:
                c += 1
            raw, inner = _cell_raw(cell)
            nested.extend(inner)
            text = _clean_cell(raw)
            for dr in range(cell.rowspan):
                for dc in range(cell.colspan):
                    occupied.add((r + dr, c + dc))
                    placed[(r + dr, c + dc)] = text if dr == 0 and dc == 0 else ""
            max_c = max(max_c, c + cell.colspan)
            max_r = max(max_r, r + cell.rowspan)
            c += cell.colspan
        max_r = max(max_r, r + 1)
    grid = []
    for r in range(max_r):
        line = [placed.get((r, c), "") for c in range(max_c)]
        if any(cell.strip() for cell in line):
            grid.append(line)
    return grid, nested


def _markdown(grid):
    width = max(len(row) for row in grid)
    def line(row):
        cells = list(row) + [""] * (width - len(row))
        return "| " + " | ".join(cells) + " |"
    rows = [line(row) for row in grid]
    sep = "| " + " | ".join("---" for _ in range(width)) + " |"
    return "\n".join([rows[0], sep, *rows[1:]])


def _one_column(table):
    widths = [sum(cell.colspan for cell in row) for row in table.rows if row]
    return not widths or max(widths) <= 1


def _sparse(grid):
    return all(sum(1 for cell in row if cell.strip()) <= 1 for row in grid)


def _cell_raw(cell):
    bits = []
    nested = []
    for part in cell.parts:
        if isinstance(part, _Table):
            nested.append(part)
        else:
            bits.append(part)
    return "".join(bits), nested


def _clean_cell(raw):
    text = " ".join((raw or "").split()).replace("|", "\\|")
    if not text or _NAV.match(text) or _CHROME.search(text):
        return ""
    return text


def _span(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 1
    if number < 1:
        return 1
    return min(number, _SPAN_LIMIT)
