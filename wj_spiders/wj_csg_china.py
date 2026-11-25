import time
import datetime
import re
import os
import sys
import logging
import traceback
import hashlib
import random
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from pymongo import MongoClient
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ================= Configuration =================
MONGO_URI = config.MONGO_URI
DB_NAME = config.DB_NAME
COLLECTION_DATA = config.COLLECTION_NAME
COLLECTION_LOG = config.LOG_COLLECTION_NAME

# Crawler Info
CRAWLER_NAME = "wj_csg_china"
SOURCE_NAME = "中国南方电网供应链统一服务平台"
BASE_URL = "https://www.bidding.csg.cn/zbcg/index.jhtml"

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
    """
    Save logs to MongoDB.
    status: "INFO", "ERROR", "WARNING"
    """
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
    """
    Cleaning logic for contentId generation:
    1. Strip spaces.
    2. Remove special chars: 【】[]（）-
    3. Remove all spaces (to match project standard).
    4. Lowercase.
    """
    if not title:
        return ""
    t = title.strip()
    t = re.sub(r'[【】\[\]（）\-]', '', t)
    t = re.sub(r'\s+', '', t)
    return t.lower()

def extract_budget(content):
    """
    Extract budget based on regex rules from documentation.
    """
    patterns = [
        r'(预算金额|预算总金额|项目预算).*?([\d,]+(\.\d+)?).*?(万|元)',
        r'(最高限价|最高限制单价|最高单价限价|限价).*?([\d,]+(\.\d+)?).*?(万|元)',
        r'(采购控制价|控制价).*?([\d,]+(\.\d+)?).*?(万|元)',
        r'(合同估算价|估算价).*?([\d,]+(\.\d+)?).*?(万|元)',
        r'(单价|金额|价格).*?([\d,]+(\.\d+)?).*?(万|元)'
    ]
    for p in patterns:
        match = re.search(p, content)
        if match:
            return match.group(0)
    return None

def extract_end_time(content):
    """
    Extract end time based on regex rules.
    """
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
    """
    Extract contacts as list of objects: [{"name": "...", "phone": "..."}]
    """
    contacts = []
    # 1. Combination Match
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

    # 2. Fallback Single Match
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

