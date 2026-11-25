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
        logging.FileHandler('crawler_chinatelecom.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class WJChinaTelecomChina:
    def __init__(self):
        self.base_url = "https://caigou.chinatelecom.com.cn/search"
        
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
        # 启用无头模式 (服务器必须开启)
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage') # 关键参数，防止内存崩溃
        
        # 伪装 User-Agent
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # 隐藏自动化特征
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        # 驱动加载逻辑：优先系统路径，失败则下载
        try:
            import shutil
            # 优先使用系统安装的 chromedriver (Server/Linux 环境)
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

    def run(self):
        logger.info(f"开始采集 中国电信阳光采购网 - {self.today}")
        try:
            self.driver.get(self.base_url)
            self.random_sleep(3, 5)
            
            # 获取所有分类
            # 根据分类器.html，分类在 div.noticeNavItem 中
            # 我们需要依次点击每个分类进行采集
            # 注意：点击分类会刷新列表，DOM可能会变，需要重新获取
            
            # 定义分类列表 (手动维护或动态获取)
            # 根据提供的HTML，分类有：
            categories = [
                "资格预审公告", "招标公告", "询比公告", "谈判采购公告", 
                "评价检测公告", "政企合作招募公告", "IPTV内容合作招募公告", 
                "采购结果公示", "直接采购公示", "澄清公示"
            ]
            
            for category_name in categories:
                logger.info(f"正在采集分类: {category_name}")
                self.process_category(category_name)
                
        except Exception as e:
            logger.error(f"采集过程出错: {e}")
            traceback.print_exc()
        finally:
            self.driver.quit()
            logger.info(f"采集结束。今日总采集: {self.today_count} 条")

    def process_category(self, category_name):
        try:
            # 1. 点击分类
            # 等待导航栏加载
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "noticeNavbox"))
            )
            
            # 遍历所有分类按钮，找到匹配的
            found = False
            nav_items = self.driver.find_elements(By.CSS_SELECTOR, "div.noticeNavItem")
            for item in nav_items:
                # 获取该项的所有文本（包括子元素）
                item_text = item.text
                if category_name in item_text:
                    # 检查是否激活
                    if "isActive" in item.get_attribute("class"):
                        logger.info(f"分类 {category_name} 已激活")
                    else:
                        # 点击
                        try:
                            item.click()
                        except:
                            self.driver.execute_script("arguments[0].click();", item)
                        self.random_sleep(2, 4) # 等待列表刷新
                    found = True
                    break
            
            if not found:
                logger.warning(f"未找到分类按钮: {category_name}")
                return

            # 2. 遍历分页
            page_num = 1
            while True:
                logger.info(f"[{category_name}] 正在扫描第 {page_num} 页")
                
                # 等待列表加载
                try:
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "tr.el-table__row"))
                    )
                except TimeoutException:
                    logger.warning("列表加载超时或无数据")
                    break

                # 获取列表项
                rows = self.driver.find_elements(By.CSS_SELECTOR, "tr.el-table__row")
                if not rows:
                    logger.warning("未找到列表项")
                    break

                stop_crawling = False
                
                # 遍历当前页行
                # 策略：按索引遍历，点击->(新窗口?是:否)->采集->返回
                
                rows = self.driver.find_elements(By.CSS_SELECTOR, "tr.el-table__row")
                row_count = len(rows)
                logger.info(f"本页共 {row_count} 条数据")
                
                # 遍历索引
                index = 0
                while index < row_count:
                    try:
                        # 重新获取列表 (防止Stale)
                        # 等待列表加载
                        try:
                            WebDriverWait(self.driver, 15).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "tr.el-table__row"))
                            )
                        except:
                            logger.warning("等待列表重新加载超时")
                            break
                            
                        rows = self.driver.find_elements(By.CSS_SELECTOR, "tr.el-table__row")
                        if index >= len(rows):
                            logger.warning("索引超出范围，可能列表发生了变化")
                            break
                        
                        row = rows[index]
                        
                        # 提取元数据
                        cols = row.find_elements(By.TAG_NAME, "td")
                        if len(cols) < 4:
                            index += 1
                            continue
                            
                        # 最后一列是发布日期
                        pub_date = cols[-1].text.strip()
                        
                        # 标题在第一列
                        title_elem = cols[0].find_element(By.CSS_SELECTOR, "div.noticeTitle")
                        title = title_elem.text.strip()
                        
                        # 日期判断
                        if pub_date < self.today:
                            logger.info(f"发现历史数据 ({pub_date} < {self.today})，停止本分类采集")
                            stop_crawling = True
                            break
                        
                        if pub_date == self.today:
                            # 查重
                            if self.is_duplicate(title):
                                logger.info(f"跳过重复数据: {title}")
                                index += 1
                                continue
                                
                            logger.info(f"发现今日数据: {title} ({pub_date})")
                            
                            # 点击
                            self.driver.execute_script("arguments[0].scrollIntoView(false);", title_elem)
                            self.random_sleep(0.5, 1)
                            
                            windows_before = self.driver.window_handles
                            self.driver.execute_script("arguments[0].click();", title_elem)
                            
                            # 判断是新窗口还是原地跳转
                            is_new_window = False
                            try:
                                WebDriverWait(self.driver, 5).until(EC.new_window_is_opened(windows_before))
                                is_new_window = True
                            except TimeoutException:
                                is_new_window = False
                            
                            if is_new_window:
                                windows_after = self.driver.window_handles
                                target_window = [w for w in windows_after if w not in windows_before][0]
                                self.driver.switch_to.window(target_window)
                                try:
                                    self.process_detail(title, pub_date, category_name)
                                except Exception as e:
                                    logger.error(f"详情页处理失败: {e}")
                                finally:
                                    self.driver.close()
                                    self.driver.switch_to.window(windows_before[0])
                            else:
                                # 原地跳转
                                logger.info("检测到原地跳转，正在采集...")
                                try:
                                    self.process_detail(title, pub_date, category_name)
                                except Exception as e:
                                    logger.error(f"详情页处理失败: {e}")
                                finally:
                                    # 返回列表
                                    logger.info("返回列表页...")
                                    self.driver.back()
                                    # 等待列表重新出现
                                    try:
                                        WebDriverWait(self.driver, 15).until(
                                            EC.presence_of_element_located((By.CSS_SELECTOR, "tr.el-table__row"))
                                        )
                                        # 这里存在风险：如果back()导致页面重置到第1页，而我们正在采集第2页
                                        # 检查当前页码是否正确
                                        # 暂时假设back()能保持状态（通常浏览器缓存会保持）
                                        # 如果不能，需要额外的分页恢复逻辑，但这很复杂
                                    except:
                                        logger.warning("返回列表后未检测到数据行")
                            
                            # 规范要求：采集完一条等待 1.5-3s
                            logger.info("详情采集完毕，等待中...")
                            self.random_sleep(1.5, 3)

                    except Exception as e:
                        logger.error(f"处理行 {index} 失败: {e}")
                        traceback.print_exc()
                    
                    # 只有成功处理或跳过，才增加索引
                    index += 1

                if stop_crawling:
                    break
                
                # 翻页逻辑
                # <button type="button" class="btn-next"><i class="el-icon el-icon-arrow-right"></i></button>
                try:
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, "button.btn-next")
                    if "disabled" in next_btn.get_attribute("class"):
                        logger.info("没有下一页了")
                        break
                    
                    self.driver.execute_script("arguments[0].click();", next_btn)
                    page_num += 1
                    self.random_sleep(3, 5) # 翻页等待
                    
                except NoSuchElementException:
                    logger.info("未找到下一页按钮")
                    break
                except Exception as e:
                    logger.error(f"翻页出错: {e}")
                    break

        except Exception as e:
            logger.error(f"处理分类 {category_name} 出错: {e}")

    def process_detail(self, list_title, list_date, category_name):
        try:
            # 等待加载
            # 详情页结构: div.a-main (包含标题、头部信息和正文)
            # 或者是 div.main-content
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.a-main, div.main-content, div.detail-box"))
                )
            except:
                logger.warning("未找到标准正文容器，尝试使用 body")

            self.random_sleep(1, 2)
            
            current_url = self.driver.current_url
            
            # 提取正文
            content_html = ""
            content_text = ""
            
            # 尝试定位正文容器
            # 优先级: div.a-main -> div.main-content -> div.detail-box -> body
            selectors = [
                "div.a-main",
                "div.main-content",
                "div.detail-box",
                "div.content",
                "body"
            ]
            
            for selector in selectors:
                try:
                    content_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    content_html = content_elem.get_attribute("outerHTML")
                    content_text = content_elem.text
                    if len(content_text) > 50: # 确保提取到了有效内容
                        break
                except:
                    continue
            
            if not content_text:
                logger.warning("未能提取到有效正文内容")

            # 提取字段 (复用 regex)
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
            # 截图显示附件: div.fileItem
            attachments = []
            try:
                file_items = self.driver.find_elements(By.CSS_SELECTOR, "div.fileItem")
                for item in file_items:
                    try:
                        name_elem = item.find_element(By.CSS_SELECTOR, "div.title div.el-tooltip")
                        name = name_elem.text.strip()
                        # 链接可能在 onclick 或者需要点击下载
                        # 观察 HTML: 没看到 href. 
                        # 可能是点击 div.fileItem 下载? 
                        # 或者 img src="base64..." 
                        # 如果无法直接获取链接，暂时跳过或记录提示
                        # 这里假设有 hidden link 或 data attribute
                        # 暂时存空链接，标注需要手动下载
                        url = current_url # 暂时代替
                        attachments.append({"name": name, "url": url})
                    except:
                        pass
            except Exception as e:
                logger.warning(f"附件提取失败: {e}")

            # 构造数据
            content_id = self.generate_id(list_title)
            
            data = {
                "_id": content_id,
                "contentId": content_id,
                "title": list_title,
                "createTime": list_date,
                "url": current_url,
                "detail": content_html,
                "briefText": content_text[:200] if content_text else "",
                "source": "中国电信阳光采购网",
                "noticeType": category_name,
                "budget": budget,
                "contacts": contacts,
                "fileUrl": [a['url'] for a in attachments],
                "hasAnnex": len(attachments) > 0,
                "crawl_time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "area": "", # 暂空，可从标题提取
                "industry": "通信",
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
    crawler = WJChinaTelecomChina()
    crawler.run()
