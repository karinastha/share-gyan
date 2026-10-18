"""Rule-based buy/hold/avoid read of a NEPSE scrip for secondary-market (swing and positional) trading.

Pure pandas, no I/O. Each factor scores -1 (bearish) to +1 (bullish); the weighted average becomes a 0-100 score.
This is a screening aid built on public price and ratio data, not investment advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

SESSIONS_PER_YEAR = 240
RETURN_WINDOWS = {"1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": SESSIONS_PER_YEAR}
MIN_SESSIONS = 30
ILLIQUID_TURNOVER = 500_000  # Rs per session
NO_VALUATION_SECTORS = ("mutual fund", "debenture")


def _f(value) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def _clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _mean(pairs: list[tuple[float, float]]) -> float:
    return sum(s * w for s, w in pairs) / sum(w for _, w in pairs)


def _sentence(parts: list[str]) -> str:
    text = ", ".join(parts)
    return text[:1].upper() + text[1:] + "."


@dataclass(frozen=True)
class Factor:
    name: str
    weight: int
    score: float | None  # None when the factor does not apply
    detail: str

    @property
    def stance(self) -> str:
        if self.score is None:
            return "n/a"
        return "Bullish" if self.score > 0.25 else "Bearish" if self.score < -0.25 else "Neutral"


@dataclass(frozen=True)
class Plan:
    entry_low: float
    entry_high: float
    stop: float
    target1: float
    target2: float
    support: float
    resistance: float
    stretched: bool

    @property
    def entry_mid(self) -> float:
        return (self.entry_low + self.entry_high) / 2

    @property
    def reward_risk(self) -> float | None:
        risk = self.entry_mid - self.stop
        return (self.target1 - self.entry_mid) / risk if risk > 0 else None


@dataclass(frozen=True)
class Verdict:
    score: int
    rating: str
    tone: str  # up / flat / down
    summary: str
    factors: list[Factor]
    plan: Plan
    warnings: list[str]
    metrics: dict = field(default_factory=dict)
    stretch: list[str] = field(default_factory=list)  # reasons a buy now is poorly timed


# --------------------------------------------------------------------------- #
# Indicators
# --------------------------------------------------------------------------- #


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add moving averages, RSI, MACD, Bollinger bands, ATR and average volume to a daily OHLCV frame."""
    out = df.copy()
    close = out["Close"]
    for n in (20, 50, 200):
        out[f"SMA{n}"] = close.rolling(n).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    out["RSI"] = 100 - 100 / (1 + gain / loss)

    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    out["MACD"] = macd
    out["DayChange"] = close.pct_change() * 100
    out["Signal"] = macd.ewm(span=9, adjust=False).mean()
    out["Hist"] = out["MACD"] - out["Signal"]

    spread = close.rolling(20).std()
    out["BBUpper"] = out["SMA20"] + 2 * spread
    out["BBLower"] = out["SMA20"] - 2 * spread

    prev = close.shift()
    true_range = pd.concat([out["High"] - out["Low"], (out["High"] - prev).abs(), (out["Low"] - prev).abs()], axis=1).max(axis=1)
    out["ATR"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    if "Volume" in out:
        out["VolAvg30"] = out["Volume"].rolling(30).mean()
    return out


def period_returns(close: pd.Series) -> dict[str, float | None]:
    return {label: _f((close.iloc[-1] / close.iloc[-n - 1] - 1) * 100) if len(close) > n else None for label, n in RETURN_WINDOWS.items()}


# --------------------------------------------------------------------------- #
# Factors
# --------------------------------------------------------------------------- #


def _trend(df: pd.DataFrame) -> Factor:
    last = df.iloc[-1]
    pairs, notes = [], []
    for n, weight in ((20, 0.5), (50, 1.0), (200, 1.0)):
        avg = _f(last[f"SMA{n}"])
        if avg is not None:
            above = last["Close"] > avg
            pairs.append((1.0 if above else -1.0, weight))
            notes.append(f'{"above" if above else "below"} the {n}-day average ({avg:,.1f})')
    sma50 = df["SMA50"]
    if len(df) > 60 and pd.notna(sma50.iloc[-1]) and pd.notna(sma50.iloc[-11]):
        slope = sma50.iloc[-1] / sma50.iloc[-11] - 1
        pairs.append((_clip(slope / 0.03), 1.0))
        notes.append(f'50-day average {"rising" if slope > 0 else "falling"} ({slope * 100:+.1f}% over 10 sessions)')
    if not pairs:
        return Factor("Trend", 22, None, "Not enough history to read the trend.")
    return Factor("Trend", 22, _mean(pairs), f'Price {last["Close"]:,.1f} is ' + "; ".join(notes) + ".")


def _momentum(df: pd.DataFrame) -> Factor:
    last, prev = df.iloc[-1], df.iloc[-2]
    rsi, hist = _f(last["RSI"]), _f(last["Hist"])
    if rsi is None or hist is None:
        return Factor("Momentum", 15, None, "Not enough history for RSI and MACD.")
    if rsi >= 78:
        rsi_score, rsi_note = -0.6, "overbought, prone to a pullback"
    elif rsi >= 70:
        rsi_score, rsi_note = 0.2, "strong but getting hot"
    elif rsi >= 55:
        rsi_score, rsi_note = 0.8, "healthy bullish momentum"
    elif rsi >= 45:
        rsi_score, rsi_note = 0.1, "neutral"
    elif rsi >= 30:
        rsi_score, rsi_note = -0.5, "weak momentum"
    else:
        rsi_score, rsi_note = 0.1, "oversold, a bounce is possible but unconfirmed"
    rising = hist > prev["Hist"]
    macd_score = (1.0 if rising else 0.3) if hist > 0 else (-0.2 if rising else -1.0)
    macd_note = f'MACD histogram {"positive" if hist > 0 else "negative"} and {"improving" if rising else "fading"}'
    return Factor("Momentum", 15, (rsi_score + macd_score) / 2, f"RSI {rsi:.0f} is {rsi_note}; {macd_note}.")


def _volume(df: pd.DataFrame) -> Factor:
    avg30 = _f(df["VolAvg30"].iloc[-1])
    if avg30 is None or avg30 <= 0 or len(df) < 31:
        return Factor("Volume", 10, None, "Not enough traded volume to judge.")
    ratio = df["Volume"].tail(5).mean() / avg30
    direction = np.sign(df["Close"].iloc[-1] / df["Close"].iloc[-6] - 1)
    window = df.tail(20)
    up = window.loc[window["Close"].diff() > 0, "Volume"].sum()
    down = window.loc[window["Close"].diff() < 0, "Volume"].sum()
    balance = (up - down) / (up + down) if up + down else 0.0
    score = (direction * _clip(ratio - 1) + balance) / 2
    return Factor(
        "Volume", 10, score,
        f"Last 5 sessions traded {ratio:.1f}x the 30-day average; {up / (up + down) * 100 if up + down else 50:.0f}% of the last 20 sessions' volume came on up days.",
    )


def _position(df: pd.DataFrame) -> Factor:
    year = df.tail(SESSIONS_PER_YEAR)
    hi, lo, price = year["High"].max(), year["Low"].min(), df["Close"].iloc[-1]
    if hi <= lo:
        return Factor("52-week position", 8, None, "No range to measure.")
    pos = (price - lo) / (hi - lo)
    if pos > 0.85:
        score, note = 0.3, "near the yearly high: strong, but little room before resistance"
    elif pos > 0.55:
        score, note = 0.6, "upper half of its range with room to run"
    elif pos > 0.30:
        score, note = 0.1, "mid-range"
    else:
        score, note = -0.5, "near the yearly low: cheap, but sellers are in control"
    return Factor("52-week position", 8, score, f"Sits at {pos * 100:.0f}% of its 52-week range ({lo:,.1f} to {hi:,.1f}): {note}.")


def _relative_strength(df: pd.DataFrame, index: pd.DataFrame | None) -> Factor:
    if index is None or index.empty or len(df) < 64:
        return Factor("Relative strength", 10, None, "Not enough history to compare with NEPSE.")
    start = df["Date"].iloc[-64]
    base = index.set_index("Date")["Close"].asof(start)
    if pd.isna(base):
        return Factor("Relative strength", 10, None, "Not enough index history to compare.")
    stock = (df["Close"].iloc[-1] / df["Close"].iloc[-64] - 1) * 100
    market = (index["Close"].iloc[-1] / base - 1) * 100
    gap = stock - market
    return Factor("Relative strength", 10, _clip(gap / 15), f"{stock:+.1f}% over 3 months against NEPSE {market:+.1f}% ({gap:+.1f} points).")


def _valuation(profile: dict, peers: pd.DataFrame | None) -> Factor:
    pe, pbv, eps = profile.get("pe"), profile.get("pbv"), profile.get("eps")
    sector = (profile.get("sector") or "").lower()
    if any(s in sector for s in NO_VALUATION_SECTORS) or (not eps and not pe):
        return Factor("Valuation", 15, None, "Earnings multiples do not apply (fund, debenture or no reported earnings).")
    if eps is not None and eps < 0:
        return Factor("Valuation", 15, -1.0, f"Loss-making (EPS {eps:,.2f}), so P/E is not meaningful.")

    pairs, notes = [], []
    if pe and pe > 0:
        pairs.append((1.0 if pe <= 12 else 0.5 if pe <= 18 else 0.0 if pe <= 25 else -0.5 if pe <= 35 else -1.0, 1.0))
        notes.append(f"P/E {pe:,.1f}")
    if pbv and pbv > 0:
        pairs.append((1.0 if pbv <= 1.2 else 0.4 if pbv <= 2 else -0.2 if pbv <= 3 else -0.6 if pbv <= 4.5 else -1.0, 1.0))
        notes.append(f"P/B {pbv:,.2f}")
    if peers is not None and not peers.empty:
        for column, own, label in (("P/E", pe, "P/E"), ("PBV", pbv, "P/B")):
            values = peers[column].dropna()
            values = values[values > 0]
            if own and own > 0 and len(values) >= 2:
                median = float(values.median())
                pairs.append((_clip((1 - own / median) * 2), 1.0))
                notes.append(f"peer median {label} {median:,.1f}")
    if not pairs:
        return Factor("Valuation", 15, None, "No usable P/E or P/B.")
    return Factor("Valuation", 15, _mean(pairs), ", ".join(notes) + ".")


def _income(profile: dict, price: float) -> Factor:
    cash, paid_up = profile.get("dividend") or 0.0, profile.get("paid_up") or 100.0
    cash_yield = cash * paid_up / 100 / price * 100
    pairs = [(1.0 if cash_yield >= 5 else 0.6 if cash_yield >= 3 else 0.2 if cash_yield >= 1.5 else 0.0 if cash_yield > 0 else -0.3, 1.0)]
    notes = [f"cash dividend yield {cash_yield:.2f}%" if cash else "no current cash dividend"]
    history = profile.get("dividends")
    if history is not None and not history.empty:
        recent = history.tail(5)
        paid = int((recent["Cash %"] > 0).sum())
        pairs.append((paid / len(recent) * 2 - 1, 1.0))
        notes.append(f"cash dividend paid in {paid} of the last {len(recent)} recorded years")
    return Factor("Dividends", 8, _mean(pairs), _sentence(notes))


def _risk(df: pd.DataFrame) -> tuple[Factor, float | None, float | None]:
    returns = np.log(df["Close"]).diff().tail(60).dropna()
    vol = _f(returns.std() * np.sqrt(SESSIONS_PER_YEAR)) if len(returns) >= 20 else None
    turnover = _f((df["Volume"] * df["Close"]).tail(30).mean())
    pairs, notes = [], []
    if vol is not None:
        pairs.append((_clip((0.40 - vol) / 0.40), 1.0))
        notes.append(f"annualised volatility {vol * 100:.0f}%")
    if turnover is not None:
        pairs.append((1.0 if turnover >= 10_000_000 else 0.2 if turnover >= 2_000_000 else -0.2 if turnover >= ILLIQUID_TURNOVER else -1.0, 1.0))
        notes.append(f"average daily turnover Rs {turnover / 1e5:,.1f} lakh")
    if not pairs:
        return Factor("Risk & liquidity", 12, None, "Not enough data."), vol, turnover
    return Factor("Risk & liquidity", 12, _mean(pairs), _sentence(notes)), vol, turnover


# --------------------------------------------------------------------------- #
# Plan and verdict
# --------------------------------------------------------------------------- #


def _tick(value: float) -> float:
    return round(value, 1)


def trade_plan(df: pd.DataFrame, pullback: bool = False) -> Plan:
    last = df.iloc[-1]
    price = float(last["Close"])
    atr = _f(last["ATR"]) or price * 0.025
    sma20 = _f(last["SMA20"]) or price
    rsi = _f(last["RSI"]) or 50.0
    support = float(df["Low"].tail(20).min())
    resistance = float(df["High"].tail(60).max())
    high_52 = float(df["High"].tail(SESSIONS_PER_YEAR).max())

    stretched = pullback or price > sma20 * 1.06 or rsi >= 75
    if stretched:
        anchor = min(max(sma20, support), price)
        entry_low, entry_high = anchor - 0.5 * atr, anchor + 0.5 * atr
    else:
        entry_low, entry_high = price - 0.75 * atr, price + 0.25 * atr
    mid = (entry_low + entry_high) / 2
    stop = mid - 2 * atr
    target1 = resistance if mid + 1.5 * atr <= resistance <= mid * 1.15 else mid + 3 * atr  # a far-off high is not a realistic swing target
    target2 = high_52 if target1 * 1.03 < high_52 <= mid * 1.30 else target1 + 2 * atr
    return Plan(_tick(entry_low), _tick(entry_high), _tick(max(stop, 0.1)), _tick(target1), _tick(target2), _tick(support), _tick(resistance), stretched)


def _rating(score: int) -> tuple[str, str]:
    if score >= 68:
        return "Buy", "up"
    if score >= 57:
        return "Accumulate", "up"
    if score >= 43:
        return "Hold / Wait", "flat"
    if score >= 32:
        return "Reduce", "down"
    return "Avoid", "down"


def evaluate(hist: pd.DataFrame, profile: dict, index: pd.DataFrame | None = None, peers: pd.DataFrame | None = None) -> Verdict | None:
    """Score a scrip from its daily history and fundamentals. Returns None for scrips with too little history."""
    if hist is None or len(hist) < MIN_SESSIONS:
        return None
    df = add_indicators(hist)
    last = df.iloc[-1]
    price = float(last["Close"])

    risk, vol, turnover = _risk(df)
    factors = [
        _trend(df), _momentum(df), _volume(df), _position(df), _relative_strength(df, index),
        _valuation(profile, peers), _income(profile, price), risk,
    ]
    scored = [f for f in factors if f.score is not None]
    score = round(50 + 50 * sum(f.weight * f.score for f in scored) / sum(f.weight for f in scored))
    rating, tone = _rating(score)
    plan = trade_plan(df)

    room = (plan.resistance / price - 1) * 100
    stretch: list[str] = []
    if plan.stretched:
        stretch.append("price is extended above its short-term average")
    if pd.notna(last["RSI"]) and last["RSI"] >= 70:
        stretch.append(f'RSI is {last["RSI"]:.0f}')
    if 0 <= room < 2:
        stretch.append(f"resistance is only {room:.1f}% away")
    if stretch and not plan.stretched:
        plan = trade_plan(df, pullback=True)  # entry zone moves to the dip so the plan matches the advice
    sma20 = _f(last["SMA20"])
    dip = _tick(sma20) if sma20 and sma20 < price else plan.entry_low

    warnings: list[str] = []
    if turnover is not None and turnover < ILLIQUID_TURNOVER:
        warnings.append(f"Thin liquidity (about Rs {turnover / 1e5:,.1f} lakh a day): you may struggle to exit at a fair price.")
        if tone == "up":
            rating, tone = "Hold / Wait", "flat"
    below_both = pd.notna(last["SMA200"]) and price < last["SMA50"] and price < last["SMA200"]
    if below_both and last["Hist"] < 0:
        warnings.append("Price is below both its 50- and 200-day averages with negative MACD: a downtrend, so do not try to catch the bottom.")
    if pd.notna(last["RSI"]) and last["RSI"] >= 75:
        warnings.append(f'RSI {last["RSI"]:.0f} is overbought; buying here risks a pullback.')
    if vol is not None and vol > 0.60:
        warnings.append(f"Volatility is high ({vol * 100:.0f}% annualised): size the position small.")
    if plan.reward_risk is not None and plan.reward_risk < 1.5 and tone == "up":
        warnings.append(f"Reward-to-risk is only {plan.reward_risk:.1f}:1 to the first target.")
    if stretch and tone == "up":
        rating, tone = "Buy on a dip", "flat"  # good setup but a poor price to enter at today

    strengths = [f.name.lower() for f in sorted(scored, key=lambda f: -f.weight * f.score) if f.score > 0.25][:3]
    concerns = [f.name.lower() for f in sorted(scored, key=lambda f: f.weight * f.score) if f.score < -0.25][:3]
    parts = []
    if strengths:
        parts.append("Supported by " + ", ".join(strengths))
    if concerns:
        parts.append(("held back by " if strengths else "Held back by ") + ", ".join(concerns))
    summary = (" and ".join(parts) + "." if parts else "Signals are mixed with no clear edge.") + " "
    if rating == "Buy on a dip":
        summary += f"But {' and '.join(stretch)}, so wait for a dip toward Rs {dip:,.1f} instead of chasing."
    elif tone == "up":
        summary += f"A staged entry around Rs {plan.entry_low:,.1f} to {plan.entry_high:,.1f} keeps risk contained."
    elif tone == "flat":
        summary += "No strong reason to enter now; wait for a clearer trend or a pullback toward support."
    else:
        summary += "The odds currently favour sellers; avoid new buying until the trend repairs."

    metrics = {
        "price": price,
        "returns": period_returns(df["Close"]),
        "rsi": _f(last["RSI"]),
        "macd": _f(last["MACD"]),
        "signal": _f(last["Signal"]),
        "hist": _f(last["Hist"]),
        "sma20": _f(last["SMA20"]), "sma50": _f(last["SMA50"]), "sma200": _f(last["SMA200"]),
        "bb_upper": _f(last["BBUpper"]), "bb_lower": _f(last["BBLower"]),
        "atr": _f(last["ATR"]),
        "volatility": vol,
        "turnover": turnover,
        "avg_volume": _f(last["VolAvg30"]),
        "dip": dip,
    }
    return Verdict(score, rating, tone, summary, factors, plan, warnings, metrics, stretch)
