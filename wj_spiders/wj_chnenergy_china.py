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
        logging.FileHandler('crawler_chnenergy.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class WJChnenergyChina:
    def __init__(self):
        self.base_url = "https://www.chnenergybidding.com.cn"
        # 定义需要采集的栏目 (根据筛选器.html)
        self.categories = [
            {"name": "招标公告", "url": "https://www.chnenergybidding.com.cn/bidweb/001/001002/moreinfo.html"},
            {"name": "资格预审公告", "url": "https://www.chnenergybidding.com.cn/bidweb/001/001001/moreinfo.html"},
            {"name": "非招标公告", "url": "https://www.chnenergybidding.com.cn/bidweb/001/001003/moreinfo.html"},
            {"name": "中标公告", "url": "https://www.chnenergybidding.com.cn/bidweb/001/001006/moreinfo.html"},
            {"name": "变更公告", "url": "https://www.chnenergybidding.com.cn/bidweb/001/001004/moreinfo.html"},
            {"name": "候选人公示", "url": "https://www.chnenergybidding.com.cn/bidweb/001/001005/moreinfo.html"},
            {"name": "终止公告", "url": "https://www.chnenergybidding.com.cn/bidweb/001/001007/moreinfo.html"},
        ]
        
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

    def wait_for_loading(self, timeout=20):
        """等待页面加载遮罩消失 (参考CNPC逻辑)"""
        try:
            # 检查是否有 el-loading-mask 或类似的遮罩
            WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located((By.CLASS_NAME, "el-loading-mask"))
            )
            # 如果存在，等待它消失
            WebDriverWait(self.driver, timeout).until(
                EC.invisibility_of_element_located((By.CLASS_NAME, "el-loading-mask"))
            )
        except TimeoutException:
            pass # 没有遮罩或遮罩未在短时间内出现，继续
        except Exception:
            pass

    def run(self):
        logger.info(f"开始采集 中国能源 (国能e招) - {self.today}")
        try:
            for category in self.categories:
                logger.info(f"正在采集栏目: {category['name']}")
                self.process_category(category)
        finally:
            self.driver.quit()
            logger.info(f"采集结束。今日总采集: {self.today_count} 条")

    def process_category(self, category):
        url = category['url']
        self.driver.get(url)
        self.random_sleep(2, 4)
        
        page_num = 1
        while True:
            logger.info(f"正在扫描第 {page_num} 页: {self.driver.current_url}")
            
            # 等待列表加载
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ul.right-items li.right-item"))
                )
            except TimeoutException:
                logger.warning("列表加载超时或无数据")
                break

            # 获取列表项
            items = self.driver.find_elements(By.CSS_SELECTOR, "ul.right-items li.right-item")
            if not items:
                logger.warning("未找到列表项")
                break

            stop_crawling = False
            has_today_data = False
            
            # 遍历列表项
            # 注意：点击会打开新标签页，所以需要记录 handle
            main_window = self.driver.current_window_handle
            
            for index in range(len(items)):
                try:
                    # 重新获取元素，防止 StaleElementReferenceException
                    items = self.driver.find_elements(By.CSS_SELECTOR, "ul.right-items li.right-item")
                    if index >= len(items):
                        break
                    
                    item = items[index]
                    
                    # 提取日期
                    date_elem = item.find_element(By.CSS_SELECTOR, "span.r")
                    pub_date = date_elem.text.strip()
                    
                    # 提取标题和链接元素
                    link_elem = item.find_element(By.CSS_SELECTOR, "a.infolink")
                    title = link_elem.get_attribute("title")
                    if not title:
                        title = link_elem.text.strip()
                    
                    # 日期判断逻辑
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
                        
                        # 点击进入详情页
                        # 滚动到元素可见
                        self.driver.execute_script("arguments[0].scrollIntoView(false);", link_elem)
                        self.random_sleep(0.5, 1)
                        
                        # 记录点击前的窗口句柄
                        windows_before = self.driver.window_handles
                        
                        link_elem.click()
                        
                        # 等待新标签页打开
                        try:
                            WebDriverWait(self.driver, 10).until(EC.new_window_is_opened(windows_before))
                        except TimeoutException:
                            logger.warning("点击后未检测到新窗口打开")
                            continue
                        
                        # 切换到新标签页
                        windows_after = self.driver.window_handles
                        new_window = [w for w in windows_after if w not in windows_before][0]
                        self.driver.switch_to.window(new_window)
                        
                        # 处理详情页
                        try:
                            self.process_detail(title, pub_date, category['name'])
                        except Exception as e:
                            logger.error(f"处理详情页出错: {e}")
                            traceback.print_exc()
                        finally:
                            # 关闭当前标签页并切回主窗口
                            self.driver.close()
                            self.driver.switch_to.window(main_window)
                            logger.info("详情采集完毕，等待中...")
                            self.random_sleep(1.5, 3)
                    
                except StaleElementReferenceException:
                    logger.warning("元素失效，重试当前页")
                    continue
                except Exception as e:
                    logger.error(f"处理列表项出错: {e}")
                    continue

            if stop_crawling:
                break
            
            # 翻页逻辑
            try:
                next_btn = self.driver.find_element(By.CSS_SELECTOR, "li.nextlink a")
                # 检查是否禁用 (通常 disabled 样式在 li 上，或者 href 为 javascript:void(0))
                parent_li = next_btn.find_element(By.XPATH, "./..")
                li_class = parent_li.get_attribute("class")
                
                if "disabled" in li_class or not next_btn.get_attribute("href"):
                    logger.info("没有下一页了")
                    break
                
                # 点击下一页
                logger.info("点击下一页")
                next_btn.click()
                page_num += 1
                self.random_sleep(2, 4)
                
            except NoSuchElementException:
                logger.info("未找到下一页按钮，结束翻页")
                break
            except Exception as e:
                logger.error(f"翻页出错: {e}")
                break

    def process_detail(self, list_title, list_date, category_name):
        self.wait_for_loading()
        self.random_sleep(1.5, 3)
        
        current_url = self.driver.current_url
        
        # 提取详情内容
        try:
            # 标题
            try:
                title_elem = self.driver.find_element(By.ID, "title")
                title = title_elem.text.strip()
            except:
                title = list_title
            
            # 正文
            try:
                content_elem = self.driver.find_element(By.CSS_SELECTOR, "div.article-info div.con")
                content_html = content_elem.get_attribute("outerHTML")
                content_text = content_elem.text
            except:
                content_html = ""
                content_text = ""
                logger.warning("未找到正文内容")

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
            
            # 附件提取 (div.con.attach a 或 div.con a)
            attachments = []
            try:
                # 查找所有链接
                links = self.driver.find_elements(By.CSS_SELECTOR, "div.article-info a")
                for link in links:
                    href = link.get_attribute("href")
                    text = link.text.strip()
                    # 简单判断附件
                    if href and ('.pdf' in href or '.doc' in href or '.xls' in href or '.zip' in href or 'download' in href):
                        attachments.append({"name": text, "url": href})
            except Exception as e:
                logger.warning(f"附件提取失败: {e}")

            # 构造数据
            # 生成 contentId (MD5 of stripped title)
            content_id = self.generate_id(title)
            
            data = {
                "_id": content_id, # 使用 contentId 作为主键
                "contentId": content_id,
                "title": title,
                "createTime": list_date, # 规范字段名: createTime
                "url": current_url,
                "detail": content_html, # 规范字段名: detail
                "briefText": content_text[:200] if content_text else "", # 规范字段名: briefText
                "source": "中国能源招标网",
                "noticeType": category_name, # 规范字段名: noticeType
                "budget": budget,
                "contacts": contacts,
                "fileUrl": [a['url'] for a in attachments], # 规范字段名: fileUrl (List[String])
                "hasAnnex": len(attachments) > 0,
                "crawl_time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "area": "", # 暂空
                "industry": "", # 暂空
                "purchaser": purchaser,
                "agent": agent,
                "tenderEndTime": tender_end_time,
                "winningBidder": winning_bidder,
                "winningAmount": winning_amount,
                "purchaseMethod": purchase_method
            }
            
            self.save_data(data)
            
        except Exception as e:
            logger.error(f"详情页解析失败: {e}")
            raise e

    def extract_budget(self, text):
        """提取预算金额"""
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
                return match.group(0) # 返回匹配的整句
        return ""

    def extract_tender_end_time(self, text):
        """提取截止时间"""
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
                # 优先返回具体的日期时间部分，如果pattern有捕获组
                if len(match.groups()) >= 3:
                     return match.group(3)
                return match.group(0)
        return ""

    def extract_purchaser(self, text):
        """提取采购人"""
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
        """提取代理机构"""
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
        """提取采购方式"""
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
        """提取中标信息"""
        info = {"bidder": "", "amount": ""}
        
        # Bidder
        p_bidder = r'(中标人|中标单位|成交人|成交供应商|成交单位|供应商名称|中标供应商|第一中标候选人|预中标单位|中标单位名称)[：:]\s*(.+)'
        match_bidder = re.search(p_bidder, text)
        if match_bidder:
            info["bidder"] = match_bidder.group(2).strip()
            
        # Amount
        p_amount = r'(中标金额|中标价格|成交金额|成交价格|投标报价|中标价).*?([\d,]+(\.\d+)?).*?(万|元)'
        match_amount = re.search(p_amount, text)
        if match_amount:
            info["amount"] = match_amount.group(0)
            
        return info

    def extract_contacts(self, text):
        """提取联系人 (List[Object])"""
        contacts = []
        
        # 1. 组合匹配 (推荐)
        # 查找距离姓名 50 字符以内的电话号码
        pattern_combo = r'(项目联系人|联系人|负责人|联系方式|技术咨询|商务咨询|异议联系人)[:：]\s*([\u4e00-\u9fa5]{2,4}).{0,50}?(联系电话|电话|手机)[:：]\s*([\d-]{8,})'
        matches = re.finditer(pattern_combo, text, re.DOTALL)
        
        found_combo = False
        for m in matches:
            found_combo = True
            contacts.append({
                "name": m.group(2),
                "phone": m.group(4)
            })
            
        if found_combo:
            return contacts
            
        # 2. 单项匹配 (兜底)
        pattern_name = r'(项目联系人|联系人|负责人|技术咨询|商务咨询|异议联系人)[：:]\s*([\u4e00-\u9fa5]{2,4})'
        pattern_phone = r'(联系电话|电话|手机|联系方式)[：:]\s*([\d-]{8,})'
        
        name_match = re.search(pattern_name, text)
        phone_match = re.search(pattern_phone, text)
        
        contact_obj = {}
        if name_match:
            contact_obj["name"] = name_match.group(2)
        if phone_match:
            contact_obj["phone"] = phone_match.group(2)
            
        if contact_obj:
            contacts.append(contact_obj)
            
        return contacts

    def is_duplicate(self, title):
        """查重 (MD5)"""
        content_id = self.generate_id(title)
        return self.collection.find_one({"_id": content_id}) is not None

    def generate_id(self, title):
        """
        生成 contentId (MD5 of Stripped_Title)
        清洗逻辑:
        1. 去除首尾及中间空格
        2. 去除特殊符号 【】 [] （） -
        3. 转小写
        """
        # 1. 去除空格
        stripped = title.replace(" ", "").strip()
        # 2. 去除特殊符号
        stripped = re.sub(r'[【】\[\]（）\-\(\)]', '', stripped)
        # 3. 转小写
        stripped = stripped.lower()
        
        return hashlib.md5(stripped.encode('utf-8')).hexdigest()

    def save_data(self, data):
        """保存数据"""
        try:
            self.collection.insert_one(data)
            self.today_count += 1
            self.total_crawled += 1
            logger.info(f"数据已保存: {data['title']}")
        except Exception as e:
            # 如果是主键冲突 (DuplicateKeyError)，说明已存在
            if "E11000" in str(e):
                logger.info(f"数据已存在 (E11000): {data['title']}")
            else:
                logger.error(f"数据保存失败: {e}")

if __name__ == "__main__":
    crawler = WJChnenergyChina()
    crawler.run()
