import time
import datetime
import re
import os
import sys
import logging
import traceback
import hashlib
import random
from urllib.parse import urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from pymongo import MongoClient

from selenium.webdriver.common.action_chains import ActionChains
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ================= Configuration =================
MONGO_URI = config.MONGO_URI
DB_NAME = config.DB_NAME
COLLECTION_DATA = config.COLLECTION_NAME
COLLECTION_LOG = config.LOG_COLLECTION_NAME

# Crawler Info
CRAWLER_NAME = "wj_sgcc_china"
SOURCE_NAME = "国家电网新一代电子商务平台"
BASE_URL = "https://ecp.sgcc.com.cn/ecp2.0/portal/#/"

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
        logger.error(f"Failed to save log to MongoDB: {e}")

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

def construct_attachment_url(current_url, content):
    """
    Construct SGCC attachment URL.
    """
    if "下载" in content or "附件" in content:
        parsed = urlparse(current_url)
        params = parse_qs(parsed.query)
        
        # If empty, check if they are in the fragment (after ?)
        if not params and parsed.fragment and '?' in parsed.fragment:
            try:
                fragment_query = parsed.fragment.split('?', 1)[1]
                params = parse_qs(fragment_query)
            except:
                pass
            
        notice_id = params.get('noticeId', [None])[0]
        notice_det_id = params.get('noticeDetId', [None])[0]
        
        if notice_id and notice_det_id:
            return [f"https://ecp.sgcc.com.cn/ecp2.0/ecpwcmcore//index/downLoadBid?noticeId={notice_id}&noticeDetId={notice_det_id}"]
            
    return []

# ================= Main Crawler Class =================

