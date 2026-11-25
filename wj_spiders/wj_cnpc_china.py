import time
import datetime
import re
import os
import sys
import logging
import traceback
import hashlib
import random
import base64
import json
import requests
import ddddocr
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
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ================= Configuration =================
MONGO_URI = config.MONGO_URI
DB_NAME = config.DB_NAME
COLLECTION_DATA = config.COLLECTION_NAME
COLLECTION_LOG = config.LOG_COLLECTION_NAME

# Crawler Info
CRAWLER_NAME = "wj_cnpc_china"
SOURCE_NAME = "中国石油招标投标网"
BASE_URL = "https://www.cnpcbidding.com"  # Base URL without hash

# YesCaptcha Config (Deprecated, using local ddddocr)
YESCAPTCHA_KEY = config.YESCAPTCHA_CLIENT_KEY

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

def evaluate_math_expression(text):
    """
    Parse and evaluate simple arithmetic expressions from captcha text.
    Handles: "3+5=?", "10-2=", "3x5", "4+7三？", etc.
    """
    if not text:
        return ""
        
    original_text = text
    try:
        # 1. Clean up basic formatting
        text = text.strip().replace(" ", "")
        
        # 2. Handle common noise characters (including Chinese)
        # Replace common OCR misinterpretations of '=' or '?'
        text = text.replace("p", "").replace("P", "").replace("?", "").replace("？", "")
        text = text.replace("=", "").replace("三", "").replace("_", "")
        
        # Replace operators
        text = text.replace("x", "*").replace("X", "*").replace("×", "*").replace("÷", "/")
        
        # 3. Extract valid math expression using Regex
        # Look for: Number (1+ digits) -> Operator (+-*/) -> Number (1+ digits)
        match = re.search(r'(\d+)([\+\-\*\/])(\d+)', text)
        
        if match:
            left_num = match.group(1)
            operator = match.group(2)
            right_num_full = match.group(3)
            
            # Special Handling: If second operand has multiple digits, take only the first one
            # e.g., "6*89" -> "6*8" (assuming simple captcha)
            right_num = right_num_full[0]
            
            # Construct clean expression
            expression = f"{left_num}{operator}{right_num}"
            
            # 4. Evaluate
            result = int(eval(expression))
            
            # Logic Fix: If OCR saw '*' but result is too large (likely OCR mistake for '+')
            # Heuristic: if a*b > 20, assume a+b.
            if '*' in expression and result > 20:
                 text_plus = expression.replace('*', '+')
                 result_plus = int(eval(text_plus))
                 return str(result_plus)

            return str(result)
                
    except Exception as e:
        pass
        
    return original_text

# ================= Captcha Solver =================

class LocalCaptchaSolver:
    def __init__(self):
        self.ocr = ddddocr.DdddOcr(show_ad=False)

    def solve_image_text(self, base64_img):
        """
        Solve image text captcha using ddddocr.
        """
        try:
            img_bytes = base64.b64decode(base64_img)
            res = self.ocr.classification(img_bytes)
            return res
        except Exception as e:
            logger.error(f"DDDDOCR Error: {e}")
            return None

# ================= Main Crawler Class =================

