# -*- coding: utf-8 -*-
"""
美元流动性管道 - 周频高频前瞻 (补月度央行框架的及时性短板)
净流动性 = 美联储总资产(WALCL) - 财政部TGA(WTREGEN) - 隔夜逆回购(ON RRP)
另含: ON RRP 余额、银行准备金、SOFR-IORB 利差(回购压力)
全部 FRED 免key。输出 data_weekly.js 供 index.html 用。
运行: python build_weekly.py    环境变量(可选): PROXY=http://127.0.0.1:7890
"""
import os, json, time, datetime as dt
import pandas as pd
import pandas_datareader.data as web

START = dt.datetime(2021, 1, 1)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_weekly.js')
PROXY = os.environ.get('PROXY', '').strip()
if PROXY:
    os.environ['HTTP_PROXY'] = PROXY; os.environ['HTTPS_PROXY'] = PROXY


def fred(code, retries=3, wait=5):
    for i in range(retries):
        try:
            return web.DataReader(code, 'fred', START).iloc[:, 0].dropna()
        except Exception as e:
            print(f'  FRED {code} 第{i+1}次失败({str(e)[:40]})'); time.sleep(wait*(i+1))
    raise RuntimeError(f'FRED {code} 不可达')


print('拉取美元流动性管道 (FRED 周频/日频)...')
walcl = fred('WALCL')          # 百万美元, 周
tga = fred('WTREGEN')          # 百万美元, 周 (财政部一般账户)
rrp = fred('RRPONTSYD')        # 十亿美元, 日 (隔夜逆回购)
reserves = fred('WRESBAL')     # 百万美元, 周 (准备金)
sofr = fred('SOFR')            # %, 日
iorb = fred('IORB')            # %, 日

# 统一到周(周五), 单位万亿美元
W = lambda s: s.resample('W-FRI').last()
walcl_t = W(walcl) / 1e6
tga_t = W(tga) / 1e6
rrp_t = W(rrp) / 1e3          # 十亿→万亿
res_t = W(reserves) / 1e6
netliq = (walcl_t - tga_t - rrp_t).dropna()          # 净流动性(万亿美元)
spread = (W(sofr) - W(iorb)).dropna() * 100          # SOFR-IORB, 基点


def ser(s, nd=3):
    s = s.dropna()
    return {'dates': [d.strftime('%Y-%m-%d') for d in s.index],
            'values': [round(float(v), nd) for v in s.values]}


nl = netliq
wow = float(nl.iloc[-1] - nl.iloc[-2]) if len(nl) > 1 else 0.0
w4 = float(nl.iloc[-1] - nl.iloc[-5]) if len(nl) > 4 else 0.0
data = {
    'updated': dt.datetime.now().strftime('%Y-%m-%d %H:%M'),
    'latest': {
        'date': nl.index[-1].strftime('%Y-%m-%d'),
        'netliq': round(float(nl.iloc[-1]), 2),
        'wow': round(wow, 3), 'w4': round(w4, 3),
        'rrp': round(float(rrp_t.dropna().iloc[-1] * 1e3), 1),   # 还原十亿显示
        'reserves': round(float(res_t.dropna().iloc[-1]), 2),
        'spread': round(float(spread.iloc[-1]), 1),
        'walcl': round(float(walcl_t.dropna().iloc[-1]), 2),
        'tga': round(float(tga_t.dropna().iloc[-1]), 2),
    },
    'netliq': ser(netliq, 3),
    'rrp_b': {'dates': ser(rrp_t)['dates'], 'values': [round(v*1e3, 1) for v in ser(rrp_t)['values']]},
    'reserves': ser(res_t, 3),
    'spread': ser(spread, 1),
}

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('window.WEEKLY = ' + json.dumps(data, ensure_ascii=False) + ';')

L = data['latest']
print(f"已写出 {OUT}")
print(f"净流动性 {L['netliq']} 万亿 (周环比 {L['wow']:+.3f}, 4周 {L['w4']:+.3f}) @ {L['date']}")
print(f"ON RRP {L['rrp']} 十亿 | 准备金 {L['reserves']} 万亿 | SOFR-IORB {L['spread']:+.1f}bp")
