import logging
import sys
from pathlib import Path

import streamlit as st
from streamlit.web import cli as stcli

# Importing views registers @st.cache_data before a runtime exists; the warning is harmless.
logging.getLogger("streamlit.runtime.caching.cache_data_api").setLevel(logging.ERROR)

from share_gyan import data  # noqa: E402
from share_gyan import theme as t  # noqa: E402
from share_gyan.views import corporate, dashboard, ipo, market, meroshare_page, news, results, stock, tools  # noqa: E402


def main():
    st.set_page_config(page_title="Share Gyan · NEPSE market tracker", page_icon=str(Path(__file__).parent / "assets" / "logo.png"), layout="wide")
    t.init_mode()
    t.inject_css()

    pages = [
        st.Page(dashboard.render, title="Dashboard", icon=":material/space_dashboard:", default=True),
        st.Page(market.render, title="Market Trends", icon=":material/monitoring:", url_path="market"),
        st.Page(stock.render, title="Stock Analysis", icon=":material/query_stats:", url_path="stock"),
        st.Page(ipo.render, title="IPO Center", icon=":material/rocket_launch:", url_path="ipo"),
        st.Page(results.render, title="IPO Results", icon=":material/fact_check:", url_path="ipo-results"),
        st.Page(meroshare_page.render, title="MeroShare", icon=":material/account_balance_wallet:", url_path="meroshare"),
        st.Page(news.render, title="News", icon=":material/newspaper:", url_path="news"),
        st.Page(corporate.render, title="Corporate Actions", icon=":material/event_note:", url_path="corporate"),
        st.Page(tools.render, title="Tools", icon=":material/calculate:", url_path="tools"),
    ]
    nav = st.navigation(pages, position="top")
    t.header("NEPSE market tracker", data.market_status())
    nav.run()


def run():
    # Entry point for the `app` console script: launches this file via `streamlit run`.
    sys.argv = ["streamlit", "run", str(Path(__file__).resolve())]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
