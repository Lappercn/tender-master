"""中化商务电子招投标平台。地址和栏目只在这里改。"""

SOURCE_ID = "sinochem_ebid"
SOURCE_NAME = "中化商务电子招投标平台"
HOME_URL = "https://e.sinochemitc.com"
LIST_ROW = "ul.search-list > li"
DETAIL_BOX = "div.articleMain, div.a-content"
CONTENT_BOX = "div.a-content"
INTERVAL_MINUTES = 60
FILE_HINTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".7z", "download")
CHANNELS = (
    ("ywgg1qb", "招标/预审/变更"),
    ("ywgg2qb", "评标结果/中标结果"),
    ("ywgg3qb", "非招标采购公告"),
)


def list_url(channel_code):
    return f"{HOME_URL}/cms/channel/{channel_code}/index.htm"
