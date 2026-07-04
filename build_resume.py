# -*- coding: utf-8 -*-
"""可断点续传版数据引擎: 每个网络片段单独缓存到 CACHE/, 反复运行逐步完成,
全部就绪后组装写出 data.json / data.js。逻辑与 build_data.py 完全一致。"""
import os, json, time, pickle, datetime as dt, re
import numpy as np, pandas as pd
import pandas_datareader.data as web
import yfinance as yf
from scipy.signal import find_peaks

START = dt.datetime(2004, 1, 1)
LAG_MONTHS = 4; YOY = 12; TROUGH_DISTANCE = 30; TROUGH_PROMINENCE = 4
CYCLE_MONTHS = 42; ANCHOR_DATE = '2025-12-31'
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'data.json')
CACHE = '/tmp/gl_cache'; os.makedirs(CACHE, exist_ok=True)

ASSETS = [
    ('gold','GC=F','黄金','贵金属','USD/oz','Au99.99',0),
    ('silver','SI=F','白银','贵金属','USD/oz','Ag(T+D)',0),
    ('spx','^GSPC','标普500','指数','点',None,0),
    ('ndx','^IXIC','纳斯达克','指数','点',None,0),
    ('sse','000300.SS','沪深300','指数','点',None,0),
    ('hsi','^HSI','恒生指数','指数','点',None,0),
    ('nikkei','^N225','日经225','指数','点',None,0),
    ('kospi','^KS11','韩国综指','指数','点',None,0),
    ('twii','^TWII','台湾加权','指数','点',None,0),
    ('sx600','^STOXX','欧洲STOXX600','指数','点',None,0),
    ('wti','CL=F','WTI原油','大宗','USD/桶',None,0),
    ('copper','HG=F','铜','大宗','USD/磅',None,0),
    ('bcom','^BCOM','彭博商品指数','大宗','点',None,0),
]
CN_BENCH = {'sse','hsi'}

def cput(name, obj):
    pickle.dump(obj, open(os.path.join(CACHE, name+'.pkl'),'wb'))
def cget(name):
    p = os.path.join(CACHE, name+'.pkl')
    return pickle.load(open(p,'rb')) if os.path.exists(p) else None
def have(name):
    return os.path.exists(os.path.join(CACHE, name+'.pkl'))

BUDGET = 38
t0 = time.time()
def out_of_time():
    return time.time() - t0 > BUDGET

FREDS = ['WALCL','ECBASSETSW','JPNASSETS','DEXUSEU','DEXJPUS','DEXCHUS']
for code in FREDS:
    if have('fred_'+code):
        continue
    if out_of_time():
        print('TIMEOUT before', code); raise SystemExit(2)
    try:
        s = web.DataReader(code,'fred',START).iloc[:,0]
        cput('fred_'+code, s); print('FRED', code, 'ok', len(s))
    except Exception as e:
        print('FRED', code, 'FAIL', str(e)[:60]); raise SystemExit(3)

if not have('pboc'):
    if out_of_time(): print('TIMEOUT before pboc'); raise SystemExit(2)
    import akshare as ak
    df = ak.macro_china_central_bank_balance()
    cput('pboc', df); print('pboc ok', len(df))
if not have('ms'):
    if out_of_time(): print('TIMEOUT before ms'); raise SystemExit(2)
    import akshare as ak
    df = ak.macro_china_money_supply()
    cput('ms', df); print('ms ok', len(df))

def fetch_asset_ak(symbol, lag):
    import akshare as ak
    df = ak.stock_zh_index_daily(symbol=symbol)
    sr = pd.Series(pd.to_numeric(df['close'].values, errors='coerce'),
                   index=pd.to_datetime(df['date'].values)).dropna()
    sr = sr[sr.index >= pd.Timestamp(START)]
    if len(sr) > 50:
        sr = sr.resample('ME').last()
        if lag: sr = sr.shift(-lag)
        return sr, None
    raise RuntimeError('empty')

