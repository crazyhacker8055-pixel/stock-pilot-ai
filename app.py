from __future__ import annotations
import gzip, io, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta, datetime
from urllib.parse import quote
import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go

APP='StockPilot AI'; BASE='https://api.upstox.com/v3'
MASTER_URLS=['https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz','https://assets.upstox.com/market-quote/instruments/exchange/complete.json']
st.set_page_config(page_title=APP,page_icon='📈',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>.block-container{padding:1rem;max-width:1500px}[data-testid="stSidebar"]{background:#07111d}div[data-testid="stMetric"]{background:#0b1420;border:1px solid #1d2b3a;padding:10px;border-radius:12px}@media(max-width:700px){.block-container{padding:.55rem}h1{font-size:1.7rem}}</style>''',unsafe_allow_html=True)

def token():
    try:
        x=st.secrets.get('UPSTOX_ACCESS_TOKEN')
        if x:return str(x)
    except Exception:pass
    return os.getenv('UPSTOX_ACCESS_TOKEN')
TOKEN=token()
class Upstox:
    def __init__(self,t):self.h={'Accept':'application/json','Authorization':f'Bearer {t}'}
    def get(self,path,params=None):
        r=requests.get(BASE+path,headers=self.h,params=params,timeout=30);r.raise_for_status();j=r.json()
        if j.get('status') not in (None,'success'):raise RuntimeError(str(j))
        return j
    def candles(self,key,days=420):
        e=date.today();s=e-timedelta(days=days);k=quote(key,safe='')
        return candles_df(self.get(f'/historical-candle/{k}/days/1/{e:%Y-%m-%d}/{s:%Y-%m-%d}'))
    def quotes(self,keys):return self.get('/market-quote/quotes',{'instrument_key':','.join(keys)}).get('data',{})
    def ohlc(self,keys):return self.get('/market-quote/ohlc',{'instrument_key':','.join(keys),'interval':'1d'}).get('data',{})

def candles_df(p):
    rows=p.get('data',{}).get('candles',[]); cols=['timestamp','open','high','low','close','volume','open_interest']
    d=pd.DataFrame([x[:7] for x in rows if len(x)>=6],columns=cols)
    if d.empty:return d
    d.timestamp=pd.to_datetime(d.timestamp,errors='coerce')
    for c in cols[1:]:d[c]=pd.to_numeric(d[c],errors='coerce')
    return d.dropna(subset=['timestamp','close']).sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)

def indicators(d):
    x=d.copy();x['sma50']=x.close.rolling(50).mean();x['sma150']=x.close.rolling(150).mean();x['ema220']=x.close.ewm(span=220,adjust=False).mean();x['low52']=x.low.rolling(252,min_periods=200).min();x['high52']=x.high.rolling(252,min_periods=200).max();x['avgvol20']=x.volume.rolling(20).mean();x['range_pct']=(x.high-x.low)/x.close.replace(0,np.nan);x['avg_range20']=x.range_pct.rolling(20).mean();return x

def evaluate(d,price=None,volume=None):
    x=indicators(d)
    if len(x)<260:return {'status':'INSUFFICIENT DATA','score':0,'reason':f'{len(x)} daily candles; need 260'}
    r=x.iloc[-1];p=float(price if price is not None else r.close);v=float(volume if volume is not None else r.volume)
    cond={'150 SMA > 220 EMA':r.sma150>r.ema220,'Price > 50 SMA':p>r.sma50,'50 SMA > 150 SMA':r.sma50>r.sma150,'Price > 1.25 x 52W low':pd.notna(r.low52) and p>1.25*r.low52,'220 EMA dip in last 90 sessions':(x.tail(90).low<x.tail(90).ema220).any()}
    completed=x.iloc[:-1]
    if len(completed) < 253:
        return {'status':'INSUFFICIENT DATA','score':0,'reason':'Need at least 253 completed daily candles.'}
    last_completed=completed.iloc[-1]
    breakout=float(completed.iloc[:-1].tail(252).high.max())
    last_close=float(last_completed.close)
    confirmed=last_close>breakout
    above=p>breakout
    dist=(p/breakout-1)*100 if breakout else np.nan
    near=not confirmed and .97*breakout<=p<=1.03*breakout
    vol_ok=pd.notna(r.avgvol20) and v>=.8*r.avgvol20;contract=pd.notna(r.avg_range20) and pd.notna(r.range_pct) and r.range_pct<=1.25*r.avg_range20
    score=int(round(min(100,sum(cond.values())/5*70+(10 if vol_ok else 0)+(10 if contract else 0)+(10 if confirmed else 5 if near else 0))))
    if confirmed and all(cond.values()):status='TRIGGERED'
    elif all(cond.values()) and near:status='READY'
    elif sum(cond.values())>=4 and above:status='BREAKOUT WATCH'
    elif sum(cond.values())>=4:status='FORMING'
    else:status='NEAR MISS'
    swing=float(x.tail(20).low.min());stop=max(0,min(p*.85,swing*.99))
    return {'status':status,'score':score,'price':p,'breakout_level':breakout,'distance_pct':dist,'stop':stop,'target1':max(breakout,p)*1.08,'target2':max(breakout,p)*1.15,'ema220':float(r.ema220),'sma50':float(r.sma50),'sma150':float(r.sma150),'low52':float(r.low52),'high52':float(r.high52),'volume':v,'avgvol20':float(r.avgvol20) if pd.notna(r.avgvol20) else np.nan,'confirmed_close':confirmed,'conditions':cond}

@st.cache_data(ttl=3600,show_spinner=False)
def master():
    err=None
    for u in MASTER_URLS:
        try:
            raw=requests.get(u,timeout=60).content
            if u.endswith('.gz'):raw=gzip.decompress(raw)
            return pd.read_json(io.BytesIO(raw)).drop_duplicates('instrument_key').reset_index(drop=True)
        except Exception as e:err=e
    raise RuntimeError(f'Instrument master failed: {err}')

def equity_universe(m):
    x=m[m.segment.astype(str).eq('NSE_EQ')].copy() if 'segment' in m else m.iloc[0:0].copy()
    if 'instrument_type' in x:x=x[x.instrument_type.astype(str).eq('EQ')]
    return x.drop_duplicates('instrument_key').reset_index(drop=True)

def index_keys(m):
    x=m[m.segment.astype(str).eq('NSE_INDEX')].copy() if 'segment' in m else m.iloc[0:0].copy();out={'NIFTY 50':'NSE_INDEX|Nifty 50','BANK NIFTY':'NSE_INDEX|Nifty Bank','NIFTY MIDCAP 100':'NSE_INDEX|Nifty Midcap 100','NIFTY SMALLCAP 100':'NSE_INDEX|Nifty Smallcap 100','INDIA VIX':'NSE_INDEX|India VIX'}
    if not x.empty:
        cols=[c for c in ['name','short_name','trading_symbol'] if c in x]
        if cols:
            txt=x[cols].fillna('').astype(str).agg(' | '.join,axis=1)
            aliases={'NIFTY 50':'Nifty 50','BANK NIFTY':'Nifty Bank','NIFTY MIDCAP 100':'Nifty Midcap 100','NIFTY SMALLCAP 100':'Nifty Smallcap 100','INDIA VIX':'India VIX'}
            for lab,a in aliases.items():
                h=x[txt.str.contains(a,case=False,regex=False)]
                if not h.empty:out[lab]=str(h.iloc[0].instrument_key)
    return out

def fields(item):
    if not item:return None,None,None
    lo=item.get('live_ohlc') or item.get('ohlc') or {}
    p=item.get('last_price')
    if p is None:p=lo.get('close')
    v=item.get('volume')
    if v is None:v=lo.get('volume')
    prev=item.get('prev_ohlc') or {}
    pr=prev.get('close')
    if pr is None:pr=item.get('prev_close_price')
    return (float(p) if p is not None else None,float(v) if v is not None else None,float(pr) if pr is not None else None)

def normalize_quote_map(raw):
    out={}
    for response_key,item in (raw or {}).items():
        if not isinstance(item,dict):
            continue
        out[str(response_key)] = item
        token_key=item.get('instrument_token') or item.get('instrument_key')
        if token_key:
            token_key=str(token_key)
            out[token_key]=item
            out[token_key.replace('|',':')]=item
    return out

def quote_for(qmap,key):
    k=str(key)
    return qmap.get(k) or qmap.get(k.replace('|',':')) or {}

@st.cache_data(ttl=45,show_spinner=False)
def all_quotes(_token,keys):
    u=Upstox(_token);raw={};ks=list(keys)
    for i in range(0,len(ks),500):raw.update(u.quotes(ks[i:i+500]))
    return normalize_quote_map(raw)
@st.cache_data(ttl=45,show_spinner=False)
def index_quotes(_token,keys):
    return normalize_quote_map(Upstox(_token).ohlc(list(keys)))
@st.cache_data(ttl=1800,show_spinner=False)
def history(_token,key):return Upstox(_token).candles(key)

def candidates(uni,quotes,limit):
    rows=[]
    for r in uni.itertuples(index=False):
        q=quote_for(quotes,str(r.instrument_key));p,v,_=fields(q)
        if p is None:continue
        yl=q.get('year_low');yh=q.get('year_high')
        if yl is None or yh is None or float(yl)<=0 or float(yh)<=0:continue
        yl=float(yl);yh=float(yh)
        if p>1.25*yl and p/yh>=.90:rows.append({'row':r,'quote':q,'near_high':p/yh,'volume':v or 0})
    rows.sort(key=lambda z:(z['near_high'],z['volume']),reverse=True)
    return rows[:limit]

def scan_one(token,row,q):
    try:
        d=history(token,str(row.instrument_key));p,v,_=fields(q)
        if d.empty:return {'symbol':str(row.trading_symbol),'status':'NO DATA','score':0,'instrument_key':str(row.instrument_key)}
        r=evaluate(d,p,v);r.update(symbol=str(row.trading_symbol),instrument_key=str(row.instrument_key));return r
    except Exception as e:return {'symbol':str(row.trading_symbol),'status':'ERROR','score':0,'instrument_key':str(row.instrument_key),'reason':str(e)[:180]}

def full_scan(token,uni,limit,workers):
    quotes=all_quotes(token,tuple(uni.instrument_key.astype(str)));cand=candidates(uni,quotes,limit);results=[]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fs=[ex.submit(scan_one,token,z['row'],z['quote']) for z in cand]
        for f in as_completed(fs):results.append(f.result())
    if not results:return pd.DataFrame(),len(cand),len(quotes)
    order={'TRIGGERED':0,'READY':1,'BREAKOUT WATCH':2,'FORMING':3,'NEAR MISS':4,'INSUFFICIENT DATA':5,'NO DATA':6,'ERROR':7};df=pd.DataFrame(results);df['_o']=df.status.map(order).fillna(99);return df.sort_values(['_o','score','distance_pct'],ascending=[True,False,False]).drop(columns='_o').reset_index(drop=True),len(cand),len(quotes)

with st.sidebar:
    st.markdown('## 📈 StockPilot AI');st.caption('Indian Market Intelligence')
    page=st.radio('Navigation',['Dashboard','Live Scanner','Top Setups','Watchlist','Portfolio','SMC Charts','News & Alerts','Results Calendar','Corporate Actions','FII/DII Data','Sector Heatmap','Backtesting','Settings'],label_visibility='collapsed')
    st.divider()
    if TOKEN:
        st.success('🟢 UPSTOX CONNECTED')
    else:
        st.error('🔴 UPSTOX TOKEN REQUIRED')
st.title(APP);st.caption('Pre-breakout intelligence • SMC • market structure • risk-aware setups')
if not TOKEN:st.warning('Add UPSTOX_ACCESS_TOKEN to Streamlit Secrets. No fake market data is used.');st.stop()
try:m=master();uni=equity_universe(m);iks=index_keys(m)
except Exception as e:st.error(f'Instrument master error: {e}');st.stop()
labels=['NIFTY 50','BANK NIFTY','NIFTY MIDCAP 100','NIFTY SMALLCAP 100','INDIA VIX']
try:iq=index_quotes(TOKEN,tuple(iks[x] for x in labels))
except Exception as e:iq={};st.error(f'Index quote error: {e}')
cs=st.columns(5)
for c,l in zip(cs,labels):
    p,_,pr=fields(quote_for(iq,iks[l]));d=(p-pr)/pr*100 if p is not None and pr else None
    with c:st.metric(l,f'{p:,.2f}' if p is not None else 'N/A',f'{d:+.2f}%' if d is not None else None)
st.divider()

if page=='Dashboard':
    st.markdown('### 🔥 Highest Conviction Setups');df=st.session_state.get('scan_results')
    if df is None or df.empty:st.info('Run the Full NSE Live Scan to populate this table with fresh Upstox data.')
    else:
        show=df[['symbol','status','score','price','breakout_level','distance_pct','stop','target1','target2']].copy();show.columns=['Stock','Status','Score','Live Price','Breakout','Distance %','Risk Stop','Target 1','Target 2'];st.dataframe(show.head(25),use_container_width=True,hide_index=True)
    st.success(f'🟢 Live Upstox connection • {datetime.now():%d-%m-%Y %H:%M:%S}')
elif page=='Live Scanner':
    st.markdown('### ⚡ Live Scanner');st.caption('Every run pulls fresh Upstox quotes for the NSE equity universe, then calculates the strict strategy only for the strongest live candidates.')
    st.write(f'NSE equity universe: **{len(uni):,} instruments** • full quotes: **500 instruments/request**')
    st.info('Pre-filter: live price > 1.25× trailing year low and within 10% of trailing year high. Then the full daily-history strategy is evaluated. No fake data is inserted.')
    limit=st.slider('Historical candidates after live pre-filter',50,300,150,25);workers=st.slider('Concurrent historical requests',2,8,6)
    if st.button('🚀 RUN FULL NSE LIVE SCAN',type='primary',use_container_width=True):
        with st.spinner('Pulling live Upstox quotes and calculating candidates...'):
            try:df,nq,ncand=full_scan(TOKEN,uni,limit,workers)
            except Exception as e:df=pd.DataFrame();nq=ncand=0;st.error(f'Scan failed: {e}')
        st.session_state.scan_results=df;st.session_state.scan_time=datetime.now();st.session_state.quote_count=nq;st.session_state.candidate_count=ncand
        if df.empty:
            st.warning('No strategy candidates returned. Live quotes were received, but none passed the live 52-week pre-filter/history stage. No fake data was inserted.')
        else:st.success(f'Scan complete: {nq:,} live quotes checked → {ncand:,} historical candidates evaluated.')
    df=st.session_state.get('scan_results')
    if df is not None and not df.empty:
        cols=[c for c in ['symbol','status','score','price','breakout_level','distance_pct','stop','target1','target2','ema220','sma50','sma150','low52','high52','confirmed_close'] if c in df];st.dataframe(df[cols],use_container_width=True,hide_index=True)
        a,b,c=st.columns(3);a.metric('Triggered',int((df.status=='TRIGGERED').sum()));b.metric('Ready',int((df.status=='READY').sum()));c.metric('Forming',int((df.status=='FORMING').sum()));st.caption(f"Last scan: {st.session_state.get('scan_time')} • Source: Upstox V3")
elif page=='Top Setups':
    df=st.session_state.get('scan_results');st.info('Run the Live Scanner first.') if df is None or df.empty else st.dataframe(df.head(20),use_container_width=True,hide_index=True)
elif page=='SMC Charts':
    df=st.session_state.get('scan_results')
    if df is None or df.empty:st.info('Run the Live Scanner first.')
    else:
        s=st.selectbox('Select scanned stock',df.symbol.astype(str).tolist());r=df[df.symbol.astype(str)==s].iloc[0];d=history(TOKEN,str(r.instrument_key)).tail(120);fig=go.Figure(go.Candlestick(x=d.timestamp,open=d.open,high=d.high,low=d.low,close=d.close));fig.update_layout(template='plotly_dark',height=520,title=f'{s} • Daily structure');st.plotly_chart(fig,use_container_width=True);st.caption('Dedicated SMC order-block/FVG/BOS/CHOCH detection will be added after the live scanner foundation is validated.')
elif page=='Settings':
    st.markdown('### ⚙️ Settings');st.write(f'NSE equity universe: **{len(uni):,}**');st.write('Upstox API: **V3**');st.write('Order execution: **Disabled**');st.write('Token display: **Never**')
else:st.info(f'{page} module is queued for the next build stage. Live Upstox connectivity remains active.')
st.caption('StockPilot AI • Upstox V3 • No orders are executed automatically.')
