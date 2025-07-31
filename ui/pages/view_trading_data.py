import streamlit as st
import pandas as pd
from trading_functions.db.session import SessionLocal
from trading_functions.db.models import PriceData, TradeRecord
from sqlalchemy.orm import Session



def calculate_fields(trade, price, sell_or_buy_threshold, risk_threshold):
    """Calculates buy_diff, sell_diff, risks, ratios, and signals for one trade record."""
    current_close = price.close if price else None

    if current_close is None:
        return None  # Skip if no price data is found

    buy_take = trade.buy_take_profit or 0
    sell_take = trade.sell_take_profit or 0
    buy_stop = trade.buy_stop_loss or 0
    sell_stop = trade.sell_stop_loss or 0

    # --- Base calculations ---
    buy_diff = buy_take - current_close
    sell_diff = current_close - sell_take
    buy_risk = current_close - buy_stop
    sell_risk = sell_stop - current_close

    # --- Ratios ---
    buy_risk_ratio = buy_risk / buy_diff if buy_diff != 0 else 0
    sell_risk_ratio = sell_risk / sell_diff if sell_diff != 0 else 0

    # --- Sell/Buy Ratio ---
    if buy_diff < 0:
        sell_buy_ratio = (abs(buy_diff) + 1) * sell_diff
    else:
        sell_buy_ratio = sell_diff / (buy_diff + 1) if buy_diff != 0 else 0

    # --- Buy/Sell Ratio ---
    if sell_diff < 0:
        buy_sell_ratio = (abs(sell_diff) + 1) * buy_diff
    else:
        buy_sell_ratio = buy_diff / (sell_diff + 1) if sell_diff != 0 else 0

    # --- Signals ---
    buy_signal = buy_sell_ratio > sell_or_buy_threshold and buy_sell_ratio > sell_buy_ratio and buy_risk_ratio < risk_threshold
    sell_signal = sell_buy_ratio > sell_or_buy_threshold and sell_buy_ratio > buy_sell_ratio and sell_risk_ratio < risk_threshold
    signal = 1 if buy_signal else -1 if sell_signal else 0

    return {
        "current_close": current_close,
        "buy_diff": buy_diff,
        "sell_diff": sell_diff,
        "buy_risk": buy_risk,
        "sell_risk": sell_risk,
        "buy_risk_ratio": buy_risk_ratio,
        "sell_risk_ratio": sell_risk_ratio,
        "buy_sell_ratio": buy_sell_ratio,
        "sell_buy_ratio": sell_buy_ratio,
        "buy_signal": buy_signal,
        "sell_signal": sell_signal,
        "signal": signal
    }


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
