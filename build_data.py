# -*- coding: utf-8 -*-
"""
全球流动性看板 - 数据引擎
全球流动性框架: 全球流动性 = 美+欧+日(+中国) 央行资产负债表折美元加总
叠加: 贵金属 / 全球主要指数 / 主要大宗商品 + 领先滞后相关性

数据源:
  央行表&汇率 = FRED(免key)                  主源
  中国央行    = AkShare(macro_china_central_bank_balance)  国内直连
  各类资产    = Yahoo Finance(免key); 金银兜底上海金交所(SGE)
运行: python build_data.py
环境变量(可选): PROXY=http://127.0.0.1:7890   # 国内访问FRED/Yahoo不通时设代理
"""
import os
import json
import time
import datetime as dt
import numpy as np
import pandas as pd
import pandas_datareader.data as web
import yfinance as yf
from scipy.signal import find_peaks

# ---- 可调参数 ----
START = dt.datetime(2004, 1, 1)
LAG_MONTHS = 4
YOY = 12
TROUGH_DISTANCE = 30
TROUGH_PROMINENCE = 4
CYCLE_MONTHS = 42
ANCHOR_DATE = '2025-12-31'   # manual模式的相位锚点(2025-26为周期起点)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')

# 标的清单: key, yahoo代码, 中文名, 分组, 单位, SGE兜底(仅金银), 领先月数
ASSETS = [
    ('gold',   'GC=F',      '黄金',      '贵金属', 'USD/oz', 'Au99.99',  0),
    ('silver', 'SI=F',      '白银',      '贵金属', 'USD/oz', 'Ag(T+D)',  0),
    ('spx',    '^GSPC',     '标普500',   '指数',   '点',     None,       0),
    ('ndx',    '^IXIC',     '纳斯达克',  '指数',   '点',     None,       0),
    ('sse',    '000300.SS', '沪深300',  '指数',   '点',     None,       0),
    ('hsi',    '^HSI',      '恒生指数',  '指数',   '点',     None,       0),
    ('nikkei', '^N225',     '日经225',   '指数',   '点',     None,       0),
    ('kospi',  '^KS11',     '韩国综指',  '指数',   '点',     None,       0),
    ('twii',   '^TWII',     '台湾加权',  '指数',   '点',     None,       0),
    ('sx600',  '^STOXX',    '欧洲STOXX600','指数', '点',     None,       0),
    ('wti',    'CL=F',      'WTI原油',   '大宗',   'USD/桶', None,       0),
    ('copper', 'HG=F',      '铜',        '大宗',   'USD/磅', None,       0),
    ('bcom',   '^BCOM',     '彭博商品指数', '大宗', '点',    None,       0),
]

CN_BENCH = {'sse', 'hsi'}   # 这些标的锚定中国流动性(M1), 其余锚全球G3

PROXY = os.environ.get('PROXY', '').strip()
if PROXY:
    os.environ['HTTP_PROXY'] = PROXY
    os.environ['HTTPS_PROXY'] = PROXY
    print(f'[net] 使用代理 {PROXY}')


def fred(code, retries=3, wait=5):
    for i in range(retries):
        try:
            return web.DataReader(code, 'fred', START).iloc[:, 0]
        except Exception as e:
            print(f'  FRED {code} 第{i+1}次失败({str(e)[:40]})')
            time.sleep(wait * (i + 1))
    raise RuntimeError(f'FRED {code} 不可达 (国内可设 PROXY 环境变量)')


print('拉取央行表 & 汇率 (FRED)...')
fed = fred('WALCL'); ecb = fred('ECBASSETSW'); boj = fred('JPNASSETS')
usd_eur = fred('DEXUSEU'); jpy_usd = fred('DEXJPUS'); cny_usd = fred('DEXCHUS')

to_m = lambda s: s.resample('ME').last()
fed_t = to_m(fed) / 1e6
ecb_t = to_m(ecb) * to_m(usd_eur) / 1e6
boj_t = to_m(boj) / (to_m(jpy_usd) * 1e4)

