from calendar import c
from pydoc import resolve
from turtle import clear
from matplotlib import legend, scale
from matplotlib.pyplot import grid
from pyparsing import line
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime, timezone

st.title("📈 Candlestick with Hover-Only TP/SL (Altair) V3")

# — Sidebar controls —
bars = st.sidebar.number_input("Number of Bars", min_value=20, max_value=500, value=100, step=10)
interval = st.sidebar.selectbox("Interval (min)", [1, 5, 10, 15, 30], index=1)
side = st.sidebar.radio("Signal Side", ["Buy", "Sell"])
tp_pct = st.sidebar.slider("Take Profit %", 0.5, 10.0, 2.0, step=0.5)
sl_pct = st.sidebar.slider("Stop Loss %", 0.5, 10.0, 2.0, step=0.5)

# 1) Initialize your log buffer and container once
if "logs" not in st.session_state:
    st.session_state.logs = []              # list of log strings
if "log_container" not in st.session_state:
    st.session_state.log_container = st.empty()

def log(message: str):
    """Add a message to the log and refresh the display."""
    st.session_state.logs.append(message)
    # You can choose write(), text(), or text_area() here
    st.session_state.log_container.text("\n".join(st.session_state.logs))

# — 1) Generate random OHLC data —
def make_random_candles(n, freq_minutes):
    end = datetime.now(timezone.utc)
    dates = pd.date_range(end=end, periods=n, freq=f"{freq_minutes}T")
    price = 100 + np.cumsum(np.random.randn(n))
    opens = price + np.random.randn(n)*0.5
    closes = price + np.random.randn(n)*0.5
    highs = np.maximum(opens, closes) + np.random.rand(n)*1.0
    lows = np.minimum(opens, closes) - np.random.rand(n)*1.0

    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes
    })
# define a fixed y‐scale:


def add_trade_signal_to_chart(df, trade_time, side):
    hover_selection = alt.selection_point(
        fields=['date'],
        on='mouseover',
        empty=False,
        # clear='mouseout'
    )

    row_df = df[df['date'] == trade_time]
    if row_df.empty:
        return "Not found"
    else:
        log("Trade row found")
        high_price = row_df['high'].values[0]
        low_price = row_df['low'].values[0]
        trade_price = row_df['close'].values[0]
        if side == "Buy":
            take_profit = trade_price * (1 + tp_pct/100)
            stop_loss = trade_price * (1 - sl_pct/100)
            arrow_y = low_price - (high_price - low_price) * 0.2
        else:
            take_profit = trade_price * (1 - tp_pct/100)
            stop_loss = trade_price * (1 + sl_pct/100)
            arrow_y = high_price + (high_price - low_price) * 0.2
        log(f"Trade Price: {trade_price}, TP: {take_profit}, SL: {stop_loss}")
        log(f"Arrow Y: {arrow_y}")
        point_data = pd.DataFrame({
            "date": [trade_time],
            "arrow_y": [arrow_y],
            "Take Profit": [take_profit],
            "Stop Loss": [stop_loss],
            "Signal": [side]
        })
        
        arrow = alt.Chart(point_data).mark_point(
            shape="triangle-up" if side=="Buy" else "triangle-down",
            size=150,
            color="white",
            filled=True,
        ).encode(
            x="date:T",
            y=alt.Y("arrow_y:Q"),
            tooltip=[
                alt.Tooltip("Signal:N"),
                alt.Tooltip("arrow_y:Q",      title="Entry", format=".2f"),
                alt.Tooltip("Take Profit:Q",  title="TP",    format=".2f"),
                alt.Tooltip("Stop Loss:Q",    title="SL",    format=".2f"),
            ]
        ).add_params(hover_selection)

        lines_data = pd.DataFrame({
            "date": [trade_time, trade_time],
            "value": [take_profit, stop_loss],
            "level": ["TP", "SL"]
        })
        
        lines = alt.Chart(lines_data).mark_rule(
            strokeDash=[5, 5],
        ).encode(
            y=alt.Y("value:Q"),
            color=alt.Color("level:N",
                            scale=alt.Scale(domain=["TP", "SL"],
                                            range=["forestgreen", "crimson"]), legend=None),
            opacity=alt.condition(hover_selection, alt.value(1), alt.value(0))
        )
        log("Hello")
        return alt.layer(arrow, lines)

