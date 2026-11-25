import time
import json
import random
import datetime
import hashlib
import re
import logging
import base64
import requests
import os
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import pymongo
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        # logging.FileHandler('spider.log', encoding='utf-8') # Optional
    ]
)
logger = logging.getLogger(__name__)

# ================= Configuration =================
MONGO_URI = config.MONGO_URI
DB_NAME = config.DB_NAME
COLLECTION_NAME = config.COLLECTION_NAME
LOG_COLLECTION_NAME = config.LOG_COLLECTION_NAME

# YesCaptcha Configuration
YESCAPTCHA_CLIENT_KEY = config.YESCAPTCHA_CLIENT_KEY
YESCAPTCHA_API_URL = config.YESCAPTCHA_API_URL

# ================= YesCaptcha Solver =================
class YesCaptchaSolver:
    def __init__(self, client_key):
        self.client_key = client_key

    def solve_image_text(self, base64_img):
        """
        Solve image text captcha using YesCaptcha API.
        """
        try:
            # 1. Create Task
            create_task_url = f"{YESCAPTCHA_API_URL}/createTask"
            data = {
                "clientKey": self.client_key,
                "task": {
                    "type": "ImageToTextTask",
                    "body": base64_img
                }
            }
            
            resp = requests.post(create_task_url, json=data, timeout=10)
            resp_json = resp.json()
            
            if resp_json.get("errorId") != 0:
                logger.error(f"YesCaptcha CreateTask Error: {resp_json}")
                return None
                
            task_id = resp_json.get("taskId")
            if not task_id:
                logger.error("YesCaptcha No TaskID returned")
                return None
                
            # 2. Get Result (Polling)
            get_result_url = f"{YESCAPTCHA_API_URL}/getTaskResult"
            for _ in range(10): # Try 10 times
                time.sleep(1)
                resp = requests.post(get_result_url, json={"clientKey": self.client_key, "taskId": task_id}, timeout=10)
                result_json = resp.json()
                
                if result_json.get("status") == "ready":
                    text = result_json.get("solution", {}).get("text")
                    logger.info(f"YesCaptcha Result: {text}")
                    return text
                
                if result_json.get("errorId") != 0:
                    logger.error(f"YesCaptcha GetResult Error: {result_json}")
                    return None
            
            logger.error("YesCaptcha Timeout")
            return None
            
        except Exception as e:
            logger.error(f"YesCaptcha Exception: {e}")
            return None

# ================= Main Spider Class =================

