# StockPilot AI

Live Indian market dashboard and pre-breakout scanner using Upstox API V3.

## Files
- app.py
- requirements.txt
- README.md

## Streamlit Secret
```toml
UPSTOX_ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"
```

Never commit the token to GitHub.

## Current live engine
- Upstox V3 OHLC quotes
- Upstox V3 historical daily candles
- Upstox NSE equity instrument master
- Fresh scan on button press
- 150 SMA / 220 EMA / 50 SMA rules
- 52-week low and high
- 90-session 220 EMA dip
- 15% risk stop
- breakout / ready / forming / near-miss states
- conviction score

No orders are executed.
