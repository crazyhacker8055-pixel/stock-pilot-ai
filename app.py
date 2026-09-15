from __future__ import annotations

import io, os
from datetime import date, timedelta, datetime
from urllib.parse import quote
import gzip
import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go
import streamlit as st

APP_NAME = "StockPilot AI"
UPSTOX_BASE = "https://api.upstox.com/v3"

st.set_page_config(page_title=APP_NAME, page_icon="📈", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container{padding:1rem 1rem 2rem;max-width:1500px}
[data-testid="stSidebar"]{background:#07111d}
div[data-testid="stMetric"]{background:#0b1420;border:1px solid #1d2b3a;padding:10px;border-radius:12px}
@media(max-width:700px){.block-container{padding-left:.55rem;padding-right:.55rem}}
</style>
""", unsafe_allow_html=True)

def get_token():
    try:
        v = st.secrets.get("UPSTOX_ACCESS_TOKEN")
        if v: return str(v)
    except Exception:
        pass
    return os.getenv("UPSTOX_ACCESS_TOKEN")

TOKEN = get_token()

class Upstox:
    def __init__(self, token):
        self.headers = {"Accept":"application/json",
                        "Authorization":f"Bearer {token}"}
    def get(self, path, params=None):
        r = requests.get(UPSTOX_BASE + path, headers=self.headers,
                         params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    def candles(self, key, days=400):
        end = date.today()
        start = end - timedelta(days=days)
        k = quote(key, safe="")
        p = f"/historical-candle/{k}/days/1/{end:%Y-%m-%d}/{start:%Y-%m-%d}"
        return candles_df(self.get(p))
    def ohlc(self, keys, interval="1d"):
        return self.get("/market-quote/ohlc",
                        {"instrument_key":",".join(keys),"interval":interval}).get("data",{})

def candles_df(payload):
    rows = payload.get("data",{}).get("candles",[])
    data = []
    for c in rows:
        if len(c) >= 6:
            data.append(c[:7])
    df = pd.DataFrame(data, columns=["timestamp","open","high","low","close","volume","open_interest"])
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    return df

def indicators(df):
    x = df.copy()
    x["sma50"] = x.close.rolling(50).mean()
    x["sma150"] = x.close.rolling(150).mean()
    x["ema220"] = x.close.ewm(span=220, adjust=False).mean()
    x["low52"] = x.low.rolling(252, min_periods=200).min()
    x["high52"] = x.high.rolling(252, min_periods=200).max()
    x["avgvol20"] = x.volume.rolling(20).mean()
    x["range_pct"] = (x.high-x.low)/x.close.replace(0,np.nan)
    x["avg_range20"] = x.range_pct.rolling(20).mean()
    return x

def evaluate(df, live_price=None):
    x = indicators(df)
    if len(x) < 260:
        return {"status":"INSUFFICIENT DATA","score":0,"reason":"Need 260 daily candles."}
    r = x.iloc[-1]
    price = float(live_price if live_price is not None else r.close)
    cond = {
        "150 SMA > 220 EMA": bool(r.sma150 > r.ema220),
        "Price > 50 SMA": bool(price > r.sma50),
        "50 SMA > 150 SMA": bool(r.sma50 > r.sma150),
        "Price > 1.25 x 52W low": bool(pd.notna(r.low52) and price > 1.25*r.low52),
        "220 EMA dip in last 90 sessions": bool((x.tail(90).low < x.tail(90).ema220).any()),
    }
    prior = x.iloc[:-1]
    breakout = float(prior.tail(252).high.max())
    confirmed = price > breakout
    near = (price < breakout) and (price >= breakout*0.97)
    volume_ok = bool(pd.notna(r.avgvol20) and r.volume >= .8*r.avgvol20)
    contraction = bool(pd.notna(r.avg_range20) and r.range_pct <= 1.25*r.avg_range20)
    score = int(round(min(100, sum(cond.values())/5*70 +
                          (10 if volume_ok else 0) +
                          (10 if contraction else 0) +
                          (10 if confirmed else 5 if near else 0))))
    if confirmed and all(cond.values()):
        status = "TRIGGERED"
    elif all(cond.values()) and near:
        status = "READY"
    elif sum(cond.values()) >= 4:
        status = "FORMING"
    else:
        status = "NEAR MISS"
    return {"status":status,"score":score,"price":price,
            "breakout_level":breakout,"stop":price*.85,
            "ema220":float(r.ema220),"sma50":float(r.sma50),
            "sma150":float(r.sma150),"low52":float(r.low52),
            "high52":float(r.high52),"conditions":cond}

@st.cache_data(ttl=3600, show_spinner=False)
def instruments():
    urls = [
        "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz",
        "https://assets.upstox.com/market-quote/instruments/exchange/complete.json",
    ]
    err = None
    for url in urls:
        try:
            raw = requests.get(url, timeout=45).content
            if url.endswith(".gz"): raw = gzip.decompress(raw)
            df = pd.read_json(io.BytesIO(raw))
            if "segment" in df: df = df[df.segment.astype(str)=="NSE_EQ"]
            if "instrument_type" in df: df = df[df.instrument_type.astype(str)=="EQ"]
            return df.drop_duplicates("instrument_key").reset_index(drop=True)
        except Exception as e:
            err = e
    raise RuntimeError(f"Instrument master download failed: {err}")

@st.cache_data(ttl=45, show_spinner=False)
def scan(token, symbol, key):
    u = Upstox(token)
    df = u.candles(key, 400)
    if df.empty: return {"symbol":symbol,"status":"NO DATA","score":0}
    live = None
    try:
        q = u.ohlc([key])
        item = next(iter(q.values()))
        liveobj = item.get("live_ohlc", {})
        live = liveobj.get("close") or item.get("last_price")
    except Exception:
        pass
    r = evaluate(df, live)
    r.update({"symbol":symbol,"instrument_key":key})
    return r

with st.sidebar:
    st.markdown("## 📈 StockPilot AI")
    st.caption("Indian Market Intelligence")
    page = st.radio("Navigation",
        ["Dashboard","Live Scanner","Top Setups","Watchlist","Portfolio",
         "SMC Charts","News & Alerts","Results Calendar","Corporate Actions",
         "FII/DII Data","Sector Heatmap","Backtesting","Settings"],
        label_visibility="collapsed")
    st.divider()
    if TOKEN: st.success("🟢 UPSTOX CONNECTED")
    else: st.error("🔴 UPSTOX TOKEN REQUIRED")

st.title("StockPilot AI")
st.caption("Pre-breakout intelligence • SMC • market structure • risk-aware setups")

if not TOKEN:
    st.warning("Add UPSTOX_ACCESS_TOKEN to Streamlit Secrets. No fake market data is used.")
    st.stop()

u = Upstox(TOKEN)

index_keys = {
    "NIFTY 50":"NSE_INDEX|Nifty 50",
    "BANK NIFTY":"NSE_INDEX|Nifty Bank",
    "INDIA VIX":"NSE_INDEX|India VIX",
}
try:
    iq = u.ohlc(list(index_keys.values()))
except Exception as e:
    iq = {}
    st.error(f"Upstox quote error: {e}")

cols = st.columns(3)
for col,(name,key) in zip(cols,index_keys.items()):
    item = iq.get(key,{})
    live = item.get("live_ohlc",{})
    price = live.get("close") or item.get("last_price")
    prev = item.get("prev_ohlc",{}).get("close")
    delta = (price-prev)/prev*100 if price and prev else None
    with col:
        st.metric(name, f"{price:,.2f}" if price else "N/A",
                  f"{delta:+.2f}%" if delta is not None else None)

st.divider()

if page == "Dashboard":
    st.markdown("### 🔥 Highest Conviction Setups")
    out = st.session_state.get("scan_results")
    if out is None:
        st.info("Run Live Scanner to populate this table with fresh Upstox data.")
    else:
        st.dataframe(out[["symbol","status","score","price","breakout_level","stop"]]
                     .rename(columns={"symbol":"Stock","status":"Status","score":"Score",
                                      "price":"Live Price","breakout_level":"Breakout Level",
                                      "stop":"15% Risk Stop"}),
                     use_container_width=True, hide_index=True)
    st.success(f"🟢 Live Upstox connection • Refreshed {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")

elif page == "Live Scanner":
    st.markdown("### ⚡ Live Scanner")
    st.caption("Every scan retrieves market data from Upstox and recalculates the strategy.")
    uni = instruments()
    st.write(f"NSE equity universe: **{len(uni):,} instruments**")
    symbols = st.multiselect("Stocks to scan",
        sorted(uni.trading_symbol.astype(str).tolist()),
        default=[s for s in ["HAL","BEL","BHEL","BAJAJELEC","RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK"]
                  if s in set(uni.trading_symbol.astype(str))],
        max_selections=100)
    if st.button("🚀 RUN LIVE SCAN", type="primary", use_container_width=True):
        results=[]; bar=st.progress(0)
        for i,symbol in enumerate(symbols):
            row=uni[uni.trading_symbol.astype(str)==symbol].iloc[0]
            try: results.append(scan(TOKEN,symbol,row.instrument_key))
            except Exception as e: results.append({"symbol":symbol,"status":"ERROR","score":0,"reason":str(e)})
            bar.progress((i+1)/max(1,len(symbols)))
        st.session_state["scan_results"]=pd.DataFrame(results).sort_values(["score","symbol"],ascending=[False,True])
        st.session_state["scan_time"]=datetime.now()
    out=st.session_state.get("scan_results")
    if out is not None:
        st.dataframe(out,use_container_width=True,hide_index=True)
        st.caption(f"Last scan: {st.session_state.get('scan_time')} • Source: Upstox V3")

elif page == "Top Setups":
    out=st.session_state.get("scan_results")
    if out is None: st.info("Run Live Scanner first.")
    else: st.dataframe(out.head(20),use_container_width=True,hide_index=True)
elif page == "SMC Charts":
    st.info("Live data is connected. SMC chart engine will be added to this same application next.")
else:
    st.info(f"{page} module is planned in the next build stage.")

st.caption("StockPilot AI • Upstox V3 • No orders are executed automatically.")
