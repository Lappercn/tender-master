import datetime
import unittest

from collect.sources.csg_supply.constants import list_url as csg_list_url
from collect.sources.registry import load_sources
from crawl.browser import DEFAULT_UA, BrowserProfile
from crawl.csg_list import parse_rows
from crawl.extract import classify_notice, extract_budget, extract_end_time
from crawl.identity import clean_title, content_id, skip_as_duplicate
from crawl.record import build_notice
from crawl.window import judge_date, window_bounds
from ops.guard import Breaker
from ops.naming import notice_collection, notice_collections
from ops.nodes import local_node
from ops.plan import default_jobs
from processing.pipeline import PassThrough, WordSurvey
from serve.search import notice_filter


class IdentityTest(unittest.TestCase):
    def test_clean_title_ignores_punctuation(self):
        self.assertEqual(clean_title("【国网】测试 公告-1"), "国网测试公告1")
        self.assertEqual(content_id("测试 公告"), content_id("测试公告"))

    def test_site_id_alone_does_not_decide(self):
        existing = {"contentId": "aaa", "siteNoticeId": "1200", "projectCode": "A"}
        self.assertFalse(skip_as_duplicate(existing, "bbb"))
        self.assertTrue(skip_as_duplicate(existing, "aaa"))
        self.assertFalse(skip_as_duplicate(None, "aaa"))


class RuleTest(unittest.TestCase):
    def test_date_window_stops_on_older_rows(self):
        start, end = window_bounds(14 * 24, datetime.datetime(2026, 11, 17, 18, 0, 0))
        self.assertEqual(start.date().isoformat(), "2026-11-03")
        self.assertEqual(judge_date("2026-11-10", start, end), "take")
        self.assertEqual(judge_date("2026-11-01", start, end), "stop")
        self.assertEqual(judge_date("2026-11-18", start, end), "skip")
        self.assertEqual(judge_date("不是日期", start, end), "skip")
        hour_start, hour_end = window_bounds(1, datetime.datetime(2026, 11, 17, 15, 0, 0))
        self.assertEqual(judge_date("2026-11-17", hour_start, hour_end), "take")
        self.assertEqual(judge_date("2026-11-17 13:00", hour_start, hour_end), "stop")
        self.assertEqual(judge_date("2026-11-17 14:30", hour_start, hour_end), "take")

    def test_notice_types_keep_old_inquiry_rule(self):
        self.assertEqual(classify_notice("食堂采购意见征集"), "意见征集")
        self.assertEqual(classify_notice("某项目", "寻源公告"), "寻源公告")
        self.assertEqual(classify_notice("某项目", "流标公告"), "流标公告")
        self.assertEqual(classify_notice("设备询比采购"), "招标公告")
        self.assertEqual(classify_notice("第一中标候选人公示"), "中标候选人公示")
        self.assertEqual(classify_notice("中标结果变更公告"), "更正公告")

    def test_budget_uses_the_old_phrase(self):
        text = "项目预算金额为 12.5 万元。"
        budget, label = extract_budget(text)
        self.assertIn("12.5", budget)
        self.assertIn("万", budget)
        self.assertIn("预算", label)
        self.assertEqual(extract_end_time("投标截止时间：2026年11月20日 09:30"), "2026年11月20日 09:30")
        self.assertIsNone(extract_end_time("递交截止时间 2026-11-27 17:00:00"))


