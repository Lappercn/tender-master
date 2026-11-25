import os
import time
import random
import logging
import re
import datetime
import traceback
import hashlib
from pymongo import MongoClient
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('crawler_airchina.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class WJAirChinaChina:
    def __init__(self):
        self.base_host = "https://pur.airchina.com.cn"
        
        # 数据库连接
        self.client = MongoClient(config.MONGO_URI)
        self.db = self.client[config.DB_NAME]
        self.collection = self.db[config.COLLECTION_NAME]
        
        # 统计
        self.total_crawled = 0
        self.today_count = 0
        
        # 今天的日期
        self.today = datetime.datetime.now().strftime('%Y-%m-%d')
        # self.today = "2026-03-14" # 调试用
        
        # 增加超时时间以适应慢速网站
        self.wait_timeout = 30
        
        self.setup_driver()

    def setup_driver(self):
        options = Options()
        # 启用无头模式
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        # 伪装 User-Agent
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # 隐藏自动化特征
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        # 使用国内镜像源解决网络问题 (已废弃，改为优先使用系统驱动)
        # os.environ['WDM_SSL_VERIFY'] = '0'
        
        try:
            # 优先尝试系统路径 (Ubuntu/Server)
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
                # 本地开发环境回退到 webdriver_manager
                logger.info("未找到系统 chromedriver，尝试使用 webdriver_manager...")
                service = Service(ChromeDriverManager().install())
            
            self.driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            logger.error(f"Failed to initialize Chrome Driver: {e}")
            raise
        
        # 进一步隐藏 webdriver 属性
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })

    def random_sleep(self, min_seconds=2, max_seconds=5):
        """模拟人工随机等待，针对慢速网站适当延长"""
        time.sleep(random.uniform(min_seconds, max_seconds))

    def run(self):
        logger.info(f"开始采集 中国航空集团有限公司采购管理平台 - {self.today}")
        
        # 定义分类
        categories = [
            {"name": "采购公告", "url": "https://pur.airchina.com.cn/001/001001/moreinfo.html"},
            {"name": "澄清公告", "url": "https://pur.airchina.com.cn/001/001002/moreinfo.html"},
            {"name": "中标公示", "url": "https://pur.airchina.com.cn/001/001003/moreinfo.html"},
            {"name": "结果公告", "url": "https://pur.airchina.com.cn/001/001004/moreinfo.html"},
            {"name": "其他公告", "url": "https://pur.airchina.com.cn/001/001005/moreinfo.html"}
        ]
        
        try:
            for category in categories:
                logger.info(f"正在采集分类: {category['name']}")
                self.process_category(category)
                
        except Exception as e:
            logger.error(f"采集过程出错: {e}")
            traceback.print_exc()
        finally:
            self.driver.quit()
            logger.info(f"采集结束。今日总采集: {self.today_count} 条")

    def process_category(self, category):
        try:
            self.driver.get(category['url'])
            # 初始加载可能很慢
            self.random_sleep(3, 6)
            
            page_num = 1
            while True:
                logger.info(f"[{category['name']}] 正在扫描第 {page_num} 页")
                
                # 等待列表加载
                try:
                    WebDriverWait(self.driver, self.wait_timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "tbody#infoContent tr"))
                    )
                except TimeoutException:
                    logger.warning("列表加载超时或无数据")
                    break

                # 获取列表项
                rows = self.driver.find_elements(By.CSS_SELECTOR, "tbody#infoContent tr")
                if not rows:
                    logger.warning("未找到列表项")
                    break

                stop_crawling = False
                
                # 遍历当前页行
                # 策略：获取链接，在新标签页打开
                
                # 提取本页所有链接信息，防止Stale
                page_items = []
                for row in rows:
                    try:
                        cols = row.find_elements(By.TAG_NAME, "td")
                        if len(cols) < 3:
                            continue
                        
                        # 第2列是标题和链接，第3列是时间
                        title_link = cols[1].find_element(By.TAG_NAME, "a")
                        title = title_link.get_attribute("title")
                        if not title:
                            title = title_link.text.strip()
                        href = title_link.get_attribute("href")
                        
                        pub_date = cols[2].text.strip()
                        # 处理可能的非标准日期格式，如 "2026-03-14 00:00:00" 或 "2026/03/14"
                        pub_date = pub_date.split()[0].replace('/', '-')
                        
                        page_items.append({
                            "title": title,
                            "href": href,
                            "pub_date": pub_date
                        })
                    except Exception as e:
                        logger.error(f"提取行信息失败: {e}")

                # 处理本页数据
                for item in page_items:
                    title = item['title']
                    pub_date = item['pub_date']
                    href = item['href']
                    
                    # 日期判断
                    if pub_date < self.today:
                        logger.info(f"发现历史数据 ({pub_date} < {self.today})，停止本分类采集")
                        stop_crawling = True
                        break
                    
                    if pub_date == self.today:
                        # 查重
                        if self.is_duplicate(title):
                            logger.info(f"跳过重复数据: {title}")
                            continue
                            
                        logger.info(f"发现今日数据: {title} ({pub_date})")
                        
                        # 打开详情页 (新标签页)
                        try:
                            self.driver.execute_script(f"window.open('{href}', '_blank');")
                            
                            # 切换窗口
                            windows = self.driver.window_handles
                            self.driver.switch_to.window(windows[-1])
                            
                            # 处理详情
                            try:
                                self.process_detail(title, pub_date, category['name'], href)
                            except Exception as e:
                                logger.error(f"详情页处理失败: {e}")
                                traceback.print_exc()
                            finally:
                                self.driver.close()
                                self.driver.switch_to.window(windows[0])
                                # 规范要求：采集完一条等待 1.5-3s
                                logger.info("详情采集完毕，等待中...")
                                self.random_sleep(1.5, 3)
                                
                        except Exception as e:
                            logger.error(f"打开详情页失败: {e}")

                if stop_crawling:
                    break
                
                # 翻页逻辑
                # 查找 "下一页" 按钮
                # HTML示例: <li><a data-page-index="1">下一页</a></li>
                try:
                    # 使用 text() 包含 "下一页"
                    next_btns = self.driver.find_elements(By.XPATH, "//li/a[contains(text(), '下一页')]")
                    
                    if not next_btns:
                        logger.info("未找到下一页按钮")
                        break
                        
                    next_btn = next_btns[0]
                    
                    # 检查是否可点击 (有些网站如果是最后一页，下一页可能隐藏或disable)
                    # 这里的HTML没显示disabled类，通常如果是最后一页，下一页按钮可能不存在
                    
                    # 点击下一页
                    self.driver.execute_script("arguments[0].click();", next_btn)
                    page_num += 1
                    
                    # 等待页面刷新
                    # 由于是Ajax翻页或整页刷新，我们需要等待内容变化或 loading 消失
                    # 这里简单处理：等待一段时间，然后再次检查列表
                    logger.info("正在翻页...")
                    self.random_sleep(3, 6) # 网站慢，多等一会
                    
                except Exception as e:
                    logger.error(f"翻页出错: {e}")
                    break

        except Exception as e:
            logger.error(f"处理分类 {category['name']} 出错: {e}")

    def process_detail(self, list_title, list_date, category_name, url):
        try:
            # 等待加载
            # 详情页容器: div.ewb-notice
            try:
                WebDriverWait(self.driver, self.wait_timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.ewb-notice"))
                )
            except:
                logger.warning("未找到标准详情容器 div.ewb-notice")
            
            self.random_sleep(1, 2)
            
            # 提取正文
            # 正文通常在 div.ewb-notice-bd 或 div.ewb-notice-copy
            content_html = ""
            content_text = ""
            
            try:
                # 优先尝试 div.ewb-notice-copy (根据提供的HTML)
                content_elem = self.driver.find_element(By.CSS_SELECTOR, "div.ewb-notice-copy")
                content_html = content_elem.get_attribute("outerHTML")
                content_text = content_elem.text
            except:
                try:
                    # 尝试 div.ewb-notice-bd
                    content_elem = self.driver.find_element(By.CSS_SELECTOR, "div.ewb-notice-bd")
                    content_html = content_elem.get_attribute("outerHTML")
                    content_text = content_elem.text
                except:
                    # 兜底 body
                    content_elem = self.driver.find_element(By.TAG_NAME, "body")
                    content_html = content_elem.get_attribute("outerHTML")
                    content_text = content_elem.text

            # 提取字段
            budget = self.extract_budget(content_text)
            contacts = self.extract_contacts(content_text)
            tender_end_time = self.extract_tender_end_time(content_text)
            purchaser = self.extract_purchaser(content_text)
            agent = self.extract_agent(content_text)
            winning_info = self.extract_winning_info(content_text)
            winning_bidder = winning_info.get("bidder", "")
            winning_amount = winning_info.get("amount", "")
            purchase_method = self.extract_purchase_method(content_text)
            
            # 附件提取
            # <div class="ewb-download">附件： <p class="ewb-attach-p"><a href="...">filename</a></p></div>
            attachments = []
            try:
                attach_divs = self.driver.find_elements(By.CSS_SELECTOR, "div.ewb-download a")
                for a in attach_divs:
                    name = a.text.strip()
                    href = a.get_attribute("href")
                    if href and name:
                        # 处理相对路径
                        if href.startswith("/"):
                            href = self.base_host + href
                        attachments.append({"name": name, "url": href})
            except Exception as e:
                logger.warning(f"附件提取失败: {e}")

            # 构造数据
            content_id = self.generate_id(list_title)
            
            data = {
                "_id": content_id,
                "contentId": content_id,
                "title": list_title,
                "createTime": list_date,
                "url": url,
                "detail": content_html,
                "briefText": content_text[:200] if content_text else "",
                "source": "中国航空集团有限公司采购管理平台",
                "noticeType": category_name,
                "budget": budget,
                "contacts": contacts,
                "fileUrl": [a['url'] for a in attachments],
                "hasAnnex": len(attachments) > 0,
                "crawl_time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "area": "", 
                "industry": "航空",
                "purchaser": purchaser,
                "agent": agent,
                "tenderEndTime": tender_end_time,
                "winningBidder": winning_bidder,
                "winningAmount": winning_amount,
                "purchaseMethod": purchase_method
            }
            
            self.save_data(data)
            
        except Exception as e:
            logger.error(f"详情解析失败: {e}")
            raise e

    # ================= 字段提取逻辑 (复用通用正则) =================
    
    def extract_budget(self, text):
        patterns = [
            r'(预算金额|预算总金额|项目预算).*?([\d,]+(\.\d+)?).*?(万|元)',
            r'(最高限价|最高限制单价|最高单价限价|限价|招标控制价|投标限价|最高投标限价).*?([\d,]+(\.\d+)?).*?(万|元)',
            r'(采购控制价|控制价).*?([\d,]+(\.\d+)?).*?(万|元)',
            r'(合同估算价|估算价|项目概算|概算金额|项目投资).*?([\d,]+(\.\d+)?).*?(万|元)',
            r'(资金来源|出资比例).*?([\d,]+(\.\d+)?).*?(万|元)',
            r'(单价|金额|价格).*?([\d,]+(\.\d+)?).*?(万|元)'
        ]
        for p in patterns:
            match = re.search(p, text)
            if match:
                return match.group(0)
        return ""

    def extract_tender_end_time(self, text):
        patterns = [
            r'(递交|提交).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?)',
            r'(投标|响应|报价|比选|申请文件).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?)',
            r'(开标时间|开启时间|开标).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?)',
            r'(报名).*?(截止时间|结束时间).*?([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?)',
            r'([\d]{4}年[\d]{1,2}月[\d]{1,2}日(\s*[\d]{1,2}:[\d]{1,2})?).*?截止'
        ]
        for p in patterns:
            match = re.search(p, text)
            if match:
                if len(match.groups()) >= 3:
                     return match.group(3)
                return match.group(0)
        return ""

    def extract_purchaser(self, text):
        patterns = [
            r'(采购人|采购单位|招标人|招标单位|需求单位|业主单位|建设单位|发包人|项目业主|招商人|采购单位名称)[：:]\s*(.+)',
            r'(采购人名称|招标人名称)[：:]\s*(.+)'
        ]
        for p in patterns:
            match = re.search(p, text)
            if match:
                return match.group(2).strip()
        return ""

    def extract_agent(self, text):
        patterns = [
            r'(代理机构|招标代理|招标代理机构|采购代理|采购代理机构|代理单位|招标服务单位|比选代理机构)[：:]\s*(.+)',
            r'(代理机构名称)[：:]\s*(.+)'
        ]
        for p in patterns:
            match = re.search(p, text)
            if match:
                return match.group(2).strip()
        return ""

    def extract_purchase_method(self, text):
        patterns = [
            r'(采购方式|招标方式|选取方式|运作方式)[：:]\s*(.+)',
            r'(项目类型)[：:]\s*(.+)'
        ]
        for p in patterns:
            match = re.search(p, text)
            if match:
                return match.group(2).strip()
        return ""

    def extract_winning_info(self, text):
        info = {"bidder": "", "amount": ""}
        p_bidder = r'(中标人|中标单位|成交人|成交供应商|成交单位|供应商名称|中标供应商|第一中标候选人|预中标单位|中标单位名称)[：:]\s*(.+)'
        match_bidder = re.search(p_bidder, text)
        if match_bidder:
            info["bidder"] = match_bidder.group(2).strip()
        p_amount = r'(中标金额|中标价格|成交金额|成交价格|投标报价|中标价).*?([\d,]+(\.\d+)?).*?(万|元)'
        match_amount = re.search(p_amount, text)
        if match_amount:
            info["amount"] = match_amount.group(0)
        return info

    def extract_contacts(self, text):
        contacts = []
        pattern_combo = r'(项目联系人|联系人|负责人|联系方式|技术咨询|商务咨询|异议联系人)[:：]\s*([\u4e00-\u9fa5]{2,4}).{0,50}?(联系电话|电话|手机)[:：]\s*([\d-]{8,})'
        matches = re.finditer(pattern_combo, text, re.DOTALL)
        found_combo = False
        for m in matches:
            found_combo = True
            contacts.append({"name": m.group(2), "phone": m.group(4)})
        if found_combo:
            return contacts
        pattern_name = r'(项目联系人|联系人|负责人|技术咨询|商务咨询|异议联系人)[：:]\s*([\u4e00-\u9fa5]{2,4})'
        pattern_phone = r'(联系电话|电话|手机|联系方式)[：:]\s*([\d-]{8,})'
        name_match = re.search(pattern_name, text)
        phone_match = re.search(pattern_phone, text)
        contact_obj = {}
        if name_match: contact_obj["name"] = name_match.group(2)
        if phone_match: contact_obj["phone"] = phone_match.group(2)
        if contact_obj: contacts.append(contact_obj)
        return contacts

    def is_duplicate(self, title):
        content_id = self.generate_id(title)
        return self.collection.find_one({"_id": content_id}) is not None

    def generate_id(self, title):
        stripped = title.replace(" ", "").strip()
        stripped = re.sub(r'[【】\[\]（）\-\(\)]', '', stripped)
        stripped = stripped.lower()
        return hashlib.md5(stripped.encode('utf-8')).hexdigest()

    def save_data(self, data):
        try:
            self.collection.insert_one(data)
            self.today_count += 1
            self.total_crawled += 1
            logger.info(f"数据已保存: {data['title']}")
        except Exception as e:
            if "E11000" in str(e):
                logger.info(f"数据已存在 (E11000): {data['title']}")
            else:
                logger.error(f"数据保存失败: {e}")

if __name__ == "__main__":
    crawler = WJAirChinaChina()
    crawler.run()
