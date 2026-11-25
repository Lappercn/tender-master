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
import tempfile
import os
try:
    import winreg  # Windows 注册表用于定位 Chrome 路径
except Exception:
    winreg = None

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


# 说明：在Windows环境下定位Chrome可执行文件路径，返回字符串路径；找不到则返回None。
def get_chrome_binary_path() -> str | None:
    """
    功能说明：自动定位 Windows 下 Chrome 的可执行程序路径。
    核心功能：优先检查常见安装目录，其次读取注册表 App Paths。
    依赖模块：os、winreg
    """
    # 常见安装位置
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\\Google\\Chrome\\Application\\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\\Google\\Chrome\\Application\\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\\Google\\Chrome SxS\\Application\\chrome.exe"),  # Canary
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p

    # 通过注册表 App Paths 查找
    if winreg is not None:
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe") as key:
                    val, _ = winreg.QueryValueEx(key, None)
                    if val and os.path.isfile(val):
                        return val
            except Exception:
                pass

    # 未找到
    return None


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
        subscription_menu = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//li[normalize-space()='订阅信息']"))
        )
        subscription_menu.click()
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

def scrape_biaoxun_no_filters(driver, wait, force_year=None):
    """
    采集“标讯”数据，不做关键词筛选和日期过滤。
    """
    try:
        logging.info("准备点击'标讯'菜单...")

        def _find_clickable(locators):
            for by, locator in locators:
                try:
                    el = wait.until(EC.element_to_be_clickable((by, locator)))
                    if el:
                        return el
                except Exception:
                    continue
            return None

        # 兼容多种页面结构的'标讯'入口定位
        bx_menu = _find_clickable([
            (By.XPATH, "//ul[contains(@class,'el-menu')]//li[normalize-space()='标讯']"),
            (By.XPATH, "//li[contains(normalize-space(.),'标讯') and not(.//li)]"),
            (By.XPATH, "//span[normalize-space()='标讯']/ancestor::li"),
            (By.XPATH, "//a[contains(normalize-space(.),'标讯')]"),
        ])

        if bx_menu:
            time.sleep(2)
            bx_menu.click()
            logging.info("已点击'标讯'，等待页面加载...")
            time.sleep(3)
        else:
            logging.warning("未找到'标讯'菜单，尝试直接打开标讯页面作为回退...")
            try:
                driver.get("https://vip.qianlima.com/search/")
            except Exception:
                logging.warning("直达标讯页面失败，继续尝试采集流程。")

        # 应用“信息类型”筛选：仅勾选“公告”和“招标公告”，不主动取消“不限”
        def apply_info_type_filters():
            logging.info("应用'信息类型'筛选：公告 + 招标公告（不取消'不限'）")
            try:
                wait.until(EC.presence_of_element_located((By.ID, "search-content-main-part")))
            except Exception:
                logging.info("主区域未及时加载，继续尝试筛选。")

            # 可选：点击“查看更多筛选”以确保筛选项可见
            try:
                see_more_btn = driver.find_element(By.XPATH, "//p[contains(@class,'seeMore') and contains(.,'查看更多筛选')]")
                if see_more_btn.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", see_more_btn)
                    see_more_btn.click()
                    time.sleep(random.uniform(0.5, 1.5))
            except Exception:
                pass

            def _locate_label(paths):
                for by, locator in paths:
                    try:
                        el = wait.until(EC.element_to_be_clickable((by, locator)))
                        if el:
                            return el
                    except Exception:
                        continue
                return None

            def _ensure_checked(label_el, name=''):
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", label_el)
                    # 检查选中态
                    try:
                        cls = label_el.find_element(By.CSS_SELECTOR, "span.el-checkbox__input").get_attribute("class") or ""
                    except Exception:
                        cls = ""
                    if "is-checked" not in cls:
                        try:
                            label_el.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", label_el)
                        time.sleep(random.uniform(0.5, 1.2))
                        logging.info(f"已勾选{name}。")
                    else:
                        logging.info(f"{name}已处于选中状态。")
                except Exception:
                    logging.warning(f"勾选{name}失败。", exc_info=True)

            # 勾选“公告”
            gonggao = _locate_label([
                (By.XPATH, "//div[contains(@class,'TypeTenderFilter')]//span[contains(@class,'labelaname') and normalize-space()='公告']/ancestor::label"),
                (By.XPATH, "//label[.//span[contains(@class,'labelaname') and normalize-space()='公告']]")
            ])
            if gonggao:
                _ensure_checked(gonggao, "'公告'")
            else:
                logging.warning("未找到'公告'勾选项。")

            # 勾选“招标公告”
            zhaobiao = _locate_label([
                (By.XPATH, "//div[contains(@class,'TypeTenderFilter')]//label[.//span[contains(@class,'el-checkbox__label') and normalize-space()='招标公告']]"),
                (By.XPATH, "//label[.//span[contains(@class,'el-checkbox__label') and normalize-space()='招标公告']]")
            ])
            if zhaobiao:
                _ensure_checked(zhaobiao, "'招标公告'")
            else:
                logging.warning("未找到'招标公告'勾选项。")

        # 应用“项目金额”筛选：选择“200万以上”
        def apply_amount_filter():
            logging.info("应用'项目金额'筛选：200万以上")
            try:
                # 在筛选金额前，先点击“查看更多筛选”按钮（如果存在）
                try:
                    see_more_btn = driver.find_element(By.XPATH, "//p[contains(@class,'seeMore') and contains(.,'查看更多筛选')]")
                    if see_more_btn.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", see_more_btn)
                        see_more_btn.click()
                        logging.info("已点击查看更多筛选，等待折叠栏展开...")
                        time.sleep(random.uniform(1, 2))
                except Exception:
                    pass

                # 点开“项目金额”
                amount_filter_btn = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//p[@class='cell-title' and contains(text(),'项目金额')]"))
                )
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", amount_filter_btn)
                try:
                    amount_filter_btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", amount_filter_btn)
                time.sleep(random.uniform(1, 2))

                # 选择“200万以上”
                bx_amount = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//p[contains(@class,'list-item-text') and contains(text(),'200万以上')]"))
                )
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", bx_amount)
                try:
                    bx_amount.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", bx_amount)
                logging.info("已选择'200万以上'")
                time.sleep(random.uniform(2, 4))
            except Exception:
                logging.warning("应用'项目金额'筛选失败，继续后续流程。", exc_info=True)

        # 清空关键词输入框（用于年份切换前后）
        def clear_search_input(tag="通用清空"):
            try:
                logging.info(f"清空关键词输入框（{tag}）")
                search_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='请输入产品、项目名称、编号或其他关键词，多个词用空格隔开']")))
                try:
                    search_input.send_keys(Keys.CONTROL, 'a')
                    search_input.send_keys(Keys.DELETE)
                    time.sleep(0.4)
                except Exception:
                    pass
                try:
                    search_input.clear()
                except Exception:
                    pass
                time.sleep(random.uniform(0.6, 1.2))
            except Exception:
                logging.warning("清空关键词输入框失败。", exc_info=True)

        # 翻页采集（带关键词字段）
        def collect_pages_keyworded(pass_name="标讯-关键词", keywords_joined="", max_items=None):
            page_number = 1
            collected = 0
            while True:
                logging.info(f"--- <{pass_name}> 开始处理第 {page_number} 页 ---")
                try:
                    wait.until(EC.presence_of_element_located((By.ID, "search-content-main-part")))
                except Exception:
                    logging.info("主区域未及时加载，继续尝试翻页采集。")
                time.sleep(random.uniform(1, 2))

                # 人性化滚动
                current_scroll_position, new_height = 0, 1
                speed = random.uniform(200, 400)
                while current_scroll_position <= new_height:
                    current_scroll_position += speed
                    driver.execute_script("window.scrollTo(0, {});".format(current_scroll_position))
                    new_height = driver.execute_script("return document.body.scrollHeight;")
                    time.sleep(random.uniform(0.1, 0.3))
                logging.info("页面滚动到底部。")

                items = driver.find_elements(By.CSS_SELECTOR, "div.list-single")
                if not items and page_number == 1:
                    logging.warning("标讯列表未找到数据，结束采集。")
                    break

                extracted_data = []
                for item in items:
                    try:
                        # 标题与链接
                        try:
                            title_element = item.find_element(By.CSS_SELECTOR, "a.content-tit")
                            title_text = title_element.text
                            url = title_element.get_attribute('href')
                            content_id = int(title_element.get_attribute('data-cid')) if title_element.get_attribute('data-cid') else None
                        except Exception:
                            title_text = ''
                            url = ''
                            content_id = None

                        # 发布时间
                        try:
                            create_time = item.find_element(By.CSS_SELECTOR, "div.content-time span").text.strip()
                        except Exception:
                            try:
                                create_time = item.find_element(By.CSS_SELECTOR, "div.content-time").text.strip()
                            except Exception:
                                create_time = ''

                        # 所属地区
                        try:
                            area = item.find_element(By.XPATH, ".//div[@class='con-address' and not(contains(@class, 'con-type')) and not(contains(@class, 'con-file'))]").text
                        except Exception:
                            area = ''

                        # 信息类型
                        try:
                            notice_type = item.find_element(By.XPATH, ".//div[contains(@class, 'con-address') and contains(@class, 'con-type')]/span").text
                        except Exception:
                            notice_type = ''

                        # 附件标识
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

                        # 招标预算
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
                            "keywords": keywords_joined,
                            "noticeType": notice_type,
                            "tenderEndTime": tender_end_time,
                            "tenderees": tenderees,
                            "title": title_text,
                            "url": url,
                        }
                        extracted_data.append(data_dict)
                        # 若设置了采集上限，在单页采集过程中提前停止追加
                        if max_items is not None and (collected + len(extracted_data)) >= max_items:
                            logging.info("已达到采集上限，提前结束当前页的数据提取。")
                            break
                    except Exception:
                        logging.warning("提取单条数据时出错，已跳过。", exc_info=True)
                        continue

                # 处理采集上限与保存
                if max_items is not None:
                    remaining = max_items - collected
                    if remaining <= 0:
                        logging.info(f"达到采集上限 {max_items} 条，结束 <{pass_name}> 采集。")
                        return True
                    page_to_save = extracted_data[:max(0, remaining)]
                else:
                    page_to_save = extracted_data

                logging.info(f"成功提取 {len(page_to_save)} 条数据。")
                save_to_mongo(page_to_save)
                collected += len(page_to_save)

                if max_items is not None and collected >= max_items:
                    logging.info(f"达到采集上限 {max_items} 条，结束 <{pass_name}> 采集。")
                    return True

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
                        logging.info(f"到达 <{pass_name}> 的最后一页，采集结束。")
                        break
                except Exception:
                    logging.info("无法找到下一页按钮，采集结束。")
                    break

        # 批量输入关键词并搜索（每组5-6个）
        def run_keyword_groups(context_label="标讯-关键词", group_size=6):
            keywords = get_keywords_from_mongo()
            if not keywords:
                logging.info("关键词列表为空，跳过关键词搜索采集。")
                return
            total_groups = (len(keywords) + group_size - 1) // group_size
            for group_idx in range(total_groups):
                group_keywords = keywords[group_idx*group_size:(group_idx+1)*group_size]
                if not group_keywords:
                    continue
                logging.info(f"正在输入第{group_idx+1}/{total_groups}组关键词: {group_keywords}")
                # 定位输入框
                try:
                    search_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='请输入产品、项目名称、编号或其他关键词，多个词用空格隔开']")))
                except Exception:
                    logging.warning("未找到关键词输入框，跳过本组。")
                    continue

                # 强制清空输入框（Ctrl+A+Delete，防止累加）
                try:
                    search_input.send_keys(Keys.CONTROL, 'a')
                    search_input.send_keys(Keys.DELETE)
                    time.sleep(0.5)
                except Exception:
                    pass
                try:
                    search_input.clear()
                except Exception:
                    pass
                time.sleep(random.uniform(1, 2))
                # 输入关键词（空格分隔）
                keywords_joined = ' '.join(group_keywords)
                try:
                    search_input.send_keys(keywords_joined)
                except Exception:
                    logging.warning("输入关键词失败，跳过本组。")
                    continue
                time.sleep(random.uniform(1, 2))
                # 点击搜索按钮
                try:
                    search_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'search-button')]//i[contains(@class,'icon-search')]")))
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", search_btn)
                    try:
                        search_btn.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", search_btn)
                except Exception:
                    logging.warning("未找到搜索按钮或点击失败，跳过本组。")
                    continue
                logging.info("已点击搜索，等待结果加载...")
                time.sleep(random.uniform(3, 5))

                # 翻页采集（带关键词字段，默认不设上限）
                collect_pages_keyworded(f"{context_label}-关键词组{group_idx+1}", keywords_joined)
                # 组间随机等待
                time.sleep(random.uniform(3, 6))

                # 采集完成后，清空输入框，避免下一组关键词叠加
                try:
                    search_input_post = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='请输入产品、项目名称、编号或其他关键词，多个词用空格隔开']")))
                    try:
                        search_input_post.send_keys(Keys.CONTROL, 'a')
                        search_input_post.send_keys(Keys.DELETE)
                        time.sleep(0.4)
                    except Exception:
                        pass
                    try:
                        search_input_post.clear()
                    except Exception:
                        pass
                    logging.info("已清空关键词输入框，准备下一组关键词。")
                    time.sleep(random.uniform(1, 2))
                except Exception:
                    logging.warning("采集后清空关键词输入框失败，但下一组仍将尝试覆盖输入。", exc_info=True)

        def collect_pages(pass_name="标讯-无筛选", max_items=None):
            page_number = 1
            collected = 0
            while True:
                logging.info(f"--- <{pass_name}> 开始处理第 {page_number} 页 ---")
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

                items = driver.find_elements(By.CSS_SELECTOR, "div.list-single")
                if not items and page_number == 1:
                    logging.warning("标讯列表未找到数据，结束采集。")
                    break

                extracted_data = []
                for item in items:
                    try:
                        # 标题与链接
                        try:
                            title_element = item.find_element(By.CSS_SELECTOR, "a.content-tit")
                            title_text = title_element.text
                            url = title_element.get_attribute('href')
                            content_id = int(title_element.get_attribute('data-cid')) if title_element.get_attribute('data-cid') else None
                        except Exception:
                            title_text = ''
                            url = ''
                            content_id = None

                        # 发布时间
                        try:
                            create_time = item.find_element(By.CSS_SELECTOR, "div.content-time span").text.strip()
                        except Exception:
                            try:
                                create_time = item.find_element(By.CSS_SELECTOR, "div.content-time").text.strip()
                            except Exception:
                                create_time = ''

                        # 所属地区
                        try:
                            area = item.find_element(By.XPATH, ".//div[@class='con-address' and not(contains(@class, 'con-type')) and not(contains(@class, 'con-file'))]").text
                        except Exception:
                            area = ''

                        # 信息类型
                        try:
                            notice_type = item.find_element(By.XPATH, ".//div[contains(@class, 'con-address') and contains(@class, 'con-type')]/span").text
                        except Exception:
                            notice_type = ''

                        # 附件标识
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

                        # 招标预算
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
                            "keywords": '',
                            "noticeType": notice_type,
                            "tenderEndTime": tender_end_time,
                            "tenderees": tenderees,
                            "title": title_text,
                            "url": url,
                        }
                        extracted_data.append(data_dict)
                        # 若设置了采集上限，在单页采集过程中提前停止追加
                        if max_items is not None and (collected + len(extracted_data)) >= max_items:
                            logging.info("已达到采集上限，提前结束当前页的数据提取。")
                            break
                    except Exception:
                        logging.warning("提取单条数据时出错，已跳过。", exc_info=True)
                        continue

                # 处理采集上限与保存
                if max_items is not None:
                    remaining = max_items - collected
                    if remaining <= 0:
                        logging.info(f"达到采集上限 {max_items} 条，结束 <{pass_name}> 采集。")
                        return True
                    page_to_save = extracted_data[:max(0, remaining)]
                else:
                    page_to_save = extracted_data

                logging.info(f"成功提取 {len(page_to_save)} 条数据。")
                save_to_mongo(page_to_save)
                collected += len(page_to_save)
                
                if max_items is not None and collected >= max_items:
                    logging.info(f"达到采集上限 {max_items} 条，结束 <{pass_name}> 采集。")
                    return True

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
                        logging.info(f"到达 <{pass_name}> 的最后一页，采集结束。")
                        break
                except Exception:
                    logging.info("无法找到下一页按钮，采集结束。")
                    break

        # 先决定是否需要选择“近一年”
        use_near_year = False
        fy_int = None
        if force_year is None:
            # 未指定年份：按原逻辑先采集近一年
            use_near_year = True
        else:
            try:
                fy_int = int(str(force_year).strip())
            except Exception:
                logging.warning(f"指定年份格式异常: {force_year}，按'近一年'处理。")
                use_near_year = True
            else:
                if fy_int >= datetime.now().year:
                    logging.info(f"指定年份为当年或未来({fy_int})，切换为'近一年'采集。")
                    use_near_year = True

        if use_near_year:
            try:
                near_year = _find_clickable([
                    (By.XPATH, "//p[normalize-space()='近一年']/ancestor::label"),
                    (By.XPATH, "//label[.//p[@data-extendinfo='近一年']]"),
                    (By.XPATH, "//label[.//p[contains(normalize-space(),'近一年')]]"),
                ])
                if near_year:
                    logging.info("选择日期筛选：近一年")
                    near_year.click()
                    time.sleep(random.uniform(1, 3))
                else:
                    logging.warning("未找到'近一年'筛选标签，继续不筛选采集。")
            except Exception:
                logging.warning("选择'近一年'筛选失败，继续不筛选采集。", exc_info=True)

            # 应用信息类型筛选（不取消'不限'）
            apply_info_type_filters()
            # 应用项目金额筛选（200万以上）
            apply_amount_filter()
            # 切换到近一年后先清空一次
            clear_search_input(tag="近一年前")
            # 近一年：按关键词分组采集
            logging.info("开始按关键词分组采集'近一年'数据。")
            run_keyword_groups(context_label="标讯-近一年", group_size=6)
            # 结束近一年采集后再清一次
            clear_search_input(tag="近一年后")

            # 若指定年份为当年或未来，近一年采集完成后直接结束该函数（不处理往年）
            if force_year is not None and (fy_int is None or fy_int >= datetime.now().year):
                return

        # 选择“往年”，逐年采集或采集指定年份
        try:
            dropdown = _find_clickable([
                (By.XPATH, "//div[contains(@class,'dropdown-options')]//span[contains(@class,'dropdown-name-text') and normalize-space()='往年']"),
                (By.XPATH, "//span[normalize-space()='往年']/ancestor::span[contains(@class,'dropdown-name')]")
            ])
            if dropdown:
                logging.info("打开'往年'下拉菜单...")
                # 点击并显式等待弹层渲染，必要时重试
                def _get_visible_year_items():
                    candidates = driver.find_elements(By.XPATH,
                        "//ul[contains(@class,'el-dropdown-menu')]//li | //div[contains(@class,'el-select-dropdown__list')]//li | //div[contains(@class,'el-scrollbar__view')]//li")
                    visible = []
                    for li in candidates:
                        try:
                            if li.is_displayed():
                                txt = li.text.strip()
                                if txt:
                                    visible.append(li)
                        except Exception:
                            continue
                    return visible

                visible_year_items = []
                for attempt in range(3):
                    try:
                        dropdown.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", dropdown)
                    time.sleep(1.0)  # 先点击，等待约1秒让弹层出现
                    visible_year_items = _get_visible_year_items()
                    if visible_year_items:
                        break
                    else:
                        logging.info("未检测到年份选项，重试展开'往年'下拉...")

                # 收集可选年份文本（基于可见项）
                year_texts = [it.text.strip() for it in visible_year_items if it.text and it.text.strip()]
                # 过滤出可能的年份格式
                year_texts = [t for t in year_texts if any(ch.isdigit() for ch in t)]
                if not year_texts:
                    logging.warning("'往年'下拉中未检测到年份选项，跳过往年采集。")
                else:
                    logging.info(f"检测到往年年份选项: {year_texts}")
                    if force_year:
                        # 仅采集指定年份
                        target_str = str(force_year)
                        logging.info(f"启动指定年份采集：{target_str}")
                        # 先在可见项中匹配（支持'2024'或'2024年'等）
                        year_option = None
                        for li in visible_year_items:
                            try:
                                txt = li.text.strip()
                                if target_str in txt:
                                    year_option = li
                                    break
                            except Exception:
                                continue
                        # 若未匹配到，再尝试可点击定位
                        if not year_option:
                            year_option = _find_clickable([
                                (By.XPATH, f"//ul[contains(@class,'el-dropdown-menu')]//li[normalize-space()='{target_str}']"),
                                (By.XPATH, f"//div[contains(@class,'el-select-dropdown__list')]//li[normalize-space()='{target_str}']"),
                                (By.XPATH, f"//div[contains(@class,'el-scrollbar__view')]//li[normalize-space()='{target_str}']"),
                                (By.XPATH, f"//ul[contains(@class,'el-dropdown-menu')]//li[contains(normalize-space(),'{target_str}')]"),
                                (By.XPATH, f"//div[contains(@class,'el-select-dropdown__list')]//li[contains(normalize-space(),'{target_str}')]"),
                                (By.XPATH, f"//div[contains(@class,'el-scrollbar__view')]//li[contains(normalize-space(),'{target_str}')]"),
                            ])
                        if year_option:
                            logging.info(f"选择年份: {target_str}")
                            try:
                                year_option.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", year_option)
                            time.sleep(random.uniform(2, 4))
                            # 切换年份后应用信息类型与金额筛选，并按关键词采集
                            apply_info_type_filters()
                            apply_amount_filter()
                            # 年份切换前清空
                            clear_search_input(tag=f"往年前-{target_str}")
                            run_keyword_groups(context_label=f"标讯-往年-{target_str}", group_size=6)
                            # 年份采集结束后清空
                            clear_search_input(tag=f"往年后-{target_str}")
                        else:
                            logging.warning(f"未找到指定年份选项: {target_str}，不执行往年采集。")
                    else:
                        # 逐年倒序采集（从最近年份到较早年份）
                        # 将年份文本按其中的年份数字排序（降序）
                        def _extract_year_num(text):
                            try:
                                import re
                                m = re.search(r"(19\d{2}|20\d{2})", text)
                                return int(m.group(1)) if m else -1
                            except Exception:
                                return -1
                        sorted_year_texts = sorted(year_texts, key=lambda t: _extract_year_num(t), reverse=True)
                        for y in sorted_year_texts:
                            try:
                                # 每次选择年份前重新打开下拉并等待1秒
                                dropdown = _find_clickable([
                                    (By.XPATH, "//div[contains(@class,'dropdown-options')]//span[contains(@class,'dropdown-name-text') and normalize-space()='往年']"),
                                    (By.XPATH, "//span[normalize-space()='往年']/ancestor::span[contains(@class,'dropdown-name')]")
                                ])
                                if not dropdown:
                                    logging.warning("未能重新打开'往年'下拉，结束往年采集循环。")
                                    break
                                try:
                                    dropdown.click()
                                except Exception:
                                    driver.execute_script("arguments[0].click();", dropdown)
                                time.sleep(1.0)

                                # 点击具体年份项
                                # 先在可见项中精确匹配
                                visible_year_items = _get_visible_year_items()
                                year_option = None
                                for li in visible_year_items:
                                    try:
                                        if li.text.strip() == y:
                                            year_option = li
                                            break
                                    except Exception:
                                        continue
                                # 若未匹配到，再尝试可点击定位
                                if not year_option:
                                    year_option = _find_clickable([
                                        (By.XPATH, f"//ul[contains(@class,'el-dropdown_menu')]//li[normalize-space()='{y}']"),
                                        (By.XPATH, f"//div[contains(@class,'el-select-dropdown__list')]//li[normalize-space()='{y}']"),
                                        (By.XPATH, f"//div[contains(@class,'el-scrollbar__view')]//li[normalize-space()='{y}']"),
                                    ])
                                if year_option:
                                    logging.info(f"选择年份: {y}")
                                    try:
                                        year_option.click()
                                    except Exception:
                                        driver.execute_script("arguments[0].click();", year_option)
                                    time.sleep(random.uniform(2, 4))
                                    # 切换年份后应用信息类型与金额筛选，并按关键词采集
                                    apply_info_type_filters()
                                    apply_amount_filter()
                                    # 年份切换前清空
                                    clear_search_input(tag=f"往年前-{y}")
                                    run_keyword_groups(context_label=f"标讯-往年-{y}", group_size=6)
                                    # 年份采集结束后清空
                                    clear_search_input(tag=f"往年后-{y}")
                                else:
                                    logging.warning(f"未找到具体年份选项: {y}")
                            except Exception:
                                logging.warning(f"选择年份 {y} 时发生错误，继续下一个。", exc_info=True)
            else:
                logging.warning("未找到'往年'下拉入口，跳过往年采集。")
        except Exception:
            logging.warning("处理'往年'下拉筛选时失败，跳过往年采集。", exc_info=True)
    except Exception:
        logging.exception("采集标讯（无筛选）时出错")


