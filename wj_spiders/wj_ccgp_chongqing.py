
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

SOURCE_NAME = "重庆市政府采购网"
FILTER_HTML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "喂给模型的内容", "重庆公共交易平台", "标讯类型l筛选器.html")

# ==========================================
# Setup Logging
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CCGPChongqingSpider:
    def __init__(self):
        self.init_db()
        self.init_driver()
        self.today = datetime.date.today()
        # self.today = datetime.date(2025, 1, 1) # Debugging line for testing

    def init_db(self):
        try:
            self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            self.client.server_info() # Trigger connection check
            self.db = self.client[DB_NAME]
            self.collection = self.db[COLLECTION_NAME]
            self.log_collection = self.db[LOG_COLLECTION_NAME]
            logger.info("MongoDB connected successfully.")
        except errors.ServerSelectionTimeoutError:
            logger.error("================================================================")
            logger.error("MongoDB 连接失败！请确保 MongoDB 服务已启动。")
            logger.error("错误信息: [WinError 10061] 由于目标计算机积极拒绝，无法连接。")
            logger.error("解决方法: 请先启动 MongoDB 服务 (运行 mongod.exe)。")
            logger.error("================================================================")
            sys.exit(1)
        except Exception as e:
            logger.error(f"MongoDB connection failed: {e}")
            sys.exit(1)

    def init_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument('--headless') # Uncomment for production
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--start-maximized')
        # Anti-detection settings
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

    def generate_content_id(self, title):
        """
        Generate contentId based on specification:
        MD5(Stripped_Title)
        """
        # 1. Strip spaces
        s_title = title.strip()
        # 2. Remove special chars
        s_title = re.sub(r'[【】\[\]（）\-]', '', s_title)
        # 3. Remove all spaces
        s_title = re.sub(r'\s+', '', s_title) 
        # 4. To lower
        s_title = s_title.lower()
        
        return hashlib.md5(s_title.encode('utf-8')).hexdigest()

    def is_today(self, date_str):
        """
        Check if the date string represents today.
        """
        date_str = date_str.strip()
        # 1. Explicit Exclusions
        if "昨天" in date_str:
            return False
        if "前天" in date_str:
            return False
        if "天前" in date_str: # e.g. "3天前"
            return False
            
        # 2. Relative "Today" Inclusions
        if "刚刚" in date_str:
            return True
        if "分钟前" in date_str:
            return True
        if "小时前" in date_str:
            return True
        if "秒前" in date_str:
            return True
            
        # 3. Absolute Date Check
        # Handle YYYY-MM-DD
        try:
            match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', date_str)
            if match:
                date_obj = datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                return date_obj == self.today
        except:
            pass
            
        return False

    def random_sleep(self, min_sec=1.5, max_sec=4.0):
        """Simulate human wait time"""
        sleep_time = random.uniform(min_sec, max_sec)
        time.sleep(sleep_time)

    def smooth_scroll_to_bottom(self):
        """Simulate human scrolling to bottom"""
        total_height = self.driver.execute_script("return document.body.scrollHeight")
        current_scroll = 0
        
        while current_scroll < total_height:
            scroll_step = random.randint(150, 400) # Slowed down
            current_scroll += scroll_step
            self.driver.execute_script(f"window.scrollTo(0, {current_scroll});")
            time.sleep(random.uniform(0.8, 1.5)) # Increased delay
            
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height > total_height:
                total_height = new_height
            
            # Break if reached bottom
            if current_scroll >= total_height:
                break

    def simulate_reading(self):
        """Simulate human reading: slow scroll down, occasional pause/scroll up"""
        try:
            total_height = self.driver.execute_script("return document.body.scrollHeight")
            viewport_height = self.driver.execute_script("return window.innerHeight")
            current_scroll = 0
            
            # Scroll down slowly
            while current_scroll < total_height:
                # Random scroll distance
                scroll_step = random.randint(100, 300)
                current_scroll += scroll_step
                self.driver.execute_script(f"window.scrollTo(0, {current_scroll});")
                
                # Random "reading" pause
                time.sleep(random.uniform(0.6, 1.5))
                
                # Check if height changed (lazy load)
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height > total_height:
                    total_height = new_height
                
                # Stop if reached bottom
                if current_scroll + viewport_height >= total_height:
                    break
            
            # Occasional scroll back up (30% chance) to simulate re-reading
            if random.random() < 0.3:
                scroll_up = random.randint(300, 600)
                self.driver.execute_script(f"window.scrollBy(0, -{scroll_up});")
                time.sleep(random.uniform(1.0, 2.0))
                
        except Exception as e:
            logger.warning(f"Error during reading simulation: {e}")

    def log_event(self, level, message, details=None):
        """
        Log event to both console/file and MongoDB.
        Level: "INFO", "WARNING", "ERROR"
        """
        # 1. Console/File Logging
        if level == "INFO":
            logger.info(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "ERROR":
            logger.error(message)

        # 2. MongoDB Logging
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

    def crawl_detail(self, url, basic_info):
        """
        Crawl detail page.
        """
        try:
            # Switch to the new window
            # original_window = self.driver.current_window_handle # Not used in logic but good context
            
            # Human-like wait for load
            self.random_sleep(2.0, 4.0)

            # Wait for content
            try:
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.wrap-post, div.notice-detail")))
            except TimeoutException:
                self.log_event("WARNING", f"Timeout waiting for detail content: {url}", {"url": url})
                return None
            
            # Simulate Reading Behavior
            self.simulate_reading()
            
            # Extract content (Only keep .wrap-post or .notice-detail as user requested)
            content_elem = None
            try:
                content_elem = self.driver.find_element(By.CSS_SELECTOR, "div.wrap-post") 
            except:
                try:
                    content_elem = self.driver.find_element(By.CSS_SELECTOR, "div.notice-detail")
                except:
                    # Fallback only if strictly necessary, but prefer specific content areas
                    try:
                        content_elem = self.driver.find_element(By.CSS_SELECTOR, "div.notice-content")
                    except:
                        content_elem = self.driver.find_element(By.TAG_NAME, "body")

            detail_html = content_elem.get_attribute('outerHTML')
            detail_text = content_elem.text
            
            # Extract budget with flexible regex
            # Priority: 预算金额 > 最高限价 > 限价 > 价格 > 金额
            budget = basic_info.get('budget')
            if not budget:
                # Regex strategies
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
                        budget = m.group(0) # Keep the full string like "预算金额：1000元" for context
                        break
                        
            # Extract tenderEndTime with flexible regex
            tender_end_time = ""
            try:
                # Patterns for end time
                end_time_patterns = [
                    r'(递交|提交).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?)',
                    r'(投标|响应).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?)',
                    r'(开标时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?)',
                    r'(报名).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?)',
                    r'([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?).*?截止'
                ]
                
                for pattern in end_time_patterns:
                    m = re.search(pattern, detail_text)
                    if m:
                        # Extract the date part specifically if possible, or take the relevant substring
                        # The groups in regex above try to capture the date. 
                        # Let's try to extract just the date string if group 3 or similar exists
                        if len(m.groups()) >= 3 and m.group(3):
                             tender_end_time = m.group(3).strip()
                        else:
                             tender_end_time = m.group(0).strip()
                        break
            except: pass

            # Extract Purchaser (采购人)
            purchaser = ""
            try:
                purchaser_patterns = [
                    r'(采购人|采购单位|招标人|招标单位|需求单位|业主单位|建设单位)[：:]\s*(.+)',
                    r'(采购人名称|招标人名称)[：:]\s*(.+)'
                ]
                for pattern in purchaser_patterns:
                    m = re.search(pattern, detail_text)
                    if m:
                        purchaser = m.group(2).strip()
                        break
            except: pass

            # Extract Agent (代理机构)
            agent = ""
            try:
                agent_patterns = [
                    r'(代理机构|招标代理|招标代理机构|采购代理|采购代理机构|代理单位)[：:]\s*(.+)',
                    r'(代理机构名称)[：:]\s*(.+)'
                ]
                for pattern in agent_patterns:
                    m = re.search(pattern, detail_text)
                    if m:
                        agent = m.group(2).strip()
                        break
            except: pass

            # Extract Purchase Method (采购方式)
            purchase_method = ""
            try:
                method_patterns = [
                    r'(采购方式|招标方式)[：:]\s*(.+)',
                    r'(项目类型)[：:]\s*(.+)'
                ]
                for pattern in method_patterns:
                    m = re.search(pattern, detail_text)
                    if m:
                        purchase_method = m.group(2).strip()
                        break
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
                # 1. Combined Match (Priority) - to avoid mismatch
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

                # 2. Fallback Match
                if not contacts:
                    p_name = ""
                    p_phone = ""
                    
                    # Contact Person
                    person_patterns = [
                        r'(项目联系人|联系人|负责人)[：:]\s*([\u4e00-\u9fa5]{2,4})'
                    ]
                    for pattern in person_patterns:
                        m = re.search(pattern, detail_text)
                        if m:
                            p_name = m.group(2).strip()
                            break
                    
                    # Contact Phone
                    phone_patterns = [
                        r'(联系电话|电话|手机|联系方式)[：:]\s*([\d-]{8,})'
                    ]
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
                "hasAnnex": "附件" in detail_text or "download" in detail_html,
                "tenderEndTime": tender_end_time,
                "purchaser": purchaser,
                "agent": agent,
                "purchaseMethod": purchase_method,
                "winningBidder": winning_bidder,
                "winningAmount": winning_amount,
                "contacts": contacts
            }

        except Exception as e:
            self.log_event("ERROR", f"Error crawling detail {url}: {e}", {"url": url, "error": str(e)})
            return None

    def get_notice_types(self):
        """
        Parse local HTML file to get notice types and URLs.
        Updated: Only return '采购公告'.
        """
        types = []
        target_title = "采购公告"
        
        try:
            if not os.path.exists(FILTER_HTML_PATH):
                self.log_event("ERROR", f"筛选器文件未找到: {FILTER_HTML_PATH}")
                return [{"title": target_title, "url": "https://www.ccgp-chongqing.gov.cn/info-notice/procument-notice"}]

            with open(FILTER_HTML_PATH, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Regex to find links and titles
            # Matches: <a ... href="..." ... > Title </a>
            pattern = r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
            matches = re.findall(pattern, content, re.DOTALL)
            
            for href, title in matches:
                title = title.strip()
                title = re.sub(r'<[^>]+>', '', title).strip() # Clean inner tags
                
                if title != target_title:
                    continue
                
                if not href: continue
                
                if not href.startswith("http") and not href.startswith("//"):
                    full_url = "https://www.ccgp-chongqing.gov.cn" + href
                elif href.startswith("//"):
                    full_url = "https:" + href
                else:
                    full_url = href
                
                types.append({"title": title, "url": full_url})
                break # Found the target, stop looking
            
            if not types:
                self.log_event("WARNING", f"筛选器文件中未找到 '{target_title}'，将使用默认链接。")
                types = [{"title": target_title, "url": "https://www.ccgp-chongqing.gov.cn/info-notice/procument-notice"}]
            
            self.log_event("INFO", f"已锁定采集目标类型: {[t['title'] for t in types]}")
            
        except Exception as e:
            self.log_event("ERROR", f"读取筛选器文件失败: {e}")
            types = [{"title": target_title, "url": "https://www.ccgp-chongqing.gov.cn/info-notice/procument-notice"}]
            
        return types

    def run(self):
        self.log_event("INFO", "爬虫启动。", {"source": SOURCE_NAME})
        
        notice_types = self.get_notice_types()
        self.log_event("INFO", f"确定采集目标分类: {[t['title'] for t in notice_types]}", {"categories": notice_types})
        
        for notice_type in notice_types:
            category_name = notice_type['title']
            target_url = notice_type['url']
            
            self.log_event("INFO", f"=== 开始采集分类: {category_name} ===", {"url": target_url})
            
            try:
                self.crawl_category(target_url, category_name)
            except Exception as e:
                self.log_event("ERROR", f"采集分类 {category_name} 失败: {e}", {"url": target_url, "error": str(e)})
                
            self.random_sleep(3.0, 5.0)

    def crawl_category(self, url, category_name):
        try:
            self.driver.get(url)
        except Exception as e:
            self.log_event("ERROR", f"加载URL失败: {url}, 错误: {e}")
            return

        # Wait for list to load
        try:
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".notice-list")))
        except TimeoutException:
            self.log_event("WARNING", f"等待列表容器超时: {category_name}。跳过该分类。")
            return

        consecutive_non_today_pages = 0
        page_num = 1
        
        while True:
            self.log_event("INFO", f"正在扫描 {category_name} 第 {page_num} 页...")
            
            if page_num > 1 and page_num % random.randint(5, 8) == 0:
                rest_time = random.uniform(8.0, 15.0)
                self.log_event("INFO", f"模拟人工休息 {rest_time:.2f} 秒...")
                time.sleep(rest_time)
            
            # Wait for items
            try:
                self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".notice-list-item")))
            except TimeoutException:
                self.log_event("WARNING", "等待列表项加载超时（可能该页为空）。")
                pass

            items = self.driver.find_elements(By.CSS_SELECTOR, ".notice-list-item")
            if not items:
                self.log_event("WARNING", "该页未发现任何标讯项。")
                break
                
            today_items_count = 0
            
            # Iterate through items by index to avoid staleness
            for i in range(len(items)):
                # Re-fetch items at start of loop iteration
                items = self.driver.find_elements(By.CSS_SELECTOR, ".notice-list-item")
                if i >= len(items): break
                item = items[i]
                
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                    
                    # Extract Basic Info
                    title_elem = item.find_element(By.CSS_SELECTOR, ".list-group-item-heading")
                    title = title_elem.text.strip()
                    
                    date_elem = item.find_element(By.CSS_SELECTOR, ".display-date")
                    date_text = date_elem.text.strip()
                    
                    # Date Check
                    if not self.is_today(date_text):
                        continue
                        
                    today_items_count += 1
                    
                    # Deduplication
                    content_id = self.generate_content_id(title)
                    if self.collection.find_one({'contentId': content_id}):
                        self.log_event("INFO", f"跳过已存在数据: {title}")
                        continue
                        
                    # Extract Metadata
                    area = ""
                    try: area = item.find_element(By.CSS_SELECTOR, ".tag-area").text.strip()
                    except: pass
                    
                    purchase_method = ""
                    try: purchase_method = item.find_element(By.CSS_SELECTOR, ".tag-purchase").text.strip()
                    except: pass
                    
                    buyer = ""
                    try: 
                        buyer_text = item.find_element(By.CSS_SELECTOR, ".buyer").text
                        # Use regex to handle "采购人:" or "采购人：" with optional spaces
                        buyer = re.sub(r'采购人[：:]\s*', '', buyer_text).strip()
                    except: pass
                    
                    agent = ""
                    try: 
                        agent_text = item.find_element(By.CSS_SELECTOR, ".agency").text
                        # Use regex to handle "代理机构:" or "代理机构：" with optional spaces
                        agent = re.sub(r'代理机构[：:]\s*', '', agent_text).strip()
                    except: pass
                    
                    # Click Logic
                    main_window = self.driver.current_window_handle
                    
                    try:
                        actions = ActionChains(self.driver)
                        actions.move_to_element(title_elem).pause(random.uniform(0.1, 0.3)).click().perform()
                    except:
                        self.driver.execute_script("arguments[0].click();", title_elem)
                    
                    self.random_sleep(1.0, 2.0)
                    
                    # Handle Windows/Tabs
                    if len(self.driver.window_handles) > 1:
                        self.driver.switch_to.window(self.driver.window_handles[-1])
                        current_url = self.driver.current_url
                        
                        detail_data = self.crawl_detail(current_url, {"budget": None})
                        
                        self.driver.close()
                        self.driver.switch_to.window(main_window)
                    else:
                        # SPA fallback (unlikely for this site but handled)
                        time.sleep(2)
                        current_url = self.driver.current_url
                        detail_data = self.crawl_detail(current_url, {"budget": None})
                        self.driver.back()
                        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".notice-list")))

                    if detail_data:
                        data = {
                            "contentId": content_id,
                            "title": title,
                            "url": current_url, 
                            "source": SOURCE_NAME, 
                            "createTime": str(self.today),
                            "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "noticeType": category_name,
                            "area": area,
                            "budget": detail_data.get('budget'),
                            "tenderEndTime": detail_data.get('tenderEndTime'),
                            "tenderees": detail_data.get('purchaser') or buyer,
                            "agent": detail_data.get('agent') or agent,
                            "briefText": detail_data.get('briefText'),
                            "detail": detail_data.get('detail'),
                            "hasAnnex": detail_data.get('hasAnnex'),
                            "purchaser": detail_data.get('purchaser') or buyer,
                            "purchaseMethod": detail_data.get('purchaseMethod') or purchase_method,
                            "winningBidder": detail_data.get('winningBidder'),
                            "winningAmount": detail_data.get('winningAmount'),
                            "contacts": detail_data.get('contacts', [])
                        }
                        
                        self.collection.insert_one(data)
                        self.log_event("INFO", f"成功保存数据: {title}")
                        
                except Exception as e:
                    self.log_event("ERROR", f"处理列表项失败: {e}", {"error": str(e)})
                    # Recovery
                    while len(self.driver.window_handles) > 1:
                        self.driver.switch_to.window(self.driver.window_handles[-1])
                        self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])

            # Pagination Check
            if today_items_count == 0:
                consecutive_non_today_pages += 1
            else:
                consecutive_non_today_pages = 0
                
            if consecutive_non_today_pages >= 2:
                self.log_event("INFO", f"{category_name} 终止条件达成: 连续2页无今日标讯。")
                break
            
            self.smooth_scroll_to_bottom()
            self.random_sleep(1.0, 2.0)

            # Next Page
            try:
                next_btn = self.driver.find_element(By.XPATH, "//ul[contains(@class,'pagination')]//a[contains(text(),'下一页')]")
                parent_li = next_btn.find_element(By.XPATH, "./..")
                
                if "disabled" in parent_li.get_attribute("class"):
                    self.log_event("INFO", "已到达最后一页。")
                    break
                
                try:
                    actions = ActionChains(self.driver)
                    actions.move_to_element(next_btn).pause(random.uniform(0.2, 0.5)).click().perform()
                except:
                    self.driver.execute_script("arguments[0].click();", next_btn)
                    
                time.sleep(2)
                self.random_sleep(1.0, 3.0)
                page_num += 1
                
            except NoSuchElementException:
                self.log_event("INFO", "未找到下一页按钮，翻页结束。")
                break
            except Exception as e:
                self.log_event("ERROR", f"翻页操作失败: {e}")
                break

    def close(self):
        if hasattr(self, 'driver') and self.driver:
            self.driver.quit()
        if hasattr(self, 'client') and self.client:
            self.client.close()

if __name__ == "__main__":
    spider = CCGPChongqingSpider()
    try:
        spider.run()
    finally:
        spider.close()
