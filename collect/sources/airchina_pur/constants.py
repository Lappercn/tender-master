"""中国航空集团有限公司采购管理平台。地址和栏目只在这里改。"""

SOURCE_ID = "airchina_pur"
SOURCE_NAME = "中国航空集团有限公司采购管理平台"
ORIGIN = "https://pur.airchina.com.cn"
HOME_URL = "https://pur.airchina.com.cn/001/001001/moreinfo.html"
LIST_ROW = "tbody#infoContent tr"
DETAIL_BOX = "div.ewb-notice, div.ewb-notice-copy, div.ewb-notice-bd"
INTERVAL_MINUTES = 60
CHANNELS = (
    ("001001", "采购公告"),
    ("001002", "澄清公告"),
    ("001003", "中标公示"),
    ("001004", "结果公告"),
    ("001005", "其他公告"),
)


def list_url(channel_code):
    return f"{ORIGIN}/001/{channel_code}/moreinfo.html"