def dismiss_account_risk_popup(driver, wait, max_wait=6):
    """
    检测并关闭“账号风险提醒”弹窗：点击“取消”按钮。
    如果弹窗未出现则直接跳过。
    """
    try:
        # 登录后可能需要短暂时间让弹窗渲染
        time.sleep(1)
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

        # 点击“取消”按钮（失败则降级为JS点击）
        try:
            cancel_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", cancel_btn)

        logging.info("检测到账号风险提醒弹窗，已点击‘取消’。")

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

def run_scraper_task(force_year=None):
    """
    执行一次完整的登录、抓取、保存数据任务
    """
    logging.info("初始化WebDriver...")
    
    # 使用 undetected-chromedriver 替代普通的 selenium webdriver
    options = uc.ChromeOptions()
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

    # 创建 undetected-chromedriver 实例 - 自动适配Chrome版本
    chrome_path = get_chrome_binary_path()
    if chrome_path:
        logging.info(f"定位到Chrome路径: {chrome_path}")
        # 显式传入字符串路径，避免 TypeError: Binary Location Must be a String
        try:
            options.binary_location = chrome_path
        except TypeError:
            # 某些 selenium 版本严格校验类型；我们确保传入字符串
            options.binary_location = str(chrome_path)
        driver = uc.Chrome(options=options, version_main=None, browser_executable_path=str(chrome_path))
    else:
        driver = uc.Chrome(options=options, version_main=None)
    
    # 执行脚本来隐藏自动化标识
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
    driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']})")
    driver.execute_script("Object.defineProperty(navigator, 'permissions', {get: () => {query: () => Promise.resolve({state: 'granted'})}})")
    
    # 隐藏 Chrome 自动化标识
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
        logging.info("等待登录完成，验证已离开登录页...")
        try:
            wait.until(lambda d: 'login' not in d.current_url)
            logging.info(f"登录成功，当前页面: {driver.current_url}")
        except TimeoutException:
            logging.warning("登录后页面未及时跳转，继续尝试采集标讯。")

        # 弹窗处理：账号风险提醒（若出现）
        dismiss_account_risk_popup(driver, wait)
        # 登录后直接进行“标讯”采集（函数内部会自行定位菜单并处理回退）
        scrape_biaoxun_no_filters(driver, wait, force_year=force_year)

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
    elif len(sys.argv) > 1 and sys.argv[1].lower() == 'test_wangnian':
        logging.info("'往年'点击测试启动。")
        # 轻量化的“往年”点击测试，不做数据采集
        try:
            logging.info("初始化WebDriver用于'往年'点击测试...")
            options = uc.ChromeOptions()
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
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
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

            chrome_path = get_chrome_binary_path()
            if chrome_path:
                logging.info(f"定位到Chrome路径: {chrome_path}")
                try:
                    options.binary_location = chrome_path
                except TypeError:
                    options.binary_location = str(chrome_path)
                driver = uc.Chrome(options=options, browser_executable_path=str(chrome_path))
            else:
                driver = uc.Chrome(options=options)
            driver.maximize_window()

            # 注入防检测脚本，保持与主任务一致
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": '''
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    window.navigator.chrome = { runtime: {} };
                    Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(Notification, 'permission', {get: () => 'denied'});
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ? Promise.resolve({ state: Notification.permission }) : originalQuery(parameters)
                    );
                '''
            })

            logging.info("5秒后将打开登录页面进行测试...")
            time.sleep(5)

            logging.info(f"正在打开登录页面: {LOGIN_URL}")
            driver.get(LOGIN_URL)
            wait = WebDriverWait(driver, 10)

            logging.info("等待'密码登录'标签并点击...")
            password_login_tab = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='密码登录']"))
            )
            password_login_tab.click()
            time.sleep(random.uniform(1, 2))

            logging.info("输入账号与密码...")
            username_input = wait.until(
                EC.presence_of_element_located((By.XPATH, '//form[contains(@class, "password-login-form")]//input[@placeholder="请输入用户名"]'))
            )
            username_input.send_keys(USERNAME)
            password_input = driver.find_element(By.XPATH, '//form[contains(@class, "password-login-form")]//input[@placeholder="请输入密码"]')
            password_input.send_keys(PASSWORD)
            time.sleep(random.uniform(1, 2))

            logging.info("点击登录按钮...")
            login_button = driver.find_element(By.XPATH, "//button[.//span[normalize-space()='登录']]")
            login_button.click()

            logging.info("等待离开登录页...")
            try:
                wait.until(lambda d: 'login' not in d.current_url)
                logging.info(f"登录成功，当前页面: {driver.current_url}")
            except TimeoutException:
                logging.warning("登录后页面未及时跳转，继续尝试进入标讯页面。")

            # 弹窗处理：账号风险提醒（若出现）
            dismiss_account_risk_popup(driver, wait)

            # 小工具：尝试按多种方式找到可点击元素
            def _find_clickable(locators):
                for by, locator in locators:
                    try:
                        el = wait.until(EC.element_to_be_clickable((by, locator)))
                        if el:
                            return el
                    except Exception:
                        continue
                return None

            # 进入“标讯”或回退直达
            logging.info("尝试进入'标讯'页面...")
            bx_menu = _find_clickable([
                (By.XPATH, "//ul[contains(@class,'el-menu')]//li[normalize-space()='标讯']"),
                (By.XPATH, "//li[contains(normalize-space(.),'标讯') and not(.//li)]"),
                (By.XPATH, "//span[normalize-space()='标讯']/ancestor::li"),
                (By.XPATH, "//a[contains(normalize-space(.),'标讯')]")
            ])

            if bx_menu:
                time.sleep(2)
                bx_menu.click()
                logging.info("已点击'标讯'，等待页面加载...")
                time.sleep(3)
            else:
                logging.warning("未找到'标讯'菜单，尝试直接打开标讯页面作为回退...")
                driver.get("https://vip.qianlima.com/search/")
                time.sleep(3)

            # 等待搜索主区域加载
            wait.until(EC.presence_of_element_located((By.ID, "search-content-main-part")))
            logging.info("标讯页面已加载，准备点击'往年'...")

            # 点击“往年”下拉入口
            wangnian_entry = _find_clickable([
                (By.XPATH, "//span[contains(@class,'dropdown-name-text') and normalize-space()='往年']"),
                (By.XPATH, "//p[normalize-space()='往年']/ancestor::label"),
                (By.XPATH, "//p[@data-extendinfo='往年']/ancestor::label"),
            ])
            if not wangnian_entry:
                logging.error("未定位到'往年'筛选入口，测试失败。")
            else:
                wangnian_entry.click()
                logging.info("已点击'往年'下拉入口，查找年份选项...")
                time.sleep(random.uniform(1, 2))

                # 搜索可能的年份选项容器，并点击第一个可用年份
                candidate_items = driver.find_elements(By.XPATH, 
                    "//ul[contains(@class,'el-dropdown-menu')]//li|//div[contains(@class,'el-select-dropdown__list')]//li|//div[contains(@class,'el-scrollbar__view')]//li"
                )
                if not candidate_items:
                    logging.error("未发现年份选项列表，测试失败。")
                else:
                    # 过滤出有可见文本的项
                    visible_years = []
                    for li in candidate_items:
                        try:
                            txt = li.text.strip()
                            if txt:
                                visible_years.append(li)
                        except Exception:
                            continue
                    if not visible_years:
                        logging.error("年份列表存在但无可见文本，测试失败。")
                    else:
                        target = visible_years[0]
                        logging.info(f"准备点击年份: {target.text.strip()}")
                        try:
                            target.click()
                            logging.info("年份点击成功！'往年'点击测试通过。")
                        except Exception:
                            logging.exception("点击年份项时发生错误。")

            # 结束测试
            driver.quit()
            logging.info("'往年'点击测试结束，浏览器已关闭。")
        except Exception:
            logging.exception("'往年'点击测试过程中出现错误。")
    elif len(sys.argv) > 1 and sys.argv[1].lower() == 'test_zhaobiao':
        logging.info("'招标公告'点击测试启动（不取消'不限'）。")
        try:
            # 初始化与防检测设置
            options = uc.ChromeOptions()
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
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
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

            chrome_path = get_chrome_binary_path()
            if chrome_path:
                logging.info(f"定位到Chrome路径: {chrome_path}")
                try:
                    options.binary_location = chrome_path
                except TypeError:
                    options.binary_location = str(chrome_path)
                driver = uc.Chrome(options=options, browser_executable_path=str(chrome_path))
            else:
                driver = uc.Chrome(options=options)
            driver.maximize_window()
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": '''
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    window.navigator.chrome = { runtime: {} };
                    Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(Notification, 'permission', {get: () => 'denied'});
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ? Promise.resolve({ state: Notification.permission }) : originalQuery(parameters)
                    );
                '''
            })

            time.sleep(2)
            logging.info(f"正在打开登录页面: {LOGIN_URL}")
            driver.get(LOGIN_URL)
            wait = WebDriverWait(driver, 10)

            # 登录流程
            password_login_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='密码登录']")))
            password_login_tab.click()
            time.sleep(random.uniform(0.6, 1.2))
            username_input = wait.until(EC.presence_of_element_located((By.XPATH, '//form[contains(@class, "password-login-form")]//input[@placeholder="请输入用户名"]')))
            username_input.send_keys(USERNAME)
            password_input = driver.find_element(By.XPATH, '//form[contains(@class, "password-login-form")]//input[@placeholder="请输入密码"]')
            password_input.send_keys(PASSWORD)
            time.sleep(random.uniform(0.5, 1.0))
            login_button = driver.find_element(By.XPATH, "//button[.//span[normalize-space()='登录']]")
            login_button.click()
            try:
                wait.until(lambda d: 'login' not in d.current_url)
                logging.info("登录成功，进入标讯页面...")
            except TimeoutException:
                logging.warning("登录后页面未及时跳转，尝试直达标讯页面。")

            # 弹窗处理：账号风险提醒（若出现）
            dismiss_account_risk_popup(driver, wait)

            # 工具函数
            def _find_clickable(locators):
                for by, locator in locators:
                    try:
                        el = wait.until(EC.element_to_be_clickable((by, locator)))
                        if el:
                            return el
                    except Exception:
                        continue
                return None

            def _ensure_checked(label_el, name=''):
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", label_el)
                    try:
                        cls = label_el.find_element(By.CSS_SELECTOR, "span.el-checkbox__input").get_attribute("class") or ""
                    except Exception:
                        cls = ""
                    if "is-checked" not in cls:
                        try:
                            label_el.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", label_el)
                        time.sleep(random.uniform(0.5, 1.2))
                        logging.info(f"已勾选{name}。")
                    else:
                        logging.info(f"{name}已处于选中状态。")
                except Exception:
                    logging.warning(f"勾选{name}失败。", exc_info=True)

            # 直接进入标讯搜索页，避免菜单等待阻塞
            driver.get("https://vip.qianlima.com/search/")
            time.sleep(2)

            # 等待主区域
            wait.until(EC.presence_of_element_located((By.ID, "search-content-main-part")))
            logging.info("标讯页面加载完成，测试点击'招标公告'...")

            # 只点击“招标公告”，不操作“不限”和“公告”
            zhaobiao_label = _find_clickable([
                (By.XPATH, "//div[contains(@class,'TypeTenderFilter')]//label[.//span[contains(@class,'el-checkbox__label') and normalize-space()='招标公告']]"),
                (By.XPATH, "//label[.//span[contains(@class,'el-checkbox__label') and normalize-space()='招标公告']]")
            ])
            if not zhaobiao_label:
                logging.error("未定位到'招标公告'复选框，测试失败。")
            else:
                _ensure_checked(zhaobiao_label, "'招标公告'")
                logging.info("'招标公告'点击测试通过。")

            driver.quit()
            logging.info("'招标公告'点击测试结束，浏览器已关闭。")
        except Exception:
            logging.exception("'招标公告'点击测试过程中出现错误。")
    elif len(sys.argv) > 1 and sys.argv[1].startswith('-') and sys.argv[1][1:].isdigit() and len(sys.argv[1][1:]) == 4:
        # 支持命令：python claw.py -2024
        year = int(sys.argv[1][1:])
        logging.info(f"按指定年份采集启动：{year}")
        run_scraper_task(force_year=year)
    elif len(sys.argv) > 2 and sys.argv[1].lower() in ('--year', '-y') and sys.argv[2].isdigit():
        # 兼容命令：python claw.py --year 2024 或 -y 2024
        year = int(sys.argv[2])
        logging.info(f"按指定年份采集启动：{year}")
        run_scraper_task(force_year=year)
    elif len(sys.argv) > 1 and sys.argv[1].lower().startswith('--year='):
        # 兼容命令：python claw.py --year=2024
        val = sys.argv[1].split('=', 1)[1]
        if val.isdigit():
            year = int(val)
            logging.info(f"按指定年份采集启动：{year}")
            run_scraper_task(force_year=year)
        else:
            logging.warning("--year 参数格式无效，应为 --year=YYYY 或 --year YYYY")
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
