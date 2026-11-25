import os
import time
import random
import logging
import re
import datetime
import traceback
import hashlib
from urllib.parse import urlparse, parse_qs
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
        logging.FileHandler('crawler_chinapost.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class WJChinaPostChina:
    def __init__(self):
        # 初始URL
        self.base_url = "https://cg.11185.cn/zgyzcms/category/bulletinList.html?searchDate=2001-03-14&dates=300&goSearch=&categoryId=88&tabName=%E9%87%87%E8%B4%AD%E4%BF%A1%E6%81%AF&industryName=&status=&page=1"
        self.host = "https://cg.11185.cn"
        
        # 数据库连接
        self.client = MongoClient(config.MONGO_URI)
        self.db = self.client[config.DB_NAME]
        self.collection = self.db[config.COLLECTION_NAME]
        
        # 统计
        self.total_crawled = 0
        self.today_count = 0
        
        # 今天的日期
        self.today = datetime.datetime.now().strftime('%Y-%m-%d')
        # self.today = "2026-03-13" # 调试用: 根据提供的HTML样例日期
        
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

    def run(self):
        logger.info(f"开始采集 中国邮政电子采购与物资供应平台 - {self.today}")
        try:
            self.driver.get(self.base_url)
            self.random_sleep(3, 5)
            self.process_list()
        except Exception as e:
            logger.error(f"采集过程出错: {e}")
            traceback.print_exc()
        finally:
            self.driver.quit()
            logger.info(f"采集结束。今日总采集: {self.today_count} 条")

    def process_list(self):
        page_num = 1
        while True:
            logger.info(f"正在扫描第 {page_num} 页")
            
            # 等待列表加载
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ul.newslist li"))
                )
            except TimeoutException:
                logger.warning("列表加载超时或无数据")
                break

            # 获取列表项
            items = self.driver.find_elements(By.CSS_SELECTOR, "ul.newslist li")
            if not items:
                logger.warning("未找到列表项")
                break

            stop_crawling = False
            has_today_data = False
            
            # 遍历列表项
            # 同样因为可能打开新标签页，记录主窗口句柄
            main_window = self.driver.current_window_handle
            
            for index in range(len(items)):
                try:
                    # 重新获取元素
                    items = self.driver.find_elements(By.CSS_SELECTOR, "ul.newslist li")
                    if index >= len(items):
                        break
                    
                    item = items[index]
                    
                    # 提取日期
                    # <div class="newsDate"><div>2026</div>03/13</div>
                    # text可能会得到 "2026\n03/13"
                    date_text = item.find_element(By.CSS_SELECTOR, "div.newsDate").text.strip()
                    parts = date_text.split()
                    if len(parts) >= 2: # ["2026", "03/13"]
                        year = parts[0]
                        month_day = parts[1].replace('/', '-')
                        pub_date = f"{year}-{month_day}"
                    else:
                        # 尝试另一种解析
                        pub_date = date_text.replace('\n', '-').replace('/', '-')
                    
                    # 提取标题和链接
                    link_elem = item.find_element(By.TAG_NAME, "a")
                    href = link_elem.get_attribute("href")
                    title = link_elem.get_attribute("title")
                    if not title:
                        title = link_elem.find_element(By.TAG_NAME, "h1").text.strip()
                    
                    # 提取额外元数据 (项目编号, 采购方式, 截止时间)
                    # <ul class="newsinfo"><li>项目编号：...</li><li>采购方式：...</li><li>报名截止时间：...</li></ul>
                    meta_info = {}
                    try:
                        info_lis = item.find_elements(By.CSS_SELECTOR, "ul.newsinfo li")
                        for li in info_lis:
                            text = li.text.strip()
                            if "项目编号" in text:
                                meta_info["project_no"] = text.split("：")[-1].strip()
                            elif "采购方式" in text:
                                meta_info["purchase_method"] = text.split("：")[-1].strip()
                            elif "截止时间" in text:
                                meta_info["deadline"] = text.split("：")[-1].strip()
                    except:
                        pass
                    
                    # 日期判断
                    if pub_date < self.today:
                        logger.info(f"发现历史数据 ({pub_date} < {self.today})，停止采集")
                        stop_crawling = True
                        break
                    
                    if pub_date == self.today:
                        has_today_data = True
                        
                        # 查重
                        if self.is_duplicate(title):
                            logger.info(f"跳过重复数据: {title}")
                            continue
                            
                        logger.info(f"发现今日数据: {title} ({pub_date})")
                        
                        # 打开详情页
                        self.driver.execute_script("arguments[0].scrollIntoView(false);", link_elem)
                        self.random_sleep(0.5, 1)
                        
                        # 记录点击前的窗口句柄
                        windows_before = self.driver.window_handles
                        
                        # 点击打开新标签页 (如果是 _blank) 或者 当前页跳转
                        # 这里 href 是直接链接，我们可以直接 open_new_tab 或者 click
                        # 观察 HTML 似乎没有 target="_blank"，可能是直接跳转。
                        # 为了稳妥，用 JS 打开新标签页
                        self.driver.execute_script(f"window.open('{href}', '_blank');")
                        
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
                        
                        try:
                            self.process_detail(title, pub_date, href, meta_info)
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
                # 查找下一页按钮
                # 分页HTML: <a href="javascript:void(0);" onclick="turnPage(2);">下一页</a>
                # 我们可以直接构造 URL 参数 page={page_num+1}
                next_page = page_num + 1
                next_url = f"{self.base_url.split('&page=')[0]}&page={next_page}"
                
                # 检查是否还有下一页
                # 简单检查: 如果当前页没有数据，或者 "下一页" 按钮是 disabled
                next_btns = self.driver.find_elements(By.XPATH, "//a[contains(text(), '下一页')]")
                if not next_btns:
                    logger.info("没有下一页按钮")
                    break
                
                if "disabled" in next_btns[0].get_attribute("class"):
                    logger.info("下一页按钮不可用")
                    break
                
                logger.info(f"跳转到第 {next_page} 页")
                self.driver.get(next_url)
                page_num += 1
                self.random_sleep(2, 4)
                
            except Exception as e:
                logger.error(f"翻页出错: {e}")
                break

    def process_detail(self, list_title, list_date, current_url, meta_info):
        try:
            # 等待加载
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.topTitle"))
            )
            self.random_sleep(1, 2)
            
            # 提取正文 HTML (包含iframe)
            try:
                content_elem = self.driver.find_element(By.ID, "main") # 或 div.block
                content_html = content_elem.get_attribute("outerHTML")
                content_text = content_elem.text
            except:
                content_html = ""
                content_text = ""
            
            # 核心任务: 提取 PDF 链接
            # <iframe id="pdfContainer" src="..."></iframe>
            file_url = ""
            try:
                iframe = self.driver.find_element(By.ID, "pdfContainer")
                src = iframe.get_attribute("src")
                if src:
                    # src 格式: .../viewer.html?file=https://cg.11185.cn/...&page=1
                    parsed = urlparse(src)
                    qs = parse_qs(parsed.query)
                    if 'file' in qs:
                        file_url = qs['file'][0]
                        logger.info(f"提取到 PDF 链接: {file_url}")
            except NoSuchElementException:
                logger.warning("未找到 PDF iframe (pdfContainer)")
            except Exception as e:
                logger.warning(f"提取 PDF 链接失败: {e}")

            # 字段整合
            # 由于正文主要是PDF，我们尽量使用列表页提取的元数据
            
            # 构造数据
            content_id = self.generate_id(list_title)
            
            # 附件列表
            attachments = []
            if file_url:
                attachments.append({"name": "公告原文.pdf", "url": file_url})
            
            # 摘要逻辑：如果有PDF，简要说明；否则使用提取到的正文
            if file_url:
                brief_text = "详情为PDF文件，请下载查看"
                # 如果有PDF，正文detail字段留空，不存iframe代码，避免冗余
                detail_html = "" 
            else:
                brief_text = content_text[:200] if content_text else ""
                detail_html = content_html
            
            data = {
                "_id": content_id,
                "contentId": content_id,
                "title": list_title,
                "createTime": list_date,
                "url": current_url,
                "detail": detail_html, 
                "briefText": brief_text,
                "source": "中国邮政电子采购与物资供应平台",
                "noticeType": "采购公告", # 默认，或者从 meta_info 分析
                "budget": "", # PDF 难提取，暂空
                "contacts": [], # PDF 难提取，暂空
                "fileUrl": [a['url'] for a in attachments],
                "hasAnnex": len(attachments) > 0,
                "crawl_time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "area": "",
                "industry": "邮政",
                "purchaser": "中国邮政", # 默认
                "agent": "",
                "tenderEndTime": meta_info.get("deadline", ""), # 从列表页提取
                "winningBidder": "",
                "winningAmount": "",
                "purchaseMethod": meta_info.get("purchase_method", "") # 从列表页提取
            }
            
            # 补充项目编号到标题或摘要? (可选)
            if meta_info.get("project_no"):
                data["project_no"] = meta_info["project_no"] # 也可以存个额外字段
            
            self.save_data(data)
            
        except Exception as e:
            logger.error(f"详情解析失败: {e}")

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
    crawler = WJChinaPostChina()
    crawler.run()
