import logging
import random
import sys
import time
from datetime import datetime, timedelta
import tempfile
import pymongo
import json
import re
from urllib.parse import urljoin, urlparse
from bson import ObjectId

import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, InvalidSessionIdException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys


def json_serialize(obj):
    """自定义JSON序列化函数，处理ObjectId等特殊类型"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, '__dict__'):
        return obj.__dict__
    else:
        return str(obj)


def safe_json_dumps(data, **kwargs):
    """安全的JSON序列化，处理ObjectId等特殊类型"""
    try:
        return json.dumps(data, default=json_serialize, **kwargs)
    except Exception as e:
        logging.warning(f"JSON序列化失败: {e}")
        # 创建一个清理后的数据副本
        clean_data = {}
        for key, value in data.items():
            try:
                if isinstance(value, ObjectId):
                    clean_data[key] = str(value)
                elif isinstance(value, datetime):
                    clean_data[key] = value.isoformat()
                else:
                    clean_data[key] = value
            except:
                clean_data[key] = str(value)
        return json.dumps(clean_data, **kwargs)

# --- 日志配置 ---
# 创建一个日志记录器，同时输出到文件和控制台
# 确保日志目录存在
import os
log_dir = "中标数据爬取/logs"
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("中标数据爬取/logs/tender_winner.log", mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# --- 配置 ---
# 在这里填入您的账号和密码（或通过环境变量 QIANLIMA_USERNAME / QIANLIMA_PASSWORD 传入）
USERNAME = os.getenv("QIANLIMA_USERNAME", "YOUR_USERNAME")  # 请替换为您的账号/手机号
PASSWORD = os.getenv("QIANLIMA_PASSWORD", "YOUR_PASSWORD")  # 请替换为您的密码
LOGIN_URL = "https://vip.qianlima.com/login/"
SEARCH_URL = "https://search.vip.qianlima.com/index.html"

# MongoDB配置
MONGO_HOST = "localhost"
MONGO_PORT = 27017
DATABASE_NAME = "hawkeye"
INDUSTRY_COLLECTION = "industry_companies"  # 企业名单集合
TENDER_COLLECTION = "Winner_Notice"  # 中标公告集合



def setup_driver():
    """
    设置并返回配置好的WebDriver实例
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
    user_data_dir = tempfile.mkdtemp(prefix="new_spider_user_data_")
    options.add_argument(f'--user-data-dir={user_data_dir}')

    # 创建 undetected-chromedriver 实例
    driver = uc.Chrome(options=options, version_main=138)
    
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
    
    return driver


def perform_login_steps(driver):
    """
    执行具体的登录步骤（输入账号密码并点击登录）
    """
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
    
    # 清空输入框
    username_input.clear()
    time.sleep(0.5)
    
    # 模拟鼠标点击用户名输入框
    from selenium.webdriver.common.action_chains import ActionChains
    actions = ActionChains(driver)
    actions.move_to_element(username_input).click().perform()
    time.sleep(random.uniform(0.3, 0.8))
    
    # 模拟逐字符输入用户名
    for char in USERNAME:
        username_input.send_keys(char)
        time.sleep(random.uniform(0.08, 0.2))
    
    time.sleep(random.uniform(0.5, 1.2))

    logging.info("定位密码输入框并输入密码...")
    password_input = driver.find_element(By.XPATH, '//form[contains(@class, "password-login-form")]//input[@placeholder="请输入密码"]')
    
    # 清空密码输入框
    password_input.clear()
    time.sleep(0.5)
    
    # 模拟鼠标点击密码输入框
    actions.move_to_element(password_input).click().perform()
    time.sleep(random.uniform(0.3, 0.8))
    
    # 模拟逐字符输入密码
    for char in PASSWORD:
        password_input.send_keys(char)
        time.sleep(random.uniform(0.08, 0.2))
    
    time.sleep(random.uniform(0.5, 1.2))

    logging.info("点击登录按钮...")
    login_button = driver.find_element(By.XPATH, "//button[.//span[normalize-space()='登录']]")
    
    # 模拟鼠标悬停在登录按钮上
    actions.move_to_element(login_button).perform()
    time.sleep(random.uniform(0.3, 0.8))
    
    # 模拟用户思考时间
    think_time = random.uniform(0.5, 1.2)
    logging.info(f"模拟用户思考 {think_time:.1f} 秒...")
    time.sleep(think_time)
    
    # 点击登录
    login_button.click()
    
    # 等待登录处理
    time.sleep(random.uniform(3, 5))


def login(driver):
    """
    执行登录操作，包含重试机制
    """
    try:
        logging.info("正在打开登录页面")
        driver.get(LOGIN_URL)
        
        # 检测是否出现"您的账号已在其他设备登录"弹窗的重试机制
        max_retries = 3
        for retry in range(max_retries):
            logging.info(f"开始第 {retry + 1} 次登录尝试...")
            
            # 执行登录步骤
            perform_login_steps(driver)
            
            # 等待登录完成并检测可能的弹窗
            logging.info("等待登录完成...")
            
            try:
                # 检查是否有弹窗出现
                logout_dialog = driver.find_element(By.CSS_SELECTOR, ".layui-layer-dialog.logout-box-tip")
                if logout_dialog.is_displayed():
                    logging.warning(f"检测到账号在其他设备登录的提示弹窗，第 {retry + 1} 次重试")
                    
                    # 点击确定按钮
                    confirm_button = driver.find_element(By.CSS_SELECTOR, ".layui-layer-btn0")
                    confirm_button.click()
                    time.sleep(random.uniform(1, 2))
                    
                    if retry < max_retries - 1:  # 如果不是最后一次重试
                        logging.info("重新打开登录页面并重新输入账号密码...")
                        driver.get(LOGIN_URL)  # 重新打开登录页面
                        time.sleep(2)
                        continue  # 继续下一次循环
                    else:
                        logging.error("多次重试后仍然出现设备登录冲突，登录失败")
                        return False
                else:
                    # 没有弹窗，登录成功
                    break
            except NoSuchElementException:
                # 没有找到弹窗元素，说明登录正常
                break
            except Exception as e:
                logging.warning(f"检测弹窗时出现异常: {e}")
                break
        
        logging.info("登录完成！")
        
        # 登录成功后等待1-2秒
        wait_time = random.uniform(1, 2)
        logging.info(f"登录成功，等待 {wait_time:.1f} 秒后继续...")
        time.sleep(wait_time)
        
        return True

    except Exception as e:
        logging.exception("登录过程中出现错误")
        return False


