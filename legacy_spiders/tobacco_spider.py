import time
import re
import logging
import random
import sys
import argparse
from datetime import datetime, timedelta
from urllib.parse import urljoin

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from pymongo import MongoClient
import schedule
import tempfile
from webdriver_manager.chrome import ChromeDriverManager

# 命令行参数解析
def parse_arguments():
    parser = argparse.ArgumentParser(description='中国烟草行业招标采集脚本')
    parser.add_argument('mode', nargs='?', default='run', choices=['run', 'schedule', 'test'], 
                       help='运行模式: run(直接运行), schedule(定时任务), test(测试模式)')
    parser.add_argument('--headless', action='store_true', help='无头模式运行')
    parser.add_argument('--pages', type=int, default=None, help='测试模式下采集的页数')
    parser.add_argument('--time', default='16:00', help='定时任务执行时间 (默认16:00)')
    return parser.parse_args()

# 日志配置
def setup_logging(debug_mode=False):
    level = logging.DEBUG if debug_mode else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("logs/tobacco_spider.log", mode='a', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

# MongoDB 配置
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB = "qianlima"
MONGO_COLLECTION = "tender_data"

BASE_URL = "https://cgjy.tobacco.com.cn"
START_URL = BASE_URL + "/zbNotice/index.jhtml"

def simulate_human_behavior(driver):
    """模拟人类行为，增加随机性"""
    # 随机滚动页面
    scroll_height = driver.execute_script("return document.body.scrollHeight")
    if scroll_height > 1000:
        scroll_times = random.randint(1, 3)
        for _ in range(scroll_times):
            scroll_amount = random.randint(100, 500)
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(0.5, 1.5))
    
    # 随机移动鼠标（如果不在headless模式）
    if not driver.execute_script("return navigator.webdriver"):
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(driver)
            # 随机移动鼠标
            x_offset = random.randint(-100, 100)
            y_offset = random.randint(-50, 50)
            actions.move_by_offset(x_offset, y_offset).perform()
        except:
            pass

def get_driver(headless=True):
    options = uc.ChromeOptions()
    if headless:
        options.add_argument('--headless')  # 无头模式
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1200,900')
    
    # 添加更多反检测参数
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-images')  # 禁用图片加载，提高速度
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
            "notifications": 2,  # 禁用通知
            "geolocation": 2,    # 禁用地理位置
            "media_stream": 2,    # 禁用媒体流
        },
        "profile.managed_default_content_settings": {
            "images": 2,  # 禁用图片
        },
        "profile.default_content_settings": {
            "popups": 2,  # 禁用弹窗
        }
    }
    options.add_experimental_option("prefs", prefs)
    
    # 设置独立的user-data-dir
    user_data_dir = tempfile.mkdtemp(prefix="tobacco_user_data_")
    options.add_argument(f'--user-data-dir={user_data_dir}')
    
    # 创建 undetected-chromedriver 实例
    driver_path = ChromeDriverManager().install()
    driver = uc.Chrome(driver_executable_path=driver_path, options=options)
    
    # 等待浏览器完全启动
    time.sleep(2)
    
    try:
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
    except Exception as e:
        print(f"警告: 执行反检测脚本时出错: {e}")
        # 继续执行，不中断程序
    
    return driver

def save_to_mongo(data):
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    col = db[MONGO_COLLECTION]
    if data.get("contentId"):
        col.update_one({"contentId": data["contentId"]}, {"$set": data}, upsert=True)
        logger.info(f"更新: {data['contentId']} {data.get('title','')}")
    else:
        col.insert_one(data)
        logger.info(f"新增: {data.get('title','')}")
    client.close()

