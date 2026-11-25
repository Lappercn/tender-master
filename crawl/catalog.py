"""采集源头名单。真正的定义在 collect/sources 各自的目录里。"""
from collect.sources.registry import channel_label, get_source, load_sources, source_map

SPECS = load_sources()
BY_ID = source_map()
