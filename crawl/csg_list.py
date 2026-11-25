"""南方电网列表是普通 HTML，用标准库解析，避免再绑一个解析包。"""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from collect.sources.csg_supply.constants import DETAIL_CODES, ORIGIN


class _ListParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_list = False
        self.in_item = False
        self.current = None
        self.capture = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attr = {key: value or "" for key, value in attrs}
        classes = set(attr.get("class", "").split())
        if tag == "div" and "List2" in classes:
            self.in_list = True
            return
        if not self.in_list:
            return
        if tag == "li":
            self.in_item = True
            self.current = {"date": "", "links": []}
            return
        if not self.in_item:
            return
        if tag == "a":
            self.capture = {
                "kind": "a",
                "href": attr.get("href", ""),
                "classes": set(attr.get("class", "").split()),
                "title": attr.get("title", "").strip(),
                "text": "",
            }
        elif tag == "span" and "Gray" in classes:
            self.capture = {"kind": "date", "text": ""}

    def handle_data(self, data):
        if self.capture is not None:
            self.capture["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.capture and self.capture.get("kind") == "a":
            if self.current is not None:
                self.current["links"].append(self.capture)
            self.capture = None
        elif tag == "span" and self.capture and self.capture.get("kind") == "date":
            if self.current is not None:
                self.current["date"] = self.capture["text"].strip()
            self.capture = None
        elif tag == "li" and self.current is not None:
            self.rows.append(self.current)
            self.current = None
            self.in_item = False
        elif tag == "div" and self.in_list and not self.in_item:
            self.in_list = False


def parse_rows(html):
    parser = _ListParser()
    parser.feed(html or "")
    rows = []
    for item in parser.rows:
        org = ""
        link = None
        for anchor in item["links"]:
            if "Blue" in anchor["classes"] and not org:
                org = " ".join(anchor["text"].split())
            href = anchor["href"]
            if "index.jhtml" in href:
                continue
            if any(f"/{code}/" in href for code in DETAIL_CODES):
                link = anchor
        if link is None:
            continue
        if org.lower() in ("[null]", "null"):
            org = ""
        title = " ".join(link["text"].split())
        title_attr = link["title"]
        truncated = title.endswith("...") or title.endswith("…")
        if truncated and title_attr and not title_attr.endswith("...") and not title_attr.endswith("…"):
            title = title_attr
            truncated = False
        href = urljoin(ORIGIN, link["href"])
        match = re.search(r"/(\d+)\.jhtml", href)
        rows.append({
            "title": title,
            "date": item["date"][:10],
            "org": org,
            "url": href,
            "site_id": match.group(1) if match else "",
            "truncated": truncated,
        })
    return rows
