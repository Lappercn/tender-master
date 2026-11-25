import datetime
import tempfile
import unittest
from pathlib import Path

from collect.sources.registry import load_sources
from crawl.registry import spider_for
from ops.application.storage_status import fill_days
from ops.nodes import delete_node, load_nodes, upsert_node
from serve.domain.nets import all_nets, net_for_source, require_open


class NetCatalogTest(unittest.TestCase):
    def test_six_nets_open_and_cover_all_fifteen_sources(self):
        nets = {item.id: item for item in all_nets()}
        self.assertEqual(len(nets), 6)
        opened = [item for item in nets.values() if item.open]
        self.assertEqual(len(opened), 6)
        grid = require_open("power-grid")
        self.assertEqual(grid.source_ids, ("sgcc_ecp", "csg_supply", "chnenergy_bid", "huaneng_ec"))
        self.assertEqual(grid.path, "/api/nets/power-grid/notices")
        water = require_open("water")
        self.assertEqual(water.source_ids, ("ccgp_gov", "ggzy_gov", "ccgp_chongqing"))
        self.assertEqual(water.path, "/api/nets/water/notices")
        sources = load_sources()
        self.assertEqual(len(sources), 15)
        for src in sources:
            spider = spider_for(src.id)
            self.assertEqual(spider.spec.id, src.id)
            matched_net = net_for_source(src.id)
            self.assertIn(src.id, matched_net.source_ids)

    def test_unknown_net_raises_key_error(self):
        with self.assertRaises(KeyError):
            require_open("unknown-net")

    def test_distributed_node_upsert_and_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            node_file = str(Path(tmp) / "nodes.json")
            upsert_node({
                "node_id": "master-1",
                "roles": ["master", "storage"],
                "accept": [],
                "headless": True,
                "browser": "undetected",
                "fingerprint": "fixed",
            }, path=node_file)
            upsert_node({
                "node_id": "worker-grid",
                "roles": ["worker"],
                "accept": ["sgcc_ecp", "csg_supply"],
                "headless": True,
                "browser": "selenium",
                "fingerprint": "rotate",
            }, path=node_file)
            loaded = load_nodes(node_file)
            self.assertEqual([n["node_id"] for n in loaded], ["local-1", "master-1", "worker-grid"])
            self.assertEqual(loaded[2]["accept"], ["sgcc_ecp", "csg_supply"])
            self.assertEqual(loaded[2]["browser"], "selenium")
            delete_node("worker-grid", path=node_file)
            delete_node("local-1", path=node_file)
            after = load_nodes(node_file)
            self.assertEqual([n["node_id"] for n in after], ["master-1"])
            with self.assertRaises(ValueError):
                delete_node("master-1", path=node_file)

    def test_daily_rows_keep_empty_days(self):
        rows = fill_days({"2026-11-17": 4}, {"2026-11-16": 2}, days=3, today=datetime.date(2026, 11, 17))
        self.assertEqual([item["day"] for item in rows], ["2026-11-17", "2026-11-16", "2026-11-15"])
        self.assertEqual(rows[0]["inserted"], 4)
        self.assertEqual(rows[1]["collected"], 2)
        self.assertEqual(rows[2]["inserted"], 0)

    def test_frontend_domains_do_not_share_endpoints(self):
        root = Path(__file__).resolve().parents[1] / "console" / "web" / "src" / "domains"
        collect = (root / "collect" / "api.js").read_text(encoding="utf-8")
        storage = (root / "storage" / "api.js").read_text(encoding="utf-8")
        exposure = (root / "exposure" / "api.js").read_text(encoding="utf-8")
        nodes = (root / "nodes" / "api.js").read_text(encoding="utf-8")
        self.assertIn("/admin/sources/", collect)
        self.assertNotIn("/admin/storage", collect)
        self.assertIn("/admin/storage/", storage)
        self.assertNotIn("/admin/sources", storage)
        self.assertIn("/api/nets", exposure)
        self.assertNotIn("/admin/", exposure)
        self.assertIn("/admin/nodes/", nodes)

    def test_notice_edit_cannot_touch_captured_text(self):
        from ops.application.notices import editable_patch
        patch = editable_patch({"title": "新标题", "detailText": "原文", "contentId": "abc", "area": "广东"})
        self.assertEqual(patch, {"area": "广东"})

    def test_multi_scopes_merges_same_net_collections(self):
        from ops.storage import CollectStore
        store = CollectStore.__new__(CollectStore)
        scopes = store._multi_scopes(("sgcc_ecp", "csg_supply", "chnenergy_bid", "huaneng_ec"))
        shared = [item for item in scopes if item[0].startswith("notices_power_grid")]
        self.assertEqual(len(shared), 1)
        self.assertEqual(
            shared[0][1],
            {"crawlerId": {"$in": ["sgcc_ecp", "csg_supply", "chnenergy_bid", "huaneng_ec"]}},
        )
