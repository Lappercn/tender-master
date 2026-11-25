import time
import re
import logging
import random
import sys
import argparse
import os
from datetime import datetime, timedelta
from urllib.parse import urljoin

# 设置环境变量来禁用调试日志
os.environ['WDM_LOG_LEVEL'] = '0'
os.environ['WDM_PRINT_FIRST_LINE'] = 'False'
os.environ['WDM_LOCAL'] = '1'

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from pymongo import MongoClient
import schedule
import tempfile
from webdriver_manager.chrome import ChromeDriverManager

def check_existing_driver():
    """检查是否已经有可用的Chrome驱动"""
    try:
        # 尝试直接创建驱动，如果成功说明驱动已存在
        options = uc.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        
        # 禁用Chrome日志输出
        options.add_argument('--log-level=3')
        options.add_argument('--silent')
        options.add_argument('--disable-logging')
        
        # 设置临时目录
        user_data_dir = tempfile.mkdtemp(prefix="test_driver_")
        options.add_argument(f'--user-data-dir={user_data_dir}')
        
        # 尝试创建驱动
        driver_path = ChromeDriverManager().install()
        test_driver = uc.Chrome(driver_executable_path=driver_path, options=options, version_main=None)  # 自动适配Chrome版本
        test_driver.quit()
        
        # 清理临时目录
        import shutil
        shutil.rmtree(user_data_dir, ignore_errors=True)
        
        return True
    except Exception as e:
        logger.warning(f"检查现有驱动失败: {e}")
        return False

# 命令行参数解析
def parse_arguments():
    parser = argparse.ArgumentParser(description='CFCPN招标信息采集脚本')
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
            logging.FileHandler("logs/cfcpn_spider.log", mode='a', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # 完全禁用第三方库的调试日志
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    logging.getLogger('selenium').setLevel(logging.ERROR)
    logging.getLogger('undetected_chromedriver').setLevel(logging.ERROR)
    logging.getLogger('requests').setLevel(logging.ERROR)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)
    logging.getLogger('urllib3.util.retry').setLevel(logging.ERROR)
    
    # 禁用所有HTTP相关的调试日志
    for logger_name in ['urllib3', 'requests', 'selenium', 'undetected_chromedriver']:
        logger = logging.getLogger(logger_name)
        logger.disabled = True
    
    return logging.getLogger(__name__)

# MongoDB 配置
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB = "qianlima"
MONGO_COLLECTION = "tender_data"

BASE_URL = "http://www.cfcpn.com"
START_URL = "http://www.cfcpn.com/jcw/sys/index/goUrl?url=modules/sys/login/list&column=cggg"

def simulate_human_behavior(driver):
    """模拟人类行为，增加随机性"""
    # 随机滚动页面
    scroll_height = driver.execute_script("return document.body.scrollHeight")
    if scroll_height > 1000:
        scroll_times = random.randint(2, 5)  # 增加滚动次数
        for i in range(scroll_times):
            scroll_amount = random.randint(200, 800)  # 增加滚动距离
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            # 模拟阅读时间
            read_time = random.uniform(1, 3)
            time.sleep(read_time)
    
    # 随机移动鼠标（如果不在headless模式）
    if not driver.execute_script("return navigator.webdriver"):
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(driver)
            # 随机移动鼠标
            x_offset = random.randint(-150, 150)
            y_offset = random.randint(-100, 100)
            actions.move_by_offset(x_offset, y_offset).perform()
            time.sleep(random.uniform(0.5, 1.5))
        except:
            pass
    
    # 模拟人工暂停
    pause_time = random.uniform(1, 3)
    time.sleep(pause_time)

def simulate_mouse_click(driver, element):
    """模拟鼠标点击元素"""
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        actions = ActionChains(driver)
        
        # 移动到元素
        actions.move_to_element(element)
        time.sleep(random.uniform(0.5, 1))
        
        # 点击元素
        actions.click(element)
        actions.perform()
        
        logger.info("模拟鼠标点击成功")
        return True
    except Exception as e:
        logger.warning(f"模拟鼠标点击失败: {e}")
        return False