class CSGCrawler:
    def __init__(self):
        self.setup_driver()

    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Anti-detection settings
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

    def random_sleep(self, min_sec=2.0, max_sec=5.0):
        """模拟人工随机等待"""
        sleep_time = random.uniform(min_sec, max_sec)
        time.sleep(sleep_time)

    def simulate_reading(self):
        """模拟人工阅读页面：随机滚动"""
        try:
            total_height = self.driver.execute_script("return document.body.scrollHeight")
            viewport_height = self.driver.execute_script("return window.innerHeight")
            current_scroll = 0
            
            # 随机滚动 2-4 次
            scroll_times = random.randint(2, 4)
            for _ in range(scroll_times):
                if current_scroll + viewport_height >= total_height:
                    break
                    
                scroll_step = random.randint(200, 500)
                current_scroll += scroll_step
                self.driver.execute_script(f"window.scrollTo(0, {current_scroll});")
                time.sleep(random.uniform(0.5, 1.5))
                
        except Exception as e:
            pass

    def run(self):
        try:
            logger.info("开始运行爬虫...")
            self.driver.get(BASE_URL)
            save_log("INFO", "爬虫启动", f"打开页面: {BASE_URL}")
            
            # 1. Initial Wait
            self.random_sleep(2, 4) 
            
            # 2. Crawl Pages
            page = 1
            while True:
                logger.info(f"正在抓取第 {page} 页...")
                has_data = self.crawl_list()
                
                if not has_data:
                    logger.info("本页无今日数据或已处理完毕，停止翻页。")
                    break
                
                # Check for next page
                try:
                    next_page = self.driver.find_element(By.LINK_TEXT, "下一页")
                    if "disabled" in next_page.get_attribute("class") or not next_page.is_enabled():
                        logger.info("已到达最后一页。")
                        break
                    
                    next_page.click()
                    self.random_sleep(3, 5) # Wait for page load
                    page += 1
                except:
                    logger.info("未找到下一页按钮，结束。")
                    break

        except Exception as e:
            logger.error(f"严重错误: {e}")
            save_log("ERROR", "严重错误", str(e))
            traceback.print_exc()
        finally:
            self.driver.quit()
            logger.info("爬虫运行结束。")

    def crawl_list(self):
        """
        Crawl current list page.
        Returns: True if should continue to next page, False if should stop.
        """
        try:
            # Wait for list
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.List2 ul li")))
            
            # Get rows
            rows = self.driver.find_elements(By.CSS_SELECTOR, "div.List2 ul li")
            if not rows:
                return False
                
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            found_today = False
            
            for i in range(len(rows)):
                # Re-fetch rows
                rows = self.driver.find_elements(By.CSS_SELECTOR, "div.List2 ul li")
                if i >= len(rows): break
                
                row = rows[i]
                try:
                    # Extract Date: 2026-03-11
                    # Structure: <span class="Right">...<span class="Black14 Gray">2026-03-11</span></span>
                    date_elem = row.find_element(By.CSS_SELECTOR, "span.Right span.Black14.Gray")
                    date_text = date_elem.text.strip()
                    
                    # Date Filter
                    if date_text != today_str:
                        logger.info(f"发现非今日数据: {date_text}")
                        # If list is strictly chronological, we can stop here.
                        # Assuming it is mixed or roughly sorted, we might want to check a few more.
                        # But for efficiency and standard logic:
                        # If we encounter a date < today, we usually stop if sorted.
                        # Let's assume sorted descending.
                        if date_text < today_str:
                             logger.info("日期早于今日，停止翻页。")
                             return False
                        continue
                        
                    found_today = True
                    
                    # Extract Title & Link
                    # Structure: <a href="..." target="_blank">Title...</a>
                    # There are multiple <a> tags in li. The title link is usually the last one or the one with target="_blank"
                    links = row.find_elements(By.TAG_NAME, "a")
                    target_link = None
                    full_title_text = ""
                    
                    for link in links:
                        href = link.get_attribute("href")
                        if href and ("zbhxrgs" in href or "zbgg" in href or "fzbgg" in href) and "index.jhtml" not in href:
                            target_link = link
                            full_title_text = link.text.strip()
                            # If text is truncated (ends with ...), try title attribute or we might need to get it from detail
                            if full_title_text.endswith("..."):
                                title_attr = link.get_attribute("title")
                                if title_attr: full_title_text = title_attr
                            break
                    
                    if not target_link:
                        continue

                    logger.info(f"正在处理: {full_title_text}")
                    
                    # Deduplication
                    stripped_title = clean_title(full_title_text)
                    content_id = get_md5(stripped_title)
                    
                    if col_data.find_one({"contentId": content_id}):
                        logger.info(f"跳过重复数据: {full_title_text}")
                        continue
                    
                    # Click (Open in new tab usually)
                    target_link.click()
                    
                    self.random_sleep(1.5, 3.0)
                    
                    # Process Detail
                    self.process_detail_tab(content_id, full_title_text, date_text)
                    
                    self.random_sleep(1.5, 3.0)
                    
                except Exception as e:
                    logger.error(f"处理第 {i} 行出错: {e}")
                    continue
            
            # If we found at least one today's item, or if all items were today (but maybe duplicates), we continue.
            # If we didn't find any today's item in this whole page, we stop.
            return found_today
            
        except Exception as e:
            logger.error(f"列表抓取出错: {e}")
            return False

    def process_detail_tab(self, content_id, title, date_str):
        original_window = self.driver.current_window_handle
        try:
            # Wait for new window
            WebDriverWait(self.driver, 10).until(EC.number_of_windows_to_be(2))
            
            # Switch
            for window_handle in self.driver.window_handles:
                if window_handle != original_window:
                    self.driver.switch_to.window(window_handle)
                    break
            
            # Wait for content
            self.random_sleep(1.5, 3.0)
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.Content")))
            
            # Simulate Reading
            self.simulate_reading()
            
            current_url = self.driver.current_url
            
            # Extract Content
            content_elem = self.driver.find_element(By.CSS_SELECTOR, "div.Content")
            detail_text = content_elem.text
            detail_html = content_elem.get_attribute("outerHTML")
            
            # Extract Fields
            budget = extract_budget(detail_text)
            tender_end_time = extract_end_time(detail_text)
            contacts = extract_contacts(detail_text)
            
            # Notice Type Mapping
            notice_type = "招标公告"
            if "变更" in title or "修改" in title: notice_type = "更正公告"
            elif "中标" in title or "成交" in title: notice_type = "中标公告"
            elif "废标" in title: notice_type = "废标公告"
            elif "询比" in title: notice_type = "招标公告" # Treat inquiry as tender
            
            # Attachments (Check for links in content)
            file_urls = []
            try:
                # Find all links in content
                alist = content_elem.find_elements(By.TAG_NAME, "a")
                for a in alist:
                    href = a.get_attribute("href")
                    if href and (".pdf" in href or ".doc" in href or ".xls" in href or ".zip" in href or "download" in href):
                        file_urls.append(href)
            except:
                pass

            # Data Object
            data = {
                "contentId": content_id,
                "title": title,
                "url": current_url,
                "source": SOURCE_NAME,
                "createTime": date_str,
                "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "noticeType": notice_type,
                "area": "南方电网覆盖区域", # CSG covers 5 southern provinces
                "industry": "能源电力",
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
            
            # Refine Area/Purchaser
            if "广东" in title or "广州" in title or "深圳" in title: data['area'] = "广东"
            elif "广西" in title: data['area'] = "广西"
            elif "云南" in title: data['area'] = "云南"
            elif "贵州" in title: data['area'] = "贵州"
            elif "海南" in title: data['area'] = "海南"
            
            # Save
            col_data.insert_one(data)
            logger.info(f"保存成功: {title}")
            save_log("INFO", "数据已保存", title=title, content_id=content_id)
            
        except Exception as e:
            logger.error(f"详情页处理出错: {e}")
            save_log("ERROR", "详情页提取失败", str(e), title=title, content_id=content_id)
        finally:
            if len(self.driver.window_handles) > 1:
                self.driver.close()
            self.driver.switch_to.window(original_window)

if __name__ == "__main__":
    crawler = CSGCrawler()
    crawler.run()
