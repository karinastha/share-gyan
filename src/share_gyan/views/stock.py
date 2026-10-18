"""Single-scrip page: price action, technicals, fundamentals and a secondary-market buy/wait/avoid read."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from share_gyan import analysis, charts, data, insights, lwcharts, scraper
from share_gyan import theme as t
from share_gyan.views import common
from share_gyan.views.tools import _buy_cost, _sell_net, breakeven_price

CHART_RANGES = {"1M": 21, "3M": 63, "6M": 126, "1Y": 240, "2Y": 480}
STANCE_TAG = {"Bullish": "open", "Bearish": "bad", "Neutral": "closed", "n/a": "closed"}
MIN_PICK_SCORE, MIN_PICK_RR = 62, 1.3


def _n(value, digits: int = 2, suffix: str = "") -> str:
    return "—" if value is None or pd.isna(value) else f"{value:,.{digits}f}{suffix}"


def _kv_card(title: str, rows: list[tuple[str, str]]) -> str:
    body = "".join(f'<div class="kv"><span>{t.esc(k)}</span><span>{t.esc(v)}</span></div>' for k, v in rows)
    return f'<div class="card"><div class="label" style="margin-bottom:6px">{t.esc(title)}</div>{body}</div>'


def _picker(symbols: list[str], names: dict[str, str]) -> str | None:
    wanted = st.query_params.get("symbol", "").strip().upper()

    def sync() -> None:
        choice = st.session_state.get("stock-symbol")
        if choice:
            st.query_params["symbol"] = choice

    return st.selectbox(
        "Scrip", symbols, index=symbols.index(wanted) if wanted in symbols else None, key="stock-symbol", on_change=sync,
        placeholder="Search a symbol or company, e.g. NABIL", format_func=lambda s: f"{s} · {names.get(s, '')}" if names.get(s) else s,
        label_visibility="collapsed",
    )


def _landing(board_df: pd.DataFrame | None, unknown: str = "") -> None:
    t.render(t.hero("Stock", "analysis", "Pick a scrip to see its price action, fundamentals and whether the secondary market looks like a buy, a wait or an avoid right now."))
    if unknown:
        t.render(t.empty_state(f"{unknown} was not found", "Check the symbol or search for it above."))
    if board_df is not None and not board_df.empty:
        t.render(t.section("Most active today", "click a symbol to open its analysis"))
        t.render(t.mover_table(data.top_turnover(board_df, 15), "turnover"))


# --------------------------------------------------------------------------- #
# Header, snapshot and verdict
# --------------------------------------------------------------------------- #


def _price_now(row: pd.Series | None, hist: pd.DataFrame) -> tuple[float | None, float, float]:
    if row is not None:
        return float(row["LTP"]), float(row["Change"]), float(row["% Change"])
    if len(hist) >= 2:
        last, prev = float(hist["Close"].iloc[-1]), float(hist["Close"].iloc[-2])
        return last, last - prev, (last / prev - 1) * 100
    return None, 0.0, 0.0


def _head(symbol: str, name: str, sector: str, ltp: float | None, change: float, pct: float, as_of: str) -> str:
    sector_tag = t.tag(sector) if sector else ""
    price = (
        f'<div class="px"><div class="big">Rs {t.num(ltp)}</div><div style="margin-top:6px">{t.pill(change, pct)}</div>'
        f'<div class="sub" style="margin-top:4px">{t.esc(as_of)}</div></div>'
        if ltp is not None
        else ""
    )
    return (
        f'<div class="stock-head"><div class="who-id">{t.avatar(symbol, 68)}<div><h1>{t.esc(symbol)}</h1><div class="co">{t.esc(name)}</div>'
        f'<div style="margin-top:8px">{sector_tag}</div></div></div>{price}</div>'
    )


def _snapshot(row: pd.Series | None, prof: dict | None, hist: pd.DataFrame, verdict: analysis.Verdict | None) -> None:
    prof = prof or {}
    cards = []
    if row is not None:
        cards.append(t.stat_card("Day range", f'{row["Low"]:,.1f} – {row["High"]:,.1f}', note=f'Open {row["Open"]:,.1f} · VWAP {row["VWAP"]:,.1f}'))
        ratio = f' · {row["Volume"] / prof["avg_volume_30"]:.1f}x 30-day avg' if prof.get("avg_volume_30") else ""
        cards.append(t.stat_card("Volume", f'{row["Volume"]:,.0f}', note=f'{row["Trades"]:,.0f} trades · Rs {t.nepali_amount(row["Turnover"])}{ratio}'))
    elif not hist.empty:
        last = hist.iloc[-1]
        cards.append(t.stat_card("Day range", f'{last["Low"]:,.1f} – {last["High"]:,.1f}', note=f'Open {last["Open"]:,.1f}'))
        cards.append(t.stat_card("Volume", f'{last["Volume"]:,.0f}', note=f'Session of {last["Date"]:%d %b %Y}'))
    if prof.get("market_cap"):
        cards.append(t.stat_card("Market cap", f'Rs {t.nepali_amount(prof["market_cap"])}', note=f'{prof["listed_shares"]:,.0f} listed shares' if prof.get("listed_shares") else ""))
    lo, hi = prof.get("low_52"), prof.get("high_52")
    if lo and hi and hi > lo and prof.get("price"):
        pos = (prof["price"] - lo) / (hi - lo) * 100
        cards.append(t.stat_card("52-week range", f"{lo:,.1f} – {hi:,.1f}", note=f"Trading at {pos:.0f}% of the range"))
    for col, card in zip(st.columns(max(len(cards), 1)), cards):
        with col:
            t.render(card)


def _who(verdict: analysis.Verdict) -> str:
    """The action for current holders and for new buyers, side by side."""
    holders, buyers = insights.stances(verdict)
    cell = lambda label, s: f'<div><div class="label">{label}</div><b class="{s.tone}">{t.esc(s.action)}</b></div>'  # noqa: E731
    return f'<div class="who">{cell("If you own it", holders)}{cell("If you want to buy", buyers)}</div>'


def _verdict_card(v: analysis.Verdict, warnings: list[str]) -> str:
    notes = "".join(f'<div class="warn">{t.esc(w)}</div>' for w in warnings)
    return (
        '<div class="card verdict"><div class="label">Secondary-market view</div>'
        f'<div class="rating {v.tone}">{t.esc(v.rating)}</div>'
        f'<div class="score">Score {v.score} / 100 from {sum(f.score is not None for f in v.factors)} weighted factors</div>'
        f'<div><div class="meter"><i style="left:{v.score}%"></i></div><div class="meter-scale"><span>Avoid</span><span>Hold</span><span>Buy</span></div></div>'
        f"<p>{t.esc(v.summary)}</p>{_who(v)}{notes}</div>"
    )


def _lvl(label: str, text: str, tone: str = "") -> str:
    return f'<div class="lvl"><span>{t.esc(label)}</span><b class="{tone}">{t.esc(text)}</b></div>'


def _buy_setup(v: analysis.Verdict | None) -> bool:
    return v is not None and v.rating in ("Buy", "Accumulate", "Buy on a dip")


def _plan_card(v: analysis.Verdict) -> str:
    p, m = v.plan, v.metrics
    if not _buy_setup(v):
        rows = [
            _lvl("Support (recent low)", f"Rs {p.support:,.1f}"),
            _lvl("Resistance (recent high)", f"Rs {p.resistance:,.1f}"),
            _lvl("Exit level for holders", f"Close below Rs {p.stop:,.1f}", "down"),
        ]
        if v.tone == "down" and m["sma20"] and m["sma50"]:
            rows.append(_lvl("First signs of recovery", f"Closes above Rs {m['sma20']:,.1f}, then Rs {m['sma50']:,.1f}"))
        else:
            rows.append(_lvl("Buying gets interesting", f"A close above Rs {p.resistance:,.1f} on strong volume"))
        return (
            f'<div class="card"><div class="label" style="margin-bottom:6px">Levels to watch</div>{"".join(rows)}'
            f'<div class="sub" style="margin-top:10px">No entry is suggested: the model rates this {t.esc(v.rating)}. These are reference levels, not a buy plan.</div></div>'
        )

    mid = p.entry_mid
    move = lambda x: f"{(x / mid - 1) * 100:+.1f}%"  # noqa: E731
    rr = p.reward_risk
    rows = [
        _lvl("Entry zone" + (" (wait for pullback)" if p.stretched else ""), f"Rs {p.entry_low:,.1f} – {p.entry_high:,.1f}"),
        _lvl("Stop-loss (close below)", f"Rs {p.stop:,.1f}  ({move(p.stop)})", "down"),
        _lvl("Target 1", f"Rs {p.target1:,.1f}  ({move(p.target1)})", "up"),
        _lvl("Target 2", f"Rs {p.target2:,.1f}  ({move(p.target2)})", "up"),
        _lvl("Reward : risk to target 1", f"{rr:.1f} : 1" if rr else "—"),
        _lvl("Support · resistance", f"{p.support:,.1f} · {p.resistance:,.1f}"),
        _lvl("Break-even sell price", f"Rs {breakeven_price(mid):,.1f}"),
    ]
    return f'<div class="card"><div class="label" style="margin-bottom:6px">Trade plan idea</div>{"".join(rows)}</div>'


def _event_warnings(symbol: str) -> list[str]:
    out = []
    div = data.dividends()
    if not div.empty:
        match = div[div["Symbol"] == symbol]
        if not match.empty:
            r = match.iloc[0]
            book = pd.to_datetime(r["Book close"], errors="coerce")
            if pd.notna(book) and book >= pd.Timestamp.today().normalize():
                out.append(
                    f'Book close on {book:%d %b %Y} ({_n(r["Cash %"])}% cash, {_n(r["Bonus %"])}% bonus for FY {r["Year"]}). '
                    "Shares must settle (T+2) before then, and the price normally drops by the payout after book close."
                )
    agm = data.corporate().get("agm", pd.DataFrame())
    if not agm.empty and (agm["Symbol"] == symbol).any():
        when = agm[agm["Symbol"] == symbol]["AGM"].iloc[0]
        if pd.notna(when) and when >= pd.Timestamp.today().normalize():
            out.append(f"AGM scheduled for {when:%d %b %Y}.")
    return out


# --------------------------------------------------------------------------- #
# Tabs
# --------------------------------------------------------------------------- #


def _returns_row(returns: dict) -> None:
    for col, (label, value) in zip(st.columns(len(returns)), returns.items()):
        tone = "flat" if value is None else t.tone(value)
        text = "—" if value is None else f"{value:+.1f}%"
        with col:
            t.render(f'<div class="card stat" style="min-height:0"><div class="label">{label} return</div><div class="value {tone}">{text}</div></div>')


def _technical_table(v: analysis.Verdict, price: float) -> str:
    m = v.metrics
    rows = []

    def add(name: str, value: str, reading: str) -> None:
        rows.append({"Indicator": name, "Value": value, "Reading": reading})

    rsi = m["rsi"]
    if rsi is not None:
        add("RSI (14)", f"{rsi:.1f}", "Overbought" if rsi >= 70 else "Oversold" if rsi <= 30 else "Bullish zone" if rsi >= 55 else "Neutral" if rsi >= 45 else "Weak")
    if m["hist"] is not None:
        add("MACD histogram", f'{m["hist"]:+.2f}', "Bullish" if m["hist"] > 0 else "Bearish")
    for key, label in (("sma20", "20-day average"), ("sma50", "50-day average"), ("sma200", "200-day average")):
        if m[key] is not None:
            add(label, f"{m[key]:,.1f}", "Price above" if price > m[key] else "Price below")
    if m["bb_upper"] is not None:
        add("Bollinger band (20, 2)", f'{m["bb_lower"]:,.1f} – {m["bb_upper"]:,.1f}', "Above upper band" if price > m["bb_upper"] else "Below lower band" if price < m["bb_lower"] else "Inside the band")
    if m["atr"] is not None:
        add("ATR (14)", f'{m["atr"]:,.2f}  ({m["atr"] / price * 100:.1f}% of price)', "Typical daily swing")
    if m["volatility"] is not None:
        add("Volatility (60 sessions)", f'{m["volatility"] * 100:.0f}% annualised', "High" if m["volatility"] > 0.5 else "Moderate" if m["volatility"] > 0.3 else "Low")
    if m["turnover"] is not None:
        add("Average daily turnover", f'Rs {t.nepali_amount(m["turnover"])}', "Liquid" if m["turnover"] >= 10_000_000 else "Tradable" if m["turnover"] >= 2_000_000 else "Thin")
    return t.data_table(pd.DataFrame(rows), [("Indicator", "Indicator", "text"), ("Value", "Value", "text"), ("Reading", "Reading", "text")])


def _with_live(df: pd.DataFrame, row: pd.Series | None, as_of: str) -> pd.DataFrame:
    """Overlay today's board candle so the chart ends on the latest trade, not the last cached history row."""
    if row is None or df.empty or not as_of:
        return df
    today, last, ltp = pd.Timestamp(as_of), df.iloc[-1], float(row["LTP"])
    if today < last["Date"] or abs(ltp / last["Close"] - 1) > 0.11:  # 10% circuit limit; a bigger gap means a different price basis
        return df
    pick = lambda col: float(row[col]) if pd.notna(row[col]) else ltp  # noqa: E731
    live = {"Date": today, "Open": pick("Open"), "High": pick("High"), "Low": pick("Low"), "Close": ltp, "Volume": float(row["Volume"])}
    if "Turnover" in df:
        live["Turnover"] = float(row["Turnover"])
    base = df.iloc[:-1] if today == last["Date"] else df
    return pd.concat([base, pd.DataFrame([live])], ignore_index=True)