def get_detail_url_by_click(driver, content_id, title):
    """通过点击获取详情页URL"""
    try:
        # 查找标题链接
        title_selectors = [
            f"a[onclick*='{content_id}']",
            f"a[title*='{title[:20]}']",
            "a.cfcpn-notice-title"
        ]
        
        title_element = None
        for selector in title_selectors:
            try:
                title_element = driver.find_element(By.CSS_SELECTOR, selector)
                break
            except NoSuchElementException:
                continue
        
        if not title_element:
            logger.warning("未找到标题链接元素")
            return None
        
        # 获取当前URL
        current_url = driver.current_url
        
        # 模拟点击
        if simulate_mouse_click(driver, title_element):
            # 等待页面跳转
            time.sleep(random.uniform(2, 4))
            
            # 获取新URL
            new_url = driver.current_url
            if new_url != current_url:
                logger.info(f"通过点击获取到详情页URL: {new_url}")
                return new_url
            else:
                logger.warning("点击后URL未发生变化")
                return None
        else:
            return None
            
    except Exception as e:
        logger.error(f"通过点击获取详情页URL失败: {e}")
        return None

def get_driver(headless=True, max_retries=3):
    """获取Chrome驱动，带重试机制"""
    for attempt in range(max_retries):
        try:
            options = uc.ChromeOptions()
            if headless:
                options.add_argument('--headless')  # 无头模式
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--window-size=1200,900')
            
            # 禁用Chrome日志输出
            options.add_argument('--log-level=3')  # 只显示致命错误
            options.add_argument('--silent')
            options.add_argument('--disable-logging')
            options.add_argument('--disable-dev-shm-usage')
            
            # 添加更多反检测参数
            options.add_argument('--disable-blink-features=AutomationControlled')
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
            user_data_dir = tempfile.mkdtemp(prefix="cfcpn_user_data_")
            options.add_argument(f'--user-data-dir={user_data_dir}')
            
            # 创建 undetected-chromedriver 实例 - 自动适配Chrome版本
            driver_path = ChromeDriverManager().install()
            driver = uc.Chrome(driver_executable_path=driver_path, options=options, version_main=None)  # 自动适配Chrome版本
            
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
            
            logger.info(f"Chrome驱动初始化成功 (尝试 {attempt + 1}/{max_retries})")
            return driver
            
        except Exception as e:
            logger.warning(f"Chrome驱动初始化失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info("等待5秒后重试...")
                time.sleep(5)
            else:
                logger.error("Chrome驱动初始化失败，已达到最大重试次数")
                logger.info("提示：如果网络连接有问题，请尝试：")
                logger.info("1. 开启VPN后重试")
                logger.info("2. 或者先运行其他爬虫脚本（如tobacco_spider.py）来下载驱动")
                raise

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
    
    # 等待列表加载 - 根据实际HTML结构调整选择器
    list_selectors = [
        "div#noticeUl div.cfcpn-list-main",
        "div.cfcpn-list-main",
        "div#noticeUl",
        "h5.cfcpn-list-title"
    ]
    
    items = []
    for selector in list_selectors:
        try:
            # 等待元素出现
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            # 根据实际HTML结构，列表项在noticeUl容器内
            if "noticeUl" in selector:
                items = driver.find_elements(By.CSS_SELECTOR, "div#noticeUl div.cfcpn-list-main")
            else:
                items = driver.find_elements(By.CSS_SELECTOR, "div.cfcpn-list-main")
            
            if items:
                logger.info(f"找到列表元素，使用选择器: {selector}，共找到 {len(items)} 个项目")
                break
        except TimeoutException:
            logger.warning(f"选择器 {selector} 未找到元素")
            continue
    
    if not items:
        logger.warning("未找到任何列表元素，尝试获取页面源码进行分析")
        page_source = driver.page_source
        logger.debug(f"页面源码片段: {page_source[:1000]}...")
        return []
    
    results = []
    
    for item in items:
        try:
            # 获取标题和链接 - 根据实际HTML结构
            title_selectors = [
                "h5.cfcpn-list-title a.cfcpn-notice-title",
                "h5.cfcpn-list-title a",
                "a.cfcpn-notice-title"
            ]
            
            title_element = None
            for selector in title_selectors:
                try:
                    title_element = item.find_element(By.CSS_SELECTOR, selector)
                    break
                except NoSuchElementException:
                    continue
            
            if not title_element:
                logger.warning("未找到标题元素")
                continue
                
            title = title_element.get_attribute("title") or title_element.text
            onclick = title_element.get_attribute("onclick")
            
            # 从onclick中提取ID - 根据实际格式 noticeDetail('bb5d5b63df844edd90387abeb8940a75','undefined')
            content_id_match = re.search(r"noticeDetail\('([^']+)'", onclick) if onclick else None
            content_id = content_id_match.group(1) if content_id_match else None
            
            # 如果无法提取到content_id，跳过这个项目
            if not content_id:
                logger.warning(f"无法提取content_id，跳过项目: {title}")
                continue
            
            # 获取发布时间 - 根据实际HTML结构
            date_selectors = [
                "h6.cfcpn-list-date",
                "h6.text-muted"
            ]
            
            pub_date = ""
            for selector in date_selectors:
                try:
                    date_element = item.find_element(By.CSS_SELECTOR, selector)
                    pub_date = date_element.text.strip()
                    break
                except NoSuchElementException:
                    continue
            
            # 日期判断
            try:
                pub_date_dt = datetime.strptime(pub_date, "%Y-%m-%d %H:%M:%S")
                if pub_date_dt.date() < week_ago:
                    logger.info(f"跳过一周前的公告: {title} {pub_date}")
                    continue
            except Exception:
                pass
            
            # 获取其他信息 - 根据实际HTML结构
            content_divs = item.find_elements(By.CSS_SELECTOR, "div.cfcpn-list-content div")
            info_dict = {}
            for div in content_divs:
                text = div.text.strip()
                if "：" in text:
                    key, value = text.split("：", 1)
                    info_dict[key] = value
                    logger.debug(f"提取信息: {key} = {value}")
            
            # 记录提取到的信息
            logger.info(f"提取到项目信息: 采购人={info_dict.get('采购人', 'N/A')}, 采购方式={info_dict.get('采购方式', 'N/A')}, 地区={info_dict.get('地区', 'N/A')}")
            
            # 获取标签值，用于设置tenderees
            tags_value = info_dict.get("标签", "")
            
            results.append({
                "contentId": content_id,
                "title": title,
                "createTime": pub_date,
                "purchaser": info_dict.get("采购人", ""),
                "purchaseMethod": info_dict.get("采购方式", ""),
                "area": info_dict.get("地区", ""),
                "tags": tags_value,
                "category": info_dict.get("品类", ""),
                "onclick": onclick,
                # 添加与tobacco_spider.py兼容的字段
                "agent": "",
                "briefText": "",
                "budget": "",
                "budget_label": None,
                "detail": "",
                "hasAnnex": False,
                "highlightedWords": None,
                "keywords": "",
                "noticeType": "招标公告",
                "tenderEndTime": "",
                "tenderees": tags_value,  # 使用tags的值
                "url": ""
            })
            
        except Exception as e:
            logger.warning(f"列表页解析失败: {e}")
    
    return results

def construct_detail_url(content_id):
    """构造详情页URL"""
    detail_url = f"{BASE_URL}/jcw/sys/index/goUrl?url=modules/sys/login/detail&column=undefined&searchVal={content_id}"
    return detail_url

def parse_detail_page(driver, content_id, title):
    """构造详情页URL"""
    # 构造详情页URL
    detail_url = construct_detail_url(content_id)
    
    data = {
        "contentId": content_id,
        "title": title,
        "detail_url": detail_url,  # 保存构造的URL
        "url": detail_url,  # 兼容字段
        "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # 确保所有字段都存在，与tobacco_spider.py兼容
        "agent": "",
        "briefText": "",
        "budget": "",
        "budget_label": None,
        "detail": "",
        "hasAnnex": False,
        "highlightedWords": None,
        "keywords": "",
        "noticeType": "招标公告",
        "tenderEndTime": "",
        "tenderees": "",  # 这个会在数据合并时被覆盖
        "purchaser": "",
        "purchaseMethod": "",
        "area": "",
        "tags": "",  # 这个会在数据合并时被覆盖
        "category": ""
    }
    
    return data
    


def get_current_max_page(driver):
    """获取当前显示的最大页码"""
    try:
        # 查找所有页码
        page_elements = driver.find_elements(By.CSS_SELECTOR, "li.page-number")
        if page_elements:
            # 获取最后一个页码
            page_numbers = []
            for elem in page_elements:
                try:
                    if elem.text.isdigit():
                        page_numbers.append(int(elem.text))
                except Exception:
                    continue
            
            if page_numbers:
                return max(page_numbers)
        return 1
    except Exception as e:
        logger.warning(f"获取当前最大页码失败: {e}")
        return 1

def can_go_next_page(driver):
    """检查是否可以点击下一页"""
    try:
        next_btn = driver.find_elements(By.CSS_SELECTOR, "li#img_next")
        if next_btn:
            # 检查按钮是否被禁用
            btn_class = next_btn[0].get_attribute("class")
            if "disabled" not in btn_class:
                return True
        return False
    except Exception as e:
        logger.warning(f"检查下一页按钮失败: {e}")
        return False

def click_next_page(driver):
    """点击下一页"""
    try:
        next_btn = driver.find_element(By.CSS_SELECTOR, "li#img_next a")
        next_btn.click()
        
        # 等待页面加载
        time.sleep(random.uniform(2, 4))
        simulate_human_behavior(driver)
        
        logger.info("成功点击下一页")
        return True
    except Exception as e:
        logger.error(f"点击下一页失败: {e}")
        return False

def navigate_to_page(driver, page_num):
    """导航到指定页面"""
    if page_num == 1:
        return
    
    try:
        # 查找页码输入框 - 尝试多种选择器
        input_selectors = [
            "input.cfcpn-page",
            "input.form-control",
            "input[type='text']"
        ]
        
        page_input = None
        for selector in input_selectors:
            try:
                page_input = driver.find_element(By.CSS_SELECTOR, selector)
                break
            except NoSuchElementException:
                continue
        
        if not page_input:
            logger.error(f"未找到页码输入框")
            return
        
        # 查找跳转按钮 - 尝试多种选择器
        button_selectors = [
            "a.bg-warning",
            "a.page-link.bg-warning",
            "a[href='javascript:void(0);']"
        ]
        
        jump_btn = None
        for selector in button_selectors:
            try:
                jump_btn = driver.find_element(By.CSS_SELECTOR, selector)
                if "跳转" in jump_btn.text:
                    break
            except NoSuchElementException:
                continue
        
        if not jump_btn:
            logger.error(f"未找到跳转按钮")
            return
        
        # 执行页面跳转
        page_input.clear()
        page_input.send_keys(str(page_num))
        jump_btn.click()
        
        # 等待页面加载
        time.sleep(random.uniform(2, 4))
        simulate_human_behavior(driver)
        
        logger.info(f"成功导航到第{page_num}页")
        
    except Exception as e:
        logger.error(f"导航到第{page_num}页失败: {e}")

def main(max_pages=None, headless=True):
    logger.info("==== 启动CFCPN招标信息采集脚本 ====")
    
    # 检查是否已经有可用的驱动
    if not check_existing_driver():
        logger.warning("未检测到可用的Chrome驱动，可能需要网络下载")
        logger.info("建议：如果网络连接有问题，请先运行其他爬虫脚本（如tobacco_spider.py）来下载驱动")
    
    driver = get_driver(headless=headless)
    
    try:
        driver.get(START_URL)
        
        # 模拟人工等待首页加载，增加随机性
        initial_load_time = random.uniform(2, 4)
        time.sleep(initial_load_time)
        
        # 模拟人类行为
        simulate_human_behavior(driver)
        
        # 等待分页元素加载
        pagination_selectors = [
            "ul.pagination",
            "div#pager1",
            "div#paging-container",
            "ul.cfcpn-list-page"
        ]
        
        pagination_found = False
        for selector in pagination_selectors:
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                pagination_found = True
                logger.info(f"找到分页元素，使用选择器: {selector}")
                break
            except TimeoutException:
                continue
        
        if not pagination_found:
            logger.warning("未找到分页元素")
        
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        
        # 动态分页循环
        current_page = 1
        max_pages_reached = False
        
        while not max_pages_reached:
            logger.info(f"采集第 {current_page} 页...")
            
            # 如果不是第一页，需要导航到指定页面
            if current_page > 1:
                navigate_to_page(driver, current_page)
            
            items = parse_list_page(driver, week_ago)
            logger.info(f"本页有效公告数: {len(items)}")
            
            # 如果没有数据，可能到达了最后一页
            if not items:
                logger.info("本页没有数据，可能到达了最后一页")
                break
            
            for item in items:
                logger.info(f"处理项目: {item['title']}")
                try:
                    # 模拟人工处理时间
                    pre_detail_delay = random.uniform(0.5, 1)
                    logger.info(f"模拟人工处理 {pre_detail_delay:.1f} 秒...")
                    time.sleep(pre_detail_delay)
                    
                    # 构造详情页URL
                    detail = parse_detail_page(driver, item['contentId'], item['title'])
                    
                    # 合并列表页和详情页数据
                    for k, v in item.items():
                        if k not in detail or not detail.get(k):
                            detail[k] = v
                    
                    # 确保URL字段正确设置
                    if detail.get('detail_url'):
                        detail['url'] = detail['detail_url']
                    
                    save_to_mongo(detail)
                    logger.info(f"已保存: {detail['contentId']} {detail['title']} - URL: {detail.get('url', 'N/A')}")
                    
                    # 模拟人工处理时间
                    interval_time = random.uniform(0.5, 1)
                    logger.info(f"模拟人工处理 {interval_time:.1f} 秒...")
                    time.sleep(interval_time)
                    
                except Exception as e:
                    logger.error(f"处理项目失败: {e}")
            
            # 检查是否达到最大页数限制
            if max_pages and current_page >= max_pages:
                logger.info(f"达到最大页数限制 {max_pages}，停止采集")
                break
            
            # 检查是否可以继续到下一页
            current_max_page = get_current_max_page(driver)
            logger.info(f"当前显示的最大页码: {current_max_page}")
            
            if current_page >= current_max_page:
                # 到达当前显示的最后一页，尝试点击下一页
                if can_go_next_page(driver):
                    logger.info("到达当前显示的最后一页，点击下一页继续...")
                    if click_next_page(driver):
                        current_page += 1
                        continue
                    else:
                        logger.info("点击下一页失败，停止采集")
                        break
                else:
                    logger.info("没有下一页按钮或按钮已禁用，停止采集")
                    break
            else:
                # 还没到当前显示的最后一页，继续到下一页
                current_page += 1
            
            # 页面间添加随机延迟，模拟翻页时间
            page_interval = random.uniform(3, 6)
            logger.info(f"页面间休息 {page_interval:.1f} 秒...")
            time.sleep(page_interval)
                
    except Exception as e:
        logger.error(f"采集过程中发生错误: {e}")
    finally:
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