def fetch_asset(yfc, sge, lag):
    df = yf.download(yfc, start=START, progress=False, auto_adjust=True)
    sr = df['Close'].squeeze().dropna()
    if len(sr) > 50:
        sr = sr.resample('ME').last()
        if lag: sr = sr.shift(-lag)
        return sr, None
    raise RuntimeError('empty')

# key -> akshare 指数代码（长历史，替代 Yahoo 短历史）
AK_INDEX = {'sse': 'sh000300'}

def get_sr(key, yfc, sge, lag):
    if key in AK_INDEX:
        return fetch_asset_ak(AK_INDEX[key], lag)
    return fetch_asset(yfc, sge, lag)

for key, yfc, name, group, unit, sge, lag in ASSETS:
    if have('asset_'+key):
        continue
    if out_of_time(): print('TIMEOUT before asset', key); raise SystemExit(2)
    try:
        sr, uo = get_sr(key, yfc, sge, lag)
        cput('asset_'+key, {'sr': sr, 'unit_override': uo}); print('asset', key, 'ok', len(sr))
    except Exception as e:
        print('asset', key, 'retry', str(e)[:40])
        try:
            time.sleep(2); sr, uo = get_sr(key, yfc, sge, lag)
            cput('asset_'+key, {'sr': sr, 'unit_override': uo}); print('asset', key, 'ok2', len(sr))
        except Exception as e2:
            print('asset', key, 'FAIL', str(e2)[:40]); raise SystemExit(4)

print('all fetched, assembling...')
to_m = lambda s: s.resample('ME').last()
fed = cget('fred_WALCL'); ecb = cget('fred_ECBASSETSW'); boj = cget('fred_JPNASSETS')
usd_eur = cget('fred_DEXUSEU'); jpy_usd = cget('fred_DEXJPUS'); cny_usd = cget('fred_DEXCHUS')
fed_t = to_m(fed)/1e6
ecb_t = to_m(ecb)*to_m(usd_eur)/1e6
boj_t = to_m(boj)/(to_m(jpy_usd)*1e4)

_pboc = cget('pboc').copy()
_pboc['总资产'] = pd.to_numeric(_pboc['总资产'], errors='coerce')
_pboc = _pboc.dropna(subset=['总资产'])
def _parse_ym(s):
    y,m = str(s).split('.'); return pd.Timestamp(int(y),int(m),1)+pd.offsets.MonthEnd(0)
_pboc['dt'] = _pboc['统计时间'].apply(_parse_ym)
_pboc = _pboc.sort_values('dt').set_index('dt')
pboc_cny = _pboc['总资产'].resample('ME').last()
cny = to_m(cny_usd).reindex(pboc_cny.index).ffill()
pboc_t = pboc_cny/(cny*1e4)

_ms = cget('ms').copy()
def _parse_ms(x):
    m = re.match(r'(\d{4})年(\d{1,2})月', str(x)); return pd.Timestamp(int(m.group(1)),int(m.group(2)),1)+pd.offsets.MonthEnd(0)
_ms['dt'] = _ms['月份'].apply(_parse_ms)
_ms = _ms.sort_values('dt').set_index('dt')
cn_m1 = pd.to_numeric(_ms['货币(M1)-同比增长'], errors='coerce').dropna()
cn_m2 = pd.to_numeric(_ms['货币和准货币(M2)-同比增长'], errors='coerce').dropna()
cn_m1 = cn_m1[cn_m1.index>=pd.Timestamp(START)]; cn_m2 = cn_m2[cn_m2.index>=pd.Timestamp(START)]

gl3 = pd.concat([fed_t,ecb_t,boj_t],axis=1).dropna().sum(axis=1); gl3_yoy = gl3.pct_change(YOY)*100
gl = pd.concat([fed_t,ecb_t,boj_t,pboc_t],axis=1).dropna().sum(axis=1); gl_yoy = gl.pct_change(YOY)*100