def connect_to_mongo():
    """连接到MongoDB"""
    try:
        client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
        db = client[DATABASE_NAME]
        logging.info(f"成功连接到MongoDB数据库: {DATABASE_NAME}")
        return client, db
    except Exception as e:
        logging.error(f"连接MongoDB失败: {e}")
        return None, None


def get_company_list(db):
    """从MongoDB获取企业名单"""
    try:
        collection = db[INDUSTRY_COLLECTION]
        companies = list(collection.find({}, {"company_name": 1, "industry": 1, "_id": 0}))
        logging.info(f"成功获取企业名单，共 {len(companies)} 家企业")
        return companies
    except Exception as e:
        logging.error(f"获取企业名单失败: {e}")
        return []


def save_tender_notice(db, tender_data):
    """保存招标公告到数据库"""
    try:
        collection = db[TENDER_COLLECTION]
        # 检查是否已存在相同的contentId（支持id和contentId两个字段）
        content_id = tender_data.get("contentId") or tender_data.get("id")
        if content_id and (collection.find_one({"contentId": content_id}) or collection.find_one({"id": content_id})):
            logging.info(f"招标公告已存在: {tender_data.get('title', 'Unknown')}")
            return False
        
        # 添加爬取时间
        tender_data["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        result = collection.insert_one(tender_data)
        logging.info(f"成功保存招标公告: {tender_data.get('title', 'Unknown')}")
        return True
    except Exception as e:
        logging.error(f"保存招标公告失败: {e}")
        return False


def get_total_pages(driver):
    """动态检测总页数"""
    try:
        # 方法1: 从分页器中获取最后一页的页码
        page_links = driver.find_elements(By.CSS_SELECTOR, ".pagingUl li a")
        if page_links:
            # 获取所有页码链接中的最大数字
            max_page = 0
            for link in page_links:
                try:
                    page_num = int(link.text.strip())
                    max_page = max(max_page, page_num)
                except ValueError:
                    continue
            if max_page > 0:
                logging.info(f"从分页器检测到总页数: {max_page}")
                return max_page
        
        # 方法2: 检查是否有"尾页"按钮并点击获取总页数
        last_page_btn = driver.find_elements(By.CSS_SELECTOR, ".last:not(.disabled)")
        if last_page_btn:
            logging.info("尝试通过尾页按钮检测总页数...")
            current_url = driver.current_url
            last_page_btn[0].click()
            time.sleep(2)
            
            # 检测跳转后的页码
            try:
                active_page = driver.find_element(By.CSS_SELECTOR, ".activP-d")
                total_pages = int(active_page.text.strip())
                logging.info(f"通过尾页检测到总页数: {total_pages}")
                
                # 返回第一页
                first_page_btn = driver.find_element(By.CSS_SELECTOR, ".first:not(.disabled)")
                if first_page_btn:
                    first_page_btn.click()
                    time.sleep(2)
                
                return total_pages
            except Exception as e:
                logging.warning(f"尾页检测失败: {e}")
                # 尝试返回原页面
                driver.get(current_url)
                time.sleep(2)
        
        # 方法3: 默认返回较大的页数，让程序自然停止
        logging.warning("无法检测总页数，使用默认值50")
        return 50
        
    except Exception as e:
        logging.error(f"检测总页数时发生错误: {e}")
        return 10  # 保守估计

def navigate_to_page(driver, target_page):
    """导航到指定页面，支持多种翻页方式"""
    try:
        current_page = get_current_page(driver)
        if current_page == target_page:
            logging.info(f"已在第 {target_page} 页")
            return True
        
        logging.info(f"从第 {current_page} 页导航到第 {target_page} 页")
        
        # 方法1: 直接点击页码链接
        page_links = driver.find_elements(By.CSS_SELECTOR, f".pagingUl li a")
        for link in page_links:
            if link.text.strip() == str(target_page):
                logging.info(f"直接点击页码 {target_page}")
                link.click()
                time.sleep(random.uniform(2, 3))
                return verify_page_change(driver, target_page)
        
        # 方法2: 使用跳转输入框
        jump_input = driver.find_elements(By.CSS_SELECTOR, ".jump-input")
        jump_go = driver.find_elements(By.CSS_SELECTOR, ".jump-go")
        
        if jump_input and jump_go:
            logging.info(f"使用跳转输入框导航到第 {target_page} 页")
            jump_input[0].clear()
            jump_input[0].send_keys(str(target_page))
            time.sleep(random.uniform(0.5, 1))
            jump_go[0].click()
            time.sleep(random.uniform(2, 3))
            return verify_page_change(driver, target_page)
        
        # 方法3: 逐步翻页（下一页/上一页）
        if target_page > current_page:
            # 向后翻页
            for _ in range(target_page - current_page):
                next_btn = driver.find_elements(By.CSS_SELECTOR, ".next:not(.disabled)")
                if next_btn:
                    next_btn[0].click()
                    time.sleep(random.uniform(1.5, 2.5))
                else:
                    logging.warning("下一页按钮不可用")
                    return False
        else:
            # 向前翻页
            for _ in range(current_page - target_page):
                prev_btn = driver.find_elements(By.CSS_SELECTOR, ".prv:not(.disabled)")
                if prev_btn:
                    prev_btn[0].click()
                    time.sleep(random.uniform(1.5, 2.5))
                else:
                    logging.warning("上一页按钮不可用")
                    return False
        
        return verify_page_change(driver, target_page)
        
    except Exception as e:
        logging.error(f"导航到第 {target_page} 页失败: {e}")
        return False

def get_current_page(driver):
    """获取当前页码"""
    try:
        # 方法1: 从激活的页码获取
        active_page = driver.find_elements(By.CSS_SELECTOR, ".activP-d")
        if active_page:
            return int(active_page[0].text.strip())
        
        # 方法2: 从URL参数获取
        current_url = driver.current_url
        import re
        page_match = re.search(r'currentPage=(\d+)', current_url)
        if page_match:
            return int(page_match.group(1))
        
        # 默认返回1
        return 1
    except Exception as e:
        logging.warning(f"获取当前页码失败: {e}")
        return 1

def verify_page_change(driver, expected_page):
    """验证页面是否成功跳转"""
    try:
        # 等待页面加载
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".container-con li"))
        )
        time.sleep(2)
        
        current_page = get_current_page(driver)
        if current_page == expected_page:
            logging.info(f"✓ 成功跳转到第 {expected_page} 页")
            return True
        else:
            logging.warning(f"⚠ 页面跳转异常: 期望第 {expected_page} 页，实际第 {current_page} 页")
            return False
    except Exception as e:
        logging.error(f"验证页面跳转失败: {e}")
        return False

