# StockPilot AI V5

Mobile-friendly Indian-market intelligence dashboard built with Streamlit, Python and Upstox V3.

## Files

- `app.py` — complete Streamlit application
- `requirements.txt` — Python dependencies
- `README.md` — project/setup notes

## V5 features

- Full NSE equity universe discovery from the Upstox instrument master
- Upstox V3 Full Market Quotes with 500-instrument request batching
- Live pre-filter: price above 1.25× trailing 52-week low and within 10% of trailing 52-week high
- Historical daily validation for the strongest live candidates
- Strict strategy conditions:
  1. 150 SMA > 220 EMA
  2. Price > 50 SMA
  3. 50 SMA > 150 SMA
  4. Price > 1.25 × 52-week low
  5. Low below 220 EMA at least once during the prior 90 sessions
  6. Completed-candle 52-week closing breakout confirmation
- Statuses: TRIGGERED, READY, BREAKOUT WATCH, FORMING, NEAR MISS
- Score, breakout distance, stop, Target 1 and Target 2
- NIFTY 50, BANK NIFTY, NIFTY MIDCAP 100, NIFTY SMALLCAP 100 and INDIA VIX cards
- Highest Conviction Setups dashboard
- Top Setups page
- Strategy checklist for selected setups
- Daily chart with SMA 50, SMA 150, EMA 220, breakout level and swing markers
- Mobile-friendly dark dashboard layout
- No fake market data
- No automatic order execution

## Streamlit Secrets

Add the Upstox Analytics Token in Streamlit Cloud → Settings → Secrets:

```toml
UPSTOX_ACCESS_TOKEN = "YOUR_TOKEN"
```

Never commit the token to GitHub.

## Deployment

Repository structure must remain exactly:

```text
stock-pilot-ai/
├── app.py
├── requirements.txt
└── README.md
```

Streamlit entry point: `app.py`

## Notes

The scanner intentionally remains strict to reduce low-quality signals. A `BREAKOUT WATCH` or `READY` status is not a guarantee of a trade. The app is for research/information and does not place orders.
