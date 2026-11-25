import datetime
import unittest
from pathlib import Path

from ops.application.storage_status import fill_days
from serve.domain.nets import all_nets, require_open


class NetCatalogTest(unittest.TestCase):
    def test_six_nets_and_one_grid_query(self):
        nets = {item.id: item for item in all_nets()}
        self.assertEqual(len(nets), 6)
        opened = [item for item in nets.values() if item.open]
        self.assertEqual([item.id for item in opened], ["power-grid"])
        grid = require_open("power-grid")
        self.assertEqual(grid.source_ids, ("sgcc_ecp", "csg_supply"))
        self.assertEqual(grid.path, "/api/nets/power-grid/notices")
        self.assertEqual(nets["water"].path, "")

    def test_closed_net_is_not_queryable(self):
        with self.assertRaises(KeyError):
            require_open("compute")

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
        self.assertIn("/admin/sources/", collect)
        self.assertNotIn("/admin/storage", collect)
        self.assertIn("/admin/storage/", storage)
        self.assertNotIn("/admin/sources", storage)
        self.assertIn("/api/nets", exposure)
        self.assertNotIn("/admin/", exposure)

    def test_notice_edit_cannot_touch_captured_text(self):
        from ops.application.notices import editable_patch
        patch = editable_patch({"title": "新标题", "detailText": "原文", "contentId": "abc", "area": "广东"})
        self.assertEqual(patch, {"area": "广东"})
