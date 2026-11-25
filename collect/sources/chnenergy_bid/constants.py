"""国家能源招标网（国能e招）。地址和栏目只在这里改。"""

SOURCE_ID = "chnenergy_bid"
SOURCE_NAME = "国家能源招标网"
HOME_URL = "https://www.chnenergybidding.com.cn"
LIST_ROW = "ul.right-items li.right-item"
DETAIL_BOX = "div.article-info div.con, div.article-info"
INTERVAL_MINUTES = 60
FILE_HINTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".7z", "download")
CHANNELS = (
    ("001002", "招标公告"),
    ("001001", "资格预审公告"),
    ("001003", "非招标公告"),
    ("001006", "中标公告"),
    ("001004", "变更公告"),
    ("001005", "候选人公示"),
    ("001007", "终止公告"),
)


def list_url(channel_code):
    return f"{HOME_URL}/bidweb/001/{channel_code}/moreinfo.html"
