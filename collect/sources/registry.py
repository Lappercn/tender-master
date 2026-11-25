"""扫描 collect/sources 下的每个源头。新增爬虫不必改调度代码。"""
import importlib
from pathlib import Path


def load_sources():
    root = Path(__file__).resolve().parent
    found = []
    for child in sorted(root.iterdir()):
        if not (child / "source.py").is_file():
            continue
        module = importlib.import_module(f"collect.sources.{child.name}.source")
        found.append(module.SOURCE)
    return tuple(found)


def source_map():
    return {item.id: item for item in load_sources()}


def get_source(source_id):
    found = source_map().get(source_id)
    if found is None:
        raise KeyError(f"没有这个采集源头：{source_id}")
    return found


def channel_label(source, code):
    return source.channel(code).name
