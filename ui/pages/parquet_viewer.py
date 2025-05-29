import streamlit as st
import duckdb

st.title("Parquet Viewer")
params = st.query_params
parq_path = params.get("file", None)
if parq_path:
    #parq_path = parq_path[0]

    try:
        df = duckdb.query(f"SELECT * FROM '{parq_path}'").fetchdf()
        st.dataframe(df)
    except Exception as e:
        st.error(f"Error executing query: {e}")
        st.text("Please check your SQL syntax and try again.")
else:
    st.error("No file path provided in the query parameters.")
    st.text("Please provide a valid file path to a Parquet file.")