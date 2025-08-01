import streamlit as st
import pandas as pd
from trading_functions.db.session import SessionLocal
from trading_functions.db.models import PriceData, TradeRecord
from trading_functions.inference.inf_functions import calculate_fields
from sqlalchemy.orm import Session


def query_trades(session_id: int, sell_or_buy_threshold: float, risk_threshold: float, filter_query: str = None):
    """Queries trades for a given session ID and applies optional > / < filters."""
    
    db: Session = SessionLocal()

    trades = db.query(TradeRecord).filter(TradeRecord.session_id == session_id).order_by(TradeRecord.trade_time.desc()).all()

    results = []
    for trade in trades:
        price = db.query(PriceData).filter(
            PriceData.symbol == trade.symbol,
            PriceData.time == trade.trade_time
        ).first()
        db.close()

        calc_fields = calculate_fields(trade, price, sell_or_buy_threshold, risk_threshold)
        if not calc_fields:
            continue

        trade_dict = {
            "symbol": trade.symbol,
            "trade_time": trade.trade_time,
            "status": trade.status,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "profit": trade.profit,
            **calc_fields
        }
        results.append(trade_dict)

    db.close()
    df = pd.DataFrame(results)

    # ✅ Optional filter logic for > / < queries
    if filter_query:
        try:
            df = df.query(filter_query)
        except Exception as e:
            st.error(f"❌ Invalid filter query: {e}")

    return df



# ✅ --- Streamlit UI ---
st.title("📊 Trade Records Viewer")

# ✅ Inputs
session_id = st.number_input("Enter Session ID:", min_value=0, step=1)

sell_or_buy_threshold = st.number_input("Sell/Buy Threshold", value=1.2, step=0.1, format="%.2f")
risk_threshold = st.number_input("Risk Threshold", value=2.0, step=0.1, format="%.2f")

filter_query = st.text_input("Optional Filter (e.g., buy_diff > 5 & sell_risk < 2):")

if st.button("Load Trades"):
    df = query_trades(session_id, sell_or_buy_threshold, risk_threshold, filter_query)

    if not df.empty:
        st.success(f"✅ Loaded {len(df)} trades for session {session_id}")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("⚠️ No trades found for this session.")
