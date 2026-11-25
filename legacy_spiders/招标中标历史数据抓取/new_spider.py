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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/new_spider.log", mode='a', encoding='utf-8'),
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
TENDER_COLLECTION = "tender_notices"  # 招标公告集合


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
        # 检查是否已存在相同的contentId
        if collection.find_one({"contentId": tender_data.get("contentId")}):
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


def search_company_tenders(driver, company_name, industry, db):
    """搜索指定企业的招标信息"""
    try:
        logging.info(f"开始搜索企业: {company_name} (行业: {industry})")
        
        # 获取原始窗口句柄，用于详情页处理
        original_window = driver.current_window_handle
        
        # 进入搜索页面
        driver.get(SEARCH_URL)
        wait = WebDriverWait(driver, 15)
        
        # 等待页面加载
        time.sleep(random.uniform(3, 5))
        
        # 首先模拟点击"招标信息"标签 - 确保在正确的标签页下进行搜索设置
        logging.info("首先模拟点击'招标信息'标签")
        try:
            # 等待招标信息标签元素可点击
            tender_info_tab = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".tabItem.tabItem1[data-id='1']"))
            )
            
            # 检查当前状态（仅用于日志记录）
            tab_classes = tender_info_tab.get_attribute("class")
            if "tabItemSelect" in tab_classes:
                logging.info("'招标信息'标签当前已选中，但仍执行模拟点击操作")
            else:
                logging.info("'招标信息'标签当前未选中，执行点击操作")
            
            # 模拟人工点击行为
            # 先滚动到元素位置
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tender_info_tab)
            time.sleep(random.uniform(0.5, 1.0))
            
            # 使用ActionChains模拟更真实的点击
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(driver)
            actions.move_to_element(tender_info_tab).pause(random.uniform(0.3, 0.8)).click().perform()
            
            logging.info("已成功模拟点击'招标信息'标签")
            
            # 等待页面响应和内容加载
            time.sleep(random.uniform(2, 3))
            
        except Exception as e:
            logging.warning(f"主要方法点击'招标信息'标签失败: {e}")
            logging.info("尝试备用方法...")
            try:
                # 备用方法1：通过文本内容查找并点击
                tender_info_tab_alt = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//div[@class and contains(@class, 'tabItem') and .//p[text()='招标信息']]"))
                )
                actions = ActionChains(driver)
                actions.move_to_element(tender_info_tab_alt).pause(random.uniform(0.3, 0.8)).click().perform()
                time.sleep(random.uniform(2, 3))
                logging.info("备用方法成功点击'招标信息'标签")
                
            except Exception as e2:
                logging.warning(f"备用方法也失败: {e2}")
                logging.info("尝试直接JavaScript点击...")
                try:
                    # 备用方法2：JavaScript直接点击
                    js_click_element = driver.find_element(By.CSS_SELECTOR, ".tabItem.tabItem1[data-id='1']")
                    driver.execute_script("arguments[0].click();", js_click_element)
                    time.sleep(random.uniform(2, 3))
                    logging.info("JavaScript方法成功点击'招标信息'标签")
                except Exception as e3:
                    logging.error(f"所有点击方法都失败: {e3}")
                    logging.info("继续使用当前页面内容")
        
        # 选择"招标单位"搜索类型
        logging.info("选择'招标单位'搜索类型")
        try:
            # 查找并点击搜索类型下拉框按钮
            search_type_btn = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".searchPopupBtn"))
            )
            search_type_btn.click()
            time.sleep(1)
            
            # 等待下拉菜单出现并选择"招标单位"选项
            tender_unit_option = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".popupItem5[data-name='招标单位'][data-val='4']"))
            )
            tender_unit_option.click()
            time.sleep(1)
            logging.info("已选择'招标单位'搜索类型")
            
        except Exception as e:
            logging.warning(f"设置搜索类型失败，使用默认设置: {e}")
            # 尝试备用方法
            try:
                logging.info("尝试备用方法选择招标单位...")
                tender_unit_li = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//li[@data-name='招标单位' and @data-val='4']"))
                )
                tender_unit_li.click()
                time.sleep(1)
                logging.info("备用方法成功选择'招标单位'搜索类型")
            except Exception as e2:
                logging.warning(f"备用方法也失败，使用默认的'全文'搜索类型: {e2}")
        
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
        
        total_saved = 0  # 记录该企业总共保存的数据量
        max_pages = 5  # 最多爬取5页
        
        for page in range(1, max_pages + 1):
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
            
            # 提取当前页面的招标信息
            page_notices = extract_tender_info(driver, company_name, industry)
            
            # 立即保存当前页面的数据到数据库
            if page_notices:
                logging.info(f"=== 第 {page} 页采集到 {len(page_notices)} 条数据，开始保存到数据库 ===")
                page_saved_count = 0
                
                for i, notice in enumerate(page_notices):
                    try:
                        # 若无详情内容，尝试打开详情页采集
                        if not notice.get("detail_txt"):
                            try:
                                detail_info = get_detail_page_content(driver, notice.get("url"), original_window, page_num=page, item_num=i+1)
                                if detail_info:
                                    notice["detail_txt"] = detail_info.get("detail_txt", "")
                                    notice["detail_summary"] = detail_info.get("detail_summary", "")
                                else:
                                    # 详情页获取失败，确保字段为空值
                                    notice["detail_txt"] = ""
                                    notice["detail_summary"] = ""
                            except Exception as de:
                                logging.warning(f"获取第 {page} 页第 {i+1} 条详情失败: {de}")
                                # 确保即使异常也设置为空值
                                notice["detail_txt"] = ""
                                notice["detail_summary"] = ""

                        if save_tender_notice(db, notice):
                            page_saved_count += 1
                            logging.info(f"✓ 第 {page} 页第 {i+1} 条数据保存成功: {notice.get('title', 'Unknown')[:50]}...")
                        else:
                            logging.info(f"⚠ 第 {page} 页第 {i+1} 条数据已存在或保存失败: {notice.get('title', 'Unknown')[:50]}...")
                    except Exception as e:
                        logging.error(f"❌ 第 {page} 页第 {i+1} 条数据保存出错: {e}")
                
                total_saved += page_saved_count
                logging.info(f"第 {page} 页保存完成: 成功保存 {page_saved_count}/{len(page_notices)} 条数据")
                logging.info(f"企业 {company_name} 累计已保存 {total_saved} 条招标公告")
                
                # 打印当前页面采集的数据（JSON格式，仅显示前2条）
                logging.info(f"=== 第 {page} 页数据示例 (前2条) ===")
                for i, notice in enumerate(page_notices[:2]):
                    logging.info(f"第 {i+1} 条数据:")
                    logging.info(safe_json_dumps(notice, ensure_ascii=False, indent=2))
                    logging.info("---")
            else:
                logging.warning(f"第 {page} 页未提取到任何数据")
            
            # 检查是否有下一页 - 模拟真实用户翻页行为
            try:
                # 模拟用户浏览完当前页面后的停顿
                browse_time = random.uniform(2, 4)
                logging.info(f"模拟浏览当前页面 {browse_time:.1f} 秒...")
                time.sleep(browse_time)
                
                # 模拟用户滚动到页面底部查看分页
                logging.info("模拟滚动到页面底部查看分页...")
                driver.execute_script("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'});")
                time.sleep(random.uniform(1, 2))
                
                # 首先检查"下一页"按钮是否存在且未禁用
                next_page_btn = driver.find_element(By.CSS_SELECTOR, ".next:not(.disabled)")
                if next_page_btn and "disabled" not in next_page_btn.get_attribute("class"):
                    logging.info(f"找到下一页按钮，准备翻页到第 {page + 1} 页...")
                    
                    # 模拟鼠标悬停在下一页按钮上
                    from selenium.webdriver.common.action_chains import ActionChains
                    actions = ActionChains(driver)
                    actions.move_to_element(next_page_btn).perform()
                    time.sleep(random.uniform(0.3, 0.8))
                    
                    # 模拟用户思考时间
                    think_time = random.uniform(0.5, 1.5)
                    logging.info(f"模拟用户思考 {think_time:.1f} 秒...")
                    time.sleep(think_time)
                    
                    # 点击下一页
                    next_page_btn.click()
                    logging.info("已点击下一页按钮")
                    
                    # 模拟页面加载等待时间（更真实的等待）
                    initial_wait = random.uniform(1, 2)
                    logging.info(f"初始等待 {initial_wait:.1f} 秒...")
                    time.sleep(initial_wait)
                    
                    # 验证页面是否开始跳转
                    try:
                        # 等待新页面的内容加载
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".container-con li"))
                        )
                        
                        # 模拟页面加载完成后的额外等待
                        load_complete_wait = random.uniform(2, 4)
                        logging.info(f"页面加载完成，额外等待 {load_complete_wait:.1f} 秒...")
                        time.sleep(load_complete_wait)
                        
                        # 模拟用户查看新页面内容
                        logging.info("模拟查看新页面内容...")
                        driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
                        time.sleep(random.uniform(1, 2))
                        
                        logging.info(f"成功跳转到第 {page + 1} 页")
                    except:
                        logging.warning("页面跳转可能失败，继续尝试")
                else:
                    logging.info("下一页按钮已禁用，已到最后一页")
                    break
            except Exception as e:
                logging.info(f"没有更多页面或翻页失败: {e}")
                break
        
        logging.info(f"企业 {company_name} 爬取完成，总共保存了 {total_saved} 条招标信息")
        return total_saved
        
    except Exception as e:
        logging.error(f"搜索企业 {company_name} 失败: {e}")
        return 0


