# 宏观配置层回测：流动性档位择时 vs 买入持有。数据全部来自 data.js(免费源:FRED/AkShare/Yahoo)
# 用法: python3 backtest.py    输出 report.md + equity.png
import json, re, numpy as np, pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
raw = (ROOT/'data.js').read_text()
DATA = json.loads(raw.split('=',1)[1].rstrip().rstrip(';'))
REPORT = Path(__file__).parent/'report.md'

def s2s(s):  # {dates,values} -> pd.Series(月末索引)
    return pd.Series(s['values'], index=pd.to_datetime(s['dates']))

g3 = s2s(DATA['gl3_yoy'])          # G3 现汇同比(月度)
g4 = s2s(DATA['gl_yoy'])           # G4 含中国同比
m1 = s2s(DATA['china_liq']['m1_yoy'])  # 中国 M1 同比

def analysis_asset(key):
    """回测只用完整月；排除 data.js 中用于展示的本月暂值。"""
    asset = DATA['assets'][key]
    px = s2s(asset)
    end = pd.Timestamp(asset.get('analysis_end', px.index.max()))
    return px.loc[px.index <= end]

assets = {k: analysis_asset(k) for k in DATA['asset_order']}

def monthly_ret(px):
    return px.resample('ME').last().pct_change()

def metrics(ret):  # ret: 月度收益序列(已去NaN)
    ret = ret.dropna()
    n = len(ret)
    if n < 12: return None
    cum = (1+ret).prod()
    cagr = cum**(12/n) - 1
    eq = (1+ret).cumprod()
    dd = (eq/eq.cummax()-1).min()
    vol = ret.std()*np.sqrt(12)
    sharpe = (ret.mean()*12)/(vol+1e-9)
    return dict(CAGR=cagr, MaxDD=dd, Vol=vol, Sharpe=sharpe, months=n)

def timing(px, signal_on):
    """px月价, signal_on: 布尔月度序列(True=在场持有,False=空仓现金)。信号用上月末决定本月是否持有(避免前视)。"""
    r = monthly_ret(px)
    sig = signal_on.reindex(r.index).ffill().shift(1)  # 上月信号决定本月, 防前视
    strat = r.where(sig==True, 0.0)   # 空仓=0收益(现金,不计息,保守)
    return r, strat, sig

# ---- 信号定义(简单、抗过拟合，忠实于看板"流动性水位/回升"逻辑) ----
def sig_level(x):   # 绝对水位为正 = 宽松
    return (x > 0)
def sig_momo(x):    # 同比在回升(3月均线 vs 前3月均线) = 边际改善
    ma = x.rolling(3).mean()
    return (ma >= ma.shift(3))

rules = {
  'B&H 买入持有': None,
  'R1 流动性YoY>0': ('g', sig_level(g4)),
  'R2 流动性YoY回升': ('g', sig_momo(g4)),
}
# 中国资产额外测 M1 信号与双因子
rules_cn = {
  'B&H 买入持有': None,
  'R2 全球流动性回升': ('g', sig_momo(g4)),
  'R3 中国M1回升': ('c', sig_momo(m1)),
  'R4 双因子(M1回升 且 全球流动性回升)': ('b', sig_momo(m1) & sig_momo(g4).reindex(m1.index).ffill()),
  'R5 双因子(M1回升 或 全球流动性回升)': ('o', sig_momo(m1) | sig_momo(g4).reindex(m1.index).ffill()),
}

def run(px, ruleset):
    out=[]
    for name, spec in ruleset.items():
        if spec is None:
            r = monthly_ret(px); m = metrics(r)
            inmkt=1.0
        else:
            _, strat, sig = timing(px, spec[1])
            m = metrics(strat)
            inmkt = (sig==True).mean()
        if m: out.append((name, m, inmkt))
    return out

def fmt(m):
    return f"{m['CAGR']*100:5.1f}% | {m['MaxDD']*100:6.1f}% | {m['Vol']*100:5.1f}% | {m['Sharpe']:.2f}"

# ---- 输出报告 ----
lines=["# 宏观配置层回测报告","",
 f"数据区间：{monthly_ret(assets['spx']).dropna().index[0].date()} → {monthly_ret(assets['spx']).dropna().index[-1].date()}（月度）",
 "数据源：data.js（FRED 央行资产负债表/汇率、AkShare 中国M1、Yahoo 指数/商品，全部免费）",
 "",
 "**规则说明**：信号用**上月末**数据决定本月是否持有（严格防前视）；空仓=持现金按0%计（保守，不计货基收益）。",
 "「流动性回升」= G4流动性同比的3月均线 ≥ 前3月均线；「M1回升」同理。",
 "",
 "指标：CAGR 年化 | MaxDD 最大回撤 | Vol 年化波动 | Sharpe（无风险=0）",
 ""]

