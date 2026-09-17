#!/usr/bin/env python3
from __future__ import annotations
import os,json,csv,io,statistics,subprocess,urllib.request,urllib.parse,zipfile
from pathlib import Path
from datetime import date,datetime,timezone
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; LATEST=DATA/'latest.json'; HISTORY=DATA/'history.json'; OVERRIDES=DATA/'manual_overrides.json'
SYMBOLS=['SPY','QQQ','HOOD','ARKK','SMH','XBI','IWM','RSP']
WEIGHTS={'hood':14,'hoodqqq':14,'arkk':10,'breadth':10,'vix':8,'oil':9,'teny':11,'twoy':6,'fed':8,'cpi':5,'riskoff':5}
MACRO_IDS={'oil','teny','twoy','fed','cpi'}; SPEC_IDS={'hood','hoodqqq','arkk','breadth','vix','riskoff'}
FRED_IDS={'DGS10':'DGS10','DGS2':'DGS2','VIX':'VIXCLS','BRENT':'DCOILBRENTEU','WTI':'DCOILWTICO','FED':'DFEDTARU','CORE_CPI':'CPILFESL'}

def clamp(x,lo=0,hi=10): return max(lo,min(hi,float(x)))
def lin(x,a,b,lo=0,hi=10): return lo+(hi-lo)*(x-a)/(b-a)
def req_json(url,headers=None):
    r=urllib.request.Request(url,headers=headers or {'User-Agent':'Mozilla/5.0 correction-index'})
    with urllib.request.urlopen(r,timeout=20) as x:return json.loads(x.read().decode())
def yahoo_bars(symbol):
    u=f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=1mo&interval=1d&includePrePost=false"
    j=req_json(u); r=j['chart']['result'][0]; q=r['indicators']['quote'][0]; out=[]
    for t,c in zip(r['timestamp'],q['close']):
        if c is not None: out.append({'t':t,'c':float(c)})
    return out
def alpaca_bars(symbols):
    key=os.getenv('ALPACA_API_KEY','').strip(); sec=os.getenv('ALPACA_API_SECRET','').strip()
    if not key or not sec:return None
    p=urllib.parse.urlencode({'symbols':','.join(symbols),'timeframe':'1Day','limit':'1000','adjustment':'raw','feed':'iex'})
    j=req_json('https://data.alpaca.markets/v2/stocks/bars?'+p,{'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':sec,'User-Agent':'correction-index'})
    return {s:[{'t':r['t'],'c':float(r['c'])} for r in rows if r.get('c') is not None] for s,rows in j.get('bars',{}).items()}
def fetch_equities():
    try:
        a=alpaca_bars(SYMBOLS)
        if a and all(len(a.get(s,[]))>=7 for s in SYMBOLS):return a,'Alpaca'
    except Exception as e:print('Alpaca failed:',e)
    out={}
    for s in SYMBOLS:
        try:out[s]=yahoo_bars(s)
        except Exception as e:print('Yahoo failed',s,e);out[s]=[]
    missing=[s for s in SYMBOLS if len(out[s])<7]
    if missing:raise RuntimeError('Incomplete equity data: '+', '.join(missing))
    return out,'Yahoo fallback'
def parse_fred_csv(text,series):
    for row in csv.DictReader(io.StringIO(text.lstrip('\ufeff'))):
        observed=row.get('observation_date') or row.get('DATE')
        if not observed:continue
        for sid in series:
            raw=row.get(sid)
            if raw and raw!='.':
                series[sid].append((observed,float(raw)))
