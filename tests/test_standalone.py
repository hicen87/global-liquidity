import tempfile
import unittest
from pathlib import Path

import build_standalone
from build_trade_signals import write_output


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


if __name__ == "__main__":
    unittest.main()
