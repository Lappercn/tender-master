"""采集管理。单机直接跑一个爬虫；多机时由主节点分栏目，采集节点领取。"""
import argparse
import datetime
import logging
import sys
import threading
import time

import config
from crawl.browser import BrowserProfile
from crawl.catalog import BY_ID, SPECS, channel_label
from crawl.job import Job
from crawl.registry import spider_for
from exposure.query import CollectQuery
from ops.guard import Breaker
from ops.nodes import find_node, load_nodes
from ops.plan import default_jobs
from ops.storage import CollectStore
from ops.tasks import TaskQueue, safe_queue, utcnow


def setup_logging(node_id):
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [" + node_id + "] %(name)s %(message)s"
    ))
    root.addHandler(handler)


def execute(job, node, force=False, store=None):
    logger = logging.getLogger("manage")
    store = store or CollectStore(node["node_id"])
    queue = safe_queue(store)
    breaker = Breaker()
    if queue:
        saved = queue.load_breaker(node["node_id"])
        breaker.restore(saved.get("snapshot") if saved else {})
    profile = BrowserProfile.resolve(node)
    if not force and not breaker.allow(job.crawler_id, utcnow()):
        print(f"{job.crawler_id} 正在熔断，冷却结束前不再打开浏览器。确实要跑就加 --force")
        _write_run(store, job, profile, "breaker", started=None, result=None, error="熔断中")
        return 2, None
    started = datetime.datetime.now()
    logger.info("开始采集 %s %s，%s", job.crawler_id, job.channel or "全部栏目", profile.describe())
    try:
        result = spider_for(job.crawler_id).run(job, store, profile)
    except Exception as exc:
        logger.exception("采集没有跑完")
        breaker.failure(job.crawler_id, utcnow())
        _save_breaker(queue, node, breaker)
        _write_run(store, job, profile, "failed", started, None, str(exc))
        print(f"采集失败：{exc}")
        return 1, None
    if result.status == "failed":
        breaker.failure(job.crawler_id, utcnow())
        code = 1
    else:
        breaker.success(job.crawler_id)
        code = 0
    _save_breaker(queue, node, breaker)
    _write_run(store, job, profile, result.status, started, result, result.error)
    print(
        f"完成，状态 {result.status}，保存 {result.saved} 条，"
        f"跳过 {result.skipped} 条，失败 {result.failed} 条。{result.note}"
    )
    return code, result


def _save_breaker(queue, node, breaker):
    if queue:
        queue.save_breaker(node["node_id"], breaker.snapshot())


def _write_run(store, job, profile, status, started, result, error):
    from crawl.window import label_of
    finished = datetime.datetime.now()
    spec = BY_ID.get(job.crawler_id)
    store.write_run({
        "crawlerId": job.crawler_id,
        "channel": job.channel,
        "startedAt": started.strftime("%Y-%m-%d %H:%M:%S") if started else finished.strftime("%Y-%m-%d %H:%M:%S"),
        "finishedAt": finished.strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "saved": result.saved if result else 0,
        "skipped": result.skipped if result else 0,
        "failed": result.failed if result else 0,
        "error": (error or "")[:500],
        "note": result.note if result else "",
        "span": getattr(job, "span", ""),
        "spanLabel": label_of(getattr(job, "span", "")),
        "pace": getattr(job, "pace", ""),
        "crawlerName": spec.name if spec else job.crawler_id,
        "browser": profile.engine,
        "headless": profile.headless,
        "fingerprint": profile.fingerprint,
    })


def _apply_browser_flags(node, args):
    node = dict(node)
    if getattr(args, "headless", None) is not None:
        node["headless"] = args.headless == "1"
    if getattr(args, "browser", None):
        node["browser"] = args.browser
    if getattr(args, "fingerprint", None):
        node["fingerprint"] = args.fingerprint
    return node


def cmd_run(args, nodes):
    node = _apply_browser_flags(find_node(nodes, args.node), args)
    spec = BY_ID.get(args.crawler)
    if spec is None:
        print("爬虫编号只能是：" + "、".join(item.id for item in SPECS))
        return 2
    if args.channel:
        channel_label(spec, args.channel)
    job = Job(
        crawler_id=spec.id,
        channel=args.channel or "",
        lookback_days=args.lookback or config.CRAWL_LOOKBACK_DAYS,
        span=args.span or "",
        pace=args.pace or "normal",
        max_pages=args.pages or config.CRAWL_MAX_PAGES,
        node_id=node["node_id"],
    )
    code, _ = execute(job, node, force=args.force)
    return code


def cmd_dispatch(args, nodes):
    jobs = default_jobs(
        nodes,
        args.lookback or config.CRAWL_LOOKBACK_DAYS,
        args.pages or config.CRAWL_MAX_PAGES,
    )
    if args.dry_run:
        for job in jobs:
            print(f"{job['crawlerId']} {job['channel']} {job['channelLabel']} → {job['targetNode']}")
        print(f"共 {len(jobs)} 条，未写入队列")
        return 0
    store = CollectStore(args.node)
    queue = TaskQueue(store)
    created = 0
    for job in jobs:
        if queue.enqueue(job, "manual"):
            created += 1
            print(f"投入 {job['label']} / {job['channelLabel']} → {job['targetNode']}")
    print(f"新任务 {created} 条。已经在排队或正在采集的栏目没有重复投入。")
    return 0


