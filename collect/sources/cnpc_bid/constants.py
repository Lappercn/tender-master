"""中国石油电子招标投标交易平台。地址和栏目只在这里改。"""

SOURCE_ID = "cnpc_bid"
SOURCE_NAME = "中国石油电子招标投标交易平台"
HOME_URL = "https://www.cnpcbidding.com"
LIST_ROW = "div.box_data"
DETAIL_BOX = "div.details"
INTERVAL_MINUTES = 60
CHANNELS = (
    ("zbgg", "招标公告"),
    ("zgys", "资格预审公告"),
    ("gk_hxr", "公开招标中标候选人公示"),
    ("yq_hxr", "邀请招标中标候选人通知"),
    ("gk_jg", "公开招标中标结果公告"),
    ("yq_jg", "邀请招标中标结果通知"),
)

MODULE_URLS = {
    "zbgg": f"{HOME_URL}/#/tenders",
    "zgys": f"{HOME_URL}/#/tenders",
    "gk_hxr": f"{HOME_URL}/#/candidate",
    "yq_hxr": f"{HOME_URL}/#/candidate",
    "gk_jg": f"{HOME_URL}/#/candidate",
    "yq_jg": f"{HOME_URL}/#/candidate",
}
