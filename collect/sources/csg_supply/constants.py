"""中国南方电网供应链统一服务平台。地址和栏目只在这里改。"""

SOURCE_ID = "csg_supply"
SOURCE_NAME = "中国南方电网供应链统一服务平台"
ORIGIN = "https://www.bidding.csg.cn"
LIST_BOX = "div.List2"
CONTENT_BOX = "div.Content"
DETAIL_BOX = "div.Content, h1.s-title"
INTERVAL_MINUTES = 60
FILE_HINTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".7z", "download")
CHANNELS = (
    ("zbgg", "招标公告"),
    ("fzbgg", "非招标公告"),
    ("zbhxrgs", "公示公告"),
    ("fbgg", "流标公告"),
    ("yjzjgg", "意见征集"),
    ("xygg", "寻源公告"),
)
DETAIL_CODES = tuple(code for code, _name in CHANNELS)


def list_url(channel, page):
    page = int(page or 1)
    if page <= 1:
        return f"{ORIGIN}/{channel}/index.jhtml"
    return f"{ORIGIN}/{channel}/index_{page}.jhtml"
