"""Shared pieces used by more than one page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from share_gyan import charts, data
from share_gyan import theme as t

RANGES = {"1M": 21, "3M": 63, "6M": 126, "1Y": 260}


def unavailable(what: str) -> None:
    t.render(t.empty_state(f"{what} is unavailable", "The source did not respond. Try the refresh button in a moment."))


def trend_chart(key: str, height: int = 340) -> None:
    hist = data.history()
    if hist.empty:
        unavailable("NEPSE history")
        return
    choice = st.radio("Range", list(RANGES), index=2, horizontal=True, label_visibility="collapsed", key=key)
    t.show_chart(charts.nepse_area(hist.tail(RANGES[choice]), height))


def all_issues() -> pd.DataFrame:
    frames = [df.assign(Kind=kind) for kind, df in data.issues().items() if not df.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


IPO_KINDS = ("IPO", "IPO (Local)")
_STATUS_ORDER = {"Open": 0, "Upcoming": 1, "Coming soon": 2}


def live_issues() -> pd.DataFrame:
    """Open, upcoming and undated issues, IPOs first."""
    df = all_issues()
    if df.empty:
        return df
    df = df[df["Status"].isin(_STATUS_ORDER)].copy()
    df["_s"] = df["Status"].map(_STATUS_ORDER)
    df["_k"] = (~df["Kind"].isin(IPO_KINDS)).astype(int)
    return df.sort_values(["_k", "_s", "Opens"]).drop(columns=["_s", "_k"])


def issue_card(row: pd.Series) -> str:
    units = f'{row["Units"]:,.0f}' if pd.notna(row["Units"]) else "—"
    opens = row["Opens"].strftime("%d %b %Y") if pd.notna(row["Opens"]) else "To be announced"
    closes = row["Closes"].strftime("%d %b %Y") if pd.notna(row["Closes"]) else "To be announced"
    return t.ipo_card(
        row["Symbol"],
        row["Company"],
        row["Status"],
        [("Units", units), ("Opens", opens), ("Closes", closes), ("Manager", row["Manager"] or "—")],
        kind=row["Kind"],
    )
