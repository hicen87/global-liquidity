import tempfile
import unittest
from pathlib import Path

import build_standalone
from build_trade_signals import write_output


ROOT = Path(__file__).resolve().parents[1]


class StandaloneTests(unittest.TestCase):
    def test_standalone_inlines_trade_signals(self):
        html = build_standalone.build()
        for name in build_standalone.SCRIPTS:
            self.assertNotIn(f'src="{name}"', html)
        self.assertIn("window.TRADE_SIGNALS", html)
        self.assertIn("交易确认层", html)

    def test_identical_payload_does_not_rewrite_output(self):
        data = {
            "updated": "2026-08-09T00:00+00:00",
            "assets": {
                "stock": {"asof": "2026-08-07"},
                "gold": {"asof": "2026-08-07"},
            }
        }
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "data_trade.js"
            self.assertTrue(write_output(data, output))
            before = output.read_text(encoding="utf-8")
            data["updated"] = "2026-08-10T00:00+00:00"
            self.assertFalse(write_output(data, output))
            self.assertEqual(output.read_text(encoding="utf-8"), before)

    def test_same_date_revision_is_written(self):
        data = {
            "updated": "2026-08-09T00:00+00:00",
            "assets": {
                "stock": {"asof": "2026-08-07", "close": 100},
                "gold": {"asof": "2026-08-07", "close": 200},
            },
        }
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "data_trade.js"
            self.assertTrue(write_output(data, output))
            data["assets"]["stock"]["close"] = 101
            self.assertTrue(write_output(data, output))
            self.assertIn('"close":101', output.read_text(encoding="utf-8"))

    def test_policy_overlay_is_display_only_and_inlined(self):
        summary = (ROOT / "summary.js").read_text(encoding="utf-8")
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        html = build_standalone.build()

        self.assertIn('"policyOverlay"', summary)
        self.assertIn("不计入源头紧度", summary)
        self.assertIn('"region": "中国"', summary)
        self.assertIn("中国独立政策脉络", summary)
        self.assertIn('id="policyblk"', index)
        self.assertIn("政策预期覆盖层", index)
        self.assertIn("i.region", index)
        self.assertIn("i.region!=='中国'", index)
        self.assertIn("i.region==='中国'", index)
        self.assertIn("政策预期覆盖层", html)

        tight_block = index[index.index("const SRC="):index.index("/* ---------- 一、结论层")]
        self.assertNotIn("policyOverlay", tight_block)


if __name__ == "__main__":
    unittest.main()
