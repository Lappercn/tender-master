中标数据爬取（千里马网中标通知）使用说明

一、项目简介
- 脚本 tender_winner.py 自动登录千里马网 VIP，按企业名单逐个搜索中标信息（中标通知），并实时写入 MongoDB。
- 保存策略：爬取一页保存一页，出现重复根据 contentId 去重。
- 日志输出：中标数据爬取/logs/tender_winner.log。

二、运行环境
- 操作系统：Windows 10/11
- Python：3.9+（推荐 3.10 以上）
- 浏览器：Chrome（与 undetected-chromedriver 版本匹配，脚本中使用 version_main=138）
- 数据库：MongoDB（本地或远程均可）
- 依赖安装：在项目根目录执行 pip install -r requirements.txt

三、账号与数据库配置
- 登录账号：请通过环境变量 `QIANLIMA_USERNAME` 和 `QIANLIMA_PASSWORD` 配置，或在 `中标数据爬取/tender_winner.py` 中修改常量：
  - USERNAME：登录手机号/账号
  - PASSWORD：登录密码

- MongoDB 连接参数（tender_winner.py 中）：
  - MONGO_HOST=localhost
  - MONGO_PORT=27017
  - DATABASE_NAME=qianlima
  - 行业企业集合：industry_companies
  - 中标公告集合：Winner_Notice

四、企业名单准备（industry_companies 集合）
- 集合名：industry_companies
- 字段要求：company_name（企业名称，字符串）、industry（所属行业，字符串）
- 初始化方式：可使用 `中标数据爬取/industry_companies_to_mongo.py` 导入企业名单。

五、如何启动
1) 安装依赖：
   - 在项目根目录执行：pip install -r requirements.txt
2) 启动脚本：
   - 在 `legacy_spiders` 目录执行：python 中标数据爬取\tender_winner.py
3) 运行日志：
   - 查看文件：中标数据爬取\logs\tender_winner.log

六、运行流程（核心步骤）
- 连接 MongoDB，读取 industry_companies 集合中的企业名单
- 启动 undetected-chromedriver，最大化窗口，规避自动化检测
- 打开登录页，切换“密码登录”，模拟人类输入账号密码并登录（含登录冲突重试）
- 进入搜索页，优先点击“中标信息”标签，确保在正确标签下进行搜索
- 设置筛选项：
  - 招标阶段选择“中标通知”（多重定位保障）
  - 时间筛选选择“近一年”
  - 展开“高级”筛选并选择“招标单位”作为搜索范围
- 输入企业名称并搜索
- 翻页抓取列表，每条打开详情提取字段，实时保存到 MongoDB（爬取一页保存一页）

七、数据结构（Winner_Notice 集合）

详情页处理说明：
- 摘要信息来源：详情页 id="summaryTable" 的表格，过滤 class="none" 的行；解析每一行的“标签: 值”，去除空值与无关字样并以分号拼接，保存到 detail_summary 字段。
- 详情正文来源：详情页 id="detailInfoContainer" 区域的纯文本，去除脚本样式等无关内容，保存到 detail_txt 字段。
- 空值策略：当无法获取或页面不存在上述元素时，detail_txt 与 detail_summary 均保存为空字符串，以确保字段类型稳定。

- 文档字段说明：
  - company_name：企业名称（字符串）
  - industry：行业（字符串）
  - contentId：公告唯一标识（字符串，优先使用链接中的 contentId 或 bid-数字）
  - title：标题（字符串）
  - url：详情链接（字符串）
  - createTime：发布时间（字符串）
  - area：地区（字符串）
  - noticeType：固定为“中标通知”（字符串）
  - projectType：项目类型（字符串）
  - tenderees：招标单位（字符串，等同传入的 company_name）
  - agent：代理单位（字符串）
  - budget：中标金额/价格（字符串，原文保存）
  - tenderEndTime：投标截止时间（预留，可能为空）
  - registrationEndTime：报名截止时间（预留，可能为空）
  - briefText：正文前500字作为简介（字符串）
  - hasAnnex：是否包含附件（布尔）
  - crawl_time：爬取时间（字符串，YYYY-MM-DD HH:MM:SS）
  - source：来源站点（字符串，千里马网）
  - detail_txt：详情页完整文本（字符串）
  - detail_summary：详情页摘要信息（字符串）

八、常见问题
- 登录提示“账号已在其他设备登录”：脚本内置重试并点击确认，可自动继续；若多次失败请稍后再试。
- 无头模式：当前默认可视化运行，如需无头请在 tender_winner.py 的 setup_driver 中开启 options.add_argument('--headless')。
- 反爬限制：脚本包含滚动、悬停、随机延时等人性化模拟，若仍遇到限制建议调大随机等待时间。

九、目录与日志
- 代码：legacy_spiders/中标数据爬取/tender_winner.py
- 日志：legacy_spiders/中标数据爬取/logs/tender_winner.log
- 清单导入：legacy_spiders/中标数据爬取/industry_companies_to_mongo.py