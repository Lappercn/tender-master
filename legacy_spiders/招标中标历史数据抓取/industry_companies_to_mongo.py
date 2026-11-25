#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行业和企业名单数据存储到MongoDB脚本
将各行业Top10企业/机构名单存储到hawkeye数据库
适配新的前端数据结构

使用方法:
1. 批量插入(清空现有数据): python test.py --mode insert --clear
2. 批量插入(保留现有数据): python test.py --mode insert --no-clear
3. 更新插入模式: python test.py --mode upsert
4. 查看统计信息: python test.py --mode stats

环境变量:
- MONGO_URI: MongoDB连接字符串 (默认: mongodb://localhost:27017/hawkeye)

数据结构适配:
- 添加了status、priority等新字段
- 支持可选字段如website、contact、description等
- 使用UTC时间戳
- 增强的索引支持
- 数据验证功能
"""

import pymongo
import logging
from datetime import datetime
from typing import List, Dict, Any
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/industry_companies_mongo.log", mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# MongoDB连接配置
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/hawkeye')
DATABASE_NAME = "hawkeye"
COLLECTION_NAME = "industry_companies"

class IndustryCompaniesManager:
    def __init__(self):
        """初始化MongoDB连接"""
        try:
            self.client = pymongo.MongoClient(MONGO_URI)
            self.db = self.client[DATABASE_NAME]
            self.collection = self.db[COLLECTION_NAME]
            logging.info(f"成功连接到MongoDB数据库: {DATABASE_NAME}")
        except Exception as e:
            logging.error(f"连接MongoDB失败: {e}")
            raise

    def prepare_data(self) -> List[Dict[str, Any]]:
        """准备要插入的数据"""
        data = []
        
        # 银行业
        banking_companies = [
            {"rank": 1, "name": "中国工商银行", "note": "宇宙行", "type": "国有银行"},
            {"rank": 2, "name": "中国建设银行", "note": "", "type": "国有银行"},
            {"rank": 3, "name": "中国农业银行", "note": "", "type": "国有银行"},
            {"rank": 4, "name": "中国银行", "note": "", "type": "国有银行"},
            {"rank": 5, "name": "交通银行", "note": "", "type": "国有银行"},
            {"rank": 6, "name": "招商银行", "note": "零售之王", "type": "股份制银行"},
            {"rank": 7, "name": "邮储银行", "note": "", "type": "国有银行"},
            {"rank": 8, "name": "兴业银行", "note": "", "type": "股份制银行"},
            {"rank": 9, "name": "中信银行", "note": "", "type": "股份制银行"},
            {"rank": 10, "name": "浦发银行", "note": "", "type": "股份制银行"}
        ]
        
        # 烟草业
        tobacco_companies = [
            {"rank": 1, "name": "中国烟草总公司", "note": "年利税超万亿", "type": "央企"},
            {"rank": 2, "name": "上海烟草集团", "note": "中华", "type": "地方国企"},
            {"rank": 3, "name": "云南中烟", "note": "云烟、玉溪", "type": "地方国企"},
            {"rank": 4, "name": "湖南中烟", "note": "芙蓉王", "type": "地方国企"},
            {"rank": 5, "name": "浙江中烟", "note": "利群", "type": "地方国企"},
            {"rank": 6, "name": "贵州中烟", "note": "贵烟", "type": "地方国企"},
            {"rank": 7, "name": "广东中烟", "note": "双喜", "type": "地方国企"},
            {"rank": 8, "name": "湖北中烟", "note": "黄鹤楼", "type": "地方国企"},
            {"rank": 9, "name": "江苏中烟", "note": "南京", "type": "地方国企"},
            {"rank": 10, "name": "川渝中烟", "note": "娇子", "type": "地方国企"}
        ]
        
        # 酒业
        liquor_companies = [
            {"rank": 1, "name": "贵州茅台", "note": "酱香龙头", "type": "上市公司"},
            {"rank": 2, "name": "五粮液", "note": "浓香之王", "type": "上市公司"},
            {"rank": 3, "name": "洋河股份", "note": "梦之蓝", "type": "上市公司"},
            {"rank": 4, "name": "泸州老窖", "note": "国窖1573", "type": "上市公司"},
            {"rank": 5, "name": "山西汾酒", "note": "清香代表", "type": "上市公司"},
            {"rank": 6, "name": "郎酒", "note": "青花郎", "type": "民营企业"},
            {"rank": 7, "name": "古井贡酒", "note": "徽酒龙头", "type": "上市公司"},
            {"rank": 8, "name": "剑南春", "note": "水晶剑", "type": "民营企业"},
            {"rank": 9, "name": "习酒", "note": "君品", "type": "民营企业"},
            {"rank": 10, "name": "舍得酒业", "note": "沱牌", "type": "上市公司"}
        ]
        
        # 车企
        automotive_companies = [
            {"rank": 1, "name": "比亚迪", "note": "新能源全球销冠", "type": "上市公司"},
            {"rank": 2, "name": "上汽集团", "note": "合资+自主", "type": "国有企业"},
            {"rank": 3, "name": "一汽集团", "note": "红旗", "type": "央企"},
            {"rank": 4, "name": "东风汽车", "note": "岚图", "type": "央企"},
            {"rank": 5, "name": "广汽集团", "note": "埃安", "type": "国有企业"},
            {"rank": 6, "name": "长安汽车", "note": "深蓝", "type": "国有企业"},
            {"rank": 7, "name": "吉利汽车", "note": "极氪", "type": "民营企业"},
            {"rank": 8, "name": "长城汽车", "note": "哈弗", "type": "民营企业"},
            {"rank": 9, "name": "蔚来", "note": "高端电动", "type": "民营企业"},
            {"rank": 10, "name": "理想", "note": "增程技术", "type": "民营企业"}
        ]
        
        # 保险业
        insurance_companies = [
            {"rank": 1, "name": "中国人寿", "note": "寿险龙头", "type": "央企"},
            {"rank": 2, "name": "中国平安", "note": "综合金融", "type": "上市公司"},
            {"rank": 3, "name": "中国人保", "note": "PICC", "type": "央企"},
            {"rank": 4, "name": "中国太保", "note": "太平洋保险", "type": "上市公司"},
            {"rank": 5, "name": "新华保险", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "泰康保险", "note": "养老社区", "type": "民营企业"},
            {"rank": 7, "name": "太平保险", "note": "央企", "type": "央企"},
            {"rank": 8, "name": "阳光保险", "note": "", "type": "民营企业"},
            {"rank": 9, "name": "友邦保险", "note": "外资", "type": "外资"},
            {"rank": 10, "name": "众安保险", "note": "互联网", "type": "上市公司"}
        ]
        
        # 出版社
        publishing_companies = [
            {"rank": 1, "name": "中国出版集团", "note": "国家级", "type": "央企"},
            {"rank": 2, "name": "中信出版", "note": "商业图书", "type": "上市公司"},
            {"rank": 3, "name": "商务印书馆", "note": "工具书", "type": "央企"},
            {"rank": 4, "name": "人民文学出版社", "note": "文学经典", "type": "央企"},
            {"rank": 5, "name": "高等教育出版社", "note": "教材", "type": "央企"},
            {"rank": 6, "name": "科学出版社", "note": "学术", "type": "央企"},
            {"rank": 7, "name": "外研社", "note": "外语教育", "type": "央企"},
            {"rank": 8, "name": "上海世纪出版集团", "note": "", "type": "地方国企"},
            {"rank": 9, "name": "浙江教育出版社", "note": "", "type": "地方国企"},
            {"rank": 10, "name": "电子工业出版社", "note": "科技类", "type": "央企"}
        ]
        
        # 能源电力
        energy_companies = [
            {"rank": 1, "name": "国家电网", "note": "", "type": "央企"},
            {"rank": 2, "name": "南方电网", "note": "", "type": "央企"},
            {"rank": 3, "name": "中国华能", "note": "", "type": "央企"},
            {"rank": 4, "name": "国家电投", "note": "", "type": "央企"},
            {"rank": 5, "name": "中国三峡集团", "note": "", "type": "央企"},
            {"rank": 6, "name": "中国广核", "note": "", "type": "央企"},
            {"rank": 7, "name": "华润电力", "note": "", "type": "央企"},
            {"rank": 8, "name": "协鑫集团", "note": "光伏龙头", "type": "民营企业"},
            {"rank": 9, "name": "隆基绿能", "note": "单晶硅", "type": "上市公司"},
            {"rank": 10, "name": "宁德时代", "note": "储能", "type": "上市公司"}
        ]
        
        # 公路
        highway_companies = [
            {"rank": 1, "name": "中国交建", "note": "", "type": "央企"},
            {"rank": 2, "name": "山东高速集团", "note": "", "type": "地方国企"},
            {"rank": 3, "name": "招商公路", "note": "", "type": "央企"},
            {"rank": 4, "name": "四川成渝高速", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "江苏交通控股", "note": "", "type": "地方国企"},
            {"rank": 6, "name": "浙江沪杭甬高速", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "广东交通集团", "note": "", "type": "地方国企"},
            {"rank": 8, "name": "安徽交控集团", "note": "", "type": "地方国企"},
            {"rank": 9, "name": "福建高速", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "河南交投", "note": "", "type": "地方国企"}
        ]
        
        # 房屋建筑
        construction_companies = [
            {"rank": 1, "name": "中国建筑", "note": "", "type": "央企"},
            {"rank": 2, "name": "中国中铁", "note": "", "type": "央企"},
            {"rank": 3, "name": "中国铁建", "note": "", "type": "央企"},
            {"rank": 4, "name": "上海建工", "note": "", "type": "地方国企"},
            {"rank": 5, "name": "北京城建集团", "note": "", "type": "地方国企"},
            {"rank": 6, "name": "华润置地", "note": "", "type": "央企"},
            {"rank": 7, "name": "保利发展", "note": "", "type": "央企"},
            {"rank": 8, "name": "万科企业", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "龙湖集团", "note": "", "type": "民营企业"},
            {"rank": 10, "name": "金地集团", "note": "", "type": "上市公司"}
        ]
        
        # 化学工业
        chemical_companies = [
            {"rank": 1, "name": "中国中化", "note": "合并中化与中国化工", "type": "央企"},
            {"rank": 2, "name": "万华化学", "note": "MDI全球第一", "type": "上市公司"},
            {"rank": 3, "name": "荣盛石化", "note": "", "type": "上市公司"},
            {"rank": 4, "name": "恒力石化", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "浙江龙盛", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "华鲁恒升", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "新和成", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "云天化", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "湖北宜化", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "卫星化学", "note": "", "type": "上市公司"}
        ]
        
        # 石油石化
        petrochemical_companies = [
            {"rank": 1, "name": "中国石油", "note": "", "type": "央企"},
            {"rank": 2, "name": "中国石化", "note": "", "type": "央企"},
            {"rank": 3, "name": "中海油", "note": "", "type": "央企"},
            {"rank": 4, "name": "恒力石化", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "荣盛石化", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "上海石化", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "东华能源", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "桐昆股份", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "东方盛虹", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "宝丰能源", "note": "", "type": "上市公司"}
        ]
        
        # 铁路
        railway_companies = [
            {"rank": 1, "name": "国铁集团", "note": "", "type": "央企"},
            {"rank": 2, "name": "中国中车", "note": "", "type": "央企"},
            {"rank": 3, "name": "中国通号", "note": "", "type": "央企"},
            {"rank": 4, "name": "京沪高铁", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "广深铁路", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "中铁特货", "note": "", "type": "央企"},
            {"rank": 7, "name": "中铁集装箱", "note": "", "type": "央企"},
            {"rank": 8, "name": "中国铁物", "note": "", "type": "央企"},
            {"rank": 9, "name": "阿尔斯通中国", "note": "", "type": "外资"},
            {"rank": 10, "name": "卡斯柯信号", "note": "", "type": "合资"}
        ]
        
        # 园林绿化
        landscaping_companies = [
            {"rank": 1, "name": "东方园林", "note": "", "type": "上市公司"},
            {"rank": 2, "name": "岭南股份", "note": "", "type": "上市公司"},
            {"rank": 3, "name": "棕榈股份", "note": "", "type": "上市公司"},
            {"rank": 4, "name": "杭州园林", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "美尚生态", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "乾景园林", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "文科园林", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "普邦股份", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "农尚环境", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "大千生态", "note": "", "type": "上市公司"}
        ]
        
        # 生物医药
        biomedical_companies = [
            {"rank": 1, "name": "国药集团", "note": "", "type": "央企"},
            {"rank": 2, "name": "华润医药", "note": "", "type": "央企"},
            {"rank": 3, "name": "恒瑞医药", "note": "", "type": "上市公司"},
            {"rank": 4, "name": "药明康德", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "迈瑞医疗", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "智飞生物", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "百济神州", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "复星医药", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "石药集团", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "中国生物制药", "note": "", "type": "上市公司"}
        ]
        
        # 水利水电
        water_power_companies = [
            {"rank": 1, "name": "中国电建", "note": "", "type": "央企"},
            {"rank": 2, "name": "中国能建", "note": "", "type": "央企"},
            {"rank": 3, "name": "三峡集团", "note": "", "type": "央企"},
            {"rank": 4, "name": "葛洲坝集团", "note": "", "type": "央企"},
            {"rank": 5, "name": "安徽水利", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "粤水电", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "钱江水利", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "大禹节水", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "新界泵业", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "青龙管业", "note": "", "type": "上市公司"}
        ]
        
        # 水运
        shipping_companies = [
            {"rank": 1, "name": "中远海运", "note": "", "type": "央企"},
            {"rank": 2, "name": "招商轮船", "note": "", "type": "央企"},
            {"rank": 3, "name": "中国船舶", "note": "", "type": "央企"},
            {"rank": 4, "name": "中集集团", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "宁波舟山港", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "上港集团", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "青岛港", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "天津港", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "珠海港", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "北部湾港", "note": "", "type": "上市公司"}
        ]
        
        # 港口航道
        port_companies = [
            {"rank": 1, "name": "招商港口", "note": "", "type": "央企"},
            {"rank": 2, "name": "上港集团", "note": "", "type": "上市公司"},
            {"rank": 3, "name": "宁波舟山港", "note": "", "type": "上市公司"},
            {"rank": 4, "name": "青岛港", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "天津港", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "广州港", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "厦门港务", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "北部湾港", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "盐田港", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "唐山港", "note": "", "type": "上市公司"}
        ]
        
        # 纺织轻工
        textile_companies = [
            {"rank": 1, "name": "恒力集团", "note": "化纤", "type": "上市公司"},
            {"rank": 2, "name": "魏桥创业", "note": "纺织", "type": "上市公司"},
            {"rank": 3, "name": "安踏体育", "note": "", "type": "上市公司"},
            {"rank": 4, "name": "海澜之家", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "鲁泰纺织", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "华孚时尚", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "申洲国际", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "百隆东方", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "森马服饰", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "太平鸟", "note": "", "type": "上市公司"}
        ]
        
        # 矿产冶金
        mining_companies = [
            {"rank": 1, "name": "中国宝武", "note": "钢铁", "type": "央企"},
            {"rank": 2, "name": "中国铝业", "note": "", "type": "央企"},
            {"rank": 3, "name": "中国五矿", "note": "", "type": "央企"},
            {"rank": 4, "name": "紫金矿业", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "江西铜业", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "洛阳钼业", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "山东黄金", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "北方稀土", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "天齐锂业", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "赣锋锂业", "note": "", "type": "上市公司"}
        ]
        
        # 民航
        aviation_companies = [
            {"rank": 1, "name": "中国国航", "note": "", "type": "央企"},
            {"rank": 2, "name": "东方航空", "note": "", "type": "央企"},
            {"rank": 3, "name": "南方航空", "note": "", "type": "央企"},
            {"rank": 4, "name": "海南航空", "note": "", "type": "民营企业"},
            {"rank": 5, "name": "厦门航空", "note": "", "type": "国有企业"},
            {"rank": 6, "name": "深圳航空", "note": "", "type": "国有企业"},
            {"rank": 7, "name": "四川航空", "note": "", "type": "国有企业"},
            {"rank": 8, "name": "春秋航空", "note": "", "type": "民营企业"},
            {"rank": 9, "name": "吉祥航空", "note": "", "type": "民营企业"},
            {"rank": 10, "name": "中国航信", "note": "", "type": "央企"}
        ]
        
        # 生态环保
        environmental_companies = [
            {"rank": 1, "name": "中国节能环保集团", "note": "", "type": "央企"},
            {"rank": 2, "name": "北控水务", "note": "", "type": "上市公司"},
            {"rank": 3, "name": "首创环保", "note": "", "type": "上市公司"},
            {"rank": 4, "name": "碧水源", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "高能环境", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "维尔利", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "中再资环", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "绿色动力", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "上海环境", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "瀚蓝环境", "note": "", "type": "上市公司"}
        ]
        
        # 地球科学
        geoscience_companies = [
            {"rank": 1, "name": "中国地质调查局", "note": "", "type": "事业单位"},
            {"rank": 2, "name": "中国地震局", "note": "", "type": "事业单位"},
            {"rank": 3, "name": "中国气象局", "note": "", "type": "事业单位"},
            {"rank": 4, "name": "中化地质矿山总局", "note": "", "type": "央企"},
            {"rank": 5, "name": "中国冶金地质总局", "note": "", "type": "央企"},
            {"rank": 6, "name": "东方地球物理勘探", "note": "中石油", "type": "央企"},
            {"rank": 7, "name": "中海油服", "note": "", "type": "央企"},
            {"rank": 8, "name": "卫星遥感", "note": "航天宏图", "type": "上市公司"},
            {"rank": 9, "name": "北斗导航", "note": "合众思壮", "type": "上市公司"},
            {"rank": 10, "name": "四维图新", "note": "", "type": "上市公司"}
        ]
        
        # 信息电子
        it_companies = [
            {"rank": 1, "name": "华为", "note": "", "type": "民营企业"},
            {"rank": 2, "name": "中兴通讯", "note": "", "type": "上市公司"},
            {"rank": 3, "name": "京东方", "note": "", "type": "上市公司"},
            {"rank": 4, "name": "紫光集团", "note": "", "type": "国有企业"},
            {"rank": 5, "name": "中芯国际", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "联想集团", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "小米科技", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "海康威视", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "大疆创新", "note": "", "type": "民营企业"},
            {"rank": 10, "name": "寒武纪", "note": "AI芯片", "type": "上市公司"}
        ]
        
        # 市政
        municipal_companies = [
            {"rank": 1, "name": "北京城建", "note": "", "type": "地方国企"},
            {"rank": 2, "name": "上海城投", "note": "", "type": "地方国企"},
            {"rank": 3, "name": "深圳水务集团", "note": "", "type": "地方国企"},
            {"rank": 4, "name": "成都兴城集团", "note": "", "type": "地方国企"},
            {"rank": 5, "name": "武汉城建集团", "note": "", "type": "地方国企"},
            {"rank": 6, "name": "重庆城投", "note": "", "type": "地方国企"},
            {"rank": 7, "name": "广州城投", "note": "", "type": "地方国企"},
            {"rank": 8, "name": "杭州城投", "note": "", "type": "地方国企"},
            {"rank": 9, "name": "宁波城投", "note": "", "type": "地方国企"},
            {"rank": 10, "name": "青岛城投", "note": "", "type": "地方国企"}
        ]
        
        # 广电通信
        telecom_companies = [
            {"rank": 1, "name": "中国广电", "note": "", "type": "央企"},
            {"rank": 2, "name": "中国移动", "note": "", "type": "央企"},
            {"rank": 3, "name": "中国电信", "note": "", "type": "央企"},
            {"rank": 4, "name": "中国联通", "note": "", "type": "央企"},
            {"rank": 5, "name": "华为", "note": "", "type": "民营企业"},
            {"rank": 6, "name": "中兴通讯", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "烽火通信", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "长飞光纤", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "亨通光电", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "中天科技", "note": "", "type": "上市公司"}
        ]
        
        # 科教文卫
        education_companies = [
            {"rank": 1, "name": "中国科学院", "note": "", "type": "事业单位"},
            {"rank": 2, "name": "中国工程院", "note": "", "type": "事业单位"},
            {"rank": 3, "name": "北京大学", "note": "", "type": "事业单位"},
            {"rank": 4, "name": "清华大学", "note": "", "type": "事业单位"},
            {"rank": 5, "name": "复旦大学", "note": "", "type": "事业单位"},
            {"rank": 6, "name": "上海交通大学", "note": "", "type": "事业单位"},
            {"rank": 7, "name": "浙江大学", "note": "", "type": "事业单位"},
            {"rank": 8, "name": "中山大学", "note": "", "type": "事业单位"},
            {"rank": 9, "name": "华西医院", "note": "", "type": "事业单位"},
            {"rank": 10, "name": "协和医院", "note": "", "type": "事业单位"}
        ]
        
        # 商业服务
        business_service_companies = [
            {"rank": 1, "name": "阿里巴巴", "note": "", "type": "上市公司"},
            {"rank": 2, "name": "腾讯", "note": "", "type": "上市公司"},
            {"rank": 3, "name": "京东", "note": "", "type": "上市公司"},
            {"rank": 4, "name": "美团", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "字节跳动", "note": "", "type": "民营企业"},
            {"rank": 6, "name": "拼多多", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "携程", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "顺丰控股", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "滴滴出行", "note": "", "type": "民营企业"},
            {"rank": 10, "name": "贝壳找房", "note": "", "type": "上市公司"}
        ]
        
        # 农林牧渔
        agriculture_companies = [
            {"rank": 1, "name": "中粮集团", "note": "", "type": "央企"},
            {"rank": 2, "name": "中化农业", "note": "", "type": "央企"},
            {"rank": 3, "name": "新希望集团", "note": "", "type": "上市公司"},
            {"rank": 4, "name": "温氏股份", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "牧原股份", "note": "", "type": "上市公司"},
            {"rank": 6, "name": "海大集团", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "北大荒集团", "note": "", "type": "央企"},
            {"rank": 8, "name": "隆平高科", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "通威股份", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "正邦科技", "note": "", "type": "上市公司"}
        ]
        
        # 机械设备
        machinery_companies = [
            {"rank": 1, "name": "中国机械工业集团", "note": "", "type": "央企"},
            {"rank": 2, "name": "三一重工", "note": "", "type": "上市公司"},
            {"rank": 3, "name": "中联重科", "note": "", "type": "上市公司"},
            {"rank": 4, "name": "徐工机械", "note": "", "type": "上市公司"},
            {"rank": 5, "name": "中国中车", "note": "", "type": "央企"},
            {"rank": 6, "name": "陕鼓动力", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "沈阳机床", "note": "", "type": "上市公司"},
            {"rank": 8, "name": "振华重工", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "杰克股份", "note": "", "type": "上市公司"},
            {"rank": 10, "name": "埃斯顿", "note": "机器人", "type": "上市公司"}
        ]
        
        # 航空航天
        aerospace_companies = [
            {"rank": 1, "name": "中国航天科技", "note": "", "type": "央企"},
            {"rank": 2, "name": "中国航天科工", "note": "", "type": "央企"},
            {"rank": 3, "name": "中国航空工业", "note": "", "type": "央企"},
            {"rank": 4, "name": "中国商飞", "note": "", "type": "央企"},
            {"rank": 5, "name": "中国航发", "note": "", "type": "央企"},
            {"rank": 6, "name": "北斗星通", "note": "", "type": "上市公司"},
            {"rank": 7, "name": "中航无人机", "note": "", "type": "央企"},
            {"rank": 8, "name": "航天宏图", "note": "", "type": "上市公司"},
            {"rank": 9, "name": "银河航天", "note": "", "type": "民营企业"},
            {"rank": 10, "name": "蓝箭航天", "note": "", "type": "民营企业"}
        ]
        
        # 旅游业
        tourism_companies = [
            {"rank": 1, "name": "中国旅游集团", "note": "免税店（中免）、景区运营", "type": "央企"},
            {"rank": 2, "name": "携程集团", "note": "OTA平台（携程、去哪儿）", "type": "民营企业"},
            {"rank": 3, "name": "同程旅行", "note": "在线预订、交通票务", "type": "民营企业"},
            {"rank": 4, "name": "华侨城集团", "note": "欢乐谷、文旅综合体", "type": "央企"},
            {"rank": 5, "name": "首旅集团", "note": "酒店（如家）、景区（环球影城）", "type": "地方国企"},
            {"rank": 6, "name": "美团", "note": "本地生活、景区门票", "type": "民营企业"},
            {"rank": 7, "name": "锦江国际集团", "note": "酒店（锦江、铂涛）", "type": "地方国企"},
            {"rank": 8, "name": "复星旅文", "note": "三亚亚特兰蒂斯、Club Med", "type": "民营企业"},
            {"rank": 9, "name": "中青旅", "note": "乌镇、古北水镇", "type": "央企"},
            {"rank": 10, "name": "凯撒旅业", "note": "出境游、高端定制", "type": "民营企业"}
        ]
        
        # 电商平台
        ecommerce_companies = [
            {"rank": 1, "name": "天猫", "note": "B2C旗舰店模式，品牌正品保障", "type": "阿里巴巴集团", "market_share": "占中国电商市场37%"},
            {"rank": 2, "name": "京东", "note": "自营物流（24小时达），3C家电优势", "type": "京东集团", "market_share": "年交易额2万亿"},
            {"rank": 3, "name": "拼多多", "note": "社交拼团+农产品上行，低价策略", "type": "拼多多", "market_share": "年度活跃买家近6亿"},
            {"rank": 4, "name": "淘宝", "note": "C2C海量商品，个人商家为主", "type": "阿里巴巴集团", "market_share": "全球年度活跃消费者9.6亿"},
            {"rank": 5, "name": "唯品会", "note": "品牌特卖，深度折扣限时抢购", "type": "唯品会", "market_share": "特卖电商领域标杆"},
            {"rank": 6, "name": "抖音电商", "note": "短视频+直播带货，内容电商新势力", "type": "字节跳动", "market_share": "2025年增速超50%"},
            {"rank": 7, "name": "苏宁易购", "note": "线上线下融合，家电数码优势", "type": "苏宁集团", "market_share": "覆盖家电品类超80%"},
            {"rank": 8, "name": "快手电商", "note": "直播带货，下沉市场用户占比高", "type": "快手科技", "market_share": "商品类目丰富度TOP3"},
            {"rank": 9, "name": "小红书", "note": "生活方式分享+种草电商", "type": "小红书", "market_share": "女性用户占比75%"},
            {"rank": 10, "name": "美团", "note": "本地生活服务（外卖、到店）延伸至即时零售", "type": "美团点评", "market_share": "交易用户超4.5亿"}
        ]
        
        # 乳业
        dairy_companies = [
            {"rank": 1, "name": "伊利集团", "note": "金典、安慕希、QQ星", "type": "民营企业"},
            {"rank": 2, "name": "蒙牛乳业", "note": "特仑苏、纯甄、冠益乳", "type": "民营企业"},
            {"rank": 3, "name": "中国飞鹤", "note": "星飞帆、臻稚有机", "type": "民营企业"},
            {"rank": 4, "name": "光明乳业", "note": "莫斯利安、优倍", "type": "地方国企"},
            {"rank": 5, "name": "君乐宝乳业", "note": "简醇、优萃", "type": "民营企业"},
            {"rank": 6, "name": "三元食品", "note": "极致、爱力优", "type": "地方国企"},
            {"rank": 7, "name": "新希望乳业", "note": "24小时、活润", "type": "民营企业"},
            {"rank": 8, "name": "澳优乳业", "note": "佳贝艾特（羊奶粉）", "type": "外资控股"},
            {"rank": 9, "name": "贝因美", "note": "爱加、菁爱", "type": "民营企业"},
            {"rank": 10, "name": "完达山乳业", "note": "黑沃、菁采", "type": "央企子公司"}
        ]
        
        # 组织数据结构
        industries = [
            {"industry": "银行", "companies": banking_companies},
            {"industry": "烟草", "companies": tobacco_companies},
            {"industry": "酒业", "companies": liquor_companies},
            {"industry": "车企", "companies": automotive_companies},
            {"industry": "保险", "companies": insurance_companies},
            {"industry": "出版社", "companies": publishing_companies},
            {"industry": "能源电力", "companies": energy_companies},
            {"industry": "公路", "companies": highway_companies},
            {"industry": "房屋建筑", "companies": construction_companies},
            {"industry": "化学工业", "companies": chemical_companies},
            {"industry": "石油石化", "companies": petrochemical_companies},
            {"industry": "铁路", "companies": railway_companies},
            {"industry": "园林绿化", "companies": landscaping_companies},
            {"industry": "生物医药", "companies": biomedical_companies},
            {"industry": "水利水电", "companies": water_power_companies},
            {"industry": "水运", "companies": shipping_companies},
            {"industry": "港口航道", "companies": port_companies},
            {"industry": "纺织轻工", "companies": textile_companies},
            {"industry": "矿产冶金", "companies": mining_companies},
            {"industry": "民航", "companies": aviation_companies},
            {"industry": "生态环保", "companies": environmental_companies},
            {"industry": "地球科学", "companies": geoscience_companies},
            {"industry": "信息电子", "companies": it_companies},
            {"industry": "市政", "companies": municipal_companies},
            {"industry": "广电通信", "companies": telecom_companies},
            {"industry": "科教文卫", "companies": education_companies},
            {"industry": "商业服务", "companies": business_service_companies},
            {"industry": "农林牧渔", "companies": agriculture_companies},
            {"industry": "机械设备", "companies": machinery_companies},
            {"industry": "航空航天", "companies": aerospace_companies},
            {"industry": "旅游", "companies": tourism_companies},
            {"industry": "电商平台", "companies": ecommerce_companies},
            {"industry": "乳业", "companies": dairy_companies}
        ]
        
        # 为每个行业的每个公司创建文档
        for industry_data in industries:
            industry_name = industry_data["industry"]
            companies = industry_data["companies"]
            
            for company in companies:
                document = {
                    "industry": industry_name,
                    "rank": company["rank"],
                    "company_name": company["name"],
                    "note": company.get("note", ""),
                    "company_type": company["type"],
                    "status": "active",  # 新增状态字段
                    "priority": "medium",  # 新增优先级字段
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    # 新增可选字段
                    "website": company.get("website", ""),
                    "contact": company.get("contact", ""),
                    "description": company.get("description", ""),
                    "tags": company.get("tags", []),
                    "region": company.get("region", ""),
                    "scale": company.get("scale", ""),
                    "contact_info": company.get("contact_info", {}),
                    "business_history": company.get("business_history", [])
                }
                
                # 为电商平台添加特殊字段
                if industry_name == "电商平台" and "market_share" in company:
                    document["market_share"] = company["market_share"]
                
                data.append(document)
        
        return data

    def validate_company_data(self, company: Dict[str, Any]) -> bool:
        """验证企业数据的完整性"""
        required_fields = ['company_name', 'industry', 'rank', 'company_type']
        for field in required_fields:
            if field not in company or not company[field]:
                logging.warning(f"企业数据缺少必需字段: {field}")
                return False
        return True

    def insert_data(self, data: List[Dict[str, Any]], clear_existing: bool = True) -> bool:
        """插入数据到MongoDB"""
        try:
            # 数据验证
            valid_data = []
            for item in data:
                if self.validate_company_data(item):
                    valid_data.append(item)
                else:
                    logging.warning(f"跳过无效数据: {item.get('company_name', 'Unknown')}")
            
            if not valid_data:
                logging.error("没有有效数据可插入")
                return False
            
            if clear_existing:
                # 清空现有数据
                self.collection.delete_many({})
                logging.info("已清空现有数据")
            
            # 批量插入新数据
            result = self.collection.insert_many(valid_data)
            logging.info(f"成功插入 {len(result.inserted_ids)} 条记录")
            
            # 创建索引
            self.create_indexes()
            
            return True
        except Exception as e:
            logging.error(f"插入数据失败: {e}")
            return False

    def upsert_company(self, company_data: Dict[str, Any]) -> bool:
        """更新或插入单个企业数据"""
        try:
            if not self.validate_company_data(company_data):
                return False
            
            # 使用company_name和industry作为唯一标识
            filter_query = {
                'company_name': company_data['company_name'],
                'industry': company_data['industry']
            }
            
            # 更新时间戳
            company_data['updated_at'] = datetime.utcnow()
            if 'created_at' not in company_data:
                company_data['created_at'] = datetime.utcnow()
            
            result = self.collection.update_one(
                filter_query,
                {'$set': company_data},
                upsert=True
            )
            
            if result.upserted_id:
                logging.info(f"新增企业: {company_data['company_name']}")
            else:
                logging.info(f"更新企业: {company_data['company_name']}")
            
            return True
        except Exception as e:
            logging.error(f"更新企业数据失败: {e}")
            return False

    def create_indexes(self):
        """创建索引以提高查询性能"""
        try:
            # 创建复合索引
            self.collection.create_index([("industry", 1), ("rank", 1)])
            self.collection.create_index([("company_name", 1)])
            self.collection.create_index([("company_type", 1)])
            # 新增索引
            self.collection.create_index([("status", 1)])
            self.collection.create_index([("priority", 1)])
            self.collection.create_index([("created_at", -1)])
            # 文本搜索索引
            self.collection.create_index([("company_name", "text"), ("note", "text"), ("description", "text")])
            logging.info("索引创建成功")
        except Exception as e:
            logging.error(f"创建索引失败: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """获取数据统计信息"""
        try:
            total_count = self.collection.count_documents({})
            
            # 按行业统计
            industry_stats = list(self.collection.aggregate([
                {"$group": {"_id": "$industry", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]))
            
            # 按企业类型统计
            type_stats = list(self.collection.aggregate([
                {"$group": {"_id": "$company_type", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]))
            
            return {
                "total_companies": total_count,
                "industry_distribution": industry_stats,
                "company_type_distribution": type_stats
            }
        except Exception as e:
            logging.error(f"获取统计信息失败: {e}")
            return {}

    def close_connection(self):
        """关闭数据库连接"""
        if self.client:
            self.client.close()
            logging.info("MongoDB连接已关闭")


def main():
    """主函数"""
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='企业数据管理工具')
    parser.add_argument('--mode', choices=['insert', 'upsert', 'stats'], default='insert',
                       help='操作模式: insert(插入), upsert(更新插入), stats(统计)')
    parser.add_argument('--clear', action='store_true', default=True,
                       help='是否清空现有数据(仅在insert模式下有效)')
    parser.add_argument('--no-clear', dest='clear', action='store_false',
                       help='不清空现有数据')
    
    args = parser.parse_args()
    
    manager = None
    try:
        # 初始化管理器
        manager = IndustryCompaniesManager()
        
        if args.mode == 'stats':
            # 仅显示统计信息
            stats = manager.get_statistics()
            if stats:
                print("\n=== 数据统计信息 ===")
                print(f"总企业数量: {stats['total_companies']}")
                
                print("\n行业分布:")
                for item in stats['industry_distribution']:
                    print(f"  {item['_id']}: {item['count']} 家企业")
                
                print("\n企业类型分布:")
                for item in stats['company_type_distribution']:
                    print(f"  {item['_id']}: {item['count']} 家企业")
            return
        
        # 准备数据
        logging.info("开始准备数据...")
        data = manager.prepare_data()
        logging.info(f"数据准备完成，共 {len(data)} 条记录")
        
        if args.mode == 'insert':
            # 批量插入数据
            logging.info(f"开始{'清空并' if args.clear else ''}插入数据到MongoDB...")
            if manager.insert_data(data, clear_existing=args.clear):
                logging.info("数据插入成功！")
            else:
                logging.error("数据插入失败！")
                
        elif args.mode == 'upsert':
            # 逐个更新插入数据
            logging.info("开始更新插入数据到MongoDB...")
            success_count = 0
            for item in data:
                if manager.upsert_company(item):
                    success_count += 1
            logging.info(f"成功处理 {success_count}/{len(data)} 条记录")
        
        # 获取统计信息
        stats = manager.get_statistics()
        if stats:
            logging.info("\n=== 数据统计信息 ===")
            logging.info(f"总企业数量: {stats['total_companies']}")
            
            logging.info("\n行业分布:")
            for item in stats['industry_distribution']:
                logging.info(f"  {item['_id']}: {item['count']} 家企业")
            
            logging.info("\n企业类型分布:")
            for item in stats['company_type_distribution']:
                logging.info(f"  {item['_id']}: {item['count']} 家企业")
            
    except Exception as e:
        logging.exception("程序执行过程中出现错误")
    finally:
        if manager:
            manager.close_connection()
        logging.info("程序执行完毕")


if __name__ == "__main__":
    main()