# Generate random OHLC data
df = make_random_candles(bars, interval)

# Create grid df
min_price = df['low'].min()
max_price = df['high'].max()
buffer = 0.01
step = 1
lower_bound = min_price * (1 - buffer)
upper_bound = max_price * (1 + buffer)
y_vals = np.arange(lower_bound, upper_bound + step/2, step)
y_vals = np.round(y_vals, 2)  # Round to 2 decimal places

grid_df = pd.DataFrame({
    "date": np.repeat(df['date'].values, len(y_vals)),
    "price": np.tile(y_vals, len(df)),
})
log(f"Grid DataFrame created with {len(grid_df)} rows.")
log(str(grid_df.head()))
# — 2) Pick a trade bar (10 bars ago) & compute TP/SL —
trade_idx = -10
row = df.iloc[trade_idx]
trade_time = row["date"]
log(f"Trade Time: {trade_time}")


color_up = alt.value("forestgreen")
color_down = alt.value("crimson")

open_close_color = alt.condition(
    alt.datum.close >= alt.datum.open,
    color_up,
    color_down
)

x_axis = alt.Axis(
    title="DateTime",
    format="%H:%M",
    labelExpr= """
    (hours(datum.value) === 0 && minutes(datum.value) === 0) ? timeFormat(datum.value, '%b %d, %Y'): timeFormat(datum.value, '%H:%M')
    """
)
base = alt.Chart(df).encode(
    alt.X('date:T',
          axis=x_axis,
    ),
    color=open_close_color
)

rule = base.mark_rule().encode(
    alt.Y('low:Q', title='Price', scale=alt.Scale(zero=False)),
    alt.Y2('high:Q')
)
bar = base.mark_bar().encode(
    alt.Y('open:Q'),
    alt.Y2('close:Q')
)
candlechart = rule + bar
# — 5) Add trade signal arrow with TP/SL lines —

# Add functionality to add cross hair
# Create a selection that chooses the nearest point & selects based on x-value
cross_hair_selection_date = alt.selection_point(
    on='mouseover',
    fields=['date'],
    nearest=True,
    empty='none',
    resolve='union'
    # empty='none',
)
cross_hair_selection_y = alt.selection_point(
    on='mouseover',
    fields=['price'],
    nearest=True,
    resolve='union',
)
#Vertical rule
hrule = alt.Chart(grid_df).mark_rule(
    color='red', 
).encode(
    y='price:Q'
    # opacity=alt.condition(cross_hair_selection, alt.value(0.8), alt.value(0.8))
).transform_filter(cross_hair_selection_y)

#Horizontal rule
vrule = alt.Chart(grid_df).mark_rule(
    color='red', 
).encode(
    x='date:T',
    # opacity=alt.condition(cross_hair_selection, alt.value(0.8), alt.value(0.8))
).transform_filter(cross_hair_selection_date)



# Draw text labels at the axes
x_label = alt.Chart(df).mark_text(align='center', baseline='top', dy=5, color='white').encode(
    x='date:T',
    text=alt.Text('date:T'),
    opacity=alt.condition(cross_hair_selection_date, alt.value(1), alt.value(0))
).transform_filter(cross_hair_selection_date)

y_label = alt.Chart(grid_df).mark_text(align='right', baseline='middle', dx=-5, color='white').encode(
    y='price:Q',
    text=alt.Text('price:Q'),
    opacity=alt.condition(cross_hair_selection_y, alt.value(1), alt.value(0))
).transform_filter(cross_hair_selection_y)

crosshair = alt.layer(
    hrule, vrule, x_label, y_label
)

signal_arrow = add_trade_signal_to_chart(df, trade_time, side)

date_range = pd.DataFrame({
    "min_date": [df["date"].min()],
    "max_date": [df["date"].max()]
})

chart = alt.layer(
    crosshair,
    candlechart, 
    signal_arrow,
    


).add_params(cross_hair_selection_date).add_params(cross_hair_selection_y).resolve_scale(
    y="shared"
).properties(
    width=800,
    height=400
).interactive()

st.altair_chart(chart, use_container_width=True)