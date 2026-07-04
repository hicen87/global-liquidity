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

# ===== 规则化信号(阈值写死, 代码打分, 前端覆盖①源头对应行; 人只判定性行) =====
def d13(s):
    s = s.dropna(); return float(s.iloc[-1] - s.iloc[-14]) if len(s) > 13 else 0.0
def p13(s):
    s = s.dropna(); return float(s.iloc[-1] / s.iloc[-14] - 1) * 100 if len(s) > 13 else 0.0
_rrp_b = float(rrp_t.dropna().iloc[-1] * 1e3)         # 十亿
_spd = float(spread.iloc[-1])                          # bp
_tga13 = d13(tga_t)                                    # 万亿, 13周变化
_bs13 = p13(walcl_t)                                   # %, 13周变化
signals = {
    # ON RRP: <25B=缓冲耗尽bear; 25-200B=warn; >200B=有缓冲bull
    'rrp': 'bear' if _rrp_b < 25 else ('warn' if _rrp_b < 200 else 'bull'),
    # TGA 13周变化: 回补>+0.15T=抽水bear; 释放<-0.15T=放水bull; 其间warn
    'tga': 'bear' if _tga13 > 0.15 else ('bull' if _tga13 < -0.15 else 'warn'),
    # SOFR-IORB: >+5bp=回购紧张bear; -5~+5=warn; <-5bp=宽松bull
    'spread': 'bear' if _spd > 5 else ('warn' if _spd >= -5 else 'bull'),
    # 美联储总资产 13周变化: <-1%=缩表bear; -1~+1%=横盘warn; >+1%=扩表bull
    'bs': 'bear' if _bs13 < -1 else ('warn' if _bs13 <= 1 else 'bull'),
}
sig_detail = {'tga13': round(_tga13, 3), 'bs13': round(_bs13, 2)}

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
    'signals': signals, 'sig_detail': sig_detail,
}

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('window.WEEKLY = ' + json.dumps(data, ensure_ascii=False) + ';')

L = data['latest']
print(f"已写出 {OUT}")
print(f"净流动性 {L['netliq']} 万亿 (周环比 {L['wow']:+.3f}, 4周 {L['w4']:+.3f}) @ {L['date']}")
print(f"ON RRP {L['rrp']} 十亿 | 准备金 {L['reserves']} 万亿 | SOFR-IORB {L['spread']:+.1f}bp")