class SGCCCrawler:
    def __init__(self):
        self.setup_driver()

    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Anti-detection settings (copied from wj_ccgp_chongqing.py)
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
            
            # 1. Initial Wait (User requirement: 2-4s)
            self.random_sleep(2, 4) 
            
            # 2. Click "More" (span.yewuspan)
            logger.info("正在点击 '更多'...")
            try:
                # Use class yewuspan as per user input
                more_btn = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "span.yewuspan")))
                more_btn.click()
                self.random_sleep(2, 4) # Wait for page load
            except Exception as e:
                logger.error(f"点击 '更多' 失败: {e}")
                save_log("ERROR", "点击 '更多' 失败", str(e))
                return

            # 3. Click "Tender Announcements"
            logger.info("正在点击 '招标公告'...")
            try:
                tender_link = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[title='招标公告及投标邀请书']")))
                tender_link.click()
                self.random_sleep(2, 4) # Wait for list refresh
            except Exception as e:
                logger.error(f"点击 '招标公告' 失败: {e}")
                save_log("ERROR", "点击 '招标公告' 失败", str(e))
                return

            # 4. Crawl List (Tender Announcements)
            self.crawl_list()
            
            # 5. Switch to Bid Results and Crawl
            logger.info("招标采购公告抓取完毕，准备切换到 '中标（成交）结果公告'...")
            try:
                # Simplify Selector: Find ANY <a> tag containing "中标" and "结果"
                # This avoids issues with changing class names or exact title matches
                bid_result_link = self.wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(), '中标') and contains(text(), '结果')]")))
                
                # Scroll into view
                self.driver.execute_script("arguments[0].scrollIntoView(true);", bid_result_link)
                self.random_sleep(1.0, 2.0)
                
                # Perform Double Click
                logger.info("执行双击操作...")
                try:
                    action = ActionChains(self.driver)
                    action.double_click(bid_result_link).perform()
                except:
                    # Fallback: JS Click (sometimes double click is just 2 clicks)
                    logger.info("双击失败，尝试 JS 点击...")
                    self.driver.execute_script("arguments[0].click();", bid_result_link)
                    self.random_sleep(0.2)
                    self.driver.execute_script("arguments[0].click();", bid_result_link)
                
                self.random_sleep(3, 5) # Wait for list refresh
                
                # Check for refresh logic: 
                # Since the page is SPA (Single Page Application), we need to ensure the list content actually changed or reloaded.
                # A simple way is to wait until the "loading" mask disappears or check if rows are stale.
                # Here we just wait a bit longer and re-fetch rows.
                
                
                # Crawl again
                logger.info("正在抓取中标结果列表...")
                self.crawl_list()
                
            except Exception as e:
                logger.error(f"切换到中标结果失败: {e}")
                save_log("ERROR", "切换中标结果失败", str(e))

        except Exception as e:
            logger.error(f"严重错误: {e}")
            save_log("ERROR", "严重错误", str(e))
            traceback.print_exc()
        finally:
            self.driver.quit()
            logger.info("爬虫运行结束。")

    def crawl_list(self):
        """
        Crawl the current list.
        Returns:
            bool: True if any valid data (Today's data) was found and processed.
                  False if no today's data found.
        """
        has_today_data = False
        try:
            # Wait for table rows
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tbody tr")))
            
            # Wait for potential loading mask to disappear (SGCC might use one)
            # Or just wait a bit for list to stabilize
            self.random_sleep(1.0, 2.0)
            
            # Use today's date from environment or system
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            logger.info(f"目标日期: {today_str}")
            
            # Get initial rows count
            rows = self.driver.find_elements(By.CSS_SELECTOR, "tbody tr")
            logger.info(f"发现 {len(rows)} 行数据。")
            
            # Check if empty or no rows
            if not rows:
                return False
            
            for i in range(len(rows)):
                # Re-fetch rows to prevent stale elements
                rows = self.driver.find_elements(By.CSS_SELECTOR, "tbody tr")
                if i >= len(rows): break
                
                row = rows[i]
                try:
                    # Extract Date (Last TD)
                    tds = row.find_elements(By.TAG_NAME, "td")
                    if not tds: continue
                    
                    date_text = tds[-1].text.strip()
                    
                    # Date Filter: Only Today
                    if date_text != today_str:
                        logger.info(f"跳过非今日数据: {date_text}")
                        # If list is sorted descending, we could stop here, but let's check a few more just in case.
                        continue
                    
                    has_today_data = True # Found at least one today's item
                    
                    # Extract Title
                    title_elem = row.find_element(By.CSS_SELECTOR, "td.title")
                    full_title_text = title_elem.text.strip()
                    
                    logger.info(f"正在处理: {full_title_text}")
                    
                    # Deduplication
                    stripped_title = clean_title(full_title_text)
                    content_id = get_md5(stripped_title)
                    
                    if col_data.find_one({"contentId": content_id}):
                        logger.info(f"跳过重复数据: {full_title_text}")
                        save_log("INFO", "跳过重复数据", title=full_title_text, content_id=content_id)
                        continue
                        
                    # Click to open detail
                    title_elem.click()
                    
                    # Random wait before processing detail
                    self.random_sleep(1.5, 3.0)
                    
                    # Process New Tab
                    self.process_detail_tab(content_id, full_title_text, date_text)
                    
                    # Random wait before next item
                    self.random_sleep(1.5, 3.0)
                    
                except Exception as e:
                    logger.error(f"处理第 {i} 行时出错: {e}")
                    save_log("ERROR", f"第 {i} 行错误", str(e))
                    continue
                    
        except Exception as e:
            logger.error(f"抓取列表时出错: {e}")
            save_log("ERROR", "列表抓取错误", str(e))
            
        return has_today_data

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
            
            # Wait for content load
            self.random_sleep(1.5, 3.0)
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # Simulate Reading
            self.simulate_reading()
            
            current_url = self.driver.current_url
            
            # Extract Detail Content
            # Try finding the specific content div first
            try:
                content_elem = self.driver.find_element(By.ID, "md")
                detail_text = content_elem.text
                detail_html = content_elem.get_attribute("outerHTML")
            except:
                # Fallback to body or a common container if 'md' not found
                detail_text = self.driver.find_element(By.TAG_NAME, "body").text
                detail_html = self.driver.page_source
                
            # Extract Fields
            budget = extract_budget(detail_text)
            tender_end_time = extract_end_time(detail_text)
            contacts = extract_contacts(detail_text)
            file_urls = construct_attachment_url(current_url, detail_text)
            
            # Notice Type Mapping
            notice_type = "招标公告"
            if "变更" in title: notice_type = "更正公告"
            elif "中标" in title or "成交" in title: notice_type = "中标公告"
            elif "废标" in title: notice_type = "废标公告"
            
            # Data Object
            data = {
                "contentId": content_id,
                "title": title,
                "url": current_url,
                "source": SOURCE_NAME,
                "createTime": date_str,
                "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "noticeType": notice_type,
                "area": "全国", 
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
            
            # Extract Purchaser from Title
            match_org = re.search(r'【(.*?)】', title)
            if match_org:
                org_name = match_org.group(1)
                data['purchaser'] = org_name
                if "重庆" in org_name: data['area'] = "重庆"
                elif "北京" in org_name: data['area'] = "北京"
            
            # Save
            col_data.insert_one(data)
            logger.info(f"保存成功: {title}")
            save_log("INFO", "数据已保存", title=title, content_id=content_id)

        except Exception as e:
            logger.error(f"详情页处理出错: {e}")
            save_log("ERROR", "详情页提取失败", str(e), title=title, content_id=content_id)
        finally:
            # Close tab and switch back
            if len(self.driver.window_handles) > 1:
                self.driver.close()
            self.driver.switch_to.window(original_window)

if __name__ == "__main__":
    crawler = SGCCCrawler()
    crawler.run()