# 固定汇率口径: 全历史用最新汇率折算, 剔除汇率beta——现汇同比 − 固定汇率同比 = 汇率贡献
_fx_eur = float(to_m(usd_eur).dropna().iloc[-1]); _fx_jpy = float(to_m(jpy_usd).dropna().iloc[-1])
ecb_fx = to_m(ecb)*_fx_eur/1e6; boj_fx = to_m(boj)/(_fx_jpy*1e4)
gl3_fx = pd.concat([fed_t,ecb_fx,boj_fx],axis=1).dropna().sum(axis=1); gl3_yoy_fx = gl3_fx.pct_change(YOY)*100

assets = {}
for key, yfc, name, group, unit, sge, lag in ASSETS:
    c = cget('asset_'+key)
    if not c: continue
    sr = c['sr'].dropna(); u = c['unit_override'] or unit
    assets[key] = {'name': name+(f'(领先{lag}月)' if lag else ''),'group':group,'unit':u,'lag':lag,
        'liq':'china' if key in CN_BENCH else 'global',
        'dates':[d.strftime('%Y-%m-%d') for d in sr.index],'values':[round(float(v),4) for v in sr.values]}

def compute_lead_lag(gl_series, lags=range(-6,19)):
    out=[]; base=gl_series.dropna()
    for key in [k for k,*_ in ASSETS if k in assets]:
        a=assets[key]; sr=pd.Series(a['values'],index=pd.to_datetime(a['dates'])); a_yoy=sr.pct_change(YOY)*100
        best_l,best_c,c0=0,-2.0,None
        for L in lags:
            df=pd.concat([base,a_yoy.shift(-L)],axis=1).dropna()
            if len(df)<36: continue
            c=df.iloc[:,0].corr(df.iloc[:,1])
            if L==0: c0=c
            if c>best_c: best_l,best_c=L,c
        out.append({'key':key,'name':a['name'].replace('(领先4月)',''),'group':a['group'],
            'best_lag':int(best_l),'best_corr':round(float(best_c),2),'corr0':round(float(c0),2) if c0 is not None else None})
    out.sort(key=lambda x:x['best_corr'],reverse=True); return out
lead_lag = compute_lead_lag(gl3_yoy)

# 每个资产对"自身锚定流动性"的最佳领先月数(仅取非负: 流动性领先), 供前端"流动性前移"开关用
def best_lead_vs(anchor, vals, dates, lags=range(0,19)):
    a_yoy = pd.Series(vals, index=pd.to_datetime(dates)).pct_change(YOY)*100
    base = anchor.dropna(); bc, bl = -9, 0
    for L in lags:
        df = pd.concat([base, a_yoy.shift(-L)], axis=1).dropna()
        if len(df) < 36: continue
        c = df.iloc[:,0].corr(df.iloc[:,1])
        if c > bc: bc, bl = c, L
    return int(bl)
for key in assets:
    anchor = cn_m1 if key in CN_BENCH else gl3_yoy
    assets[key]['lead_m'] = best_lead_vs(anchor, assets[key]['values'], assets[key]['dates'])

s = gl3_yoy.dropna(); yv=s.values
troughs_idx,_ = find_peaks(-yv, distance=TROUGH_DISTANCE, prominence=TROUGH_PROMINENCE)
trough_dates=[s.index[i].strftime('%Y-%m-%d') for i in troughs_idx]
def arcs_from_anchor(anchor_pos):
    p=int(anchor_pos)
    while p-CYCLE_MONTHS>=0: p-=CYCLE_MONTHS
    nodes=list(range(p,len(s)+CYCLE_MONTHS,CYCLE_MONTHS)); last=len(s)-1; out=[];bounds=[]
    for i in range(len(nodes)-1):
        a=nodes[i]
        if a<0 or a>last: continue
        nb=nodes[i+1]; x1=s.index[a]; x2_full=x1+pd.DateOffset(months=CYCLE_MONTHS)
        if nb<=last: partial,frac,b=False,1.0,nb
        else:
            partial,b=True,last; frac=round((last-a)/CYCLE_MONTHS,3)
            if frac<=0: continue
        out.append({'x1':x1.strftime('%Y-%m-%d'),'x2':s.index[b].strftime('%Y-%m-%d'),
            'x2_full':x2_full.strftime('%Y-%m-%d'),'partial':partial,'frac':frac,'label':'3.5y'})
    for n in nodes:
        if 0<=n<len(s): bounds.append(s.index[n].strftime('%Y-%m-%d'))
    return out,bounds