def has_next_page(driver):
    """检查是否还有下一页"""
    try:
        next_btn = driver.find_elements(By.CSS_SELECTOR, ".next:not(.disabled)")
        return len(next_btn) > 0
    except Exception as e:
        logging.warning(f"检查下一页状态失败: {e}")
        return False

def search_company_tenders(driver, company_name, industry, db):
    """搜索指定公司的中标信息，爬取一页立即保存一页"""
    try:
        logging.info(f"开始搜索企业: {company_name} (行业: {industry})")
        
        # 进入搜索页面
        driver.get(SEARCH_URL)
        wait = WebDriverWait(driver, 15)
        
        # 等待页面加载
        time.sleep(random.uniform(3, 5))
        
        # 首先模拟点击"中标信息"标签 - 确保在正确的标签页下进行搜索设置
        logging.info("首先模拟点击'中标信息'标签")
        try:
            # 等待中标信息标签元素可点击
            winning_info_tab = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".tabItem.tabItem2[data-id='2']"))
            )
            
            # 检查当前状态（仅用于日志记录）
            tab_classes = winning_info_tab.get_attribute("class")
            if "tabItemSelect" in tab_classes:
                logging.info("'中标信息'标签当前已选中，但仍执行模拟点击操作")
            else:
                logging.info("'中标信息'标签当前未选中，执行点击操作")
            
            # 模拟人工点击行为
            # 先滚动到元素位置
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", winning_info_tab)
            time.sleep(random.uniform(0.5, 1.0))
            
            # 使用ActionChains模拟更真实的点击
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(driver)
            actions.move_to_element(winning_info_tab).pause(random.uniform(0.3, 0.8)).click().perform()
            
            logging.info("已成功模拟点击'中标信息'标签")
            
            # 等待页面响应和内容加载
            time.sleep(random.uniform(2, 3))
            
        except Exception as e:
            logging.warning(f"主要方法点击'中标信息'标签失败: {e}")
            logging.info("尝试备用方法...")
            try:
                # 备用方法1：通过文本内容查找并点击
                winning_info_tab_alt = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//div[@class and contains(@class, 'tabItem') and .//p[text()='中标信息']]"))
                )
                actions = ActionChains(driver)
                actions.move_to_element(winning_info_tab_alt).pause(random.uniform(0.3, 0.8)).click().perform()
                time.sleep(random.uniform(2, 3))
                logging.info("备用方法成功点击'中标信息'标签")
                
            except Exception as e2:
                logging.warning(f"备用方法也失败: {e2}")
                logging.info("尝试直接JavaScript点击...")
                try:
                    # 备用方法2：JavaScript直接点击
                    js_click_element = driver.find_element(By.CSS_SELECTOR, ".tabItem.tabItem2[data-id='2']")
                    driver.execute_script("arguments[0].click();", js_click_element)
                    time.sleep(random.uniform(2, 3))
                    logging.info("JavaScript方法成功点击'中标信息'标签")
                except Exception as e3:
                    logging.error(f"所有点击方法都失败: {e3}")
                    logging.info("继续使用当前页面内容")
        
        # 使用"全文搜索"类型（默认设置）
        logging.info("使用'全文搜索'类型（默认设置）")
        
        # 添加筛选"中标通知"的逻辑
        logging.info("设置招标阶段筛选为'中标通知'")
        try:
            # 直接点击中标通知选项（使用data-name属性定位）
            winning_notice_option = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "li.pItem[data-name='中标通知']"))
            )
            winning_notice_option.click()
            time.sleep(1)
            logging.info("已选择'中标通知'招标阶段")
            
        except Exception as e:
            logging.warning(f"设置招标阶段筛选失败，尝试备用方法: {e}")
            try:
                # 备用方法：使用XPath定位
                winning_notice_alt = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//li[@data-name='中标通知' and @data-cid='1011']"))
                )
                winning_notice_alt.click()
                time.sleep(1)
                logging.info("备用方法成功选择'中标通知'招标阶段")
            except Exception as e2:
                 try:
                     # 第三种方法：使用data-cid定位
                     winning_notice_third = wait.until(
                         EC.element_to_be_clickable((By.CSS_SELECTOR, "li[data-cid='1011']"))
                     )
                     winning_notice_third.click()
                     time.sleep(1)
                     logging.info("第三种方法成功选择'中标通知'招标阶段")
                 except Exception as e3:
                     logging.warning(f"所有方法都失败，继续使用默认设置: {e3}")
        
        # 确保选择"近一年"时间筛选
        logging.info("确保选择'近一年'时间筛选")
        try:
            # 查找"近一年"选项
            near_one_year = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "li.listItem.listItem1[data-id='1'][data-name='近一年']"))
            )
            
            # 检查是否已经选中
            if "checked" not in near_one_year.get_attribute("class"):
                near_one_year.click()
                time.sleep(1)
                logging.info("已选择'近一年'时间筛选")
            else:
                logging.info("'近一年'时间筛选已经选中")
                
        except Exception as e:
            logging.warning(f"设置时间筛选失败，使用默认设置: {e}")
        
        # 点击"高级"按钮展开更多筛选选项
        logging.info("点击'高级'按钮展开更多筛选选项")
        try:
            advanced_filter = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#FilterShowMore .filterShow"))
            )
            advanced_filter.click()
            time.sleep(1)
            logging.info("已点击'高级'按钮")
        except Exception as e:
            logging.warning(f"点击'高级'按钮失败，尝试备用方法: {e}")
            try:
                # 备用方法：直接点击span元素
                advanced_span = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "#FilterShowMore .text_n"))
                )
                advanced_span.click()
                time.sleep(1)
                logging.info("备用方法成功点击'高级'按钮")
            except Exception as e2:
                logging.warning(f"所有方法都失败，继续后续步骤: {e2}")
        
        # 选择"招标单位"作为搜索范围
        logging.info("选择'招标单位'作为搜索范围")
        try:
            # 等待筛选选项显示
            time.sleep(1)
            tender_unit_option = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "li.listItem.fm4[data-id='4'][data-name='招标单位']"))
            )
            
            # 检查是否已经选中
            if "checked" not in tender_unit_option.get_attribute("class"):
                tender_unit_option.click()
                time.sleep(1)
                logging.info("已选择'招标单位'搜索范围")
            else:
                logging.info("'招标单位'搜索范围已经选中")
                
        except Exception as e:
            logging.warning(f"选择'招标单位'搜索范围失败，尝试备用方法: {e}")
            try:
                # 备用方法：使用XPath定位
                tender_unit_alt = wait.until(
                     EC.element_to_be_clickable((By.XPATH, "//li[@data-name='招标单位' and @data-id='4']"))
                 )
                tender_unit_alt.click()
                time.sleep(1)
                logging.info("备用方法成功选择'招标单位'搜索范围")
            except Exception as e2:
                logging.warning(f"所有方法都失败，使用默认搜索范围: {e2}")
        
        # 输入公司名称 - 模拟人工输入
        logging.info(f"输入搜索关键词: {company_name}")
        search_input = wait.until(
            EC.presence_of_element_located((By.ID, "toSearchValue"))
        )
        
        # 模拟鼠标点击输入框
        from selenium.webdriver.common.action_chains import ActionChains
        actions = ActionChains(driver)
        actions.move_to_element(search_input).click().perform()
        time.sleep(random.uniform(0.3, 0.8))
        
        # 清空输入框
        search_input.clear()
        time.sleep(random.uniform(0.2, 0.5))
        
        # 模拟逐字符输入（更真实的输入方式）
        for char in company_name:
            search_input.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))  # 每个字符之间的随机延迟
        
        # 输入完成后的短暂停顿
        time.sleep(random.uniform(0.5, 1.2))
        
        # 点击搜索按钮 - 处理可能的遮罩层问题
        logging.info("点击搜索按钮")
        
        # 首先检查并关闭可能的遮罩层
        try:
            # 检查是否有遮罩层
            shade_elements = driver.find_elements(By.CSS_SELECTOR, ".layui-layer-shade")
            if shade_elements:
                logging.info("检测到遮罩层，尝试关闭...")
                # 尝试点击遮罩层关闭
                for shade in shade_elements:
                    try:
                        shade.click()
                        time.sleep(0.5)
                    except:
                        pass
                
                # 或者尝试按ESC键关闭
                from selenium.webdriver.common.keys import Keys
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                time.sleep(1)
                
                # 或者使用JavaScript直接移除遮罩层
                driver.execute_script("""
                    var shades = document.querySelectorAll('.layui-layer-shade');
                    shades.forEach(function(shade) {
                        shade.remove();
                    });
                """)
                time.sleep(0.5)
        except Exception as e:
            logging.info(f"处理遮罩层时出现异常: {e}")
        
        # 等待搜索按钮可点击
        try:
            search_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "toSearchBtn"))
            )
            
            # 模拟鼠标悬停
            actions.move_to_element(search_btn).perform()
            time.sleep(random.uniform(0.3, 0.8))
            
            # 尝试普通点击
            search_btn.click()
            logging.info("搜索按钮点击成功")
            
        except Exception as e:
            logging.warning(f"普通点击失败，尝试JavaScript点击: {e}")
            try:
                # 使用JavaScript点击
                search_btn = driver.find_element(By.ID, "toSearchBtn")
                driver.execute_script("arguments[0].click();", search_btn)
                logging.info("JavaScript点击搜索按钮成功")
            except Exception as e2:
                logging.warning(f"JavaScript点击也失败，尝试ActionChains点击: {e2}")
                try:
                    # 使用ActionChains强制点击
                    search_btn = driver.find_element(By.ID, "toSearchBtn")
                    actions = ActionChains(driver)
                    actions.move_to_element(search_btn).click().perform()
                    logging.info("ActionChains点击搜索按钮成功")
                except Exception as e3:
                    logging.error(f"所有点击方法都失败: {e3}")
                    raise e3
        
        # 等待搜索结果页面加载
        logging.info("等待搜索结果页面加载...")
        time.sleep(random.uniform(5, 8))
        
        # 点击"明细"按钮切换到明细视图
        logging.info("点击'明细'按钮切换到明细视图")
        try:
            # 查找明细按钮
            detail_btn = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".summary-item[data-value='1'][data-point='1125']"))
            )
            
            # 检查是否已经选中
            if "is-select" not in detail_btn.get_attribute("class"):
                detail_btn.click()
                time.sleep(random.uniform(2, 4))  # 等待页面重新加载
                logging.info("已点击'明细'按钮，等待页面加载")
            else:
                logging.info("'明细'视图已经选中")
                
        except Exception as e:
            logging.warning(f"点击'明细'按钮失败，尝试备用方法: {e}")
            try:
                # 备用方法：使用XPath定位
                detail_btn_alt = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//div[@class='summary-item fl' and @data-value='1' and text()='明细']"))
                )
                detail_btn_alt.click()
                time.sleep(random.uniform(2, 4))
                logging.info("备用方法成功点击'明细'按钮")
            except Exception as e2:
                logging.warning(f"所有方法都失败，继续使用当前视图: {e2}")
        
        total_saved = 0  # 记录该企业总共保存的数据量
        
        # 动态检测总页数
        total_pages = get_total_pages(driver)
        logging.info(f"检测到总页数: {total_pages}，开始动态爬取所有页面")
        
        page = 1
        while page <= total_pages:
            logging.info(f"正在爬取第 {page} 页...")
            
            # 模拟用户查看页面内容
            if page == 1:
                # 第一页时模拟用户从顶部开始浏览
                logging.info("模拟用户从页面顶部开始浏览...")
                driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
                time.sleep(random.uniform(1, 2))
            
            # 模拟用户滚动浏览页面内容
            logging.info("模拟用户浏览页面内容...")
            driver.execute_script("window.scrollTo({top: window.innerHeight * 0.3, behavior: 'smooth'});")
            time.sleep(random.uniform(1, 2))
            
            driver.execute_script("window.scrollTo({top: window.innerHeight * 0.6, behavior: 'smooth'});")
            time.sleep(random.uniform(1, 2))
            
            # 提取当前页面的中标信息（点击每条标题进入详情页面）
            page_saved_count = extract_and_save_winning_info(driver, company_name, industry, db, page)
            
            total_saved += page_saved_count
            logging.info(f"第 {page} 页处理完成: 成功保存 {page_saved_count} 条数据")
            logging.info(f"企业 {company_name} 累计已保存 {total_saved} 条中标公告")
            
            # 检查是否还有下一页，如果有则翻页
            if page < total_pages:
                # 模拟用户浏览完当前页面后的停顿
                browse_time = random.uniform(2, 4)
                logging.info(f"模拟浏览当前页面 {browse_time:.1f} 秒...")
                time.sleep(browse_time)
                
                # 模拟用户滚动到页面底部查看分页
                logging.info("模拟滚动到页面底部查看分页...")
                driver.execute_script("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'});")
                time.sleep(random.uniform(1, 2))
                
                # 使用新的动态翻页函数
                next_page = page + 1
                if navigate_to_page(driver, next_page):
                    logging.info(f"✓ 成功翻页到第 {next_page} 页")
                    page = next_page
                    
                    # 模拟用户查看新页面内容
                    logging.info("模拟查看新页面内容...")
                    driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
                    time.sleep(random.uniform(1, 2))
                else:
                    logging.warning(f"翻页到第 {next_page} 页失败，停止爬取")
                    break
            else:
                logging.info(f"已完成所有 {total_pages} 页的爬取")
                break
        
        logging.info(f"企业 {company_name} 爬取完成，总共保存了 {total_saved} 条中标信息")
        return total_saved
        
    except Exception as e:
        logging.error(f"搜索企业 {company_name} 失败: {e}")
        return 0


