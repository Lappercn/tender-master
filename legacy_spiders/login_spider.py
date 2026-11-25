import logging
import random
import sys
import time
from datetime import datetime, timedelta

import schedule
from pymongo import MongoClient
import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, InvalidSessionIdException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys # Added for Keys import
from webdriver_manager.chrome import ChromeDriverManager
import tempfile

# --- 日志配置 ---
# 创建一个日志记录器，同时输出到文件和控制台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/login_spider.log", mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

import os

# --- 配置 ---
# 在这里填入您的账号和密码（或通过环境变量 QIANLIMA_USERNAME / QIANLIMA_PASSWORD 传入）
USERNAME = os.getenv("QIANLIMA_USERNAME", "YOUR_USERNAME")  # 请替换为您的账号/手机号
PASSWORD = os.getenv("QIANLIMA_PASSWORD", "YOUR_PASSWORD")  # 请替换为您的密码
LOGIN_URL = "https://vip.qianlima.com/login/"
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB = "qianlima"
MONGO_COLLECTION = "tender_data"
MONGO_KEYWORDS_COLLECTION = "search_keywords"

# 关键词列表（首次写入MongoDB用）
INIT_KEYWORDS = [
    "5G", "万科", "世界", "业主", "中烟", "乳品", "五粮液", "交车仪式", "交通银行", "人寿", "会展", "会议", "伴手礼", "体检", "供应商", "供应商入围", "促销", "保利", "保险", "保险公司", "健康", "健身", "入围", "入库", "制作", "动漫", "医疗", "医疗器械", "医药", "博物馆", "古井贡", "周年庆", "售楼部", "商超", "国窖", "大学", "奔驰", "奖", "奢侈品", "娇子", "字节跳动", "定制", "宝马", "客户服务", "宣传", "宣传品", "宣传用品", "家具", "家居", "家电", "家纺", "峰会", "平台", "年会", "康养", "建库", "建设银行", "开盘", "影视", "影视周边", "快消", "户外", "护肤", "招商", "招商会", "招商活动", "收藏品", "政务", "政务单位", "政务宣传", "政务工程", "政务平台", "政务招标", "政务推广", "政务机关", "政务机构", "政务活动", "政务礼品", "政务系统", "政务部门", "政务采购", "政务采购中心", "政务采购单位", "政务采购工程", "政务采购平台", "政务采购招标", "政务采购机构", "政务采购系统", "政务采购网", "政务采购部门", "政务采购项目", "政务项目", "政府", "故宫", "文创", "文化衫", "文旅", "旅游", "日化", "景区", "智能", "智能家居", "服饰", "本香", "机上", "机场", "权益", "杯", "校友会", "校庆", "比选", "水井坊", "泸州老窖", "洋河", "活动", "添加", "游戏", "潮玩", "烘焙", "烟叶", "烟草", "物料", "物料品", "特许", "现代", "珠宝", "电商", "电竞", "盲盒", "直播", "礼", "礼品", "福利", "科技", "积分", "移动", "穿戴", "穿戴设备", "箱包", "精品", "红旗", "纪念品", "纸", "终端", "美团", "美妆", "美术馆", "联通", "腕表", "腾讯", "航司", "航空", "茅台", "茶具", "蔚来", "衍生品", "论坛", "设计", "贺岁", "资产", "资管", "赛事", "赛事赞助", "车主", "运动", "运营商", "连锁", "通信", "邮储", "酒", "酒具", "采购", "银行", "长城", "陶瓷", "集团", "零售", "食品", "餐具", "饮料", "饰品", "黄金", "龙湖"
]

def get_keywords_from_mongo():
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    col = db[MONGO_KEYWORDS_COLLECTION]
    doc = col.find_one({"_id": "keywords"})
    if doc and "keywords" in doc:
        keywords = doc["keywords"]
    else:
        # 首次写入
        col.update_one({"_id": "keywords"}, {"$set": {"keywords": INIT_KEYWORDS}}, upsert=True)
        keywords = INIT_KEYWORDS
    client.close()
    return keywords

def save_keywords_to_mongo(keywords):
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    col = db[MONGO_KEYWORDS_COLLECTION]
    col.update_one({"_id": "keywords"}, {"$set": {"keywords": keywords}}, upsert=True)
    client.close()


