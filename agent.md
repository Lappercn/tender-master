# 架构

系统按四个边界拆开。采集负责把公告原文拿下来，处理负责以后的计算，开放查询给使用方查数据，运行管理负责启动、关闭和节点。边界之间只通过公告文档、任务和进程记录交接，不互相调用页面或浏览器。

采集的聚合是采集源头，不是旧的 `wj_` 脚本名。一个源头一个目录，放在 `collect/sources/`。目录里的常量是这个源头的地址、栏目和选择器；`source.py` 把它收成源头实体。调度启动时扫描这些目录，新增源头不用改管理入口。现在的两个源头是 `sgcc_ecp`（国家电网新一代电子商务平台）和 `csg_supply`（中国南方电网供应链统一服务平台）。

公告是采集域的实体，字段名在 `collect/domain/notice.py`。去重仍用清洗后的标题指纹，站点编号只存档。价格和联系人仍用原来的正则，抽不到的原文留在 `detailText`。

处理域在 `processing/`。采集入库时只把公告标成待样本，不改原文，也不重算价格。一到两周样本齐了，词频和字段提升写在这个域里，不写回爬虫。

开放查询在 `serve/`，是开放主机服务。领域层 `serve/domain` 按六张网划查询边界，新型电网只有一个接口，国家电网和南方电网都从这里查。应用层 `serve/application` 组装查询。用户接口层 `serve/interfaces` 用 FastAPI 暴露，Swagger 在 `/docs`。`GET /api/nets/power-grid/notices?q=关键词` 按标题、采购人、项目编号和摘要做包含查询。`python manage.py api` 默认只听本机 8787。

运行管理的接口在 `console/interfaces`，只挂路由，不写采集和查询规则。管理台页面是独立的 Vue 工程，放在 `console/web`，按采集、公告、开放查询、数据库、节点拆开，各自只调用自己的接口。公告的补录、修改和删除走管理接口，不进 Swagger；标题、链接、正文和指纹不能改。开发时在 `console/web` 执行 `npm run dev`，页面在 5173，接口代理到 8788。构建后由 `python manage.py console` 托管。采集的启动、关闭、浏览器和日志在 `collect/application`。本机配置、内存和浏览器进程数量在 `ops/application`。`python manage.py console` 听 8788，同一进程里带管理台和 Swagger。浏览器每次使用单独的用户目录，进程号记在 `runtime/browsers`。关闭时先结束采集进程，再按进程树和用户目录清掉 Chrome、chromedriver。在 Windows 上，这些进程还会放进作业对象，采集进程被系统回收时浏览器跟着退出。

公告按六张网进同一张表，新型电网是 `notices_power_grid`。旧的按站点表仍能查，不删除。采集范围和节奏在管理台选择，间隔随机，连续多了会自己停一下。附件按标讯分目录放在 `files/`。
