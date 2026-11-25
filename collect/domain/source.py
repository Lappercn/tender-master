"""采集源头。一个源头一份目录，调度只认这里的编号。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Channel:
    code: str
    name: str


@dataclass(frozen=True)
class Source:
    """采集源头。编号用于启动和分表，名称是这个源头对外的叫法。"""

    id: str
    name: str
    home_url: str
    interval_minutes: int
    channels: tuple
    spider: str
    net: str = "power_grid"
    net_name: str = "新型电网"

    @property
    def script(self):
        return self.id

    @property
    def label(self):
        return self.name

    @property
    def source(self):
        return self.name

    def channel(self, code):
        for item in self.channels:
            if item.code == code:
                return item
        raise KeyError(f"{self.name} 没有栏目 {code}")
