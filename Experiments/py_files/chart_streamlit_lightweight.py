from turtle import width

from torch import layout
import streamlit as st
import pandas as pd
import numpy as np
from lightweight_charts.widgets import StreamlitChart
from datetime import datetime, timezone


chart_width = 1200
chart_height = 600



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


st.set_page_config(layout="wide")
st.title("📈 Lightweight Charts Example 3")

bars = st.sidebar.number_input("Number of Bars", min_value=20, max_value=500, value=100, step=10)
interval = st.sidebar.selectbox("Interval (min)", [1, 5, 10, 15, 30], index=1)
hor_line_val = st.sidebar.number_input("Horizontal Line Value", min_value=0.0, value=100.0, step=1.0)
add_hor_line = st.sidebar.button("Add Horizontal Line")
if st.sidebar.button("Clear Horizontal Lines"):
    st.session_state.horizontal_lines.clear()
    log("Cleared all horizontal lines")
if add_hor_line:
    st.session_state.chart_state['chart'].horizontal_line(hor_line_val, color="blue")
    #log(f"Added horizontal line at {hor_line_val}")

if 'chart_state' not in st.session_state:
    st.session_state.chart_state = {
        "horizontal_lines": [],
        "logs": [],
        "log_container": st.empty(),
        "container": st.empty(),
        "chart": None,
        "df": None,
        "init": False
    }


#Initialize or regenerate the chart
if st.session_state.chart_state['chart'] is None:
    st.session_state.chart_state['df'] = make_random_candles(bars, interval)
    st.session_state.chart_state['chart'] = StreamlitChart(
        width=chart_width,
        height=chart_height,
    )
    st.session_state.chart_state['chart'].set(st.session_state.chart_state['df'])
    with st.session_state.chart_state['container']:
        st.session_state.chart_state['chart'].load()



# st.markdown(
#     """
#     <style>
#         .stContainer iframe {
#             width: 100%;
#         }
#     </style>
#     """,
#     unsafe_allow_html=True
# )