def parse_list_page(driver, week_ago):
    # 添加人类行为模拟
    simulate_human_behavior(driver)
    
    items = driver.find_elements(By.CSS_SELECTOR, "ul.searchList > li")
    results = []
    for li in items:
        try:
            a_tag = li.find_element(By.CSS_SELECTOR, "a[target='_blank']")
            rel_url = a_tag.get_attribute("href")
            url = urljoin(BASE_URL, rel_url)
            m = re.search(r'/([\d]+)\.jhtml', url)
            contentId = int(m.group(1)) if m else None
            title = a_tag.find_element(By.CSS_SELECTOR, "span.span_hover").get_attribute("title")
            try:
                noticeType = a_tag.find_element(By.CSS_SELECTOR, "em").text
            except Exception:
                noticeType = ""
            try:
                pub_date = li.find_element(By.CSS_SELECTOR, "i.release_date").text
                pub_date = pub_date.replace("发布日期:", "").strip()
            except Exception:
                pub_date = ""
            # 日期判断
            try:
                pub_date_dt = datetime.strptime(pub_date, "%Y-%m-%d")
                if pub_date_dt < week_ago:
                    logger.info(f"跳过一周前的公告: {title} {pub_date}")
                    continue
            except Exception:
                pass
            results.append({
                "li": li,  # 返回li元素
                "contentId": contentId,
                "title": title,
                "url": url,
                "noticeType": noticeType,
                "createTime": pub_date
            })
        except Exception as e:
            logger.warning(f"列表页解析失败: {e}")
    return results

