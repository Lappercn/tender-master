import os
import time
import random
import logging
import re
import datetime
import traceback
import hashlib
import base64
try:
    import ddddocr
except ImportError:
    ddddocr = None
from pymongo import MongoClient
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
import config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('crawler_guotie.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class WJGuotieChina:
    def __init__(self):
        self.base_url = "https://cg.95306.cn/baseinfor/notice/procurementNotice?bidType=&noticeType=000&transactionType=01&wzType=&title=&bidding=&navigation="
        
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

    def run(self):
        logger.info(f"开始采集 国铁采购平台 - {self.today}")
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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.text_con div.text_row"))
                )
            except TimeoutException:
                logger.warning("列表加载超时或无数据")
                break

            # 获取列表项
            items = self.driver.find_elements(By.CSS_SELECTOR, "div.text_con div.text_row")
            if not items:
                logger.warning("未找到列表项")
                break

            stop_crawling = False
            
            for item in items:
                try:
                    # 提取日期
                    # <div class="declare_time"><span class="declare_time_tit">发布日期：</span><span>2026-03-14</span> </div>
                    date_elem = item.find_element(By.CSS_SELECTOR, "div.declare_time span:nth-child(2)")
                    pub_date = date_elem.text.strip()
                    
                    # 提取标题和ID
                    # <div class="htit"><a href="javascript:;" onclick="noticeDetailNotice('id')" title="...">...</a></div>
                    link_elem = item.find_element(By.CSS_SELECTOR, "div.htit a")
                    title = link_elem.get_attribute("title")
                    if not title:
                        title = link_elem.text.strip()
                        
                    onclick_text = link_elem.get_attribute("onclick")
                    notice_id = ""
                    if onclick_text:
                        match = re.search(r"noticeDetailNotice\(['\"](.+?)['\"]\)", onclick_text)
                        if match:
                            notice_id = match.group(1)
                    
                    # 提取标签/类型 (如 [项目公告], 谈判采购)
                    try:
                        type_tag = item.find_element(By.CSS_SELECTOR, "div.tit_left").text.strip() # [项目公告]
                        category_tags = item.find_elements(By.CSS_SELECTOR, "ul.row_tab_list li")
                        tags = [t.text.strip() for t in category_tags]
                        notice_type = f"{type_tag} {' '.join(tags)}"
                    except:
                        notice_type = "国铁公告"

                    # 日期判断
                    if pub_date < self.today:
                        logger.info(f"发现历史数据 ({pub_date} < {self.today})，停止采集")
                        stop_crawling = True
                        break
                    
                    if pub_date == self.today:
                        # 查重
                        if self.is_duplicate(title):
                            logger.info(f"跳过重复数据: {title}")
                            continue
                            
                        logger.info(f"发现今日数据: {title} ({pub_date})")
                        
                        if notice_id:
                            detail_url = f"https://cg.95306.cn/baseinfor/notice/informationShow?id={notice_id}"
                            self.open_detail_in_new_tab(detail_url, title, pub_date, notice_type)
                            # 详情采集完毕后，增加随机等待 1.5-3 秒，降低反爬风险
                            logger.info("详情采集完毕，等待中...")
                            self.random_sleep(1.5, 3)
                        else:
                            logger.warning(f"未找到ID，跳过: {title}")
                            
                except StaleElementReferenceException:
                    logger.warning("元素失效，跳过当前项")
                    continue
                except Exception as e:
                    logger.error(f"处理列表项出错: {e}")
                    continue

            if stop_crawling:
                break
            
            # 翻页逻辑
            try:
                # <div class="next_page" ...>下一页</div>
                next_btn = self.driver.find_element(By.CSS_SELECTOR, "div.next_page")
                
                # 检查是否禁用 (cursor: not-allowed 或其他样式，根据HTML: style="cursor:pointer;")
                # 上一页是 cursor:not-allowed, 下一页如果是 cursor:not-allowed 则禁用
                style = next_btn.get_attribute("style")
                if "not-allowed" in style:
                    logger.info("没有下一页了")
                    break
                
                # 点击下一页
                self.driver.execute_script("arguments[0].click();", next_btn)
                page_num += 1
                self.random_sleep(3, 5) # 翻页等待稍长
                
            except NoSuchElementException:
                logger.info("未找到下一页按钮")
                break
            except Exception as e:
                logger.error(f"翻页出错: {e}")
                break

    def open_detail_in_new_tab(self, url, title, pub_date, notice_type):
        try:
            # 打开新标签页
            self.driver.execute_script(f"window.open('{url}', '_blank');")
            self.random_sleep(1, 2)
            
            # 切换句柄
            handles = self.driver.window_handles
            self.driver.switch_to.window(handles[-1])
            
            # 优先检查并处理验证码 (等待3秒检测)
            self.handle_captcha()
            
            # 等待内容加载
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.article_detail"))
                )
                self.random_sleep(1, 2)
                
                # 采集详情
                self.extract_detail(title, pub_date, url, notice_type)
                
            except TimeoutException:
                logger.warning(f"详情页加载超时: {url}")
            finally:
                # 关闭标签页
                self.driver.close()
                self.driver.switch_to.window(handles[0])
                
        except Exception as e:
            logger.error(f"打开详情页失败: {e}")

    def handle_captcha(self):
        """处理滑块验证码"""
        try:
            # 1. 快速检测验证码是否存在
            try:
                WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'layui-layer-title') and contains(text(), '安全验证')]"))
                )
            except TimeoutException:
                # 未检测到验证码，直接返回
                return

            logger.info(">>> 检测到滑块验证码，开始尝试破解...")
            
            if not ddddocr:
                logger.error("未安装 ddddocr 库，无法破解验证码！请运行: pip install ddddocr")
                return

            det = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)

            # 最多重试 3 次
            for i in range(3):
                logger.info(f"第 {i+1} 次尝试破解...")
                
                # 获取验证码图片
                # layui 验证码通常有两个 canvas: 
                # 背景图: canvas width="278" (通常是第一个)
                # 滑块图: canvas width="63" class="block"
                try:
                    js_bg = "return document.querySelector('#captcha canvas:not(.block)').toDataURL('image/png');"
                    js_block = "return document.querySelector('#captcha canvas.block').toDataURL('image/png');"
                    
                    bg_data = self.driver.execute_script(js_bg)
                    block_data = self.driver.execute_script(js_block)
                    
                    if not bg_data or not block_data:
                        logger.warning("无法获取验证码图片数据")
                        continue
                        
                    # 解码图片
                    bg_bytes = base64.b64decode(bg_data.split(',')[1])
                    block_bytes = base64.b64decode(block_data.split(',')[1])
                    
                    # 识别缺口距离
                    res = det.slide_match(block_bytes, bg_bytes, simple_target=True)
                    target_x = res['target'][0]
                    logger.info(f"识别缺口位置: {target_x}")
                    
                    # 定位滑块按钮
                    slider_btn = self.driver.find_element(By.CSS_SELECTOR, "div.slider")
                    
                    # 生成轨迹并拖动
                    action = ActionChains(self.driver)
                    action.click_and_hold(slider_btn).perform()
                    
                    tracks = self.get_tracks(target_x)
                    for track in tracks:
                        action.move_by_offset(xoffset=track, yoffset=random.randint(-1, 1)).perform()
                        # 极短的随机停顿，模拟人手抖动
                        time.sleep(random.uniform(0.01, 0.03))
                    
                    self.random_sleep(0.2, 0.5)
                    action.release().perform()
                    
                    # 等待验证结果
                    self.random_sleep(1.5, 2.5)
                    
                    # 检查验证码弹窗是否消失
                    try:
                        self.driver.find_element(By.XPATH, "//div[contains(@class, 'layui-layer-title') and contains(text(), '安全验证')]")
                        logger.warning("验证失败，点击刷新重试...")
                        # 刷新验证码
                        refresh_btn = self.driver.find_element(By.CSS_SELECTOR, "i.refreshIcon")
                        refresh_btn.click()
                        self.random_sleep(1, 2)
                    except NoSuchElementException:
                        logger.info(">>> 验证通过！")
                        return
                        
                except Exception as e:
                    logger.error(f"单次破解过程出错: {e}")
                    continue
            
            logger.error("3次尝试均失败，放弃破解")

        except Exception as e:
            logger.error(f"验证码处理模块异常: {e}")

    def get_tracks(self, distance):
        """生成模拟人手移动的轨迹 (Ease Out Quart)"""
        # 修正距离：减去滑块初始偏移 (约10px)
        distance -= 10
        
        tracks = []
        current = 0
        
        # 模拟人手：先快后慢，使用 easeOutQuart 曲线
        # 总步数，控制在 30 步左右完成，配合 sleep(0.02) 约 0.6秒
        steps = 30
        
        for i in range(steps):
            # x: 进度 0 -> 1
            x = (i + 1) / steps
            # y: easeOutQuart = 1 - (1-x)^4
            y = 1 - pow(1 - x, 4)
            
            target_pos = distance * y
            move = target_pos - current
            
            # 必须取整
            move_int = int(round(move))
            
            # 如果移动距离太小，积累到下一步
            if move_int == 0 and i < steps - 1:
                continue
            
            tracks.append(move_int)
            current += move_int
            
        # 补齐剩余差距
        if current < distance:
            tracks.append(int(distance - current))
        elif current > distance:
            tracks.append(int(distance - current))
            
        return tracks

    def extract_detail(self, list_title, list_date, current_url, notice_type):
        try:
            # 获取正文
            content_elem = self.driver.find_element(By.CSS_SELECTOR, "div.article_detail")
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
            attachments = []
            links = content_elem.find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute("href")
                text = link.text.strip()
                if href and ('.pdf' in href or '.doc' in href or '.xls' in href or '.zip' in href or 'download' in href):
                    # 补全相对路径
                    if not href.startswith("http"):
                        href = "https://cg.95306.cn" + href if href.startswith("/") else "https://cg.95306.cn/" + href
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
                "source": "国铁采购平台",
                "noticeType": notice_type,
                "budget": budget,
                "contacts": contacts,
                "fileUrl": [a['url'] for a in attachments],
                "hasAnnex": len(attachments) > 0,
                "crawl_time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "area": "",
                "industry": "铁路",
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
    crawler = WJGuotieChina()
    crawler.run()
