"""中国政府采购网。地址和栏目只在这里改。"""

SOURCE_ID = "ccgp_gov"
SOURCE_NAME = "中国政府采购网"
HOME_URL = "https://search.ccgp.gov.cn/bxsearch"
LIST_ROW = "ul.vT-srch-result-list-bid li"
DETAIL_BOX = "#noticeArea, .vF_detail_content"
INTERVAL_MINUTES = 60
FILE_HINTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".7z", "bizdownload")
CHANNELS = (
    ("1", "公开招标"),
    ("2", "询价公告"),
    ("3", "竞争性谈判"),
    ("4", "单一来源"),
    ("5", "资格预审"),
    ("6", "邀请公告"),
    ("7", "中标公告"),
    ("8", "更正公告"),
    ("9", "其他公告"),
    ("10", "竞争性磋商"),
    ("11", "成交公告"),
    ("12", "终止公告"),
)


def search_url(bid_type, start_date_str, end_date_str, page=1):
    return (
        f"{HOME_URL}?searchtype=1&page_index={page}&bidSort=0&buyerName=&projectId="
        f"&pinMu=0&bidType={bid_type}&dbselect=bidx&kw="
        f"&start_time={start_date_str}&end_time={end_date_str}"
        "&timeType=0&displayZone=&zoneId=&pppStatus=0&agentName="
    )
