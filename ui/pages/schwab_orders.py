import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import time
from trading_functions.db.models import SchwabOrders, RealtimeData, PriceData
from trading_functions.db.session import SessionLocal
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from streamlit_autorefresh import st_autorefresh
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Schwab Orders Tracker")

# ----------------------
# AUTO-REFRESH
# ----------------------
st_autorefresh(interval=5000, key="refresh_orders")

# ----------------------
# DB FUNCTIONS
# ----------------------
def parse_option_symbol(symbol: str) -> dict:
    underlying = symbol[:6].strip()
    date_part = symbol[6:12]         # YYMMDD
    type_part = symbol[12]           # C or P
    strike_part = symbol[13:]        # Strike price as 8 digits

    year = 2000 + int(date_part[0:2])
    month = int(date_part[2:4])
    day = int(date_part[4:6])
    expiration_date = f"{year:04d}-{month:02d}-{day:02d}"
    opt_type = "CALL" if type_part.upper() == "C" else "PUT"
    strike_price = int(int(strike_part) / 1000)

    return {
        "underlying": underlying,
        "expiration_date": expiration_date,
        "type": opt_type,
        "strike_price": strike_price
    }

def get_prices_from_db(order: pd.Series, db: Session):
    symbol_details = parse_option_symbol(order['symbol'])
    symbol = symbol_details["underlying"]
    order_open_time = order['open_time']
    if isinstance(order_open_time, str):
        order_open_time = datetime.fromisoformat(order_open_time)
    
    if order_open_time.tzinfo is None:
        order_open_time = order_open_time.replace(tzinfo=timezone.utc)

    order_open_time_est = order_open_time.astimezone(ZoneInfo("America/New_York"))
    order_open_time_est_str = order_open_time_est.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"Fetching prices for {symbol} after {order_open_time_est}")

    max_hist_price = (
        db.query(func.max(PriceData.high))
        .filter(PriceData.symbol == symbol, PriceData.time >= order_open_time_est_str)
        .scalar()
    )
    min_hist_price = (
        db.query(func.min(PriceData.low))
        .filter(PriceData.symbol == symbol, PriceData.time >= order_open_time_est_str)
        .scalar()
    )

    realtime_record = db.query(RealtimeData).first()
    if not realtime_record:
        return {"max_price": None, "min_price": None, "current_price": None}
    logger.info(f"Realtime data for {symbol}: {realtime_record}")
    if max_hist_price is None:
        logger.warning(f"No historical price data found for {symbol} after {order_open_time}. Using real-time data only.")
        max_price = realtime_record.high
    else:
        logger.info(f"Historical max price for {symbol} after {order_open_time}: {max_hist_price}")
        max_price = max(max_hist_price, realtime_record.high)
    if min_hist_price is None:
        min_price = realtime_record.low
    else:
        min_price = min(min_hist_price, realtime_record.low)

    return {
        "max_price": max_price,
        "min_price": min_price,
        "current_price": realtime_record.price
    }

def get_orders_from_db(db: Session):
    orders = db.query(SchwabOrders).order_by(SchwabOrders.open_time.desc()).all()
    df = pd.DataFrame([o.__dict__ for o in orders])
    return df.drop("_sa_instance_state", axis=1, errors="ignore")

# ----------------------
# SESSION STATE INIT
# ----------------------
if "selected_order_id" not in st.session_state:
    st.session_state.selected_order_id = None
if "max_price" not in st.session_state:
    st.session_state.max_price = None
if "min_price" not in st.session_state:
    st.session_state.min_price = None

# ----------------------
# PAGE LAYOUT
# ----------------------
#st.set_page_config(layout="wide")
st.title("Schwab Orders Tracker")

col1, col2 = st.columns([1, 3])
db: Session = SessionLocal()

# ----------------------
# LEFT COLUMN: Orders Table
# ----------------------
with col1:
    orders_df = get_orders_from_db(db)
    orders_df['open_order_id'] = orders_df['open_order_id'].astype(int)

    if orders_df.empty:
        st.warning("No orders found in database.")
    else:
        st.subheader("Orders List")

        available_ids = orders_df["open_order_id"].astype(int).tolist()

        # Ensure selection is valid
        if st.session_state.selected_order_id not in available_ids:
            st.session_state.selected_order_id = available_ids[0]

        default_index = available_ids.index(st.session_state.selected_order_id)

        selected_id = st.radio(
            "Select Order ID",
            available_ids,
            index=default_index
        )

        if selected_id != st.session_state.selected_order_id:
            st.session_state.selected_order_id = selected_id
            st.session_state.max_price = None
            st.session_state.min_price = None

# ----------------------
# RIGHT COLUMN: Order Details + Graph
# ----------------------
with col2:
    if st.session_state.selected_order_id is not None and not orders_df.empty:
        matching_orders = orders_df[orders_df["open_order_id"] == st.session_state.selected_order_id]

        if not matching_orders.empty:
            order = matching_orders.iloc[0]
            st.subheader(f"Order Details — {order['open_time']}")
            st.json(order.to_dict())

            if not order['closed']:
                prices = get_prices_from_db(order=order, db=db)
                if prices["current_price"] is not None:
                    st.session_state.max_price = prices["max_price"]
                    st.session_state.min_price = prices["min_price"]

                    fig = go.Figure()

                    fig.add_trace(go.Scatter(
                        x=[time.strftime("%H:%M:%S")],
                        y=[prices["current_price"]],
                        mode="markers+text",
                        text=[f"${prices['current_price']}"],
                        textposition="top center",
                        name="Current Price"
                    ))

                    fig.add_hline(y=order['take_profit'], line_dash="dash", line_color="green", annotation_text="Take Profit")
                    fig.add_hline(y=order['stop_loss'], line_dash="dash", line_color="red", annotation_text="Stop Loss")
                    fig.add_hline(y=st.session_state.max_price, line_dash="dot", line_color="blue", annotation_text="Max Price")
                    fig.add_hline(y=st.session_state.min_price, line_dash="dot", line_color="orange", annotation_text="Min Price")

                    fig.update_layout(yaxis_title="Price", xaxis_title="Time", title="Order Price Tracking", height=400)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Price data unavailable.")
        else:
            st.warning("Selected order not found. It may have been closed.")

db.close()
