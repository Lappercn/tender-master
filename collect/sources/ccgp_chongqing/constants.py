"""重庆市政府采购网。地址和栏目只在这里改。"""

SOURCE_ID = "ccgp_chongqing"
SOURCE_NAME = "重庆市政府采购网"
ORIGIN = "https://www.ccgp-chongqing.gov.cn"
HOME_URL = "https://www.ccgp-chongqing.gov.cn/info-notice/procument-notice"
LIST_ROW = ".notice-list-item"
DETAIL_BOX = "div.wrap-post, div.notice-detail, div.notice-content"
INTERVAL_MINUTES = 45
FILE_HINTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".7z", "download")
CHANNELS = (
    ("procument-notice", "采购公告"),
    ("result-notice", "结果公告"),
    ("correction-notice", "更正公告"),
)


def list_url(channel_code):
    return f"{ORIGIN}/info-notice/{channel_code}"
