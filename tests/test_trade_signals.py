import datetime as dt
import unittest

import numpy as np
import pandas as pd

from build_trade_signals import (
    ACTION_MATRIX,
    combine_with_proxy,
    execution_action,
    historical_diagnostic,
    indicator_frame,
    is_stale,
)


def series_from(values):
    return pd.Series(values, index=pd.bdate_range("2024-01-02", periods=len(values)))


class IndicatorTests(unittest.TestCase):
    def test_uptrend_and_new_high(self):
        frame = indicator_frame(series_from(np.linspace(100, 500, 340)))
        self.assertEqual(frame.iloc[-1]["trend"], "up")
        self.assertEqual(frame.iloc[-1]["raw_state"], "up")
        self.assertEqual(frame.iloc[-1]["breakout52w"], "high")
        self.assertGreater(frame.iloc[-1]["rsi14"], 55)

    def test_downtrend_and_new_low(self):
        frame = indicator_frame(series_from(np.linspace(500, 100, 340)))
        self.assertEqual(frame.iloc[-1]["trend"], "down")
        self.assertEqual(frame.iloc[-1]["raw_state"], "down")
        self.assertEqual(frame.iloc[-1]["breakout52w"], "low")
        self.assertLess(frame.iloc[-1]["rsi14"], 45)

    def test_flat_series_has_neutral_rsi_and_mixed_state(self):
        frame = indicator_frame(series_from(np.full(340, 100.0)))
        self.assertEqual(frame.iloc[-1]["raw_state"], "mixed")
        self.assertEqual(frame.iloc[-1]["rsi14"], 50)

    def test_false_breakout_without_rising_long_trend_is_mixed(self):
        values = np.linspace(300, 100, 339).tolist() + [301]
        frame = indicator_frame(series_from(values))
        self.assertEqual(frame.iloc[-1]["breakout52w"], "high")
        self.assertEqual(frame.iloc[-1]["raw_state"], "mixed")

    def test_insufficient_data_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "数据不足"):
            indicator_frame(series_from(np.linspace(100, 200, 200)))

    def test_proxy_disagreement_downgrades_signal(self):
        up = indicator_frame(series_from(np.linspace(100, 500, 340)))
        down = indicator_frame(series_from(np.linspace(500, 100, 340)))
        state = combine_with_proxy(up, down)
        self.assertEqual(state.iloc[-1], "mixed")

    def test_appending_future_prices_does_not_change_past_signal(self):
        values = np.linspace(100, 500, 340)
        partial = indicator_frame(series_from(values[:300]))
        full = indicator_frame(series_from(values))
        date = partial.index[-1]
        for field in ("sma200", "sma200_slope_20d_pct", "rsi14", "breakout52w", "raw_state"):
            self.assertEqual(partial.loc[date, field], full.loc[date, field])

    def test_diagnostic_has_no_nan_json_values(self):
        close = series_from(np.linspace(100, 500, 340))
        frame = indicator_frame(close)
        diag = historical_diagnostic(close, frame["raw_state"])
        self.assertIn("by_state", diag)
        self.assertIsInstance(diag["state_flips_252d"], int)
        for metrics in diag["by_state"].values():
            for value in metrics.values():
                self.assertFalse(isinstance(value, float) and np.isnan(value))


class ExecutionMatrixTests(unittest.TestCase):
    def test_all_gear_state_combinations_are_defined(self):
        for gear in ("进攻", "中性", "防御"):
            for state in ("up", "mixed", "down"):
                self.assertTrue(execution_action(gear, "stock", state))
                self.assertTrue(execution_action(gear, "gold", state))
            self.assertTrue(execution_action(gear, "bond"))

    def test_defensive_stock_never_recommends_adding(self):
        for action in ACTION_MATRIX["stock"]["防御"].values():
            self.assertNotIn("可向", action)
            self.assertNotIn("允许", action)
            self.assertIn("减", action)

    def test_gold_breakdown_never_forces_liquidation(self):
        for gear in ("进攻", "中性", "防御"):
            action = execution_action(gear, "gold", "down")
            self.assertIn("不因技术信号清仓", action)

    def test_stale_signal_overrides_action(self):
        self.assertEqual(
            execution_action("进攻", "stock", "up", stale=True),
            "信号已过期，仅观察，不执行",
        )

    def test_staleness_boundary(self):
        today = dt.date(2026, 8, 9)
        self.assertFalse(is_stale("2026-08-04", today=today))
        self.assertTrue(is_stale("2026-08-03", today=today))


if __name__ == "__main__":
    unittest.main()
