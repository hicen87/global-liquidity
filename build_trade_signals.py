# -*- coding: utf-8 -*-
"""生成大类资产日线交易确认信号。

宏观周期仍决定目标仓位；本模块只输出股票与黄金的执行节奏确认。
输出 ``data_trade.js``，供纯静态页面和 standalone 使用。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pandas_datareader.data as web
import yfinance as yf


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data_trade.js"
START = dt.datetime(2004, 1, 1)
MAX_STALE_DAYS = 5
MIN_SESSIONS = 273  # 252日突破 + 20日均线斜率 + 当日
SCHEMA_VERSION = 1

STATE_LABELS = {
    "up": "趋势确认",
    "mixed": "分歧待验证",
    "down": "破位确认",
}

ACTION_MATRIX = {
    "stock": {
        "进攻": {
            "up": "趋势确认，可向进攻目标比例执行",
            "mixed": "分歧待验证，只分批向进攻目标靠拢",
            "down": "暂停新增风险，等待趋势修复",
        },
        "中性": {
            "up": "可向中性目标比例再平衡",
            "mixed": "仅分批再平衡，不追涨",
            "down": "暂停新增，守住中性目标下沿",
        },
        "防御": {
            "up": "停止加仓，分批减至防御目标；趋势仍强只放慢、不取消",
            "mixed": "停止加仓，按计划减至防御目标",
            "down": "破位确认，加速减至防御目标",
        },
    },
    "gold": {
        gear: {
            "up": "趋势确认，低于目标时可补足；高位不追",
            "mixed": "分歧待验证，低于目标时小额分批",
            "down": "暂停主动补仓；战略长配不因技术信号清仓",
        }
        for gear in ("进攻", "中性", "防御")
    },
    "bond": {
        "进攻": "不做技术择时；按宏观目标保留流动性",
        "中性": "不做技术择时；按宏观目标承担现金管理",
        "防御": "不做技术择时；承接股票减仓资金",
    },
}


def _clean_series(series: pd.Series) -> pd.Series:
    """规范价格序列，确保日期、数值和重复项可控。"""
    values = pd.to_numeric(series, errors="coerce")
    index = pd.to_datetime(series.index)
    if getattr(index, "tz", None) is not None:
        index = index.tz_localize(None)
    out = pd.Series(values.to_numpy(), index=index.normalize()).dropna().sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out.astype(float)


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI；平盘为50，单边上涨/下跌分别收敛到100/0。"""
    close = _clean_series(close)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss > 0), 0.0)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss == 0), 50.0)
    return rsi


def indicator_frame(close: pd.Series) -> pd.DataFrame:
    """仅用当日及此前数据计算四项技术指标与原始状态。"""
    close = _clean_series(close)
    if len(close) < MIN_SESSIONS:
        raise ValueError(f"日线数据不足：需要至少{MIN_SESSIONS}条，实际{len(close)}条")

    frame = pd.DataFrame({"close": close})
    frame["sma200"] = close.rolling(200, min_periods=200).mean()
    frame["sma200_slope_20d_pct"] = (frame["sma200"] / frame["sma200"].shift(20) - 1) * 100
    frame["prior_252_high"] = close.shift(1).rolling(252, min_periods=252).max()
    frame["prior_252_low"] = close.shift(1).rolling(252, min_periods=252).min()
    frame["rsi14"] = rsi_wilder(close, 14)

    frame["breakout52w"] = "none"
    frame.loc[frame["close"] > frame["prior_252_high"], "breakout52w"] = "high"
    frame.loc[frame["close"] < frame["prior_252_low"], "breakout52w"] = "low"

    trend_up = (frame["close"] > frame["sma200"]) & (frame["sma200_slope_20d_pct"] > 0)
    trend_down = (frame["close"] < frame["sma200"]) & (frame["sma200_slope_20d_pct"] < 0)
    confirm_up = (frame["rsi14"] > 55) | (frame["breakout52w"] == "high")
    confirm_down = (frame["rsi14"] < 45) | (frame["breakout52w"] == "low")

    frame["trend"] = "mixed"
    frame.loc[trend_up, "trend"] = "up"
    frame.loc[trend_down, "trend"] = "down"
    frame["raw_state"] = "mixed"
    frame.loc[trend_up & confirm_up, "raw_state"] = "up"
    frame.loc[trend_down & confirm_down, "raw_state"] = "down"
    return frame


def combine_with_proxy(primary: pd.DataFrame, proxy: pd.DataFrame) -> pd.Series:
    """代理趋势不同向时降级为 mixed，不反向覆盖主标的。"""
    aligned = primary[["raw_state"]].join(proxy[["trend"]].rename(columns={"trend": "proxy_trend"}), how="left")
    state = aligned["raw_state"].copy()
    disagreement = ((state == "up") & (aligned["proxy_trend"] != "up")) | (
        (state == "down") & (aligned["proxy_trend"] != "down")
    )
    state.loc[disagreement] = "mixed"
    state.loc[aligned["proxy_trend"].isna()] = "mixed"
    return state


