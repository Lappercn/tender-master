"""中国烟草电子采购平台。地址和栏目只在这里改。"""

SOURCE_ID = "tobacco_cgjy"
SOURCE_NAME = "中国烟草电子采购平台"
ORIGIN = "https://cgjy.tobacco.com.cn"
HOME_URL = "https://cgjy.tobacco.com.cn/zbNotice/index.jhtml"
LIST_ROW = "ul.searchList li"
DETAIL_BOX = "div.wrap"
INTERVAL_MINUTES = 60
FILE_HINTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".7z", "download")
CHANNELS = (
    ("zbNotice", "招标公告"),
    ("zgysgg", "资格预审公告"),
    ("bgNotice", "变更公告"),
    ("zbhxrgs", "中标候选人公示"),
    ("resultNotice", "结果公告"),
)


def list_url(channel_code):
    return f"{ORIGIN}/{channel_code}/index.jhtml"