def fetch_fred():
    ids=list(FRED_IDS.values());url='https://fred.stlouisfed.org/graph/fredgraph.csv?'+urllib.parse.urlencode({'id':','.join(ids)})
    for attempt in range(2):
        try:
            if attempt==0:
                request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 correction-index'})
                with urllib.request.urlopen(request,timeout=15) as response:payload=response.read()
            else:
                payload=subprocess.run(['curl','-fsSL','--connect-timeout','10','--max-time','60',url],check=True,capture_output=True,timeout=70).stdout
            series={sid:[] for sid in ids}
            if zipfile.is_zipfile(io.BytesIO(payload)):
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    for name in archive.namelist():
                        if name.lower().endswith('.csv'):
                            parse_fred_csv(archive.read(name).decode('utf-8-sig'),series)
            else:
                parse_fred_csv(payload.decode('utf-8-sig'),series)
            today=datetime.now(timezone.utc).date()
            for sid,rows in series.items():
                if len(rows)<(13 if sid=='CPILFESL' else 1):raise ValueError('Missing FRED observations for '+sid)
                age=(today-date.fromisoformat(rows[-1][0])).days
                if age<0 or age>(75 if sid=='CPILFESL' else 10):raise ValueError(f'Stale FRED observations for {sid}: {rows[-1][0]}')
            return series
        except Exception as e:
            if attempt==1:raise RuntimeError('FRED data unavailable; keeping the last published snapshot') from e
            print(f'FRED attempt {attempt+1} failed:',e)
def last(rows):return rows[-1]['c'] if rows else None
def pct(rows,d=1):
    if len(rows)<d+1:return None
    a,b=rows[-d-1]['c'],rows[-1]['c'];return (b/a-1)*100 if a else None
def fp(x):return '—' if x is None else f'{x:+.2f}%'
def fn(x,n=2,p='',s=''):return '—' if x is None else f'{p}{x:.{n}f}{s}'
def loadj(p,d):
    try:return json.loads(p.read_text())
    except:return d
def core_cpi_yoy(series):
    v=series['CPILFESL']
    return (v[-1][1]/v[-13][1]-1)*100

def build(eq,m,overrides):
    r=lambda s,d:pct(eq.get(s,[]),d)
    h5,q5=r('HOOD',5),r('QQQ',5); rel=(h5-q5) if h5 is not None and q5 is not None else 0
    hood=clamp(lin(-(h5 or 0),0,12,4,10)); hoodqqq=clamp(lin(-rel,0,10,3.5,10))
    diffs=[x-q5 for x in [r('ARKK',5),r('SMH',5),r('XBI',5)] if x is not None and q5 is not None]; hb=statistics.mean(diffs) if diffs else 0
    arkk=clamp(lin(-hb,0,8,3,10))
    b=[]; spy5=r('SPY',5); rsp5=r('RSP',5); iwm5=r('IWM',5)
    if rsp5 is not None and spy5 is not None:b.append(rsp5-spy5)
    if iwm5 is not None and q5 is not None:b.append(iwm5-q5)
    br=statistics.mean(b) if b else 0; breadth=clamp(lin(-br,0,6,3,10))
    vix=m.get('VIX')
    if vix is None:vixs=5
    elif vix<14:vixs=9.5
    elif vix<16:vixs=9
    elif vix<18:vixs=8
    elif vix<22:vixs=6
    elif vix<28:vixs=4
    else:vixs=3
    oil=max([x for x in [m.get('BRENT'),m.get('WTI')] if x is not None],default=None); oils=5 if oil is None else clamp(lin(oil,70,110,2,10))
    ten,two,fed,core=m.get('DGS10'),m.get('DGS2'),m.get('FED'),m.get('CORE_CPI_YOY')
    tens=5 if ten is None else clamp(lin(ten,4.0,5.10,2.5,10)); twos=5 if two is None else clamp(lin(two,3.5,5.0,2.5,10))
    gap=(two-fed) if two is not None and fed is not None else None; feds=5 if gap is None else clamp(lin(gap,-.75,.75,3,10)); cpis=5 if core is None else clamp(lin(core,2,4,2.5,10))
    rets=[r(s,1) for s in ['QQQ','IWM','ARKK','XBI']]; rets=[x for x in rets if x is not None]; avg=statistics.mean(rets) if rets else 0; risk=clamp(lin(-avg,0,3.5,3,10))
    base={'hood':(hood,f'HOOD 5D {fp(h5)}','euphoria后的5日回撤'),'hoodqqq':(hoodqqq,f'5D相对 {fp(rel)}','HOOD相对QQQ越弱，风险越高'),'arkk':(arkk,f'高beta相对 {fp(hb)}','ARKK/SMH/XBI相对QQQ'),'breadth':(breadth,f'breadth相对 {fp(br)}','RSP/SPY + IWM/QQQ代理'),'vix':(vixs,fn(vix),'低VIX与高宏观风险并存=complacency'),'oil':(oils,f"Brent {fn(m.get('BRENT'),2,'$')} / WTI {fn(m.get('WTI'),2,'$')}",'高油价增加通胀压力'),'teny':(tens,fn(ten,3,s='%'),'5%附近为关键阈值'),'twoy':(twos,fn(two,3,s='%'),'短端反映政策路径'),'fed':(feds,'—' if gap is None else f'2Y-Fed {gap:+.2f}pp','2Y与政策上限差作为代理'),'cpi':(cpis,fn(core,2,s='% YoY'),'核心CPI同比压力代理'),'riskoff':(risk,f'1D basket {fp(avg)}','QQQ/IWM/ARKK/XBI平均')}
    manual=(overrides or {}).get('signals',{}); out=[]
    for sid,(score,raw,note) in base.items():
        if sid in manual and isinstance(manual[sid],(int,float)):score=clamp(manual[sid]);note+=' · 手动覆盖'
        out.append({'id':sid,'score':round(score,2),'raw_display':raw,'note':note,'weight':WEIGHTS[sid]})
    return out