print('拉取中国央行资产负债表 (AkShare)...')
import akshare as ak
_pboc = ak.macro_china_central_bank_balance()
_pboc['总资产'] = pd.to_numeric(_pboc['总资产'], errors='coerce')
_pboc = _pboc.dropna(subset=['总资产'])


def _parse_ym(s):
    y, m = str(s).split('.')
    return pd.Timestamp(int(y), int(m), 1) + pd.offsets.MonthEnd(0)


_pboc['dt'] = _pboc['统计时间'].apply(_parse_ym)
_pboc = _pboc.sort_values('dt').set_index('dt')
pboc_cny = _pboc['总资产'].resample('ME').last()
cny = to_m(cny_usd).reindex(pboc_cny.index).ffill()
pboc_t = pboc_cny / (cny * 1e4)

# 中国流动性(M1/M2 同比) - "M1定买卖", A股最敏感
import re
_ms = ak.macro_china_money_supply()
def _parse_ms(x):
    m = re.match(r'(\d{4})年(\d{1,2})月', str(x))
    return pd.Timestamp(int(m.group(1)), int(m.group(2)), 1) + pd.offsets.MonthEnd(0)
_ms['dt'] = _ms['月份'].apply(_parse_ms)
_ms = _ms.sort_values('dt').set_index('dt')
cn_m1 = pd.to_numeric(_ms['货币(M1)-同比增长'], errors='coerce').dropna()
cn_m2 = pd.to_numeric(_ms['货币和准货币(M2)-同比增长'], errors='coerce').dropna()
cn_m1 = cn_m1[cn_m1.index >= pd.Timestamp(START)]
cn_m2 = cn_m2[cn_m2.index >= pd.Timestamp(START)]

gl3 = pd.concat([fed_t, ecb_t, boj_t], axis=1).dropna().sum(axis=1)
gl3_yoy = gl3.pct_change(YOY) * 100
gl = pd.concat([fed_t, ecb_t, boj_t, pboc_t], axis=1).dropna().sum(axis=1)
gl_yoy = gl.pct_change(YOY) * 100


def get_asset(yf_code, sge_sym, lag, retries=4, wait=8):
    for i in range(retries):
        try:
            df = yf.download(yf_code, start=START, progress=False, auto_adjust=True)
            sr = df['Close'].squeeze().dropna()
            if len(sr) > 50:
                sr = sr.resample('ME').last()
                if lag:
                    sr = sr.shift(-lag)
                return sr, None
        except Exception as e:
            print(f'  {yf_code} 第{i+1}次失败({str(e)[:30]})')
        time.sleep(wait)
    if sge_sym:
        print(f'  Yahoo不可用, {yf_code} 切上海金交所(人民币/克)')
        df = ak.spot_hist_sge(symbol=sge_sym)
        sr = pd.Series(df['close'].values, index=pd.to_datetime(df['date'])).resample('ME').last()
        if lag:
            sr = sr.shift(-lag)
        return sr, 'CNY/g'
    raise RuntimeError(f'{yf_code} 不可达')


print('拉取各类资产 (指数/大宗/金银)...')
assets = {}
AK_INDEX = {'sse': 'sh000300'}  # 长历史指数走 AkShare，替代 Yahoo 短历史
def get_asset_ak(symbol, lag):
    df = ak.stock_zh_index_daily(symbol=symbol)
    sr = pd.Series(pd.to_numeric(df['close'].values, errors='coerce'),
                   index=pd.to_datetime(df['date'].values)).dropna()
    sr = sr[sr.index >= pd.Timestamp(START)].resample('ME').last()
    if lag: sr = sr.shift(-lag)
    return sr, None

for key, yfc, name, group, unit, sge, lag in ASSETS:
    try:
        if key in AK_INDEX:
            sr, unit_override = get_asset_ak(AK_INDEX[key], lag)
        else:
            sr, unit_override = get_asset(yfc, sge, lag)
        u = unit_override or unit
        sr = sr.dropna()
        assets[key] = {
            'name': name + (f'(领先{lag}月)' if lag else ''),
            'group': group, 'unit': u, 'lag': lag,
            'liq': 'china' if key in CN_BENCH else 'global',
            'dates': [d.strftime('%Y-%m-%d') for d in sr.index],
            'values': [round(float(v), 4) for v in sr.values],
        }
        print(f'  OK {name} {len(sr)}点 最新{round(float(sr.iloc[-1]),1)}{u}')
    except Exception as e:
        print(f'  XX {name} 跳过: {str(e)[:50]}')
    time.sleep(2)


