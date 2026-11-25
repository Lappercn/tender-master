import time
import datetime
import re
import os
import sys
import logging
import traceback
import hashlib
import random
import json
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from pymongo import MongoClient
import config

# ================= Configuration =================
MONGO_URI = config.MONGO_URI
DB_NAME = config.DB_NAME
COLLECTION_DATA = config.COLLECTION_NAME
COLLECTION_LOG = config.LOG_COLLECTION_NAME

# Crawler Info
CRAWLER_NAME = "wj_sinochem_china"
SOURCE_NAME = "中化商务电子招投标平台"
BASE_URL = "https://e.sinochemitc.com"

# ================= Logger Setup =================
def setup_logger():
    logger = logging.getLogger(CRAWLER_NAME)
    logger.setLevel(logging.INFO)
    
    # Console Handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger

logger = setup_logger()

# ================= MongoDB Connection =================
try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    col_data = db[COLLECTION_DATA]
    col_log = db[COLLECTION_LOG]
    logger.info("MongoDB 连接成功。")
except Exception as e:
    logger.error(f"MongoDB 连接失败: {e}")
    sys.exit(1)

# ================= Helper Functions =================

def save_log(status, message, details=None, title=None, content_id=None):
    log_entry = {
        "crawler_name": CRAWLER_NAME,
        "status": status,
        "message": message,
        "details": details,
        "related_title": title,
        "related_contentId": content_id,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        col_log.insert_one(log_entry)
    except Exception as e:
        logger.error(f"保存日志失败: {e}")

def get_md5(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def clean_title(title):
    if not title:
        return ""
    t = title.strip()
    t = re.sub(r'[【】\[\]（）\-]', '', t)
    t = re.sub(r'\s+', '', t)
    return t.lower()

def extract_budget(content):
    patterns = [
        r'(预算金额|预算总金额|项目预算).*?([\d,]+(\.\d+)?).*?(万|元)',
        r'(最高限价|最高限制单价|最高单价限价|限价).*?([\d,]+(\.\d+)?).*?(万|元)',
        r'(采购控制价|控制价).*?([\d,]+(\.\d+)?).*?(万|元)',
        r'(合同估算价|估算价).*?([\d,]+(\.\d+)?).*?(万|元)',
        r'(单价|金额|价格|标段报价).*?([\d,]+(\.\d+)?).*?(万|元)'
    ]
    for p in patterns:
        match = re.search(p, content)
        if match:
            return match.group(0)
    return None

def extract_end_time(content):
    patterns = [
        r'(递交|提交).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?)',
        r'(投标|响应).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?)',
        r'(开标时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?)',
        r'(报名).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?)',
        r'([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?).*?截止'
    ]
    for p in patterns:
        match = re.search(p, content)
        if match:
            if len(match.groups()) >= 3 and match.group(3): 
                 return match.group(3)
            if len(match.groups()) >= 1 and match.group(1):
                 return match.group(1)
            return match.group(0)
    return None

def extract_contacts(content):
    contacts = []
    combo_pattern = r'(项目联系人|联系人|负责人|联系方式)[:：]\s*([\u4e00-\u9fa5]{2,4}).{0,50}?(联系电话|电话|手机)[:：]\s*([\d-]{8,})'
    matches = re.finditer(combo_pattern, content)
    found_combo = False
    for m in matches:
        found_combo = True
        name = m.group(2)
        phone = m.group(4)
        contacts.append({"name": name, "phone": phone})
    
    if found_combo:
        return contacts

    name_pattern = r'(项目联系人|联系人|负责人)[：:]\s*([\u4e00-\u9fa5]{2,4})'
    phone_pattern = r'(联系电话|电话|手机|联系方式)[：:]\s*([\d-]{8,})'
    
    name_match = re.search(name_pattern, content)
    phone_match = re.search(phone_pattern, content)
    
    contact_obj = {}
    if name_match:
        contact_obj['name'] = name_match.group(2)
    if phone_match:
        contact_obj['phone'] = phone_match.group(2)
    
    if contact_obj:
        contacts.append(contact_obj)
        
    return contacts

# ================= Main Crawler Class =================

class SinochemCrawler:
    def __init__(self):
        self.setup_driver()

    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Anti-detection
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            # 优先使用系统安装的 chromedriver (Server/Linux 环境)
            import shutil
            system_driver_path = shutil.which("chromedriver")
            
            # 如果 which 没找到，尝试常见路径
            if not system_driver_path:
                possible_paths = [
                    "/usr/bin/chromedriver",
                    "/usr/local/bin/chromedriver",
                    "/usr/lib/chromium-browser/chromedriver",
                    "/snap/bin/chromium.chromedriver"
                ]
                for path in possible_paths:
                    if os.path.exists(path):
                        system_driver_path = path
                        break

            if system_driver_path and os.path.exists(system_driver_path):
                logger.info(f"使用系统 chromedriver: {system_driver_path}")
                service = Service(executable_path=system_driver_path)
            else:
                # 本地/Windows 环境使用 webdriver_manager
                logger.info("未找到系统 chromedriver，尝试使用 webdriver_manager...")
                service = Service(ChromeDriverManager().install())
            
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.wait = WebDriverWait(self.driver, 20)
            logger.info("Chrome 驱动初始化成功。")
        except Exception as e:
            logger.error(f"Chrome 驱动初始化失败: {e}")
            sys.exit(1)

    def random_sleep(self, min_sec=1.5, max_sec=5.0):
        time.sleep(random.uniform(min_sec, max_sec))

    def safe_click(self, element):
        try:
            self.wait.until(EC.element_to_be_clickable(element))
            element.click()
        except:
            self.driver.execute_script("arguments[0].click();", element)

    def simulate_reading(self):
        try:
            total_height = self.driver.execute_script("return document.body.scrollHeight")
            viewport_height = self.driver.execute_script("return window.innerHeight")
            current_scroll = 0
            scroll_times = random.randint(2, 4)
            for _ in range(scroll_times):
                if current_scroll + viewport_height >= total_height:
                    break
                scroll_step = random.randint(200, 500)
                current_scroll += scroll_step
                self.driver.execute_script(f"window.scrollTo(0, {current_scroll});")
                time.sleep(random.uniform(0.5, 1.5))
        except: pass

    def run(self):
        try:
            logger.info("开始运行爬虫...")
            
            categories = [
                {"name": "招标/预审/变更", "url": "https://e.sinochemitc.com/cms/channel/ywgg1qb/index.htm"},
                {"name": "评标结果/中标结果", "url": "https://e.sinochemitc.com/cms/channel/ywgg2qb/index.htm"},
                {"name": "非招标采购公告", "url": "https://e.sinochemitc.com/cms/channel/ywgg3qb/index.htm"}
            ]
            
            for cat in categories:
                self.crawl_category(cat)
                
        except Exception as e:
            logger.error(f"严重错误: {e}")
            save_log("ERROR", "严重错误", str(e))
            traceback.print_exc()
        finally:
            self.driver.quit()
            logger.info("爬虫运行结束。")

    def crawl_category(self, category):
        logger.info(f"正在抓取板块: {category['name']} - {category['url']}")
        self.driver.get(category['url'])
        self.random_sleep(3, 5)
        
        page = 1
        while True:
            logger.info(f"正在抓取第 {page} 页...")
            
            try:
                # Wait for list
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.search-list")))
                
                items = self.driver.find_elements(By.CSS_SELECTOR, "ul.search-list > li")
                if not items:
                    logger.info("未发现数据列表。")
                    break
                
                today_str = datetime.datetime.now().strftime("%Y-%m-%d")
                found_today = False
                
                # Extract data from current page
                page_data = []
                for item in items:
                    try:
                        link_elem = item.find_element(By.TAG_NAME, "a")
                        title = link_elem.get_attribute("title") or link_elem.text.strip()
                        url = link_elem.get_attribute("href")
                        
                        time_elem = item.find_element(By.CSS_SELECTOR, "p.time")
                        # Text format: "发布时间： 2026-03-06"
                        date_text = time_elem.text.replace("发布时间：", "").strip()
                        
                        page_data.append({
                            "title": title,
                            "url": url,
                            "date": date_text
                        })
                    except Exception as e:
                        logger.warning(f"解析列表项失败: {e}")
                
                # Process Items
                for item in page_data:
                    date_text = item['date']
                    title = item['title']
                    url = item['url']
                    
                    if date_text != today_str:
                        if date_text < today_str:
                            logger.info(f"发现历史数据 ({date_text})，停止该板块抓取。")
                            return # Stop category
                        continue # Skip future date? unlikely
                    
                    found_today = True
                    logger.info(f"正在处理: {title}")
                    
                    content_id = get_md5(clean_title(title))
                    if col_data.find_one({"contentId": content_id}):
                        logger.info("跳过重复。")
                        continue
                    
                    # Enter Detail
                    self.process_detail(content_id, title, url, date_text, category['name'])
                
                if not found_today:
                    logger.info("本页无今日数据，停止翻页。")
                    break
                
                # Next Page
                try:
                    # Find "下页" button
                    next_btn = self.driver.find_element(By.XPATH, "//a[contains(text(),'下页')]")
                    
                    # Check if disabled (usually class 'disabled')
                    if "disabled" in next_btn.get_attribute("class"):
                        logger.info("已到达最后一页。")
                        break
                        
                    self.safe_click(next_btn)
                    page += 1
                    self.random_sleep(2, 4)
                    
                    # Wait for page update (simple way: wait for list to reload)
                    # Since it's likely ajax or page reload, wait a bit
                    
                except:
                    logger.info("未找到下一页按钮或翻页结束。")
                    break
                    
            except Exception as e:
                logger.error(f"列表页处理出错: {e}")
                break

    def process_detail(self, content_id, title, url, date_str, category_name):
        # Open in new tab to preserve list state
        try:
            self.driver.execute_script(f"window.open('{url}', '_blank');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            self.random_sleep(2, 4)
            
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.articleMain")))
            self.simulate_reading()
            
            # Content
            content_div = self.driver.find_element(By.CSS_SELECTOR, "div.a-content")
            detail_html = content_div.get_attribute("innerHTML")
            detail_text = content_div.text
            
            # Attachments
            file_urls = []
            try:
                # Look for <a> tags inside content_div that might be files
                # Or specific structure if known.
                # Generic approach:
                links = content_div.find_elements(By.TAG_NAME, "a")
                for link in links:
                    href = link.get_attribute("href")
                    name = link.text.strip()
                    if href and ("doc" in href or "pdf" in href or "xls" in href or "zip" in href or "rar" in href):
                        file_urls.append({"name": name, "url": href})
            except: pass
            
            # Fields
            budget = extract_budget(detail_text)
            tender_end_time = extract_end_time(detail_text)
            contacts = extract_contacts(detail_text)
            
            # Notice Type
            notice_type = "招标公告"
            if "中标" in category_name or "成交" in category_name or "结果" in category_name:
                notice_type = "中标公告"
            elif "非招标" in category_name:
                notice_type = "采购公告"
            
            # Refine based on title
            if "变更" in title or "更正" in title: notice_type = "更正公告"
            elif "预审" in title: notice_type = "资格预审公告"
            elif "单一来源" in title: notice_type = "单一来源公示"
            
            data = {
                "contentId": content_id,
                "title": title,
                "url": url,
                "source": SOURCE_NAME,
                "createTime": date_str,
                "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "noticeType": notice_type,
                "area": "全国",
                "industry": "综合",
                "budget": budget,
                "tenderEndTime": tender_end_time,
                "purchaser": None,
                "agent": None,
                "purchaseMethod": None,
                "winningBidder": None,
                "winningAmount": None,
                "briefText": detail_text[:200] if detail_text else "",
                "detail": detail_html,
                "hasAnnex": len(file_urls) > 0, 
                "fileUrl": file_urls,
                "contacts": contacts,
                "keywords": None,
                "highlightedWords": None,
                "budget_label": None,
                "tags": None,
                "category": None,
                "onclick": None
            }
            
            col_data.insert_one(data)
            logger.info(f"保存成功: {title}")
            save_log("INFO", "数据已保存", title=title, content_id=content_id)
            
        except Exception as e:
            logger.error(f"详情提取出错: {e}")
            save_log("ERROR", "详情提取失败", str(e), title=title, content_id=content_id)
        finally:
            # Close tab
            if len(self.driver.window_handles) > 1:
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])

if __name__ == "__main__":
    spider = SinochemCrawler()
    spider.run()
