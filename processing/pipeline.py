"""处理域。当前只给公告打上“待样本”标记，不改采集下来的原文和价格。"""
import importlib

import config


class PassThrough:
    name = "passthrough"

    def on_notice(self, notice):
        return {
            "processStatus": "pending",
            "processNote": "原文已保存。价格仍用原有规则。等一到两周样本后，再在处理域做词频和字段提升。",
        }


class WordSurvey:
    """样本够了再切词。现在不产出六张网词表。"""

    def run(self, texts):
        return {
            "status": "waiting_sample",
            "docs": len(list(texts or [])),
            "words": [],
            "note": "先采一到两周，再看哪些词反复出现、哪些和业务有关。",
        }


def load_pipeline():
    module_name, class_name = config.PROCESS_PIPELINE.split(":")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)()