manual_pos=int(np.argmin(np.abs((s.index-pd.Timestamp(ANCHOR_DATE)).days)))
recent_pos=int(troughs_idx[-1]) if len(troughs_idx) else manual_pos
if len(troughs_idx):
    ang=np.array(troughs_idx)*2*np.pi/CYCLE_MONTHS
    phase=(np.angle(np.mean(np.exp(1j*ang)))/(2*np.pi)*CYCLE_MONTHS)%CYCLE_MONTHS; fit_pos=int(round(phase))
else: fit_pos=manual_pos
cycles={}
for mode,posv,lbl in [('manual',manual_pos,'手动锚点'),
        ('recent',recent_pos,'最近谷底('+s.index[recent_pos].strftime('%Y-%m')+')'),
        ('fit',fit_pos,'拟合所有谷底')]:
    ar,bd=arcs_from_anchor(posv); cycles[mode]={'arcs':ar,'bounds':bd,'label':lbl}
arcs=cycles['manual']['arcs']
def ser(sr):
    sr=sr.dropna(); return {'dates':[d.strftime('%Y-%m-%d') for d in sr.index],'values':[round(float(v),4) for v in sr.values]}
data={'updated':dt.datetime.now().strftime('%Y-%m-%d %H:%M'),
    'latest':{'total':round(float(gl.iloc[-1]),2),'yoy':round(float(gl_yoy.dropna().iloc[-1]),2),
        'total3':round(float(gl3.iloc[-1]),2),'yoy3':round(float(gl3_yoy.dropna().iloc[-1]),2),
        'yoy3_fx':round(float(gl3_yoy_fx.dropna().iloc[-1]),2),
        'date':gl.index[-1].strftime('%Y-%m-%d')},
    'gl_yoy':ser(gl_yoy),'gl3_yoy':ser(gl3_yoy),'gl3_yoy_fx':ser(gl3_yoy_fx),'gl_total':ser(gl),'gl3_total':ser(gl3),
    'china_liq':{'m1_yoy':ser(cn_m1),'m2_yoy':ser(cn_m2),
        'latest':{'m1':round(float(cn_m1.iloc[-1]),1),'m2':round(float(cn_m2.iloc[-1]),1),'date':cn_m1.index[-1].strftime('%Y-%m-%d')}},
    'assets':assets,'asset_order':[k for k,*_ in ASSETS if k in assets],'lead_lag':lead_lag,
    'troughs':trough_dates,'arcs':arcs,'cycles':cycles,'cycle_default':'manual','cycle_months':CYCLE_MONTHS}
json.dump(data, open(OUT,'w',encoding='utf-8'), ensure_ascii=False, indent=1)
open(os.path.join(HERE,'data.js'),'w',encoding='utf-8').write('window.DATA = '+json.dumps(data,ensure_ascii=False)+';')
print('WROTE', OUT)
print(f"[G3] {data['latest']['total3']}万亿 同比{data['latest']['yoy3']}%  [G4] {data['latest']['total']}万亿 同比{data['latest']['yoy']}%")
print(f"资产{len(assets)}个 波谷{len(trough_dates)}个 弧{len(arcs)}段 M1最新{data['china_liq']['latest']['m1']}%")
print('DONE_OK')
