"""Trading tools: trade P&L, SIP and dividend calculators plus learning links."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from share_gyan import charts, data
from share_gyan import theme as t

# Broker commission slabs: (upper bound of trade value, rate)
_SLABS = [(50_000, 0.0040), (500_000, 0.0037), (2_000_000, 0.0034), (10_000_000, 0.0030), (float("inf"), 0.0027)]
SEBON_FEE = 0.00015
DP_CHARGE = 25.0
MIN_COMMISSION = 10.0


def _commission(amount: float) -> float:
    rate = next(r for limit, r in _SLABS if amount <= limit)
    return max(amount * rate, MIN_COMMISSION)


def _buy_cost(qty: int, price: float) -> float:
    amount = qty * price
    return amount + _commission(amount) + amount * SEBON_FEE


def _sell_net(qty: int, price: float, buy_cost: float, cgt_rate: float) -> tuple[float, float]:
    amount = qty * price
    fees = _commission(amount) + amount * SEBON_FEE + DP_CHARGE
    cgt = max(amount - fees - buy_cost, 0) * cgt_rate
    return amount - fees - cgt, cgt


def breakeven_price(price: float, budget: float = 100_000) -> float:
    """Sell price that recovers every charge on a round trip (no tax is due at break-even)."""
    qty = max(int(budget // price), 1)
    cost = _buy_cost(qty, price)
    return (cost + _commission(cost) + cost * SEBON_FEE + DP_CHARGE) / qty


def _trade_tab() -> None:
    c1, c2, c3, c4 = st.columns(4)
    qty = c1.number_input("Quantity", min_value=1, value=100, step=10)
    buy = c2.number_input("Buy price (Rs)", min_value=0.01, value=300.0, step=1.0)
    sell = c3.number_input("Sell price (Rs)", min_value=0.01, value=330.0, step=1.0)
    term = c4.selectbox("Holding period", ["Up to 365 days (7.5% CGT)", "Over 365 days (5% CGT)"])
    cgt_rate = 0.075 if term.startswith("Up") else 0.05

    cost = _buy_cost(qty, buy)
    proceeds, cgt = _sell_net(qty, sell, cost, cgt_rate)
    pnl = proceeds - cost

    lo, hi = buy, buy * 3 + 500 / qty
    for _ in range(40):
        mid = (lo + hi) / 2
        if _sell_net(qty, mid, cost, cgt_rate)[0] - cost >= 0:
            hi = mid
        else:
            lo = mid

    cards = [
        t.stat_card("Total buy cost", f"Rs {cost:,.2f}", note=f"Commission Rs {_commission(qty * buy):,.2f}"),
        t.stat_card("Net sale proceeds", f"Rs {proceeds:,.2f}", note=f"CGT Rs {cgt:,.2f}"),
        t.stat_card("Net profit / loss", f"Rs {pnl:,.2f}", change=pnl, pct=pnl / cost * 100 if cost else 0),
        t.stat_card("Break-even sell price", f"Rs {hi:,.2f}", note="After all charges"),
    ]
    for col, card in zip(st.columns(4), cards):
        with col:
            t.render(card)
    st.caption("Assumes SEBON commission slabs (0.40% down to 0.27%), a 0.015% SEBON fee, Rs 25 DP charge on sale and capital gains tax on net profit. Confirm current rates with your broker.")


def _sip_tab() -> None:
    c1, c2, c3 = st.columns(3)
    monthly = c1.number_input("Monthly investment (Rs)", min_value=100, value=5_000, step=500)
    annual = c2.slider("Expected annual return (%)", 1.0, 30.0, 12.0, 0.5)
    years = c3.slider("Years", 1, 30, 10)

    r = annual / 100 / 12
    rows = [{"Year": y, "Invested": monthly * y * 12, "Value": monthly * (((1 + r) ** (y * 12) - 1) / r) * (1 + r) if y else 0.0} for y in range(years + 1)]
    df = pd.DataFrame(rows)
    invested, value = monthly * years * 12, df["Value"].iloc[-1]

    cols = st.columns(3)
    with cols[0]:
        t.render(t.stat_card("Invested", f"Rs {invested:,.0f}"))
    with cols[1]:
        t.render(t.stat_card("Estimated value", f"Rs {value:,.0f}", change=value - invested, pct=(value / invested - 1) * 100))
    with cols[2]:
        t.render(t.stat_card("Wealth gained", f"Rs {value - invested:,.0f}", note=f"{value / invested:.2f}x your money"))
    t.show_chart(charts.sip_growth(df))
    st.caption("Projection only. Returns are not guaranteed and compounding is assumed monthly.")


def _dividend_tab() -> None:
    c1, c2, c3 = st.columns(3)
    shares = c1.number_input("Shares held", min_value=1, value=500, step=10)
    cash = c2.number_input("Cash dividend (%)", min_value=0.0, value=7.0, step=0.5)
    bonus = c3.number_input("Bonus shares (%)", min_value=0.0, value=10.0, step=0.5)
    tax, face = 0.05, 100

    cash_gross = shares * face * cash / 100
    bonus_shares = shares * bonus / 100
    bonus_value = bonus_shares * face
    cards = [
        t.stat_card("Cash received", f"Rs {cash_gross * (1 - tax):,.2f}", note=f"Gross Rs {cash_gross:,.2f} less 5% tax"),
        t.stat_card("Bonus shares", f"{bonus_shares:,.2f}", note=f"Face value Rs {bonus_value:,.0f}"),
        t.stat_card("Tax on bonus", f"Rs {bonus_value * tax:,.2f}", note="5% of face value, paid in cash"),
        t.stat_card("New holding", f"{shares + bonus_shares:,.2f}", note="Shares after bonus"),
    ]
    for col, card in zip(st.columns(4), cards):
        with col:
            t.render(card)
    st.caption("Uses Rs 100 face value and 5% dividend tax. Fractional bonus shares are pooled by the company.")


def _learn_tab() -> None:
    for i, (title, body, url) in enumerate(data.LEARN_LINKS):
        if i % 2 == 0:
            cols = st.columns(2)
        with cols[i % 2]:
            t.render(
                f'<div class="card"><div class="label">{t.esc(title)}</div><div style="margin:8px 0 10px">{t.esc(body)}</div>'
                f'<a href="{t.esc(url)}" target="_blank" rel="noopener noreferrer">Open</a></div>'
            )
        if i % 2 == 1:
            st.write("")


def render() -> None:
    t.render(t.hero("Trading", "tools", "Charges and tax calculators, SIP projections and beginner guides for Nepal's share market."))
    tabs = st.tabs(["Trade calculator", "SIP planner", "Dividend calculator", "Learn"])
    for tab, fn in zip(tabs, (_trade_tab, _sip_tab, _dividend_tab, _learn_tab)):
        with tab:
            fn()
    t.render(t.disclaimer())
