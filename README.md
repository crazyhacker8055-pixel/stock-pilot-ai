# StockPilot AI V6

Mobile-friendly Indian market intelligence dashboard using Upstox V3.

## V6
- Full NSE equity live quote pre-filter.
- Strict pre-breakout strategy retained.
- Highest Conviction Setups ranking.
- Entry/live price, breakout, stop, targets and trend metrics.
- Strategy checklist.
- SMC chart engine using transparent OHLC-based heuristics for:
  - Swing structure
  - BOS (Break of Structure)
  - CHOCH (Change of Character)
  - Fair Value Gaps (FVG)
  - Order Blocks
  - Liquidity sweeps
- No fake market data.
- No order execution.

## Files
- `app.py`
- `requirements.txt`
- `README.md`

## Streamlit Secret

```toml
UPSTOX_ACCESS_TOKEN = "YOUR_TOKEN"
```

Never commit the token to GitHub.

## Important SMC note
The SMC engine is deliberately rule-based and uses OHLC history. It is not Level-2/order-book/order-flow data. Patterns are shown only when the defined price-action rules detect them.
