# 架构

系统按四个边界拆开。采集负责把公告原文拿下来，处理负责以后的计算，开放查询给使用方查数据，运行管理负责启动、关闭和分布式节点调度。边界之间只通过公告文档、任务和进程记录交接，不互相调用页面或浏览器。

采集的聚合是采集源头，不是旧的 `wj_` 脚本名。一个源头一个目录，放在 `collect/sources/`。目录里的常量是这个源头的地址、栏目和选择器；`source.py` 把它收成源头实体。调度启动时自动扫描这些目录，新增源头不用改管理入口。目前 `wj_spiders/` 下的全部 15 个标准化源头均已完整迁入 `collect/sources/` 与 `crawl/spiders/`，覆盖「六张网」全部领域：
- **新型电网 (`power_grid`)**：`sgcc_ecp`（国家电网新一代电子商务平台）、`csg_supply`（中国南方电网供应链统一服务平台）、`chnenergy_bid`（国家能源招标网）、`huaneng_ec`（中国华能集团电子商务平台）
- **水网与综合政务 (`water`)**：`ccgp_gov`（中国政府采购网）、`ggzy_gov`（全国公共资源交易平台）、`ccgp_chongqing`（重庆市政府采购网）
- **算力网 (`compute`)**：`cfcpn_fin`（金采网·中国金融集中采购网）
- **新一代通信网 (`comm`)**：`chinatelecom_sun`（中国电信阳光采购网）
- **城市地下管网 (`urban_pipe`)**：`cnpc_bid`（中国石油电子招标投标交易平台）、`sinochem_ebid`（中化商务电子招投标平台）
- **物流网 (`logistics`)**：`guotie_95306`（国铁采购平台）、`chinapost_11185`（中国邮政电子采购与供应平台）、`airchina_pur`（中国航空集团采购管理平台）、`tobacco_cgjy`（中国烟草电子采购平台）

公告是采集域的实体，字段名在 `collect/domain/notice.py`。去重仍用清洗后的标题指纹，站点编号只存档。价格和联系人仍用原来的正则，抽不到的原文留在 `detailText`。

处理域在 `processing/`。采集入库时只把公告标成待样本，不改原文，也不重算价格。一到两周样本齐了，词频和字段提升写在这个域里，不写回爬虫。

开放查询在 `serve/`，是开放主机服务。领域层 `serve/domain` 按六张网划查询边界（`water`、`power-grid`、`compute`、`comm`、`urban-pipe`、`logistics`），每张网下挂载对应的采集源头。应用层 `serve/application` 组装查询。用户接口层 `serve/interfaces` 用 FastAPI 暴露，Swagger 在 `/docs`。`GET /api/nets/{net_id}/notices?q=关键词` 按标题、采购人、项目编号和摘要做包含查询。`python manage.py api` 默认只听本机 8787。

运行管理的接口在 `console/interfaces`，只挂路由，不写采集和查询规则。管理台页面是独立的 Vue 工程，放在 `console/web`，按采集、公告、开放查询、数据库、节点拆开，各自只调用自己的接口。分布式节点管理由 `ops/nodes.py`、`ops/tasks.py` 与 `ops/application/cluster.py` 协同提供，支持在管理台可视化增删改节点拓扑（`nodes.json`）、查看各节点在线心跳与熔断器（`Breaker`）状态、一键向集群队列派发全量栏目任务、回收失联超时任务以及直接启停主节点调度器（`master`）和工作节点守护进程（`work`）。
