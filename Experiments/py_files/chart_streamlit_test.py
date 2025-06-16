# streamlit_random_candles.py

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from dateutil import tz
import plotly.graph_objects as go

st.title("📈 Random Candlestick with Hover-Only TP/SL")

# — Sidebar inputs —
bars     = st.sidebar.number_input("Number of Bars", min_value=20, max_value=500, value=100, step=10)
interval = st.sidebar.selectbox("Interval (min)", [1, 5, 10, 15, 30], index=1)
side     = st.sidebar.radio("Signal Side", ["Buy", "Sell"])
tp_pct   = st.sidebar.slider("Take Profit %", 0.2, 5.0, 2.0, step=0.1)
sl_pct   = st.sidebar.slider("Stop Loss %", 0.2, 5.0, 2.0, step=0.1)

# — Generate random OHLC data —
def make_random_candles(n, freq_minutes):
    end = datetime.now(timezone.utc)
    dates = pd.date_range(end=end, periods=n, freq=f"{freq_minutes}T")
    # start price and random walk
    price = 100 + np.cumsum(np.random.randn(n))  
    # open/close as walk, high/low around them
    opens  = price + np.random.randn(n) * 0.5
    closes = price + np.random.randn(n) * 0.5
    highs  = np.maximum(opens, closes) + np.random.rand(n) * 1.0
    lows   = np.minimum(opens, closes) - np.random.rand(n) * 1.0
    return pd.DataFrame({
        "open":  opens,
        "high":  highs,
        "low":   lows,
        "close": closes
    }, index=dates)

df = make_random_candles(bars, interval)

# — Pick a trade bar (e.g. 10 bars ago) —
trade_idx   = -10
trade_time  = df.index[trade_idx]
trade_price = float(df["close"].iloc[trade_idx])
take_profit = trade_price * (1 + tp_pct/100) if side=="Buy" else trade_price * (1 - tp_pct/100)
stop_loss   = trade_price * (1 - sl_pct/100) if side=="Buy" else trade_price * (1 + sl_pct/100)

# — Build the Plotly figure —
fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=df.index,
    open=df["open"], high=df["high"],
    low=df["low"],   close=df["close"],
    name="Price"
))
# arrow marker
fig.add_trace(go.Scatter(
    x=[trade_time], y=[trade_price],
    mode="markers",
    marker=dict(
        symbol="arrow-up" if side=="Buy" else "arrow-down",
        size=18,
        color="green" if side=="Buy" else "red"
    ),
    hovertemplate=(
        f"{side} @ {trade_price:.2f}<br>"
        f"<span style='color:green'>TP: {take_profit:.2f}</span><br>"
        f"<span style='color:red'>SL: {stop_loss:.2f}</span><extra></extra>"
    ),
    name="Trade"
))
# remove any default shapes
fig.update_layout(
    shapes=[],
    xaxis=dict(rangeslider=dict(visible=False)),
    margin=dict(l=20,r=20,t=30,b=20),
    height=600
)

# — Embed with Plotly.js hover logic —
fig_json = fig.to_json()

html = f"""
<div id="chart"></div>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<script>
  const fig = {fig_json};
  Plotly.newPlot('chart', fig.data, fig.layout).then(plot => {{
    plot.on('plotly_hover', event => {{
      if(event.points[0].data.name === 'Trade') {{
        Plotly.relayout('chart', {{
          shapes: [
            {{
              type: 'line', xref: 'paper', x0: 0, x1: 1,
              yref: 'y', y0: {take_profit}, y1: {take_profit},
              line: {{color: 'green', dash: 'dash'}}
            }},
            {{
              type: 'line', xref: 'paper', x0: 0, x1: 1,
              yref: 'y', y0: {stop_loss}, y1: {stop_loss},
              line: {{color: 'red', dash: 'dash'}}
            }}
          ]
        }});
      }}
    }});
    plot.on('plotly_unhover', event => {{
      Plotly.relayout('chart', {{shapes: []}});
    }});
  }});
</script>
"""

st.components.v1.html(html, height=650)
