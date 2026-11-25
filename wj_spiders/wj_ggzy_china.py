
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

SOURCE_NAME = "全国公共资源交易平台"
BASE_URL = "https://www.ggzy.gov.cn/deal/dealList.html"

# ==========================================
# Setup Logging
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GGZYSpider:
    def __init__(self):
        self.init_db()
        self.init_driver()
        self.today = datetime.date.today()
        # self.today = datetime.date(2026, 3, 3) # Debugging

    def init_db(self):
        try:
            self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            self.client.server_info()
            self.db = self.client[DB_NAME]
            self.collection = self.db[COLLECTION_NAME]
            self.log_collection = self.db[LOG_COLLECTION_NAME]
            logger.info("MongoDB connected successfully.")
        except errors.ServerSelectionTimeoutError:
            logger.error("MongoDB connection failed.")
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
        s_title = title.strip()
        s_title = re.sub(r'[【】\[\]（）\-]', '', s_title)
        s_title = re.sub(r'\s+', '', s_title) 
        s_title = s_title.lower()
        return hashlib.md5(s_title.encode('utf-8')).hexdigest()

    def is_today(self, date_str):
        date_str = date_str.strip()
        if "昨天" in date_str or "前天" in date_str or "天前" in date_str:
            return False
        if "刚刚" in date_str or "分钟前" in date_str or "小时前" in date_str or "秒前" in date_str:
            return True
        try:
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

    def crawl_detail(self, url, basic_info):
        try:
            self.random_sleep(2.0, 4.0)
            try:
                # Wait for detail content. GGZY usually has iframe or div with content.
                # Based on provided detail.html: <div class="detailShow" id="show0202">...</div>
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.detailShow")))
            except TimeoutException:
                self.log_event("WARNING", f"等待详情页内容超时: {url}", {"url": url})
                return None

            self.simulate_reading()

            # Switch to iframe if present (common in GGZY)
            iframe = None
            try:
                iframe = self.driver.find_element(By.CSS_SELECTOR, "div.detailShow iframe")
                self.driver.switch_to.frame(iframe)
            except: pass

            content_elem = self.driver.find_element(By.TAG_NAME, "body")
            detail_html = content_elem.get_attribute('outerHTML')
            detail_text = content_elem.text
            
            # Switch back if iframe was used
            if iframe:
                self.driver.switch_to.default_content()

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
                    r'(递交|提交).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}[:时][\d]{1,2}分?)?)',
                    r'(投标|响应).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}[:时][\d]{1,2}分?)?)',
                    r'(开标时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}[:时][\d]{1,2}分?)?)',
                    r'([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}[:时][\d]{1,2}分?)?).*?截止'
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

            # Attachment Extraction (New)
            file_urls = []
            try:
                # Based on user snippet: <ul class="fjxx">...<a href="...">...</a>...</ul>
                attachment_links = self.driver.find_elements(By.CSS_SELECTOR, ".fjxx a")
                for link in attachment_links:
                    href = link.get_attribute("href")
                    if href:
                        href = href.strip()
                        if href not in file_urls:
                            file_urls.append(href)
            except Exception as e:
                self.log_event("WARNING", f"附件链接提取失败: {e}")

            # Winning Bidder & Amount Extraction (New)
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

            # 9. Extract Contacts (New: Array of Objects)
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

                # 2. Fallback Match (If no pairs found)
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
                "hasAnnex": "附件" in detail_text or "download" in detail_html or len(file_urls) > 0,
                "tenderEndTime": tender_end_time,
                "fileUrl": file_urls,
                "winningBidder": winning_bidder,
                "winningAmount": winning_amount,
                "contacts": contacts
            }
        except Exception as e:
            self.log_event("ERROR", f"详情页采集失败: {url} - {e}", {"url": url, "error": str(e)})
            return None

    def run(self):
        self.log_event("INFO", "爬虫启动。", {"source": SOURCE_NAME})
        
        # Define target categories: Engineering Construction (01) and Government Procurement (02)
        # Based on filter.html structure
        target_categories = [
            {"name": "工程建设", "id": "choose_classify_01", "code": "01"},
            {"name": "政府采购", "id": "choose_classify_02", "code": "02"}
        ]

        for category in target_categories:
            self.log_event("INFO", f"=== 开始采集业务类型: {category['name']} ===")
            try:
                self.crawl_category(category)
            except Exception as e:
                self.log_event("ERROR", f"业务类型采集异常: {category['name']} - {e}", {"error": str(e)})
            
            self.random_sleep(3.0, 5.0)

    def crawl_category(self, category):
        self.driver.get(BASE_URL)
        self.random_sleep(3.0, 5.0)

        # 1. Select "Today" (当天)
        try:
            time_elem = self.driver.find_element(By.LINK_TEXT, "当天")
            if "toggle" not in time_elem.find_element(By.XPATH, "./..").get_attribute("class"):
                actions = ActionChains(self.driver)
                actions.move_to_element(time_elem).pause(random.uniform(0.3, 0.7)).click().perform()
                self.random_sleep(1.5, 2.5)
        except Exception as e:
            self.log_event("WARNING", f"设置'当天'筛选失败: {e}")

        # 2. Select Business Type (业务类型)
        try:
            type_elem = self.driver.find_element(By.ID, category['id'])
            if "toggle" not in type_elem.get_attribute("class"):
                actions = ActionChains(self.driver)
                actions.move_to_element(type_elem).pause(random.uniform(0.3, 0.7)).click().perform()
                self.random_sleep(1.5, 2.5)
        except Exception as e:
            self.log_event("WARNING", f"设置业务类型 {category['name']} 失败: {e}")
            return

        # 3. Click Search Button to Refresh (New Requirement)
        try:
            search_btn = self.driver.find_element(By.ID, "searchButton")
            actions = ActionChains(self.driver)
            actions.move_to_element(search_btn).pause(random.uniform(0.3, 0.7)).click().perform()
            self.log_event("INFO", f"已点击搜索按钮刷新列表 ({category['name']})")
            self.random_sleep(2.0, 4.0)
        except Exception as e:
            self.log_event("WARNING", f"点击搜索按钮失败: {e}")
            return

        # Wait for list to load
        try:
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "publicont")))
        except TimeoutException:
            self.log_event("INFO", f"{category['name']}: 无今日数据或加载超时。")
            return

        consecutive_non_today_pages = 0
        page_num = 1
        
        while True:
            self.log_event("INFO", f"正在扫描 {category['name']} 第 {page_num} 页...")
            
            items = self.driver.find_elements(By.CLASS_NAME, "publicont")
            if not items:
                self.log_event("WARNING", "未找到列表项。")
                break

            today_items_count = 0
            
            for i in range(len(items)):
                items = self.driver.find_elements(By.CLASS_NAME, "publicont")
                if i >= len(items): break
                item = items[i]
                
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                    
                    # Extract List Info
                    # <h4><a href="..." title="..." target="_blank">...</a><span class="span_o">2026-03-03</span></h4>
                    h4_elem = item.find_element(By.TAG_NAME, "h4")
                    a_elem = h4_elem.find_element(By.TAG_NAME, "a")
                    title = a_elem.get_attribute("title").strip()
                    url = a_elem.get_attribute("href")
                    
                    date_span = h4_elem.find_element(By.CLASS_NAME, "span_o")
                    date_str = date_span.text.strip()
                    
                    if not self.is_today(date_str):
                        continue
                        
                    today_items_count += 1
                    
                    # Deduplication
                    content_id = self.generate_content_id(title)
                    if self.collection.find_one({'contentId': content_id}):
                        self.log_event("INFO", f"跳过已存在: {title}")
                        continue

                    # Extract Meta from <p class="p_tw">
                    # <span>省份：</span><span class="span_on">江西省</span>...
                    meta_p = item.find_element(By.CLASS_NAME, "p_tw")
                    meta_text = meta_p.text
                    
                    area = ""
                    notice_type = "" # 信息类型
                    industry = "" # 行业
                    
                    # Parse meta text manually or via regex
                    # Example: 省份：江西省来源平台：...业务类型：...信息类型：中标公告
                    if "省份：" in meta_text:
                        area = meta_text.split("省份：")[1].split("来源平台")[0].strip()
                    if "信息类型：" in meta_text:
                        # Find text after "信息类型：" until next label or end
                        # This is tricky without strict delimiters, try splitting
                        parts = meta_text.split("信息类型：")[1]
                        # Check for "行业：" which might follow
                        if "行业：" in parts:
                            notice_type = parts.split("行业：")[0].strip()
                            industry = parts.split("行业：")[1].strip()
                        else:
                            notice_type = parts.strip()

                    # Click Logic
                    main_window = self.driver.current_window_handle
                    a_elem.click()
                    self.random_sleep(1.0, 2.0)
                    
                    if len(self.driver.window_handles) > 1:
                        self.driver.switch_to.window(self.driver.window_handles[-1])
                        detail_data = self.crawl_detail(self.driver.current_url, {})
                        self.driver.close()
                        self.driver.switch_to.window(main_window)
                    else:
                        detail_data = self.crawl_detail(self.driver.current_url, {})
                        self.driver.back()
                        self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "publicont")))

                    if detail_data:
                        data = {
                            "contentId": content_id,
                            "title": title,
                            "url": url,
                            "source": SOURCE_NAME,
                            "createTime": str(self.today),
                            "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "noticeType": notice_type, # Using "信息类型" as noticeType
                            "area": area,
                            "industry": industry, # New field as requested
                            "budget": detail_data.get('budget'),
                            "tenderEndTime": detail_data.get('tenderEndTime'),
                            "briefText": detail_data.get('briefText'),
                            "detail": detail_data.get('detail'),
                            "hasAnnex": detail_data.get('hasAnnex'),
                            "fileUrl": detail_data.get('fileUrl', []),
                            "winningBidder": detail_data.get('winningBidder'),
                            "winningAmount": detail_data.get('winningAmount'),
                            "contactPerson": detail_data.get('contactPerson'),
                            "contactPhone": detail_data.get('contactPhone')
                        }
                        self.collection.insert_one(data)
                        self.log_event("INFO", f"成功保存: {title}")

                except Exception as e:
                    self.log_event("ERROR", f"处理单条失败: {e}")
                    while len(self.driver.window_handles) > 1:
                        self.driver.switch_to.window(self.driver.window_handles[-1])
                        self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])

            if today_items_count == 0:
                consecutive_non_today_pages += 1
            else:
                consecutive_non_today_pages = 0
            
            if consecutive_non_today_pages >= 2:
                self.log_event("INFO", f"{category['name']} 终止: 连续2页无今日数据。")
                break
                
            self.smooth_scroll_to_bottom()
            self.random_sleep(1.0, 2.0)
            
            # Next Page
            try:
                # Based on paging.html: <a href="javascript:getList(2)" class="a_righta">下一页</a>
                next_btn = self.driver.find_element(By.XPATH, "//a[contains(text(),'下一页')]")
                
                # Check if it's the last page (usually class or style changes, but generic try here)
                # Or check page number input
                
                actions = ActionChains(self.driver)
                actions.move_to_element(next_btn).pause(random.uniform(0.3, 0.8)).click().perform()
                
                self.log_event("INFO", "点击下一页...")
                self.random_sleep(3.0, 5.0)
                
                # Wait for staleness or new content
                # For simplicity in this demo, just wait
                page_num += 1
            except NoSuchElementException:
                self.log_event("INFO", "翻页结束（未找到下一页）。")
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
    spider = GGZYSpider()
    try:
        spider.run()
    finally:
        spider.close()
