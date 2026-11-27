import time
import random
import math
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc
from pymongo import MongoClient
import logging
from datetime import datetime
import ssl
import urllib3
from webdriver_manager.chrome import ChromeDriverManager

# 禁用SSL警告和验证
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/main_spider.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class LegalCebpubserviceSpider:
    def __init__(self):
        self.driver = None
        self.db = None
        self.collection = None
        self.base_url = "https://bulletin.cebpubservice.com/"
        self.backup_url = "https://www.cebpubservice.com/"
        
        # iframe位置缓存 - 基于日志分析优化定位效率
        self.iframe_cache = {
            'industry_selection': 'main_page',  # 行业选择在主页面
            'next_page_button': 1,  # 下一页按钮在iframe[1]
            'data_table': 1  # 数据表格在iframe[1]
        }
        
        # 行业列表
        self.industries = [
            "能源电力", "公路", "房屋建筑", "化学工业", 
            "石油石化", "铁路", "园林绿化", "生物医药",
            "水利水电", "水运", "港口航道", "纺织轻工",
            "矿产冶金", "民航", "生态环保", "地球科学",
            "信息电子", "市政", "广电通信", "科教文卫",
            "商业服务", "农林牧渔", "保险金融",
            "机械设备", "航空航天", "其他"
        ]
        
        # 反爬验证相关选择器
        self.verification_selectors = [
            "div[class*='verify']",
            "div[class*='captcha']",
            "div[class*='slider']",
            "div[id*='verify']",
            "div[id*='captcha']",
            "div[id*='slider']",
            ".verification-container",
            ".captcha-container",
            ".slider-container",
            "div[class*='访问验证']",
            "div[class*='access']",
            "div[class*='challenge']",
            "iframe[src*='captcha']",
            "iframe[src*='verify']"
        ]
        
        # 滑块相关选择器（优先使用确定的选择器）
        self.slider_selectors = [
            "div[id*='slider']",  # 该网站确定的滑块选择器，优先匹配
            "div[class*='slider-handle']",
            "div[class*='slide-handle']",
            "div[class*='drag-handle']",
            "span[class*='slider-handle']",
            "span[class*='slide-handle']",
            "span[class*='drag-handle']",
            ".slider-handle",
            ".slide-handle",
            ".drag-handle",
            "div[class*='slider-btn']",
            "div[class*='slide-btn']",
            "button[class*='slider']",
            "button[class*='slide']",
            "div[role='slider']"
        ]
        
        # 请求头配置
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
    def setup_driver(self):
        """初始化Chrome浏览器驱动"""
        try:
            # 使用undetected_chromedriver，它自动处理大部分反检测
            options = uc.ChromeOptions()
            
            # 只保留必要的选项，避免可疑参数
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument(f'--user-agent={self.headers["User-Agent"]}')
            
            # 添加SSL和网络相关配置来解决连接问题
            options.add_argument('--ignore-ssl-errors')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--ignore-certificate-errors-spki-list')
            options.add_argument('--disable-web-security')
            options.add_argument('--allow-running-insecure-content')
            options.add_argument('--disable-extensions')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            # 设置一些基本的偏好设置
            options.add_experimental_option('prefs', {
                'profile.default_content_setting_values': {
                    'notifications': 2,  # 阻止通知
                }
            })
            
            # 使用undetected_chromedriver创建驱动，添加重试机制
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    logger.info(f"🔄 尝试初始化Chrome驱动 (第 {attempt + 1} 次)")
                    # 每次重试都创建新的options对象，避免重用问题
                    if attempt > 0:
                        options = uc.ChromeOptions()
                        options.add_argument('--window-size=1920,1080')
                        options.add_argument('--start-maximized')
                        options.add_argument(f'--user-agent={self.headers["User-Agent"]}')
                        options.add_argument('--ignore-ssl-errors')
                        options.add_argument('--ignore-certificate-errors')
                        options.add_argument('--ignore-certificate-errors-spki-list')
                        options.add_argument('--disable-web-security')
                        options.add_argument('--allow-running-insecure-content')
                        options.add_argument('--disable-extensions')
                        options.add_argument('--no-sandbox')
                        options.add_argument('--disable-dev-shm-usage')
                        options.add_experimental_option('prefs', {
                            'profile.default_content_setting_values': {
                                'notifications': 2,
                            }
                        })
                    
                    driver_path = ChromeDriverManager().install()
                    self.driver = uc.Chrome(
                        options=options,
                        version_main=None,  # 自动适配Chrome版本
                        driver_executable_path=driver_path,  # 使用webdriver-manager管理的驱动
                        browser_executable_path=None,  # 使用系统Chrome
                        user_data_dir=None,  # 使用临时用户数据目录
                        headless=True,  # 关闭浏览器界面显示
                        use_subprocess=True,  # 使用子进程
                        debug=False
                    )
                    break
                except Exception as retry_error:
                    logger.warning(f"⚠️ 第 {attempt + 1} 次初始化失败: {retry_error}")
                    if attempt == max_retries - 1:
                        raise retry_error
                    time.sleep(2)  # 等待2秒后重试
            
            # 设置页面加载超时
            self.driver.set_page_load_timeout(30)
            self.driver.implicitly_wait(10)
            
            logger.info("✅ Chrome浏览器驱动初始化成功 (使用undetected-chromedriver)")
            return True
        except Exception as e:
            logger.error(f"❌ 浏览器驱动初始化失败: {e}")
            logger.info("💡 建议检查网络连接或尝试使用VPN")
            return False
    
    def setup_database(self):
        """初始化MongoDB数据库连接"""
        try:
            self.client = MongoClient('mongodb://localhost:27017/')
            self.db = self.client['qianlima']
            self.collection = self.db['tender_data']
            
            # 测试连接
            self.client.admin.command('ping')
            logger.info("✅ MongoDB数据库连接成功")
            return True
        except Exception as e:
            logger.error(f"❌ 数据库连接失败: {e}")
            return False
    
    def random_delay(self, min_seconds=1, max_seconds=3):
        """随机延迟，模拟人类行为"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def check_for_verification(self, quick_mode=False):
        """验证检测 - 检查是否出现反爬验证"""
        try:
            if quick_mode:
                return self._quick_verification_check()
            else:
                logger.info("🔍 检查页面验证...")
                return self._full_verification_check()
            
        except Exception as e:
            logger.warning(f"⚠️ 验证检查失败: {e}")
            return False
    
    def check_for_complete_verification(self):
        """完整验证检测 - 同时检测captcha和滑块，只有两者都存在才返回True"""
        try:
            logger.info("🔍 检测验证码和滑块是否同时存在...")
            
            # 1. 检测captcha关键词
            captcha_detected = False
            try:
                page_source = self.driver.page_source.lower()
                if 'captcha' in page_source:
                    logger.info("✅ 检测到captcha关键词")
                    captcha_detected = True
            except:
                pass
            
            # 2. 快速检测滑块元素（3秒内完成）
            slider_detected = False
            try:
                import time
                start_time = time.time()
                self.driver.implicitly_wait(0.3)  # 极速检测
                
                # 检测主页面滑块（优先检测最常见的选择器）
                priority_selectors = [
                    "div[id*='aliyunCaptcha']",
                    "div[class*='nc_']",
                    "div[id*='slider']"
                ]
                
                for selector in priority_selectors:
                    if time.time() - start_time > 1.0:  # 主页面检测超过1秒就跳出
                        break
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements and any(el.is_displayed() for el in elements):
                        logger.info(f"✅ 主页面检测到滑块: {selector}")
                        slider_detected = True
                        break
                
                # 如果主页面没有找到且时间允许，快速检测iframe（最多2秒）
                if not slider_detected and time.time() - start_time < 2.0:
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    for i, iframe in enumerate(iframes[:2]):  # 只检查前2个iframe
                        if time.time() - start_time > 2.5:  # 总时间超过2.5秒就停止
                            break
                        if iframe.is_displayed():
                            try:
                                self.driver.switch_to.frame(iframe)
                                # 只检测最常见的阿里云选择器
                                for selector in priority_selectors[:2]:
                                    if time.time() - start_time > 2.8:  # 接近3秒限制
                                        break
                                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                    if elements and any(el.is_displayed() for el in elements):
                                        logger.info(f"✅ iframe {i+1} 检测到滑块: {selector}")
                                        slider_detected = True
                                        break
                                self.driver.switch_to.default_content()
                                if slider_detected:
                                    break
                            except:
                                try:
                                    self.driver.switch_to.default_content()
                                except:
                                    pass
                                continue
                
                # 记录检测耗时
                detection_time = time.time() - start_time
                logger.info(f"⏱️ 滑块检测耗时: {detection_time:.2f}秒")
                
                self.driver.implicitly_wait(10)  # 恢复默认超时
            except:
                try:
                    self.driver.implicitly_wait(10)  # 确保恢复默认超时
                except:
                    pass
            
            # 3. 判断结果
            if captcha_detected and slider_detected:
                logger.info("🎯 同时检测到captcha和滑块，需要进行验证处理")
                return True
            elif captcha_detected and not slider_detected:
                logger.info("ℹ️ 检测到captcha但未发现滑块，跳过验证处理")
                return False
            elif not captcha_detected and slider_detected:
                logger.info("ℹ️ 检测到滑块但未发现captcha，跳过验证处理")
                return False
            else:
                logger.info("✅ 未检测到验证元素，直接进行数据爬取")
                return False
            
        except Exception as e:
            logger.warning(f"⚠️ 完整验证检测失败: {e}")
            return False
    
    def _quick_verification_check(self):
        """快速验证检测 - 仅检测最常见的验证元素"""
        try:
            # 设置短超时，快速检测
            self.driver.implicitly_wait(1)
            
            # 优先检测阿里云验证（最常见）
            aliyun_selectors = [
                "div[id*='aliyunCaptcha']",
                "div[class*='aliyunCaptcha']",
                "div[id*='nc_']",
                "div[class*='nc_']"
            ]
            
            for selector in aliyun_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements and any(el.is_displayed() for el in elements):
                    logger.info(f"🔍 快速检测到阿里云验证: {selector}")
                    return True
            
            # 检测iframe中的验证
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes[:3]:  # 只检查前3个iframe
                if iframe.is_displayed():
                    iframe_src = iframe.get_attribute("src") or ""
                    iframe_id = iframe.get_attribute("id") or ""
                    if any(keyword in f"{iframe_src} {iframe_id}".lower() for keyword in ['captcha', 'aliyun', 'nc_']):
                        logger.info(f"🔍 快速检测到验证iframe: {iframe_id}")
                        return True
            
            # 快速关键词检测（仅检测最明显的）
            page_source = self.driver.page_source.lower()
            quick_keywords = ['aliyuncaptcha', 'nc_wrapper', '请完成验证', '拖动滑块']
            for keyword in quick_keywords:
                if keyword in page_source:
                    logger.info(f"🔍 快速检测到验证关键词: {keyword}")
                    return True
            
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ 快速验证检查失败: {e}")
            return False
        finally:
            self.driver.implicitly_wait(10)  # 恢复默认超时
    
    def _full_verification_check(self):
        """完整验证检测 - 优化版本，直接定位验证元素"""
        try:
            # 1. 快速检测页面源码中的captcha关键词（根据日志优化）
            try:
                page_source = self.driver.page_source.lower()
                if 'captcha' in page_source:
                    logger.info(f"🔍 页面源码检测到验证关键词: captcha")
                    return True
            except:
                pass
            
            # 2. 直接定位阿里云滑块按钮（根据日志优化）
            try:
                # 根据日志经验，直接查找阿里云滑块选择器
                aliyun_slider_selectors = [
                    "div[id*='slider']",  # 根据日志: div[id*='slider']
                    "div[class*='slider']",
                    "div[id*='aliyunCaptcha']",
                    "div[class*='aliyunCaptcha']",
                    "div[class*='nc_']",
                    "div[id*='nc_']"
                ]
                
                self.driver.implicitly_wait(1)  # 快速检测
                for selector in aliyun_slider_selectors:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements and any(el.is_displayed() for el in elements):
                        logger.info(f"🔍 直接检测到阿里云滑块: {selector}")
                        self.driver.implicitly_wait(10)  # 恢复默认超时
                        return True
                        
                self.driver.implicitly_wait(10)  # 恢复默认超时
            except:
                self.driver.implicitly_wait(10)  # 确保恢复默认超时
                pass
            
            # 3. 检查验证相关iframe（简化版本）
            try:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    if iframe.is_displayed():
                        iframe_info = f"{iframe.get_attribute('src') or ''} {iframe.get_attribute('id') or ''}".lower()
                        if any(keyword in iframe_info for keyword in ['captcha', 'aliyun', 'nc_']):
                            logger.info(f"🔍 检测到验证iframe")
                            return True
            except:
                pass
            
            # 4. 检查页面标题（保留作为备用）
            try:
                title = self.driver.title.lower()
                if any(keyword in title for keyword in ['验证', 'verify', 'captcha']):
                    logger.info(f"🔍 页面标题检测到验证: {title}")
                    return True
            except:
                pass
            
            logger.info("✅ 未检测到验证元素")
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ 完整验证检查失败: {e}")
            return False
    
    def handle_slider_verification(self, max_retries=3):
        """处理滑块验证 - 增强版本，包含验证失败检测和重试机制"""
        try:
            logger.info("🔧 开始处理滑动验证...")
            
            # 保存验证页面截图
            try:
                self.driver.save_screenshot("slider_verification.png")
                logger.info("📸 已保存滑动验证截图: slider_verification.png")
            except Exception:
                pass
            
            for attempt in range(max_retries):
                logger.info(f"🔄 第 {attempt + 1} 次尝试处理滑动验证")
                
                # 优先策略: 直接定位并处理阿里云滑块（根据日志优化）
                if self.handle_direct_aliyun_slider():
                    logger.info("✅ 滑块拖动完成，检测验证结果...")
                    if self.verify_slider_success():
                        logger.info("✅ 滑块验证成功")
                        return True
                    else:
                        logger.warning("⚠️ 阿里云滑块验证失败，尝试刷新验证码重试")
                        if self.refresh_verification_and_retry():
                            logger.info("🔄 验证码已刷新，准备重新拖动")
                            continue
                
                # 备用策略: 聚焦iframe处理
                if self.find_and_handle_slider_focused():
                    logger.info("✅ 滑块拖动完成，检测验证结果...")
                    if self.verify_slider_success():
                        logger.info("✅ 滑块验证成功")
                        return True
                    else:
                        logger.warning("⚠️ 聚焦iframe滑块验证失败，尝试刷新验证码重试")
                        if self.refresh_verification_and_retry():
                            logger.info("🔄 验证码已刷新，准备重新拖动")
                            continue
                
                # 最后策略: 标准拖拽
                if self.perform_standard_slider_drag():
                    logger.info("✅ 滑块拖动完成，检测验证结果...")
                    if self.verify_slider_success():
                        logger.info("✅ 滑块验证成功")
                        return True
                    else:
                        logger.warning("⚠️ 标准拖拽滑块验证失败，尝试刷新验证码重试")
                        if self.refresh_verification_and_retry():
                            logger.info("🔄 验证码已刷新，准备重新拖动")
                            continue
                
                logger.warning(f"⚠️ 第 {attempt + 1} 次尝试失败，等待后重试")
                self.random_delay(2, 3)
                
                # 刷新页面重试
                if attempt < max_retries - 1:
                    self.driver.refresh()
                    self.random_delay(3, 5)
            
            logger.error("❌ 所有滑动验证尝试都失败了")
            return False
            
        except Exception as e:
            logger.error(f"❌ 处理滑动验证失败: {e}")
            return False
    
    def verify_slider_success(self, timeout=10):
        """验证滑块拖动是否成功 - 通过检测表格是否加载和验证失败文字"""
        try:
            logger.info("🔍 检测滑块验证结果...")
            
            # 等待验证结果
            self.random_delay(3, 5)
            
            # 1. 检测页面是否有验证失败的文字
            try:
                page_source = self.driver.page_source
                failure_keywords = ['验证失败', '验证错误', '请重新验证', '验证超时', '验证码错误', '拖动失败']
                for keyword in failure_keywords:
                    if keyword in page_source:
                        logger.warning(f"⚠️ 检测到验证失败关键词: {keyword}")
                        return False
            except Exception:
                pass
            
            # 2. 检测表格是否成功加载
            try:
                # 使用智能切换到数据表格所在的iframe
                if self.smart_switch_to_iframe('data_table'):
                    tables = self.driver.find_elements(By.TAG_NAME, "table")
                    if tables:
                        # 检查表格是否有数据行
                        table = tables[0]
                        rows = table.find_elements(By.TAG_NAME, "tr")
                        if len(rows) > 1:  # 有表头和数据行
                            logger.info("✅ 检测到表格数据，验证成功")
                            self.driver.switch_to.default_content()
                            return True
                        else:
                            logger.warning("⚠️ 表格无数据行，验证可能失败")
                    else:
                        logger.warning("⚠️ 未找到表格，验证可能失败")
                    self.driver.switch_to.default_content()
                else:
                    logger.warning("⚠️ 无法切换到数据表格iframe")
            except Exception as e:
                logger.debug(f"表格检测失败: {e}")
                try:
                    self.driver.switch_to.default_content()
                except:
                    pass
            
            # 3. 检测是否还有验证码元素存在
            try:
                if self.check_for_complete_verification():
                    logger.warning("⚠️ 仍检测到验证码元素，验证可能失败")
                    return False
            except Exception:
                pass
            
            # 如果没有明确的失败标志，认为验证成功
            logger.info("✅ 未检测到验证失败标志，认为验证成功")
            return True
            
        except Exception as e:
            logger.error(f"❌ 验证结果检测失败: {e}")
            return False
    
    def refresh_verification_and_retry(self):
        """刷新验证码并准备重试"""
        try:
            logger.info("🔄 尝试刷新验证码...")
            
            # 查找刷新按钮的选择器
            refresh_selectors = [
                "div[class*='refresh']",
                "button[class*='refresh']",
                "span[class*='refresh']",
                "div[class*='reload']",
                "button[class*='reload']",
                "div[title*='刷新']",
                "button[title*='刷新']",
                "div[title*='重新']",
                "button[title*='重新']",
                "div[onclick*='refresh']",
                "div[onclick*='reload']",
                "i[class*='refresh']",
                "i[class*='reload']"
            ]
            
            # 首先在主页面查找刷新按钮
            refresh_button = None
            for selector in refresh_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed():
                            refresh_button = element
                            logger.info(f"🔄 在主页面找到刷新按钮: {selector}")
                            break
                    if refresh_button:
                        break
                except Exception:
                    continue
            
            # 如果主页面没找到，在iframe中查找
            if not refresh_button:
                try:
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    for i, iframe in enumerate(iframes[:3]):  # 只检查前3个iframe
                        if iframe.is_displayed():
                            try:
                                self.driver.switch_to.frame(iframe)
                                for selector in refresh_selectors:
                                    try:
                                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                        for element in elements:
                                            if element.is_displayed():
                                                refresh_button = element
                                                logger.info(f"🔄 在iframe {i+1}找到刷新按钮: {selector}")
                                                break
                                        if refresh_button:
                                            break
                                    except Exception:
                                        continue
                                if refresh_button:
                                    break
                                self.driver.switch_to.default_content()
                            except Exception:
                                try:
                                    self.driver.switch_to.default_content()
                                except:
                                    pass
                                continue
                        if refresh_button:
                            break
                except Exception:
                    try:
                        self.driver.switch_to.default_content()
                    except:
                        pass
            
            # 点击刷新按钮
            if refresh_button:
                try:
                    self.driver.execute_script("arguments[0].click();", refresh_button)
                    logger.info("✅ 成功点击刷新按钮")
                    self.random_delay(2, 3)
                    try:
                        self.driver.switch_to.default_content()
                    except:
                        pass
                    return True
                except Exception as e:
                    logger.warning(f"⚠️ 点击刷新按钮失败: {e}")
                    try:
                        self.driver.switch_to.default_content()
                    except:
                        pass
            else:
                logger.warning("⚠️ 未找到刷新按钮，使用页面刷新")
                self.driver.refresh()
                self.random_delay(3, 5)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 刷新验证码失败: {e}")
            try:
                self.driver.switch_to.default_content()
            except:
                pass
            return False
    
    def handle_direct_aliyun_slider(self):
        """超级优化版本 - 直接使用已知选择器快速定位并拖拽"""
        try:
            logger.info("🎯 开始超快速定位阿里云滑块...")
            
            # 使用已知的精确选择器
            target_selector = "div[id*='slider']"
            
            # 首先在主页面快速检查
            self.driver.implicitly_wait(1)
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, target_selector)
                for element in elements:
                    if element.is_displayed():
                        logger.info(f"🎯 在主页面找到滑块: {target_selector}")
                        return self._quick_drag_slider(element)
            finally:
                self.driver.implicitly_wait(10)
            
            # 直接检查iframe 2（根据经验最可能的位置）
            try:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                if len(iframes) >= 2:
                    iframe = iframes[1]  # iframe 2
                    if iframe.is_displayed():
                        try:
                            self.driver.switch_to.frame(iframe)
                            logger.info("🎯 直接检查iframe 2")
                            
                            elements = self.driver.find_elements(By.CSS_SELECTOR, target_selector)
                            for element in elements:
                                if element.is_displayed():
                                    logger.info(f"🎯 在iframe 2找到滑块: {target_selector}")
                                    result = self._quick_drag_slider(element)
                                    self.driver.switch_to.default_content()
                                    return result
                            
                            self.driver.switch_to.default_content()
                        except Exception as e:
                            logger.debug(f"iframe 2处理失败: {e}")
                            try:
                                self.driver.switch_to.default_content()
                            except:
                                pass
            except Exception as e:
                logger.debug(f"iframe处理失败: {e}")
                try:
                    self.driver.switch_to.default_content()
                except:
                    pass
            
            logger.info("🎯 未找到目标滑块")
            return False
            
        except Exception as e:
            logger.error(f"❌ 快速滑块处理失败: {e}")
            try:
                self.driver.switch_to.default_content()
            except:
                pass
            return False
    
    def _quick_drag_slider(self, slider_element):
        """快速拖拽滑块 - 简化版本，立即执行拖拽"""
        try:
            logger.info("🚀 立即执行滑块拖拽")
            
            # 获取滑块容器尺寸
            container = slider_element.find_element(By.XPATH, "./ancestor::*[contains(@class, 'slider') or contains(@id, 'slider')][1]")
            container_width = container.size['width']
            
            # 计算拖拽距离（容器宽度的80%）
            drag_distance = int(container_width * 0.8)
            
            logger.info(f"📦 容器宽度: {container_width}px, 拖拽距离: {drag_distance}px")
            
            # 立即执行拖拽
            actions = ActionChains(self.driver)
            actions.click_and_hold(slider_element)
            actions.move_by_offset(drag_distance, 0)
            actions.release()
            actions.perform()
            
            logger.info("✅ 快速拖拽完成")
            time.sleep(2)  # 等待验证结果
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 快速拖拽失败: {e}")
            # 备用方案：使用标准拖拽
            try:
                logger.info("🔄 使用备用拖拽方案")
                return self.perform_aliyun_slider_drag(slider_element)
            except:
                return False
    
    def find_and_handle_slider_focused(self):
        """聚焦查找并处理滑块元素 - 优化版本"""
        try:
            logger.info("🎯 开始聚焦滑块检测和处理...")
            
            # 快速检测阿里云验证码元素
            aliyun_selectors = [
                "div[id*='aliyunCaptcha']",
                "div[class*='aliyunCaptcha']",
                "div[id='aliyunCaptcha-sliding-body']",
                "div[class='sliding']",
                "div[class='slider-move']"
            ]
            
            # 首先在主页面快速检测
            for selector in aliyun_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                         logger.info(f"🎯 在主页面发现阿里云验证码: {selector}")
                         elem_info_list = []
                         for elem in elements:
                             if elem.is_displayed():
                                 elem_info_list.append({
                                     'element': elem,
                                     'selector': selector,
                                     'id': elem.get_attribute('id') or '',
                                     'class': elem.get_attribute('class') or ''
                                 })
                         if elem_info_list and self.handle_aliyun_captcha_elements(elem_info_list):
                             return True
                except Exception:
                    continue
            
            # 智能定位iframe中的验证码 - 直接定位优化版本
            try:
                # 设置短超时时间进行快速检测
                original_timeout = self.driver.implicitly_wait(0)
                
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                logger.info(f"🔍 发现 {len(iframes)} 个iframe，开始智能定位")
                
                # 直接定位策略：根据日志经验优化
                target_iframes = []
                
                # 1. 优先检查第2个iframe（根据日志经验，阿里云验证码通常在iframe2中）
                if len(iframes) >= 2:
                    logger.info("🎯 根据经验优先检查第2个iframe")
                    target_iframes.append((1, iframes[1]))
                
                # 2. 检查包含阿里云关键词的iframe
                for i, iframe in enumerate(iframes):
                    if i == 1:  # 跳过已添加的第2个iframe
                        continue
                    try:
                        if iframe.is_displayed():
                            iframe_src = iframe.get_attribute("src") or ""
                            iframe_id = iframe.get_attribute("id") or ""
                            iframe_class = iframe.get_attribute("class") or ""
                            iframe_info = f"{iframe_src} {iframe_id} {iframe_class}".lower()
                            
                            # 检查iframe属性是否包含验证码相关关键词
                            if any(keyword in iframe_info for keyword in ['captcha', 'aliyun', 'nc_', 'verify']):
                                logger.info(f"🎯 发现阿里云关键词iframe {i+1}")
                                target_iframes.insert(0, (i, iframe))  # 插入到最前面
                                break
                    except Exception:
                        continue
                
                # 3. 如果还没找到足够的iframe，添加第1个iframe
                if len(target_iframes) < 2 and len(iframes) >= 1:
                    if 0 not in [idx for idx, _ in target_iframes]:
                        target_iframes.append((0, iframes[0]))
                
                # 按优先级处理iframe（最多检查2个）
                for i, iframe in target_iframes[:2]:
                    try:
                        logger.info(f"🎯 快速检测iframe {i+1}")
                        
                        # 设置0.5秒超时限制进行极速检测
                        import time
                        start_time = time.time()
                        
                        try:
                            self.driver.switch_to.frame(iframe)
                            
                            # 在iframe中极速检测阿里云验证码
                            for selector in aliyun_selectors[:3]:  # 只检查前3个最常见的选择器
                                # 检查是否超时
                                if time.time() - start_time > 0.5:
                                    logger.warning(f"⚠️ iframe {i+1} 检测超时(0.5s)，跳过")
                                    break
                                    
                                try:
                                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                    if elements:
                                         logger.info(f"✅ 在iframe {i+1} 中发现阿里云验证码: {selector}")
                                         elem_info_list = []
                                         for elem in elements:
                                             if elem.is_displayed():
                                                 elem_info_list.append({
                                                     'element': elem,
                                                     'selector': selector,
                                                     'id': elem.get_attribute('id') or '',
                                                     'class': elem.get_attribute('class') or ''
                                                 })
                                         if elem_info_list and self.handle_aliyun_captcha_elements(elem_info_list):
                                             self.driver.switch_to.default_content()
                                             self.driver.implicitly_wait(10)  # 恢复原超时
                                             return True
                                except Exception:
                                    continue
                            
                            self.driver.switch_to.default_content()
                            
                        except Exception as iframe_error:
                            logger.debug(f"iframe {i+1} 处理失败: {iframe_error}")
                            try:
                                self.driver.switch_to.default_content()
                            except:
                                pass
                            
                    except Exception as e:
                        logger.debug(f"处理iframe {i+1} 失败: {e}")
                        try:
                            self.driver.switch_to.default_content()
                        except:
                            pass
                        
                # 恢复原超时设置
                self.driver.implicitly_wait(10)
                
            except Exception as e:
                logger.warning(f"iframe检测失败: {e}")
                # 确保恢复原超时设置
                try:
                    self.driver.implicitly_wait(10)
                except:
                    pass
            
            # 如果没有找到阿里云验证码，尝试通用滑块检测
            logger.info("🔍 未发现阿里云验证码，尝试通用滑块检测")
            return self._find_slider_in_context()
            
        except Exception as e:
            logger.error(f"❌ 聚焦滑块检测失败: {e}")
            return False
    
    def find_and_handle_slider(self):
        """查找并处理滑块元素"""
        try:
            # 打印页面HTML结构用于调试
            try:
                page_source = self.driver.page_source
                logger.info(f"📄 验证页面HTML长度: {len(page_source)}")
                # 查找包含slider、captcha等关键词的HTML片段
                import re
                slider_patterns = re.findall(r'<[^>]*(?:slider|captcha|verify|drag)[^>]*>', page_source, re.IGNORECASE)
                for i, pattern in enumerate(slider_patterns[:5]):
                    logger.info(f"🔍 滑块相关HTML {i+1}: {pattern}")
            except Exception:
                pass
            
            # 首先在主页面中查找
            if self._find_slider_in_context():
                return True
            
            # 然后在所有iframe中查找
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            logger.info(f"🔍 发现 {len(iframes)} 个iframe")
            
            for i, iframe in enumerate(iframes):
                try:
                    if iframe.is_displayed():
                        logger.info(f"🔍 检查iframe {i+1}")
                        self.driver.switch_to.frame(iframe)
                        
                        # 在iframe中查找滑块
                        if self._find_slider_in_context():
                            self.driver.switch_to.default_content()
                            return True
                        
                        self.driver.switch_to.default_content()
                except Exception as e:
                    logger.debug(f"处理iframe {i+1} 失败: {e}")
                    try:
                        self.driver.switch_to.default_content()
                    except:
                        pass
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 查找滑块失败: {e}")
            return False
    
    def _find_slider_in_context(self):
        """在当前上下文中查找滑块元素"""
        try:
            # 扩展的滑块选择器 - 基于阿里云验证码结构
            extended_slider_selectors = [
                # 阿里云验证码特定选择器
                "div[id*='aliyunCaptcha']",
                "div[class*='aliyunCaptcha']",
                "div[id='aliyunCaptcha-sliding-body']",
                "div[class='sliding']",
                "div[id*='aliyunCaptcha-sliding']",
                "div[class*='aliyunCaptcha-sliding']",
                "div[id='aliyunCaptcha-sliding-slider']",
                "div[class='slider-move']",
                "div[class*='slider-move']",
                "div[id*='slider-move']",
                "div[class='width-change']",
                "div[class*='width-change']",
                "div[id*='width-change']",
                # 常见滑块验证码选择器
                "div[class*='slider']",
                "div[class*='slide']",
                "div[class*='captcha']",
                "div[class*='verify']",
                "div[class*='drag']",
                "span[class*='slider']",
                "button[class*='slider']",
                "div[class*='handle']",
                "div[class*='thumb']",
                "div[class*='knob']",
                "div[class*='btn']",
                # ID选择器
                "div[id*='slider']",
                "div[id*='captcha']",
                "div[id*='verify']",
                "div[id*='drag']",
                # 通用选择器
                "[role='slider']",
                "input[type='range']",
                "canvas",
                # 可能的滑块容器
                "div[style*='cursor']",
                "div[draggable='true']",
                # 橙色按钮（基于截图中的橙色滑块）
                "div[style*='background'][style*='orange']",
                "div[style*='background'][style*='#ff']",
                "button[style*='background']"
            ]
            
            all_selectors = self.slider_selectors + extended_slider_selectors
            
            # 首先尝试查找所有可能的滑块元素
            found_elements = []
            for selector in all_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed():
                            try:
                                location = element.location
                                size = element.size
                                tag_name = element.tag_name
                                class_name = element.get_attribute('class') or ''
                                id_attr = element.get_attribute('id') or ''
                                style = element.get_attribute('style') or ''
                                
                                found_elements.append({
                                    'element': element,
                                    'selector': selector,
                                    'location': location,
                                    'size': size,
                                    'tag': tag_name,
                                    'class': class_name,
                                    'id': id_attr,
                                    'style': style[:100]  # 只取前100字符
                                })
                                
                                logger.debug(f"🎯 找到元素: {selector} | 标签:{tag_name} | 位置:{location} | 大小:{size} | 类名:{class_name[:50]}")
                            except Exception:
                                pass
                                
                except Exception as e:
                    logger.debug(f"选择器 {selector} 失败: {e}")
                    continue
            
            logger.debug(f"📊 总共找到 {len(found_elements)} 个可能的滑块元素")
            
            # 优先处理阿里云验证码
            aliyun_elements = []
            other_elements = []
            
            for elem_info in found_elements:
                element_id = elem_info['id']
                element_class = elem_info['class']
                if 'aliyun' in element_id.lower() or 'aliyun' in element_class.lower():
                    aliyun_elements.append(elem_info)
                else:
                    other_elements.append(elem_info)
            
            # 首先尝试处理阿里云验证码
            if aliyun_elements:
                logger.info(f"发现阿里云验证码元素: {len(aliyun_elements)}个")
                if self.handle_aliyun_captcha_elements(aliyun_elements):
                    return True
            
            # 然后处理其他元素
            for elem_info in other_elements:
                element = elem_info['element']
                selector = elem_info['selector']
                
                try:
                    logger.info(f"🔧 尝试处理元素: {selector}")
                    
                    # 尝试不同的拖拽方式
                    if self.drag_slider_element(element):
                        logger.info(f"✅ 元素 {selector} 拖拽成功")
                        return True
                    
                    # 如果是canvas，尝试特殊处理
                    if element.tag_name == 'canvas':
                        if self.handle_canvas_slider(element):
                            logger.info(f"✅ Canvas {selector} 处理成功")
                            return True
                    
                    # 尝试点击元素
                    if self.safe_click(element):
                        logger.info(f"✅ 元素 {selector} 点击成功")
                        self.random_delay(1, 2)
                        if not self.check_for_verification():
                            return True
                            
                except Exception as e:
                    logger.debug(f"处理元素 {selector} 失败: {e}")
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 查找滑块失败: {e}")
            return False
    
    def drag_slider_element(self, element):
        """拖拽滑块元素"""
        try:
            # 获取元素位置和大小
            location = element.location
            size = element.size
            
            logger.info(f"📍 滑块位置: {location}, 大小: {size}")
            
            # 获取窗口宽度，不设置边界限制，直接拖拽到屏幕最右侧
            window_width = self.driver.get_window_size()['width']
            drag_distance = window_width - 40  # 留40px避免完全贴边
            
            try:
                # 方法1: 一次性快速拖拽到屏幕最右侧
                actions = ActionChains(self.driver)
                actions.click_and_hold(element)
                jitter_x = random.randint(-15, 15)
                jitter_y = random.randint(-2, 2)
                actions.move_by_offset(drag_distance + jitter_x, jitter_y)
                actions.release()
                actions.perform()
                
                logger.info(f"✅ 快速拖拽完成，距离: {drag_distance}px")
                self.random_delay(1, 2)
                
                # 检查是否成功
                if not self.check_for_verification():
                    logger.info("✅ 快速拖拽验证成功")
                    return True
                
                # 方法2: 如果第一次失败，尝试更大的拖拽距离
                larger_distance = window_width - 20  # 更接近屏幕边缘
                actions = ActionChains(self.driver)
                actions.click_and_hold(element)
                jitter_x = random.randint(-20, 20)
                actions.move_by_offset(larger_distance + jitter_x, 0)
                actions.release()
                actions.perform()
                
                logger.info(f"✅ 大距离拖拽完成，距离: {larger_distance}px")
                self.random_delay(1, 2)
                
                if not self.check_for_verification():
                    logger.info("✅ 大距离拖拽验证成功")
                    return True
                        
            except Exception as e:
                 logger.debug(f"拖拽失败: {e}")
                 return False
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 拖拽滑块元素失败: {e}")
            return False
    
    def handle_aliyun_captcha_elements(self, aliyun_elements):
        """专门处理阿里云验证码元素列表"""
        try:
            logger.info("🔧 开始处理阿里云验证码")
            
            for elem_info in aliyun_elements:
                element = elem_info['element']
                element_id = elem_info['id']
                element_class = elem_info['class']
                
                logger.info(f"处理阿里云元素: id={element_id}, class={element_class}")
                
                if self.handle_aliyun_captcha(element):
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 处理阿里云验证码失败: {e}")
            return False
    
    def handle_aliyun_captcha(self, element):
        """专门处理单个阿里云验证码元素"""
        try:
            logger.info("🎯 处理阿里云验证码元素")
            
            # 查找滑块按钮
            slider_button = None
            try:
                # 在阿里云验证码容器内查找滑块按钮
                slider_selectors = [
                    "div[class*='slider-move']",
                    "div[class*='width-change']", 
                    "div[id*='slider']",
                    "div[style*='background']",
                    "button",
                    "div[draggable='true']"
                ]
                
                for selector in slider_selectors:
                    buttons = element.find_elements(By.CSS_SELECTOR, selector)
                    for button in buttons:
                        if button.is_displayed():
                            slider_button = button
                            logger.info(f"找到阿里云滑块按钮: {selector}")
                            break
                    if slider_button:
                        break
                        
            except Exception:
                pass
            
            if slider_button:
                # 尝试拖拽滑块
                if self.perform_aliyun_slider_drag(slider_button):
                    return True
            else:
                # 如果没找到滑块按钮，尝试在整个容器上操作
                if self.perform_aliyun_container_drag(element):
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 处理阿里云验证码失败: {e}")
            return False
    
    def perform_aliyun_slider_drag(self, slider_button):
        """执行阿里云滑块拖拽 - 根据容器尺寸一次性拖拽"""
        try:
            logger.info("🎯 执行阿里云滑块拖拽 - 根据容器尺寸一次性拖拽")
            
            # 获取滑块容器的实际尺寸
            try:
                # 尝试找到滑块容器
                container = self.driver.find_element(By.CSS_SELECTOR, "div[id*='aliyunCaptcha-sliding-text-box']")
                container_size = container.size
                container_width = container_size['width']
                logger.info(f"📏 检测到滑块容器宽度: {container_width}px")
            except:
                # 如果找不到容器，使用滑块按钮的父容器
                try:
                    parent_container = slider_button.find_element(By.XPATH, "./ancestor::div[contains(@class, 'sliding') or contains(@id, 'sliding')]")
                    container_size = parent_container.size
                    container_width = container_size['width']
                    logger.info(f"📏 从父容器检测到宽度: {container_width}px")
                except:
                    # 使用默认值
                    container_width = 360
                    logger.info(f"📏 使用默认容器宽度: {container_width}px")
            
            # 计算拖拽距离 - 使用容器宽度减去小边距避免超出边界
            drag_distance = container_width - 20  # 减去20px边距避免超出边界
            logger.info(f"🎯 计算拖拽距离: {drag_distance}px (容器宽度:{container_width}px - 边距:20px)")
            
            # 执行一次性拖拽
            success = self._perform_aliyun_direct_drag(slider_button, drag_distance)
            
            if success:
                logger.info("✅ 阿里云滑块拖拽完成")
                # 短暂等待让验证结果生效
                self.random_delay(2, 3)
                logger.info("✅ 滑块拖拽成功，跳过验证检查直接进入下一阶段")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 阿里云滑块拖拽失败: {e}")
            return False
    
    def _perform_aliyun_direct_drag(self, slider_element, drag_distance):
        """执行阿里云滑块一次性拖拽"""
        try:
            logger.info(f"🎭 执行阿里云滑块一次性拖拽，距离: {drag_distance}px")
            
            # 使用单一的ActionChains完成整个拖拽序列
            actions = ActionChains(self.driver)
            
            # 移动到滑块中心，点击并保持，然后拖拽到目标位置，最后释放
            y_offset = random.uniform(-2, 2)  # 添加轻微的Y轴抖动模拟人手不稳
            
            actions.move_to_element(slider_element)\
                   .pause(random.uniform(0.1, 0.3))\
                   .click_and_hold(slider_element)\
                   .pause(random.uniform(0.1, 0.2))\
                   .move_by_offset(xoffset=drag_distance, yoffset=y_offset)\
                   .pause(random.uniform(0.2, 0.4))\
                   .release()\
                   .perform()
            
            logger.info("✅ 阿里云滑块一次性拖拽完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 阿里云滑块一次性拖拽失败: {e}")
            return False
    
    def perform_aliyun_container_drag(self, container):
        """在阿里云容器上执行拖拽 - 根据容器尺寸一次性拖拽"""
        try:
            logger.info("📦 在阿里云容器上执行拖拽 - 根据容器尺寸一次性拖拽")
            
            # 获取容器的实际尺寸
            container_size = container.size
            container_width = container_size['width']
            logger.info(f"📏 检测到容器宽度: {container_width}px")
            
            # 计算拖拽距离 - 使用容器宽度减去小边距避免超出边界
            drag_distance = container_width - 20  # 减去20px边距避免超出边界
            logger.info(f"🎯 计算拖拽距离: {drag_distance}px (容器宽度:{container_width}px - 边距:20px)")
            
            # 执行一次性容器拖拽
            success = self._perform_aliyun_container_direct_drag(container, drag_distance)
            
            if success:
                logger.info(f"✅ 阿里云容器拖拽完成，距离: {int(drag_distance)}px")
                self.random_delay(2, 3)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 阿里云容器拖拽失败: {e}")
            return False
    
    def _perform_aliyun_container_direct_drag(self, container, drag_distance):
        """执行阿里云容器一次性拖拽"""
        try:
            logger.info(f"🎭 执行阿里云容器一次性拖拽，距离: {drag_distance}px")
            
            # 使用单一的ActionChains完成整个拖拽序列
            actions = ActionChains(self.driver)
            
            # 移动到容器中心，点击并保持，然后拖拽到目标位置，最后释放
            y_offset = random.uniform(-2, 2)  # 添加轻微的Y轴抖动
            
            actions.move_to_element(container)\
                   .pause(random.uniform(0.1, 0.3))\
                   .click_and_hold(container)\
                   .pause(random.uniform(0.1, 0.2))\
                   .move_by_offset(xoffset=drag_distance, yoffset=y_offset)\
                   .pause(random.uniform(0.2, 0.4))\
                   .release()\
                   .perform()
            
            logger.info("✅ 阿里云容器一次性拖拽完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 阿里云容器一次性拖拽失败: {e}")
            return False
    
    def handle_canvas_slider(self, canvas):
        """处理canvas滑块"""
        try:
            logger.info("🎨 处理canvas滑块")
            
            # 获取canvas的位置和大小
            location = canvas.location
            size = canvas.size
            
            # 获取窗口宽度，不设置边界限制，直接拖拽到屏幕最右侧
            window_width = self.driver.get_window_size()['width']
            drag_distance = window_width - 70  # 留70px避免完全贴边
            
            # 在canvas上进行拖拽操作
            actions = ActionChains(self.driver)
            
            # 移动到canvas中心
            actions.move_to_element(canvas)
            
            # 按下鼠标
            actions.click_and_hold(canvas)
            
            # 一次性快速拖拽到屏幕最右侧
            jitter_x = random.randint(-12, 12)
            jitter_y = random.randint(-2, 2)
            actions.move_by_offset(drag_distance + jitter_x, jitter_y)
            actions.release()
            actions.perform()
            
            logger.info(f"✅ Canvas拖拽完成，距离: {drag_distance}px")
            return True
            
        except Exception as e:
            logger.error(f"❌ 处理canvas滑块失败: {e}")
            return False
    
    def click_verification_buttons(self):
        """点击验证相关按钮"""
        try:
            button_selectors = [
                "button[class*='verify']",
                "button[class*='confirm']",
                "button[class*='submit']",
                "div[class*='btn'][class*='verify']",
                "span[class*='btn'][class*='verify']",
                "a[class*='verify']",
                "input[type='submit']"
            ]
            
            # XPath选择器用于包含文本的按钮
            xpath_selectors = [
                "//button[contains(text(), '确认')]",
                "//button[contains(text(), '验证')]",
                "//button[contains(text(), '提交')]",
                "//div[contains(text(), '确认')]",
                "//span[contains(text(), '确认')]"
            ]
            
            # 尝试CSS选择器
            for selector in button_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            logger.info(f"🔘 点击验证按钮: {selector}")
                            if self.safe_click(element):
                                self.random_delay(1, 2)
                                return True
                                
                except Exception as e:
                    logger.debug(f"按钮选择器 {selector} 失败: {e}")
                    continue
            
            # 尝试XPath选择器
            for xpath in xpath_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            logger.info(f"🔘 点击验证按钮: {xpath}")
                            if self.safe_click(element):
                                self.random_delay(1, 2)
                                return True
                                
                except Exception as e:
                    logger.debug(f"按钮XPath {xpath} 失败: {e}")
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 点击验证按钮失败: {e}")
            return False
    
    def perform_standard_slider_drag(self):
        """执行标准滑块拖拽"""
        try:
            # 尝试多种滑块选择器
            slider_element = None
            for selector in self.slider_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed():
                            slider_element = element
                            logger.info(f"✅ 找到滑块元素: {selector}")
                            break
                    if slider_element:
                        break
                except Exception:
                    continue
            
            if slider_element:
                return self.perform_slider_drag(slider_element)
            else:
                logger.warning("⚠️ 未找到标准滑块元素")
                return False
                
        except Exception as e:
            logger.error(f"❌ 标准滑块拖拽失败: {e}")
            return False
    
    def perform_slider_drag(self, slider_element):
        """执行滑块拖拽操作 - 使用高级轨迹模拟"""
        try:
            # 获取滑块位置和大小
            slider_location = slider_element.location
            slider_size = slider_element.size
            
            # 计算拖拽距离 - 使用更保守的距离
            window_width = self.driver.get_window_size()['width']
            container_width = min(window_width - 100, 400)  # 限制最大拖拽距离
            drag_distance = container_width * random.uniform(0.8, 0.95)  # 80%-95%的容器宽度
            
            # 使用高级轨迹计算
            tracks = self._get_human_like_tracks(int(drag_distance))
            
            # 执行模拟人工滑动
            return self._perform_human_like_slider_action(slider_element, tracks)
            
        except Exception as e:
            logger.error(f"❌ 滑块拖拽失败: {e}")
            return False
    
    def _get_human_like_tracks(self, distance):
        """根据距离计算人工滑动轨迹"""
        logger.info(f"🧮 计算人工滑动轨迹，距离: {distance}px")
        
        track = []
        mid1 = round(distance * random.uniform(0.1, 0.2))
        mid2 = round(distance * random.uniform(0.65, 0.76))
        mid3 = round(distance * random.uniform(0.84, 0.88))
        
        # 设置初始位置、初始速度、时间间隔
        current, v, t = 0, 0, 0.2
        distance = round(distance)
        
        # 四段加速度模拟人工滑动
        while current < distance:
            if current < mid1:
                a = random.randint(10, 15)  # 起始加速
            elif current < mid2:
                a = random.randint(30, 40)  # 中段快速
            elif current < mid3:
                a = -70  # 减速准备
            else:
                a = random.randint(-25, -18)  # 最终微调
            
            v0 = v  # 初速度
            v = v0 + a * t  # 当前速度
            v = v if v >= 0 else 0
            move = v0 * t + 1 / 2 * a * (t ** 2)
            move = round(move if move >= 0 else 1)
            current += move
            track.append(move)
        
        # 处理超出范围的情况
        back_tracks = []
        out_range = distance - current
        
        if out_range < -8:
            sub = int(out_range + 8)
            back_tracks = [-1, sub, -3, -1, -1, -1, -1]
        elif out_range < -2:
            sub = int(out_range + 3)
            back_tracks = [-1, -1, sub]
        
        logger.debug(f"📊 轨迹计算完成: 前进{len(track)}步, 回退{len(back_tracks)}步")
        return {'forward_tracks': track, 'back_tracks': back_tracks}
    
    def _perform_human_like_slider_action(self, slider_element, tracks):
        """执行模拟人工的滑块动作"""
        try:
            logger.info("🎭 执行模拟人工滑块动作")
            
            # 点击并保持滑块
            actions = ActionChains(self.driver)
            actions.click_and_hold(slider_element).perform()
            
            # 执行前进轨迹
            for track in tracks['forward_tracks']:
                # 添加随机Y轴抖动模拟人手不稳
                y_offset = random.uniform(-2, 4)
                actions = ActionChains(self.driver)
                actions.move_by_offset(xoffset=track, yoffset=y_offset).perform()
                # 随机停顿模拟人的反应时间
                time.sleep(random.uniform(0.01, 0.03))
            
            # 中间停顿
            time.sleep(random.uniform(0.06, 0.5))
            
            # 执行回退轨迹（微调）
            for back_track in tracks['back_tracks']:
                y_offset = random.uniform(-2, 2)
                actions = ActionChains(self.driver)
                actions.move_by_offset(xoffset=back_track, yoffset=y_offset).perform()
                time.sleep(random.uniform(0.01, 0.02))
            
            # 最终抖动模拟人手的细微调整
            for _ in range(2):
                x_jitter = random.uniform(-1.67, 1.67)
                y_jitter = random.uniform(-1, 1)
                actions = ActionChains(self.driver)
                actions.move_by_offset(xoffset=x_jitter, yoffset=y_jitter).perform()
                time.sleep(random.uniform(0.01, 0.02))
            
            # 最终停顿后释放
            time.sleep(random.uniform(0.2, 0.6))
            actions = ActionChains(self.driver)
            actions.release().perform()
            
            logger.info("✅ 人工模拟滑块动作完成")
            
            # 等待验证结果
            self.random_delay(2, 4)
            
            # 检查验证是否成功
            if not self.check_for_verification():
                logger.info("✅ 人工模拟滑块验证成功")
                return True
            
            logger.info("⏳ 人工模拟滑块验证可能需要更多时间")
            return True
            
        except Exception as e:
            logger.error(f"❌ 人工模拟滑块动作失败: {e}")
            return False
    
    def try_javascript_slider(self):
        """使用JavaScript处理滑块"""
        try:
            # 获取窗口宽度用于JavaScript
            window_width = self.driver.get_window_size()['width']
            drag_distance = window_width - 50  # 留50px避免完全贴边
            
            js_script = f"""
            var sliders = document.querySelectorAll('[class*="slider"], [class*="drag"], [class*="handle"]');
            for (var i = 0; i < sliders.length; i++) {{
                var slider = sliders[i];
                if (slider.offsetParent !== null) {{
                    var rect = slider.getBoundingClientRect();
                    var event = new MouseEvent('mousedown', {{
                        bubbles: true,
                        cancelable: true,
                        clientX: rect.left + rect.width/2,
                        clientY: rect.top + rect.height/2
                    }});
                    slider.dispatchEvent(event);
                    
                    setTimeout(function() {{
                        var moveEvent = new MouseEvent('mousemove', {{
                            bubbles: true,
                            cancelable: true,
                            clientX: {drag_distance},
                            clientY: rect.top + rect.height/2
                        }});
                        document.dispatchEvent(moveEvent);
                        
                        setTimeout(function() {{
                            var upEvent = new MouseEvent('mouseup', {{
                                bubbles: true,
                                cancelable: true,
                                clientX: {drag_distance},
                                clientY: rect.top + rect.height/2
                            }});
                            document.dispatchEvent(upEvent);
                        }}, 50);  // 快速拖拽
                    }}, 20);  // 快速拖拽
                    break;
                }}
            }}
            """
            self.driver.execute_script(js_script)
            logger.info(f"✅ JavaScript滑块处理完成，拖拽距离: {drag_distance}px")
        except Exception as e:
            logger.error(f"❌ JavaScript滑块处理失败: {e}")
    
    def perform_generic_verification_handling(self):
        """通用验证处理方法"""
        try:
            # 获取窗口大小
            window_size = self.driver.get_window_size()
            window_width = window_size['width']
            
            # 减少拖拽距离，避免超出边界
            drag_distance = min(window_width - 100, 300)  # 最大300px，留100px边距
            
            # 使用单一的ActionChains完成整个拖拽序列
            actions = ActionChains(self.driver)
            
            # 从屏幕中央开始，点击并保持，然后拖拽，最后释放
            actions.move_by_offset(window_width // 2, window_size['height'] // 2)\
                   .pause(0.1)\
                   .click_and_hold()\
                   .pause(0.1)\
                   .move_by_offset(drag_distance, 0)\
                   .pause(0.2)\
                   .release()\
                   .perform()
            
            logger.info(f"✅ 通用验证处理完成，拖拽距离: {drag_distance}px")
            return True
        except Exception as e:
            logger.error(f"❌ 通用验证处理失败: {e}")
            return False
    
    def safe_click(self, element):
        """安全点击元素，包含反爬处理"""
        try:
            # 滚动到元素可见
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            self.random_delay(0.5, 1)
            
            # 点击元素
            element.click()
            logger.info("✅ 元素点击成功")
            
            # 点击后检查是否出现验证
            self.random_delay(1, 2)
            if self.check_for_verification():
                logger.info("🔍 点击后检测到验证，开始处理...")
                if not self.handle_slider_verification():
                    logger.warning("⚠️ 点击后验证处理失败，刷新页面")
                    # 验证失败时刷新页面
                    try:
                        self.driver.refresh()
                        logger.info("🔄 页面已刷新，等待重新加载")
                        self.random_delay(3, 5)
                    except Exception as refresh_error:
                        logger.error(f"❌ 页面刷新失败: {refresh_error}")
            
            return True
        except Exception as e:
            logger.error(f"❌ 元素点击失败: {e}")
            return False
    
    def navigate_to_site(self):
        """导航到目标网站"""
        try:
            logger.info("🌐 访问中国招标投标公共服务平台...")
            
            # 设置页面加载超时
            self.driver.set_page_load_timeout(30)
            
            # 首先尝试主URL
            try:
                self.driver.get(self.base_url)
                self.random_delay(3, 5)
                
                # 检查页面是否正常加载
                title = self.driver.title
                logger.info(f"✅ 页面加载成功: {title}")
                
                if "502" in title or "Bad Gateway" in title or "Error" in title or not title:
                    raise Exception(f"主站点返回错误页面: {title}")
                    
            except Exception as e:
                logger.warning(f"⚠️ 主站点访问失败，尝试备用URL: {e}")
                try:
                    self.driver.get(self.backup_url)
                    self.random_delay(3, 5)
                    
                    title = self.driver.title
                    logger.info(f"📄 备用页面标题: {title}")
                    
                    if "502" in title or "Bad Gateway" in title or "Error" in title:
                        raise Exception(f"备用站点也返回错误: {title}")
                        
                except Exception as e2:
                    logger.error(f"❌ 备用URL也访问失败: {e2}")
                    # 尝试使用测试页面
                    logger.info("🔗 尝试访问百度进行网络连接测试...")
                    self.driver.get("https://www.baidu.com")
                    self.random_delay(2, 3)
                    if "百度" in self.driver.title:
                        logger.info("✅ 网络连接正常，目标网站可能暂时不可用")
                    else:
                        logger.error("❌ 网络连接可能存在问题")
                    return False
            
            logger.info(f"🔗 当前URL: {self.driver.current_url}")
            
            # 跳过验证检查，直接进入数据爬取阶段
            logger.info("✅ 页面加载成功，跳过验证检查，直接进入数据爬取阶段")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 网站访问失败: {e}")
            return False
    
    def find_info_disclosure_link(self):
        """查找信息公开链接"""
        try:
            logger.info("🔍 查找信息公开入口...")
            
            # 多种选择器尝试
            selectors = [
                "a[href*='info']",
                "a[href*='disclosure']",
                "a[href*='public']",
                "a:contains('信息公开')",
                "a:contains('信息披露')",
                "a:contains('公开信息')"
            ]
            
            for selector in selectors:
                try:
                    if ":contains" in selector:
                        # 使用XPath处理包含文本的选择器
                        text = selector.split("'")[1]
                        xpath = f"//a[contains(text(), '{text}')]"
                        elements = self.driver.find_elements(By.XPATH, xpath)
                    else:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    for element in elements:
                        if element.is_displayed():
                            logger.info(f"✅ 找到信息公开链接: {element.text}")
                            return element
                except Exception:
                    continue
            
            logger.warning("⚠️ 未找到信息公开链接")
            return None
            
        except Exception as e:
            logger.error(f"❌ 查找信息公开链接失败: {e}")
            return None
    
    def navigate_to_tender_announcements(self):
        """导航到招标公告页面"""
        try:
            logger.info("🎯 开始导航到招标公告页面...")
            
            # 查找招标公告相关链接
            announcement_selectors = [
                "a[href*='zbgg']",  # 招标公告
                "a[href*='tender']",
                "a[href*='announcement']",
                "a:contains('招标公告')",
                "a:contains('公告')",
                "a:contains('招标')"
            ]
            
            announcement_link = None
            for selector in announcement_selectors:
                try:
                    if ":contains" in selector:
                        text = selector.split("'")[1]
                        xpath = f"//a[contains(text(), '{text}')]"
                        elements = self.driver.find_elements(By.XPATH, xpath)
                    else:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    for element in elements:
                        if element.is_displayed():
                            logger.info(f"✅ 找到招标公告链接: {element.text}")
                            announcement_link = element
                            break
                    
                    if announcement_link:
                        break
                except Exception:
                    continue
            
            # 如果找到链接，点击进入
            if announcement_link:
                try:
                    self.safe_click(announcement_link)
                    logger.info("✅ 成功点击招标公告链接")
                    self.random_delay(3, 5)
                    
                    # 智能验证检测（只有同时检测到captcha和滑块才进行验证）
                    if self.check_for_complete_verification():
                        logger.info("🔍 导航后需要进行验证处理")
                        if not self.handle_slider_verification():
                            logger.error("❌ 导航后验证处理失败")
                            return False
                    else:
                        logger.info("✅ 导航后无需验证，直接进行数据爬取")
                    
                    logger.info(f"🔗 当前页面URL: {self.driver.current_url}")
                    logger.info(f"📄 当前页面标题: {self.driver.title}")
                    return True
                    
                except Exception as e:
                    logger.error(f"❌ 点击招标公告链接失败: {e}")
            
            # 如果没有找到招标公告链接，直接在当前页面查找数据
            logger.info("⚠️ 未找到招标公告链接，将在当前页面查找招标数据")
            
            return True  # 继续在当前页面尝试
            
        except Exception as e:
            logger.error(f"❌ 导航到招标公告页面失败: {e}")
            return False
    
    def select_industry(self, industry_name="能源电力"):
        """选择行业分类 - 超快速定位优化版本（3秒内完成）"""
        try:
            start_time = time.time()
            logger.info(f"🎯 快速查找行业: {industry_name}")
            
            # 确保在主页面上下文中
            self.driver.switch_to.default_content()
            
            # 设置极短的隐式等待时间
            original_wait = self.driver.implicitly_wait(0)
            
            try:
                # 优化的选择器 - 按优先级排序，最精确的在前
                selectors = [
                    f"//div[@class='list_01']//a[contains(@onclick, 'resetIndustry') and text()='{industry_name}']",  # 最精确匹配
                    f"//a[contains(@onclick, 'resetIndustry') and text()='{industry_name}']",  # 精确文本匹配
                    f"//div[@class='list_01']//a[contains(text(), '{industry_name}')]",  # 包含匹配
                    f"//a[contains(text(), '{industry_name}') and contains(@onclick, 'resetIndustry')]",  # 备用匹配
                ]
                
                industry_element = None
                
                # 直接查找，不使用WebDriverWait
                for i, selector in enumerate(selectors):
                    try:
                        elements = self.driver.find_elements(By.XPATH, selector)
                        for element in elements:
                            if element.is_displayed() and element.is_enabled():
                                industry_element = element
                                logger.info(f"✅ 快速找到行业元素: {industry_name} (选择器 {i+1})")
                                break
                        if industry_element:
                            break
                    except Exception:
                        continue
                    
                    # 时间控制 - 超过2秒就停止
                    if time.time() - start_time > 2.0:
                        break
                
                if industry_element:
                    # 直接JavaScript点击 - 最快最可靠
                    self.driver.execute_script("arguments[0].click();", industry_element)
                    logger.info(f"✅ 快速点击行业: {industry_name}")
                    
                    # 最小等待时间 - 只等待0.5秒
                    time.sleep(0.5)
                    
                    # 快速检查表格是否更新（可选，不影响主流程）
                    try:
                        table_elements = self.driver.find_elements(By.CSS_SELECTOR, "table.table_text")
                        if table_elements:
                            logger.info("✅ 表格已更新")
                        else:
                            logger.info("⚠️ 未检测到表格，但继续执行")
                    except:
                        pass  # 忽略检查错误，继续执行
                    
                    elapsed_time = time.time() - start_time
                    logger.info(f"✅ 快速完成行业选择: {industry_name} (耗时: {elapsed_time:.2f}秒)")
                    return True
                else:
                    elapsed_time = time.time() - start_time
                    logger.error(f"❌ 未找到行业元素: {industry_name} (耗时: {elapsed_time:.2f}秒)")
                    return False
                    
            finally:
                # 恢复原始隐式等待时间
                self.driver.implicitly_wait(10)
                
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"❌ 选择行业失败: {e} (耗时: {elapsed_time:.2f}秒)")
            return False
    
    def crawl_data(self, max_items_per_page=20):
        """爬取数据主函数 - 支持多行业循环爬取（无页面限制，爬取所有可用数据）"""
        try:
            logger.info("🚀 开始数据爬取...")
            
            # 导航到网站（包含验证处理）
            if not self.navigate_to_site():
                return False
            
            # 等待页面完全加载
            self.random_delay(3, 5)
            
            # 通过验证后已经在正确页面，无需导航
            logger.info("✅ 未检测到验证，直接进入数据爬取阶段")
            
            total_scraped = 0
            
            # 循环爬取每个行业
            for industry_index, industry_name in enumerate(self.industries):
                logger.info(f"\n🎯 开始爬取行业 [{industry_index+1}/{len(self.industries)}]: {industry_name}")
                
                # 选择行业分类（不跳转页面，只更新表格内容）
                if not self.select_industry_with_verification(industry_name):
                    logger.warning(f"⚠️ 行业 {industry_name} 选择失败，跳过")
                    continue
                
                # 爬取该行业的所有页面（在同一页面上翻页）
                industry_scraped = self.crawl_industry_pages(industry_name, max_items_per_page)
                total_scraped += industry_scraped
                
                logger.info(f"✅ 行业 {industry_name} 爬取完成，获得 {industry_scraped} 条数据")
                
                # 行业间延迟
                self.random_delay(3, 6)
            
            logger.info(f"🎉 所有行业爬取完成，共爬取 {total_scraped} 条数据")
            return True
            
        except Exception as e:
            logger.error(f"❌ 数据爬取失败: {e}")
            return False
    
    def select_industry_with_verification(self, industry_name):
        """选择行业并进行智能验证检测"""
        try:
            logger.info(f"🎯 选择行业: {industry_name}")
            
            # 选择行业
            if not self.select_industry(industry_name):
                return False
            
            # 等待页面响应
            self.random_delay(1, 2)
            
            # 智能验证检测（只有同时检测到captcha和滑块才进行验证）
            logger.info("🔍 选择行业后进行智能验证检测")
            if self.check_for_complete_verification():
                logger.info("🔍 选择行业后需要进行验证处理")
                if not self.handle_slider_verification():
                    logger.error("❌ 选择行业后验证处理失败，刷新页面重试")
                    # 验证失败时刷新页面
                    try:
                        self.driver.refresh()
                        logger.info("🔄 页面已刷新，等待重新加载")
                        self.random_delay(3, 5)
                    except Exception as refresh_error:
                        logger.error(f"❌ 页面刷新失败: {refresh_error}")
                    return False
            else:
                logger.info("✅ 选择行业后无需验证，直接进行数据爬取")
            
            logger.info(f"✅ 行业 {industry_name} 选择成功，开始爬取数据")
            return True
            
        except Exception as e:
            logger.error(f"❌ 选择行业失败: {e}")
            return False
    
    def crawl_industry_pages(self, industry_name, max_items_per_page):
        """爬取指定行业的所有页面（优化版：检测到过期数据时直接跳转下一行业）"""
        industry_scraped = 0
        page = 1
        
        try:
            while True:  # 无限循环，直到无法翻页或检测到过期数据为止
                logger.info(f"📄 爬取 {industry_name} 第 {page} 页...")
                
                # 爬取当前页面数据
                page_data = self.scrape_current_page(max_items_per_page)
                if page_data:
                    valid_items = 0
                    outdated_items = 0
                    
                    # 检查每条数据的发布时间，判断是否过期
                    for item in page_data:
                        create_time = item.get('createTime', '')
                        
                        # 检查日期是否在合理范围内（最近30天）
                        if self.is_data_recent(create_time):
                            try:
                                # 数据已经按照指定格式构建，直接保存
                                self.collection.insert_one(item)
                                industry_scraped += 1
                                valid_items += 1
                                logger.info(f"✅ 保存数据: {item.get('title', '未知标题')[:50]}... (发布时间: {create_time})")
                            except Exception as e:
                                if "duplicate key error" in str(e).lower():
                                    logger.info(f"⚠️ 跳过重复数据: {item.get('title', '未知标题')[:50]}... (发布时间: {create_time})")
                                else:
                                    logger.error(f"❌ 数据保存失败: {e}")
                        else:
                            outdated_items += 1
                            logger.info(f"⏰ 检测到过期数据: {item.get('title', '未知标题')[:50]}... (发布时间: {create_time})")
                    
                    # 如果当前页面检测到过期数据，直接跳转到下一个行业
                    if outdated_items > 0:
                        logger.info(f"🚫 行业 {industry_name} 第 {page} 页检测到 {outdated_items} 条过期数据，由于数据按时间排序，后续页面数据会更旧，直接跳转到下一个行业")
                        logger.info(f"✅ 行业 {industry_name} 爬取完成，共获得 {industry_scraped} 条有效数据")
                        break
                        
                else:
                    logger.warning(f"⚠️ 第 {page} 页没有获取到数据")
                
                # 尝试翻页（在同一页面上翻页）
                if not self.go_to_next_page_with_verification():
                    logger.info(f"✅ 行业 {industry_name} 已爬取到最后一页（第 {page} 页），结束爬取")
                    break
                
                page += 1
                self.random_delay(2, 4)
            
            # 注意：不需要返回行业选择页面，因为行业选择始终在左侧可见
            logger.info(f"✅ 行业 {industry_name} 的所有页面爬取完成")
            
            return industry_scraped
            
        except Exception as e:
            logger.error(f"❌ 爬取行业 {industry_name} 失败: {e}")
            return industry_scraped
    
    # 注意：不再需要return_to_industry_selection函数
    # 因为行业选择始终在同一页面的左侧可见，不需要页面跳转
    
    def go_to_next_page_with_verification(self):
        """翻页并进行智能验证检测"""
        try:
            # 翻页
            if not self.go_to_next_page():
                return False
            
            # 等待页面响应
            self.random_delay(1, 2)
            
            # 智能验证检测（只有同时检测到captcha和滑块才进行验证）
            logger.info("🔍 翻页后进行智能验证检测")
            if self.check_for_complete_verification():
                logger.info("🔍 翻页后需要进行验证处理")
                if not self.handle_slider_verification():
                    logger.error("❌ 翻页验证处理失败，刷新页面重试")
                    # 验证失败时刷新页面
                    try:
                        self.driver.refresh()
                        logger.info("🔄 页面已刷新，等待重新加载")
                        self.random_delay(3, 5)
                    except Exception as refresh_error:
                        logger.error(f"❌ 页面刷新失败: {refresh_error}")
                    return False
            else:
                logger.info("✅ 翻页后无需验证，直接进行数据爬取")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 翻页失败: {e}")
            return False
    
    def smart_switch_to_iframe(self, target_type):
        """智能切换到目标iframe - 基于缓存机制直接定位"""
        try:
            # 确保在主页面上下文中
            self.driver.switch_to.default_content()
            
            if target_type == 'main_page':
                logger.debug("🎯 保持在主页面上下文")
                return True
            
            # 获取缓存的iframe索引
            iframe_index = self.iframe_cache.get(target_type)
            if iframe_index is None:
                logger.warning(f"⚠️ 未找到 {target_type} 的iframe缓存")
                return False
            
            # 查找所有iframe
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            if len(iframes) <= iframe_index:
                logger.error(f"❌ iframe[{iframe_index}] 不存在，总共只有 {len(iframes)} 个iframe")
                return False
            
            # 切换到目标iframe
            self.driver.switch_to.frame(iframes[iframe_index])
            logger.debug(f"🎯 已切换到iframe[{iframe_index}] ({target_type})")
            return True
            
        except Exception as e:
            logger.error(f"❌ 切换到iframe失败 ({target_type}): {e}")
            try:
                self.driver.switch_to.default_content()
            except:
                pass
            return False
    
    def scrape_current_page(self, max_items):
        """爬取当前页面的数据 - 直接定位优化版本，基于缓存机制直接定位到iframe[1]"""
        try:
            logger.info("🔍 开始爬取当前页面数据...")
            data_list = []
            
            # 等待页面加载完成
            self.random_delay(2, 3)
            
            # 使用智能切换到数据表格所在的iframe
            if not self.smart_switch_to_iframe('data_table'):
                logger.error("❌ 无法切换到数据表格iframe")
                return data_list
            
            try:
                logger.info("✅ 已切换到数据表格iframe")
                
                # 查找表格
                tables = self.driver.find_elements(By.TAG_NAME, "table")
                if not tables:
                    logger.error("❌ iframe[1]中未找到表格")
                    self.driver.switch_to.default_content()
                    return data_list
                
                # 使用第一个表格
                table = tables[0]
                rows = table.find_elements(By.TAG_NAME, "tr")
                logger.info(f"📊 iframe[1]中的表格包含 {len(rows)} 行数据")
                
                if len(rows) <= 1:
                    logger.warning("⚠️ 表格中没有数据行（只有表头或无数据）")
                    self.driver.switch_to.default_content()
                    return data_list
                
                # 跳过表头，提取数据行
                data_rows = rows[1:max_items+1]  # 跳过第一行（表头）
                logger.info(f"📊 准备提取 {len(data_rows)} 行数据")
                
                # 提取每行数据
                for i, row in enumerate(data_rows):
                    try:
                        item_data = self.extract_row_data(row, i + 1)
                        if item_data:
                            data_list.append(item_data)
                    except Exception as e:
                        logger.error(f"❌ 提取第 {i+1} 行数据失败: {e}")
                        continue
                
                # 切换回主页面
                self.driver.switch_to.default_content()
                
            except Exception as e:
                logger.error(f"❌ 处理iframe[1]失败: {e}")
                self.driver.switch_to.default_content()
                return data_list
            
            logger.info(f"✅ 当前页面提取到 {len(data_list)} 条有效数据")
            return data_list
            
        except Exception as e:
            logger.error(f"❌ 爬取当前页面失败: {e}")
            return []
    
    def extract_row_data(self, row, row_index):
        """从数据行中提取信息 - 按照指定的MongoDB数据结构格式"""
        try:
            import re
            
            # 首先获取行的原始文本，确保row_text变量始终被定义
            row_text = row.text.strip()
            
            # 查找标题和链接
            title_element = None
            link_url = None
            
            # 多种标题选择器（基于实际页面结构）
            title_selectors = [
                "td:first-child a",  # 第一列的链接（项目名称）
                "td a[title]",  # 带title属性的链接
                "td a[href]",  # 带href的链接
                "a[title]",
                "a[href]",
                "td a",
                "div a",
                "span a",
                "a"
            ]
            
            for selector in title_selectors:
                try:
                    elements = row.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        title_element = elements[0]
                        break
                except Exception:
                    continue
            
            if not title_element:
                # 如果没有链接，尝试直接获取文本
                if row_text and len(row_text) > 10:
                    title = row_text.split('\n')[0]  # 取第一行作为标题
                else:
                    return None
            else:
                title = title_element.get_attribute("title") or title_element.text.strip()
                link_url = title_element.get_attribute("href")
                
                # 尝试从HTML源码注释中提取完整URL
                try:
                    # 获取包含该元素的HTML源码
                    row_html = row.get_attribute("outerHTML")
                    
                    # 查找注释中的完整URL
                    # 匹配模式：<!-- 完整URL -->
                    comment_pattern = r'<!--\s*([^\s]+)\s*-->'
                    comment_matches = re.findall(comment_pattern, row_html)
                    
                    for comment_url in comment_matches:
                        # 如果是javascript:urlOpen()格式，提取其中的URL
                        if 'javascript:urlOpen(' in comment_url:
                            url_match = re.search(r"javascript:urlOpen\(['\"]([^'\"]+)['\"]\)", comment_url)
                            if url_match:
                                link_url = url_match.group(1)
                                logger.info(f"✅ 从注释中提取到完整URL: {link_url}")
                                break
                        # 检查是否是有效的URL（包含http或以/开头的相对路径）
                        elif (comment_url.startswith('http') or 
                              comment_url.startswith('/') or 
                              'bulletin.cebpubservice.com' in comment_url):
                            link_url = comment_url
                            logger.info(f"✅ 从注释中提取到完整URL: {link_url}")
                            break
                    
                    # 如果注释中没找到，尝试查找onclick事件中的URL参数
                    if not link_url or 'javascript:' in link_url:
                        onclick_attr = title_element.get_attribute("onclick")
                        if onclick_attr:
                            # 提取onclick中的参数，如urlOpen('769926c3847c4d958dd821b773cd34c6')
                            param_match = re.search(r"urlOpen\(['\"]([^'\"]+)['\"]\)", onclick_attr)
                            if param_match:
                                param_id = param_match.group(1)
                                # 构建完整URL
                                base_url = "https://bulletin.cebpubservice.com/"
                                link_url = f"{base_url}biddingBulletin/{param_id}.html"
                                logger.info(f"✅ 从onclick参数构建完整URL: {link_url}")
                                
                except Exception as e:
                    logger.warning(f"⚠️ 提取注释URL失败: {e}")
            
            if not title or len(title.strip()) < 5:
                return None
            
            # 提取其他信息（基于实际表格结构）
            cells = row.find_elements(By.TAG_NAME, "td")
            if not cells:
                cells = row.find_elements(By.CSS_SELECTOR, "div, span")
            
            # 根据表格列结构提取数据
            publish_date = ""
            area = ""
            industry = ""
            source_channel = ""
            remaining_days = ""
            
            # 如果有足够的列，按顺序提取
            if len(cells) >= 5:
                # 表格列顺序：项目名称、所属行业、所属地区、来源渠道、发布时间、剩余天数
                try:
                    industry = cells[1].text.strip() if len(cells) > 1 else ""  # 所属行业（第2列）
                    area_raw = cells[2].text.strip() if len(cells) > 2 else ""  # 所属地区（第3列）
                    # 去掉地区名称中的【】大括号
                    area = area_raw.replace('【', '').replace('】', '') if area_raw else ""
                    source_channel = cells[3].text.strip() if len(cells) > 3 else ""  # 来源渠道（第4列）
                    publish_date = cells[4].text.strip() if len(cells) > 4 else ""  # 发布时间（第5列）
                    # 剩余天数通常在最后一列
                    if len(cells) > 5:
                        remaining_days = cells[5].text.strip()
                    elif len(cells) == 5:
                        # 如果只有5列，检查最后一列是否包含"剩余"字样
                        last_cell_text = cells[4].text.strip()
                        if "剩余" in last_cell_text:
                            remaining_days = last_cell_text
                            publish_date = ""  # 重新分配
                except Exception:
                    pass
            
            # 如果上述方法失败，使用正则匹配
            if not publish_date and row_text:
                date_pattern = r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})'
                date_match = re.search(date_pattern, row_text)
                if date_match:
                    publish_date = date_match.group(1)
            
            # 从URL中提取contentId
            content_id = None
            if link_url:
                # 尝试从URL中提取ID，如 /zchwzb/16952.jhtml
                id_match = re.search(r'/(\d+)\.', link_url)
                if id_match:
                    content_id = int(id_match.group(1))
            
            # 提取预算信息（从标题或原始文本中）
            budget = None
            budget_patterns = [
                r'(\d+(?:\.\d+)?万元)',
                r'(\d+(?:\.\d+)?亿元)',
                r'预算[：:](\d+(?:\.\d+)?[万亿]元)',
                r'金额[：:](\d+(?:\.\d+)?[万亿]元)'
            ]
            
            for pattern in budget_patterns:
                match = re.search(pattern, row_text + ' ' + title)
                if match:
                    budget = match.group(1)
                    break
            
            # 如果没有从表格列中提取到剩余天数，尝试从文本中提取
            if not remaining_days and row_text:
                remaining_pattern = r'(剩余\d+天)'
                remaining_match = re.search(remaining_pattern, row_text)
                if remaining_match:
                    remaining_days = remaining_match.group(1)
            
            # 构建按照指定格式的数据项
            item_data = {
                "contentId": content_id,
                "agent": None,  # 代理机构信息，暂时置为None
                "area": area if area else None,  # 所属地区
                "briefText": None,  # 简要文本，按用户要求置为null
                "budget": budget,
                "budget_label": None,
                "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "createTime": publish_date if publish_date else None,  # 发布时间
                "detail": None,
                "hasAnnex": False,
                "highlightedWords": None,
                "keywords": "",
                "noticeType": "公告",
                "tenderEndTime": remaining_days if remaining_days else None,  # 剩余天数
                "tenderees": source_channel if source_channel else None,  # 来源渠道
                "title": title.strip(),
                "url": link_url if link_url else None,
                "industry": industry if industry else None  # 所属行业
            }
            
            return item_data
            
        except Exception as e:
            logger.error(f"❌ 提取行数据失败: {e}")
            return None
    
    def go_to_next_page(self):
        """翻到下一页 - 直接定位优化版本，基于日志分析直接定位到iframe[1]"""
        try:
            logger.info("🔍 开始查找下一页按钮...")
            
            # 确保在主页面上下文中
            self.driver.switch_to.default_content()
            
            # 基于日志分析，下一页按钮总是在iframe[1]中，直接定位
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            logger.info(f"📊 发现 {len(iframes)} 个iframe元素")
            
            if len(iframes) >= 2:  # 确保iframe[1]存在
                try:
                    logger.info("🎯 直接切换到下一页按钮所在iframe...")
                    if not self.smart_switch_to_iframe('next_page_button'):
                        logger.error("❌ 无法切换到下一页按钮iframe")
                        return False
                    
                    # 使用较短的超时时间，因为我们知道按钮在这里
                    next_button = self._find_next_button_in_context(timeout=3)
                    if next_button:
                        # 使用JavaScript点击 - 更可靠
                        try:
                            self.driver.execute_script("arguments[0].click();", next_button)
                            logger.info("✅ 成功点击iframe[1]中的下一页按钮 (JavaScript)")
                            self.driver.switch_to.default_content()
                            time.sleep(3)  # 等待页面加载
                            return True
                        except Exception as e:
                            logger.warning(f"JavaScript点击失败，尝试普通点击: {e}")
                            if self.safe_click(next_button):
                                logger.info("✅ 成功点击iframe[1]中的下一页按钮")
                                self.driver.switch_to.default_content()
                                time.sleep(3)
                                return True
                    else:
                        logger.warning("⚠️ 在iframe[1]中未找到下一页按钮")
                    
                    self.driver.switch_to.default_content()
                    
                except Exception as e:
                    logger.error(f"❌ 在iframe[1]中查找翻页按钮失败: {e}")
                    try:
                        self.driver.switch_to.default_content()
                    except:
                        pass
            
            # 如果iframe[1]中没有找到，回退到原来的逐个查找方式
            logger.info("🔄 回退到逐个iframe查找模式...")
            for i, iframe in enumerate(iframes):
                try:
                    logger.info(f"🔍 切换到iframe[{i}]，开始查找下一页按钮...")
                    self.driver.switch_to.frame(iframe)
                    
                    # 使用固定的5秒超时时间
                    next_button = self._find_next_button_in_context(timeout=5)
                    if next_button:
                        # 使用JavaScript点击 - 更可靠
                        try:
                            self.driver.execute_script("arguments[0].click();", next_button)
                            logger.info(f"✅ 成功点击iframe[{i}]中的下一页按钮 (JavaScript)")
                            self.driver.switch_to.default_content()
                            time.sleep(3)  # 等待页面加载
                            return True
                        except Exception as e:
                            logger.warning(f"JavaScript点击失败，尝试普通点击: {e}")
                            if self.safe_click(next_button):
                                logger.info(f"✅ 成功点击iframe[{i}]中的下一页按钮")
                                self.driver.switch_to.default_content()
                                time.sleep(3)
                                return True
                    else:
                        logger.warning(f"⚠️ 在iframe[{i}]中未找到下一页按钮")
                    
                    self.driver.switch_to.default_content()
                    
                except Exception as e:
                    logger.error(f"❌ 在iframe[{i}]中查找翻页按钮失败: {e}")
                    try:
                        self.driver.switch_to.default_content()
                    except:
                        pass
            
            logger.warning("⚠️ 未找到下一页按钮，可能已到最后一页")
            return False
                
        except Exception as e:
            logger.error(f"❌ 翻页失败: {e}")
            return False
    
    def _find_next_button_in_context(self, timeout=10):
        """在当前上下文中查找下一页按钮，带超时机制 - 增强版本"""
        try:
            start_time = time.time()
            
            # 增强的选择器 - 按优先级排序，针对中国招标网站优化
            selectors = [
                # 最精确的XPath - 针对招标网站
                "//a[contains(text(), '下一页') and contains(@onclick, 'turnPage')]",
                "//a[contains(text(), '下一页') and contains(@href, 'javascript')]",
                "//a[contains(@onclick, 'turnPage') and not(contains(@class, 'disabled'))]",
                "//a[contains(@onclick, 'nextPage') and not(contains(@class, 'disabled'))]",
                
                # 通用下一页文本匹配
                "//a[contains(text(), '下一页') and not(contains(@class, 'disabled'))]",
                "//a[text()='下一页' and not(contains(@class, 'disabled'))]",
                "//a[contains(text(), '>') and not(contains(@class, 'disabled'))]",
                "//a[contains(text(), '»') and not(contains(@class, 'disabled'))]",
                "//a[contains(text(), 'Next') and not(contains(@class, 'disabled'))]",
                
                # 分页容器内的下一页
                "//div[contains(@class, 'page')]//a[contains(text(), '下一页')]",
                "//div[contains(@class, 'pagination')]//a[contains(text(), '下一页')]",
                "//ul[contains(@class, 'pagination')]//a[contains(text(), '下一页')]",
                "//div[contains(@id, 'page')]//a[contains(text(), '下一页')]",
                
                # onclick属性匹配
                "//a[contains(@onclick, 'turnPage')]",
                "//a[contains(@onclick, 'nextPage')]",
                "//a[contains(@onclick, 'next')]",
                "//a[contains(@onclick, 'goPage')]",
                "//a[contains(@onclick, 'changePage')]",
                
                # CSS选择器
                "a[onclick*='turnPage']:not(.disabled)",
                "a[onclick*='nextPage']:not(.disabled)",
                "a[onclick*='next']:not(.disabled)",
                "a[href*='javascript'][onclick*='Page']:not(.disabled)",
                "a[class*='next']:not(.disabled)",
                "button[class*='next']:not(.disabled)",
                "span[class*='next']:not(.disabled)",
                "li[class*='next'] a:not(.disabled)",
                "div[class*='page'] a[class*='next']:not(.disabled)",
                "div[class*='pagination'] a[class*='next']:not(.disabled)",
                "a[title*='下一页']:not(.disabled)",
                "button[title*='下一页']:not(.disabled)",
                
                # 通用分页选择器
                ".pagination a:contains('下一页')",
                ".page-nav a:contains('下一页')",
                ".page-link:contains('下一页')",
                "[data-page='next']",
                "[data-action='next']"
            ]
            
            # 尝试所有选择器
            for i, selector in enumerate(selectors):
                if time.time() - start_time > timeout:
                    logger.warning(f"⚠️ 查找下一页按钮超时 ({timeout}秒)")
                    return None
                    
                try:
                    # 根据选择器类型选择查找方法
                    if selector.startswith("//"):  # XPath选择器
                        elements = self.driver.find_elements(By.XPATH, selector)
                    elif selector.startswith(".") or selector.startswith("#") or "[" in selector:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    else:  # 其他CSS选择器
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    logger.debug(f"🔍 选择器 {i+1}/{len(selectors)}: {selector} - 找到 {len(elements)} 个元素")
                    
                    for j, element in enumerate(elements):
                        try:
                            # 检查元素是否可见和可用
                            if not element.is_displayed():
                                logger.debug(f"  元素 {j+1} 不可见")
                                continue
                            if not element.is_enabled():
                                logger.debug(f"  元素 {j+1} 不可用")
                                continue
                                
                            # 获取元素属性
                            element_text = element.text.strip()
                            onclick_attr = element.get_attribute('onclick') or ''
                            href_attr = element.get_attribute('href') or ''
                            class_attr = element.get_attribute('class') or ''
                            title_attr = element.get_attribute('title') or ''
                            
                            # 检查是否被禁用
                            if 'disabled' in class_attr.lower():
                                logger.debug(f"  元素 {j+1} 被禁用: {class_attr}")
                                continue
                            
                            # 增强验证条件
                            is_next_button = (
                                '下一页' in element_text or 
                                '>' in element_text or 
                                '»' in element_text or 
                                'Next' in element_text or
                                'turnPage' in onclick_attr or
                                'nextPage' in onclick_attr or
                                'goPage' in onclick_attr or
                                'changePage' in onclick_attr or
                                '下一页' in title_attr or
                                'next' in class_attr.lower()
                            )
                            
                            if is_next_button:
                                logger.info(f"✅ 找到下一页按钮: 选择器{i+1} (文本: '{element_text}', onclick: '{onclick_attr[:50]}...')")
                                return element
                            else:
                                logger.debug(f"  元素 {j+1} 不符合下一页条件: 文本='{element_text}', onclick='{onclick_attr[:30]}...'")
                                
                        except Exception as elem_e:
                            logger.debug(f"  检查元素 {j+1} 时出错: {elem_e}")
                            continue
                            
                except Exception as e:
                    logger.debug(f"选择器 {i+1} 失败: {e}")
                    continue
            
            logger.info("🔍 未找到下一页按钮，可能已到最后一页")
            return None
            
        except Exception as e:
            logger.error(f"❌ 查找下一页按钮失败: {e}")
            return None
    
    def close(self):
        """关闭浏览器和数据库连接"""
        try:
            if self.driver:
                self.driver.quit()
                logger.info("✅ 浏览器已关闭")
            
            if hasattr(self, 'client'):
                self.client.close()
                logger.info("✅ 数据库连接已关闭")
                
        except Exception as e:
            logger.error(f"❌ 关闭资源时出错: {e}")
    
    def run(self):
        """运行爬虫"""
        try:
            logger.info("🎯 启动中国招标投标公共服务平台爬虫")
            
            # 初始化
            if not self.setup_database():
                return False
            
            if not self.setup_driver():
                return False
            
            # 爬取数据
            success = self.crawl_data()
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 爬虫运行失败: {e}")
            return False
        finally:
            self.close()

# 添加调度相关导入
from datetime import timedelta
import schedule
import threading
import re

class ScheduledCrawler:
    def __init__(self):
        self.is_running = False
        self.spider = None
        self.start_time = None
        self.crawl_duration = None  # 无时间限制
        # 固定爬取最近7天的数据
        self.days_back = self.calculate_crawl_days()
        # 计算7天前的日期作为截止日期
        self.cutoff_date = (datetime.now() - timedelta(days=self.days_back-1)).strftime('%Y-%m-%d')
        # 初始化数据库连接用于去重
        self.db = None
        self.collection = None
        self.setup_database()
    
    def calculate_crawl_days(self):
        """固定爬取最近7天的数据"""
        # 每天都爬取最近7天的数据
        days_back = 7
        return days_back
    
    def is_data_recent(self, create_time_str):
        """检查数据是否在最近7天内（用于过期数据检测）"""
        try:
            if not create_time_str:
                return True  # 如果没有时间信息，默认认为是最新的
            
            # 解析日期字符串
            import re
            from datetime import datetime, timedelta
            
            # 提取日期部分（支持多种格式）
            date_patterns = [
                r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',  # YYYY-MM-DD 或 YYYY/MM/DD
                r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})',  # MM-DD-YYYY 或 MM/DD/YYYY
                r'(\d{4}年\d{1,2}月\d{1,2}日)',     # 中文格式
            ]
            
            date_str = None
            for pattern in date_patterns:
                match = re.search(pattern, create_time_str)
                if match:
                    date_str = match.group(1)
                    break
            
            if not date_str:
                logger.warning(f"⚠️ 无法解析日期格式: {create_time_str}")
                return True  # 无法解析时默认认为是最新的
            
            # 尝试解析日期
            try:
                # 处理不同的日期格式
                if '年' in date_str:
                    # 中文格式：2024年1月15日
                    date_str = date_str.replace('年', '-').replace('月', '-').replace('日', '')
                
                # 统一为YYYY-MM-DD格式
                if '/' in date_str:
                    date_str = date_str.replace('/', '-')
                
                # 解析日期
                if len(date_str.split('-')[0]) == 4:  # YYYY-MM-DD
                    create_date = datetime.strptime(date_str, '%Y-%m-%d')
                else:  # MM-DD-YYYY
                    parts = date_str.split('-')
                    if len(parts) == 3:
                        create_date = datetime.strptime(f"{parts[2]}-{parts[0]}-{parts[1]}", '%Y-%m-%d')
                    else:
                        return True
                
                # 计算时间差
                today = datetime.now()
                days_diff = (today - create_date).days
                
                # 如果数据超过7天，认为是过期数据
                if days_diff > 7:
                    logger.debug(f"📅 数据过期: {create_time_str} (距今 {days_diff} 天，超过7天限制)")
                    return False
                else:
                    logger.debug(f"📅 数据有效: {create_time_str} (距今 {days_diff} 天，在7天范围内)")
                    return True
                    
            except ValueError as e:
                logger.warning(f"⚠️ 日期解析失败: {date_str} - {e}")
                return True  # 解析失败时默认认为是最新的
                
        except Exception as e:
            logger.error(f"❌ 检查数据时效性失败: {e}")
            return True  # 出错时默认认为是最新的
    

    
    def is_duplicate(self, title, publish_time):
        """检查数据是否已存在（去重机制）"""
        try:
            existing = self.collection.find_one({
                "title": title,
                "publish_time": publish_time
            })
            return existing is not None
        except Exception as e:
            logger.error(f"❌ 去重检查失败: {e}")
            return False
    
    def should_stop_crawling(self):
        """检查是否应该停止爬取（无时间限制）"""
        # 移除时间限制，只有手动中断才会停止
        return False
    
    def crawl_with_time_limit(self):
        """带时间限制的爬取任务"""
        try:
            logger.info("🚀 开始定时爬取任务")
            self.is_running = True
            self.start_time = time.time()
            
            total_scraped = 0
            
            # 初始化爬虫
            self.spider = LegalCebpubserviceSpider()
            
            # 使用调度器的数据库连接，不需要重复初始化
            if self.db is None or self.collection is None:
                logger.error("❌ 数据库连接未初始化")
                return
            
            # 将调度器的数据库连接传递给spider
            self.spider.db = self.db
            self.spider.collection = self.collection
            
            if not self.spider.setup_driver():
                logger.error("❌ 浏览器驱动初始化失败")
                return
            
            # 导航到网站
            if not self.spider.navigate_to_site():
                logger.error("❌ 网站导航失败")
                return
            
            # 等待页面加载
            self.spider.random_delay(3, 5)
            
            # 从第一个行业开始爬取
            industries = self.spider.industries
            
            for industry_index, industry_name in enumerate(industries):
                # 移除时间限制检查
                # if self.should_stop_crawling():
                #     logger.info("⏰ 达到时间限制，停止爬取")
                #     break
                
                logger.info(f"🎯 爬取行业 [{industry_index+1}/{len(industries)}]: {industry_name}")
                
                # 选择行业
                if not self.spider.select_industry_with_verification(industry_name):
                    logger.warning(f"⚠️ 行业 {industry_name} 选择失败，跳过")
                    continue
                
                # 爬取该行业的页面
                industry_scraped = self.crawl_industry_with_time_limit(industry_name, 1, industry_index, total_scraped)
                total_scraped += industry_scraped
                
                # 移除时间限制检查
                # if self.should_stop_crawling():
                #     break
                
                self.spider.random_delay(3, 6)
            
            elapsed_time = time.time() - self.start_time
            logger.info(f"✅ 定时爬取任务完成，耗时 {elapsed_time/60:.1f} 分钟，共爬取 {total_scraped} 条数据")
            
        except Exception as e:
            logger.error(f"❌ 定时爬取任务失败: {e}")
        finally:
            self.is_running = False
            if self.spider:
                self.spider.close()
    
    def is_date_within_range(self, date_str):
        """检查日期是否在指定天数范围内"""
        if not date_str:
            return True  # 如果没有日期信息，默认保留
        
        try:
            # 尝试解析不同格式的日期
            date_formats = ['%Y-%m-%d', '%Y/%m/%d', '%Y-%m-%d %H:%M:%S']
            item_date = None
            
            for fmt in date_formats:
                try:
                    item_date = datetime.strptime(date_str.split()[0], fmt).date()
                    break
                except ValueError:
                    continue
            
            if not item_date:
                # 如果无法解析日期，尝试正则匹配
                date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', date_str)
                if date_match:
                    date_part = date_match.group(1).replace('/', '-')
                    item_date = datetime.strptime(date_part, '%Y-%m-%d').date()
                else:
                    return True  # 无法解析日期，默认保留
            
            cutoff_date = datetime.strptime(self.cutoff_date, '%Y-%m-%d').date()
            return item_date >= cutoff_date
            
        except Exception as e:
            logger.warning(f"⚠️ 日期解析失败: {date_str}, 错误: {e}")
            return True  # 解析失败时默认保留
    
    def crawl_industry_with_time_limit(self, industry_name, start_page, industry_index, total_scraped):
        """带时间限制和日期过滤的行业爬取"""
        industry_scraped = 0
        page = start_page
        should_stop_industry = False
        
        try:
            while not should_stop_industry:
                logger.info(f"📄 爬取 {industry_name} 第 {page} 页...")
                
                # 爬取当前页面数据
                page_data = self.spider.scrape_current_page(20)
                if page_data:
                    valid_items = 0
                    outdated_items = 0
                    
                    # 检查每条数据的发布时间
                    for item in page_data:
                        create_time = item.get('createTime', '')
                        
                        # 检查日期是否在范围内
                        if self.is_date_within_range(create_time):
                            try:
                                title = item.get('title', '')
                                publish_time = item.get('publish_time', create_time)
                                
                                # 检查是否重复
                                if self.is_duplicate(title, publish_time):
                                    logger.info(f"⚠️ 跳过重复数据: {title[:50]}... (发布时间: {create_time})")
                                    continue
                                
                                # 保存到数据库
                                self.collection.insert_one(item)
                                industry_scraped += 1
                                valid_items += 1
                                logger.info(f"✅ 保存新数据: {title[:50]}... (发布时间: {create_time})")
                            except Exception as e:
                                if "duplicate key error" in str(e).lower():
                                    logger.info(f"⚠️ 跳过重复数据: {item.get('title', '未知标题')[:50]}... (发布时间: {create_time})")
                                else:
                                    logger.error(f"❌ 数据保存失败: {e}")
                        else:
                            outdated_items += 1
                            logger.info(f"⏰ 跳过过期数据: {item.get('title', '未知标题')[:50]}... (发布时间: {create_time})")
                    
                    # 如果当前页面检测到过期数据，直接跳转到下一个行业
                    if outdated_items > 0:
                        logger.info(f"🚫 行业 {industry_name} 第 {page} 页检测到 {outdated_items} 条过期数据，由于数据按时间排序，后续页面数据会更旧，直接跳转到下一个行业")
                        should_stop_industry = True
                        break
                        
                else:
                    logger.warning(f"⚠️ 第 {page} 页没有获取到数据")
                
                # 尝试翻页
                if not self.spider.go_to_next_page_with_verification():
                    logger.info(f"✅ 行业 {industry_name} 已爬取到最后一页（第 {page} 页）")
                    break
                
                page += 1
                self.spider.random_delay(2, 4)
            
            if should_stop_industry:
                logger.info(f"📅 行业 {industry_name} 因时间过滤提前结束，共爬取 {industry_scraped} 条有效数据")
            
            return industry_scraped
            
        except Exception as e:
            logger.error(f"❌ 爬取行业 {industry_name} 失败: {e}")
            return industry_scraped
    
    def start_scheduled_task(self):
        """启动定时任务"""
        if self.is_running:
            logger.warning("⚠️ 爬取任务正在运行中，跳过本次调度")
            return
        
        # 在新线程中运行爬取任务，避免阻塞调度器
        thread = threading.Thread(target=self.crawl_with_time_limit)
        thread.daemon = True
        thread.start()
    
    def run_scheduler(self):
        """运行调度器"""
        # 每天下午4点开始爬取
        schedule.every().day.at("16:00").do(self.start_scheduled_task)
        
        logger.info("📅 定时爬取调度器已启动，每天下午16:00开始爬取（无时间限制）")
        logger.info(f"📅 时间过滤: 只爬取最近7天数据 ({self.cutoff_date} 及之后的数据)")
        logger.info("💡 提示: 按 Ctrl+C 停止调度器")
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
        except KeyboardInterrupt:
            logger.info("👋 调度器已停止")
            if self.is_running and self.spider:
                self.spider.close()

def main():
    """主函数 - 支持立即运行和定时运行两种模式"""
    import sys
    
    # 检查命令行参数
    if len(sys.argv) > 1 and sys.argv[1] == "--now":
        # 立即运行模式
        try:
            # 创建爬虫实例
            crawler = ScheduledCrawler()
            
            # 显示爬取配置
            today = datetime.now().strftime('%Y-%m-%d %A')
            weekday_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            current_weekday = weekday_names[datetime.now().weekday()]
            
            logger.info(f"🚀 启动爬虫系统 | {today} | 爬取最近7天数据({crawler.cutoff_date}至今) | 数据库已连接")
            
            # 立即开始爬取
            crawler.crawl_with_time_limit()
            
            logger.info("\n✅ 爬取任务完成！")
            
        except KeyboardInterrupt:
            logger.info("\n⚠️ 用户中断了爬取任务")
        except Exception as e:
            logger.error(f"\n❌ 爬取任务失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    else:
        # 定时运行模式（默认）
        logger.info("🚀 启动智能定时爬虫系统（中国招标投标公共服务平台）")
        logger.info("💡 提示: 使用 'python cebpubservice_spider.py --now' 或 'python wj_spiders/wj_cebpubservice_china.py --now' 可立即运行")
        
        # 创建爬虫实例（自动根据当前日期计算爬取天数）
        crawler = ScheduledCrawler()
        
        # 启动定时调度器
        crawler.run_scheduler()

if __name__ == "__main__":
    main()