def _note(what: str, how: str, now: str) -> str:
    return (
        '<div class="note"><div><div class="label">What is it?</div>'
        f'<p>{t.esc(what)}</p><div class="label" style="margin-top:12px">How to read it</div><p>{t.esc(how)}</p></div>'
        f'<div><div class="label">What it says right now</div><p>{t.esc(now)}</p></div></div>'
    )


TONE_TAG = {"up": ("Positive", "open"), "down": ("Negative", "bad"), "flat": ("Neutral", "closed")}


def _insight_card(item: insights.Insight) -> str:
    label, kind = TONE_TAG[item.tone]
    return (
        f'<div class="card insight {item.tone}"><div class="card-head"><div class="label">{t.esc(item.title)}</div>{t.tag(label, kind)}</div>'
        f"<p>{t.esc(item.text)}</p></div>"
    )


def _stance_card(title: str, stance: insights.Stance) -> str:
    items = "".join(f"<li>{t.esc(p)}</li>" for p in stance.points)
    return (
        f'<div class="card verdict"><div class="label">{t.esc(title)}</div><div class="rating {stance.tone}" style="font-size:1.45rem">{t.esc(stance.action)}</div>'
        f'<ul class="pts {stance.tone if stance.tone != "flat" else ""}">{items}</ul></div>'
    )


