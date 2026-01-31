import streamlit as st
from screener import run_screener

st.set_page_config(page_title="Market Screener", layout="wide")

# Initialize session state
if "show_help" not in st.session_state:
    st.session_state.show_help = False

# Help page
if st.session_state.show_help:
    col1, col2 = st.columns([0.95, 0.05])
    
    with col2:
        if st.button("✕", key="close_help"):
            st.session_state.show_help = False
            st.rerun()
    
    # Read and display README
    try:
        with open("README.md", "r", encoding="utf-8") as f:
            readme_content = f.read()
        st.markdown(readme_content)
        
        # Close button at bottom
        st.divider()
        col1, col2, col3 = st.columns([0.4, 0.2, 0.4])
        with col2:
            if st.button("✕ Close", key="close_help_bottom", use_container_width=True):
                st.session_state.show_help = False
                st.rerun()
    except FileNotFoundError:
        st.error("README.md not found!")
else:
    # Main page
    col1, col2 = st.columns([0.95, 0.05])
    
    with col1:
        st.title("📈 Indian Market Screener")
    
    with col2:
        if st.button("❓", key="help_btn", help="Read Help"):
            st.session_state.show_help = True
            st.rerun()

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