def save_to_mongo(data_list):
    """
    将数据列表保存到MongoDB，使用upsert避免重复键错误
    """
    if not data_list:
        logging.info("本次没有提取到新数据，无需保存。")
        return
    try:
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        collection = db[MONGO_COLLECTION]
        
        # 修改为逐条插入并使用upsert策略
        insert_count = 0
        update_count = 0
        for data in data_list:
            # 如果contentId存在，使用它作为唯一标识；否则使用URL
            if data.get('contentId'):
                query = {'contentId': data['contentId']}
            else:
                query = {'url': data['url']}
                
            # 使用update_one并设置upsert=True，存在则更新，不存在则插入
            result = collection.update_one(query, {'$set': data}, upsert=True)
            
            if result.upserted_id:
                insert_count += 1
            elif result.modified_count > 0:
                update_count += 1
        
        logging.info(f"成功保存数据到MongoDB: 新增 {insert_count} 条，更新 {update_count} 条。")
        client.close()
    except Exception as e:
        logging.exception("保存到MongoDB时出错")


def get_element_text_or_na(parent_element, by, value):
    try:
        return parent_element.find_element(by, value).text.strip()
    except NoSuchElementException:
        return 'N/A'


def scrape_details(driver, detail_list):
    scraped_data = []
    for detail in detail_list:
        try:
            # 缓慢滚动到元素，使其可见
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", detail)
            time.sleep(random.uniform(0.5, 1.5)) # 模拟查看

            title_element = detail.find_element(By.CSS_SELECTOR, "p.title a")
            title = title_element.text.strip()
            url = title_element.get_attribute('href')
            
            pub_date = get_element_text_or_na(detail, By.XPATH, ".//span[normalize-space()='发布时间：']/following-sibling::span")

            if pub_date != 'N/A':
                try:
                    item_date = datetime.strptime(pub_date, '%Y-%m-%d').date()
                    cutoff_date = datetime.now().date()
                    if item_date < cutoff_date:
                        logging.info(f"发现过旧项目 (发布于 {item_date})，将停止抓取当前订阅器分类。")
                        return None # 使用None作为信号，表示应停止当前分类
                except ValueError:
                    logging.warning(f"无法解析项目 '{title}' 的日期 '{pub_date}'。跳过日期检查。")
            else:
                logging.warning(f"项目 '{title}' 未找到发布日期。跳过日期检查。")

            data = {
                'title': title,
                'url': url,
                'pub_date': pub_date,
                'zhaobiao_danwei': get_element_text_or_na(detail, By.XPATH, ".//span[normalize-space()='招标单位：']/following-sibling::span"),
                'suoshu_diqu': get_element_text_or_na(detail, By.XPATH, ".//span[normalize-space()='所属地区：']/following-sibling::span"),
                'baoming_jiezhi_shijian': get_element_text_or_na(detail, By.XPATH, ".//span[normalize-space()='报名截止时间：']/following-sibling::span"),
                'zhaobiao_daili': get_element_text_or_na(detail, By.XPATH, ".//span[normalize-space()='招标代理：']/following-sibling::span"),
                'project_type': get_element_text_or_na(detail, By.CSS_SELECTOR, "div.project-type span")
            }
            scraped_data.append(data)
            logging.info(f"成功抓取项目: {data['title']}")
        except StaleElementReferenceException:
            logging.warning("捕获到StaleElementReferenceException，元素已过时，正在跳过此项目。")
            continue
        except Exception:
            logging.warning("提取单条数据时出错，已跳过。", exc_info=True)
            continue
    return scraped_data


def dismiss_account_risk_popup(driver, wait, max_wait=6):
    """
    检测并关闭“账号风险提醒”弹窗：点击“取消”按钮。
    如果弹窗未出现则直接跳过。
    """
    try:
        # 登录后可能需要短暂时间让弹窗渲染
        logging.info("登录成功，等待检测账号风险弹窗...")
        time.sleep(random.uniform(5.0, 8.0))
        try:
            cancel_btn = WebDriverWait(driver, max_wait).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#dialogAccountRsk .opc-btn.cancel-btn"))
            )
        except TimeoutException:
            logging.info("未检测到账号风险提醒弹窗，继续后续流程。")
            return False

        # 尝试将按钮滚动到视口中
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cancel_btn)
        except Exception:
            pass

        # 增加等待：点击前随机等待，模拟人工确认
        logging.info("弹窗已出现，等待几秒后再点击取消...")
        time.sleep(random.uniform(2.0, 4.0))

        # 点击“取消”按钮（失败则降级为JS点击）
        try:
            cancel_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", cancel_btn)

        logging.info("检测到账号风险提醒弹窗，已点击‘取消’。")

        # 增加等待：点击后等待弹窗消失及页面恢复
        logging.info("点击取消后，等待页面恢复...")
        time.sleep(random.uniform(2.0, 4.0))

        # 等待弹窗消失（若未消失则不阻塞主流程）
        try:
            WebDriverWait(driver, 3).until(
                EC.invisibility_of_element_located((By.ID, "dialogAccountRsk"))
            )
        except Exception:
            pass
        return True
    except Exception:
        logging.exception("处理账号风险弹窗时发生异常")
        return False


