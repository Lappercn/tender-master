# 行业企业数据导入工具

## 功能说明

这个工具用于将各行业Top10企业/机构名单数据存储到MongoDB的qianlima数据库中。

## 包含的行业数据

### 金融类
- 银行（10家）
- 保险（10家）

### 制造业
- 烟草（10家）
- 酒业（10家）
- 车企（10家）
- 化学工业（10家）
- 石油石化（10家）
- 纺织轻工（10家）
- 矿产冶金（10家）
- 机械设备（10家）
- 乳业（10家）

### 基础设施
- 能源电力（10家）
- 公路（10家）
- 房屋建筑（10家）
- 铁路（10家）
- 水利水电（10家）
- 水运（10家）
- 港口航道（10家）
- 市政（10家）

### 科技服务
- 信息电子（10家）
- 广电通信（10家）
- 航空航天（10家）
- 地球科学（10家）

### 其他行业
- 出版社（10家）
- 园林绿化（10家）
- 生物医药（10家）
- 民航（10家）
- 生态环保（10家）
- 科教文卫（10家）
- 商业服务（10家）
- 农林牧渔（10家）
- 旅游（10家）
- 电商平台（10家）

## 数据结构

每条记录包含以下字段：
- `industry`: 行业名称
- `rank`: 排名（1-10）
- `company_name`: 企业名称
- `note`: 备注信息（如品牌、特色等）
- `company_type`: 企业性质（央企、国有企业、民营企业、上市公司等）
- `created_at`: 创建时间
- `updated_at`: 更新时间

## 使用方法

### 1. 环境准备

确保已安装所需依赖：
```bash
pip install -r ../requirements.txt
```

确保MongoDB服务正在运行（默认连接localhost:27017）

### 2. 运行数据导入

```bash
# 方法1：直接运行主脚本
python industry_companies_to_mongo.py

# 方法2：使用运行脚本
python run_industry_data_import.py
```

### 3. 查看结果

脚本运行后会：
- 清空现有数据
- 插入新的行业企业数据
- 创建索引以提高查询性能
- 显示数据统计信息

## 数据库配置

默认配置：
- 数据库：qianlima
- 集合：industry_companies
- 主机：localhost
- 端口：27017

如需修改配置，请编辑 `industry_companies_to_mongo.py` 文件中的以下常量：
```python
MONGO_HOST = "localhost"
MONGO_PORT = 27017
DATABASE_NAME = "qianlima"
COLLECTION_NAME = "industry_companies"
```

## 日志文件

运行日志会保存在 `logs/industry_companies_mongo.log` 文件中。

## 数据查询示例

连接MongoDB后，可以使用以下查询：

```javascript
// 查看所有行业
db.industry_companies.distinct("industry")

// 查看银行业Top10
db.industry_companies.find({"industry": "银行"}).sort({"rank": 1})

// 查看所有央企
db.industry_companies.find({"company_type": "央企"})

// 统计各行业企业数量
db.industry_companies.aggregate([
  {"$group": {"_id": "$industry", "count": {"$sum": 1}}},
  {"$sort": {"count": -1}}
])
```

## 注意事项

1. 运行前请确保MongoDB服务已启动
2. 脚本会清空现有数据，请谨慎操作
3. 如遇到连接问题，请检查MongoDB配置
4. 数据总计约330条记录（33个行业 × 10家企业）