def main():
    DATA.mkdir(exist_ok=True); eq,provider=fetch_equities(); fred=fetch_fred()
    m={k:fred[sid][-1][1] for k,sid in FRED_IDS.items() if k!='CORE_CPI'}
    m['CORE_CPI_YOY']=core_cpi_yoy(fred)
    signals=build(eq,m,loadj(OVERRIDES,{'signals':{}})); total=sum(s['score']*s['weight'] for s in signals)/100
    sub=lambda ids:sum(s['score']*s['weight'] for s in signals if s['id'] in ids)/sum(s['weight'] for s in signals if s['id'] in ids)
    now=datetime.now(timezone.utc); syd=now.astimezone(ZoneInfo('Australia/Sydney')); market={}
    for s in SYMBOLS:
        rows=eq.get(s,[]); market[s]={'display':f"{last(rows):.2f} ({fp(pct(rows,1))})" if last(rows) is not None else '—'}
    for key,display in {'VIX':fn(m['VIX']),'DGS10':fn(m['DGS10'],3,s='%'),'DGS2':fn(m['DGS2'],3,s='%'),'BRENT':fn(m['BRENT'],2,'$'),'WTI':fn(m['WTI'],2,'$')}.items():
        observed=fred[FRED_IDS[key]][-1][0]
        market[key]={'display':f'{display} ({observed})','asof':observed}
    payload={'version':2,'updated_at':now.isoformat(),'updated_at_display':syd.strftime('%Y-%m-%d %H:%M Sydney'),'freshness':'自动更新' if provider=='Alpaca' else '自动更新 · 后备行情','provider_note':f'股票/ETF: {provider}；宏观: FRED（括号内为数据日期）。GitHub Action 每小时重算。','score':round(total,2),'macro_score':round(sub(MACRO_IDS),2),'spec_score':round(sub(SPEC_IDS),2),'signals':signals,'market':market}
    LATEST.write_text(json.dumps(payload,ensure_ascii=False,indent=2)); hist=loadj(HISTORY,[]); hist.append({'updated_at':now.isoformat(),'score':payload['score'],'macro_score':payload['macro_score'],'spec_score':payload['spec_score']}); HISTORY.write_text(json.dumps(hist[-1000:],ensure_ascii=False,indent=2)); print(json.dumps({'score':payload['score'],'provider':provider,'updated':payload['updated_at_display']},ensure_ascii=False))
if __name__=='__main__':main()
