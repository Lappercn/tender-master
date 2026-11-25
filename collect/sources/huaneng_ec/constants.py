"""中国华能集团电子商务平台。地址和栏目只在这里改。"""

SOURCE_ID = "huaneng_ec"
SOURCE_NAME = "中国华能集团电子商务平台"
HOME_URL = "https://ec.chng.com.cn/channel/home/#/purchase"
DETAIL_URL = "https://ec.chng.com.cn/channel/home/#/detail?id={notice_id}"
LIST_ROW = "tr.ant-table-row"
DETAIL_BOX = "div.content"
INTERVAL_MINUTES = 60
FILE_HINTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".7z", "download")
CHANNELS = (
    ("zb_zbgg", "招标专栏-招标公告"),
    ("zb_zgys", "招标专栏-资格预审公告"),
    ("zb_hxrgs", "招标专栏-候选人公示"),
    ("zb_zbjg", "招标专栏-中标结果公告"),
    ("fzb_cggg", "非招标专栏-采购公告"),
    ("fzb_hxrgs", "非招标专栏-候选人公示"),
    ("fzb_cgjg", "非招标专栏-采购结果公告"),
)