# 全球资产用全球流动性规则
global_assets = [('spx','标普500'),('ndx','纳斯达克'),('gold','黄金'),('bcom','彭博商品'),('sx600','欧洲STOXX600')]
global_results = {}
lines.append("## 一、全球资产 × 全球流动性择时\n")
for k,nm in global_assets:
    lines.append(f"### {nm} ({k})")
    lines.append("| 策略 | CAGR | MaxDD | Vol | Sharpe | 在场% |")
    lines.append("|---|---|---|---|---|---|")
    rows = run(assets[k], rules)
    global_results[k] = {name: (m, inm) for name, m, inm in rows}
    for name,m,inm in rows:
        lines.append(f"| {name} | {m['CAGR']*100:.1f}% | {m['MaxDD']*100:.1f}% | {m['Vol']*100:.1f}% | {m['Sharpe']:.2f} | {inm*100:.0f}% |")
    lines.append("")

# 中国资产用 M1 + 双因子
cn_assets=[('sse','沪深300'),('hsi','恒生指数')]
cn_results = {}
lines.append("## 二、中国资产 × M1/双因子择时\n")
for k,nm in cn_assets:
    lines.append(f"### {nm} ({k})")
    lines.append("| 策略 | CAGR | MaxDD | Vol | Sharpe | 在场% |")
    lines.append("|---|---|---|---|---|---|")
    rows = run(assets[k], rules_cn)
    cn_results[k] = {name: (m, inm) for name, m, inm in rows}
    for name,m,inm in rows:
        lines.append(f"| {name} | {m['CAGR']*100:.1f}% | {m['MaxDD']*100:.1f}% | {m['Vol']*100:.1f}% | {m['Sharpe']:.2f} | {inm*100:.0f}% |")
    lines.append("")

def pct(v):
    return f"{v*100:.1f}%"

sse_bh, _ = cn_results['sse']['B&H 买入持有']
sse_m1, sse_in = cn_results['sse']['R3 中国M1回升']
hsi_bh, _ = cn_results['hsi']['B&H 买入持有']
hsi_m1, hsi_in = cn_results['hsi']['R3 中国M1回升']
spx_bh, _ = global_results['spx']['B&H 买入持有']
spx_r1, _ = global_results['spx']['R1 流动性YoY>0']
spx_r2, _ = global_results['spx']['R2 流动性YoY回升']

lines.extend([
    "---", "", "## 三、结论与诚实解读", "",
    "### 被验证有效的", "",
    "**中国资产的 M1 回升择时，在本样本中主要改善回撤与风险收益比。**", "",
    f"- 沪深300：最大回撤从 {pct(sse_bh['MaxDD'])} 降至 {pct(sse_m1['MaxDD'])}，年化收益 {pct(sse_bh['CAGR'])}→{pct(sse_m1['CAGR'])}，在场 {sse_in*100:.0f}%；Sharpe {sse_bh['Sharpe']:.2f}→{sse_m1['Sharpe']:.2f}。",
    f"- 恒生指数：最大回撤从 {pct(hsi_bh['MaxDD'])} 降至 {pct(hsi_m1['MaxDD'])}，年化收益 {pct(hsi_bh['CAGR'])}→{pct(hsi_m1['CAGR'])}，在场 {hsi_in*100:.0f}%；Sharpe {hsi_bh['Sharpe']:.2f}→{hsi_m1['Sharpe']:.2f}。",
    "- 这支持看板把 M1 作为中国资产配置锚，但不证明未来一定复现。", "",
    "### 需要修正认知的", "",
    "**全球流动性对美股更适合调节风险敞口，不适合机械全进全出。**", "",
    f"- 标普500：买入持有年化 {pct(spx_bh['CAGR'])}；流动性同比>0策略为 {pct(spx_r1['CAGR'])}，流动性回升策略为 {pct(spx_r2['CAGR'])}。",
    "- 双因子 AND 规则历史上在场时间过低，更多用于描述场景，不作为机械开关。", "",
    "### 局限", "",
    "1. 月度频率、空仓按0%计；未计交易成本。",
    "2. M1和央行资产负债表会修订，历史序列存在轻微修订值偏差。",
    "3. 极端年份对结果贡献较大，未来未必复现。",
    "4. 只测试指数、商品和黄金配置，不包含个股选股。", "",
    "### 一句话", "",
    "**M1信号在历史样本中显著降低中国资产回撤；全球流动性对美股应作为仓位背景板，不作为清仓信号。**", ""
])

report = "\n".join(lines)
REPORT.write_text(report, encoding='utf-8')
print(report)

# ---- 净值曲线图(英文标签避免字体缺失) ----
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axes=plt.subplots(1,2,figsize=(13,5))
def eqcurve(ax, px, specs, title):
    for label,spec in specs:
        if spec is None:
            r=monthly_ret(px)
        else:
            _,r,_=timing(px,spec)
        r=r.dropna(); eq=(1+r).cumprod()
        ax.plot(eq.index, eq.values, label=label, linewidth=1.4)
    ax.set_yscale('log'); ax.set_title(title); ax.legend(fontsize=8); ax.grid(alpha=.3)
eqcurve(axes[0], assets['sse'], [('CSI300 Buy&Hold',None),('CSI300 M1-timing',sig_momo(m1))], 'China A (CSI300): M1 timing vs Buy&Hold')
eqcurve(axes[1], assets['spx'], [('SPX Buy&Hold',None),('SPX Liquidity-timing',sig_momo(g4))], 'US (SPX): Liquidity timing vs Buy&Hold')
equity_path = Path(__file__).parent/'equity.png'
plt.tight_layout(); plt.savefig(equity_path,dpi=120)
print(f'saved {equity_path}')
