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
        logging.FileHandler('crawler_huaneng.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class WJHuanengChina:
    def __init__(self):
        self.base_url = "https://ec.chng.com.cn/channel/home/#/purchase"
        
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
            import shutil
            # 优先尝试系统路径 (Ubuntu/Server)
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

    def random_sleep(self, min_seconds=1.5, max_seconds=3.5):
        """模拟人工随机等待"""
        time.sleep(random.uniform(min_seconds, max_seconds))

    def run(self):
        logger.info(f"开始采集 中国华能电子商务平台 - {self.today}")
        try:
            self.driver.get(self.base_url)
            self.random_sleep(3, 5)
            
            # 首页有两个主要板块：招标专栏 和 非招标专栏
            # 它们在同一页面上下排列，或者通过锚点区分。根据完整首页.html，它们是并列存在的 div 块。
            # 我们需要分别处理这两个板块。
            # 策略：通过定位 "招标专栏" 和 "非招标专栏" 的容器，分别进行操作。
            
            # 1. 处理招标专栏
            logger.info(">>> 开始处理 [招标专栏] <<<")
            self.process_section(section_index=0, section_name="招标专栏")
            
            # 2. 处理非招标专栏
            # 刷新页面或重新进入，确保状态重置
            self.driver.get(self.base_url)
            self.random_sleep(3, 5)
            
            logger.info(">>> 开始处理 [非招标专栏] <<<")
            self.process_section(section_index=1, section_name="非招标专栏")

        except Exception as e:
            logger.error(f"采集过程出错: {e}")
            traceback.print_exc()
        finally:
            self.driver.quit()
            logger.info(f"采集结束。今日总采集: {self.today_count} 条")

    def process_section(self, section_index, section_name):
        """
        处理指定的专栏板块
        section_index: 0 for 招标专栏, 1 for 非招标专栏 (基于页面结构顺序)
        """
        try:
            # 定位主容器
            # 根据完整首页.html，页面有两个主要的 .content 区域（或者类似的 wrapper）
            # 我们可以通过查找包含 "招标专栏" 或 "非招标专栏" 文本的元素来定位
            
            # 查找所有板块容器
            # 观察HTML，每个板块似乎包含一个 .menu (左侧菜单) 和 .table (右侧列表)
            # 我们可以通过查找 .menu 来区分板块
            menus = self.driver.find_elements(By.CSS_SELECTOR, "div.menu")
            if len(menus) <= section_index:
                logger.warning(f"未找到 {section_name} 的菜单容器")
                return
            
            target_menu = menus[section_index]
            
            # 滚动到该板块可见
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", target_menu)
            self.random_sleep(1, 2)
            
            # 获取该板块下的所有菜单项
            menu_items = target_menu.find_elements(By.CSS_SELECTOR, "div.menu-item, div.menu-checked")
            
            # 遍历菜单项 (如: 招标公告, 资格预审公告...)
            # 注意：点击菜单项会导致页面刷新或DOM更新，需要重新获取元素
            for i in range(len(menu_items)):
                # 重新定位菜单容器和项 (防止StaleElement)
                menus = self.driver.find_elements(By.CSS_SELECTOR, "div.menu")
                if len(menus) <= section_index:
                    break
                target_menu = menus[section_index]
                menu_items = target_menu.find_elements(By.CSS_SELECTOR, "div.menu-item, div.menu-checked")
                
                if i >= len(menu_items):
                    break
                    
                item = menu_items[i]
                category_title = item.text.strip()
                
                logger.info(f"正在采集: [{section_name}] - {category_title}")
                
                # 点击菜单项
                # 检查是否已经是选中状态
                if "menu-checked" not in item.get_attribute("class"):
                    item.click()
                    self.random_sleep(2, 4) # 等待列表刷新
                
                # 处理当前类别的列表
                self.process_list(section_index, f"{section_name}-{category_title}")
                
        except Exception as e:
            logger.error(f"处理 {section_name} 出错: {e}")
            traceback.print_exc()

    def process_list(self, section_index, full_category_name):
        page_num = 1
        while True:
            logger.info(f"正在扫描第 {page_num} 页")
            
            # 定位当前板块的表格
            # 同样需要重新定位，因为DOM可能变化
            tables = self.driver.find_elements(By.CSS_SELECTOR, "div.table")
            if len(tables) <= section_index:
                logger.warning("找不到表格容器")
                break
            
            current_table = tables[section_index]
            
            # 等待行加载
            try:
                WebDriverWait(self.driver, 10).until(
                    lambda d: len(current_table.find_elements(By.CSS_SELECTOR, "tr.ant-table-row")) > 0
                )
            except TimeoutException:
                logger.info("当前页无数据")
                break
                
            rows = current_table.find_elements(By.CSS_SELECTOR, "tr.ant-table-row")
            if not rows:
                break
                
            stop_crawling = False
            has_today_data = False
            
            for row in rows:
                try:
                    # 获取行数据
                    # 假设最后两列是日期
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if not cols:
                        continue
                        
                    # 提取日期 (通常在最后一列，或者倒数第二列)
                    # 观察HTML结构，日期在最后一列
                    pub_date = cols[-1].text.strip()
                    
                    # 提取标题 (通常在第一列或第二列，包含链接或文本)
                    # 列表.html显示 td -> div -> span (title) or similar
                    # 尝试获取所有文本，取最长的作为标题
                    title = cols[0].text.strip()
                    # 尝试从 data-row-key 获取 ID
                    row_id = row.get_attribute("data-row-key")
                    
                    # 日期判断
                    if not self.is_valid_date(pub_date):
                         # 尝试从文本中正则提取日期
                         date_match = re.search(r'\d{4}-\d{2}-\d{2}', row.text)
                         if date_match:
                             pub_date = date_match.group(0)
                    
                    if pub_date < self.today:
                        logger.info(f"发现历史数据 ({pub_date} < {self.today})，停止本栏目采集")
                        stop_crawling = True
                        break
                        
                    if pub_date == self.today:
                        has_today_data = True
                        
                        # 查重
                        if self.is_duplicate(title):
                            logger.info(f"跳过重复数据: {title}")
                            continue
                            
                        logger.info(f"发现今日数据: {title} ({pub_date})")
                        
                        # 进入详情
                        # 方式1：直接构造URL (推荐，因为是SPA)
                        if row_id:
                            detail_url = f"https://ec.chng.com.cn/channel/home/#/detail?id={row_id}"
                            self.open_detail_in_new_tab(detail_url, title, pub_date, full_category_name)
                        else:
                            # 方式2：点击行 (如果不含ID)
                            # row.click()
                            logger.warning(f"无法获取 row_id，跳过: {title}")
                            
                except Exception as e:
                    logger.error(f"处理行出错: {e}")
                    continue
            
            if stop_crawling:
                break
                
            # 翻页逻辑
            # 定位当前板块的分页器
            # 需要在 current_table 附近找 ant-pagination
            # 通常 pagination 在 table 下方
            try:
                # 重新获取 pagination (防止 stale)
                # 注意：页面上有两个 pagination，需要根据 section_index 区分
                paginations = self.driver.find_elements(By.CSS_SELECTOR, "ul.ant-pagination")
                if len(paginations) <= section_index:
                    break
                
                current_pagination = paginations[section_index]
                
                # 查找 "下一页" 按钮
                # class="ant-pagination-next"
                next_li = current_pagination.find_element(By.CSS_SELECTOR, "li.ant-pagination-next")
                
                if "ant-pagination-disabled" in next_li.get_attribute("class"):
                    logger.info("没有下一页了")
                    break
                    
                # 点击下一页
                next_btn = next_li.find_element(By.TAG_NAME, "a")
                self.driver.execute_script("arguments[0].click();", next_btn)
                page_num += 1
                self.random_sleep(2, 4)
                
            except NoSuchElementException:
                logger.info("未找到翻页按钮")
                break
            except Exception as e:
                logger.error(f"翻页出错: {e}")
                break

    def open_detail_in_new_tab(self, url, title, pub_date, category_name):
        """在新标签页打开详情并采集"""
        try:
            # 打开新标签页
            self.driver.execute_script(f"window.open('{url}', '_blank');")
            self.random_sleep(1, 2)
            
            # 切换句柄
            handles = self.driver.window_handles
            self.driver.switch_to.window(handles[-1])
            
            # 等待内容加载
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.content"))
                )
                self.random_sleep(1, 2)
                
                # 采集详情
                self.extract_detail(title, pub_date, url, category_name)
                
            except TimeoutException:
                logger.warning(f"详情页加载超时: {url}")
            finally:
                # 关闭标签页
                self.driver.close()
                self.driver.switch_to.window(handles[0])
                logger.info("详情采集完毕，等待中...")
                self.random_sleep(1.5, 3)
                
        except Exception as e:
            logger.error(f"打开详情页失败: {e}")

    def extract_detail(self, list_title, list_date, current_url, category_name):
        try:
            # 获取正文
            content_elem = self.driver.find_element(By.CSS_SELECTOR, "div.content")
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
            
            # 附件提取 (简单提取所有a标签链接)
            attachments = []
            links = content_elem.find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute("href")
                text = link.text.strip()
                if href and ('.pdf' in href or '.doc' in href or '.xls' in href or '.zip' in href or 'download' in href):
                    attachments.append({"name": text, "url": href})

            # 生成ID
            content_id = self.generate_id(list_title)
            
            data = {
                "_id": content_id,
                "contentId": content_id,
                "title": list_title,
                "createTime": list_date,
                "url": current_url,
                "detail": content_html,
                "briefText": content_text[:200] if content_text else "",
                "source": "中国华能电子商务平台",
                "noticeType": category_name,
                "budget": budget,
                "contacts": contacts,
                "fileUrl": [a['url'] for a in attachments],
                "hasAnnex": len(attachments) > 0,
                "crawl_time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "area": "",
                "industry": "",
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

    # ================= 字段提取逻辑 (复用 wj_chnenergy_china.py) =================
    
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

    def is_valid_date(self, date_str):
        try:
            datetime.datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False

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
    crawler = WJHuanengChina()
    crawler.run()
