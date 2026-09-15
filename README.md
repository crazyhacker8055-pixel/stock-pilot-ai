# StockPilot AI

Live Indian-market scanner using Upstox V3 and Streamlit.

## Current build
- Live Upstox connection from Streamlit Secrets
- Full NSE equity quote pre-filter using Upstox V3 Full Market Quotes
- Up to 500 instruments per quote request
- Historical daily validation for strongest candidates
- Strict pre-breakout strategy:
  - 150 SMA > 220 EMA
  - price > 50 SMA
  - 50 SMA > 150 SMA
  - price > 1.25 × trailing 52-week low
  - low below 220 EMA at least once in prior 90 sessions
  - closing breakout confirmation tracked separately from live intraday price
- NIFTY 50, BANK NIFTY, NIFTY MIDCAP 100, NIFTY SMALLCAP 100 and INDIA VIX cards
- No fake market data
- No automatic order execution

## Secrets
Add this in Streamlit Cloud Settings → Secrets:

```toml
UPSTOX_ACCESS_TOKEN = "YOUR_TOKEN"
```

Never commit the token to GitHub.

## V3 fixes
- Correctly maps Upstox V3 quote responses keyed as `EXCHANGE:SYMBOL` back to `instrument_key`.
- Fixes index quote lookup.
- Removes Streamlit magic rendering of the sidebar connection expression.
- Fixes closing-breakout confirmation so the breakout level excludes the same completed candle being tested.