class LayoutTest(unittest.TestCase):
    def test_tables_split_by_net_and_keep_old_site_tables(self):
        self.assertEqual(notice_collection("sgcc_ecp", shard="crawler"), "notices_power_grid")
        self.assertEqual(notice_collection("csg_supply", shard="crawler"), "notices_power_grid")
        names = notice_collections("csg_supply", when=datetime.date(2026, 11, 17), shard="month")
        self.assertEqual(names[0], "notices_power_grid_202611")
        self.assertIn("notices_csg_supply_202611", names)
        with self.assertRaises(ValueError):
            notice_collection("SGCC", shard="crawler")

    def test_default_tasks_cover_new_channels_and_nodes(self):
        sources = {item.id: item for item in load_sources()}
        self.assertEqual(sources["sgcc_ecp"].name, "国家电网新一代电子商务平台")
        self.assertEqual(sources["csg_supply"].name, "中国南方电网供应链统一服务平台")
        jobs = default_jobs([local_node("local-1")], 14, 40)
        self.assertEqual(len(jobs), sum(len(item.channels) for item in sources.values()))
        self.assertTrue(all(job["targetNode"] == "local-1" for job in jobs))
        channels = {job["channel"] for job in jobs}
        self.assertTrue({"prequal", "award", "fbgg", "yjzjgg", "xygg"} <= channels)
        split = default_jobs([
            {"node_id": "worker-sgcc", "roles": ["worker"], "accept": ["sgcc_ecp"]},
            {"node_id": "worker-csg", "roles": ["worker"], "accept": ["csg_supply"]},
        ])
        self.assertTrue(all(job["targetNode"] == "worker-sgcc" for job in split if job["crawlerId"] == "sgcc_ecp"))
        self.assertTrue(all(job["targetNode"] == "worker-csg" for job in split if job["crawlerId"] == "csg_supply"))

    def test_breaker_opens_and_cools_down(self):
        moment = datetime.datetime(2026, 11, 17, tzinfo=datetime.timezone.utc)
        breaker = Breaker(limit=3, cooldown_seconds=60)
        breaker.failure("sgcc", moment)
        breaker.failure("sgcc", moment)
        self.assertTrue(breaker.allow("sgcc", moment))
        breaker.failure("sgcc", moment)
        self.assertFalse(breaker.allow("sgcc", moment))
        self.assertTrue(breaker.allow("sgcc", moment + datetime.timedelta(seconds=61)))
        breaker.success("sgcc")
        self.assertTrue(breaker.allow("sgcc", moment))