def scrape_subscription_data(driver, wait):
    """
    循环抓取所有订阅器的数据
    """
    def get_yesterday_titles():
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        col = db[MONGO_COLLECTION]
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        docs = col.find({"createTime": yesterday})
        titles = set()
        count = 0
        for doc in docs:
            if 'title' in doc:
                titles.add(doc['title'])
                count += 1
        client.close()
        logging.info(f"昨日({yesterday})已采集标题数: {count}")
        return titles

    yesterday_titles = get_yesterday_titles()
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    def should_collect(item):
        create_time = ''
        title = ''
        # 兼容item为WebElement或dict
        if isinstance(item, dict):
            create_time = item.get('createTime', '')
            title = item.get('title', '')
        else:
            # WebElement，需在下方采集后再判断
            return True
        try:
            item_date = datetime.strptime(create_time, '%Y-%m-%d').date()
        except Exception:
            logging.info(f"跳过无效日期数据: title={title} createTime={create_time}")
            return False
        if item_date == today:
            logging.info(f"采集今日数据: {title}")
            return True
        elif item_date == yesterday:
            if title in yesterday_titles:
                logging.info(f"昨天的数据已存在，跳过: {title}")
                return False
            else:
                logging.info(f"补采集昨日数据: {title}")
                return True
        else:
            logging.info(f"跳过非今日/昨日数据: {title} createTime={create_time}")
            return False

    try:
        logging.info("登录成功！开始抓取订阅信息...")

        # 1. 点击"订阅信息"菜单
        logging.info("正在点击'订阅信息'菜单...")
        try:
            # 优先尝试通过title属性定位，这通常更准确（基于用户提供的HTML结构: <a title="订阅信息">...</a>）
            subscription_menu = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[@title='订阅信息']"))
            )
        except TimeoutException:
            logging.info("通过title定位超时，尝试通过文本内容定位...")
            try:
                # 备用方案1：通过内部span文本定位
                subscription_menu = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//a[.//span[contains(text(), '订阅信息')]]"))
                )
            except TimeoutException:
                # 备用方案2：直接查找包含文本的元素
                subscription_menu = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), '订阅信息')]"))
                )

        # 确保元素可见再点击
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", subscription_menu)
            time.sleep(0.5)
        except Exception:
            pass

        try:
            subscription_menu.click()
        except Exception:
            logging.info("普通点击失败，尝试JS点击...")
            driver.execute_script("arguments[0].click();", subscription_menu)
            
        logging.info("已点击'订阅信息'，等待订阅器列表页面加载...")

        # 替换不稳定的sleep，改为等待页面上明确的标志性元素"订阅器列表"标题出现
        wait.until(
            EC.presence_of_element_located((By.XPATH, "//h2[normalize-space()='订阅器列表']"))
        )
        logging.info("订阅器列表页面已加载。")

        # 新增：等待列表中的第一个项目出现，确保列表内容已动态加载
        logging.info("等待第一个订阅器项目('全行业')出现...")
        wait.until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'menu')]//p[@title='全行业']"))
        )
        logging.info("订阅器项目已加载。")

        # 2. 首先获取所有"标讯订阅"下的订阅器名称
        logging.info("获取所有订阅器列表...")
        # 采用更精确的层级定位，从H2标题找到其后的第一个menu容器，再获取内部的项目
        subscriber_elements = wait.until(
            EC.presence_of_all_elements_located((By.XPATH, "//h2[normalize-space()='订阅器列表']/following-sibling::div[contains(@class, 'menu')][1]//p[contains(@class, 'menu-item')]"))
        )
        subscriber_titles = [el.get_attribute('title') for el in subscriber_elements if el.get_attribute('title')]
        logging.info(f"找到 {len(subscriber_titles)} 个订阅器: {subscriber_titles}")

        # 3. 循环处理每一个订阅器
        for title in subscriber_titles:
            logging.info(f"\n{'='*20}\n>> 开始处理订阅器: {title}\n{'='*20}")
            try:
                # 维稳措施 1: 每次循环开始时，重新聚焦于主窗口，防止session丢失
                logging.info("重新聚焦主浏览器窗口以确保会话稳定...")
                driver.switch_to.window(driver.window_handles[0])
                time.sleep(random.uniform(1, 2))

                # 重新定位并点击当前循环的订阅器，避免元素过期
                logging.info(f"准备点击订阅器: <{title}>")
                current_subscriber = wait.until(
                    EC.element_to_be_clickable((By.XPATH, f"//div[contains(@class, 'menu')]//p[@title='{title}']"))
                )
                current_subscriber.click()
                logging.info(f"已切换到 <{title}>, 等待筛选区域完全加载...")

                # 增加一个更可靠的等待，确保切换订阅器后，筛选区域已重新渲染
                wait.until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'info-filter')]"))
                )
                logging.info("筛选区域已加载。")
                time.sleep(random.uniform(1, 2)) # 短暂暂停，应对可能的动画效果

                # -- 开始对当前订阅器执行筛选和抓取 --

                # A. 根据您的要求，跳过日期筛选步骤
                logging.info("步骤A: 已跳过日期筛选。")

                # B. 点击"按时间排序"
                logging.info("步骤B: 点击'按时间排序'...")
                sort_by_time_button = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//span[normalize-space()='按时间排序']/parent::span/parent::label"))
                )
                sort_by_time_button.click()
                time.sleep(random.uniform(1, 2))

                # C. 点击"明细"视图
                logging.info("步骤C: 切换到'明细'视图...")
                details_view_button = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//span[normalize-space()='明细']/parent::span/parent::label"))
                )
                details_view_button.click()
                logging.info("等待视图切换...")
                time.sleep(random.uniform(3, 5))

                # D. 循环翻页抓取 (加入日期检查和人性化滚动)
                page_number = 1
                stop_current_subscriber = False
                
                # today = datetime.now() # Moved outside loop
                # Monday is 0, Sunday is 6
                if today.weekday() == 0:  # If it's Monday
                    cutoff_date = today - timedelta(days=3)
                    logging.info(f"今天是周一，设置数据日期阈值：抓取自 {cutoff_date} (上周五) 以来的数据。")
                else:  # Other days
                    cutoff_date = today
                    logging.info(f"设置数据日期阈值：只抓取发布于 {cutoff_date} (今天) 的数据。")

                while True:
                    logging.info(f"--- <{title}> 开始处理第 {page_number} 页 ---")

                    wait.until(EC.presence_of_element_located((By.ID, "search-content-main-part")))
                    time.sleep(random.uniform(1, 2))

                    logging.info("开始人性化滚动页面...")
                    # 替换之前的瞬间滚动，改为分段平滑滚动
                    current_scroll_position, new_height= 0, 1
                    speed = random.uniform(200, 400) # 每次滚动的像素距离
                    while current_scroll_position <= new_height:
                        current_scroll_position += speed
                        driver.execute_script("window.scrollTo(0, {});".format(current_scroll_position))
                        new_height = driver.execute_script("return document.body.scrollHeight;")
                        time.sleep(random.uniform(0.1, 0.3)) # 模拟滚动中的微小停顿
                    logging.info("页面滚动到底部。")


                    items = driver.find_elements(By.CSS_SELECTOR, "div.list-single")
                    if not items and page_number == 1:
                        logging.warning(f"订阅器 <{title}> 筛选后没有找到数据，继续下一个。")
                        break

                    extracted_data = []
                    # ... [数据提取逻辑保持不变] ...
                    for item in items:
                        try:
                            # 优先取span内容，支持"几分钟前"等
                            try:
                                create_time = item.find_element(By.CSS_SELECTOR, "div.content-time span").text.strip()
                            except Exception:
                                create_time = item.find_element(By.CSS_SELECTOR, "div.content-time").text.strip()
                            
                            # --- 日期检查逻辑 ---
                            is_recent = True
                            try:
                                # 只处理绝对日期，相对日期（如"xx分钟前"）默认都算作近期
                                if '前' not in create_time and '昨天' not in create_time:
                                    item_date = datetime.strptime(create_time, '%Y-%m-%d').date()
                                    if item_date < cutoff_date:
                                        logging.info(f"发现过旧项目 (发布于 {item_date})，将停止抓取订阅器 <{title}>。")
                                        is_recent = False
                                        stop_current_subscriber = True
                            except ValueError:
                                logging.warning(f"无法解析日期字符串: '{create_time}'，默认当作近期项目处理。")
                            except Exception as e:
                                logging.warning(f"日期检查时发生未知错误: {e}")

                            if not is_recent:
                                break # 发现过旧数据，停止处理本页的剩余项目

                            # 提取标题和URL
                            try:
                                title_element = item.find_element(By.CSS_SELECTOR, "a.content-tit")
                                title_text = title_element.text
                                url = title_element.get_attribute('href')
                                content_id = int(title_element.get_attribute('data-cid')) if title_element.get_attribute('data-cid') else None
                            except Exception:
                                title_text = ''
                                url = ''
                                content_id = None

                            # 提取区域信息
                            try:
                                area = item.find_element(By.XPATH, ".//div[@class='con-address' and not(contains(@class, 'con-type')) and not(contains(@class, 'con-file'))]").text
                            except Exception:
                                area = ''

                            # 提取公告类型
                            try:
                                notice_type = item.find_element(By.XPATH, ".//div[contains(@class, 'con-address') and contains(@class, 'con-type')]/span").text
                            except Exception:
                                notice_type = ''

                            # 提取附件信息
                            try:
                                has_annex = True if item.find_elements(By.XPATH, ".//span[@title='该公告内有附件可下载']") else False
                            except Exception:
                                has_annex = False

                            # 提取正文预览
                            try:
                                brief_text = item.find_element(By.XPATH, ".//span[normalize-space()='正文预览：']/following-sibling::span").text
                            except Exception:
                                brief_text = ''

                            # 提取招标单位
                            try:
                                tenderees = item.find_element(By.XPATH, ".//span[normalize-space()='招标单位：']/following-sibling::span").text
                            except Exception:
                                tenderees = ''

                            # 提取代理单位
                            try:
                                agent = item.find_element(By.XPATH, ".//span[normalize-space()='代理单位：']/following-sibling::span").text
                            except Exception:
                                agent = ''

                            # 提取预算信息
                            try:
                                budget = item.find_element(By.XPATH, ".//span[normalize-space()='招标预算：']/following-sibling::span").text
                            except Exception:
                                budget = ''

                            # 提取截止时间
                            try:
                                tender_end_time = item.find_element(By.XPATH, ".//span[normalize-space()='投标截止时间：']/following-sibling::span").text
                            except Exception:
                                try:
                                    tender_end_time = item.find_element(By.XPATH, ".//span[normalize-space()='报名截止时间：']/following-sibling::span").text
                                except Exception:
                                    tender_end_time = ''

                            data_dict = {
                                "contentId": content_id, 
                                "agent": agent, 
                                "area": area, 
                                "briefText": brief_text, 
                                "budget": budget,
                                "budget_label": None, 
                                "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S"), 
                                "createTime": create_time,
                                "hasAnnex": has_annex, 
                                "highlightedWords": None, 
                                "keywords": None, 
                                "noticeType": notice_type,
                                "tenderEndTime": tender_end_time, 
                                "tenderees": tenderees, 
                                "title": title_text, 
                                "url": url,
                            }
                            extracted_data.append(data_dict)
                        except Exception:
                            logging.warning("提取单条数据时出错，已跳过。", exc_info=True)
                            continue

                    logging.info(f"成功提取 {len(extracted_data)} 条数据。")
                    save_to_mongo(extracted_data)
                    
                    if stop_current_subscriber:
                        logging.info(f"已停止抓取订阅器 <{title}>，因为它包含过旧的数据。")
                        break # 停止翻页，处理下一个订阅器

                    try:
                        next_page_button = driver.find_element(By.XPATH, "//button[contains(@class, 'btn-next')]")
                        if next_page_button.is_enabled():
                            # 翻页前随机“思考”
                            sleep_duration = random.uniform(1, 10)
                            logging.info(f"准备点击下一页...将在 {sleep_duration:.2f} 秒后继续。")
                            time.sleep(sleep_duration)
                            
                            next_page_button.click()
                            page_number += 1
                            time.sleep(random.uniform(4, 6)) # 等待新页面加载
                        else:
                            logging.info(f"到达 <{title}> 的最后一页，抓取结束。")
                            break
                    except Exception:
                        logging.info("无法找到下一页按钮，当前订阅器抓取结束。")
                        break

            except Exception as e:
                logging.exception(f"处理订阅器 <{title}> 时发生严重错误")
                logging.info("将继续处理下一个订阅器...")
                continue

        logging.info("\n所有订阅器处理完毕，任务圆满结束！")

        # 新增：采集“标讯”
        try:
            logging.info("准备点击'标讯'菜单...")
            bx_menu = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//ul[contains(@class,'el-menu')]//li[normalize-space()='标讯']"))
            )
            time.sleep(2)
            bx_menu.click()
            logging.info("已点击'标讯'，等待页面加载...")
            time.sleep(3)

            # 关键词分组输入与采集
            keywords = get_keywords_from_mongo()
            group_size = 6
            total_groups = (len(keywords) + group_size - 1) // group_size
            for group_idx in range(total_groups):
                group_keywords = keywords[group_idx*group_size:(group_idx+1)*group_size]
                if not group_keywords:
                    continue
                logging.info(f"正在输入第{group_idx+1}/{total_groups}组关键词: {group_keywords}")
                # 定位输入框
                search_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='请输入产品、项目名称、编号或其他关键词，多个词用空格隔开']")))
                # 强制清空输入框（Ctrl+A+Delete，防止累加）
                try:
                    search_input.send_keys(Keys.CONTROL, 'a')
                    search_input.send_keys(Keys.DELETE)
                    time.sleep(0.5)
                except Exception:
                    pass
                search_input.clear()
                time.sleep(random.uniform(1, 2))
                # 输入关键词（空格分隔）
                search_input.send_keys(' '.join(group_keywords))
                time.sleep(random.uniform(1, 2))
                # 点击搜索按钮
                search_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'search-button')]//i[contains(@class,'icon-search')]")))
                search_btn.click()
                logging.info("已点击搜索，等待结果加载...")
                time.sleep(random.uniform(3, 5))

                # 1. 点击“发布时间”筛选，选择“当日”
                logging.info("点击'发布时间'筛选...")
                time.sleep(random.uniform(3, 5))  # 模拟人工思考时间
                bx_pub_time = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//p[@class='cell-title' and contains(text(),'发布时间')]/following-sibling::div//p[contains(@class,'list-item-text') and contains(text(),'当日')]"))
                )
                bx_pub_time.click()
                logging.info("已选择'当日'发布")
                time.sleep(random.uniform(2, 4))  # 模拟人工等待筛选生效

                # 在筛选金额前，先点击“查看更多筛选”按钮（如果存在）
                try:
                    see_more_btn = driver.find_element(By.XPATH, "//p[contains(@class,'seeMore') and contains(.,'查看更多筛选')]")
                    if see_more_btn.is_displayed():
                        see_more_btn.click()
                        logging.info("已点击查看更多筛选，等待折叠栏展开...")
                        time.sleep(random.uniform(1, 2))
                except Exception:
                    logging.info("未找到或无需点击查看更多筛选。")

                # 2. 点击“项目金额”筛选，选择“200万以上”
                logging.info("点击'项目金额'筛选...")
                time.sleep(random.uniform(3, 5))  # 模拟人工思考时间
                # 先点开“项目金额”主按钮
                amount_filter_btn = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//p[@class='cell-title' and contains(text(),'项目金额')]"))
                )
                amount_filter_btn.click()
                time.sleep(random.uniform(1, 2))  # 等下拉弹出
                # 再点“200万以上”
                bx_amount = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//p[contains(@class,'list-item-text') and contains(text(),'200万以上')]"))
                )
                bx_amount.click()
                logging.info("已选择'200万以上'")
                time.sleep(random.uniform(2, 4))  # 模拟人工等待筛选生效

                # 3. 点击“信息类型”筛选，选择“公告”和“招标公告”
                logging.info("点击'信息类型'筛选，选择'公告'和'招标公告'...")
                time.sleep(random.uniform(3, 5))  # 模拟人工思考时间
                # 先点开“公告”
                bx_notice = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//span[contains(@class,'labelaname') and normalize-space()='公告']/ancestor::label"))
                )
                bx_notice.click()
                time.sleep(random.uniform(1, 3))  # 模拟人工等待选项展开
                # 再点开“招标公告”
                bx_zb_notice = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//label[.//span[contains(text(),'招标公告')]]"))
                )
                bx_zb_notice.click()
                time.sleep(random.uniform(2, 4))  # 模拟人工等待筛选生效

                # 采集与翻页（复用原有采集逻辑）
                page_number = 1
                while True:
                    logging.info(f"--- <标讯-关键词组{group_idx+1}> 开始处理第 {page_number} 页 ---")
                    wait.until(EC.presence_of_element_located((By.ID, "search-content-main-part")))
                    time.sleep(random.uniform(1, 2))
                    # 人性化滚动
                    current_scroll_position, new_height= 0, 1
                    speed = random.uniform(200, 400)
                    while current_scroll_position <= new_height:
                        current_scroll_position += speed
                        driver.execute_script("window.scrollTo(0, {});".format(current_scroll_position))
                        new_height = driver.execute_script("return document.body.scrollHeight;")
                        time.sleep(random.uniform(0.1, 0.3))
                    logging.info("页面滚动到底部。")
                    # 数据采集
                    items = driver.find_elements(By.CSS_SELECTOR, "div.list-single")
                    extracted_data = []
                    for item in items:
                        if not should_collect(item):
                            continue
                        try:
                            # 标题
                            try:
                                title_element = item.find_element(By.CSS_SELECTOR, "a.content-tit")
                                title_text = title_element.text
                                url = title_element.get_attribute('href')
                                content_id = int(title_element.get_attribute('data-cid')) if title_element.get_attribute('data-cid') else None
                            except Exception:
                                title_text = ''
                                url = ''
                                content_id = None
                            # 时间
                            try:
                                create_time = item.find_element(By.CSS_SELECTOR, "div.content-time span").text.strip()
                            except Exception:
                                try:
                                    create_time = item.find_element(By.CSS_SELECTOR, "div.content-time").text.strip()
                                except Exception:
                                    create_time = ''
                            # 区域
                            try:
                                area = item.find_element(By.XPATH, ".//div[@class='con-address' and not(contains(@class, 'con-type')) and not(contains(@class, 'con-file'))]").text
                            except Exception:
                                area = ''
                            # 公告类型
                            try:
                                notice_type = item.find_element(By.XPATH, ".//div[contains(@class, 'con-address') and contains(@class, 'con-type')]/span").text
                            except Exception:
                                notice_type = ''
                            # 附件
                            try:
                                has_annex = True if item.find_elements(By.XPATH, ".//span[@title='该公告内有附件可下载']") else False
                            except Exception:
                                has_annex = False
                            # 正文预览
                            try:
                                brief_text = item.find_element(By.XPATH, ".//span[normalize-space()='正文预览：']/following-sibling::span").text
                            except Exception:
                                brief_text = ''
                            # 招标单位
                            try:
                                tenderees = item.find_element(By.XPATH, ".//span[normalize-space()='招标单位：']/following-sibling::span").text
                            except Exception:
                                tenderees = ''
                            # 代理单位
                            try:
                                agent = item.find_element(By.XPATH, ".//span[normalize-space()='代理单位：']/following-sibling::span").text
                            except Exception:
                                agent = ''
                            # 预算
                            try:
                                budget = item.find_element(By.XPATH, ".//span[normalize-space()='招标预算：']/following-sibling::span").text
                            except Exception:
                                budget = ''
                            # 截止时间
                            try:
                                tender_end_time = item.find_element(By.XPATH, ".//span[normalize-space()='投标截止时间：']/following-sibling::span").text
                            except Exception:
                                try:
                                    tender_end_time = item.find_element(By.XPATH, ".//span[normalize-space()='报名截止时间：']/following-sibling::span").text
                                except Exception:
                                    tender_end_time = ''
                            data_dict = {
                                "contentId": content_id, 
                                "agent": agent, 
                                "area": area, 
                                "briefText": brief_text, 
                                "budget": budget,
                                "budget_label": None, 
                                "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S"), 
                                "createTime": create_time,
                                "hasAnnex": has_annex, 
                                "highlightedWords": None, 
                                "keywords": ' '.join(group_keywords), 
                                "noticeType": notice_type,
                                "tenderEndTime": tender_end_time, 
                                "tenderees": tenderees, 
                                "title": title_text, 
                                "url": url,
                            }
                            extracted_data.append(data_dict)
                        except Exception:
                            logging.warning("提取单条数据时出错，已跳过。", exc_info=True)
                            continue
                    logging.info(f"成功提取 {len(extracted_data)} 条数据。")
                    save_to_mongo(extracted_data)
                    # 翻页
                    try:
                        next_page_button = driver.find_element(By.XPATH, "//button[contains(@class, 'btn-next')]")
                        if next_page_button.is_enabled():
                            sleep_duration = random.uniform(1, 10)
                            logging.info(f"准备点击下一页...将在 {sleep_duration:.2f} 秒后继续。")
                            time.sleep(sleep_duration)
                            next_page_button.click()
                            page_number += 1
                            time.sleep(random.uniform(4, 6))
                        else:
                            logging.info(f"到达 <标讯-关键词组{group_idx+1}> 的最后一页，采集结束。")
                            break
                    except Exception:
                        logging.info("无法找到下一页按钮，采集结束。")
                        break
                # 组间等待
                time.sleep(random.uniform(3, 6))
            logging.info("所有关键词组采集完毕。")
            return  # 采集完关键词后不再采集无关键词筛选的标讯
        except Exception as e:
            logging.exception("采集标讯时出错")

    except TimeoutException:
        logging.exception("抓取订阅信息超时，可能页面结构已改变或网络问题。")
    except Exception as e:
        logging.exception(f"抓取订阅信息过程中出现未知错误")