class CFCPNSpider:
    def __init__(self):
        self.setup_driver()
        self.setup_db()
        self.captcha_solver = YesCaptchaSolver(YESCAPTCHA_CLIENT_KEY)
        self.today = datetime.date.today()

    def setup_driver(self):
        options = Options()
        # 启用无头模式 (服务器环境必须)
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
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
            
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 20)

    def setup_db(self):
        try:
            self.client = pymongo.MongoClient(MONGO_URI)
            self.db = self.client[DB_NAME]
            self.collection = self.db[COLLECTION_NAME]
            self.log_collection = self.db[LOG_COLLECTION_NAME]
            # Ensure index for deduplication
            self.collection.create_index("contentId", unique=True)
            logger.info("MongoDB connected.")
        except Exception as e:
            logger.error(f"MongoDB connection failed: {e}")
            raise

    def log_event(self, level, message, context=None):
        """
        Log event to both Console and MongoDB
        """
        # Console
        if level == "INFO":
            logger.info(message)
        elif level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
            
        # MongoDB
        try:
            log_entry = {
                "level": level,
                "message": message,
                "timestamp": datetime.datetime.now(),
                "spider": "wj_cfcpn_china",
                "context": context or {}
            }
            self.log_collection.insert_one(log_entry)
        except Exception as e:
            logger.error(f"Failed to write log to DB: {e}")

    def random_sleep(self, min_s=1.5, max_s=3.0):
        time.sleep(random.uniform(min_s, max_s))

    def get_md5(self, text):
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def clean_title(self, title):
        """
        Spec:
        1. Trim spaces
        2. Remove special chars 【】[]（）-
        3. Lowercase
        """
        if not title: return ""
        title = title.strip()
        title = re.sub(r"[【】\[\]（）\-\s]", "", title)
        return title.lower()

    # ================= Login Logic =================
    def login(self):
        login_url = "http://www.cfcpn.com/jcw/supplierLogin"
        max_retries = 5
        
        for attempt in range(max_retries):
            try:
                logger.info(f"尝试登录 (第 {attempt+1} 次)...")
                self.driver.get(login_url)
                
                # Try to click "Supplier Login" tab if exists, to be safe
                try:
                    supplier_tab = self.driver.find_element(By.XPATH, "//*[contains(text(), '供应商登录')]")
                    if supplier_tab.is_displayed():
                        supplier_tab.click()
                        self.random_sleep(0.5, 1.0)
                except:
                    pass

                self.wait.until(EC.presence_of_element_located((By.ID, "username")))
                
                # Fill Username & Password
                user_input = self.driver.find_element(By.ID, "username")
                pass_input = self.driver.find_element(By.ID, "password")
                
                user_input.clear()
                user_input.send_keys(config.CFCPN_USERNAME or os.getenv("CFCPN_USERNAME", "YOUR_CFCPN_USERNAME"))
                
                pass_input.clear()
                pass_input.send_keys(config.CFCPN_PASSWORD or os.getenv("CFCPN_PASSWORD", "YOUR_CFCPN_PASSWORD"))
                
                # Handle Captcha
                captcha_input = self.driver.find_element(By.ID, "validateCode")
                captcha_img = self.driver.find_element(By.CSS_SELECTOR, "img.validateImg")
                
                # Get Screenshot of captcha
                # Option 1: Screenshot element
                img_base64 = captcha_img.screenshot_as_base64
                
                # Solve
                code = self.captcha_solver.solve_image_text(img_base64)
                if not code:
                    logger.warning("验证码识别失败，刷新重试...")
                    self.driver.refresh()
                    continue
                    
                captcha_input.clear()
                captcha_input.send_keys(code)
                
                self.random_sleep(1, 2)
                
                # Click Login
                login_btn = self.driver.find_element(By.ID, "sign")
                login_btn.click()
                
                # Check Login Success
                # Wait for redirection or error
                self.random_sleep(3, 5)
                
                current_url = self.driver.current_url
                if "login" not in current_url:
                    logger.info("登录成功！")
                    return True
                
                # Check for error message
                try:
                    error_msg = self.driver.find_element(By.ID, "errorMsg") # Hypothetical ID, or check alert
                    # Actually spec/html doesn't show error msg element clearly, might be alert
                    alert = self.driver.switch_to.alert
                    if alert:
                        logger.warning(f"登录失败提示: {alert.text}")
                        alert.accept()
                except:
                    pass
                    
                logger.warning("登录未跳转，可能失败，重试...")
                
            except Exception as e:
                logger.error(f"登录异常: {e}")
                
        return False

    # ================= Crawling Logic =================
    def is_today(self, date_str):
        """
        Date Filter Logic based on Spec
        """
        if not date_str: return False
        date_str = date_str.strip()
        
        # 1. Negative Filter
        if any(x in date_str for x in ["昨天", "前天", "天前"]):
            return False
            
        # 2. Relative Include
        if any(x in date_str for x in ["刚刚", "分钟前", "小时前", "秒前"]):
            return True
            
        # 3. Absolute Date
        # Format: 2026-03-14 10:05:51 -> 2026-03-14
        try:
            # Extract YYYY-MM-DD
            match = re.search(r"(\d{4}-\d{2}-\d{2})", date_str)
            if match:
                d_str = match.group(1)
                d_obj = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
                return d_obj == self.today
        except:
            pass
            
        return False

    def crawl_list(self):
        categories = [
            {"id": "cggg", "name": "采购公告"},
            {"id": "zjgg", "name": "征集公告"},
            {"id": "jggg", "name": "结果公告"},
            {"id": "gzgg", "name": "更正公告"}
        ]
        
        for cat in categories:
            self.crawl_category(cat["id"], cat["name"])
            logger.info(f"分类 {cat['name']} 采集完成，等待切换下一个分类...")
            self.random_sleep(5, 8)
            
    def crawl_category(self, column_id, notice_type_name):
        logger.info(f"开始采集分类: {notice_type_name} ({column_id})")
        target_url = f"http://www.cfcpn.com/jcw/sys/index/goUrl?url=modules/sys/login/list&column={column_id}"
        self.driver.get(target_url)
        self.random_sleep(3, 5)
        
        self.consecutive_no_today_pages = 0
        page = 1
        while True:
            logger.info(f"正在扫描 {notice_type_name} 第 {page} 页...")
            
            try:
                # Wait for list
                self.wait.until(EC.presence_of_element_located((By.ID, "noticeUl")))
                
                items = self.driver.find_elements(By.CSS_SELECTOR, "div.cfcpn-list-main")
                if not items:
                    logger.warning("未找到列表项")
                    break
                    
                today_items_count = 0
                
                # Store window handle
                main_window = self.driver.current_window_handle
                
                for item in items:
                    try:
                        title_tag = item.find_element(By.CSS_SELECTOR, "a.cfcpn-notice-title")
                        date_tag = item.find_element(By.CSS_SELECTOR, "h6.cfcpn-list-date")
                        
                        title = title_tag.get_attribute("title") or title_tag.text
                        date_str = date_tag.text.strip()
                        
                        if not self.is_today(date_str):
                            continue
                            
                        today_items_count += 1
                        
                        # Check Dedup
                        content_id = self.get_md5(self.clean_title(title))
                        if self.collection.find_one({"contentId": content_id}):
                            logger.info(f"跳过重复: {title}")
                            continue
                            
                        logger.info(f"发现今日标讯: {title} ({date_str})")
                        
                        # Click to open detail
                        # It uses onclick="noticeDetail(...)".
                        # Spec says "新开标签页".
                        # We can click or execute script.
                        # Clicking might be intercepted by anchor href="javascript:void(0)".
                        self.driver.execute_script("arguments[0].click();", title_tag)
                        
                        self.random_sleep(2, 3)
                        
                        # Switch to new window
                        new_window = None
                        for handle in self.driver.window_handles:
                            if handle != main_window:
                                new_window = handle
                                break
                                
                        if new_window:
                            self.driver.switch_to.window(new_window)
                            self.process_detail(content_id, title, date_str, notice_type_name)
                            self.driver.close()
                            self.driver.switch_to.window(main_window)
                            
                            # Random sleep after each detail collection
                            self.random_sleep(3, 6)
                        else:
                            logger.warning("未检测到新窗口打开")
                            
                        self.random_sleep(1.5, 3.0) # Spec requirement
                        
                    except Exception as e:
                        logger.error(f"处理列表项失败: {e}")
                        continue
                
                if today_items_count == 0:
                    self.consecutive_no_today_pages += 1
                    logger.info(f"{notice_type_name} 第 {page} 页无今日数据 (连续 {self.consecutive_no_today_pages} 页)")
                    if self.consecutive_no_today_pages >= 2:
                        logger.info("连续 2 页无今日数据，停止翻页。")
                        break
                else:
                    self.consecutive_no_today_pages = 0

                # Next Page
                try:
                    # Check "Next" button
                    next_li = self.driver.find_element(By.ID, "img_next")
                    # Check if disabled? Class might change or specific attribute.
                    # Usually "disabled" class on li or a.
                    # HTML: <li id="img_next" class="page-item"><a ...>
                    
                    # If we can't find specific disabled class, we assume valid if present.
                    # But we need to check if we are at last page.
                    # Logic: if today_items_count > 0, we try next page.
                    
                    next_btn = next_li.find_element(By.TAG_NAME, "a")
                    self.driver.execute_script("arguments[0].click();", next_btn)
                    
                    self.random_sleep(3, 5)
                    page += 1
                    
                except Exception as e:
                    logger.info("无法点击下一页或已结束。")
                    break
                    
            except Exception as e:
                logger.error(f"页面处理异常: {e}")
                break

    def process_detail(self, content_id, title, date_str, notice_type_name):
        try:
            self.wait.until(EC.presence_of_element_located((By.ID, "detail-new")))
            
            url = self.driver.current_url
            content_html = self.driver.find_element(By.ID, "detail-new").get_attribute("outerHTML")
            detail_text = self.driver.find_element(By.ID, "detail-new").text
            
            # Extract Fields
            # Info Block
            info_block = self.driver.find_elements(By.CSS_SELECTOR, "div.cfcpn-announcements-info-main")
            
            purchaser = ""
            purchase_method = ""
            area = ""
            category = ""
            tags = ""
            
            for info in info_block:
                text = info.text
                if "采购人" in text:
                    purchaser = text.replace("采购人", "").strip()
                elif "采购方式" in text:
                    purchase_method = text.replace("采购方式", "").strip()
                elif "所在地区" in text:
                    area = text.replace("所在地区", "").strip()
                elif "品类" in text:
                    category = text.replace("品类", "").strip()
                elif "标签" in text:
                    tags = text.replace("标签", "").strip()
            
            # Budget & End Time (Regex from Spec)
            budget = self.extract_budget(detail_text)
            end_time = self.extract_end_time(detail_text)
            
            # Contacts (Simple Regex)
            contacts = self.extract_contacts(detail_text)
            
            data = {
                "contentId": content_id,
                "title": title,
                "url": url,
                "source": "金采网",
                "createTime": date_str, # Keep original string for now or normalize
                "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "noticeType": notice_type_name, 
                "area": area,
                "industry": "金融", # Spec says "金融行业"
                "budget": budget,
                "tenderEndTime": end_time,
                "purchaser": purchaser,
                "agent": "",
                "purchaseMethod": purchase_method,
                "winningBidder": "",
                "winningAmount": "",
                "briefText": detail_text[:200].strip(),
                "detail": content_html,
                "hasAnnex": False, # TODO: Check attachment
                "fileUrl": [],
                "contacts": contacts,
                "category": category,
                "tags": tags
            }
            
            # Check Attachments
            # HTML: <div id="file-new"></div> usually populates via JS
            try:
                files_div = self.driver.find_element(By.ID, "file-new")
                links = files_div.find_elements(By.TAG_NAME, "a")
                file_urls = []
                for link in links:
                    href = link.get_attribute("href")
                    if href:
                        file_urls.append(href)
                
                if file_urls:
                    data["hasAnnex"] = True
                    data["fileUrl"] = file_urls
            except:
                pass
                
            # Save
            try:
                self.collection.insert_one(data)
                logger.info(f"保存成功: {title}")
            except pymongo.errors.DuplicateKeyError:
                logger.info(f"重复数据跳过: {title}")
                
        except Exception as e:
            logger.error(f"详情页解析错误: {e}")

    def extract_budget(self, text):
        # Budget extraction logic from spec
        # Keywords priority: 预算金额 > 最高限价 > ...
        patterns = [
            r"(预算金额|预算总金额|项目预算)[:：]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(万|元)",
            r"(最高限价|最高限制单价|最高单价限价|限价)[:：]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(万|元)",
            r"(采购控制价|控制价)[:：]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(万|元)",
            r"(合同估算价|估算价)[:：]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(万|元)",
            r"(单价|金额|价格)[:：]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(万|元)"
        ]
        
        for p in patterns:
            match = re.search(p, text)
            if match:
                return match.group(0) # Return full match string as per spec
        return ""

    def extract_end_time(self, text):
        # End time extraction logic from spec
        # Keywords: 递交截止时间, 投标截止时间, etc.
        keywords = ["递交.*截止时间", "提交.*截止时间", "投标.*截止时间", "响应.*截止时间", "开标时间", "报名.*截止时间"]
        
        # Regex for date time: YYYY年MM月DD日 HH:mm or YYYY-MM-DD HH:mm
        date_pattern = r"(\d{4}[年-]\d{1,2}[月-]\d{1,2}[日]?\s?\d{1,2}[:：]\d{1,2})"
        
        for kw in keywords:
            # Look for keyword + context + date
            # Simplified approach: Find keyword, then look for date in next 50 chars
            kw_match = re.search(kw, text)
            if kw_match:
                start_idx = kw_match.end()
                context = text[start_idx : start_idx + 50]
                date_match = re.search(date_pattern, context)
                if date_match:
                    return date_match.group(1)
        return ""

    def extract_contacts(self, text):
        contacts = []
        # Simple heuristic for Contact Person and Phone
        # Name: 联系人(姓名)?[:：]\s*([\u4e00-\u9fa5]{2,4})
        # Phone: 电话|手机[:：]\s*(\d{11}|[\d-]{10,13})
        
        name_match = re.search(r"联系人(姓名)?[:：]\s*([\u4e00-\u9fa5]{2,4})", text)
        phone_match = re.search(r"(电话|手机)[:：]\s*([0-9\-]+)", text)
        
        if name_match or phone_match:
            contacts.append({
                "name": name_match.group(1) if name_match else "",
                "phone": phone_match.group(2) if phone_match else ""
            })
        return contacts

    def run(self):
        try:
            if self.login():
                self.crawl_list()
            else:
                logger.error("登录最终失败，无法继续。")
        finally:
            self.driver.quit()
            self.client.close()

if __name__ == "__main__":
    spider = CFCPNSpider()
    spider.run()
