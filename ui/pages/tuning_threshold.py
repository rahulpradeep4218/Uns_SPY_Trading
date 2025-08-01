import streamlit as st
import pandas as pd
import optuna
from datetime import datetime
from sqlalchemy.orm import Session
from trading_functions.db.session import SessionLocal
from trading_functions.db.models import PriceData, TradeRecord
from trading_functions.inference.inf_functions import calculate_fields


# --- Helper function to calculate total profit ---
def calculate_total_profit(session_id: int, sell_or_buy_threshold: float, risk_threshold: float,
                           start_date: datetime = None, end_date: datetime = None) -> float:
    db: Session = SessionLocal()
    query = db.query(TradeRecord).filter(TradeRecord.session_id == session_id)

    if start_date:
        query = query.filter(TradeRecord.trade_time >= start_date)
    if end_date:
        query = query.filter(TradeRecord.trade_time <= end_date)

    trades = query.all()
    total_profit = 0.0

    for trade in trades:
        price = db.query(PriceData).filter(
            PriceData.symbol == trade.symbol,
            PriceData.time == trade.trade_time
        ).first()

        if not price:
            continue

        calc_fields = calculate_fields(trade, price, sell_or_buy_threshold, risk_threshold)
        if not calc_fields:
            continue
        if calc_fields.get('signal') != 0:
            total_profit += trade.profit

    db.close()
    return total_profit


# --- Objective function for Optuna ---
def create_objective(session_id, start_date, end_date,
                     sb_start, sb_end, sb_step,
                     r_start, r_end, r_step,
                     log_list):

    def objective(trial):
        # Suggest values from the given ranges
        sell_buy_threshold = trial.suggest_float("sell_buy_threshold", sb_start, sb_end, step=sb_step)
        risk_threshold = trial.suggest_float("risk_threshold", r_start, r_end, step=r_step)

        total_profit = calculate_total_profit(session_id, sell_buy_threshold, risk_threshold,
                                              start_date, end_date)

        # Add trial info to log
        log_list.append(
            f"Trial {trial.number} → Sell/Buy={sell_buy_threshold:.2f}, Risk={risk_threshold:.2f}, "
            f"Profit={total_profit:.2f}"
        )

        return total_profit

    return objective


# --- Streamlit UI ---
st.title("🎯 Trade Parameter Tuning with Trial Logs")

# ✅ Session input
session_id = st.number_input("Enter Session ID:", min_value=0, step=1)

# ✅ Date filters
start_date = st.date_input("Start Date (optional)", value=None)
end_date = st.date_input("End Date (optional)", value=None)

st.markdown("---")
st.subheader("⚙️ Sell/Buy Threshold Range")
sb_start = st.number_input("Sell/Buy Threshold Start", value=0.5, step=0.1, format="%.2f")
sb_end = st.number_input("Sell/Buy Threshold End", value=3.0, step=0.1, format="%.2f")
sb_step = st.number_input("Sell/Buy Threshold Step", value=0.1, step=0.1, format="%.2f")

st.markdown("---")
st.subheader("⚙️ Risk Threshold Range")
r_start = st.number_input("Risk Threshold Start", value=0.5, step=0.1, format="%.2f")
r_end = st.number_input("Risk Threshold End", value=5.0, step=0.1, format="%.2f")
r_step = st.number_input("Risk Threshold Step", value=0.1, step=0.1, format="%.2f")

st.markdown("---")
n_trials = st.slider("Number of tuning trials", min_value=5, max_value=1000, value=20)

# ✅ Placeholder for logs
log_box = st.container()
log_text_placeholder = log_box.empty()

if st.button("🚀 Run Parameter Tuning"):
    if session_id < 0:
        st.error("❌ Please enter a valid session ID.")
    else:
        st.info("🔍 Running Optuna tuning... Please wait.")

        # Convert dates to datetime
        start_dt = datetime.combine(start_date, datetime.min.time()) if start_date else None
        end_dt = datetime.combine(end_date, datetime.max.time()) if end_date else None

        # ✅ Log list to store trial logs
        log_list = []

        # ✅ Create Optuna study
        study = optuna.create_study(direction="maximize")

        # ✅ Optimize with real-time logging
        objective = create_objective(session_id, start_dt, end_dt,
                                     sb_start, sb_end, sb_step,
                                     r_start, r_end, r_step,
                                     log_list)

        for _ in range(n_trials):
            study.optimize(objective, n_trials=1)

            # Display logs in a scrollable box
            log_html = """
            <div style='height:300px; overflow-y:scroll; padding:10px;
                        border:1px solid #ccc;
                        background-color:#1e1e1e;
                        color:#ffffff;
                        font-family:monospace;'>
            """
            for line in log_list:
                log_html += f"{line}<br>"
            log_html += "</div>"

            log_text_placeholder.markdown(log_html, unsafe_allow_html=True)

        best_params = study.best_params
        best_profit = study.best_value

        st.success("✅ Tuning Completed!")
        st.subheader("📈 Best Parameters")
        st.write(f"**Optimum Sell/Buy Threshold:** {best_params['sell_buy_threshold']:.2f}")
        st.write(f"**Optimum Risk Threshold:** {best_params['risk_threshold']:.2f}")
        st.write(f"💰 **Maximum Profit Achieved:** {best_profit:.2f}")
