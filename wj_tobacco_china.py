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
import config

# ==========================================
# Configuration & Constants
# ==========================================
MONGO_URI = config.MONGO_URI
DB_NAME = config.DB_NAME
COLLECTION_NAME = config.COLLECTION_NAME
LOG_COLLECTION_NAME = config.LOG_COLLECTION_NAME

SOURCE_NAME = "中国烟草电子采购平台"
BASE_URL = "https://cgjy.tobacco.com.cn"

# Categories to iterate (Announcement Types)
CATEGORIES = [
    {"name": "招标公告", "url": "https://cgjy.tobacco.com.cn/zbNotice/index.jhtml"},
    {"name": "资格预审公告", "url": "https://cgjy.tobacco.com.cn/zgysgg/index.jhtml"},
    {"name": "变更公告", "url": "https://cgjy.tobacco.com.cn/bgNotice/index.jhtml"},
    {"name": "中标候选人公示", "url": "https://cgjy.tobacco.com.cn/zbhxrgs/index.jhtml"},
    {"name": "结果公告", "url": "https://cgjy.tobacco.com.cn/resultNotice/index.jhtml"}
]

# ==========================================
# Setup Logging
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TobaccoSpider:
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
                self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "wrap")))
            except TimeoutException:
                self.log_event("WARNING", f"等待详情页内容超时: {url}", {"url": url})
                return None

            self.simulate_reading() # Simulate human reading behavior

            # Get Content
            content_elem = self.driver.find_element(By.CLASS_NAME, "wrap")
            detail_html = content_elem.get_attribute('outerHTML')
            detail_text = content_elem.text
            
            # --- Field Extraction Logic (Regex) ---
            
            # 1. Budget
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
                        budget = m.group(0) # Keep context
                        break

            # 2. Tender End Time
            tender_end_time = ""
            try:
                end_time_patterns = [
                    r'(递交|提交).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}[:时][\d]{1,2}分?)?)',
                    r'(投标|响应).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}[:时][\d]{1,2}分?)?)',
                    r'(开标时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}[:时][\d]{1,2}分?)?)',
                    r'(报名).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}[:时][\d]{1,2}分?)?)',
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

            # 3. Purchaser
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

            # 4. Agent
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

            # 5. Purchase Method
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

            # 6. Attachments (fileUrl)
            file_urls = []
            try:
                # Basic link scan for files
                links = self.driver.find_elements(By.TAG_NAME, "a")
                for link in links:
                    href = link.get_attribute("href")
                    if href and any(ext in href.lower() for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar']):
                        if href not in file_urls:
                            file_urls.append(href)
            except: pass

            # 7. Area (Try to extract from detail if missing)
            area = basic_info.get('area', '')
            if not area:
                try:
                    m = re.search(r'(所在地区|行政区域)[：:]\s*(.+)', detail_text)
                    if m:
                        area = m.group(2).strip()
                except: pass

            # 8. Winning Bidder & Amount Extraction (New)
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

            # 9. Extract Contact Person & Phone (New)
            contact_person = ""
            contact_phone = ""
            try:
                # 1. Combined Match (Priority) - to avoid mismatch
                combined_pattern = r'(项目联系人|联系人|负责人|联系方式)[:：]\s*([\u4e00-\u9fa5]{2,4}).{0,50}?(联系电话|电话|手机)[:：]\s*([\d-]{8,})'
                matches = re.findall(combined_pattern, detail_text, re.DOTALL)
                
                if matches:
                    persons = []
                    phones = []
                    seen = set()
                    for match in matches:
                        p_name = match[1].strip()
                        p_phone = match[3].strip()
                        pair_key = f"{p_name}-{p_phone}"
                        if pair_key not in seen:
                            persons.append(p_name)
                            phones.append(p_phone)
                            seen.add(pair_key)
                    
                    if persons:
                        contact_person = " | ".join(persons)
                        contact_phone = " | ".join(phones)

                # 2. Fallback Match
                if not contact_person:
                    # Contact Person
                    person_patterns = [
                        r'(项目联系人|联系人|负责人)[：:]\s*([\u4e00-\u9fa5]{2,4})'
                    ]
                    for pattern in person_patterns:
                        m = re.search(pattern, detail_text)
                        if m:
                            contact_person = m.group(2).strip()
                            break
                    
                    # Contact Phone
                    phone_patterns = [
                        r'(联系电话|电话|手机|联系方式)[：:]\s*([\d-]{8,})'
                    ]
                    for pattern in phone_patterns:
                        m = re.search(pattern, detail_text)
                        if m:
                            contact_phone = m.group(2).strip()
                            break
            except: pass

            return {
                "detail": detail_html,
                "briefText": detail_text[:200],
                "budget": budget,
                "tenderEndTime": tender_end_time,
                "purchaser": purchaser,
                "agent": agent,
                "purchaseMethod": purchase_method,
                "fileUrl": file_urls,
                "hasAnnex": len(file_urls) > 0,
                "area": area,
                "winningBidder": winning_bidder,
                "winningAmount": winning_amount,
                "contactPerson": contact_person,
                "contactPhone": contact_phone
            }
        except Exception as e:
            self.log_event("ERROR", f"详情页采集失败: {url} - {e}", {"url": url, "error": str(e)})
            return None

    def run(self):
        self.log_event("INFO", "爬虫启动。", {"source": SOURCE_NAME})
        
        for category in CATEGORIES:
            self.log_event("INFO", f"=== 开始采集分类: {category['name']} ===")
            try:
                self.crawl_category(category)
            except Exception as e:
                self.log_event("ERROR", f"分类采集异常: {category['name']} - {e}", {"error": str(e)})
            
            self.random_sleep(3.0, 5.0)

    def crawl_category(self, category):
        self.driver.get(category['url'])
        self.random_sleep(3.0, 5.0)
        
        consecutive_non_today_pages = 0
        page_num = 1
        
        while True:
            self.log_event("INFO", f"正在扫描 {category['name']} 第 {page_num} 页...")
            
            try:
                # Wait for list to load
                self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "searchList")))
                list_ul = self.driver.find_element(By.CLASS_NAME, "searchList")
                items = list_ul.find_elements(By.TAG_NAME, "li")
            except TimeoutException:
                self.log_event("WARNING", "列表加载超时或无数据。")
                break

            if not items:
                self.log_event("WARNING", "未找到列表项。")
                break

            today_items_count = 0
            
            for i in range(len(items)):
                # Re-fetch items to avoid StaleElementReferenceException
                try:
                    list_ul = self.driver.find_element(By.CLASS_NAME, "searchList")
                    items = list_ul.find_elements(By.TAG_NAME, "li")
                    if i >= len(items): break
                    item = items[i]
                    
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                    
                    # Extract List Info
                    # Date: <i class="release_date">发布日期: 2026-03-03</i>
                    try:
                        date_text = item.find_element(By.CLASS_NAME, "release_date").text
                        date_str = date_text.replace("发布日期:", "").strip()
                    except:
                        date_str = ""
                    
                    if not self.is_today(date_str):
                        continue
                        
                    today_items_count += 1
                    
                    # Title & Link
                    # <span class="span_hover" title="...">...</span>
                    try:
                        title_span = item.find_element(By.CLASS_NAME, "span_hover")
                        title = title_span.get_attribute("title").strip()
                        link_elem = item.find_element(By.TAG_NAME, "a")
                        href = link_elem.get_attribute("href")
                        if href.startswith("/"):
                            url = BASE_URL + href
                        else:
                            url = href
                    except:
                        continue

                    # Deduplication
                    content_id = self.generate_content_id(title)
                    if self.collection.find_one({'contentId': content_id}):
                        self.log_event("INFO", f"跳过已存在: {title}")
                        continue

                    # Extract Notice Type from Title or Tag
                    # <em class="fuwu">服务</em>
                    notice_type_tag = ""
                    try:
                        em = item.find_element(By.TAG_NAME, "em")
                        notice_type_tag = em.text.strip()
                    except: pass
                    
                    # Click Logic
                    main_window = self.driver.current_window_handle
                    
                    # Open in new tab (target="_blank" is usually default here, but let's control it)
                    # Use JS to open new tab to avoid losing list context
                    self.driver.execute_script(f"window.open('{url}', '_blank');")
                    self.random_sleep(1.0, 2.0)
                    
                    self.driver.switch_to.window(self.driver.window_handles[-1])
                    
                    detail_data = self.crawl_detail(url, {"area": ""}) # Area might not be in list
                    
                    self.driver.close()
                    self.driver.switch_to.window(main_window)

                    if detail_data:
                        data = {
                            "contentId": content_id,
                            "title": title,
                            "url": url,
                            "source": SOURCE_NAME,
                            "createTime": str(self.today),
                            "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "noticeType": category['name'], # Use category as main type
                            "area": detail_data.get('area', ''),
                            "industry": "烟草", 
                            "budget": detail_data.get('budget'),
                            "tenderEndTime": detail_data.get('tenderEndTime'),
                            "briefText": detail_data.get('briefText'),
                            "detail": detail_data.get('detail'),
                            "hasAnnex": detail_data.get('hasAnnex'),
                            "fileUrl": detail_data.get('fileUrl', []),
                            "purchaser": detail_data.get('purchaser'),
                            "agent": detail_data.get('agent'),
                            "purchaseMethod": detail_data.get('purchaseMethod') or notice_type_tag,
                            "winningBidder": detail_data.get('winningBidder'),
                            "winningAmount": detail_data.get('winningAmount'),
                            "contacts": detail_data.get('contacts', [])
                        }
                        self.collection.insert_one(data)
                        self.log_event("INFO", f"成功保存: {title}")

                except Exception as e:
                    self.log_event("ERROR", f"处理单条失败: {e}")
                    # Ensure we are back on main window
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
                # Need to identify next page button. 
                # Common pattern: contains text "下一页" or class "next"
                # If not found, break
                next_btns = self.driver.find_elements(By.XPATH, "//a[contains(text(),'下一页') or contains(text(),'>')]")
                found_next = False
                for btn in next_btns:
                    if "disabled" not in btn.get_attribute("class") and btn.is_displayed():
                        actions = ActionChains(self.driver)
                        actions.move_to_element(btn).pause(random.uniform(0.3, 0.8)).click().perform()
                        found_next = True
                        break
                
                if not found_next:
                    self.log_event("INFO", "翻页结束（未找到下一页或已禁用）。")
                    break
                    
                self.log_event("INFO", "点击下一页...")
                self.random_sleep(3.0, 5.0)
                page_num += 1
            except Exception as e:
                self.log_event("ERROR", f"翻页错误: {e}")
                break

    def close(self):
        if hasattr(self, 'driver') and self.driver:
            self.driver.quit()
        if hasattr(self, 'client') and self.client:
            self.client.close()

if __name__ == "__main__":
    spider = TobaccoSpider()
    try:
        spider.run()
    finally:
        spider.close()