def _points(title: str, points: list[str], kind: str = "") -> str:
    items = "".join(f"<li>{t.esc(p)}</li>" for p in points) or "<li>Nothing significant.</li>"
    return f'<div class="card"><div class="label">{t.esc(title)}</div><ul class="pts {kind}">{items}</ul></div>'


def _rs(value: float) -> str:
    return f"Rs {value:+,.0f}"


def _sizing(verdict: analysis.Verdict) -> None:
    """Turn a capital amount into a staged buy plan, a sell plan and the net result at each exit."""
    plan, price = verdict.plan, verdict.metrics["price"]
    t.render(t.section("Buy and sell plan for your capital", "type your capital to see how many shares to buy, at what price and when to sell"))
    if verdict.tone == "down":
        t.render(t.empty_state("No buy plan", f"The model rates this {verdict.rating}, so it does not suggest an entry. If you hold it, see the exit levels above."))
        return
    c1, c2, c3 = st.columns(3)
    capital = c1.number_input("Capital you can deploy (Rs)", min_value=1_000, value=100_000, step=10_000)
    risk_pct = c2.number_input("Most you accept to lose on this trade (% of capital)", min_value=0.1, max_value=20.0, value=2.0, step=0.5)
    term = c3.selectbox("Expected holding period", ["Up to 365 days (7.5% CGT)", "Over 365 days (5% CGT)"])
    cgt = 0.075 if term.startswith("Up") else 0.05
    if verdict.rating == "Hold / Wait":
        st.caption(f"The model does not recommend buying now (rating: {verdict.rating}). Treat this as a what-if, not a signal.")

    ladder = [(plan.entry_high, 0.40), (plan.entry_mid, 0.35), (plan.entry_low, 0.25)]
    avg_entry = sum(p * w for p, w in ladder)
    risk_per_share = avg_entry - plan.stop
    if risk_per_share <= 0:
        return
    total = int(min(capital * risk_pct / 100 // risk_per_share, capital // (avg_entry * 1.01)))
    if total < 3:
        t.render(t.empty_state("Budget too small", "Raise the capital or the loss you accept to size a position."))
        return
    qtys = [int(total * w) for _, w in ladder]
    qtys[0] += total - sum(qtys)
    legs = [(p, q) for (p, _), q in zip(ladder, qtys) if q > 0]
    qty = sum(q for _, q in legs)
    cost = sum(_buy_cost(q, p) for p, q in legs)

    def sale(shares: int, at: float) -> float:
        cost_share = cost * shares / qty
        net, _ = _sell_net(shares, at, cost_share, cgt)
        return net - cost_share

    half = max(qty // 2, 1)
    stop_pnl, t1_pnl, t2_pnl = sale(qty, plan.stop), sale(half, plan.target1), sale(qty - half, plan.target2)
    even = breakeven_price(avg_entry, cost)

    cards = [
        t.stat_card("Shares to buy", f"{qty:,}", note=f"In {len(legs)} steps, average price Rs {avg_entry:,.1f}"),
        t.stat_card("Capital used", f"Rs {cost:,.0f}", note=f"{cost / capital * 100:.0f}% of your capital, charges included"),
        t.stat_card("Loss if stopped out", _rs(stop_pnl), note=f"Exit all at Rs {plan.stop:,.1f}, after charges"),
        t.stat_card("Profit if both targets hit", _rs(t1_pnl + t2_pnl), note=f"After charges and {cgt * 100:.1f}% capital gains tax"),
    ]
    for col, card in zip(st.columns(4), cards):
        with col:
            t.render(card)

    st.write("")
    left, right = st.columns(2)
    with left:
        t.render(t.section("When and where to buy"))
        buys = pd.DataFrame(
            [{"Step": f"Buy {i}", "Price": f"Rs {p:,.1f}", "Shares": f"{q:,}", "Cost": f"Rs {_buy_cost(q, p):,.0f}"} for i, (p, q) in enumerate(legs, start=1)]
        )
        t.render(t.data_table(buys, [("Step", "Step", "text"), ("Price", "Buy at or below", "text"), ("Shares", "Shares", "text"), ("Cost", "Cost incl. charges", "text")]))
        st.caption(
            f"Place these as limit orders below today's Rs {price:,.1f} and skip any that are not filled instead of raising your price."
            if plan.stretched
            else "Buy the first step now and place the others as limit orders on any dip."
        )
    with right:
        t.render(t.section("When to sell"))
        sells = pd.DataFrame(
            [
                {"Exit": "Stop-loss: sell everything", "When": f"A close below Rs {plan.stop:,.1f}", "Shares": f"{qty:,}", "Result": _rs(stop_pnl)},
                {"Exit": "Target 1: sell half", "When": f"Price reaches Rs {plan.target1:,.1f}, then move your stop up to break-even Rs {even:,.1f}", "Shares": f"{half:,}", "Result": _rs(t1_pnl)},
                {"Exit": "Target 2: sell the rest", "When": f"Price reaches Rs {plan.target2:,.1f}, or it closes below its 20-day average", "Shares": f"{qty - half:,}", "Result": _rs(t2_pnl)},
            ]
        )
        t.render(t.data_table(sells, [("Exit", "Exit", "text"), ("When", "When", "wrap"), ("Shares", "Shares", "text"), ("Result", "Net result", "text")]))
    st.write("")
    t.render(
        _points(
            "Rules for selling",
            [
                f"Sell everything on a close below Rs {plan.stop:,.1f}. Do not wait for it to come back or add more.",
                f"After target 1, never let the rest turn into a loss: the break-even sell price is Rs {even:,.1f}.",
                "If neither the stop nor a target is reached within about 8 weeks, re-check this page; sell if momentum has faded or the rating has dropped to Reduce or Avoid.",
                "NEPSE allows a 10% move in a day, so a stop can be gapped through. Keep each position small enough to survive that.",
            ],
        )
    )
    st.caption("Results include broker commission, SEBON fee, DP charge and capital gains tax at the rates in the Tools page. Plan levels come from the model above and are not guaranteed.")


def _insights_section(full: pd.DataFrame, verdict: analysis.Verdict | None, prof: dict | None, events: list[str]) -> None:
    if verdict is None:
        return
    items = insights.key_insights(full, verdict, prof)
    t.render(t.section("What the data is telling us", "each point feeds the rating"))
    for i in range(0, len(items), 2):
        for col, item in zip(st.columns(2), items[i : i + 2]):
            with col:
                t.render(_insight_card(item))
        st.write("")

    concl = insights.conclusion(full, verdict, prof)
    t.render(t.section("Conclusion", "should you buy this now?"))
    t.render(
        f'<div class="card verdict"><div class="label">Verdict for the secondary market</div><div class="rating {concl.tone}">{t.esc(concl.action)}</div>'
        f'<div class="score">Model score {verdict.score} / 100 · {t.esc(verdict.rating)}</div><p>{t.esc(concl.headline)}</p>{_who(verdict)}</div>'
    )
    st.write("")
    t.render(t.section("What to do", "separate advice depending on whether you already own it"))
    hold_col, buy_col = st.columns(2)
    with hold_col:
        t.render(_stance_card("If you already own it", concl.holders))
        avg = st.number_input("Your average buy price (Rs), optional", min_value=0.0, value=0.0, step=1.0, key="stock-avg-price", help="Enter what you paid per share for a check that fits your position.")
        if avg > 0:
            tone, lines = insights.holder_review(avg, verdict)
            t.render(_points("Check for your position", lines, tone if tone in ("up", "down") else ""))
    with buy_col:
        t.render(_stance_card("If you are thinking of buying", concl.new_buyers))
    st.write("")
    for_col, against_col, change_col = st.columns(3)
    with for_col:
        t.render(_points("Why it could work", concl.for_points, "up"))
    with against_col:
        t.render(_points("Reasons for caution", concl.against_points + events, "down"))
    with change_col:
        t.render(_points("What would improve the view", concl.upgrade, "up"))
        st.write("")
        t.render(_points("What would hurt it", concl.downgrade, "down"))
    st.write("")
    t.render(_points("Who it suits", concl.horizon))
    _sizing(verdict)
    st.caption(
        "This conclusion comes from the app's rule-based scoring of price, volume, momentum, valuation, dividends and liquidity, not from a language model. "
        "It cannot see company news, rumours or your own situation, so treat it as a starting point and not as advice."
    )


def _interactive_panels(symbol: str, full: pd.DataFrame, bars: int, verdict: analysis.Verdict | None, notes: dict | None) -> None:
    """TradingView-style candles with volume, RSI and MACD that zoom, pan and hover together."""
    plan = verdict.plan if _buy_setup(verdict) else None
    channel = f"sg-{symbol}-{st.session_state.get('stock-basis', '')}"
    sections = [
        ("price", "1. Price candles and volume", "scroll to zoom, drag to pan, hover for the crosshair", ("price", "volume")),
        ("rsi", "2. RSI", "is the price overheated or washed out?", ("rsi",)),
        ("macd", "3. MACD", "is momentum building or fading?", ("macd",)),
    ]
    for kind, title, sub, note_keys in sections:
        st.write("")
        t.render(t.section(title, sub))
        html, height = lwcharts.build(kind, full, t.palette(), plan, symbol, bars, channel)
        st.iframe(html, height=height)
        for key in note_keys:
            if notes:
                t.render(_note(*notes[key]))
        st.write("")


def _price_tab(
    symbol: str, hist: pd.DataFrame, verdict: analysis.Verdict | None, row: pd.Series | None, as_of: str, notes: dict | None,
    adj_full: pd.DataFrame | None, prof: dict | None, events: list[str],
) -> None:
    if hist.empty:
        common.unavailable("Price history")
        return
    pick, style_col, basis_col = st.columns([2, 2, 2], vertical_alignment="center")
    with style_col:
        style = st.radio(
            "Chart style", ["Interactive", "Classic"], horizontal=True, label_visibility="collapsed", key="stock-style",
            help="Interactive works like TradingView: scroll to zoom, drag to pan, and the three charts move together. Classic is a static chart with a zoom slider.",
        )
    with basis_col:
        basis = st.radio(
            "Prices", ["Bonus-adjusted", "As traded"], horizontal=True, label_visibility="collapsed", key="stock-basis",
            help="Adjusted prices are rolled back for bonus shares so there is no false drop at book close. As traded shows the raw prices from the exchange.",
        )
    source, source_note = hist, ""
    if basis == "As traded":
        traded = _with_live(data.traded_history(symbol), row, as_of)
        if traded.empty:
            source_note = "Could not load as-traded prices, so the charts show bonus-adjusted prices."
        else:
            source = traded
    full = analysis.add_indicators(source)
    with pick:
        choice = st.radio("Range", list(CHART_RANGES), index=1, horizontal=True, label_visibility="collapsed", key="stock-range")
    window = full.tail(CHART_RANGES[choice]).reset_index(drop=True)
    if style == "Classic":
        days = window["Date"].dt.date.tolist()
        start, end = st.select_slider("Zoom", options=days, value=(days[0], days[-1]), format_func=lambda d: f"{d:%d %b %Y}", label_visibility="collapsed")
        view = window[window["Date"].dt.date.between(start, end)].reset_index(drop=True)
        if len(view) < 5:
            view = window.tail(5).reset_index(drop=True)
    else:
        view = window

    if source_note:
        st.caption(source_note)
    elif basis == "As traded":
        st.caption("As-traded prices drop at each bonus book close, which also bends the moving averages for a few weeks. The notes and the rating always use bonus-adjusted prices.")
    else:
        st.caption("Bonus-adjusted: older candles are scaled down for bonus shares so a book close does not look like a crash, so they can differ from the quotes you saw back then. Choose As traded for the raw exchange prices.")
    st.caption(
        f"Latest candle: {view['Date'].iloc[-1]:%d %b %Y}. "
        + ("Scroll to zoom and drag to pan; the charts move together. Pick a range to reset the view." if style == "Interactive" else "Pick a range, then drag the zoom handles to narrow the window; every chart rescales to it.")
    )

    if style == "Interactive":
        _interactive_panels(symbol, full, len(view), verdict, notes)
    else:
        headings = {
            "price": ("1. Price candles", "what the price did, day by day"),
            "volume": ("2. Volume", "how much trading backed the moves"),
            "rsi": ("3. RSI", "is the price overheated or washed out?"),
            "macd": ("4. MACD", "is momentum building or fading?"),
        }
        panels = charts.stock_panels(view, verdict.plan if _buy_setup(verdict) else None)
        for key, panel in zip(("price", "volume", "rsi", "macd"), panels):
            st.write("")
            t.render(t.section(*headings[key]))
            t.show_chart(panel)
            if notes:
                t.render(_note(*notes[key]))
            st.write("")

    if verdict:
        t.render(t.section("Returns", "over the last N trading sessions"))
        _returns_row(verdict.metrics["returns"])
    index = data.history()
    if not index.empty:
        t.render(t.section(f"{symbol} against NEPSE", "both rebased to 100 at the start of the window"))
        first, last = view["Date"].iloc[0], view["Date"].iloc[-1]
        chart = charts.relative_performance(hist[hist["Date"].between(first, last)], index[index["Date"].between(first, last)], symbol, len(view))
        if chart is not None:
            t.show_chart(chart)
            if notes:
                t.render(_note(*notes["relative"]))
    if verdict:
        t.render(t.section("Indicator readings", "latest session"))
        t.render(_technical_table(verdict, verdict.metrics["price"]))
        _insights_section(adj_full, verdict, prof, events)


def _why_tab(verdict: analysis.Verdict | None) -> None:
    if verdict is None:
        t.render(t.empty_state("Not enough trading history", "A rating needs at least 30 trading sessions, so newly listed scrips are not scored."))
        return
    rows = pd.DataFrame(
        [
            {"Factor": f.name, "Weight": f"{f.weight}%", "Stance": t.tag(f.stance, STANCE_TAG[f.stance]), "Detail": f.detail}
            for f in verdict.factors
        ]
    )
    left, right = st.columns([2, 3])
    with left:
        t.show_chart(charts.factor_bars(verdict.factors))
    with right:
        t.render(t.data_table(rows, [("Factor", "Factor", "text"), ("Weight", "Weight", "text"), ("Stance", "Stance", "html"), ("Detail", "What the data shows", "wrap")]))
    st.caption(
        "Each factor scores from bearish to bullish; the weighted average becomes the 0-100 score (68+ Buy, 57+ Accumulate, 43+ Hold / Wait, 32+ Reduce, below that Avoid). Buy and Accumulate become 'Buy on a dip' when the price is stretched (RSI 70+, far above its average or just under resistance). "
        "The plan uses 14-day average true range for the stop and the recent 60-day high as the first target. NEPSE allows a 10% move per day, so gaps through a stop are possible. "
        "Capital gains tax is 7.5% on holdings up to a year and 5% beyond."
    )


def _fundamentals_tab(prof: dict | None) -> None:
    if prof is None:
        common.unavailable("Fundamentals")
        return
    price = prof.get("price")
    cash = prof.get("dividend") or 0.0
    cash_yield = cash * (prof.get("paid_up") or 100) / 100 / price * 100 if price else None
    eps_note = f' ({prof["eps_period"]})' if prof.get("eps_period") else ""
    left, mid, right = st.columns(3)
    with left:
        t.render(_kv_card("Valuation", [
            ("EPS" + eps_note, _n(prof.get("eps"))), ("P/E ratio", _n(prof.get("pe"))),
            ("Book value", _n(prof.get("book_value"))), ("Price to book", _n(prof.get("pbv"))),
        ]))
    with mid:
        t.render(_kv_card("Payout", [
            ("Cash dividend", _n(prof.get("dividend"), 2, "%") if cash else "None"), ("Bonus shares", _n(prof.get("bonus"), 2, "%") if prof.get("bonus") else "None"),
            ("Cash yield at this price", _n(cash_yield, 2, "%") if cash else "—"), ("1-year price yield", _n(prof.get("yield_1y"), 2, "%")),
        ]))
    with right:
        t.render(_kv_card("Share structure", [
            ("Listed shares", _n(prof.get("listed_shares"), 0)), ("Paid-up value", f'Rs {_n(prof.get("paid_up"), 0)}'),
            ("30-day average volume", _n(prof.get("avg_volume_30"), 0)), ("120 / 180-day average", f'{_n(prof.get("avg_120"))} / {_n(prof.get("avg_180"))}'),
        ]))
    history = prof["dividends"]
    t.render(t.section("Cash dividend history", "% of paid-up value, by fiscal year"))
    if history.empty:
        t.render(t.empty_state("No cash dividend history", "This scrip has no recorded cash dividends."))
    else:
        t.show_chart(charts.payout_history(history))
    st.caption("Ratios are as reported by Merolagani, so check the latest quarterly report before relying on them. Bonus shares do not add value on their own: the price adjusts at book close.")


def _peers_tab(symbol: str, name: str, prof: dict | None, peer_df: pd.DataFrame) -> None:
    t.render(t.section("Most traded scrips in the sector", "today's move and valuation"))
    if peer_df.empty:
        t.render(t.empty_state("No peers to compare", "The sector could not be matched on today's price board."))
    else:
        t.render(
            t.data_table(
                peer_df,
                [("Symbol", "Symbol", "sym"), ("LTP", "LTP", "num"), ("% Change", "Change", "pct"), ("Turnover", "Turnover", "money"),
                 ("P/E", "P/E", "num"), ("PBV", "P/B", "num"), ("EPS", "EPS", "num"), ("Cash %", "Cash div %", "num")],
            )
        )
        if prof and prof.get("pe") and (valid := peer_df["P/E"].dropna().loc[lambda s: s > 0]).size >= 2:
            st.caption(f'{symbol} P/E {prof["pe"]:,.1f} against a peer median of {valid.median():,.1f}.')

    t.render(t.section("In the news", f"headlines that mention {symbol}"))
    news = data.news()
    if news.empty:
        t.render(t.empty_state("No news loaded", "The news feeds did not respond."))
        return
    core = re.sub(r"\b(limited|ltd\.?)\b", "", name or "", flags=re.I).strip()
    mask = news["Title"].str.contains(rf"\b{re.escape(symbol)}\b", case=False, regex=True)
    if len(core) > 6:
        mask |= news["Title"].str.contains(re.escape(core), case=False, regex=True)
    hits = news[mask].head(8)
    t.render(t.news_list(hits) if not hits.empty else t.empty_state("Nothing recent", f"No current headline mentions {symbol}."))


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #


def _pick_economics(r, budget: float = 100_000, cgt: float = 0.075) -> tuple[float, float, float, float] | None:
    """Entry price, cost, net profit at target 1 and net result at the stop for a Rs 1 lakh position."""
    mid = (r.EntryLow + r.EntryHigh) / 2
    qty = int(budget // (mid * 1.01))
    if qty < 1:
        return None
    cost = _buy_cost(qty, mid)
    return mid, cost, _sell_net(qty, r.Target1, cost, cgt)[0] - cost, _sell_net(qty, r.Stop, cost, cgt)[0] - cost


def _picks_section(board_df: pd.DataFrame | None) -> None:
    t.render(t.section("Shares to buy today", "the model's positive setups among the most traded scrips, ranked by profit potential"))
    if board_df is None or board_df.empty:
        common.unavailable("The price board")
        return
    c1, c2, c3 = st.columns([3, 3, 2], vertical_alignment="bottom")
    n = c1.selectbox("Scan", [20, 40, 60], index=1, format_func=lambda k: f"Top {k} scrips by turnover today")
    sort = c2.selectbox("Rank by", ["Profit potential", "Model score", "Reward to risk"])
    if c3.button("Scan the market", width="stretch", key="picks-run"):
        st.session_state["picks-n"] = n
    scanned = st.session_state.get("picks-n")
    if not scanned:
        t.render(t.empty_state("Ready when you are", "Press Scan the market to rate the most traded scrips and list the ones with a buy setup. The first scan takes a few seconds."))
        return

    top = board_df[~board_df["Sector"].str.contains("Mutual|Debenture|Bond", case=False, na=False)].sort_values("Turnover", ascending=False).head(scanned)
    with st.spinner(f"Rating {len(top)} scrips..."):
        result = data.screen(tuple(zip(top["Symbol"], top["Company"], top["Sector"])))
    if result.empty:
        common.unavailable("The market scan")
        return
    picks = result[result["Rating"].isin(("Buy", "Accumulate", "Buy on a dip")) & (result["Score"] >= MIN_PICK_SCORE) & (result["RewardRisk"].fillna(0) >= MIN_PICK_RR)]
    rows = []
    for r in picks.itertuples():
        eco = _pick_economics(r)
        if eco is None:
            continue
        mid, cost, gain, loss = eco
        rows.append(
            {
                "Symbol": r.Symbol, "Company": r.Company, "Rating": t.tag(r.Rating, "soon" if r.Rating == "Buy on a dip" else "open"),
                "Action": f"Buy near Rs {mid:,.1f}" if r.Rating == "Buy on a dip" else "Buy now",
                "Price": r.Price, "Zone": f"{r.EntryLow:,.1f} – {r.EntryHigh:,.1f}", "Stop": r.Stop, "Target": r.Target1,
                "Profit": f"Rs {gain:+,.0f} ({gain / cost * 100:+.1f}%)", "Loss": f"Rs {loss:+,.0f}",
                "RR": r.RewardRisk, "Score": r.Score, "_gain": gain / cost,
            }
        )
    if not rows:
        t.render(t.empty_state("No buy setups right now", f"None of the {len(result)} scrips rated has a strong enough setup (score {MIN_PICK_SCORE}+ and reward-to-risk {MIN_PICK_RR}+). Staying in cash is a valid position."))
        return
    key = {"Profit potential": "_gain", "Model score": "Score", "Reward to risk": "RR"}[sort]
    table = pd.DataFrame(rows).sort_values(key, ascending=False).head(15)
    t.render(
        t.data_table(
            table,
            [("Symbol", "Symbol", "sym"), ("Rating", "Rating", "html"), ("Action", "Today", "text"), ("Price", "Price", "num"), ("Zone", "Buy zone", "text"),
             ("Stop", "Stop", "num"), ("Target", "Target 1", "num"), ("Profit", "Profit at target 1", "text"), ("Loss", "Loss at stop", "text"),
             ("RR", "Reward : risk", "num"), ("Score", "Score", "int")],
        )
    )
    st.caption(
        f"{len(rows)} of {len(result)} scrips rated pass the bar (a buy-type rating, score {MIN_PICK_SCORE}+ and reward-to-risk {MIN_PICK_RR}+). Profit and loss are for Rs 1,00,000 bought in the middle of the buy zone, after charges and 7.5% capital gains tax, "
        "and only happen if the target or stop is actually reached. 'Buy near' means place a limit order at that price instead of paying today's. Click a symbol for its full analysis. "
        "Scores here compare valuation with the other scrips in this scan, so the detail page can differ by a few points."
    )


def _issue_rows(symbol: str) -> list[tuple[str, str]]:
    """Issue facts for a scrip that is in the IPO, right, FPO or SEBON pipeline."""
    rows: list[tuple[str, str]] = []
    for kind, df in data.issues().items():
        if df.empty or "Symbol" not in df:
            continue
        match = df[df["Symbol"] == symbol]
        if match.empty:
            continue
        r = match.iloc[0]
        date = lambda v: "To be announced" if pd.isna(v) else f"{v:%d %b %Y}"  # noqa: E731
        rows += [("Issue type", kind), ("Status", str(r["Status"])), ("Units", _n(r["Units"], 0)), ("Price", f'Rs {_n(r["Price"])}'),
                 ("Opens", date(r["Opens"])), ("Closes", date(r["Closes"])), ("Issue manager", r["Manager"] or "—")]
        break
    if not rows:
        pending = data.upcoming()
        match = pending[pending["Symbol"] == symbol] if not pending.empty else pending
        if not match.empty:
            r = match.iloc[0]
            rows = [("Issue", "Approved by SEBON"), ("Units", _n(r["Units"], 0)), ("Amount", f'Rs {t.nepali_amount(r["Amount"])}' if pd.notna(r["Amount"]) else "—"),
                    ("Issue manager", r["Manager"] or "—")]
    return rows


def _source_links(symbol: str) -> None:
    links = [
        ("ShareSansar", scraper.company_url(symbol)),
        ("Merolagani", f"{scraper.ML}/CompanyDetail.aspx?symbol={symbol}"),
        ("Arthakendra", f"{scraper.AK}/stock-market/company/{symbol}"),
        ("NEPSE", "https://nepalstock.com/company"),
    ]
    for col, (label, url) in zip(st.columns(len(links)), links):
        with col:
            st.link_button(label, url, icon=":material/open_in_new:", width="stretch")


def _details_page(symbol: str, name_hint: str, sector_hint: str, reason: str) -> bool:
    """Fallback for scrips without price history: company details, issue facts and links to the sources. False if nothing is known."""
    if not re.fullmatch(r"[A-Za-z0-9]{1,15}", symbol):
        return False
    info = data.company_info(symbol) or {}
    issue = _issue_rows(symbol)
    known = bool(info or issue or name_hint)
    name = info.get("Name") or name_hint
    sector = info.get("Sector") or sector_hint
    t.render(_head(symbol, name, sector, None, 0, 0, ""))
    if not known:
        reason = "No company details were found for this symbol. Check the spelling, or look it up directly on the sources below."
    t.render(t.empty_state(f"No analysis for {symbol} yet", reason))
    st.write("")

    details = [(k, v) for k, v in info.items() if k not in ("Symbol", "Name", "Sector") and not re.fullmatch(r"(Rs\.?\s*)?0+(\.0+)?(\s*units)?", v)]
    if known:
        left, right = st.columns(2)
        with left:
            t.render(_kv_card("Company details", [("Symbol", symbol), ("Name", name or "—"), ("Sector", sector or "—"), *details]))
        with right:
            if issue:
                t.render(_kv_card("Issue details", issue))
            else:
                t.render(_kv_card("Where to look", [("Prices and history", "Open the sources below"), ("Official data", "NEPSE listed securities"), ("Reports and news", "Company page on ShareSansar")]))
    t.render(t.section("Open the full details", "ShareSansar, Merolagani and others"))
    _source_links(symbol)
    return True


def render() -> None:
    b = data.board()
    board_df = None if b is None else b["df"]
    directory = data.companies()

    names: dict[str, str] = {}
    sectors: dict[str, str] = {}
    for frame in (directory, board_df):
        if frame is not None and not frame.empty:
            names |= dict(zip(frame["Symbol"], frame["Company"]))
            sectors |= dict(zip(frame["Symbol"], frame["Sector"]))
    symbols = sorted(names)
    if not symbols:
        t.render(t.hero("Stock", "analysis"))
        common.unavailable("The company list")
        return

    picker, _, ss, ml = st.columns([5, 1, 2, 2], vertical_alignment="center")
    with picker:
        symbol = _picker(symbols, names)
    if not symbol:
        wanted = st.query_params.get("symbol", "").strip().upper()
        if wanted and wanted not in names and _details_page(
            wanted, "", "", "This symbol is not on today's price board, so it is not trading yet (for example an IPO or a newly approved issue) or it has been delisted. Here is what is publicly known."
        ):
            _picks_section(board_df)
            t.render(t.disclaimer())
            return
        _landing(board_df, wanted if wanted and wanted not in names else "")
        _picks_section(board_df)
        t.render(t.disclaimer())
        return
    with ss:
        st.link_button("ShareSansar", scraper.company_url(symbol), icon=":material/open_in_new:", width="stretch")
    with ml:
        st.link_button("Merolagani", f"{scraper.ML}/CompanyDetail.aspx?symbol={symbol}", icon=":material/open_in_new:", width="stretch")

    with st.spinner(f"Loading {symbol}…"):
        hist = data.stock_history(symbol)
        prof = data.profile(symbol)
        row = None
        if board_df is not None:
            match = board_df[board_df["Symbol"] == symbol]
            row = match.iloc[0] if not match.empty else None
        sector = sectors.get(symbol, "")
        as_of = b["as_of"] if b else ""
        hist = _with_live(hist, row, as_of)
        peer_df = data.peers(symbol, sector, board_df) if board_df is not None else pd.DataFrame()
        verdict = analysis.evaluate(hist, prof or {}, data.history(), peer_df) if not hist.empty else None
        full = analysis.add_indicators(hist) if verdict else None
        notes = insights.panel_notes(full, verdict) if verdict else None

    name = (prof or {}).get("name") or names.get(symbol, "")
    if hist.empty:
        _details_page(symbol, name, sector, "There is no price history for this scrip yet, so charts and a rating are not available.") or common.unavailable(f"{symbol} data")
        _picks_section(board_df)
        t.render(t.disclaimer(b["fetched_at"] if b and "fetched_at" in b else None))
        return
    ltp, change, pct = _price_now(row, hist)
    day_label = f'Trading day {b["as_of"]}' if b and row is not None else (f'Last session {hist["Date"].iloc[-1]:%d %b %Y}' if not hist.empty else "")
    t.render(_head(symbol, name, sector or (prof or {}).get("sector", ""), ltp, change, pct, day_label))
    if hist.empty and prof is None:
        common.unavailable(f"{symbol} data")
        return

    _snapshot(row, prof, hist, verdict)
    st.write("")
    events = _event_warnings(symbol) if verdict else []
    if verdict:
        left, right = st.columns([3, 2])
        with left:
            t.render(_verdict_card(verdict, verdict.warnings + events))
        with right:
            t.render(_plan_card(verdict))
    else:
        t.render(t.empty_state("No rating yet", "A rating needs at least 30 trading sessions of price history."))
    st.write("")

    price_tab, why_tab, fund_tab, peer_tab = st.tabs(["Price & technicals", "Why this rating", "Fundamentals", "Peers & news"])
    with price_tab:
        _price_tab(symbol, hist, verdict, row, as_of, notes, full, prof, events)
    with why_tab:
        _why_tab(verdict)
    with fund_tab:
        _fundamentals_tab(prof)
    with peer_tab:
        _peers_tab(symbol, name, prof, peer_df)
    _picks_section(board_df)
    t.render(t.disclaimer(b["fetched_at"] if b and "fetched_at" in b else None))
