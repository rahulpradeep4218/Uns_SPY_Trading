import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import time
import random
from trading_functions.db.models import SchwabOrders, RealtimeData, PriceData
from trading_functions.db.session import SessionLocal
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from streamlit_autorefresh import st_autorefresh

# ----------------------
# DB FUNCTIONS
# ----------------------

st_autorefresh(interval=5000, key="refresh_orders")

def get_details_from_option_symbol(option_symbol: str):
    """Extracts details from the option symbol."""
    parts = option_symbol.split("_")
    if len(parts) < 3:
        return None, None, None, None

    symbol = parts[0]
    expiration_date = parts[1]
    strike_price = parts[2]
    option_type = parts[3] if len(parts) > 3 else None

    return symbol, expiration_date, strike_price, option_type

def parse_option_symbol(symbol: str) -> dict:
    """
    Parse Schwab-style option symbol into components.
    
    Example:
        "SPY   250807C00631000" ->
        {
            "underlying": "SPY",
            "expiration_date": "2025-08-07",
            "type": "CALL",
            "strike_price": 631.0
        }
    """
    # Trim and split underlying from the rest
    underlying = symbol[:6].strip()  # First 6 chars contain underlying padded with spaces
    date_part = symbol[6:12]         # YYMMDD
    type_part = symbol[12]           # C or P
    strike_part = symbol[13:]        # Strike price as 8 digits

    # Convert expiration date
    year = 2000 + int(date_part[0:2])
    month = int(date_part[2:4])
    day = int(date_part[4:6])
    expiration_date = f"{year:04d}-{month:02d}-{day:02d}"

    # Type mapping
    opt_type = "CALL" if type_part.upper() == "C" else "PUT"

    # Strike price conversion
    strike_price = int(int(strike_part) / 1000)  # because 00631000 → 631.000

    return {
        "underlying": underlying,
        "expiration_date": expiration_date,
        "type": opt_type,
        "strike_price": strike_price
    }




def get_prices_from_db(order: pd.Series, db: Session) -> float:
    symbol_details = parse_option_symbol(order['symbol'])
    symbol = symbol_details["underlying"]
    order_open_time = order['open_time']

    max_hist_price = (
        db.query(func.max(PriceData.high))
        .filter(
            and_(
                PriceData.symbol == symbol,
                PriceData.time >= order_open_time
            )
        )
        .scalar()
    )
    min_hist_price = (
        db.query(func.min(PriceData.low))
        .filter(
            and_(
                PriceData.symbol == symbol,
                PriceData.time >= order_open_time
            )
        )
        .scalar()
    )
    
    realtime_record = db.query(RealtimeData).first()
    max_current = realtime_record.high
    min_current = realtime_record.low
    if max_hist_price is None:
        max_price = max_current
    else:
        max_price = max(max_hist_price, max_current)
    
    if min_hist_price is None:
        min_price = min_current
    else:
        min_price = min(min_hist_price, min_current)
    current_price = realtime_record.price
    return {
        "max_price": max_price,
        "min_price": min_price,
        "current_price": current_price
    }

def get_orders_from_db(db: Session):
    """Fetch orders from schwab_orders table."""  
    schwab_orders = db.query(SchwabOrders).order_by(SchwabOrders.open_time.desc()).all()
    df = pd.DataFrame([order.__dict__ for order in schwab_orders])
    df = df.drop("_sa_instance_state", axis=1, errors="ignore")
    return df


def get_latest_price(order):
    """Get latest price for the selected order's symbol (stub for now)."""
    # Replace with your API call to fetch option price
    return round(random.uniform(0.5, 2.5), 2)

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
st.set_page_config(layout="wide")
st.title("Schwab Orders Tracker")

col1, col2 = st.columns([1, 3])  # Table on left, details/graph on right

# Initiate DB Session
db: Session = SessionLocal()

# ----------------------
# LEFT COLUMN: Orders Table
# ----------------------
with col1:
    orders_df = get_orders_from_db(db)

    if orders_df.empty:
        st.warning("No orders found in database.")
    else:
        st.subheader("Orders List")

        selected_id = st.radio(
            "Select Order ID",
            orders_df["open_order_id"],
            index=0 if st.session_state.selected_order_id is None else
                  orders_df.index[orders_df["open_order_id"] == st.session_state.selected_order_id][0]
        )

        if selected_id != st.session_state.selected_order_id:
            st.session_state.selected_order_id = selected_id
            st.session_state.max_price = None
            st.session_state.min_price = None

# ----------------------
# RIGHT COLUMN: Order Details + Graph
# ----------------------
with col2:
    if st.session_state.selected_order_id is not None:
        order = orders_df[orders_df["open_order_id"] == st.session_state.selected_order_id].iloc[0]

        st.subheader(f"Order Details — {order['open_time']}")
        st.json(order.to_dict())

        if not order['closed']:
        # Simulate getting prices
            prices = get_prices_from_db(order=order, db=db)
            current_price = prices["current_price"]

            take_profit = order['take_profit']
            stop_loss = order['stop_loss']

            # Track min/max

            st.session_state.max_price = prices["max_price"]
            st.session_state.min_price = prices["min_price"]

            # Plotly chart
            fig = go.Figure()

            # Scatter point for current price
            fig.add_trace(go.Scatter(
                x=[time.strftime("%H:%M:%S")],
                y=[current_price],
                mode="markers+text",
                text=[f"${current_price}"],
                textposition="top center",
                name="Current Price"
            ))

            # Horizontal lines
            fig.add_hline(y=take_profit, line_dash="dash", line_color="green", annotation_text="Take Profit")
            fig.add_hline(y=stop_loss, line_dash="dash", line_color="red", annotation_text="Stop Loss")
            fig.add_hline(y=st.session_state.max_price, line_dash="dot", line_color="blue", annotation_text="Max Price")
            fig.add_hline(y=st.session_state.min_price, line_dash="dot", line_color="orange", annotation_text="Min Price")

            fig.update_layout(
                yaxis_title="Price",
                xaxis_title="Time",
                title="Order Price Tracking",
                height=400
            )

            st.plotly_chart(fig, use_container_width=True)
db.close()