def parse_detail_page(driver, url):
    driver.get(url)
    
    # 模拟人工等待页面加载，增加随机性
    load_time = random.uniform(1, 3)
    time.sleep(load_time)
    
    # 模拟人类行为
    simulate_human_behavior(driver)
    
    data = {}
    try:
        data["title"] = driver.find_element(By.CSS_SELECTOR, "div.app > h2").text
    except Exception:
        data["title"] = ""
    try:
        pub_time = driver.find_element(By.CSS_SELECTOR, "div.app > div > span").text
        pub_time = pub_time.replace("发布时间：", "").strip()
        data["createTime"] = pub_time
    except Exception:
        data["createTime"] = ""
    data["noticeType"] = "公告"
    try:
        area = driver.find_element(By.XPATH, "//p[contains(text(),'招标项目所在地区')]/em").text
        data["area"] = area
    except Exception:
        data["area"] = ""
    try:
        content = driver.find_element(By.CSS_SELECTOR, "div#content").text
        data["briefText"] = content[:300]
        data["detail"] = content  # 保存全文
    except Exception:
        data["briefText"] = ""
        data["detail"] = ""
    try:
        budget = driver.find_element(By.XPATH, "//h5[contains(text(),'项目概况')]/following-sibling::p[1]/em").text
        data["budget"] = budget
    except Exception:
        try:
            content = driver.find_element(By.CSS_SELECTOR, "div#content").text
            m = re.search(r"预算[：: ]*([\d\.]+[万千元]*)", content)
            data["budget"] = m.group(1) if m else ""
        except Exception:
            data["budget"] = ""
    try:
        tenderEndTime = driver.find_element(By.XPATH, "//p[contains(text(),'递交截止时间')]/em").text
        data["tenderEndTime"] = tenderEndTime
    except Exception:
        data["tenderEndTime"] = ""
    try:
        tenderees = driver.find_element(By.XPATH, "//p[contains(text(),'招标人')]/em").text
        data["tenderees"] = tenderees
    except Exception:
        data["tenderees"] = ""
    try:
        agent = driver.find_element(By.XPATH, "//p[contains(text(),'招标代理机构')]/em").text
        data["agent"] = agent
    except Exception:
        data["agent"] = ""
    try:
        hasAnnex = bool(driver.find_elements(By.XPATH, "//a[contains(text(),'附件') or contains(text(),'下载')]"))
        data["hasAnnex"] = hasAnnex
    except Exception:
        data["hasAnnex"] = False
    data["budget_label"] = None
    data["highlightedWords"] = None
    data["keywords"] = ""
    data["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["url"] = url
    m = re.search(r'/([\d]+)\.jhtml', url)
    data["contentId"] = int(m.group(1)) if m else None
    
    # 模拟人工阅读公告详情的时间（增加随机性）
    read_time = random.uniform(1, 2)  # 1-2秒阅读时间
    time.sleep(read_time)
    
    return data

def main(max_pages=None, headless=True):
    logger.info("==== 启动中国烟草行业招标采集脚本 ====")
    driver = get_driver(headless=headless)
    driver.get(START_URL)
    
    # 模拟人工等待首页加载，增加随机性
    initial_load_time = random.uniform(1, 3)
    time.sleep(initial_load_time)
    
    # 模拟人类行为
    simulate_human_behavior(driver)
    
    try:
        select = driver.find_element(By.CSS_SELECTOR, "div.pagination_div select")
        options = select.find_elements(By.TAG_NAME, "option")
        total_pages = int(options[-1].get_attribute("value"))
    except Exception:
        total_pages = 1
    logger.info(f"总页数: {total_pages}")
    
    # 如果设置了最大页数限制，使用较小的值
    if max_pages and max_pages < total_pages:
        total_pages = max_pages
        logger.info(f"测试模式：限制采集页数为 {max_pages}")
    
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    
    # 主循环部分
    for page in range(1, total_pages + 1):
        logger.info(f"采集第 {page} 页...")
        if page > 1:
            next_url = f"{BASE_URL}/zbNotice/index_{page}.jhtml" if page > 1 else START_URL
            driver.get(next_url)
            
            # 模拟人工等待翻页加载，增加随机性
            page_load_time = random.uniform(1, 3)
            time.sleep(page_load_time)
            
            # 模拟人类行为
            simulate_human_behavior(driver)
            
        items = parse_list_page(driver, week_ago)
        logger.info(f"本页有效公告数: {len(items)}")
        
        for item in items:
            logger.info(f"采集详情: {item['title']}")
            try:
                # 在访问详情页前添加随机延迟
                pre_detail_delay = random.uniform(0.5, 1.5)
                time.sleep(pre_detail_delay)
                
                # 直接用 driver.get 进入详情页
                driver.get(item['url'])
                
                # 等待详情页加载
                detail_load_time = random.uniform(1, 3)
                time.sleep(detail_load_time)
                
                # 采集详情页
                detail = parse_detail_page(driver, item['url'])
                for k in item:
                    if k != "li" and not detail.get(k):
                        detail[k] = item[k]
                save_to_mongo(detail)
                logger.info(f"已保存: {detail['contentId']} {detail['title']}")
                
                # 模拟人工阅读，增加随机性
                interval_time = random.uniform(1, 2)
                time.sleep(interval_time)
                
            except Exception as e:
                logger.error(f"采集详情失败: {e}")
                
        # 页面间添加随机延迟
        if page < total_pages:
            page_interval = random.uniform(2, 4)
            time.sleep(page_interval)
            
    driver.quit()
    logger.info("==== 全部采集完成 ====")

def job():
    """定时任务执行函数"""
    try:
        logger.info("==== 开始执行定时采集任务 ====")
        main(headless=True)
        logger.info("==== 定时采集任务完成 ====")
    except Exception as e:
        logger.error(f"定时任务执行失败: {e}")

if __name__ == "__main__":
    args = parse_arguments()
    logger = setup_logging(args.mode == 'test')
    
    if args.mode == 'run':
        logger.info("==== 直接运行模式 ====")
        main(headless=not args.headless)
    elif args.mode == 'test':
        logger.info("==== 测试模式 ====")
        main(max_pages=args.pages, headless=not args.headless)
    elif args.mode == 'schedule':
        logger.info(f"==== 定时任务模式，每天 {args.time} 执行 ====")
        schedule.every().day.at(args.time).do(job)
        while True:
            schedule.run_pending()
            time.sleep(1)
 