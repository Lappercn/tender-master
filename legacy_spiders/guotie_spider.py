#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国铁采购平台爬虫
爬取当天的招标公告信息
"""

import undetected_chromedriver as uc
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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
            logging.FileHandler(os.path.join(log_dir, "guotie_spider.log"), mode='a', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

class GuotieSpider:
    def __init__(self, headless=True):
        self.base_url = "https://cg.95306.cn/baseinfor/notice/toBuyNoticeMore"
        self.params = {
            'bidType': '01',
            'noticeType': '01', 
            'transactionType': '01',
            'navigation': 'c',
            'wzType': '',
            'title': ''
        }
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
            self.driver = uc.Chrome(driver_executable_path=driver_path, options=options)
            
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
    
    def random_mouse_movement(self):
        """随机鼠标移动，模拟人工操作"""
        try:
            actions = ActionChains(self.driver)
            
            # 获取页面尺寸
            page_width = self.driver.execute_script("return window.innerWidth")
            page_height = self.driver.execute_script("return window.innerHeight")
            
            # 获取当前鼠标位置
            current_x = 0
            current_y = 0
            
            # 随机移动鼠标到页面不同位置
            for _ in range(random.randint(1, 3)):
                # 确保新位置在页面边界内
                new_x = random.randint(100, page_width - 100)
                new_y = random.randint(100, page_height - 100)
                
                # 计算相对移动距离
                move_x = new_x - current_x
                move_y = new_y - current_y
                
                # 移动鼠标
                actions.move_by_offset(move_x, move_y)
                actions.pause(random.uniform(0.1, 0.5))
                
                # 更新当前鼠标位置
                current_x = new_x
                current_y = new_y
            
            actions.perform()
            
        except Exception as e:
            logger.warning(f"鼠标移动操作出错: {e}")
    
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
            url = f"{self.base_url}?{'&'.join([f'{k}={v}' for k, v in self.params.items()])}"
            logger.info(f"🌐 访问页面: {url}")
            
            self.driver.get(url)
            self.human_like_wait("page_load")
            
            # 等待页面加载
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "text_con")))
            
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
            
            # 随机鼠标移动
            self.random_mouse_movement()
            
            # 查找页码输入框
            page_input = self.wait.until(EC.presence_of_element_located((By.ID, "jumptopage")))
            
            # 模拟人工输入行为
            page_input.clear()
            self.human_like_wait("before_click")
            
            # 逐字符输入，模拟人工打字
            for char in str(page_num):
                page_input.send_keys(char)
                time.sleep(random.uniform(0.1, 0.3))
            
            self.human_like_wait("before_click")
            
            # 点击Go按钮
            go_button = self.driver.find_element(By.CLASS_NAME, "buttonGo")
            go_button.click()
            
            # 等待页面加载
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "text_con")))
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
            # 标题
            title_element = notice_element.find_element(By.CSS_SELECTOR, ".htit a")
            title = title_element.get_attribute("title") or title_element.text.strip()
            
            # 发布日期
            date_element = notice_element.find_element(By.CSS_SELECTOR, ".declare_time span:last-child")
            publish_date = date_element.text.strip()
            
            # 公告ID (从onclick中提取)
            onclick = title_element.get_attribute("onclick")
            notice_id = re.search(r"noticeDetail\('([^']+)'\)", onclick)
            notice_id = notice_id.group(1) if notice_id else None
            
            # 尝试从href属性中提取ID作为备选方案
            if not notice_id:
                href = title_element.get_attribute("href")
                if href:
                    # 尝试从URL中提取ID
                    url_match = re.search(r'id=([^&]+)', href)
                    notice_id = url_match.group(1) if url_match else None
            
            # 如果仍然没有ID，生成一个基于标题和日期的唯一标识符
            if not notice_id:
                # 使用标题和日期生成唯一标识符
                notice_id = f"{title[:20]}_{publish_date}".replace(" ", "_")
            
            # 详情内容
            detail_element = notice_element.find_element(By.CLASS_NAME, "text_row_detail")
            detail = detail_element.text.strip()
            
            # 标签信息
            tags = []
            try:
                tag_elements = notice_element.find_elements(By.CSS_SELECTOR, ".row_tab_list li")
                tags = [tag.text.strip() for tag in tag_elements if tag.text.strip()]
            except:
                pass
            
            # 检查是否为当天数据
            if publish_date != self.today:
                return None
            
            # 将标签转换为逗号分隔的字符串
            keywords_str = ",".join(tags)
            
            # 构建真实的URL
            url = ""
            if notice_id:
                url = f"https://cg.95306.cn/baseinfor/notice/informationShow?id={notice_id}"
            
            # 构建符合目标结构的数据
            notice_data = {
                'contentId': notice_id,
                'area': "",  # 国铁数据中没有地区信息
                'briefText': detail,
                'budget': "",  # 国铁数据中没有预算信息
                'budget_label': "",  # 国铁数据中没有预算标签
                'crawl_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'createTime': publish_date,
                'hasAnnex': False,  # 国铁数据中没有附件信息
                'highlightedWords': keywords_str,  # 使用标签作为高亮词
                'keywords': keywords_str,  # 使用标签作为关键词
                'noticeType': "招标公告",  # 国铁采购平台主要是招标公告
                'tenderees': "",  # 国铁数据中没有招标人信息
                'title': title,
                'url': url,  # 真实的URL
                'agent': None,  # 国铁数据中没有代理信息
                'tenderEndTime': ""  # 国铁数据中没有投标截止时间
            }
            
            return notice_data
            
        except Exception as e:
            logger.warning(f"提取公告数据失败: {e}")
            return None
    
    def get_total_pages(self):
        """获取总页数"""
        try:
            # 查找分页信息
            page_info = self.driver.find_element(By.CSS_SELECTOR, ".page_div")
            page_text = page_info.text
            
            # 提取总页数
            match = re.search(r'共(\d+)页', page_text)
            if match:
                total_pages = int(match.group(1))
                logger.info(f"📄 总页数: {total_pages}")
                return total_pages
            else:
                logger.warning("无法获取总页数，使用默认值")
                return 1
                
        except Exception as e:
            logger.warning(f"获取总页数失败: {e}")
            return 1
    
    def crawl_page(self, page_num):
        """爬取单页数据"""
        try:
            # 等待公告列表加载
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "text_row")))
            
            # 获取所有公告元素
            notice_elements = self.driver.find_elements(By.CLASS_NAME, "text_row")
            logger.info(f"📋 第 {page_num} 页找到 {len(notice_elements)} 个公告")
            
            page_data = []
            today_count = 0
            
            for i, notice_element in enumerate(notice_elements):
                try:
                    notice_data = self.extract_notice_data(notice_element)
                    
                    if notice_data:
                        page_data.append(notice_data)
                        today_count += 1
                        logger.info(f"✅ 提取公告: {notice_data['title'][:50]}...")
                    else:
                        # 如果不是当天数据，说明已经翻过了当天的数据
                        logger.info(f"⏭️ 跳过非当天数据")
                        return page_data, True  # 返回True表示应该停止翻页
                    
                    # 随机等待，模拟人工阅读
                    self.human_like_wait("reading")
                    
                except Exception as e:
                    logger.warning(f"处理第 {i+1} 个公告时出错: {e}")
                    continue
            
            logger.info(f"📊 第 {page_num} 页提取到 {today_count} 个当天公告")
            return page_data, False  # 返回False表示可以继续翻页
            
        except Exception as e:
            logger.error(f"❌ 爬取第 {page_num} 页失败: {e}")
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
            logger.info("🚀 开始爬取国铁采购平台")
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
            
            while page_num <= total_pages and not should_stop:
                logger.info(f"🔄 正在爬取第 {page_num} 页...")
                
                # 爬取当前页
                page_data, should_stop = self.crawl_page(page_num)
                total_crawled += len(page_data)
                
                # 保存当前页数据
                saved_count = self.save_to_mongodb(page_data)
                total_saved += saved_count
                
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
                        logger.error(f"❌ 翻页失败，停止爬取: {e}")
                        break
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
    parser = argparse.ArgumentParser(description="国铁采购平台爬虫")
    parser.add_argument("--headless", action="store_true", default=True, help="无头模式运行")
    parser.add_argument("--visible", action="store_true", help="有头模式运行（调试用）")
    args = parser.parse_args()
    
    # 设置运行模式
    headless = not args.visible
    
    try:
        spider = GuotieSpider(headless=headless)
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
