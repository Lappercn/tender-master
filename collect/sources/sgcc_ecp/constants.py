"""国家电网新一代电子商务平台。地址和栏目只在这里改。"""

SOURCE_ID = "sgcc_ecp"
SOURCE_NAME = "国家电网新一代电子商务平台"
HOME_URL = "https://ecp.sgcc.com.cn/ecp2.0/portal/#/"
MORE_BUTTON = "span.yewuspan"
LIST_ROW = "tbody tr"
TITLE_CELL = "td.title"
INTERVAL_MINUTES = 60
CORE = "https://ecp.sgcc.com.cn/ecp2.0/ecpwcmcore/"
FILE_API = CORE + "/index/getFile"
NOTICE_BID_API = CORE + "/index/getNoticeBid"
CHANGE_BID_API = CORE + "/index/getChangeBid"
DELAY_BID_API = CORE + "/index/getDelayNoticeBid"
WIN_API = CORE + "/index/getNoticeWin"
WIN_FILE_API = CORE + "/index/getWinFile"
DOWNLOAD_FILE = CORE + "/index/downLoad?fileId={file_id}&a=b"
DOWNLOAD_BID = CORE + "/index/downLoadBid?noticeId={notice_id}&noticeDetId={notice_det_id}"
DOWNLOAD_WIN = CORE + "/index/downLoadWin?notice={notice_id}"
DOWNLOAD_WIN_FILE = CORE + "/index/downLoadWinFile?filePath={file_path}&fileName={file_name}"
CHANNELS = (
    ("prequal", "资格预审公告"),
    ("tender", "招标公告及投标邀请书"),
    ("purchase", "采购公告"),
    ("candidate", "推荐中标候选人公示"),
    ("award", "中标（成交）结果公告"),
)
