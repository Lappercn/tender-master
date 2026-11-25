"""国铁采购平台（原95306）。地址和栏目只在这里改。"""

SOURCE_ID = "guotie_95306"
SOURCE_NAME = "国铁采购平台"
ORIGIN = "https://cg.95306.cn"
HOME_URL = (
    "https://cg.95306.cn/baseinfor/notice/procurementNotice"
    "?bidType=&noticeType=000&transactionType=01&wzType=&title=&bidding=&navigation="
)
DETAIL_URL = "https://cg.95306.cn/baseinfor/notice/informationShow?id={notice_id}"
LIST_ROW = "div.text_con div.text_row"
DETAIL_BOX = "div.article_detail"
INTERVAL_MINUTES = 60
FILE_HINTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".7z", "download")
CHANNELS = (
    ("01", "采购公告"),
    ("02", "变更公告"),
    ("03", "结果公告"),
)


def list_url(channel_code):
    return (
        "https://cg.95306.cn/baseinfor/notice/procurementNotice"
        f"?bidType=&noticeType=000&transactionType={channel_code}&wzType=&title=&bidding=&navigation="
    )