def cmd_work(args, nodes):
    node = _apply_browser_flags(find_node(nodes, args.node), args)
    store = CollectStore(node["node_id"])
    queue = TaskQueue(store)
    while True:
        queue.recover()
        queue.heartbeat(node, "worker")
        breaker = Breaker()
        breaker.restore((queue.load_breaker(node["node_id"]) or {}).get("snapshot"))
        task = queue.claim(node["node_id"], node.get("accept") or ["*"])
        if task is None:
            print("当前没有可领的任务")
            if args.once:
                return 0
            time.sleep(10)
            continue
        if not args.force and not breaker.allow(task["crawlerId"], utcnow()):
            queue.release(task, "节点熔断，任务退回")
            print(f"{task['crawlerId']} 熔断中，任务已退回")
            if args.once:
                return 2
            time.sleep(20)
            continue
        stop = threading.Event()

        def beat(current=task):
            while not stop.wait(20):
                queue.renew(current)

        threading.Thread(target=beat, daemon=True).start()
        job = Job(
            crawler_id=task["crawlerId"],
            channel=task["channel"],
            lookback_days=task.get("lookbackDays") or 14,
            span=task.get("span") or "",
            pace=task.get("pace") or "normal",
            page_start=task.get("pageStart") or 1,
            page_end=task.get("pageEnd") or 0,
            max_pages=task.get("maxPages") or 40,
            node_id=node["node_id"],
        )
        try:
            code, result = execute(job, node, force=True, store=store)
        finally:
            stop.set()
        status = "failed" if code else "success"
        queue.finish(
            task,
            status,
            error="" if result is None else result.error,
            saved=0 if result is None else result.saved,
            skipped=0 if result is None else result.skipped,
            failed_rows=0 if result is None else result.failed,
            note="" if result is None else result.note,
        )
        if args.once:
            return code


def cmd_master(args, nodes):
    node = find_node(nodes, args.node)
    store = CollectStore(node["node_id"])
    queue = TaskQueue(store)
    queue.seed_schedules(SPECS)
    print("主节点已启动。频率以库里的计划为准，默认每 60 分钟、回看 14 天。")
    while True:
        queue.recover()
        queue.heartbeat(node, "master")
        for item in queue.due_schedules():
            spec = BY_ID.get(item["_id"])
            if spec is None:
                continue
            jobs = [
                job for job in default_jobs(nodes, item.get("lookbackDays") or 14, config.CRAWL_MAX_PAGES)
                if job["crawlerId"] == spec.id
            ]
            created = sum(1 for job in jobs if queue.enqueue(job, "schedule"))
            queue.mark_enqueued(spec.id)
            print(f"{spec.label} 到点，新投入 {created} 个栏目")
        if args.once:
            return 0
        time.sleep(20)


def cmd_schedule(args, nodes):
    store = CollectStore(args.node)
    queue = TaskQueue(store)
    queue.seed_schedules(SPECS)
    if args.crawler:
        queue.set_schedule(args.crawler, args.every, None if args.enabled is None else args.enabled == "1", args.lookback)
    for item in queue.schedule_map().values():
        state = "开" if item.get("enabled", True) else "关"
        print(
            f"{item.get('label') or item['_id']} 每 {item.get('intervalMinutes')} 分钟，"
            f"回看 {item.get('lookbackDays')} 天，开关 {state}"
        )
    return 0


def cmd_status(args, nodes):
    store = CollectStore(args.node)
    queue = safe_queue(store)
    summary = CollectQuery(store, queue).summary()
    if not summary["online"]:
        print(f"存储未连通：{summary['reason']}")
        print("采集不会丢，会先写到 data-foundation/spool，连通后执行 replay。")
        return 0
    print("公告表：" + ("、".join(f"{name} {count} 条" for name, count in summary["counts"].items()) or "还没有"))
    tasks = summary["tasks"] or {}
    if tasks:
        print("任务：" + "，".join(f"{key} {value}" for key, value in tasks.items()))
    else:
        print("任务：还没有")
    for node in summary["nodes"]:
        print(f"节点 {node['nodeId']} {'/'.join(node['roles'])} {node['status']} 最近 {node['lastSeen']}")
    for run in summary["runs"]:
        print(
            f"记录 {run.get('startedAt')} {run.get('crawlerId')} {run.get('channel') or '全部'} "
            f"{run.get('status')} 保存{run.get('saved')} 节点{run.get('nodeId')}"
        )
    return 0


