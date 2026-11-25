"""开放查询的领域模型。一张网一个查询边界，采集源头只是这张网下面的来源。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class QueryNet:
    id: str
    name: str
    summary: str
    source_ids: tuple = ()
    open: bool = False

    @property
    def path(self):
        if not self.open:
            return ""
        return f"/api/nets/{self.id}/notices"


# 顺序按中央对「六张网」的表述。15个采集源头全部按业务归口至六张网并开放查询。
NETS = (
    QueryNet(
        "water",
        "水网",
        "中国政府采购网、全国公共资源交易平台、重庆市政府采购网共用这一个查询（含水利水务、生态环保及综合政务采购）。",
        ("ccgp_gov", "ggzy_gov", "ccgp_chongqing"),
        open=True,
    ),
    QueryNet(
        "power-grid",
        "新型电网",
        "国家电网、南方电网、国家能源、中国华能共用这一个查询。不指定源头时，四家一起按关键词查找。",
        ("sgcc_ecp", "csg_supply", "chnenergy_bid", "huaneng_ec"),
        open=True,
    ),
    QueryNet(
        "compute",
        "算力网",
        "金采网（中国金融集中采购网）算力、金融科技与数据中心集中采购公告查询。",
        ("cfcpn_fin",),
        open=True,
    ),
    QueryNet(
        "comm",
        "新一代通信网",
        "中国电信阳光采购网通信工程、软件集成与网络设备采购公告查询。",
        ("chinatelecom_sun",),
        open=True,
    ),
    QueryNet(
        "urban-pipe",
        "城市地下管网",
        "中国石油、中化商务油气管网、石油化工及市政管道工程招标采购查询。",
        ("cnpc_bid", "sinochem_ebid"),
        open=True,
    ),
    QueryNet(
        "logistics",
        "物流网",
        "国铁采购平台、中国邮政、中国国航、中国烟草铁路货运、邮政速递、航空物流及供应链采购查询。",
        ("guotie_95306", "chinapost_11185", "airchina_pur", "tobacco_cgjy"),
        open=True,
    ),
)


def all_nets():
    return NETS


def get_net(net_id):
    for item in NETS:
        if item.id == net_id:
            return item
    raise KeyError("没有这张网")


def require_open(net_id):
    item = get_net(net_id)
    if not item.open:
        raise KeyError(f"{item.name}还没有开放查询")
    return item


def net_for_source(source_id):
    for item in NETS:
        if source_id in item.source_ids:
            return item
    return require_open("power-grid")