class CaptureTest(unittest.TestCase):
    def test_csg_list_keeps_full_title_and_ignores_index_links(self):
        html = """
        <div class="List2"><ul><li>
          <span class="Right"><a href="/yjzjgg/index.jhtml" class="Black14">意见征集</a> |
          <span class="Black14 Gray">2026-11-17</span></span>
          <a class="Blue">深圳供电局有限公司</a>
          <a href="/yjzjgg/1200450301.jhtml" target="_blank" title="深圳供电局2026年意见征集">深圳供电局2026年...</a>
        </li></ul></div>
        """
        rows = parse_rows(html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "深圳供电局2026年意见征集")
        self.assertEqual(rows[0]["site_id"], "1200450301")
        self.assertFalse(rows[0]["truncated"])
        self.assertEqual(csg_list_url("yjzjgg", 1), "https://www.bidding.csg.cn/yjzjgg/index.jhtml")
        self.assertEqual(csg_list_url("fbgg", 2), "https://www.bidding.csg.cn/fbgg/index_2.jhtml")

    def test_record_keeps_raw_text_and_old_budget_rule(self):
        doc = build_notice(
            crawler_id="csg_supply",
            source="中国南方电网供应链统一服务平台",
            title="设备询比采购公告",
            url="https://www.bidding.csg.cn/fzbgg/1.jhtml",
            content_id=content_id("设备询比采购公告"),
            create_time="2026-11-17",
            channel_id="fzbgg",
            channel_label="非招标公告",
            node_id="local-1",
            detail_text="项目预算金额为 3 万元。采购人：深圳供电局",
            detail_html="<div>原文</div>",
            file_urls=[],
            site_notice_id="1",
        )
        self.assertEqual(doc["noticeType"], "招标公告")
        self.assertEqual(doc["detail"], "<div>原文</div>")
        self.assertIn("3", doc["budget"])
        self.assertEqual(doc["purchaser"], "深圳供电局")
        self.assertEqual(doc["bizNet"], "新型电网")
        self.assertEqual(PassThrough().on_notice(doc)["processStatus"], "pending")
        self.assertEqual(WordSurvey().run(["原文"])["words"], [])

    def test_fixed_fingerprint_uses_the_previous_browser_identity(self):
        profile = BrowserProfile.resolve({"headless": True, "browser": "undetected", "fingerprint": "fixed"})
        self.assertTrue(profile.headless)
        self.assertEqual(profile.engine, "undetected")
        self.assertEqual(profile.user_agent, DEFAULT_UA)

    def test_fuzzy_query_escapes_user_text(self):
        query = notice_filter("阀.冷", notice_type="招标公告", area="广东")
        self.assertEqual(query["noticeType"], "招标公告")
        self.assertIn(r"阀\.冷", query["$or"][0]["title"]["$regex"])

    def test_run_reads_channel_objects(self):
        from collect.sources.registry import get_source
        from crawl.job import Job, channels_for
        source = get_source("csg_supply")
        whole = channels_for(source, Job(crawler_id="csg_supply"))
        self.assertEqual([item.code for item in whole], [item.code for item in source.channels])
        self.assertTrue(whole[0].name)
        one = channels_for(source, Job(crawler_id="csg_supply", channel="yjzjgg"))
        self.assertEqual(one[0].code, "yjzjgg")
        self.assertTrue(one[0].name)

    def test_body_drops_neighbor_links_and_keeps_lines(self):
        from crawl.text import html_to_text
        html = "<div><p>不接受联合体投标。</p><p>3.2专用资格要求</p><p>上一篇：另一条招标公告</p><p>下一篇：再一条公告</p></div>"
        text = html_to_text(html)
        self.assertIn("不接受联合体投标。", text)
        self.assertIn("3.2专用资格要求", text)
        self.assertNotIn("上一篇", text)
        self.assertNotIn("下一篇", text)
        chrome = "<div><p>招标人 国家电网有限公司</p><p>下载公告文件</p><p>联系我们 | 法律声明 | 网站地图</p><p>项目介绍 详见附件</p></div>"
        cleaned = html_to_text(chrome)
        self.assertIn("招标人 国家电网有限公司", cleaned)
        self.assertIn("项目介绍 详见附件", cleaned)
        self.assertNotIn("下载公告文件", cleaned)
        self.assertNotIn("联系我们", cleaned)

    def test_tables_keep_rows_and_fall_back_when_they_are_not_grids(self):
        from crawl.text import html_to_text, present_text
        grid = """
        <div>
          <p>项目介绍</p>
          <table>
            <tr><td>采购项目状态</td><td>正在招标</td><td>采购项目编号</td><td>0711</td></tr>
            <tr><td>采购项目名称</td><td>输变电</td><td>采购类型</td><td>物资</td></tr>
          </table>
          <p>详见附件</p>
        </div>
        """
        text = html_to_text(grid)
        self.assertIn("| 采购项目状态 | 正在招标 | 采购项目编号 | 0711 |", text)
        self.assertIn("| 采购项目名称 | 输变电 | 采购类型 | 物资 |", text)
        self.assertIn("项目介绍", text)
        self.assertIn("详见附件", text)
        self.assertLess(text.index("项目介绍"), text.index("采购项目状态"))
        self.assertLess(text.index("物资"), text.index("详见附件"))
        stored = present_text(text)
        self.assertIn("| 采购类型 | 物资 |", stored)

        spanned = "<table><tr><td rowspan='2'>招标人</td><td>国家电网</td></tr><tr><td>物资部</td></tr></table>"
        spanned_text = html_to_text(spanned)
        self.assertIn("| 招标人 | 国家电网 |", spanned_text)
        self.assertIn("|  | 物资部 |", spanned_text)

        wide = "<table><tr><td colspan='2'>标题</td></tr><tr><td>招标人</td><td>国家电网</td></tr></table>"
        self.assertIn("| 标题 |  |", html_to_text(wide))
        self.assertIn("| 招标人 | 国家电网 |", html_to_text(wide))

        uneven = "<table><tr><td>一</td><td>二</td><td>三</td></tr><tr><td>只一格</td></tr></table>"
        self.assertIn("| 只一格 |  |  |", html_to_text(uneven))

        pipe = "<table><tr><td>A|B</td><td>C</td></tr></table>"
        self.assertIn("| A\\|B | C |", html_to_text(pipe))

        article = "<table><tr><td><p>第一段</p><p>第二段</p></td></tr></table>"
        loose = html_to_text(article)
        self.assertIn("第一段", loose)
        self.assertIn("第二段", loose)
        self.assertNotIn("|", loose)

        nested = "<table><tr><td><table><tr><td>甲</td><td>乙</td></tr></table></td></tr></table>"
        self.assertIn("| 甲 | 乙 |", html_to_text(nested))

        button = "<table><tr><td>招标人</td><td>国家电网</td></tr><tr><td>下载公告文件</td><td></td></tr></table>"
        kept = html_to_text(button)
        self.assertIn("招标人", kept)
        self.assertNotIn("下载公告文件", kept)

    def test_pace_choices_spell_out_the_waits(self):
        from crawl.runtime import pace_choices
        paces = {item["code"]: item for item in pace_choices()}
        self.assertIn("2～5 秒", " ".join(paces["normal"]["steps"]))
        self.assertIn("1.8～4.5 秒", " ".join(paces["normal"]["steps"]))
        self.assertIn("8～14 次", " ".join(paces["normal"]["steps"]))
        self.assertIn("4～9 秒", " ".join(paces["calm"]["steps"]))
        self.assertIn("6～10 次", " ".join(paces["calm"]["steps"]))
        self.assertIn("15～40 秒", " ".join(paces["calm"]["steps"]))

    def test_gap_grows_after_many_pages(self):
        from crawl.runtime import gap_plan
        class Rand:
            def uniform(self, low, high):
                return low
            def randint(self, low, high):
                return low
        short, done, every = gap_plan("normal", "detail", 0, 8, Rand())
        self.assertLess(short, 8)
        long, done, every = gap_plan("normal", "detail", 8, 8, Rand())
        self.assertGreater(long, short)
        self.assertEqual(done, 0)

    def test_attachment_folder_belongs_to_one_notice(self):
        import tempfile
        from pathlib import Path
        import crawl.files as files
        origin = files.FILES
        try:
            files.FILES = Path(tempfile.mkdtemp())
            saved = files.store_files("power_grid", "csg_supply", "abc123", ["https://example.com/a.pdf"], fetch=lambda url: b"pdf")
            self.assertTrue(saved[0]["ok"])
            self.assertIn("power_grid/csg_supply/abc123", saved[0]["path"].replace("\\", "/"))
        finally:
            files.FILES = origin

    def test_each_notice_keeps_every_file_and_same_url_once(self):
        import tempfile
        from pathlib import Path
        import crawl.files as files
        origin = files.FILES
        try:
            files.FILES = Path(tempfile.mkdtemp())
            saved = files.store_files(
                "power_grid", "csg_supply", "abc123",
                ["https://example.com/a.pdf", "https://example.com/a.pdf", "https://example.com/b.doc"],
                fetch=lambda url: (b"pdf" if url.endswith(".pdf") else b"doc", "说明.pdf" if url.endswith(".pdf") else "清单.doc"),
            )
            self.assertEqual(len(saved), 2)
            self.assertTrue(all(item["ok"] for item in saved))
            self.assertEqual(saved[0]["key"], files.file_key("https://example.com/a.pdf"))
            self.assertNotEqual(saved[0]["path"], files.store_files(
                "power_grid", "csg_supply", "other", ["https://example.com/a.pdf"], fetch=lambda url: b"pdf",
            )[0]["path"])
        finally:
            files.FILES = origin

    def test_empty_or_huge_file_does_not_count_as_saved(self):
        import tempfile
        from pathlib import Path
        import crawl.files as files
        origin_dir, origin_max = files.FILES, files.MAX_BYTES
        try:
            files.FILES = Path(tempfile.mkdtemp())
            files.MAX_BYTES = 4
            empty = files.store_files("power_grid", "sgcc_ecp", "n1", ["https://example.com/downLoad"], fetch=lambda url: b"PK\x05\x06empty")
            huge = files.store_files("power_grid", "sgcc_ecp", "n1", ["https://example.com/big"], fetch=lambda url: b"12345")
            self.assertFalse(empty[0]["ok"])
            self.assertEqual(empty[0]["error"], "对方没有返回文件")
            self.assertFalse(huge[0]["ok"])
            self.assertIn("文件过大", huge[0]["error"])
            self.assertFalse(files.files_settled({"files": empty, "fileUrl": ["https://example.com/downLoad"]}))
            self.assertTrue(files.files_settled({"files": huge, "fileUrl": ["https://example.com/big"]}))
            self.assertFalse(files.files_settled({"fileUrl": []}))
            self.assertTrue(files.files_settled({"files": [], "fileUrl": []}))
            self.assertIsNone(files.locate_file({"path": "../config.py"}))
        finally:
            files.FILES = origin_dir
            files.MAX_BYTES = origin_max

    def test_sgcc_lists_every_file_and_ignores_menu_id(self):
        from collect.sources.sgcc_ecp.attachments import resolve_attachments
        spec = "https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doc-spec/2611131044761778_2018032700290425"

        def post(url, notice_id):
            self.assertEqual(notice_id, "2611131044761778")
            self.assertTrue(url.endswith("/index/getFile"))
            return {"resultValue": {"files": [{"firstPageFileId": 11}, {"firstPageFileId": 22}, {"firstPageFileId": 11}]}}

        found = resolve_attachments(spec, post=post)
        self.assertEqual(len(found["urls"]), 2)
        self.assertIn("fileId=11", found["urls"][0])
        self.assertNotIn("2018032700290425", "".join(found["urls"]))

        bid = "https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doci-bid/2611131047155856_2018032700290425"

        def bid_post(url, notice_id):
            return {"resultValue": {"fileFlag": "1", "notice": {
                "ONLINE_BID_NOTICE_ID": notice_id,
                "PURPRJ_NOTICE_DET_ID": None,
                "NOTICE_TYPE_NAME": "资格预审公告",
            }}}

        packed = resolve_attachments(bid, post=bid_post)
        self.assertIn("noticeId=2611131047155856", packed["urls"][0])
        self.assertNotIn("2018032700290425", packed["urls"][0])
        invite = resolve_attachments(bid, post=lambda url, notice_id: {"resultValue": {"fileFlag": "1", "notice": {"NOTICE_TYPE_NAME": "招标邀请书"}}})
        self.assertEqual(invite["urls"], [])
        self.assertFalse(invite["retry"])

    def test_csg_keeps_every_download_link(self):
        from crawl.spiders.csg import links_from
        urls = links_from([
            "https://www.bidding.csg.cn/filesrv/srv/file/download/1/AAA",
            "javascript:void(0)",
            "https://www.bidding.csg.cn/zbgg/2.jhtml",
            "https://www.bidding.csg.cn/filesrv/srv/file/download/1/BBB",
            "https://www.bidding.csg.cn/filesrv/srv/file/download/1/AAA",
        ])
        self.assertEqual(urls, [
            "https://www.bidding.csg.cn/filesrv/srv/file/download/1/AAA",
            "https://www.bidding.csg.cn/filesrv/srv/file/download/1/BBB",
        ])

    def test_public_detail_downloads_from_our_address(self):
        from serve.application.query import public_files
        rows = public_files("abc", [{
            "key": "k1", "name": "公告.doc", "size": 12, "ok": True, "url": "https://example.com/secret",
        }, {
            "key": "", "name": "失败.doc", "size": 0, "ok": False, "error": "对方没有返回文件", "url": "https://example.com/bad",
        }])
        self.assertEqual(rows[0]["download"], "/api/nets/power-grid/notices/abc/files/k1")
        self.assertEqual(rows[0]["sourceUrl"], "https://example.com/secret")
        self.assertNotIn("url", rows[0])
        self.assertNotIn("download", rows[1])
        self.assertEqual(rows[1]["error"], "对方没有返回文件")


if __name__ == "__main__":
    unittest.main()