# ---- 领先/滞后相关性: 资产12月同比 vs G3流动性同比, 扫描滞后取最佳正相关 ----
def compute_lead_lag(gl_series, lags=range(-6, 19)):
    out = []
    base = gl_series.dropna()
    for key in [k for k, *_ in ASSETS if k in assets]:
        a = assets[key]
        sr = pd.Series(a['values'], index=pd.to_datetime(a['dates']))
        a_yoy = sr.pct_change(YOY) * 100
        best_l, best_c, c0 = 0, -2.0, None
        for L in lags:
            df = pd.concat([base, a_yoy.shift(-L)], axis=1).dropna()
            if len(df) < 36:
                continue
            c = df.iloc[:, 0].corr(df.iloc[:, 1])
            if L == 0:
                c0 = c
            if c > best_c:                 # 最佳正相关(贴合"流动性升→资产涨")
                best_l, best_c = L, c
        out.append({'key': key, 'name': a['name'].replace('(领先4月)', ''),
                    'group': a['group'], 'best_lag': int(best_l),
                    'best_corr': round(float(best_c), 2),
                    'corr0': round(float(c0), 2) if c0 is not None else None})
    out.sort(key=lambda x: x['best_corr'], reverse=True)
    return out


lead_lag = compute_lead_lag(gl3_yoy)

# 每个资产对"自身锚定流动性"的最佳领先月数(仅取非负), 供前端"流动性前移"开关
def best_lead_vs(anchor, vals, dates, lags=range(0, 19)):
    a_yoy = pd.Series(vals, index=pd.to_datetime(dates)).pct_change(YOY) * 100
    base = anchor.dropna(); bc, bl = -9, 0
    for L in lags:
        df = pd.concat([base, a_yoy.shift(-L)], axis=1).dropna()
        if len(df) < 36:
            continue
        c = df.iloc[:, 0].corr(df.iloc[:, 1])
        if c > bc:
            bc, bl = c, L
    return int(bl)
for _k in assets:
    _anchor = cn_m1 if _k in CN_BENCH else gl3_yoy
    assets[_k]['lead_m'] = best_lead_vs(_anchor, assets[_k]['values'], assets[_k]['dates'])

print('领先/滞后相关性(vs G3流动性同比, 取最佳正相关):')
for r in lead_lag:
    tag = f"流动性领先{r['best_lag']}月" if r['best_lag'] > 0 else (f"滞后{-r['best_lag']}月" if r['best_lag'] < 0 else "同步")
    print(f"  {r['name']:8s} r={r['best_corr']:+.2f} ({tag}), 同步r={r['corr0']}")

# ---- 周期波谷 & 3.5年等距弧 (G3口径) ----
s = gl3_yoy.dropna()
yv = s.values
troughs_idx, _ = find_peaks(-yv, distance=TROUGH_DISTANCE, prominence=TROUGH_PROMINENCE)
trough_dates = [s.index[i].strftime('%Y-%m-%d') for i in troughs_idx]

