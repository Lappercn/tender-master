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


# 顺序按中央对「六张网」的表述。目前只有新型电网开放，国家电网和南方电网共用这一个查询。
NETS = (
    QueryNet("water", "水网", "还没有采集源头，查询未开放。"),
    QueryNet(
        "power-grid",
        "新型电网",
        "国家电网和南方电网共用这一个查询。不指定源头时，两家一起按关键词查找。",
        ("sgcc_ecp", "csg_supply"),
        open=True,
    ),
    QueryNet("compute", "算力网", "还没有采集源头，查询未开放。"),
    QueryNet("comm", "新一代通信网", "还没有采集源头，查询未开放。"),
    QueryNet("urban-pipe", "城市地下管网", "还没有采集源头，查询未开放。"),
    QueryNet("logistics", "物流网", "还没有采集源头，查询未开放。"),
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
