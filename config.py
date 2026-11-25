import os
import logging

logger = logging.getLogger(__name__)

def load_env(env_path=None):
    """
    Simple .env file loader to avoid python-dotenv dependency if not installed.
    """
    if not env_path:
        beside = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        env_path = beside if os.path.exists(beside) else ".env"
    config = {}
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        config[key.strip()] = value.strip()
        except Exception as e:
            logger.error(f"Error loading .env file: {e}")
    return config

# Load configuration
_conf = load_env()

# Export variables with defaults
MONGO_HOST = _conf.get("MONGO_HOST", "localhost")
MONGO_PORT = _conf.get("MONGO_PORT", "27017")
MONGO_USER = _conf.get("MONGO_USER", "")
MONGO_PASS = _conf.get("MONGO_PASS", "")
DB_NAME = _conf.get("DB_NAME", "yuedongData")

# Construct URI
if "MONGO_URI" in _conf:
    MONGO_URI = _conf["MONGO_URI"]
else:
    if MONGO_USER and MONGO_PASS:
        # Append authSource to ensure authentication against the correct database
        # Optimized connection parameters:
        # - serverSelectionTimeoutMS=30000: Increase to 30s for slow network/elections
        # - connectTimeoutMS=30000: Increase to 30s for establishing connection
        # - socketTimeoutMS=60000: Increase to 60s for slow queries/large payloads
        # - maxPoolSize=100: Concurrent connections (default 100)
        MONGO_URI = f"mongodb://{MONGO_USER}:{MONGO_PASS}@{MONGO_HOST}:{MONGO_PORT}/?authSource={DB_NAME}&serverSelectionTimeoutMS=30000&connectTimeoutMS=30000&socketTimeoutMS=60000&maxPoolSize=100"
    else:
        MONGO_URI = f"mongodb://{MONGO_HOST}:{MONGO_PORT}/?serverSelectionTimeoutMS=30000&connectTimeoutMS=30000&socketTimeoutMS=60000&maxPoolSize=100"

COLLECTION_NAME = _conf.get("COLLECTION_NAME", "tender_data")
LOG_COLLECTION_NAME = _conf.get("LOG_COLLECTION_NAME", "tender_datalog")

# YesCaptcha
YESCAPTCHA_CLIENT_KEY = _conf.get("YESCAPTCHA_CLIENT_KEY", "")
YESCAPTCHA_API_URL = _conf.get("YESCAPTCHA_API_URL", "https://api.yescaptcha.com")

# 站点登录账号配置（通过 .env 或环境变量注入，请勿硬编码）
CFCPN_USERNAME = _conf.get("CFCPN_USERNAME", "")
CFCPN_PASSWORD = _conf.get("CFCPN_PASSWORD", "")

# 六张网按域分库。yuedongData 只留作旧项目的库名，本项目默认不再写入那里。
COLLECT_DB = _conf.get("COLLECT_DB", "six_collect")
PROCESS_DB = _conf.get("PROCESS_DB", "six_process")
SERVE_DB = _conf.get("SERVE_DB", "six_serve")
STORAGE_MONGO_URI = _conf.get("STORAGE_MONGO_URI") or MONGO_URI
# crawler：一个站点一张公告表。month：再按公告月份拆成 notices_sgcc_202611。
NOTICE_SHARD = _conf.get("NOTICE_SHARD", "crawler")
CRAWL_LOOKBACK_DAYS = int(_conf.get("CRAWL_LOOKBACK_DAYS") or "14")
CRAWL_MAX_PAGES = int(_conf.get("CRAWL_MAX_PAGES") or "40")
CRAWL_HEADLESS = _conf.get("CRAWL_HEADLESS", "1") not in ("0", "false", "False", "no")
CRAWL_BROWSER = _conf.get("CRAWL_BROWSER", "undetected")
CRAWL_USER_AGENT = _conf.get("CRAWL_USER_AGENT", "")
CRAWL_FINGERPRINT = _conf.get("CRAWL_FINGERPRINT", "fixed")
CRAWL_WINDOW = _conf.get("CRAWL_WINDOW", "1920,1080")
CRAWL_LANG = _conf.get("CRAWL_LANG", "zh-CN,zh")
CRAWL_TIMEZONE = _conf.get("CRAWL_TIMEZONE", "Asia/Shanghai")
NODE_ID = _conf.get("NODE_ID", "local-1")
NODE_FILE = _conf.get("NODE_FILE", "")
PROCESS_PIPELINE = _conf.get("PROCESS_PIPELINE", "processing.pipeline:PassThrough")
API_HOST = _conf.get("API_HOST", "127.0.0.1")
API_PORT = int(_conf.get("API_PORT") or "8787")
CONSOLE_PORT = int(_conf.get("CONSOLE_PORT") or "8788")
