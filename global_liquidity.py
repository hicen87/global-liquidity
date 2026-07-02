# -*- coding: utf-8 -*-
"""
复现「全球流动性条件 vs 黄金/白银」叠加图
Phase 2: 增加 850天 / 3.5年 周期弧线
数据源: 央行表&汇率=FRED(免key), 金银=Yahoo(免key)
口径(MVP): 全球流动性=美+欧+日 三大行资产负债表折美元加总;
          蓝线=12个月同比(%); 白银右移 LAG 个月。(中国央行待 Phase 1)
"""
import datetime as dt
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas_datareader.data as web
import yfinance as yf
from scipy.signal import find_peaks

# ---- 可调参数 ----
START = dt.datetime(2004, 1, 1)
LAG_MONTHS = 4            # 白银领先期(月), 通常 3-6
YOY = 12                 # 同比窗口(月)
TROUGH_DISTANCE = 30     # 找周期波谷的最小间距(月)
TROUGH_PROMINENCE = 4    # 波谷显著性阈值(越大越少)
ARC_MODE = 'fixed'       # 'fixed'=固定3.5年等距尺子(还原3.5年尺子); 'trough'=按实际波谷
CYCLE_MONTHS = 42        # 周期长度(月) ≈ 850天 ≈ 3.5年
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def fred(code):
    return web.DataReader(code, 'fred', START).iloc[:, 0]


print("拉取数据中...")
fed = fred('WALCL')          # 百万美元
ecb = fred('ECBASSETSW')     # 百万欧元
boj = fred('JPNASSETS')      # 亿日元
usd_eur = fred('DEXUSEU')    # 美元/欧元
jpy_usd = fred('DEXJPUS')    # 日元/美元

to_m = lambda s: s.resample('ME').last()
fed_t = to_m(fed) / 1e6
ecb_t = to_m(ecb) * to_m(usd_eur) / 1e6
boj_t = to_m(boj) / (to_m(jpy_usd) * 1e4)
gl = pd.concat([fed_t, ecb_t, boj_t], axis=1).dropna().sum(axis=1)
gl_yoy = gl.pct_change(YOY) * 100

def get_metal(ticker_yf, sym_sge, retries=4, wait=8):
    """金银获取: 主源 Yahoo(2004起, 美元/盎司, 带重试扛限流); 兜底 上海金交所(2017起, 人民币/克)"""
    for i in range(retries):
        try:
            df = yf.download(ticker_yf, start=START, progress=False, auto_adjust=True)
            sr = df['Close'].squeeze()
            if len(sr) > 50:
                return sr.resample('ME').last(), 'USD'
        except Exception as e:
            print(f'  {ticker_yf} 第{i+1}次失败({str(e)[:30]}), {wait}s后重试')
        time.sleep(wait)
    print(f'  Yahoo不可用, {ticker_yf} 切换上海金交所(人民币/克, 仅2017起)')
    import akshare as ak
    df = ak.spot_hist_sge(symbol=sym_sge)
    sr = pd.Series(df['close'].values, index=pd.to_datetime(df['date']))
    return sr.resample('ME').last(), 'CNY/g'

gold, GOLD_UNIT = get_metal('GC=F', 'Au99.99')
time.sleep(3)
silver, SILVER_UNIT = get_metal('SI=F', 'Ag(T+D)')
silver_lag = silver.shift(-LAG_MONTHS)


def draw_cycle_arcs(ax, series):
    """子图底部画周期弧线。
    fixed: 以首个显著波谷为相位锚点, 每 CYCLE_MONTHS 个月画一段等距弧(还原3.5年尺子)。
    trough: 直接连相邻实际波谷。两种都用红三角标出实际波谷供对照。"""
    s = series.dropna()
    x = mdates.date2num(s.index.to_pydatetime())
    y = s.values
    troughs, _ = find_peaks(-y, distance=TROUGH_DISTANCE, prominence=TROUGH_PROMINENCE)
    ymin, ymax = ax.get_ylim()
    base = ymin
    h = (ymax - ymin) * 0.05
    ax.set_ylim(bottom=base - h * 2.6)

    if ARC_MODE == 'fixed':
        step = CYCLE_MONTHS * 30.44
        anchor = x[troughs[0]] if len(troughs) else x[0]
        start = anchor
        while start - step >= x[0]:
            start -= step
        nodes = list(np.arange(start, x[-1] + step, step))
        for i in range(len(nodes) - 1):
            x1, x2 = nodes[i], nodes[i + 1]
            xc, a = (x1 + x2) / 2, (x2 - x1) / 2
            t = np.linspace(0, np.pi, 60)
            ax.plot(xc + a * np.cos(t), base - h * np.sin(t),
                    color='#c0392b', lw=1.0, alpha=0.75)
            ax.text(xc, base - h * 1.25, '3.5y', ha='center', va='top',
                    color='#c0392b', fontsize=7)
    else:
        xt = x[troughs]
        for i in range(len(xt) - 1):
            x1, x2 = xt[i], xt[i + 1]
            xc, a = (x1 + x2) / 2, (x2 - x1) / 2
            t = np.linspace(0, np.pi, 60)
            ax.plot(xc + a * np.cos(t), base - h * np.sin(t),
                    color='#c0392b', lw=1.0, alpha=0.75)
            months = round((x2 - x1) / 30.44)
            ax.text(xc, base - h * 1.25, f'{months}m', ha='center', va='top',
                    color='#c0392b', fontsize=7)
    ax.plot(x[troughs], y[troughs], 'v', color='#c0392b', ms=5)  # 实际波谷
    return len(troughs)


# 画图
fig, axes = plt.subplots(2, 1, figsize=(13, 9.5), sharex=True)
n_tr = 0
for ax, metal, name, unit in [(axes[0], gold, '黄金', GOLD_UNIT),
                              (axes[1], silver_lag, f'白银(领先{LAG_MONTHS}个月)', SILVER_UNIT)]:
    ax.fill_between(gl_yoy.index, gl_yoy, 0, color='#3a7bd5', alpha=0.25)
    ax.plot(gl_yoy.index, gl_yoy, color='#3a7bd5', lw=1.5, label='全球流动性条件(同比%, 左轴)')
    ax.axhline(0, color='gray', lw=0.6)
    ax.set_ylabel('流动性条件 同比%', color='#3a7bd5')
    ax2 = ax.twinx()
    ax2.plot(metal.index, metal, color='#111', lw=1.3, label=f'{name}价格(右轴)')
    ax2.set_ylabel(f'{name} ({unit})')
    n_tr = draw_cycle_arcs(ax, gl_yoy)           # ← Phase 2 弧线
    ax.set_title(f'全球流动性条件 vs {name}  (红弧=3.5年周期)', fontsize=12, loc='left')
    l1, lab1 = ax.get_legend_handles_labels()
    l2, lab2 = ax2.get_legend_handles_labels()
    ax.legend(l1 + l2, lab1 + lab2, loc='upper left', fontsize=8)

axes[1].set_xlabel('年份')
fig.suptitle('全球流动性条件 vs 黄金/白银  (全球流动性框架, Phase 2: +周期弧线)', fontsize=14, fontweight='bold')
fig.tight_layout()
fig.savefig('global_liquidity.png', dpi=130)
print("已保存 global_liquidity.png")
print(f"识别到 {n_tr} 个周期波谷")
print(f"最新全球流动性总量: {gl.iloc[-1]:.2f} 万亿美元 ({gl.index[-1].date()})")
print(f"最新流动性条件(同比): {gl_yoy.iloc[-1]:.1f}%")