def extract_and_save_winning_info(driver, company_name, industry, db, page):
    """从明细页面直接提取中标信息并保存到数据库"""
    wait = WebDriverWait(driver, 10)
    saved_count = 0
    
    try:
        # 等待中标列表加载
        logging.info("等待中标列表加载...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".container-con li")))
        time.sleep(3)
        
        # 获取所有中标项目
        tender_items = driver.find_elements(By.CSS_SELECTOR, ".container-con li")
        total_items = len(tender_items)
        logging.info(f"第 {page} 页找到 {total_items} 个中标项目")
        
        # 记录原始窗口句柄
        original_window = driver.current_window_handle
        
        # 使用索引而不是直接遍历元素，避免stale element问题
        for i in range(total_items):
            try:
                # 重新获取当前项目元素，避免stale element问题
                tender_items = driver.find_elements(By.CSS_SELECTOR, ".container-con li")
                if i >= len(tender_items):
                    logging.warning(f"项目索引 {i} 超出范围，跳过")
                    continue
                    
                item = tender_items[i]
                
                # 滚动到当前项目
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                time.sleep(0.5)
                
                # 提取基本信息
                title_element = item.find_element(By.CSS_SELECTOR, ".con-title")
                title = title_element.get_attribute("title") or title_element.text.strip()
                
                # 优先使用data-url属性中的详情页链接
                link = title_element.get_attribute("data-url")
                if not link:
                    # 备用方案：使用href属性
                    link = title_element.get_attribute("href")
                    if link and link.startswith("//"):
                        link = "https:" + link
                
                # 确保链接格式正确
                if link and not link.startswith("http"):
                    if link.startswith("//"):
                        link = "https:" + link
                    else:
                        link = "https://" + link
                
                # 提取contentId（从搜索结果页面的data-contentid属性）
                content_id = title_element.get_attribute("data-contentid") or ""
                
                logging.info(f"正在处理第 {i+1} 条: {title[:50]}...")
                
                # 直接从明细页面提取信息
                tender_data = extract_summary_info(item, company_name, industry, title, link, content_id)
                
                if tender_data:
                    # 点击标题链接获取详情页内容和额外信息
                    detail_info = get_detail_page_content(driver, link, original_window, page, i+1)
                    
                    if detail_info:
                        tender_data['detail_txt'] = detail_info.get('detail_txt', '')
                        tender_data['detail_summary'] = detail_info.get('detail_summary', '')
                    else:
                        tender_data['detail_txt'] = ''
                        tender_data['detail_summary'] = ''
                    # area和projectType已从搜索结果页面提取，不需要从详情页覆盖
                    
                    # 保存到数据库
                    if save_tender_notice(db, tender_data):
                        saved_count += 1
                        logging.info(f"✓ 第 {page} 页第 {i+1} 条数据保存成功: {title[:30]}...")
                    else:
                        logging.info(f"⚠ 第 {page} 页第 {i+1} 条数据已存在或保存失败: {title[:30]}...")
                else:
                    logging.warning(f"第 {i+1} 条数据提取失败")
                
            except Exception as e:
                logging.error(f"处理第 {i+1} 项信息失败: {e}")
                # 确保回到原始窗口
                try:
                    driver.switch_to.window(original_window)
                except:
                    pass
                continue
        
        logging.info(f"第 {page} 页处理完成，成功保存 {saved_count}/{total_items} 条中标信息")
        return saved_count
        
    except Exception as e:
        logging.error(f"提取中标信息失败: {e}")
        return 0


def extract_summary_info(item, company_name, industry, title, link, content_id):
    """从明细页面的summary信息中提取数据"""
    try:
        # 查找item-summary区域
        summary_div = item.find_element(By.CSS_SELECTOR, ".item-summary")
        
        # 提取中标单位
        winning_unit = None
        try:
            winning_element = summary_div.find_element(By.XPATH, ".//span[contains(text(),'中标单位：')]/following-sibling::span")
            winning_unit = winning_element.text.strip() if winning_element.text.strip() else None
        except:
            pass
        
        # 提取中标价格
        winning_amount = None
        try:
            amount_element = summary_div.find_element(By.XPATH, ".//span[contains(text(),'中标价格：')]/following-sibling::span")
            amount_text = amount_element.text.strip()
            winning_amount = amount_text if amount_text and amount_text != '-' else None
        except:
            pass
        
        # 提取招标单位
        tender_unit = None
        try:
            tender_element = summary_div.find_element(By.XPATH, ".//span[contains(text(),'招标单位：')]/following-sibling::span")
            tender_unit = tender_element.text.strip() if tender_element.text.strip() else None
        except:
            pass
        
        # 提取代理单位
        agent_unit = None
        try:
            agent_element = summary_div.find_element(By.XPATH, ".//span[contains(text(),'代理单位：')]/following-sibling::span")
            agent_unit = agent_element.text.strip() if agent_element.text.strip() else None
        except:
            pass
        
        # 提取正文预览
        brief_text = None
        try:
            preview_element = summary_div.find_element(By.XPATH, ".//span[contains(text(),'正文预览：')]/following-sibling::span")
            brief_text = preview_element.text.strip() if preview_element.text.strip() else None
        except:
            pass
        
        # 提取地区和项目类型信息（从con-bottom元素中）
        area = None
        project_type = None
        try:
            # 查找con-bottom区域
            con_bottom = item.find_element(By.CSS_SELECTOR, ".con-bottom")
            # 查找所有con-address元素
            address_elements = con_bottom.find_elements(By.CSS_SELECTOR, "a.con-address")
            
            for element in address_elements:
                text = element.text.strip()
                # 提取地区信息（包含-的文本，且不是"结果 - 中标通知"）
                if '-' in text and '结果' not in text and '中标通知' not in text:
                    area = text
                # 提取项目类型（货物、工程、服务等）
                elif text in ['货物', '工程', '服务']:
                    project_type = text
        except Exception as e:
            logging.debug(f"提取地区和项目类型失败: {e}")
            pass
        
        # 提取公告时间
        create_time = None
        try:
            # 查找时间元素
            time_element = item.find_element(By.CSS_SELECTOR, ".con-time")
            time_text = time_element.text.strip()
            
            # 处理相对时间
            if '分钟前' in time_text or '小时前' in time_text or '刚刚' in time_text:
                create_time = datetime.now().strftime('%Y-%m-%d')
            elif '天前' in time_text:
                # 提取天数
                import re
                match = re.search(r'(\d+)天前', time_text)
                if match:
                    days_ago = int(match.group(1))
                    create_time = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
                else:
                    create_time = datetime.now().strftime('%Y-%m-%d')
            else:
                # 直接使用显示的日期
                create_time = time_text
        except:
            create_time = datetime.now().strftime('%Y-%m-%d')
        
        # 构建数据字典
        tender_data = {
            'company_name': company_name,
            'industry': industry,
            'contentId': content_id,
            'title': title,
            'url': link,
            'createTime': create_time,
            'area': area,  # 从搜索结果页面提取的地区信息
            'noticeType': '中标通知',
            'projectType': project_type,  # 从搜索结果页面提取的项目类型
            'winning_bidder': winning_unit,  # 中标单位
            'tenderees': tender_unit,  # 招标单位
            'agent': agent_unit,  # 代理单位
            'budget': winning_amount,  # 中标金额
            'tenderEndTime': None,
            'registrationEndTime': None,
            'briefText': brief_text,
            'hasAnnex': False,  # 明细页面无法判断是否有附件
            'crawl_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source': '千里马网',
            'detail_txt': '',
            'detail_summary': ''
        }
        
        return tender_data
        
    except Exception as e:
        logging.error(f"提取明细信息失败: {e}")
        return None


def get_detail_page_content(driver, link, original_window, page=None, item_num=None):
    """在新标签页中打开详情页获取摘要信息和详情内容，返回 {'detail_txt': str, 'detail_summary': str}"""
    if not link:
        logging.warning("详情页链接为空，跳过获取详情页内容")
        return None

    # 防检测：每次详情页间隔10秒打开
    logging.info("防检测延迟：等待10秒后打开详情页...")
    time.sleep(10)

    max_retries = 3
    new_window = None

    for attempt in range(max_retries):
        try:
            # 校验会话有效
            try:
                _ = driver.current_window_handle
            except InvalidSessionIdException:
                logging.warning(f"会话失效，尝试第 {attempt + 1} 次重新获取详情页内容")
                if attempt == max_retries - 1:
                    return None
                continue

            if page and item_num:
                 logging.info(f"正在访问第 {page} 页第 {item_num} 条详情页")
            else:
                logging.info("正在访问详情页")

            # 优先尝试在当前页定位对应href或data-url的元素进行Ctrl+Click
            link_element = None
            try:
                link_elements = driver.find_elements(By.XPATH, f"//a[@href='{link}' or @data-url='{link}']")
                if link_elements:
                    link_element = link_elements[0]
                else:
                    # 创建一个临时隐藏的链接在新标签页打开
                    driver.execute_script(
                        """
                        var tempLink = document.createElement('a');
                        tempLink.href = arguments[0];
                        tempLink.target = '_blank';
                        tempLink.style.display = 'none';
                        tempLink.id = 'temp-detail-link';
                        document.body.appendChild(tempLink);
                        """,
                        link,
                    )
                    link_element = driver.find_element(By.ID, "temp-detail-link")
            except Exception as e:
                logging.error(f"无法找到或创建链接元素: {e}")
                continue

            # 使用ActionChains Ctrl+Click 打开新标签页，失败则fallback为window.open
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                actions = ActionChains(driver)
                actions.key_down(Keys.CONTROL).click(link_element).key_up(Keys.CONTROL).perform()
                logging.info("方法1成功: Ctrl+Click打开新标签页")
                time.sleep(2.5)
            except Exception as e:
                logging.warning(f"Ctrl+Click失败: {e}")
                try:
                    driver.execute_script("window.open(arguments[0], '_blank');", link)
                    logging.info("方法2成功: JavaScript window.open 打开新标签页")
                    time.sleep(2)
                except Exception as js_e:
                    logging.error(f"JavaScript打开新标签页也失败: {js_e}")
                    continue

            # 清理临时链接
            try:
                temp_link = driver.find_element(By.ID, "temp-detail-link")
                driver.execute_script("arguments[0].remove();", temp_link)
            except:
                pass

            # 定位新窗口
            all_windows = driver.window_handles
            for win in all_windows:
                if win != original_window:
                    new_window = win
                    break

            if not new_window:
                logging.error("无法找到新打开的标签页")
                continue

            # 切换到新标签页
            driver.switch_to.window(new_window)

            # 等待页面主体出现，设置1分钟超时
            try:
                WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                time.sleep(1.5)
                logging.info("详情页加载成功")
            except TimeoutException:
                logging.warning("详情页加载超时（1分钟），设置详情内容为空")
                # 关闭新标签页并返回空值
                try:
                    driver.close()
                finally:
                    driver.switch_to.window(original_window)
                return {
                    "detail_txt": "",
                    "detail_summary": ""
                }

            # 简单检查加载是否成功
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text
            except Exception:
                body_text = ""

            current_url = driver.current_url
            if (
                current_url == link
                or "error" in current_url.lower()
                or any(x in current_url for x in ["404", "403"])
                or len(body_text.strip()) < 50
            ):
                logging.warning("详情页加载可能失败，内容过短或URL异常")
            else:
                logging.info("详情页加载成功")

            # 模拟滚动浏览，便于加载懒加载内容
            try:
                page_height = driver.execute_script("return document.body.scrollHeight")
                viewport = driver.execute_script("return window.innerHeight") or 800
                pos = 0
                step = max(200, viewport // 2)
                while pos < page_height:
                    driver.execute_script("window.scrollTo(0, arguments[0]);", pos)
                    time.sleep(random.uniform(0.3, 0.7))
                    pos += step
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.8)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.4)
            except Exception as se:
                logging.debug(f"页面滚动失败: {se}")

            # 尝试提取摘要信息和详情内容
            detail_summary = ""
            detail_txt = ""
            
            try:
                # 尝试提取摘要信息（summaryTable）
                summary_element = driver.find_element(By.ID, "summaryTable")
                summary_table = summary_element.find_element(By.CSS_SELECTOR, "table.summaryTable")
                
                # 解析摘要表格
                summary_items = []
                rows = summary_table.find_elements(By.TAG_NAME, "tr")
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 2:
                        # 处理表格行，每行可能有2列或4列
                        for i in range(0, len(cells), 2):
                            if i + 1 < len(cells):
                                title_cell = cells[i]
                                content_cell = cells[i + 1]
                                
                                # 过滤掉class='none'的行
                                row_class = row.get_attribute("class") or ""
                                if "none" in row_class:
                                    continue
                                
                                title = title_cell.text.strip()
                                content = content_cell.text.strip()
                                
                                # 清理内容中的多余信息，如"企业信息"链接、"更多联系人"等
                                if "企业信息" in content:
                                    content = content.split("企业信息")[0].strip()
                                if "更多联系人" in content:
                                    content = content.split("更多联系人")[0].strip()
                                
                                if title and content and content != "-":
                                    summary_items.append(f"{title}: {content}")
                
                detail_summary = "; ".join(summary_items)
                logging.info(f"成功提取摘要信息，共 {len(summary_items)} 项")
                
            except Exception as e:
                logging.warning(f"提取摘要信息失败: {e}")
                detail_summary = ""

            try:
                # 尝试提取详情内容（detailInfoContainer）
                detail_container = driver.find_element(By.ID, "detailInfoContainer")
                detail_txt = detail_container.text.strip()
                logging.info("成功提取详情内容")
                
            except Exception as e:
                logging.warning(f"提取详情内容失败: {e}")
                try:
                    # 备用方案：读取整个页面内容
                    detail_txt = driver.find_element(By.TAG_NAME, "body").text
                    logging.info("使用备用方案提取页面内容")
                except Exception:
                    detail_txt = body_text

            # 防检测：浏览50秒再关闭页面
            logging.info("防检测浏览：在详情页停留50秒...")
            time.sleep(50)

            # 关闭新标签页并返回
            try:
                driver.close()
            finally:
                driver.switch_to.window(original_window)
                time.sleep(0.8)

            return {
                "detail_txt": detail_txt,
                "detail_summary": detail_summary
            }

        except InvalidSessionIdException as e:
            logging.warning(f"会话ID无效错误，尝试第 {attempt + 1} 次: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            else:
                logging.error(f"多次尝试后仍然失败: {e}")
                return None
        except Exception as e:
            logging.error(f"获取详情页内容失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            try:
                if new_window and new_window in driver.window_handles:
                    driver.switch_to.window(new_window)
                    driver.close()
                driver.switch_to.window(original_window)
            except:
                pass
            
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                return None
    
    return None


def extract_detail_page_info(driver, company_name, industry, title, link, content_id=None):
    """从详情页面提取完整的中标信息"""
    try:
        # 提取ID（优先使用传入的content_id，然后从链接中获取，最后从页面元素中获取）
        if not content_id:
            if link:
                import re
                # 尝试从链接中提取contentId
                match = re.search(r'contentId=(\d+)', link)
                if match:
                    content_id = match.group(1)
                else:
                    # 尝试从链接中提取bid-后面的数字
                    match = re.search(r'bid-(\d+)', link)
                    if match:
                        content_id = match.group(1)
            
            # 如果从链接中没有提取到，尝试从页面元素中获取data-contentid
            if not content_id:
                try:
                    # 查找带有data-contentid属性的元素
                    elements_with_contentid = driver.find_elements(By.XPATH, "//*[@data-contentid]")
                    if elements_with_contentid:
                        content_id = elements_with_contentid[0].get_attribute("data-contentid")
                except:
                    pass
        
        # 提取页面内容
        page_content = driver.page_source
        
        # 提取发布时间
        publish_time = ""
        try:
            time_elements = driver.find_elements(By.XPATH, "//span[contains(text(),'发布时间')]/following-sibling::span | //td[contains(text(),'发布时间')]/following-sibling::td")
            if time_elements:
                publish_time = time_elements[0].text.strip()
        except:
            pass
        
        # 提取地区信息
        region = ""
        try:
            region_elements = driver.find_elements(By.XPATH, "//span[contains(text(),'地区')]/following-sibling::span | //td[contains(text(),'地区')]/following-sibling::td")
            if region_elements:
                region = region_elements[0].text.strip()
        except:
            pass
        
        # 提取项目类型
        project_type = ""
        try:
            type_elements = driver.find_elements(By.XPATH, "//span[contains(text(),'项目类型')]/following-sibling::span | //td[contains(text(),'项目类型')]/following-sibling::td")
            if type_elements:
                project_type = type_elements[0].text.strip()
        except:
            pass
        
        # 提取中标单位
        winning_unit = ""
        try:
            winning_elements = driver.find_elements(By.XPATH, "//span[contains(text(),'中标单位') or contains(text(),'中标人')]/following-sibling::span | //td[contains(text(),'中标单位') or contains(text(),'中标人')]/following-sibling::td")
            if winning_elements:
                winning_unit = winning_elements[0].text.strip()
        except:
            pass
        
        # 提取中标金额
        winning_amount = ""
        try:
            amount_elements = driver.find_elements(By.XPATH, "//span[contains(text(),'中标金额') or contains(text(),'中标价')]/following-sibling::span | //td[contains(text(),'中标金额') or contains(text(),'中标价')]/following-sibling::td")
            if amount_elements:
                winning_amount = amount_elements[0].text.strip()
        except:
            pass
        
        # 提取招标单位
        tender_unit = ""
        try:
            tender_elements = driver.find_elements(By.XPATH, "//span[contains(text(),'招标人') or contains(text(),'采购人')]/following-sibling::span | //td[contains(text(),'招标人') or contains(text(),'采购人')]/following-sibling::td")
            if tender_elements:
                tender_unit = tender_elements[0].text.strip()
        except:
            pass
        
        # 提取代理单位
        agent_unit = ""
        try:
            agent_elements = driver.find_elements(By.XPATH, "//span[contains(text(),'代理机构')]/following-sibling::span | //td[contains(text(),'代理机构')]/following-sibling::td")
            if agent_elements:
                agent_unit = agent_elements[0].text.strip()
        except:
            pass
        
        # 提取正文内容作为简介
        brief_text = ""
        try:
            content_elements = driver.find_elements(By.CSS_SELECTOR, ".content, .detail-content, .zb-detail-content, .main-content")
            if content_elements:
                brief_text = content_elements[0].text[:500]  # 取前500字符
        except:
            pass
        
        # 检查是否有附件
        has_annex = False
        try:
            annex_elements = driver.find_elements(By.XPATH, "//a[contains(@href,'download') or contains(text(),'附件') or contains(text(),'下载')]")
            has_annex = len(annex_elements) > 0
        except:
            pass
        
        # 获取详情页完整内容
        detail_txt = ""
        try:
            # 尝试获取页面的完整文本内容
            body_element = driver.find_element(By.TAG_NAME, "body")
            detail_txt = body_element.text
        except:
            detail_txt = brief_text  # 如果获取失败，使用简介内容
        
        # 构建数据字典 - 严格按照用户要求的JSON结构
        notice_data = {
            'company_name': company_name if company_name else None,
            'industry': industry if industry else None,
            'contentId': content_id if content_id else None,
            'title': title if title else None,
            'url': link if link else None,
            'createTime': publish_time if publish_time else None,
            'area': region if region else None,
            'noticeType': '中标通知',
            'projectType': project_type if project_type else None,
            'tenderees': company_name if company_name else None,  # 招标单位与company_name一致
            'agent': agent_unit if agent_unit else None,
            'budget': winning_amount if winning_amount else None,
            'tenderEndTime': None,
            'registrationEndTime': None,
            'briefText': brief_text if brief_text else None,
            'hasAnnex': has_annex,
            'crawl_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source': '千里马网',
            'detail-txt': detail_txt if detail_txt else None
        }
        
        return notice_data
        
    except Exception as e:
        logging.error(f"提取详情页面信息失败: {e}")
        return None


def main():
    """
    主函数
    """
    driver = None
    mongo_client = None
    
    try:
        # 连接MongoDB
        mongo_client, db = connect_to_mongo()
        if db is None:
            logging.error("无法连接到MongoDB，程序退出")
            return
        
        # 获取企业名单
        companies = get_company_list(db)
        if not companies:
            logging.error("未获取到企业名单，程序退出")
            return
        
        # 设置浏览器
        driver = setup_driver()
        
        # 执行登录
        if not login(driver):
            logging.error("登录失败！程序退出")
            return
        
        logging.info("登录成功！开始爬取招标信息...")
        
        # 统计信息
        total_companies = len(companies)
        processed_companies = 0
        total_notices = 0
        
        # 遍历每个企业进行搜索
        for company in companies:
            company_name = company["company_name"]
            industry = company["industry"]
            
            try:
                processed_companies += 1
                logging.info(f"正在处理第 {processed_companies}/{total_companies} 家企业: {company_name}")
                
                # 搜索该企业的中标信息（已在函数内部完成保存）
                saved_count = search_company_tenders(driver, company_name, industry, db)
                
                total_notices += saved_count
                logging.info(f"企业 {company_name} 处理完成，成功保存 {saved_count} 条中标公告")
                
                # 随机延迟，避免请求过于频繁
                time.sleep(random.uniform(3, 6))
                
            except Exception as e:
                logging.error(f"处理企业 {company_name} 时出现错误: {e}")
                continue
        
        logging.info(f"爬取完成！共处理 {processed_companies} 家企业，保存 {total_notices} 条中标公告")

    except Exception as e:
        logging.exception("主程序执行过程中出现错误")
    finally:
        if driver:
            driver.quit()
            logging.info("浏览器已关闭。")
        if mongo_client:
            mongo_client.close()
            logging.info("MongoDB连接已关闭。")
        logging.info("程序执行完毕。")


if __name__ == '__main__':
    main()