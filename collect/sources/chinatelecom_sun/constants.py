"""中国电信阳光采购网。地址和栏目只在这里改。"""

SOURCE_ID = "chinatelecom_sun"
SOURCE_NAME = "中国电信阳光采购网"
HOME_URL = "https://caigou.chinatelecom.com.cn/search"
LIST_ROW = "tr.el-table__row"
DETAIL_BOX = "div.a-main, div.main-content, div.detail-box, div.content"
INTERVAL_MINUTES = 60
CHANNELS = (
    ("prequal", "资格预审公告"),
    ("tender", "招标公告"),
    ("inquiry", "询比公告"),
    ("negotiate", "谈判采购公告"),
    ("eval", "评价检测公告"),
    ("gov_coop", "政企合作招募公告"),
    ("iptv", "IPTV内容合作招募公告"),
    ("result", "采购结果公示"),
    ("direct", "直接采购公示"),
    ("clarify", "澄清公示"),
)
