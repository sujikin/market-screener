import streamlit as st
from screener import run_screener

st.set_page_config(page_title="Market Screener", layout="wide")

st.title("📈 Indian Market Screener")

strategy = st.selectbox("Select Strategy", ["contra", "reverse"])
universe = st.selectbox("Select Universe", ["nifty50", "niftynext50", "custom"])

custom_tickers = ""
if universe == "custom":
    custom_tickers = st.text_input(
        "Enter tickers (comma separated, without .NS)",
        "RELIANCE,TCS,INFY"
    )

if st.button("Run Screener"):
    with st.spinner("Fetching market data..."):
        df = run_screener(strategy, universe, custom_tickers)

    st.success("Done!")

    st.dataframe(df, use_container_width=True)

    st.download_button(
        "Download CSV",
        df.to_csv(index=False),
        file_name="screener_output.csv",
        mime="text/csv"
    )