def execution_action(gear: str, asset: str, state: str | None = None, stale: bool = False) -> str:
    """返回稳定、可穷举测试的执行建议。"""
    if stale:
        return "信号已过期，仅观察，不执行"
    if gear not in ("进攻", "中性", "防御"):
        raise ValueError(f"未知宏观档位：{gear}")
    if asset == "bond":
        return ACTION_MATRIX[asset][gear]
    if asset not in ("stock", "gold") or state not in STATE_LABELS:
        raise ValueError(f"未知资产或状态：{asset}/{state}")
    return ACTION_MATRIX[asset][gear][state]


def is_stale(asof: str | dt.date, today: dt.date | None = None, max_days: int = MAX_STALE_DAYS) -> bool:
    """页面与测试共用的5日历日失效口径。"""
    if isinstance(asof, str):
        asof = dt.date.fromisoformat(asof)
    today = today or dt.date.today()
    return (today - asof).days > max_days


def _future_max_drawdown(close: pd.Series, horizon: int) -> pd.Series:
    """从每个信号日开始、未来 horizon 个交易日内的最低收益。"""
    values = close.to_numpy(dtype=float)
    out = [float("nan")] * len(values)
    for i in range(len(values) - horizon):
        future = values[i + 1 : i + horizon + 1]
        out[i] = float(future.min() / values[i] - 1)
    return pd.Series(out, index=close.index)


def historical_diagnostic(close: pd.Series, states: pd.Series) -> dict[str, Any]:
    """评估状态区分度；未来收益只用于诊断，不参与信号。"""
    close = _clean_series(close)
    frame = pd.DataFrame({"close": close, "state": states.reindex(close.index)})
    frame["fwd20"] = close.shift(-20) / close - 1
    frame["fwd60"] = close.shift(-60) / close - 1
    frame["fwd_mdd60"] = _future_max_drawdown(close, 60)

    by_state: dict[str, Any] = {}
    for state in ("up", "mixed", "down"):
        rows = frame[frame["state"] == state]
        by_state[state] = {
            "count": int(len(rows)),
            "mean_fwd20_pct": _round_or_none(rows["fwd20"].mean() * 100, 2),
            "mean_fwd60_pct": _round_or_none(rows["fwd60"].mean() * 100, 2),
            "mean_fwd_mdd60_pct": _round_or_none(rows["fwd_mdd60"].mean() * 100, 2),
            "worst_fwd_mdd60_pct": _round_or_none(rows["fwd_mdd60"].min() * 100, 2),
        }

    recent = states.dropna().tail(252)
    flips = int((recent != recent.shift(1)).iloc[1:].sum()) if len(recent) > 1 else 0
    return {
        "method": "no-lookahead indicators; forward returns are diagnostic only",
        "state_flips_252d": flips,
        "by_state": by_state,
    }


def _round_or_none(value: Any, digits: int) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, digits) if math.isfinite(number) else None


def _download_yahoo(ticker: str, retries: int = 3) -> pd.Series:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            data = yf.download(ticker, start=START, progress=False, auto_adjust=True, threads=False)
            if data.empty or "Close" not in data:
                raise RuntimeError("empty close series")
            close = _clean_series(data["Close"].squeeze())
            if len(close) < MIN_SESSIONS:
                raise RuntimeError(f"only {len(close)} sessions")
            return close
        except Exception as exc:  # 网络错误保留完整因果链，最终统一失败
            last_error = exc
            print(f"Yahoo {ticker} 第{attempt}次失败：{str(exc)[:100]}")
            time.sleep(attempt * 2)
    raise RuntimeError(f"Yahoo {ticker} 不可用") from last_error


def _fred_sp500() -> pd.Series:
    data = web.DataReader("SP500", "fred", START).iloc[:, 0].dropna()
    close = _clean_series(data)
    if len(close) < MIN_SESSIONS:
        raise RuntimeError("FRED SP500 数据不足")
    return close


def verify_sp500(yahoo: pd.Series, fred: pd.Series, tolerance_pct: float = 0.2) -> dict[str, Any]:
    """同日点位交叉核验；超过0.2%视为口径异常并停止写出。"""
    overlap = pd.concat([_clean_series(yahoo).rename("yahoo"), _clean_series(fred).rename("fred")], axis=1).dropna()
    if overlap.empty:
        raise RuntimeError("Yahoo ^GSPC 与 FRED SP500 无重叠日期")
    row = overlap.iloc[-1]
    deviation = abs(float(row["yahoo"]) / float(row["fred"]) - 1) * 100
    if deviation > tolerance_pct:
        raise RuntimeError(f"标普500交叉核验偏差{deviation:.3f}% > {tolerance_pct}%")
    return {
        "kind": "same-day independent price check",
        "source": "FRED SP500",
        "asof": overlap.index[-1].strftime("%Y-%m-%d"),
        "deviation_pct": round(deviation, 4),
        "ok": True,
    }