def cmd_logs(args, nodes):
    store = CollectStore(args.node)
    if not store.online:
        print(f"存储未连通：{store.reason}")
        return 0
    rows = store.recent_runs(args.crawler or "", args.limit)
    if not rows:
        print("还没有采集记录")
        return 0
    for run in rows:
        print(
            f"{run.get('startedAt')} → {run.get('finishedAt')} "
            f"{run.get('crawlerId')} {run.get('channel') or '全部栏目'} "
            f"状态 {run.get('status')} 保存 {run.get('saved')} 跳过 {run.get('skipped')} "
            f"失败 {run.get('failed')} 机器 {run.get('nodeId')} "
            f"浏览器 {run.get('browser')} 无头 {run.get('headless')}"
        )
        if run.get("error"):
            print(f"  原因：{run.get('error')}")
        if run.get("note"):
            print(f"  说明：{run.get('note')}")
    return 0


def cmd_replay(args, nodes):
    store = CollectStore(args.node)
    moved = store.replay()
    print(f"回放完成，写入或确认重复 {moved} 条")
    return 0


def cmd_check(args, nodes):
    node = find_node(nodes, args.node)
    profile = BrowserProfile.resolve(node)
    names = {
        "采集库": config.COLLECT_DB,
        "处理库": config.PROCESS_DB,
        "服务库": config.SERVE_DB,
    }
    print(f"节点 {node['node_id']}，角色 {' / '.join(node['roles'])}，可领 {'、'.join(node['accept']) or '无'}")
    print(f"浏览器 {profile.describe()}")
    for label, name in names.items():
        print(f"{label} {name}")
    print(f"分表方式 {config.NOTICE_SHARD}。新型电网写入 notices_power_grid，旧的按站点表仍可查询。")
    for spec in SPECS:
        labels = "、".join(channel.name for channel in spec.channels)
        print(f"{spec.name}（{spec.id}）每 {spec.interval_minutes} 分钟：{labels}")
    print(f"单次回看 {config.CRAWL_LOOKBACK_DAYS} 天，每个栏目最多 {config.CRAWL_MAX_PAGES} 页。")
    store = CollectStore(node["node_id"])
    if store.online:
        print("存储已连通")
    else:
        print(f"存储未连通，采集时写本机暂存。{store.reason}")
    return 0


def cmd_api(args, nodes):
    from serve.http import serve
    serve(config.API_HOST, config.API_PORT, args.node)
    return 0


def cmd_console(args, nodes):
    from console.interfaces.http import serve
    serve(config.API_HOST, config.CONSOLE_PORT, args.node)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="六张网采集管理")
    parser.add_argument("--node", default=config.NODE_ID)
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="本机直接跑一个爬虫")
    run.add_argument("crawler", choices=[item.id for item in SPECS])
    run.add_argument("--channel", default="")
    run.add_argument("--lookback", type=int)
    run.add_argument("--span", default="")
    run.add_argument("--pace", choices=["calm", "normal"], default="normal")
    run.add_argument("--pages", type=int)
    run.add_argument("--headless", choices=["0", "1"])
    run.add_argument("--browser", choices=["undetected", "selenium"])
    run.add_argument("--fingerprint", choices=["fixed", "rotate"])
    run.add_argument("--force", action="store_true")
    run.set_defaults(func=cmd_run)

    dispatch = sub.add_parser("dispatch", help="投入默认栏目任务")
    dispatch.add_argument("--lookback", type=int)
    dispatch.add_argument("--pages", type=int)
    dispatch.add_argument("--dry-run", action="store_true")
    dispatch.set_defaults(func=cmd_dispatch)

    work = sub.add_parser("work", help="领取任务并采集")
    work.add_argument("--once", action="store_true")
    work.add_argument("--headless", choices=["0", "1"])
    work.add_argument("--browser", choices=["undetected", "selenium"])
    work.add_argument("--fingerprint", choices=["fixed", "rotate"])
    work.add_argument("--force", action="store_true")
    work.set_defaults(func=cmd_work)

    master = sub.add_parser("master", help="按频率投入任务")
    master.add_argument("--once", action="store_true")
    master.set_defaults(func=cmd_master)

    schedule = sub.add_parser("schedule", help="查看或修改采集频率")
    schedule.add_argument("crawler", nargs="?", choices=[item.id for item in SPECS])
    schedule.add_argument("--every", type=int)
    schedule.add_argument("--lookback", type=int)
    schedule.add_argument("--enabled", choices=["0", "1"])
    schedule.set_defaults(func=cmd_schedule)

    status = sub.add_parser("status", help="看库存、任务和节点")
    status.set_defaults(func=cmd_status)
    logs = sub.add_parser("logs", help="看每次采集的时间和结果")
    logs.add_argument("--crawler", default="")
    logs.add_argument("--limit", type=int, default=20)
    logs.set_defaults(func=cmd_logs)
    replay = sub.add_parser("replay", help="把本机暂存写回数据库")
    replay.set_defaults(func=cmd_replay)
    check = sub.add_parser("check", help="检查节点、库和浏览器配置")
    check.set_defaults(func=cmd_check)
    api = sub.add_parser("api", help="启动开放查询")
    api.set_defaults(func=cmd_api)
    console = sub.add_parser("console", help="启动采集管理页面")
    console.set_defaults(func=cmd_console)
    return parser


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    nodes = load_nodes()
    setup_logging(args.node)
    try:
        return args.func(args, nodes)
    except KeyError as exc:
        print(str(exc))
        return 2
    except RuntimeError as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
