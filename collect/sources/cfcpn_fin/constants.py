"""金采网（中国金融集中采购网）。地址和栏目只在这里改。"""

SOURCE_ID = "cfcpn_fin"
SOURCE_NAME = "金采网（中国金融集中采购网）"
ORIGIN = "http://www.cfcpn.com"
HOME_URL = "http://www.cfcpn.com/jcw/sys/index/goUrl?url=modules/sys/login/list&column=cggg"
LOGIN_URL = "http://www.cfcpn.com/jcw/supplierLogin"
LIST_ROW = "div.cfcpn-list-main"
DETAIL_BOX = "#detail-new"
INTERVAL_MINUTES = 60
CHANNELS = (
    ("cggg", "采购公告"),
    ("zjgg", "征集公告"),
    ("jggg", "结果公告"),
    ("gzgg", "更正公告"),
)


def list_url(channel_code):
    return f"{ORIGIN}/jcw/sys/index/goUrl?url=modules/sys/login/list&column={channel_code}"
