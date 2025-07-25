# streamlit_schwab_data_loader.py

import os
import streamlit as st
import requests
from datetime import datetime

st.set_page_config(page_title="Sync Schwab Data", layout="centered")

st.title("📈 Sync Schwab Realtime Data")

### SECTION 1: Realtime Sync from Schwab API ###
st.subheader("🔄 Sync Realtime Price Data from Schwab")

symbol_realtime = st.text_input("Symbol (Realtime)", value="SPY")

use_period = st.checkbox("📆 Use Period Instead of Dates", value=False)
if use_period:
    period = st.number_input("Period (in days)", min_value=1, value=1)
else:
    period = 1
    start_time = st.text_input("Start Time (ISO format)", value="2020-01-01T00:00:00")
    end_time = st.text_input("End Time (ISO format)", value=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))

if st.button("📡 Sync Realtime Data"):
    try:
        with st.spinner("Syncing data from Schwab..."):
            backend_host = os.getenv("BACKEND_HOST", "http://localhost:8000")
            realtime_url = "/api/schwab/sync-realtime"
            complete_url = f"{backend_host}{realtime_url}"
            print(f"Sending request to: {complete_url} with symbol={symbol_realtime} and period={period}")
            response = requests.post(
                complete_url,
                params={
                    "symbol": symbol_realtime, 
                    "period": period,
                    "use_period": use_period,
                    "start_time": start_time if not use_period else None
                    }
            )
            if response.status_code == 200:
                st.success(response.json().get("message", "Data synced successfully!"))
            else:
                st.error(f"Error: {response.status_code} - {response.text}")
    except Exception as e:
        st.error(f"Exception: {e}")


### SECTION 2: Add from Predefined Excel File ###
st.subheader("📁 Add Data from Excel on Server")

symbol_excel = st.text_input("Symbol (Excel)", value="SPY")
start_time = st.text_input("Start Time (ISO format)", value="2023-01-01T00:00:00")
end_time = st.text_input("End Time (ISO format)", value="2023-01-31T23:59:59")

if st.button("📥 Add from Excel"):
    try:
        backend_host = os.getenv("BACKEND_HOST", "http://localhost:8000")
        excel_url = f"/api/price_data/{symbol_excel}/add_from_excel"
        with st.spinner("Adding data from Excel..."):
            response = requests.post(
                f"{backend_host}{excel_url}",
                data={
                    "start_time": start_time,
                    "end_time": end_time
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            if response.status_code == 200:
                st.success(response.json().get("message", "Data added from Excel!"))
            else:
                st.error(f"Error: {response.status_code} - {response.text}")
    except Exception as e:
        st.error(f"Exception: {e}")
