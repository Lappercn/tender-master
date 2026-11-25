"""默认任务：每个栏目一条，方便把国家电网和南方电网分到不同机器。"""
from crawl.catalog import SPECS
from ops.nodes import is_worker, node_accepts


def assign_target(crawler_id, index, nodes):
    workers = [node for node in nodes if is_worker(node) and node_accepts(node, crawler_id)]
    dedicated = [node for node in workers if crawler_id in (node.get("accept") or [])]
    pool = dedicated or workers
    if not pool:
        return "any"
    return pool[index % len(pool)]["node_id"]


def default_jobs(nodes, lookback_days=14, max_pages=40):
    jobs = []
    cursor = {}
    for spec in SPECS:
        for channel in spec.channels:
            index = cursor.get(spec.id, 0)
            cursor[spec.id] = index + 1
            jobs.append({
                "crawlerId": spec.id,
                "script": spec.script,
                "label": spec.label,
                "channel": channel.code,
                "channelLabel": channel.name,
                "lookbackDays": lookback_days,
                "pageStart": 1,
                "pageEnd": 0,
                "maxPages": max_pages,
                "targetNode": assign_target(spec.id, index, nodes),
            })
    return jobs
