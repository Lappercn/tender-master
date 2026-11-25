# 国铁采购平台爬虫使用说明

## 功能特点

- 🎯 **只爬取当天数据**：自动过滤非当天发布的招标公告
- 🔄 **自动翻页**：智能翻页，遇到非当天数据自动停止
- 🤖 **反检测机制**：模拟人工操作，避免被网站检测
- 💾 **MongoDB存储**：数据自动保存到MongoDB数据库
- 📊 **详细日志**：完整的运行日志记录

## 反检测措施

### 1. 时间控制
- 页面加载后等待：3-6秒
- 翻页前等待：5-10秒
- 阅读内容等待：2-5秒
- 点击前等待：1-3秒

### 2. 人工模拟
- 逐字符输入页码
- 随机鼠标移动
- 模拟人工滚动模式
- 随机暂停阅读

### 3. 浏览器配置
- 随机User-Agent
- 禁用自动化标识
- 模拟真实浏览器环境

## 使用方法

### 1. 直接运行
```bash
# 无头模式运行（推荐）
python guotie_spider.py

# 有头模式运行（调试用）
python guotie_spider.py --visible
```

### 2. 通过调度器运行
```bash
# 立即运行一次
python scheduler.py --once

# 立即运行并继续调度
python scheduler.py --now
```

## 数据存储

### MongoDB集合结构
```json
{
  "notice_id": "公告唯一ID",
  "title": "公告标题",
  "publish_date": "发布日期",
  "detail": "公告详情",
  "tags": ["标签1", "标签2"],
  "crawl_time": "爬取时间",
  "source": "国铁采购平台"
}
```

### 数据库配置
- 数据库：`guotie_data`
- 集合：`tender_notices`
- 索引：`notice_id`（唯一）、`publish_date`（降序）

## 日志文件

- 主日志：`logs/guotie_spider.log`
- 调度器日志：`logs/scheduler.log`
- 脚本运行日志：`logs/guotie_YYYYMMDD_HHMMSS.log`

## 注意事项

1. **翻页速度**：已优化翻页间隔，避免触发检测机制
2. **网络稳定**：确保网络连接稳定，避免页面加载失败
3. **Chrome版本**：确保Chrome浏览器版本兼容
4. **MongoDB服务**：确保MongoDB服务正在运行

## 故障排除

### 常见问题
1. **Chrome驱动错误**：检查Chrome版本和undetected-chromedriver兼容性
2. **页面加载超时**：检查网络连接和网站可访问性
3. **翻页失败**：可能是网站结构变化，需要更新选择器

### 调试建议
1. 使用`--visible`参数查看浏览器操作
2. 检查日志文件了解详细错误信息
3. 确认MongoDB连接正常

## 更新日志

- v1.0：基础爬虫功能
- v1.1：优化反检测机制
- v1.2：增加人工模拟操作
- v1.3：优化翻页策略，避免检测
