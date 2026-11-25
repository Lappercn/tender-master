#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
军采网爬虫
爬取当天的招标公告信息
"""

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import time
import random
import json
import os
import logging
from datetime import datetime, timedelta
import re
from urllib.parse import urljoin, urlparse, parse_qs
import pymongo
from pymongo import MongoClient
import argparse

# 配置日志
def setup_logging():
    """配置日志系统"""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(log_dir, "plap_spider.log"), mode='a', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

class PlapSpider:
    def __init__(self, headless=True):
        self.base_url = "https://www.plap.mil.cn/freecms-glht/site/juncai/cggg/index.html"
        self.domain = "https://www.plap.mil.cn"
        self.headless = headless
        self.driver = None
        self.wait = None
        self.today = datetime.now().strftime('%Y-%m-%d')
        self.data = []
        
        # MongoDB连接
        self.client = MongoClient('localhost', 27017)
        self.db = self.client['qianlima']
        self.collection = self.db['tender_data']
        
        # 创建索引
        self.collection.create_index([("contentId", pymongo.ASCENDING)], unique=True)
        self.collection.create_index([("createTime", pymongo.DESCENDING)])
        
    def setup_driver(self):
        """设置Chrome驱动"""
        try:
            options = uc.ChromeOptions()
            
            if self.headless:
                options.add_argument('--headless')
            
            # 反检测配置 - 使用undetected_chromedriver兼容的方式
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-plugins')
            options.add_argument('--disable-images')  # 禁用图片加载，提高速度
            
            # 随机User-Agent
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'
            ]
            options.add_argument(f'--user-agent={random.choice(user_agents)}')
            
            # 窗口大小
            options.add_argument('--window-size=1920,1080')
            
            # 使用undetected_chromedriver，它会自动处理反检测
            driver_path = ChromeDriverManager().install()
            self.driver = uc.Chrome(driver_executable_path=driver_path, options=options, version_main=None)
            
            # 执行反检测脚本
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
            self.driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']})")
            
            self.wait = WebDriverWait(self.driver, 15)
            logger.info("✅ Chrome驱动初始化成功")
            
        except Exception as e:
            logger.error(f"❌ Chrome驱动初始化失败: {e}")
            raise
    
    def random_sleep(self, min_seconds=1, max_seconds=3):
        """随机等待时间"""
        time.sleep(random.uniform(min_seconds, max_seconds))
    
    def human_like_wait(self, action_type="normal"):
        """模拟人工等待，不同类型操作等待时间不同"""
        if action_type == "page_load":
            # 页面加载后等待
            time.sleep(random.uniform(3, 6))
        elif action_type == "before_click":
            # 点击前等待
            time.sleep(random.uniform(1, 3))
        elif action_type == "after_click":
            # 点击后等待
            time.sleep(random.uniform(2, 4))
        elif action_type == "page_turn":
            # 翻页操作等待
            time.sleep(random.uniform(5, 10))
        elif action_type == "reading":
            # 阅读内容等待
            time.sleep(random.uniform(2, 5))
        else:
            # 普通等待
            time.sleep(random.uniform(1, 3))
    
    def human_like_scroll(self):
        """模拟人工滚动"""
        try:
            # 随机滚动
            scroll_height = self.driver.execute_script("return document.body.scrollHeight")
            current_position = 0
            
            # 模拟人工滚动模式
            scroll_patterns = [
                (100, 200),  # 小步滚动
                (200, 400),  # 中步滚动
                (300, 500),  # 大步滚动
            ]
            
            while current_position < scroll_height:
                # 随机选择滚动模式
                min_step, max_step = random.choice(scroll_patterns)
                scroll_step = random.randint(min_step, max_step)
                current_position += scroll_step
                
                # 平滑滚动
                self.driver.execute_script(f"window.scrollTo(0, {current_position});")
                
                # 随机暂停，模拟阅读
                if random.random() < 0.3:  # 30%概率暂停
                    time.sleep(random.uniform(0.5, 2.0))
                else:
                    time.sleep(random.uniform(0.1, 0.4))
            
            # 回到顶部
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(random.uniform(0.5, 1.5))
            
        except Exception as e:
            logger.warning(f"滚动操作出错: {e}")
    
    def navigate_to_page(self, page_num=1):
        """导航到指定页面"""
        try:
            url = self.base_url
            logger.info(f"🌐 访问页面: {url}")
            
            self.driver.get(url)
            self.human_like_wait("page_load")
            
            # 等待页面加载
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "noticeShowList")))
            
            # 如果不是第一页，需要翻页
            if page_num > 1:
                self.go_to_page(page_num)
            
            # 模拟人工滚动
            self.human_like_scroll()
            
            logger.info(f"✅ 成功加载第 {page_num} 页")
            return True
            
        except TimeoutException:
            logger.error(f"❌ 页面加载超时: 第 {page_num} 页")
            return False
        except Exception as e:
            logger.error(f"❌ 页面导航失败: {e}")
            return False
    
    def go_to_page(self, page_num):
        """翻页到指定页码"""
        try:
            # 翻页前等待，模拟人工思考时间
            self.human_like_wait("page_turn")
            
            # 查找页码输入框
            page_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#pagination input[type='number']")))
            
            # 模拟人工输入行为
            page_input.clear()
            self.human_like_wait("before_click")
            
            # 逐字符输入，模拟人工打字
            for char in str(page_num):
                page_input.send_keys(char)
                time.sleep(random.uniform(0.1, 0.3))
            
            # 按回车键
            page_input.send_keys(u'\ue007')  # Enter键
            
            self.human_like_wait("before_click")
            
            # 等待页面加载
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "noticeShowList")))
            self.human_like_wait("page_load")
            
            # 模拟人工滚动
            self.human_like_scroll()
            
            logger.info(f"✅ 成功翻页到第 {page_num} 页")
            
        except Exception as e:
            logger.error(f"❌ 翻页失败: {e}")
            raise
    
    def extract_notice_data(self, notice_element):
        """提取单个公告数据"""
        try:
            # 获取所有span元素
            span_elements = notice_element.find_elements(By.CSS_SELECTOR, "span.ellipsis")
            
            # 标题
            title_element = notice_element.find_element(By.CSS_SELECTOR, "span.ellipsis > p.ellipsis")
            title = title_element.text.strip()
            
            # 链接
            link_element = notice_element.find_element(By.TAG_NAME, "a")
            relative_url = link_element.get_attribute("href")
            full_url = urljoin(self.domain, relative_url)
            
            # 从URL中提取contentId
            url_path = urlparse(relative_url).path
            content_id_match = re.search(r'/([^/]+)\.html$', url_path)
            content_id = content_id_match.group(1) if content_id_match else None
            
            # 从查询参数中获取noticeType
            query_params = parse_qs(urlparse(relative_url).query)
            notice_type_code = query_params.get('noticeType', [None])[0]
            
            # 项目所在地（第二个span）
            area = span_elements[1].text.strip() if len(span_elements) > 1 else ""
            
            # 采购方式（第三个span）
            purchase_method = span_elements[2].text.strip() if len(span_elements) > 2 else ""
            
            # 项目类别（第四个span）
            project_category = span_elements[3].text.strip() if len(span_elements) > 3 else ""
            
            # 发布时间（最后一个span）
            publish_date = span_elements[-1].text.strip() if span_elements else ""
            
            # 规范化发布日期格式，只保留日期部分
            normalized_publish_date = publish_date.strip()
            if len(normalized_publish_date) > 10:  # 如果包含时间，只取日期部分
                normalized_publish_date = normalized_publish_date[:10]
            
            # 检查是否为当天数据
            if normalized_publish_date != self.today:
                logger.info(f"跳过非当天数据: 公告日期 {normalized_publish_date} != 目标日期 {self.today}")
                return None
            
            # 构建关键词
            keywords_list = []
            if purchase_method and purchase_method != "无":
                keywords_list.append(purchase_method)
            if project_category and project_category != "无":
                keywords_list.append(project_category)
            keywords_str = ",".join(keywords_list)
            
            # 根据noticeType代码确定公告类型
            notice_type_mapping = {
                "001011": "招标公告",
                "001013": "招标公告",
                "001014": "招标公告",
                "001015": "招标公告",
                "59": "采购意向",
                "001021": "结果公示",
                "001023": "结果公示",
                "001024": "结果公示",
                "001032": "结果公示",
                "001006": "流标公告"
            }
            notice_type = notice_type_mapping.get(notice_type_code, "其他公告")
            
            # 构建符合目标结构的数据
            notice_data = {
                'contentId': content_id,
                'area': area,
                'briefText': title,
                'budget': "",  # 军采网数据中没有预算信息
                'budget_label': "",  # 军采网数据中没有预算标签
                'crawl_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'createTime': publish_date,
                'hasAnnex': False,  # 军采网数据中没有附件信息
                'highlightedWords': keywords_str,  # 使用采购方式和项目类别作为高亮词
                'keywords': keywords_str,  # 使用采购方式和项目类别作为关键词
                'noticeType': notice_type,
                'tenderees': "",  # 军采网数据中没有招标人信息
                'title': title,
                'url': full_url,  # 完整的URL
                'agent': None,  # 军采网数据中没有代理信息
                'tenderEndTime': ""  # 军采网数据中没有投标截止时间
            }
            
            return notice_data
            
        except Exception as e:
            logger.warning(f"提取公告数据失败: {e}")
            return None
    
    def get_total_pages(self):
        """获取总页数"""
        try:
            # 查找分页信息
            page_elements = self.driver.find_elements(By.CSS_SELECTOR, "#pagination .totalPage")
            
            # 遍历所有.totalPage元素，找到包含页数信息的那个
            for page_element in page_elements:
                page_text = page_element.text
                # 提取总页数
                match = re.search(r'共\s*(\d+)\s*页', page_text)
                if match:
                    total_pages = int(match.group(1))
                    logger.info(f"📄 总页数: {total_pages}")
                    return total_pages
            
            logger.warning("无法获取总页数，使用默认值")
            return 100  # 设置一个较大的默认值，确保能翻页
                
        except Exception as e:
            logger.warning(f"获取总页数失败: {e}")
            return 100  # 设置一个较大的默认值，确保能翻页
    
    def crawl_page(self, page_num):
        """爬取单页数据"""
        try:
            # 等待公告列表加载
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "noticeShowList")))
            
            # 获取所有公告元素
            notice_elements = self.driver.find_elements(By.CSS_SELECTOR, "ul.noticeShowList > li")
            logger.info(f"📋 第 {page_num} 页找到 {len(notice_elements)} 个公告")
            
            page_data = []
            today_count = 0
            non_today_found = False  # 标记是否遇到了非当天数据
            
            for i, notice_element in enumerate(notice_elements):
                try:
                    notice_data = self.extract_notice_data(notice_element)
                    
                    if notice_data:
                        page_data.append(notice_data)
                        today_count += 1
                        logger.info(f"✅ 提取公告: {notice_data['title'][:50]}...")
                    else:
                        # 如果不是当天数据，说明已经翻过了当天的数据
                        non_today_found = True
                        logger.info(f"⏭️ 跳过非当天数据")
                    
                    # 随机等待，模拟人工阅读
                    self.human_like_wait("reading")
                    
                except Exception as e:
                    logger.warning(f"处理第 {i+1} 个公告时出错: {e}")
                    continue
            
            logger.info(f"📊 第 {page_num} 页提取到 {today_count} 个当天公告")
            return page_data, non_today_found  # 返回是否遇到非当天数据
            
        except Exception as e:
            logger.error(f"❌ 爬取第 {page_num} 页失败: {e}")
            # 如果是浏览器连接问题，我们不应该停止翻页，而是应该尝试重新连接
            if "invalid session id" in str(e) or "disconnected" in str(e):
                logger.warning("浏览器连接断开，将在下一轮重新初始化驱动")
                # 返回空数据但不建议停止翻页，让主循环决定是否重试
                return [], False
            return [], False
    
    def save_to_mongodb(self, data_list):
        """保存数据到MongoDB"""
        try:
            if not data_list:
                logger.info("📝 没有新数据需要保存")
                return 0
            
            saved_count = 0
            for data in data_list:
                try:
                    # 使用contentId作为唯一标识，避免重复
                    if data.get('contentId'):
                        self.collection.update_one(
                            {'contentId': data['contentId']},
                            {'$set': data},
                            upsert=True
                        )
                    else:
                        # 如果没有contentId，使用标题和日期作为唯一标识
                        self.collection.update_one(
                            {
                                'title': data['title'],
                                'createTime': data['createTime']
                            },
                            {'$set': data},
                            upsert=True
                        )
                    saved_count += 1
                    
                except Exception as e:
                    logger.warning(f"保存数据失败: {e}")
                    continue
            
            logger.info(f"💾 成功保存 {saved_count} 条数据到MongoDB")
            return saved_count
            
        except Exception as e:
            logger.error(f"❌ 保存到MongoDB失败: {e}")
            return 0
    
    def run(self):
        """运行爬虫"""
        try:
            logger.info("🚀 开始爬取军采网")
            logger.info(f"📅 目标日期: {self.today}")
            
            # 初始化驱动
            self.setup_driver()
            
            # 访问第一页
            if not self.navigate_to_page(1):
                raise Exception("无法访问网站")
            
            # 获取总页数
            total_pages = self.get_total_pages()
            
            # 爬取数据
            total_crawled = 0
            total_saved = 0
            page_num = 1
            should_stop = False
            consecutive_errors = 0  # 连续错误计数
            max_consecutive_errors = 3  # 最大连续错误次数
            
            while page_num <= total_pages and not should_stop:
                logger.info(f"🔄 正在爬取第 {page_num} 页...")
                
                # 爬取当前页
                page_data, should_stop = self.crawl_page(page_num)
                total_crawled += len(page_data)
                
                # 保存当前页数据
                saved_count = self.save_to_mongodb(page_data)
                total_saved += saved_count
                
                # 检查是否有数据被爬取
                if len(page_data) == 0 and not should_stop:
                    consecutive_errors += 1
                    logger.warning(f"第 {page_num} 页没有爬取到数据，连续错误次数: {consecutive_errors}")
                    
                    # 如果连续错误次数超过最大值，重新初始化驱动
                    if consecutive_errors >= max_consecutive_errors:
                        logger.warning("连续错误次数过多，重新初始化驱动...")
                        if self.driver:
                            try:
                                self.driver.quit()
                            except:
                                pass
                        self.setup_driver()
                        consecutive_errors = 0  # 重置错误计数
                        # 重新访问当前页
                        if not self.navigate_to_page(page_num):
                            logger.error(f"重新访问第 {page_num} 页失败")
                            break
                        continue  # 重新尝试当前页
                else:
                    consecutive_errors = 0  # 重置错误计数
                
                if should_stop:
                    logger.info("⏹️ 已翻过当天数据，停止翻页")
                    break
                
                # 准备翻页
                if page_num < total_pages:
                    page_num += 1
                    # 翻页前额外等待，避免过快翻页
                    logger.info(f"⏳ 准备翻页到第 {page_num} 页，等待中...")
                    self.human_like_wait("page_turn")
                    
                    # 翻页
                    try:
                        self.go_to_page(page_num)
                    except Exception as e:
                        logger.error(f"❌ 翻页失败: {e}")
                        # 遇到翻页错误时，重新初始化驱动并重试
                        if self.driver:
                            try:
                                self.driver.quit()
                            except:
                                pass
                        self.setup_driver()
                        # 重新访问目标页
                        if not self.navigate_to_page(page_num):
                            logger.error(f"重新访问第 {page_num} 页失败，停止爬取")
                            break
                        continue  # 重新尝试当前页
                else:
                    break
            
            logger.info(f"🎉 爬取完成！共获取 {total_crawled} 条当天数据，保存 {total_saved} 条")
            
            return {
                'total_crawled': total_crawled,
                'total_saved': total_saved,
                'date': self.today
            }
            
        except Exception as e:
            logger.error(f"❌ 爬虫运行失败: {e}")
            raise
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("🔚 浏览器已关闭")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="军采网爬虫")
    parser.add_argument("--headless", action="store_true", default=True, help="无头模式运行")
    parser.add_argument("--visible", action="store_true", help="有头模式运行（调试用）")
    args = parser.parse_args()
    
    # 设置运行模式
    headless = not args.visible
    
    try:
        spider = PlapSpider(headless=headless)
        result = spider.run()
        
        print(f"\n📊 爬取结果:")
        print(f"   总爬取数量: {result['total_crawled']}")
        print(f"   成功保存数量: {result['total_saved']}")
        print(f"   目标日期: {result['date']}")
        
    except Exception as e:
        logger.error(f"❌ 程序执行失败: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
