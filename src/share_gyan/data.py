"""Cached, failure-tolerant access to the scraped market data."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from time import monotonic
from typing import TypeVar

import pandas as pd
import streamlit as st

from share_gyan import analysis, scraper

T = TypeVar("T")
TTL = 300  # seconds

SOURCES = {
    "ShareSansar": "https://www.sharesansar.com/",
    "Merolagani": "https://eng.merolagani.com/Index.aspx",
    "Share Gyan Nepal": "https://www.sharegyannepal.com/",
}

LEARN_LINKS = [
    ("Beginner's guide, part 1", "Basics to start investing in the share market",
     "https://www.sharesansar.com/newsdetail/beginners-guide-part-1-basics-to-start-your-investment-in-share-market"),
    ("Beginner's guide, part 2", "Opening accounts, ASBA and applying for IPOs",
     "https://www.sharesansar.com/newsdetail/beginners-guide-part-2-basics-to-start-your-investment-in-share-market"),
    ("Beginner's guide, part 3", "Reading prices, orders and market depth",
     "https://www.sharesansar.com/newsdetail/beginners-guide-part-3-basics-to-start-your-investment-in-share-market"),
    ("Share Gyan Nepal on YouTube", "Mutual funds, hydropower and market policy explainers",
     "https://www.youtube.com/@ShareGyanNepal"),
]

PORTALS = [
    ("CDSC IPO result", "https://iporesult.cdsc.com.np/"),
    ("Meroshare", "https://meroshare.cdsc.com.np/"),
    ("SEBON", "https://www.sebon.gov.np/"),
    ("NEPSE", "https://www.nepalstock.com/"),
]


def _guard(label: str, fn: Callable[[], T], default: T) -> T:
    try:
        return fn()
    except Exception as exc:  # network or markup changes must not take the app down
        st.toast(f"Could not load {label} ({type(exc).__name__})", icon=":material/cloud_off:")
        return default


def _try(fn: Callable[[], T], default: T) -> T:
    try:
        return fn()
    except Exception:
        return default


# --------------------------------------------------------------------------- #
# Companies
# --------------------------------------------------------------------------- #


@st.cache_data(ttl=86400, show_spinner=False)
def _companies() -> pd.DataFrame:
    return scraper.sharesansar_companies()


def companies() -> pd.DataFrame:
    return _guard("company names", _companies, pd.DataFrame())


def with_names(df: pd.DataFrame, symbol: str = "Symbol") -> pd.DataFrame:
    """Add full company name, sector and page link keyed on the symbol column."""
    if df is None or df.empty or symbol not in df:
        return df
    out = df.copy()
    directory = companies()
    known = directory.set_index("Symbol") if not directory.empty else pd.DataFrame(columns=["Company", "Sector", "Url"])
    if "Company" not in out:
        out["Company"] = out[symbol].map(known["Company"]).fillna("")
    if "Sector" not in out:
        out["Sector"] = out[symbol].map(known["Sector"]).fillna("")
    if "Url" not in out:
        out["Url"] = out[symbol].map(known["Url"])
    if directory.empty:  # directory unavailable: fall back to ShareSansar's URL pattern
        out["Url"] = out["Url"].fillna(out[symbol].map(scraper.company_url))
    return out


# --------------------------------------------------------------------------- #
# Market
# --------------------------------------------------------------------------- #


@st.cache_data(ttl=TTL, show_spinner=False)
def _market() -> dict:
    snapshot = scraper.sharesansar_market()
    snapshot["summary"] = _try(scraper.merolagani_summary, {})
    snapshot["fetched_at"] = datetime.now()
    return snapshot


def market() -> dict | None:
    return _guard("market summary", _market, None)


@st.cache_data(ttl=TTL, show_spinner=False)
def _board() -> dict:
    as_of, df = scraper.sharesansar_board()
    span = (df["52W High"] - df["52W Low"]).where(lambda s: s > 0)
    df["52W Position"] = ((df["LTP"] - df["52W Low"]) / span * 100).clip(0, 100).round(1)
    return {"as_of": as_of, "df": df}


def board() -> dict | None:
    b = _guard("price board", _board, None)
    return None if b is None else {"as_of": b["as_of"], "df": with_names(b["df"])}


@st.cache_data(ttl=TTL, show_spinner=False)
def _sectors() -> pd.DataFrame:
    return scraper.sharesansar_sectors()


def sectors() -> pd.DataFrame:
    return _guard("sector indices", _sectors, pd.DataFrame())


@st.cache_data(ttl=TTL, show_spinner=False)
def _history() -> pd.DataFrame:
    return scraper.merolagani_history()


def history() -> pd.DataFrame:
    return _guard("NEPSE history", _history, pd.DataFrame())


# --------------------------------------------------------------------------- #
# Single scrip
# --------------------------------------------------------------------------- #


@st.cache_data(ttl=TTL, show_spinner=False)
def _stock_history(symbol: str) -> pd.DataFrame:
    return scraper.merolagani_stock_history(symbol)


def stock_history(symbol: str) -> pd.DataFrame:
    return _guard(f"{symbol} price history", lambda: _stock_history(symbol), pd.DataFrame())


@st.cache_data(ttl=TTL, show_spinner=False)
def _traded_history(symbol: str) -> pd.DataFrame:
    return scraper.sharesansar_stock_history(symbol)


def traded_history(symbol: str) -> pd.DataFrame:
    return _guard(f"{symbol} as-traded prices", lambda: _traded_history(symbol), pd.DataFrame())


@st.cache_data(ttl=3600, show_spinner=False)
def _company_info(symbol: str) -> dict:
    return scraper.sharesansar_company_info(symbol)


def company_info(symbol: str) -> dict | None:
    """Basic company details, or None when the symbol is unknown to ShareSansar."""
    return _try(lambda: _company_info(symbol), None)


@st.cache_data(ttl=TTL, show_spinner=False)
def _profile(symbol: str) -> dict:
    return scraper.merolagani_company(symbol)


def profile(symbol: str) -> dict | None:
    return _guard(f"{symbol} fundamentals", lambda: _profile(symbol), None)


@st.cache_data(ttl=TTL, show_spinner=False)
def _peer_ratios(symbols: tuple[str, ...]) -> pd.DataFrame:
    def load(symbol: str) -> dict | None:
        p = _try(lambda: scraper.merolagani_company(symbol), None)
        if p is None:
            return None
        return {"Symbol": symbol, "P/E": p["pe"] or None, "PBV": p["pbv"] or None, "EPS": p["eps"], "Cash %": p["dividend"]}

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = [r for r in pool.map(load, symbols) if r]
    return pd.DataFrame(rows, columns=["Symbol", "P/E", "PBV", "EPS", "Cash %"])


def peers(symbol: str, sector: str, board_df: pd.DataFrame, n: int = 6) -> pd.DataFrame:
    """The most traded scrips of the same sector with their price move and valuation ratios."""
    if not sector or "Sector" not in board_df:
        return pd.DataFrame()
    near = board_df[(board_df["Sector"] == sector) & (board_df["Symbol"] != symbol)].sort_values("Turnover", ascending=False).head(n)
    if near.empty:
        return near
    ratios = _guard("peer ratios", lambda: _peer_ratios(tuple(near["Symbol"])), pd.DataFrame(columns=["Symbol", "P/E", "PBV", "EPS", "Cash %"]))
    return near.merge(ratios, on="Symbol", how="left")


@st.cache_data(ttl=TTL, show_spinner=False)
def _screen(rows: tuple[tuple[str, str, str], ...]) -> pd.DataFrame:
    index = _try(scraper.merolagani_history, pd.DataFrame())

    def load(row: tuple[str, str, str]):
        try:
            return row, scraper.merolagani_stock_history(row[0]), scraper.merolagani_company(row[0])
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        loaded = [x for x in pool.map(load, rows) if x]
    ratios = pd.DataFrame(
        [{"Symbol": r[0], "Sector": r[2], "P/E": p["pe"] or None, "PBV": p["pbv"] or None} for r, _, p in loaded],
        columns=["Symbol", "Sector", "P/E", "PBV"],
    )
    out = []
    for (symbol, company, sector), hist, prof in loaded:
        peer_set = ratios[(ratios["Sector"] == sector) & (ratios["Symbol"] != symbol)] if sector else None
        try:
            v = analysis.evaluate(hist, prof, index, peer_set)
        except Exception:
            continue
        if v is None:
            continue
        p = v.plan
        out.append(
            {
                "Symbol": symbol, "Company": company, "Sector": sector, "Price": v.metrics["price"], "Rating": v.rating, "Score": v.score,
                "EntryLow": p.entry_low, "EntryHigh": p.entry_high, "Stop": p.stop, "Target1": p.target1, "Target2": p.target2,
                "RewardRisk": p.reward_risk, "RSI": v.metrics["rsi"], "Turnover": v.metrics["turnover"],
            }
        )
    return pd.DataFrame(out)


def screen(rows: tuple[tuple[str, str, str], ...]) -> pd.DataFrame:
    """Run the rating model over (symbol, company, sector) rows."""
    return _guard("market scan", lambda: _screen(rows), pd.DataFrame())


def breadth(df: pd.DataFrame) -> tuple[int, int, int]:
    advanced = int((df["Change"] > 0).sum())
    declined = int((df["Change"] < 0).sum())
    return advanced, declined, len(df) - advanced - declined


def top_gainers(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    return df[df["Change"] > 0].sort_values("% Change", ascending=False).head(n)


def top_losers(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    return df[df["Change"] < 0].sort_values("% Change").head(n)


def top_turnover(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    return df.sort_values("Turnover", ascending=False).head(n)


# --------------------------------------------------------------------------- #
# Issues
# --------------------------------------------------------------------------- #


@st.cache_data(ttl=TTL, show_spinner=False)
def _issues() -> dict[str, pd.DataFrame]:
    return scraper.sharesansar_all_issues()


def issues() -> dict[str, pd.DataFrame]:
    return _guard("share issues", _issues, {})


def ipos() -> pd.DataFrame:
    return issues().get("IPO", pd.DataFrame())


@st.cache_data(ttl=TTL, show_spinner=False)
def _upcoming() -> pd.DataFrame:
    return scraper.sharesansar_upcoming()


def upcoming() -> pd.DataFrame:
    return _guard("upcoming issues", _upcoming, pd.DataFrame())


# --------------------------------------------------------------------------- #
# Corporate actions
# --------------------------------------------------------------------------- #


@st.cache_data(ttl=TTL, show_spinner=False)
def _dividends() -> pd.DataFrame:
    return scraper.sharesansar_dividends()


def dividends() -> pd.DataFrame:
    return _guard("dividends", _dividends, pd.DataFrame())


@st.cache_data(ttl=TTL, show_spinner=False)
def _corporate() -> dict[str, pd.DataFrame]:
    return scraper.merolagani_corporate()


def corporate() -> dict[str, pd.DataFrame]:
    return {k: with_names(v) for k, v in _guard("AGM and rights", _corporate, {}).items()}


@st.cache_data(ttl=TTL, show_spinner=False)
def _mergers() -> pd.DataFrame:
    return scraper.sharesansar_mergers()


def mergers() -> pd.DataFrame:
    return _guard("mergers", _mergers, pd.DataFrame())


# --------------------------------------------------------------------------- #
# News
# --------------------------------------------------------------------------- #


@st.cache_data(ttl=TTL * 2, show_spinner=False)
def _news() -> pd.DataFrame:
    return scraper.news()


def news() -> pd.DataFrame:
    return _guard("news", _news, pd.DataFrame())


# --------------------------------------------------------------------------- #
# Company logos
# --------------------------------------------------------------------------- #

_logo_retry_at = 0.0


@st.cache_resource(ttl=86400, show_spinner=False)
def _logos() -> dict[str, str]:
    return scraper.arthakendra_logos()


def logos() -> dict[str, str]:
    """Symbol to logo URL. Failures are silent and not retried for five minutes, since badges are a fine fallback."""
    global _logo_retry_at
    if monotonic() < _logo_retry_at:
        return {}
    try:
        return _logos()
    except Exception:
        _logo_retry_at = monotonic() + 300
        return {}


def refresh() -> None:
    st.cache_data.clear()


# --------------------------------------------------------------------------- #
# Market session
# --------------------------------------------------------------------------- #

NPT = timezone(timedelta(hours=5, minutes=45))  # Nepal has no daylight saving
PRE_OPEN, OPEN, CLOSE = time(10, 30), time(11, 0), time(15, 0)
DEFAULT_TRADING_DAYS = {6, 0, 1, 2, 3}  # Sunday to Thursday


def trading_weekdays(hist: pd.DataFrame) -> set[int]:
    """Weekdays on which the exchange actually traded recently, so a change of schedule is picked up from the data."""
    if hist is None or hist.empty:
        return DEFAULT_TRADING_DAYS
    counts = hist["Date"].tail(60).dt.weekday.value_counts()
    return {int(d) for d, n in counts.items() if n >= 3} or DEFAULT_TRADING_DAYS


def _clock(t: time) -> str:
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def market_session(now: datetime, as_of: str, weekdays: set[int]) -> dict:
    """Whether NEPSE is open at `now` (Nepal time). `as_of` is the latest trading day on the price board, if known."""
    def next_open() -> str:
        for step in range(1, 8):
            day = now + timedelta(days=step)
            if day.weekday() in weekdays:
                return f"Next session {day:%a %d %b}, {_clock(OPEN)}"
        return ""

    clock = now.time()
    if now.weekday() not in weekdays:
        return {"state": "closed", "label": "Market closed", "detail": f"Not a trading day. {next_open()}"}
    if clock < PRE_OPEN:
        return {"state": "closed", "label": "Market closed", "detail": f"Pre-open starts at {_clock(PRE_OPEN)}, trading at {_clock(OPEN)}"}
    if clock < OPEN:
        return {"state": "pre", "label": "Pre-open", "detail": f"Trading starts at {_clock(OPEN)}"}
    if clock < CLOSE:
        # a trading day with no prices on the board half an hour after the open means a holiday
        if as_of and as_of != now.date().isoformat() and clock >= time(11, 30):
            return {"state": "closed", "label": "Market closed", "detail": f"No trading today (holiday). {next_open()}"}
        return {"state": "open", "label": "Market open", "detail": f"Closes at {_clock(CLOSE)}"}
    return {"state": "closed", "label": "Market closed", "detail": f"Closed at {_clock(CLOSE)}. {next_open()}"}


def market_status() -> dict:
    snapshot = _try(_market, None)
    as_of = snapshot["as_of"] if snapshot else ""
    return market_session(datetime.now(NPT), as_of, trading_weekdays(_try(_history, pd.DataFrame())))
