"""按采集源头上的爬虫类名创建实例。"""
import importlib

from collect.sources.registry import get_source


def spider_for(crawler_id):
    source = get_source(crawler_id)
    module_name, class_name = source.spider.split(":")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)()