def run_scraper_task():
    """
    执行一次完整的登录、抓取、保存数据任务
    """
    logging.info("初始化WebDriver...")
    
    # 使用 undetected-chromedriver 替代普通的 selenium webdriver
    options = uc.ChromeOptions()
    options.add_argument('--headless')  # 无头模式，不显示浏览器界面
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--start-maximized')
    
    # 添加反检测参数
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-images')
    options.add_argument('--disable-javascript-harmony-shipping')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-features=TranslateUI')
    options.add_argument('--disable-ipc-flooding-protection')
    
    # 设置用户代理
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # 设置性能参数
    prefs = {
        "profile.default_content_setting_values": {
            "notifications": 2,
            "geolocation": 2,
            "media_stream": 2,
        },
        "profile.managed_default_content_settings": {
            "images": 2,
        },
        "profile.default_content_settings": {
            "popups": 2,
        }
    }
    options.add_experimental_option("prefs", prefs)
    
    # 设置独立的user-data-dir
    user_data_dir = tempfile.mkdtemp(prefix="login_user_data_")
    options.add_argument(f'--user-data-dir={user_data_dir}')

    # 创建 undetected-chromedriver 实例 - 增强版本兼容性
    max_retries = 3
    driver = None
    
    for attempt in range(max_retries):
        try:
            logging.info(f"尝试创建Chrome驱动 (第 {attempt + 1} 次)...")
            
            # 使用 webdriver_manager 管理驱动
            driver_path = ChromeDriverManager().install()
            logging.info(f"webdriver-manager 已安装驱动: {driver_path}")
            
            driver = uc.Chrome(driver_executable_path=driver_path, options=options)
            
            logging.info("Chrome驱动创建成功！")
            break
            
        except Exception as e:
            logging.warning(f"第 {attempt + 1} 次创建驱动失败: {str(e)}")
            if attempt == max_retries - 1:
                logging.error("所有尝试都失败了，无法创建Chrome驱动")
                raise e
            time.sleep(2)  # 等待2秒后重试
    
    if driver is None:
        raise Exception("无法创建Chrome驱动")
    
    # 执行脚本来隐藏自动化标识
    try:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
        driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']})")
        driver.execute_script("Object.defineProperty(navigator, 'permissions', {get: () => {query: () => Promise.resolve({state: 'granted'})}})")
    except Exception as e:
        logging.warning(f"执行反检测脚本时出现警告: {str(e)}")
        # 继续执行，不中断程序
    
    # 隐藏 Chrome 自动化标识
    try:
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en'],
                });
                window.chrome = {
                    runtime: {},
                };
                Object.defineProperty(navigator, 'permissions', {
                    get: () => ({
                        query: () => Promise.resolve({state: 'granted'}),
                    }),
                });
            '''
        })
    except Exception as e:
        logging.warning(f"执行CDP命令时出现警告: {str(e)}")
        # 继续执行，不中断程序

    logging.info("浏览器已启动，窗口已最大化。5秒后将打开登录页面...")
    time.sleep(5)

    try:
        logging.info(f"正在打开登录页面: {LOGIN_URL}")
        driver.get(LOGIN_URL)

        wait = WebDriverWait(driver, 10)

        logging.info("等待'密码登录'标签出现...")
        password_login_tab = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='密码登录']"))
        )
        logging.info("切换到密码登录...")
        password_login_tab.click()
        time.sleep(random.uniform(1, 2)) 

        logging.info("定位账号输入框并输入账号...")
        username_input = wait.until(
            EC.presence_of_element_located((By.XPATH, '//form[contains(@class, "password-login-form")]//input[@placeholder="请输入用户名"]'))
        )
        username_input.send_keys(USERNAME)
        time.sleep(random.uniform(1, 3)) 

        logging.info("定位密码输入框并输入密码...")
        password_input = driver.find_element(By.XPATH, '//form[contains(@class, "password-login-form")]//input[@placeholder="请输入密码"]')
        password_input.send_keys(PASSWORD)
        time.sleep(random.uniform(1, 2)) 

        logging.info("点击登录按钮...")
        login_button = driver.find_element(By.XPATH, "//button[.//span[normalize-space()='登录']]")
        login_button.click()

        # 不再等待不确定的URL，而是等待登录后必然出现的"订阅信息"菜单，这更可靠
        logging.info("等待登录完成，并检查'订阅信息'菜单是否可见...")
        wait.until(EC.presence_of_element_located((By.XPATH, "//li[normalize-space()='订阅信息']")))
        logging.info("登录成功！'订阅信息'菜单已可见。")
        
        # 处理可能出现的风险弹窗
        dismiss_account_risk_popup(driver, wait)

        # 登录成功后，开始抓取数据
        scrape_subscription_data(driver, wait)

    except Exception as e:
        logging.exception("爬虫主任务执行过程中出现错误")
    finally:
        if 'driver' in locals() and driver:
            driver.quit()
            logging.info("Browser closed.")
        logging.info("Main task finished.")


if __name__ == '__main__':
    # Check for command-line arguments for manual testing
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'test':
        logging.info("Manual test run initiated by command.")
        run_scraper_task()
        logging.info("Manual test run finished.")
    else:
        # Schedule the main task
        schedule.every().day.at("16:00").do(run_scraper_task)
        logging.info("Scheduler started. Waiting for the scheduled time (16:00).")

        while True:
            try:
                schedule.run_pending()
                time.sleep(1)
            except KeyboardInterrupt:
                logging.info("Scheduler stopped by user.")
                break