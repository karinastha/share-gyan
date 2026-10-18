"""Plain-language readings of each chart and a closing buy / wait / avoid conclusion.

Everything here is derived from the rule-based model in analysis.py and the indicator frame it produces;
no language model is involved, so the same data always gives the same wording.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from share_gyan.analysis import Factor, Verdict, _f


@dataclass(frozen=True)
class Insight:
    tone: str  # up / flat / down
    title: str
    text: str


@dataclass(frozen=True)
class Stance:
    action: str
    tone: str
    points: list[str]


@dataclass(frozen=True)
class Conclusion:
    action: str
    tone: str
    headline: str
    for_points: list[str]
    against_points: list[str]
    upgrade: list[str]
    downgrade: list[str]
    horizon: list[str]
    holders: Stance
    new_buyers: Stance


# --------------------------------------------------------------------------- #
# Signal helpers
# --------------------------------------------------------------------------- #


def candle_pattern(df: pd.DataFrame) -> tuple[str, str] | None:
    """Name the most telling shape formed by the last one or two candles."""
    if len(df) < 3:
        return None
    cur, prev = df.iloc[-1], df.iloc[-2]
    o, h, l, c = cur["Open"], cur["High"], cur["Low"], cur["Close"]
    rng, body = h - l, abs(c - o)
    if rng <= 0:
        return None
    if prev["Close"] < prev["Open"] and c > o and o <= prev["Close"] and c >= prev["Open"]:
        return "up", "a bullish engulfing candle: buyers fully reversed the previous day's selling"
    if prev["Close"] > prev["Open"] and c < o and o >= prev["Close"] and c <= prev["Open"]:
        return "down", "a bearish engulfing candle: sellers fully reversed the previous day's buying"
    lower, upper = min(o, c) - l, h - max(o, c)
    if body / rng < 0.1:
        return "flat", "a doji: open and close almost equal, so buyers and sellers are balanced and the move may be pausing"
    if lower > 2 * body and upper <= body:
        return "up", "a hammer (long lower wick): sellers pushed lower but buyers rejected the lows"
    if upper > 2 * body and lower <= body:
        return "down", "a shooting star (long upper wick): buyers pushed higher but sellers rejected the highs"
    if body / rng > 0.85:
        return ("up", "a strong green candle with almost no wick: buyers controlled the whole session") if c > o else (
            "down", "a strong red candle with almost no wick: sellers controlled the whole session")
    return None


def _last_cross(a: pd.Series, b: pd.Series, lookback: int) -> tuple[str, int] | None:
    """Direction and sessions-ago of the latest time series a crossed b inside the lookback."""
    sign = np.sign((a - b).dropna().tail(lookback + 1).to_numpy())
    for i in range(len(sign) - 1, 0, -1):
        if sign[i] != 0 and sign[i - 1] != 0 and sign[i] != sign[i - 1]:
            return ("above" if sign[i] > 0 else "below", len(sign) - 1 - i)
    return None


def _divergence(df: pd.DataFrame) -> tuple[str, str] | None:
    recent = df.tail(40)
    if len(recent) < 40 or recent["RSI"].isna().any():
        return None
    old, new = recent.iloc[:20], recent.iloc[20:]
    if new["Close"].max() > old["Close"].max() and new["RSI"].max() < old["RSI"].max() - 3:
        return "down", "Bearish divergence: price made a higher high but RSI did not, a sign the rally is losing strength."
    if new["Close"].min() < old["Close"].min() and new["RSI"].min() > old["RSI"].min() + 3:
        return "up", "Bullish divergence: price made a lower low but RSI did not, a sign selling pressure is fading."
    return None


def _ago(sessions: int) -> str:
    return "today" if sessions == 0 else "1 session ago" if sessions == 1 else f"{sessions} sessions ago"


def _volume_flow(df: pd.DataFrame) -> float | None:
    """Signed-volume balance over the last 20 sessions, -1 (all selling) to +1 (all buying)."""
    window = df.tail(21)
    move = np.sign(window["Close"].diff()).iloc[1:]
    vol = window["Volume"].iloc[1:]
    total = vol.sum()
    return float((move * vol).sum() / total) if total else None


def _pct(a: float, b: float) -> str:
    return f"{(a / b - 1) * 100:+.1f}%"


# --------------------------------------------------------------------------- #
# Chart notes
# --------------------------------------------------------------------------- #


def panel_notes(df: pd.DataFrame, verdict: Verdict) -> dict[str, tuple[str, str, str]]:
    """For each chart: (what it is, how to read it, what it says right now)."""
    last, m, plan = df.iloc[-1], verdict.metrics, verdict.plan
    price = float(last["Close"])

    stack = [(n, _f(last[f"SMA{n}"])) for n in (20, 50, 200)]
    stack = [(n, v) for n, v in stack if v is not None]
    above = [n for n, v in stack if price > v]
    if not stack:
        trend = "Not enough history for the moving averages"
    elif len(above) == len(stack):
        trend = f"Price is above all {len(stack)} averages, a bullish stack"
    elif not above:
        trend = f"Price is below all {len(stack)} averages, a bearish stack"
    else:
        under = [n for n, _ in stack if n not in above]
        trend = f"Price is above the {' and '.join(map(str, above))}-day average{'s' if len(above) > 1 else ''} but below the {' and '.join(map(str, under))}-day average{'s' if len(under) > 1 else ''}"
    cross = _last_cross(df["SMA20"], df["SMA50"], 30)
    cross_text = f" The 20-day average crossed {cross[0]} the 50-day {_ago(cross[1])}." if cross else ""
    shape = candle_pattern(df)
    shape_text = f" The latest candle is {shape[1]}." if shape else ""
    recovery = (
        f"a close back above the 20-day average (Rs {m['sma20']:,.1f}) would be the first sign of recovery."
        if verdict.tone == "down" and m["sma20"]
        else f"a close above resistance would be a breakout, a close below Rs {plan.stop:,.1f} breaks the plan."
    )
    price_now = (
        f"Closed at Rs {price:,.1f}. {trend}.{cross_text} Nearest support is Rs {plan.support:,.1f} ({_pct(plan.support, price)}) and resistance Rs {plan.resistance:,.1f} "
        f"({_pct(plan.resistance, price)}); {recovery}{shape_text}"
    )

    avg = _f(last["VolAvg30"])
    recent = float(df["Volume"].tail(5).mean())
    flow = _volume_flow(df)
    if avg:
        ratio = recent / avg
        vol_now = f"The last 5 sessions averaged {recent:,.0f} shares, {ratio:.1f}x the 30-day average of {avg:,.0f}. "
        rising = price > float(df["Close"].iloc[-6])
        if ratio >= 1.2:
            vol_now += "Heavy trading backs the " + ("rise, which is a healthy sign." if rising else "fall, so sellers are active.")
        elif ratio <= 0.8:
            vol_now += "Light trading behind the " + ("rise suggests weaker conviction." if rising else "fall suggests selling is not aggressive.")
        else:
            vol_now += "Participation is normal."
    else:
        vol_now = "Not enough volume history to judge participation."
    if flow is not None:
        vol_now += f" Across 20 sessions {'buyers' if flow > 0.1 else 'sellers' if flow < -0.1 else 'neither side'} had the upper hand in volume terms ({flow:+.2f})."

    rsi = m["rsi"]
    div = _divergence(df)
    rsi_now = "Not enough history for RSI."
    if rsi is not None:
        zone = "overbought, so a pullback is more likely than a fresh leg up" if rsi >= 78 else "strong but stretched, so gains may slow or pause" if rsi >= 70 else "oversold, so a bounce is possible but needs confirmation" if rsi <= 30 else (
            "in the bullish zone with room to rise" if rsi >= 55 else "neutral" if rsi >= 45 else "weak")
        rsi_now = f"RSI is {rsi:.0f}: {zone}." + (f" {div[1]}" if div else "")

    macd_now = "Not enough history for MACD."
    if m["hist"] is not None:
        mc = _last_cross(df["MACD"], df["Signal"], 10)
        mc_text = f" The MACD line crossed {mc[0]} its signal line {_ago(mc[1])}." if mc else ""
        prev_hist = float(df["Hist"].iloc[-2])
        macd_now = (
            f"Histogram is {m['hist']:+.2f} and {'strengthening' if m['hist'] > prev_hist else 'fading'}, so momentum is "
            f"{'positive' if m['hist'] > 0 else 'negative'}{' but losing steam' if m['hist'] > 0 and m['hist'] < prev_hist else ' but improving' if m['hist'] < 0 and m['hist'] > prev_hist else ''}.{mc_text}"
        )

    relative = next((f for f in verdict.factors if f.name == "Relative strength"), None)
    return {
        "price": (
            "A candlestick summarises one trading day: where the price opened, where it closed, and its highest and lowest points.",
            "A green body means the price closed higher than it opened; red means it closed lower. The thin line (wick) reaches the day's high and low. "
            "The coloured lines are average prices: a price above them usually means an uptrend. The shaded band is the entry zone suggested for buying.",
            price_now,
        ),
        "volume": (
            "Volume is simply how many shares were bought and sold that day.",
            "Tall bars mean many people traded. A price rise on tall bars is more convincing than a rise on short bars. The dashed line is the usual daily level over the past 30 days.",
            vol_now,
        ),
        "rsi": (
            "RSI (Relative Strength Index) is a speedometer for the price on a scale of 0 to 100. It compares recent up days with down days.",
            "Above 70 means the price has been rising very fast and may be overheated, so a dip is likely. Below 30 means it has been falling very fast and may be washed out, so a bounce is possible. "
            "Between 40 and 60 is normal. Treat it as a warning light, not a buy or sell button.",
            rsi_now,
        ),
        "macd": (
            "MACD (Moving Average Convergence Divergence) shows whether the price trend is speeding up or slowing down, by comparing a fast average with a slow one.",
            "The solid line is the MACD and the dashed line is its signal line. When the solid line crosses above the dashed one, or the bars turn green and grow, buyers are gaining strength. "
            "When it crosses below, or the bars turn red, sellers are gaining. Bars shrinking toward zero mean the move is losing steam.",
            macd_now,
        ),
        "relative": (
            "This compares the stock with the whole market, the NEPSE index.",
            "Both lines start at 100 on the first day of the window, so the gap shows how much better or worse the stock did than the market.",
            relative.detail if relative and relative.score is not None else "Not enough history to compare with NEPSE.",
        ),
    }


# --------------------------------------------------------------------------- #
# Insights and conclusion
# --------------------------------------------------------------------------- #


def _tone(factor: Factor | None) -> str:
    if factor is None or factor.score is None:
        return "flat"
    return "up" if factor.score > 0.25 else "down" if factor.score < -0.25 else "flat"


def key_insights(df: pd.DataFrame, verdict: Verdict, profile: dict | None) -> list[Insight]:
    """The handful of observations that drive the rating, most important first."""
    by_name = {f.name: f for f in verdict.factors}
    notes = panel_notes(df, verdict)
    div = _divergence(df)
    out = [
        Insight(_tone(by_name.get("Trend")), "Trend", by_name["Trend"].detail),
        Insight(_tone(by_name.get("Momentum")), "Momentum", by_name["Momentum"].detail + (f" {div[1]}" if div else "")),
    ]
    shape = candle_pattern(df)
    if shape:
        out.append(Insight(shape[0], "Latest candle", f"The last session formed {shape[1]}."))
    vol = by_name.get("Volume")
    if vol and vol.score is not None:
        out.append(Insight(_tone(vol), "Volume", notes["volume"][2]))
    plan = verdict.plan
    price = verdict.metrics["price"]
    room = (plan.resistance / price - 1) * 100
    buy_setup = verdict.rating in ("Buy", "Accumulate", "Buy on a dip")
    out.append(
        Insight(
            "up" if room > 3 else "flat" if room > 1 else "down",
            "Levels",
            f"Resistance at Rs {plan.resistance:,.1f} is {room:.1f}% away and support at Rs {plan.support:,.1f} is {(1 - plan.support / price) * 100:.1f}% below."
            + (
                f" The plan risks Rs {price - plan.stop:,.1f} per share to chase Rs {plan.target1 - price:,.1f} to the first target"
                + (f" ({plan.reward_risk:.1f}:1)." if plan.reward_risk else ".")
                if buy_setup
                else ""
            ),
        )
    )
    for name in ("Relative strength", "Valuation", "Dividends", "Risk & liquidity"):
        f = by_name.get(name)
        if f and f.score is not None:
            out.append(Insight(_tone(f), name, f.detail))
    if profile and profile.get("eps_period"):
        out.append(Insight("flat", "Reporting basis", f'EPS and P/E come from the latest report ({profile["eps_period"]}); check the newest quarterly report before relying on them.'))
    return out


def conclusion(df: pd.DataFrame, verdict: Verdict, profile: dict | None) -> Conclusion:
    plan, m = verdict.plan, verdict.metrics
    price = m["price"]
    hot, dip = verdict.stretch, m["dip"]
    if verdict.rating == "Buy on a dip":
        action, tone = "Buy on a pullback", "flat"
        headline = f"The setup is positive, but {' and '.join(hot)}. Waiting for a dip toward Rs {dip:,.1f} gives a better price and a tighter stop than chasing at Rs {price:,.1f}."
    elif verdict.rating == "Buy":
        action, tone = "Buy now, in stages", "up"
        headline = f"Signals line up for a swing trade. Build the position around Rs {plan.entry_low:,.1f} to {plan.entry_high:,.1f} with a close-below stop at Rs {plan.stop:,.1f}."
    elif verdict.rating == "Accumulate":
        action, tone = "Accumulate on dips", "up"
        headline = f"Leaning positive but not decisive. Add gradually near Rs {plan.entry_low:,.1f} to {plan.entry_high:,.1f} and keep the stop at Rs {plan.stop:,.1f}."
    elif verdict.rating == "Hold / Wait":
        action, tone = "Wait", "flat"
        headline = "No clear edge right now. Holders can sit tight; new buyers do better waiting for a decisive close above resistance or a pullback toward support."
    elif verdict.rating == "Reduce":
        action, tone = "Avoid new buying", "down"
        headline = "The balance of evidence is negative. If you own it, consider trimming into strength; do not add."
    else:
        action, tone = "Avoid for now", "down"
        headline = "Trend, momentum and flows are weak. Staying out preserves capital until the picture improves."

    scored = [f for f in verdict.factors if f.score is not None]
    for_points = [f"{f.name}: {f.detail}" for f in sorted(scored, key=lambda f: -f.weight * f.score) if f.score > 0.25][:4]
    against_points = [f"{f.name}: {f.detail}" for f in sorted(scored, key=lambda f: f.weight * f.score) if f.score < -0.25][:4]
    against_points += verdict.warnings[:3]

    avg_vol = m["avg_volume"]
    upgrade = [f"A close above Rs {plan.resistance:,.1f}" + (f" on more than {avg_vol * 1.2:,.0f} shares" if avg_vol else "") + " confirms a breakout."]
    downgrade = [f"A close below Rs {plan.stop:,.1f} ends the setup: exit rather than average down."]
    if m["rsi"] is not None and m["rsi"] >= 65:
        upgrade.append("RSI cooling toward 50 to 60 while price holds the 20-day average would give a safer entry.")
    if m["rsi"] is not None and m["rsi"] <= 40:
        upgrade.append("RSI climbing back above 50 would show momentum returning.")
    if m["hist"] is not None:
        (upgrade if m["hist"] < 0 else downgrade).append(
            "The MACD histogram turning positive would confirm improving momentum." if m["hist"] < 0 else "The MACD histogram turning negative would flag fading momentum."
        )
    if m["sma50"] is not None:
        (downgrade if price > m["sma50"] else upgrade).append(
            f"Losing the 50-day average (Rs {m['sma50']:,.1f}) would turn the trend bearish." if price > m["sma50"] else f"Reclaiming the 50-day average (Rs {m['sma50']:,.1f}) would be the first sign of a recovery."
        )

    by_name = {f.name: f for f in verdict.factors}
    horizon = [
        f"Swing trade (2 to 8 weeks): {'favourable' if verdict.score >= 57 else 'neutral' if verdict.score >= 43 else 'unfavourable'}, driven mostly by trend, momentum and volume.",
    ]
    val, inc = by_name.get("Valuation"), by_name.get("Dividends")
    long_scores = [f.score for f in (val, inc) if f is not None and f.score is not None]
    if long_scores:
        avg = sum(long_scores) / len(long_scores)
        horizon.append(f"Long-term holding: {'supportive' if avg > 0.25 else 'questionable' if avg < -0.25 else 'acceptable'} on valuation and dividends, but check the latest earnings.")
    else:
        horizon.append("Long-term holding: valuation and dividend signals are not available for this scrip, so rely on the price action only.")
    return Conclusion(action, tone, headline, for_points, against_points, upgrade, downgrade, horizon, *stances(verdict))


def stances(verdict: Verdict) -> tuple[Stance, Stance]:
    """Separate advice for people who already own the scrip and for people thinking of buying."""
    plan, m, rating = verdict.plan, verdict.metrics, verdict.rating
    price, dip = m["price"], m["dip"]
    trail = m["sma20"] - m["atr"] if m["sma20"] and m["atr"] else None
    stop_line = f"Keep a close-below stop at Rs {plan.stop:,.1f}" + (
        f" and trail it up toward Rs {trail:,.1f} (20-day average less one typical day's swing) as the price rises." if trail and plan.stop < trail < price else "."
    )
    targets = f"First target Rs {plan.target1:,.1f}, second Rs {plan.target2:,.1f}: consider selling a third of the position at each."

    if rating == "Buy":
        holders = Stance("Hold and add on dips", "up", [stop_line, targets, f"Add more only on dips toward Rs {plan.entry_low:,.1f}, not after big one-day jumps."])
        buyers = Stance(
            "Buy now, in stages", "up",
            [f"Split the money into 2 or 3 buys: the first near Rs {plan.entry_mid:,.1f}, the rest on dips toward Rs {plan.entry_low:,.1f} or after a close above Rs {plan.resistance:,.1f}.",
             f"You risk about Rs {price - plan.stop:,.1f} a share down to the stop at Rs {plan.stop:,.1f}; size the position so that loss is acceptable."],
        )
    elif rating == "Buy on a dip":
        holders = Stance(
            "Hold, do not add here", "flat",
            [stop_line, f"Because {' and '.join(verdict.stretch)}, booking a small part of the profit near Rs {plan.resistance:,.1f} is reasonable.", f"Add only if it dips toward Rs {dip:,.1f} and holds there."],
        )
        buyers = Stance(
            "Wait for a dip", "flat",
            [f"Place a buy order near Rs {dip:,.1f} instead of chasing at Rs {price:,.1f}.",
             "If the price keeps rising without a dip, skip it: chasing a stretched rally is how most new buyers lose money.",
             f"A close above Rs {plan.resistance:,.1f} on higher volume would justify a small starter position."],
        )
    elif rating == "Accumulate":
        holders = Stance("Hold", "up", [stop_line, targets])
        buyers = Stance("Accumulate in small stages", "up", [f"Start with a small position near Rs {plan.entry_mid:,.1f} and add only if the trend strengthens.", f"Stop at Rs {plan.stop:,.1f}."])
    elif rating == "Hold / Wait":
        holders = Stance("Hold and watch the stop", "flat", [stop_line, f"Do not add until it closes above Rs {plan.resistance:,.1f} with strong volume."])
        buyers = Stance("Wait", "flat", [f"No clear edge: wait for a close above Rs {plan.resistance:,.1f} with strong volume, or a dip toward support at Rs {plan.support:,.1f} that holds."])
    elif rating == "Reduce":
        holders = Stance(
            "Reduce into strength", "down",
            [f"Sell part of the position on rallies toward Rs {plan.resistance:,.1f}.", stop_line, "Do not average down: adding to a falling stock multiplies the loss."],
        )
        buyers = Stance("Avoid", "down", ["Wait until the price closes back above its 50-day average and the MACD histogram turns positive."])
    else:
        holders = Stance(
            "Exit or protect capital", "down",
            [f"A close below Rs {plan.stop:,.1f} is the exit signal; do not wait for it to come back.", "Do not average down.",
             "Selling into any bounce is better than hoping. A profit held under a year pays 7.5% capital gains tax, over a year 5%."],
        )
        buyers = Stance("Avoid", "down", ["Staying out preserves capital until the trend repairs. Revisit when the price reclaims its 50-day average."])
    return holders, buyers


def holder_review(avg_price: float, verdict: Verdict) -> tuple[str, list[str]]:
    """Tone and advice for someone who bought at avg_price."""
    plan, m, rating = verdict.plan, verdict.metrics, verdict.rating
    price = m["price"]
    pnl = (price / avg_price - 1) * 100
    lines = [f"At Rs {price:,.1f} you are {'up' if pnl >= 0 else 'down'} {abs(pnl):.1f}% on your Rs {avg_price:,.1f} average before charges and tax."]
    if price <= plan.stop:
        return "down", lines + [f"Price is at or below the stop level of Rs {plan.stop:,.1f}. The plan says exit rather than average down."]
    if rating in ("Reduce", "Avoid"):
        lines.append("The model is negative, so protect capital: " + ("lock in most of this profit." if pnl > 3 else "cut the loss on a bounce rather than waiting to break even."))
        return "down", lines
    if pnl >= 10:
        lines.append(f"Good cushion: raise your stop to at least break-even and consider selling a third near Rs {plan.target1:,.1f}.")
    elif pnl > 0:
        lines.append(f"Small profit: keep the stop at Rs {plan.stop:,.1f} and let the trend work toward Rs {plan.target1:,.1f}.")
    else:
        lines.append(f"You are under water but the trend is not broken: hold while price stays above Rs {plan.stop:,.1f}, and add only on a dip toward Rs {m['dip']:,.1f} if the trend holds.")
    if rating == "Buy on a dip":
        lines.append("Do not add at today's stretched price.")
    return "up" if rating in ("Buy", "Accumulate") else "flat", lines