def _asset_payload(
    label: str,
    primary_ticker: str,
    proxy_ticker: str,
    primary: pd.Series,
    proxy: pd.Series,
    verification: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    primary_frame = indicator_frame(primary)
    proxy_frame = indicator_frame(proxy)
    states = combine_with_proxy(primary_frame, proxy_frame)
    valid = primary_frame.join(states.rename("state")).dropna(subset=["sma200", "sma200_slope_20d_pct", "rsi14"])
    latest = valid.iloc[-1]
    asof = valid.index[-1]
    proxy_latest = proxy_frame.loc[:asof].iloc[-1]
    agreement = latest["trend"] == proxy_latest["trend"]
    verification_asof = verification.get("asof")
    sources_fresh = (
        not is_stale(asof.date())
        and not is_stale(proxy_frame.index[-1].date())
        and (not verification_asof or not is_stale(str(verification_asof)))
    )

    recent_history = [
        {"date": index.strftime("%Y-%m-%d"), "state": state}
        for index, state in states.dropna().tail(260).items()
    ]
    payload = {
        "label": label,
        "primary": primary_ticker,
        "confirm_proxy": proxy_ticker,
        "asof": asof.strftime("%Y-%m-%d"),
        "close": round(float(latest["close"]), 2),
        "sma200": round(float(latest["sma200"]), 2),
        "sma200_slope_20d_pct": round(float(latest["sma200_slope_20d_pct"]), 2),
        "rsi14": round(float(latest["rsi14"]), 1),
        "breakout52w": str(latest["breakout52w"]),
        "trend": str(latest["trend"]),
        "raw_state": str(latest["raw_state"]),
        "proxy_trend": str(proxy_latest["trend"]),
        "state": str(latest["state"]),
        "state_label": STATE_LABELS[str(latest["state"])],
        "verified": bool(verification.get("ok")) and sources_fresh,
        "verification": {
            **verification,
            "proxy_trend_agreement": bool(agreement),
            "proxy_asof": proxy_frame.index[-1].strftime("%Y-%m-%d"),
        },
        "source": f"Yahoo Finance {primary_ticker}",
        "history": recent_history,
    }
    return payload, historical_diagnostic(primary, states)


def build_data() -> dict[str, Any]:
    print("拉取日线交易确认数据...")
    spx = _download_yahoo("^GSPC")
    spy = _download_yahoo("SPY")
    gold = _download_yahoo("GC=F")
    gld = _download_yahoo("GLD")
    fred_spx = _fred_sp500()

    stock_verify = verify_sp500(spx, fred_spx)
    gold_verify = {
        "kind": "tradable-proxy trend check",
        "source": "GLD",
        "asof": gld.index[-1].strftime("%Y-%m-%d"),
        "ok": True,
        "note": "GC=F主序列与GLD只核对趋势方向，不比较绝对价格",
    }
    stock_payload, stock_diag = _asset_payload("股票（标普500代理）", "^GSPC", "SPY", spx, spy, stock_verify)
    gold_payload, gold_diag = _asset_payload("黄金", "GC=F", "GLD", gold, gld, gold_verify)

    if not stock_payload["verified"] or not gold_payload["verified"]:
        raise RuntimeError("主信号数据超过5日历日或核验失败，拒绝覆盖有效产物")

    return {
        "schema": SCHEMA_VERSION,
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "cadence": "daily_close",
        "stale_after_calendar_days": MAX_STALE_DAYS,
        "observation": {
            "mode": "shadow",
            "trading_days": 20,
            "automated_orders": False,
            "note": "观察期内仅记录信号稳定性，不自动改变真实仓位",
        },
        "rules": {
            "sma_days": 200,
            "slope_lookback_days": 20,
            "breakout_lookback_days": 252,
            "rsi_period": 14,
            "rsi_bull_above": 55,
            "rsi_bear_below": 45,
            "state_labels": STATE_LABELS,
            "action_matrix": ACTION_MATRIX,
        },
        "assets": {"stock": stock_payload, "gold": gold_payload},
        "diagnostics": {"stock": stock_diag, "gold": gold_diag},
    }


def _existing_payload(output: Path) -> dict[str, Any] | None:
    if not output.exists():
        return None
    try:
        text = output.read_text(encoding="utf-8")
        return json.loads(text.split("=", 1)[1].strip().rstrip(";"))
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def write_output(data: dict[str, Any], output: Path = OUTPUT, force: bool = False) -> bool:
    new_asofs = {key: value["asof"] for key, value in data["assets"].items()}
    old = _existing_payload(output)
    comparable = {key: value for key, value in data.items() if key != "updated"}
    old_comparable = {key: value for key, value in old.items() if key != "updated"} if old else None
    if not force and old_comparable == comparable:
        print(f"NO_DATA_OR_SIGNAL_CHANGE {new_asofs}，保留原文件与原更新时间")
        return False
    text = "window.TRADE_SIGNALS = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    output.write_text(text, encoding="utf-8")
    print(f"WROTE {output}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    data = build_data()
    write_output(data, args.output)
    for key, asset in data["assets"].items():
        print(
            f"{key}: {asset['state_label']} @ {asset['asof']} | "
            f"close={asset['close']} SMA200={asset['sma200']} RSI={asset['rsi14']}"
        )


if __name__ == "__main__":
    main()
