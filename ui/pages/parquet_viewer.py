import streamlit as st
import duckdb

st.title("Parquet Viewer")
query = st.text_area("Enter your SQL query here", "SELECT * FROM 'Parquet/trading_data_with_features_auc1min.parquet' LIMIT 10")

if st.button("Run Query"):
    try:
        df = duckdb.query(query).to_df()
        st.success(f"Query executed, {len(df)} rows returned")
        st.dataframe(df)
    except Exception as e:
        st.error(f"Error executing query: {e}")
        st.text("Please check your SQL syntax and try again.")