# 三种相位锚定模式, 各算一套弧供前端切换
def arcs_from_anchor(anchor_pos):
    p = int(anchor_pos)
    while p - CYCLE_MONTHS >= 0:
        p -= CYCLE_MONTHS
    nodes = list(range(p, len(s) + CYCLE_MONTHS, CYCLE_MONTHS))
    last = len(s) - 1
    out, bounds = [], []
    for i in range(len(nodes) - 1):
        a = nodes[i]
        if a < 0 or a > last:        # 起点必须在数据范围内
            continue
        nb = nodes[i + 1]
        x1 = s.index[a]
        x2_full = x1 + pd.DateOffset(months=CYCLE_MONTHS)   # 理论终点(可能超出数据)
        if nb <= last:
            partial, frac, b = False, 1.0, nb
        else:                          # 进行中的当前周期: 只画到最新数据
            partial, b = True, last
            frac = round((last - a) / CYCLE_MONTHS, 3)
            if frac <= 0:
                continue
        out.append({'x1': x1.strftime('%Y-%m-%d'),
                    'x2': s.index[b].strftime('%Y-%m-%d'),
                    'x2_full': x2_full.strftime('%Y-%m-%d'),
                    'partial': partial, 'frac': frac, 'label': '3.5y'})
    for n in nodes:
        if 0 <= n < len(s):
            bounds.append(s.index[n].strftime('%Y-%m-%d'))
    return out, bounds


manual_pos = int(np.argmin(np.abs((s.index - pd.Timestamp(ANCHOR_DATE)).days)))
recent_pos = int(troughs_idx[-1]) if len(troughs_idx) else manual_pos
if len(troughs_idx):
    ang = np.array(troughs_idx) * 2 * np.pi / CYCLE_MONTHS
    phase = (np.angle(np.mean(np.exp(1j * ang))) / (2 * np.pi) * CYCLE_MONTHS) % CYCLE_MONTHS
    fit_pos = int(round(phase))
else:
    fit_pos = manual_pos

cycles = {}
for mode, posv, lbl in [
        ('manual', manual_pos, '手动锚点'),
        ('recent', recent_pos, '最近谷底(' + s.index[recent_pos].strftime('%Y-%m') + ')'),
        ('fit',    fit_pos,    '拟合所有谷底')]:
    ar, bd = arcs_from_anchor(posv)
    cycles[mode] = {'arcs': ar, 'bounds': bd, 'label': lbl}
    print(f'  [周期-{mode}] {lbl}: 边界 {bd}')
arcs = cycles['manual']['arcs']  # 默认


def ser(sr):
    sr = sr.dropna()
    return {'dates': [d.strftime('%Y-%m-%d') for d in sr.index],
            'values': [round(float(v), 4) for v in sr.values]}


data = {
    'updated': dt.datetime.now().strftime('%Y-%m-%d %H:%M'),
    'latest': {
        'total': round(float(gl.iloc[-1]), 2),
        'yoy': round(float(gl_yoy.dropna().iloc[-1]), 2),
        'total3': round(float(gl3.iloc[-1]), 2),
        'yoy3': round(float(gl3_yoy.dropna().iloc[-1]), 2),
        'date': gl.index[-1].strftime('%Y-%m-%d'),
    },
    'gl_yoy': ser(gl_yoy),
    'gl3_yoy': ser(gl3_yoy),
    'gl_total': ser(gl),
    'gl3_total': ser(gl3),
    'china_liq': {
        'm1_yoy': ser(cn_m1), 'm2_yoy': ser(cn_m2),
        'latest': {'m1': round(float(cn_m1.iloc[-1]), 1), 'm2': round(float(cn_m2.iloc[-1]), 1),
                   'date': cn_m1.index[-1].strftime('%Y-%m-%d')},
    },
    'assets': assets,
    'asset_order': [k for k, *_ in ASSETS if k in assets],
    'lead_lag': lead_lag,
    'troughs': trough_dates,
    'arcs': arcs,
    'cycles': cycles,
    'cycle_default': 'manual',
    'cycle_months': CYCLE_MONTHS,
}

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
OUT_JS = os.path.join(os.path.dirname(OUT), 'data.js')
with open(OUT_JS, 'w', encoding='utf-8') as f:
    f.write('window.DATA = ' + json.dumps(data, ensure_ascii=False) + ';')

print(f'\n已写出 {OUT} 和 {OUT_JS}')
print(f"[G3] {data['latest']['total3']}万亿 同比{data['latest']['yoy3']}%  [G4] {data['latest']['total']}万亿 同比{data['latest']['yoy']}%")
print(f"资产 {len(assets)} 个, 波谷 {len(trough_dates)} 个, {len(arcs)} 段弧, lead_lag {len(lead_lag)} 条")