def extract_tender_info(driver, company_name, industry):
    """从搜索结果页面中提取招标信息"""
    tender_data = []
    
    try:
        # 等待页面加载完成
        wait = WebDriverWait(driver, 15)
        
        # 等待招标列表加载
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".container-con li")))
        time.sleep(3)
        
        # 获取所有招标项目
        tender_items = driver.find_elements(By.CSS_SELECTOR, ".container-con li")
        logging.info(f"找到 {len(tender_items)} 个招标项目")
        
        for i, item in enumerate(tender_items):
            try:
                # 提取基本信息
                title_element = item.find_element(By.CSS_SELECTOR, ".con-title")
                title = title_element.get_attribute("title") or title_element.text.strip()
                
                # 提取链接和ID
                # 优先使用data-url，其次使用href
                link = title_element.get_attribute("data-url") or title_element.get_attribute("href")
                if link and link.startswith("//"):
                    link = "https:" + link
                # 确保链接以http开头
                if link and not link.startswith("http"):
                    if link.startswith("//"):
                        link = "https:" + link
                    else:
                        link = "https://" + link

                # 提取项目ID
                content_id = title_element.get_attribute("data-contentid") or ""
                
                # 提取发布时间
                time_element = item.find_element(By.CSS_SELECTOR, ".con-time")
                publish_time = time_element.text.strip().replace("", "").strip()
                
                # 提取地区信息
                region = ""
                try:
                    region_elements = item.find_elements(By.CSS_SELECTOR, ".con-address:not(.con-type)")
                    if region_elements:
                        region = region_elements[0].text.strip()
                except:
                    pass
                
                # 提取项目类型
                project_type = ""
                announcement_type = ""
                try:
                    type_elements = item.find_elements(By.CSS_SELECTOR, ".con-address.con-type")
                    if len(type_elements) >= 1:
                        announcement_type = type_elements[0].text.strip()
                    if len(type_elements) >= 2:
                        project_type = type_elements[1].text.strip()
                except:
                    pass
                
                # 提取详细信息
                tender_unit = ""  # 招标单位
                agent_unit = ""   # 代理单位
                tender_budget = ""  # 招标预算
                registration_deadline = ""  # 报名截止时间
                bidding_deadline = ""  # 投标截止时间
                content_preview = ""  # 正文预览
                
                try:
                    # 查找详细信息区域
                    summary_area = item.find_element(By.CSS_SELECTOR, ".item-summary")
                    
                    # 提取招标单位
                    try:
                        tender_unit_elem = summary_area.find_element(By.XPATH, ".//span[text()='招标单位：']/following-sibling::span")
                        tender_unit = tender_unit_elem.text.strip()
                    except:
                        pass
                    
                    # 提取代理单位
                    try:
                        agent_unit_elem = summary_area.find_element(By.XPATH, ".//span[text()='代理单位：']/following-sibling::span")
                        agent_unit = agent_unit_elem.text.strip()
                        if agent_unit == "-":
                            agent_unit = ""
                    except:
                        pass
                    
                    # 提取招标预算
                    try:
                        budget_elem = summary_area.find_element(By.XPATH, ".//span[text()='招标预算：']/following-sibling::span")
                        tender_budget = budget_elem.text.strip()
                        if tender_budget == "-":
                            tender_budget = ""
                    except:
                        pass
                    
                    # 提取报名截止时间
                    try:
                        reg_deadline_elem = summary_area.find_element(By.XPATH, ".//span[text()='报名截止时间：']/following-sibling::span")
                        registration_deadline = reg_deadline_elem.text.strip()
                        if registration_deadline == "-":
                            registration_deadline = ""
                    except:
                        pass
                    
                    # 提取投标截止时间
                    try:
                        bid_deadline_elem = summary_area.find_element(By.XPATH, ".//span[text()='投标截止时间：']/following-sibling::span")
                        bidding_deadline = bid_deadline_elem.text.strip()
                        if bidding_deadline == "-":
                            bidding_deadline = ""
                    except:
                        pass
                    
                    # 提取正文预览
                    try:
                        preview_elem = summary_area.find_element(By.XPATH, ".//span[text()='正文预览：']/following-sibling::span")
                        content_preview = preview_elem.text.strip()
                        if content_preview == "-":
                            content_preview = ""
                    except:
                        pass
                        
                except:
                    logging.debug(f"第 {i+1} 个项目详细信息提取失败")
                
                # 检查是否有附件下载
                has_attachment = False
                try:
                    attachment_img = item.find_element(By.CSS_SELECTOR, "img[alt*='招标文件下载']")
                    has_attachment = True
                except:
                    pass
                
                # 构建数据字典
                data = {
                    "company_name": company_name,
                    "industry": industry,
                    "contentId": content_id,
                    "title": title,
                    "url": link,
                    "createTime": publish_time,
                    "area": region,
                    "noticeType": announcement_type,
                    "projectType": project_type,
                    "winning_bidder": None,
                    "tenderees": company_name,  # 招标单位与企业名称保持一致
                    "agent": agent_unit,
                    "budget": tender_budget,
                    "tenderEndTime": bidding_deadline,
                    "registrationEndTime": registration_deadline,
                    "briefText": content_preview,
                    "hasAnnex": has_attachment,
                    "detail_txt": "",
                    "detail_summary": "",
                    "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "source": "千里马网"
                }
                
                tender_data.append(data)
                logging.info(f"提取第 {i+1} 个项目: {title[:50]}...")
                
            except Exception as e:
                logging.warning(f"提取第 {i+1} 个项目数据失败: {e}")
                continue
        
        logging.info(f"成功提取 {len(tender_data)} 个招标项目数据")
        return tender_data
        
    except Exception as e:
        logging.error(f"提取招标数据失败: {e}")
        return []


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
                
                # 搜索该企业的招标信息（已在函数内部完成保存）
                saved_count = search_company_tenders(driver, company_name, industry, db)
                
                total_notices += saved_count
                logging.info(f"企业 {company_name} 处理完成，成功保存 {saved_count} 条招标公告")
                
                # 随机延迟，避免请求过于频繁
                time.sleep(random.uniform(3, 6))
                
            except Exception as e:
                logging.error(f"处理企业 {company_name} 时出现错误: {e}")
                continue
        
        logging.info(f"爬取完成！共处理 {processed_companies} 家企业，保存 {total_notices} 条招标公告")

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


def get_detail_page_content(driver, link, original_window, page_num=None, item_num=None):
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

            if page_num and item_num:
                logging.info(f"正在访问第 {page_num} 页第 {item_num} 条详情页")
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





if __name__ == '__main__':
    main()