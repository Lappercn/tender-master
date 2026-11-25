
import hashlib
import time
import datetime
import re
import sys
import logging
import random
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from pymongo import MongoClient, errors
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ==========================================
# Configuration & Constants
# ==========================================
MONGO_URI = config.MONGO_URI
DB_NAME = config.DB_NAME
COLLECTION_NAME = config.COLLECTION_NAME
LOG_COLLECTION_NAME = config.LOG_COLLECTION_NAME

SOURCE_NAME = "中国政府采购网"
BASE_URL = "https://search.ccgp.gov.cn/bxsearch"

# ==========================================
# Setup Logging
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CCGPChinaSpider:
    def __init__(self):
        self.init_db()
        self.init_driver()
        self.today = datetime.date.today()
        # self.today = datetime.date(2026, 3, 3) # Debugging for provided sample date

    def init_db(self):
        try:
            self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            self.client.server_info() # Trigger connection check
            self.db = self.client[DB_NAME]
            self.collection = self.db[COLLECTION_NAME]
            self.log_collection = self.db[LOG_COLLECTION_NAME]
            logger.info("MongoDB connected successfully.")
        except errors.ServerSelectionTimeoutError:
            logger.error("MongoDB connection failed. Please ensure MongoDB service is running.")
            sys.exit(1)
        except Exception as e:
            logger.error(f"MongoDB connection failed: {e}")
            sys.exit(1)

    def init_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument('--headless') 
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--start-maximized')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
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
            
            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait = WebDriverWait(self.driver, 20)
        except Exception as e:
            logger.error(f"Failed to initialize Chrome Driver: {e}")
            sys.exit(1)

    def log_event(self, level, message, details=None):
        """
        Log event to both console/file and MongoDB.
        """
        if level == "INFO":
            logger.info(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "ERROR":
            logger.error(message)

        try:
            log_entry = {
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "level": level,
                "message": message,
                "source": SOURCE_NAME,
                "details": details or {}
            }
            self.log_collection.insert_one(log_entry)
        except Exception as e:
            logger.error(f"Failed to write log to MongoDB: {e}")

    def generate_content_id(self, title):
        """MD5(Stripped_Title)"""
        s_title = title.strip()
        s_title = re.sub(r'[【】\[\]（）\-]', '', s_title)
        s_title = re.sub(r'\s+', '', s_title) 
        s_title = s_title.lower()
        return hashlib.md5(s_title.encode('utf-8')).hexdigest()

    def is_today(self, date_str):
        """
        Check if the date string represents today.
        Format: YYYY.MM.DD HH:MM:SS or YYYY-MM-DD
        """
        date_str = date_str.strip()
        
        # 1. Explicit Exclusions
        if "昨天" in date_str or "前天" in date_str or "天前" in date_str:
            return False
            
        # 2. Relative Inclusions
        if "刚刚" in date_str or "分钟前" in date_str or "小时前" in date_str or "秒前" in date_str:
            return True
            
        # 3. Absolute Date Check
        try:
            # Handle YYYY.MM.DD (China GP style) or YYYY-MM-DD
            match = re.search(r'(\d{4})[.-](\d{1,2})[.-](\d{1,2})', date_str)
            if match:
                date_obj = datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                return date_obj == self.today
        except:
            pass
            
        return False

    def random_sleep(self, min_sec=1.5, max_sec=4.0):
        time.sleep(random.uniform(min_sec, max_sec))

    def smooth_scroll_to_bottom(self):
        total_height = self.driver.execute_script("return document.body.scrollHeight")
        current_scroll = 0
        while current_scroll < total_height:
            scroll_step = random.randint(150, 400)
            current_scroll += scroll_step
            self.driver.execute_script(f"window.scrollTo(0, {current_scroll});")
            time.sleep(random.uniform(0.8, 1.5))
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height > total_height:
                total_height = new_height
            if current_scroll >= total_height:
                break

    def simulate_reading(self):
        try:
            total_height = self.driver.execute_script("return document.body.scrollHeight")
            viewport_height = self.driver.execute_script("return window.innerHeight")
            current_scroll = 0
            while current_scroll < total_height:
                scroll_step = random.randint(100, 300)
                current_scroll += scroll_step
                self.driver.execute_script(f"window.scrollTo(0, {current_scroll});")
                time.sleep(random.uniform(0.6, 1.5))
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height > total_height:
                    total_height = new_height
                if current_scroll + viewport_height >= total_height:
                    break
            if random.random() < 0.3:
                scroll_up = random.randint(300, 600)
                self.driver.execute_script(f"window.scrollBy(0, -{scroll_up});")
                time.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            logger.warning(f"Error during reading simulation: {e}")

    def get_notice_types(self):
        """
        Return list of notice types based on '筛选器.html' logic.
        """
        return [
            {"title": "公开招标", "id": "1"},
            {"title": "询价公告", "id": "2"},
            {"title": "竞争性谈判", "id": "3"},
            {"title": "单一来源", "id": "4"},
            {"title": "资格预审", "id": "5"},
            {"title": "邀请公告", "id": "6"},
            {"title": "中标公告", "id": "7"},
            {"title": "更正公告", "id": "8"},
            {"title": "其他公告", "id": "9"},
            {"title": "竞争性磋商", "id": "10"},
            {"title": "成交公告", "id": "11"},
            {"title": "终止公告", "id": "12"}
        ]

    def crawl_detail(self, url, basic_info):
        try:
            self.random_sleep(2.0, 4.0)
            try:
                # Wait for main content area. 'noticeArea' is common in CCGP.
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#noticeArea, .vF_detail_content")))
            except TimeoutException:
                self.log_event("WARNING", f"等待详情页内容超时: {url}", {"url": url})
                return None

            self.simulate_reading()

            content_elem = None
            try:
                content_elem = self.driver.find_element(By.ID, "noticeArea")
            except:
                try:
                    content_elem = self.driver.find_element(By.CLASS_NAME, "vF_detail_content")
                except:
                    content_elem = self.driver.find_element(By.TAG_NAME, "body")

            detail_html = content_elem.get_attribute('outerHTML')
            detail_text = content_elem.text

            # Budget Extraction
            budget = basic_info.get('budget')
            if not budget:
                budget_patterns = [
                    r'(预算金额|预算总金额|项目预算).*?([\d,]+(\.\d+)?).*?(万|元)',
                    r'(最高限价|最高限制单价|最高单价限价|限价).*?([\d,]+(\.\d+)?).*?(万|元)',
                    r'(采购控制价|控制价).*?([\d,]+(\.\d+)?).*?(万|元)',
                    r'(合同估算价|估算价).*?([\d,]+(\.\d+)?).*?(万|元)',
                    r'(单价|金额|价格).*?([\d,]+(\.\d+)?).*?(万|元)'
                ]
                for pattern in budget_patterns:
                    m = re.search(pattern, detail_text)
                    if m:
                        budget = m.group(0)
                        break

            # End Time Extraction
            tender_end_time = ""
            try:
                end_time_patterns = [
                    r'(递交|提交).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}时[\d]{1,2}分)?)',
                    r'(投标|响应).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}时[\d]{1,2}分)?)',
                    r'(开标时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}时[\d]{1,2}分)?)',
                    r'([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}时[\d]{1,2}分)?).*?截止'
                ]
                for pattern in end_time_patterns:
                    m = re.search(pattern, detail_text)
                    if m:
                        if len(m.groups()) >= 3 and m.group(3):
                             tender_end_time = m.group(3).strip()
                        else:
                             tender_end_time = m.group(0).strip()
                        break
            except: pass

            # Extract attachment links
            file_urls = []
            try:
                # 1. Standard CCGP 'bizDownload' links
                attachment_links = self.driver.find_elements(By.CSS_SELECTOR, "a.bizDownload")
                for link in attachment_links:
                    href = link.get_attribute("href")
                    if href:
                        href = href.strip()
                        # Ensure protocol
                        if href.startswith("//"):
                            full_url = "https:" + href
                        elif not href.startswith("http"):
                            full_url = "https://download.ccgp.gov.cn" + href if href.startswith("/") else href
                        else:
                            full_url = href
                        
                        if full_url not in file_urls:
                            file_urls.append(full_url)
                
                # 2. Fallback: Common file extensions (if not covered by bizDownload)
                other_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, '.pdf') or contains(@href, '.doc') or contains(@href, '.zip') or contains(@href, '.rar') or contains(@href, '.xls')]")
                for link in other_links:
                    href = link.get_attribute("href")
                    if href:
                        href = href.strip()
                        if href not in file_urls and "javascript" not in href:
                             file_urls.append(href)

            except: pass

            # Extract Winning Bidder & Amount
            winning_bidder = ""
            winning_amount = ""
            try:
                # Winning Bidder
                bidder_patterns = [
                    r'(中标人|中标单位|成交人|成交供应商|成交单位|供应商名称|中标供应商)[：:]\s*(.+)',
                    r'(中标人名称|成交人名称)[：:]\s*(.+)'
                ]
                for pattern in bidder_patterns:
                    m = re.search(pattern, detail_text)
                    if m:
                        winning_bidder = m.group(2).strip()
                        break
                
                # Winning Amount
                amount_patterns = [
                    r'(中标金额|中标价格|成交金额|成交价格|投标报价|中标价).*?([\d,]+(\.\d+)?).*?(万|元)'
                ]
                for pattern in amount_patterns:
                    m = re.search(pattern, detail_text)
                    if m:
                        winning_amount = m.group(0).strip()
                        break
            except: pass

            # Extract Contacts (New: Array of Objects)
            contacts = []
            try:
                # 1. Combined Match (Priority)
                combined_pattern = r'(项目联系人|联系人|负责人|联系方式)[:：]\s*([\u4e00-\u9fa5]{2,4}).{0,50}?(联系电话|电话|手机)[:：]\s*([\d-]{8,})'
                matches = re.findall(combined_pattern, detail_text, re.DOTALL)
                
                seen = set()
                if matches:
                    for match in matches:
                        p_name = match[1].strip()
                        p_phone = match[3].strip()
                        pair_key = f"{p_name}-{p_phone}"
                        
                        if pair_key not in seen:
                            contacts.append({"name": p_name, "phone": p_phone})
                            seen.add(pair_key)
                
                # 2. Fallback Match (If no pairs found)
                if not contacts:
                    p_name = ""
                    p_phone = ""
                    
                    # Contact Person
                    person_patterns = [r'(项目联系人|联系人|负责人)[：:]\s*([\u4e00-\u9fa5]{2,4})']
                    for pattern in person_patterns:
                        m = re.search(pattern, detail_text)
                        if m:
                            p_name = m.group(2).strip()
                            break
                    
                    # Contact Phone
                    phone_patterns = [r'(联系电话|电话|手机|联系方式)[：:]\s*([\d-]{8,})']
                    for pattern in phone_patterns:
                        m = re.search(pattern, detail_text)
                        if m:
                            p_phone = m.group(2).strip()
                            break
                    
                    if p_name or p_phone:
                        contacts.append({"name": p_name, "phone": p_phone})

            except: pass

            return {
                "detail": detail_html,
                "briefText": detail_text[:200],
                "budget": budget,
                "hasAnnex": len(file_urls) > 0, # Update hasAnnex logic
                "fileUrl": file_urls, # New field: List of attachment URLs
                "tenderEndTime": tender_end_time,
                "winningBidder": winning_bidder,
                "winningAmount": winning_amount,
                "contacts": contacts # New field: List of contact objects
            }
        except Exception as e:
            self.log_event("ERROR", f"详情页采集失败: {url} - {e}", {"url": url, "error": str(e)})
            return None

    def run(self):
        self.log_event("INFO", "爬虫启动。", {"source": SOURCE_NAME})
        notice_types = self.get_notice_types()
        self.log_event("INFO", f"计划采集分类: {[t['title'] for t in notice_types]}")

        for notice_type in notice_types:
            type_id = notice_type['id']
            type_name = notice_type['title']
            
            # Construct URL for specific type
            # start_time and end_time set to today to optimize, or leave empty to crawl naturally
            # Based on spec "Date Filtering", we can use parameters to help, but logic must handle "today" check.
            # URL: ...&bidType={type_id}&...
            today_str = self.today.strftime("%Y:%m:%d") # URL uses colons like 2026:03:03
            
            # Note: The search URL structure is:
            # searchtype=1, page_index=1, bidType=X, start_time=Y, end_time=Y ...
            target_url = f"{BASE_URL}?searchtype=1&page_index=1&bidSort=0&buyerName=&projectId=&pinMu=0&bidType={type_id}&dbselect=bidx&kw=&start_time={today_str}&end_time={today_str}&timeType=0&displayZone=&zoneId=&pppStatus=0&agentName="
            
            self.log_event("INFO", f"=== 开始采集分类: {type_name} ===", {"url": target_url})
            
            try:
                self.crawl_category(target_url, type_name, type_id)
            except Exception as e:
                self.log_event("ERROR", f"分类采集异常: {type_name} - {e}", {"error": str(e)})
            
            self.random_sleep(3.0, 5.0)

    def crawl_category(self, start_url, category_name, type_id):
        self.driver.get(start_url)
        self.random_sleep(3.0, 5.0) # Initial page load wait
        
        # Ensure filters are reset correctly
        # Click "All Categories" (所有类别)
        try:
            # Try more generic selector for filter links
            cat_elem = self.driver.find_element(By.LINK_TEXT, "所有类别")
            if "selected" not in cat_elem.get_attribute("class"):
                actions = ActionChains(self.driver)
                actions.move_to_element(cat_elem).pause(random.uniform(0.2, 0.5)).click().perform()
                self.random_sleep(1.0, 2.0)
        except: pass

        # Click "All Items" (所有品目)
        try:
            item_elem = self.driver.find_element(By.LINK_TEXT, "所有品目")
            if "selected" not in item_elem.get_attribute("class"):
                actions = ActionChains(self.driver)
                actions.move_to_element(item_elem).pause(random.uniform(0.2, 0.5)).click().perform()
                self.random_sleep(1.0, 2.0)
        except: pass

        # Click "Today" (今日)
        # 1. First try LINK_TEXT "今日"
        try:
            time_elem = self.driver.find_element(By.LINK_TEXT, "今日")
            if "selected" not in time_elem.get_attribute("class"):
                actions = ActionChains(self.driver)
                actions.move_to_element(time_elem).pause(random.uniform(0.3, 0.7)).click().perform()
                self.random_sleep(2.5, 4.5) 
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.vT-srch-result-list-bid")))
        except Exception as e:
            # 2. Fallback to CSS Selector or XPath if LINK_TEXT fails (e.g., hidden text or structure change)
            try:
                # Based on typical structure: .timeType a[onclick*='timeType=6'] or similar
                # Or just find by onclick attribute which is more stable than text
                time_elem = self.driver.find_element(By.CSS_SELECTOR, "a[onclick*='timeType=6']")
                if "selected" not in time_elem.get_attribute("class"):
                    actions = ActionChains(self.driver)
                    actions.move_to_element(time_elem).pause(random.uniform(0.3, 0.7)).click().perform()
                    self.random_sleep(2.5, 4.5) 
                    self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.vT-srch-result-list-bid")))
            except Exception as e2:
                self.log_event("WARNING", f"Setting 'Today' filter failed (both methods): {e} | {e2}")
        
        # Check if no results
        try:
            # Sometimes CCGP shows "没有检索到..."
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            if "没有检索到相关内容" in body_text:
                self.log_event("INFO", f"{category_name}: 无今日数据。")
                return
        except: pass

        consecutive_non_today_pages = 0
        page_num = 1
        
        while True:
            self.log_event("INFO", f"正在扫描 {category_name} 第 {page_num} 页...")
            
            try:
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.vT-srch-result-list-bid")))
            except TimeoutException:
                self.log_event("WARNING", "列表容器加载超时，可能无数据。")
                break

            items = self.driver.find_elements(By.CSS_SELECTOR, "ul.vT-srch-result-list-bid li")
            if not items:
                self.log_event("WARNING", "未找到列表项。")
                break

            today_items_count = 0
            
            for i in range(len(items)):
                items = self.driver.find_elements(By.CSS_SELECTOR, "ul.vT-srch-result-list-bid li")
                if i >= len(items): break
                item = items[i]
                
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                    
                    # Extraction
                    link_elem = item.find_element(By.TAG_NAME, "a")
                    title = link_elem.text.strip()
                    url = link_elem.get_attribute("href")
                    
                    # Info span: "2026.03.03 10:53:23 | 采购人..."
                    # The date is the first part of the text content of the span
                    span_text = item.find_element(By.TAG_NAME, "span").text
                    # Split by pipe or just take first 19 chars (YYYY.MM.DD HH:MM:SS)
                    # Using regex to find the date pattern is safer
                    date_match = re.search(r'(\d{4}[.-]\d{2}[.-]\d{2})', span_text)
                    if date_match:
                        date_str = date_match.group(1)
                    else:
                        # Fallback to split
                        date_str = span_text.split('|')[0].strip()
                    
                    # Parse Area/Buyer/Agent if needed from span_text
                    # Area is typically after the type name
                    # Example: ... | 终止公告 | 黑龙江 | ...
                    area = ""
                    parts = span_text.split('|')
                    if len(parts) >= 4:
                        area = parts[-2].strip()

                    if not self.is_today(date_str):
                        continue
                    
                    today_items_count += 1
                    
                    content_id = self.generate_content_id(title)
                    if self.collection.find_one({'contentId': content_id}):
                        self.log_event("INFO", f"跳过已存在: {title}")
                        continue
                    
                    # Click Logic
                    main_window = self.driver.current_window_handle
                    # CCGP usually opens in new tab because of target="_blank"
                    link_elem.click()
                    
                    self.random_sleep(1.0, 2.0)
                    
                    if len(self.driver.window_handles) > 1:
                        self.driver.switch_to.window(self.driver.window_handles[-1])
                        detail_data = self.crawl_detail(self.driver.current_url, {})
                        self.driver.close()
                        self.driver.switch_to.window(main_window)
                    else:
                        # Fallback
                        detail_data = self.crawl_detail(self.driver.current_url, {})
                        self.driver.back()
                        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.vT-srch-result-list-bid")))

                    if detail_data:
                        data = {
                            "contentId": content_id,
                            "title": title,
                            "url": url,
                            "source": SOURCE_NAME,
                            "createTime": str(self.today),
                            "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "noticeType": category_name,
                            "area": area,
                            "budget": detail_data.get('budget'),
                            "tenderEndTime": detail_data.get('tenderEndTime'),
                            "briefText": detail_data.get('briefText'),
                            "detail": detail_data.get('detail'),
                            "hasAnnex": detail_data.get('hasAnnex'),
                            "fileUrl": detail_data.get('fileUrl'), # Save file URLs
                            "winningBidder": detail_data.get('winningBidder'),
                            "winningAmount": detail_data.get('winningAmount'),
                            "contactPerson": detail_data.get('contactPerson'),
                            "contactPhone": detail_data.get('contactPhone')
                        }
                        self.collection.insert_one(data)
                        self.log_event("INFO", f"成功保存: {title}")

                except Exception as e:
                    self.log_event("ERROR", f"处理单条失败: {e}")
                    # Recovery
                    while len(self.driver.window_handles) > 1:
                        self.driver.switch_to.window(self.driver.window_handles[-1])
                        self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])

            if today_items_count == 0:
                consecutive_non_today_pages += 1
            else:
                consecutive_non_today_pages = 0
            
            if consecutive_non_today_pages >= 2:
                self.log_event("INFO", f"{category_name} 终止: 连续2页无今日数据。")
                break
                
            self.smooth_scroll_to_bottom()
            self.random_sleep(1.0, 2.0)
            
            # Next Page
            try:
                next_btn = self.driver.find_element(By.CSS_SELECTOR, "a.next")
                if "javascript:void(0)" in next_btn.get_attribute("href") and not next_btn.get_attribute("onclick"):
                     # Check if really disabled or just JS
                     pass
                
                # Check current page vs next page
                # CCGP pagination: onclick="gopage(N)"
                # Just click "next" class
                
                # Human simulation for clicking next
                actions = ActionChains(self.driver)
                actions.move_to_element(next_btn).pause(random.uniform(0.3, 0.8)).click().perform()
                
                self.log_event("INFO", f"点击下一页，等待加载...")
                # Wait for page reload: wait for list to go stale or explicit wait time
                # Simple robust approach: long sleep + check for list presence
                self.random_sleep(3.0, 5.0) 
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.vT-srch-result-list-bid")))
                
                page_num += 1
            except NoSuchElementException:
                self.log_event("INFO", "翻页结束（未找到下一页按钮）。")
                break
            except TimeoutException:
                self.log_event("WARNING", "翻页后页面加载超时。")
                break
            except Exception as e:
                self.log_event("ERROR", f"翻页错误: {e}")
                break

    def close(self):
        if hasattr(self, 'driver') and self.driver:
            self.driver.quit()
        if hasattr(self, 'client') and self.client:
            self.client.close()

if __name__ == "__main__":
    spider = CCGPChinaSpider()
    try:
        spider.run()
    finally:
        spider.close()