class CNPCCrawler:
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
            self.captcha_solver = LocalCaptchaSolver()
            logger.info("Chrome 驱动初始化成功。")
        except Exception as e:
            logger.error(f"Chrome 驱动初始化失败: {e}")
            sys.exit(1)

    def random_sleep(self, min_sec=1.5, max_sec=5.0):
        time.sleep(random.uniform(min_sec, max_sec))

    def safe_click(self, element):
        """
        Safely click an element, handling overlap/visibility issues.
        """
        try:
            self.wait.until(EC.element_to_be_clickable(element))
            element.click()
        except:
            # Fallback to JS click
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
        except:
            pass

    def check_and_handle_captcha(self, max_retries=3):
        """
        Check if captcha dialog is present and solve it.
        This needs to be called frequently.
        """
        for retry in range(max_retries):
            try:
                # Check for mask first (indicates dialog is active)
                try:
                    mask = self.driver.find_elements(By.CLASS_NAME, "v-modal")
                    if mask and mask[0].is_displayed():
                        logger.info("检测到遮罩层，等待弹窗加载...")
                        self.random_sleep(1.0, 2.0)
                except: pass

                # Quick check for dialog input
                inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[placeholder='验证码']")
                if not inputs:
                    return # No captcha
                
                captcha_input = inputs[0]
                
                # Wait for visibility explicitly
                if not captcha_input.is_displayed():
                    try:
                        WebDriverWait(self.driver, 2).until(EC.visibility_of(captcha_input))
                    except:
                        return # Still not visible
                
                logger.info(f"检测到验证码 (尝试 {retry+1}/{max_retries})...")
                
                # Ensure interactable
                self.wait.until(EC.element_to_be_clickable(captcha_input))
                
                # Find Image
                imgs = self.driver.find_elements(By.CSS_SELECTOR, "img[src^='data:image']")
                target_img = None
                for img in imgs:
                    if img.is_displayed():
                        target_img = img
                        break
                
                if not target_img:
                    logger.error("未找到验证码图片")
                    return
                    
                # Get Base64
                src = target_img.get_attribute("src")
                base64_str = src.split("base64,")[1]
                
                # Solve
                code = self.captcha_solver.solve_image_text(base64_str)
                if not code:
                    logger.error("验证码识别失败")
                    continue # Retry
                    
                # Try to evaluate if it's a math expression
                final_code = evaluate_math_expression(code)
                logger.info(f"验证码识别结果: {code} -> 计算结果: {final_code}")
                
                # Input
                captcha_input.clear()
                captcha_input.send_keys(final_code)
                self.random_sleep(0.5, 1.0)
                
                # Click Confirm / Submit
                # Priority: 1. Button with text '确定' or '提交' inside dialog
                #           2. Button with class 'login_btn' (Specific to this site)
                #           3. Any primary button in dialog footer
                clicked = False
                try:
                    # Try text based match first (Robust for different labels)
                    # XPath: Look for button containing span with text '确定' or '提交' inside visible dialog
                    confirm_btn = self.driver.find_element(By.XPATH, "//div[contains(@class,'el-dialog__wrapper') and not(contains(@style,'display: none'))]//button//span[contains(text(),'确定') or contains(text(),'提交')]/..")
                    self.safe_click(confirm_btn)
                    clicked = True
                except:
                    pass

                if not clicked:
                    try:
                        # Fallback to specific class provided by user
                        login_btn = self.driver.find_element(By.CSS_SELECTOR, "button.login_btn")
                        self.safe_click(login_btn)
                        clicked = True
                    except:
                        pass

                if not clicked:
                    try:
                        # Final Fallback: Generic primary button
                        buttons = self.driver.find_elements(By.CSS_SELECTOR, ".el-dialog__footer button.el-button--primary")
                        if buttons:
                            self.safe_click(buttons[0])
                    except:
                        pass
                
                # Wait for dialog to disappear (Important!)
                logger.info("等待验证码弹窗消失...")
                try:
                    WebDriverWait(self.driver, 5).until(EC.invisibility_of_element_located((By.CLASS_NAME, "el-dialog__wrapper")))
                    self.random_sleep(1.0, 2.0) # Extra safety buffer
                    return # Success
                except:
                    logger.warning("验证码弹窗可能未正常关闭或已超时，可能验证码错误，重试...")
                
            except Exception as e:
                logger.error(f"验证码处理出错: {e}")
                self.random_sleep(1.0, 2.0)

    def wait_for_loading(self, timeout=20):
        """
        Wait for ElementUI loading mask to disappear.
        Useful for handling infinite loading or throttling.
        """
        try:
            # Check if mask is present and visible
            # 'el-loading-mask' is standard ElementUI loading overlay
            mask = self.driver.find_elements(By.CLASS_NAME, "el-loading-mask")
            if mask:
                # Filter for visible mask
                visible_mask = [m for m in mask if m.is_displayed()]
                if visible_mask:
                    logger.info("检测到页面正在加载中(转圈)，等待加载完成...")
                    WebDriverWait(self.driver, timeout).until(EC.invisibility_of_element_located((By.CLASS_NAME, "el-loading-mask")))
                    self.random_sleep(0.5, 1.0)
        except Exception as e:
            logger.warning(f"等待加载遮罩超时或出错: {e}")

    def run(self):
        try:
            logger.info("开始运行爬虫...")
            
            # --- 1. Crawl Tender Announcements (招标公告) ---
            tenders_url = f"{BASE_URL}/#/tenders"
            logger.info(f">>> 开始采集 [招标公告] 模块: {tenders_url} <<<")
            self.crawl_module(
                url=tenders_url,
                tabs=["招标公告", "资格预审公告"]
            )
            
            # --- 2. Crawl Bid Results (中标结果) ---
            candidate_url = f"{BASE_URL}/#/candidate"
            logger.info(f">>> 开始采集 [中标结果] 模块: {candidate_url} <<<")
            self.crawl_module(
                url=candidate_url,
                tabs=["公开招标中标候选人公示", "邀请招标中标候选人通知", "公开招标中标结果公告", "邀请招标中标结果通知"]
            )

        except Exception as e:
            logger.error(f"严重错误: {e}")
            save_log("ERROR", "严重错误", str(e))
            traceback.print_exc()
        finally:
            self.driver.quit()
            logger.info("爬虫运行结束。")

    def crawl_module(self, url, tabs):
        """
        Generic function to crawl a module by direct URL access.
        """
        try:
            # Access URL directly
            logger.info(f"正在访问模块页面: {url}")
            self.driver.get(url)
            save_log("INFO", "进入模块", f"URL: {url}")
            
            self.random_sleep(3, 5)
            self.check_and_handle_captcha() # Check on load
            
            # Iterate Tabs
            for tab_name in tabs:
                logger.info(f"准备抓取板块: {tab_name}")
                try:
                    # Find tab
                    self.wait.until(EC.presence_of_element_located((By.XPATH, "//ul[contains(@class,'el-menu')]")))
                    
                    # Use specific text match for tab
                    tab_elem = self.driver.find_element(By.XPATH, f"//ul[contains(@class,'el-menu')]//li//span[contains(text(),'{tab_name}')]")
                    
                    # Check if active
                    parent_li = tab_elem.find_element(By.XPATH, "./..")
                    if "is-active" not in parent_li.get_attribute("class"):
                        self.safe_click(tab_elem)
                        self.random_sleep(2, 4)
                    
                    # Crawl List
                    self.crawl_list(tab_name)
                    
                except Exception as e:
                    logger.error(f"板块 {tab_name} 处理失败: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"模块采集失败: {e}")

    def crawl_list(self, notice_type_name):
        page = 1
        while True:
            logger.info(f"正在抓取 {notice_type_name} 第 {page} 页...")
            
            # Check Captcha
            self.check_and_handle_captcha()
            
            try:
                # Wait for loading mask to disappear (ElementUI specific)
                self.wait_for_loading(timeout=20)

                # Wait for list items to be visible
                self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div.box_data")))
                
                rows = self.driver.find_elements(By.CSS_SELECTOR, "div.box_data")
                if not rows:
                    logger.info("未发现数据列表。")
                    break
                    
                today_str = datetime.datetime.now().strftime("%Y-%m-%d")
                found_today = False
                
                # Collect items first
                items = []
                for row in rows:
                    try:
                        title_div = row.find_element(By.CSS_SELECTOR, "div.contant")
                        date_div = row.find_element(By.XPATH, "./div[last()]")
                        items.append({
                            "title": title_div.text.strip(),
                            "date": date_div.text.strip(),
                            "element": title_div
                        })
                    except:
                        pass
                
                if not items:
                    break

                for item in items:
                    date_text = item['date']
                    title_text = item['title']
                    
                    # Date Filter
                    if date_text != today_str:
                        if date_text < today_str:
                            logger.info("发现早于今日的数据，停止翻页。")
                            return # Stop crawling this tab
                        continue
                        
                    found_today = True
                    logger.info(f"正在处理: {title_text}")
                    
                    # Deduplication
                    content_id = get_md5(clean_title(title_text))
                    if col_data.find_one({"contentId": content_id}):
                        logger.info(f"跳过重复: {title_text}")
                        continue
                        
                    # Enter Detail
                    try:
                        # Re-locate by text to be safe
                        target = self.driver.find_element(By.XPATH, f"//div[contains(@class,'contant') and contains(text(), '{title_text}')]")
                        self.safe_click(target)
                        
                        # Process Detail
                        self.process_detail(content_id, title_text, date_text, notice_type_name)
                        
                        # Back to list
                        if len(self.driver.window_handles) > 1:
                            self.driver.close()
                            self.driver.switch_to.window(self.driver.window_handles[0])
                        else:
                            # Try to click "Back" button first (SPA friendly)
                            try:
                                # Look for button with text "返回"
                                back_btn = self.driver.find_element(By.XPATH, "//button[contains(@class,'footer')]//span[contains(text(),'返回')]/..")
                                self.safe_click(back_btn)
                            except:
                                # Fallback to browser back
                                self.driver.back()
                                
                            self.random_sleep(2, 3)
                            self.check_and_handle_captcha()
                            
                    except Exception as e:
                        logger.error(f"处理详情失败: {e}")
                        continue

                if not found_today:
                    logger.info("本页无今日数据，停止。")
                    break
                    
                # Next Page
                try:
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, "button.btn-next")
                    if not next_btn.is_enabled() or "disabled" in next_btn.get_attribute("class"):
                        logger.info("已到达最后一页。")
                        break
                    
                    self.safe_click(next_btn)
                    self.wait_for_loading(timeout=20)
                    page += 1
                    self.random_sleep(3, 5) # Wait for page load
                    
                except:
                    logger.info("未找到下一页。")
                    break
                    
            except Exception as e:
                logger.error(f"列表页处理出错: {e}")
                break

    def process_detail(self, content_id, title, date_str, notice_type_raw):
        try:
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.details")))
            self.simulate_reading()
            
            current_url = self.driver.current_url
            
            # Extract Content from details box
            try:
                detail_container = self.driver.find_element(By.CSS_SELECTOR, "div.details")
                detail_text = detail_container.text
                detail_html = detail_container.get_attribute("innerHTML")
            except:
                detail_text = self.driver.find_element(By.TAG_NAME, "body").text
                detail_html = self.driver.page_source
            
            # Attachments: Extract file names/links if available
            file_urls = []
            try:
                # Strategy 1: "附件：" inside cursor_style div (Tender Announcement)
                annex_divs = self.driver.find_elements(By.XPATH, "//div[contains(@class,'cursor_style') and contains(text(),'附件')]")
                for div in annex_divs:
                    file_name = div.text.replace("附件：", "").replace("附件:", "").strip()
                    if file_name:
                        file_urls.append({"name": file_name, "url": ""})
                
                # Strategy 2: "附件:" in sibling label div (Bid Result)
                # Find div with class 'name' containing '附件', then get next sibling with 'cursor_style'
                annex_labels = self.driver.find_elements(By.XPATH, "//div[contains(@class,'name') and contains(text(),'附件')]")
                for label in annex_labels:
                    try:
                        file_div = label.find_element(By.XPATH, "./following-sibling::div[contains(@class,'cursor_style')]")
                        file_name = file_div.text.strip()
                        if file_name:
                            # Avoid duplicates if Strategy 1 caught it (though unlikely to overlap given structure)
                            if not any(f['name'] == file_name for f in file_urls):
                                file_urls.append({"name": file_name, "url": ""})
                    except: pass
            except:
                pass

            # Fields
            budget = extract_budget(detail_text)
            tender_end_time = extract_end_time(detail_text)
            contacts = extract_contacts(detail_text)
            
            # Notice Type
            notice_type = "招标公告"
            if "中标" in notice_type_raw or "成交" in notice_type_raw:
                if "候选人" in notice_type_raw: notice_type = "中标候选人公示"
                else: notice_type = "中标公告"
            elif "变更" in notice_type_raw: notice_type = "更正公告"
            elif "资格预审" in notice_type_raw: notice_type = "资格预审公告"
            elif "邀请" in notice_type_raw: notice_type = "投标邀请书"
            
            data = {
                "contentId": content_id,
                "title": title,
                "url": current_url,
                "source": SOURCE_NAME,
                "createTime": date_str,
                "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "noticeType": notice_type,
                "area": "全国",
                "industry": "能源化工",
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

if __name__ == "__main__":
    crawler = CNPCCrawler()
    crawler.run()
