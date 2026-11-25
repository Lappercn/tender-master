"""中国邮政电子采购与供应平台。地址和栏目只在这里改。"""

SOURCE_ID = "chinapost_11185"
SOURCE_NAME = "中国邮政电子采购与供应平台"
ORIGIN = "https://cg.11185.cn"
HOME_URL = (
    "https://cg.11185.cn/zgyzcms/category/bulletinList.html"
    "?searchDate=2001-03-14&dates=300&goSearch=&categoryId=88"
    "&tabName=%E9%87%87%E8%B4%AD%E4%BF%A1%E6%81%AF&industryName=&status=&page=1"
)
LIST_ROW = "ul.newslist li"
DETAIL_BOX = "div.topTitle, #main, iframe#pdfContainer"
INTERVAL_MINUTES = 60
CHANNELS = (
    ("88", "采购信息"),
)


def list_url(channel_code, page=1):
    page = max(1, int(page or 1))
    return (
        "https://cg.11185.cn/zgyzcms/category/bulletinList.html"
        f"?searchDate=2001-03-14&dates=300&goSearch=&categoryId={channel_code}"
        f"&tabName=%E9%87%87%E8%B4%AD%E4%BF%A1%E6%81%AF&industryName=&status=&page={page}"
    )
