"""Altair chart builders. Values are labelled on the chart itself; colors follow the active theme."""

from __future__ import annotations

import altair as alt
import pandas as pd

from share_gyan.theme import area_gradient, palette, style_chart

_Y_AXIS = {"minExtent": 58, "maxExtent": 58}  # equal widths keep stacked panels aligned


def _label_marks(p: dict, **kw) -> dict:
    # No stroke halo: Vega paints text strokes over the glyphs and hides them.
    return {"color": p["text"], "fontSize": 12, "fontWeight": 600, **kw}


def nepse_area(df: pd.DataFrame, height: int = 360):
    p = palette()
    lo, hi = float(df["Close"].min()), float(df["Close"].max())
    pad = (hi - lo) * 0.18 or 1.0
    long_range = len(df) > 90
    axis = (
        alt.Axis(format="%b %y", tickCount={"interval": "month", "step": 1}, labelFlush=False, title="Date")
        if long_range
        else alt.Axis(format="%d %b", labelFlush=False, title="Date")
    )
    base = alt.Chart(df).encode(
        x=alt.X("Date:T", axis=axis, scale=alt.Scale(padding=36)),
        y=alt.Y("Close:Q", title="NEPSE index (points)", scale=alt.Scale(domain=[lo - pad, hi + pad], clamp=True)),
        tooltip=[alt.Tooltip("Date:T", format="%d %b %Y"), alt.Tooltip("Close:Q", format=",.2f"), alt.Tooltip("High:Q", format=",.2f"), alt.Tooltip("Low:Q", format=",.2f")],
    )
    area = base.mark_area(line={"color": p["accent"], "strokeWidth": 2.4}, color=area_gradient(), interpolate="monotone", clip=True)
    hover = base.mark_circle(opacity=0, size=200)

    first, last = df.iloc[0], df.iloc[-1]
    change = (last["Close"] / first["Close"] - 1) * 100
    notes = pd.DataFrame(
        [
            {"Date": first["Date"], "Close": first["Close"], "Label": f'{first["Close"]:,.0f}', "Tone": "edge", "Dy": -12},
            {"Date": df.loc[df["Close"].idxmax(), "Date"], "Close": hi, "Label": f"High {hi:,.0f}", "Tone": "up", "Dy": -12},
            {"Date": df.loc[df["Close"].idxmin(), "Date"], "Close": lo, "Label": f"Low {lo:,.0f}", "Tone": "down", "Dy": 18},
            {"Date": last["Date"], "Close": last["Close"], "Label": f'{last["Close"]:,.0f} ({change:+.1f}%)', "Tone": "now", "Dy": -12},
        ]
    )
    colors = alt.Scale(domain=["edge", "up", "down", "now"], range=[p["muted"], p["up"], p["down"], p["accent"]])
    pts = alt.Chart(notes).encode(x="Date:T", y="Close:Q", color=alt.Color("Tone:N", scale=colors, legend=None))
    dots = pts.mark_point(filled=True, size=90, stroke=p["bg2"], strokeWidth=2)
    # edge labels are anchored away from the plot border so they never clip
    txt = alt.Chart(notes).encode(x="Date:T", y="Close:Q")
    labels = [
        txt.mark_text(**_label_marks(p, align="left", dx=6, dy=22)).encode(text="Label:N").transform_filter(alt.datum.Tone == "edge"),
        txt.mark_text(**_label_marks(p, align="center", dy=-14)).encode(text="Label:N").transform_filter(alt.datum.Tone == "up"),
        txt.mark_text(**_label_marks(p, align="center", dy=20)).encode(text="Label:N").transform_filter(alt.datum.Tone == "down"),
        txt.mark_text(**_label_marks(p, align="right", dx=-8, dy=22)).encode(text="Label:N").transform_filter(alt.datum.Tone == "now"),
    ]
    return style_chart(alt.layer(area, hover, dots, *labels), height)


def sector_change_bars(df: pd.DataFrame, height: int = 420):
    p = palette()
    data = df.rename(columns={"% Change": "Pct"})
    base = alt.Chart(data).encode(y=alt.Y("Sector:N", sort="-x", title=None, axis=alt.Axis(labelLimit=200)), x=alt.X("Pct:Q", title="% change today", scale=alt.Scale(padding=44)))
    bars = base.mark_bar(cornerRadiusEnd=8, size=16).encode(
        color=alt.condition(alt.datum.Pct >= 0, alt.value(p["up"]), alt.value(p["down"])),
        tooltip=["Sector", alt.Tooltip("Pct:Q", format="+.2f", title="% change"), alt.Tooltip("Index:Q", format=",.2f")],
    )
    pos = base.mark_text(**_label_marks(p, align="left", dx=6)).encode(text=alt.Text("Pct:Q", format="+.2f")).transform_filter(alt.datum.Pct >= 0)
    neg = base.mark_text(**_label_marks(p, align="right", dx=-6)).encode(text=alt.Text("Pct:Q", format="+.2f")).transform_filter(alt.datum.Pct < 0)
    return style_chart(alt.layer(bars, pos, neg), height)


def sector_turnover_bars(df: pd.DataFrame, height: int = 420):
    p = palette()
    data = df.assign(Crore=df["Turnover"] / 1e7)
    base = alt.Chart(data).encode(
        y=alt.Y("Sector:N", sort="-x", title=None, axis=alt.Axis(labelLimit=200)),
        x=alt.X("Crore:Q", title="Turnover (Rs crore)", scale=alt.Scale(padding=36)),
    )
    bars = base.mark_bar(cornerRadiusEnd=8, size=16, color=p["accent"]).encode(tooltip=["Sector", alt.Tooltip("Crore:Q", format=",.2f", title="Rs crore")])
    text = base.mark_text(**_label_marks(p, align="left", dx=6)).encode(text=alt.Text("Crore:Q", format=",.1f"))
    return style_chart(alt.layer(bars, text), height)


def issue_size_bars(df: pd.DataFrame, height: int = 320):
    p = palette()
    order = df.sort_values("Closes", ascending=False)["Symbol"].tolist()
    base = alt.Chart(df).encode(
        x=alt.X("Symbol:N", sort=order, title="IPO (newest first)", axis=alt.Axis(labelAngle=-40)),
        y=alt.Y("Size:Q", title="Issue size (Rs crore)", scale=alt.Scale(padding=18)),
    )
    bars = base.mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8, color=p["accent"]).encode(
        tooltip=["Symbol", "Company", alt.Tooltip("Units:Q", format=",.0f"), alt.Tooltip("Size:Q", format=",.2f", title="Rs crore")]
    )
    text = base.mark_text(**_label_marks(p, align="center", dy=-8)).encode(text=alt.Text("Size:Q", format=",.1f"))
    return style_chart(alt.layer(bars, text), height)


def dividend_stack(df: pd.DataFrame, height: int = 340):
    p = palette()
    order = df["Symbol"].tolist()
    long = df.melt(id_vars="Symbol", value_vars=["Cash %", "Bonus %"], var_name="Type", value_name="Percent").dropna()
    bars = (
        alt.Chart(long)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
        .encode(
            x=alt.X("Symbol:N", title="Company", sort=order, axis=alt.Axis(labelAngle=-40)),
            y=alt.Y("Percent:Q", title="Dividend (% of Rs 100 face value)", scale=alt.Scale(padding=18)),
            color=alt.Color("Type:N", scale=alt.Scale(domain=["Cash %", "Bonus %"], range=[p["accent"], p["accent2"]]), legend=alt.Legend(orient="top", title=None)),
            tooltip=["Symbol", "Type", alt.Tooltip("Percent:Q", format=".3f")],
        )
    )
    totals = (
        alt.Chart(df.assign(Total=df["Cash %"].fillna(0) + df["Bonus %"].fillna(0)))
        .mark_text(**_label_marks(p, align="center", dy=-8))
        .encode(x=alt.X("Symbol:N", sort=order), y="Total:Q", text=alt.Text("Total:Q", format=".1f"))
    )
    return style_chart(alt.layer(bars, totals), height)


def sip_growth(df: pd.DataFrame, height: int = 320):
    p = palette()
    long = df.melt(id_vars="Year", value_vars=["Invested", "Value"], var_name="Series", value_name="Rs")
    ends = long[long["Year"] == long["Year"].max()].assign(Label=lambda d: d["Rs"].map(lambda v: f"Rs {v:,.0f}"))
    base = alt.Chart(long).encode(
        x=alt.X("Year:Q", title="Years invested", axis=alt.Axis(tickMinStep=1, grid=False), scale=alt.Scale(domain=[0, int(long["Year"].max())], nice=False)),
        y=alt.Y("Rs:Q", title="Rupees", axis=alt.Axis(format="~s")),
        color=alt.Color("Series:N", scale=alt.Scale(domain=["Invested", "Value"], range=[p["muted"], p["accent"]]), legend=alt.Legend(orient="top", title=None)),
    )
    line = base.mark_line(strokeWidth=2.6, interpolate="monotone").encode(tooltip=["Series", "Year", alt.Tooltip("Rs:Q", format=",.0f")])
    labels = (
        alt.Chart(ends)
        .mark_text(**_label_marks(p, align="right", dx=-6, dy=-10))
        .encode(x="Year:Q", y="Rs:Q", text="Label:N")
    )
    return style_chart(alt.layer(line, labels), height)


def portfolio_bars(df: pd.DataFrame, height: int = 340):
    p = palette()
    top = df.sort_values("Value", ascending=False).head(15).rename(columns={"% Change": "Pct"})
    order = top["Symbol"].tolist()
    base = alt.Chart(top).encode(
        x=alt.X("Symbol:N", sort=order, title="Holding", axis=alt.Axis(labelAngle=-40)),
        y=alt.Y("Value:Q", title="Value at last price (Rs)", axis=alt.Axis(format="~s"), scale=alt.Scale(padding=18)),
    )
    bars = base.mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8).encode(
        color=alt.condition(alt.datum.Change >= 0, alt.value(p["up"]), alt.value(p["down"])),
        tooltip=["Symbol", "Company", alt.Tooltip("Balance:Q", format=",.0f"), alt.Tooltip("Value:Q", format=",.0f"), alt.Tooltip("Pct:Q", format="+.2f")],
    )
    text = base.mark_text(**_label_marks(p, align="center", dy=-8)).encode(text=alt.Text("Value:Q", format="~s"))
    return style_chart(alt.layer(bars, text), height)


# --------------------------------------------------------------------------- #
# Single scrip
# --------------------------------------------------------------------------- #


def _date_x(df: pd.DataFrame, labels: bool) -> alt.X:
    fmt = "%d %b" if len(df) <= 130 else "%b %y"
    return alt.X("Date:T", title=None, axis=alt.Axis(format=fmt, labels=labels, ticks=labels, grid=False, labelFlush=False), scale=alt.Scale(padding=10))


def _up_down(p: dict, test: str):
    return alt.condition(test, alt.value(p["up"]), alt.value(p["down"]))


def _panel_title(text: str) -> alt.TitleParams:
    return alt.TitleParams(text, anchor="start", fontSize=12.5, fontWeight=600, color=palette()["muted"], offset=10)


def stock_panels(df: pd.DataFrame, plan=None) -> list:
    """Annotated price, volume, RSI and MACD charts for the rows in df, sharing one date axis."""
    p = palette()
    price = float(df["Close"].iloc[-1])

    def x() -> alt.X:
        # one slot per trading session, so candles stay evenly spaced across weekends and holidays
        return alt.X(
            "Date:O", timeUnit="yearmonthdate", title=None, sort="ascending", scale=alt.Scale(paddingInner=0.25, paddingOuter=0.1),
            axis=alt.Axis(format="%d %b", labelFontSize=11, grid=False, labelOverlap="greedy", labelSeparation=34, labelAngle=0, labelPadding=6),
        )

    def windowed() -> alt.Chart:
        return alt.Chart(df)

    def newest(chart: alt.Chart) -> alt.Chart:
        return chart.transform_joinaggregate(newest="max(Date)").transform_filter("datum.Date == datum.newest")

    def callout(chart: alt.Chart, field: str, op: str, label: str, fmt: str, dy: int, color: str) -> list[alt.Chart]:
        """Mark and name the highest or lowest value of a field."""
        edge = chart.transform_joinaggregate(edge=f"{op}({field})").transform_filter(f"datum.{field} == datum.edge")
        edge = edge.transform_calculate(Text=f"'{label}: ' + format(datum.{field}, '{fmt}')")
        return [
            edge.mark_point(filled=True, size=55, color=color).encode(y=f"{field}:Q"),
            edge.mark_text(**_label_marks(p, dy=dy, fontSize=11, color=color)).encode(y=f"{field}:Q", text="Text:N"),
        ]
    # --- price ------------------------------------------------------------- #
    scale = alt.Scale(zero=False, nice=True, padding=8)
    colour = _up_down(p, "datum.Close >= datum.Open")
    tips = [
        alt.Tooltip("Date:T", format="%d %b %Y"),
        *(alt.Tooltip(f"{c}:Q", format=",.1f") for c in ("Open", "High", "Low", "Close")),
        alt.Tooltip("DayChange:Q", format="+.2f", title="Day change %"),
        alt.Tooltip("Volume:Q", format=",.0f"),
    ]
    base = windowed().encode(x=x())
    wick = base.mark_rule(strokeWidth=1.6).encode(y=alt.Y("Low:Q", scale=scale, title="Price (Rs)", axis=alt.Axis(**_Y_AXIS)), y2="High:Q", color=colour, tooltip=tips)
    body = base.mark_bar(cornerRadius=1).encode(y=alt.Y("Open:Q", scale=scale), y2="Close:Q", color=colour, tooltip=tips)
    averages = ["SMA20", "SMA50"] + (["SMA200"] if len(df) > 150 else [])
    names = "{'SMA20': '20-day average', 'SMA50': '50-day average', 'SMA200': '200-day average'}[datum.label]"
    lines = (
        base.transform_fold(averages, as_=["Average", "Value"])
        .transform_filter("isValid(datum.Value)")
        .mark_line(strokeWidth=2)
        .encode(
            y=alt.Y("Value:Q", scale=scale),
            color=alt.Color(
                "Average:N", scale=alt.Scale(domain=averages, range=[p["accent"], p["accent2"], p["muted"]][: len(averages)]),
                legend=alt.Legend(orient="top", title=None, symbolType="stroke", symbolStrokeWidth=3, labelExpr=names),
            ),
        )
    )
    layers = [wick, body, lines]
    layers += callout(base, "High", "max", "High", ",.1f", -12, p["up"])
    layers += callout(base, "Low", "min", "Low", ",.1f", 16, p["down"])
    last = newest(base)
    layers.append(last.mark_point(filled=True, size=70, color=p["accent"]).encode(y="Close:Q"))

    # labels live in the right margin, spread apart vertically so none overlap a candle or another label
    labels = [(f"Last: {price:,.1f}", price, p["accent"])]
    if plan is not None:
        zone = pd.DataFrame([{"Lo": plan.entry_low, "Hi": plan.entry_high}])
        layers.append(alt.Chart(zone).mark_rect(x=0, x2="width", fill=p["accent"], fillOpacity=0.14).encode(y=alt.Y("Lo:Q", scale=scale), y2="Hi:Q"))
        levels = pd.DataFrame(
            [
                {"Text": f"Stop: {plan.stop:,.1f}", "Value": plan.stop, "Color": p["down"]},
                {"Text": f"Target 1: {plan.target1:,.1f}", "Value": plan.target1, "Color": p["up"]},
                {"Text": f"Target 2: {plan.target2:,.1f}", "Value": plan.target2, "Color": p["up"]},
            ]
        )
        levels = levels[(levels["Value"] >= price * 0.75) & (levels["Value"] <= price * 1.25)]
        if not levels.empty:
            ref = alt.Chart(levels).encode(y=alt.Y("Value:Q", scale=scale), color=alt.Color("Color:N", scale=None))
            layers.append(ref.mark_rule(strokeDash=[6, 4], strokeWidth=1.3))
            labels += [(r.Text, r.Value, r.Color) for r in levels.itertuples()]
        labels.append((f"Buy zone: {plan.entry_low:,.1f}-{plan.entry_high:,.1f}", plan.entry_mid, p["accent"]))

    values = [v for _, v, _ in labels]
    span = max(float(df["High"].max()), *values) - min(float(df["Low"].min()), *values)
    gap = 16 * span / 340  # about 16px between label centres on a plot roughly 340px tall
    placed, previous = [], None
    for text, value, colour in sorted(labels, key=lambda r: -r[1]):
        y = value if previous is None else min(value, previous - gap)
        placed.append({"Text": text, "LabelY": y, "Color": colour})
        previous = y
    layers.append(
        alt.Chart(pd.DataFrame(placed))
        .mark_text(x="width", dx=8, align="left", baseline="middle", fontSize=11, fontWeight=600)
        .encode(y=alt.Y("LabelY:Q", scale=scale), text="Text:N", color=alt.Color("Color:N", scale=None))
    )
    price_panel = alt.layer(*layers).properties(
        title=_panel_title("Price candles (Rs): green = closed higher than it opened, red = closed lower"),
    )

    # --- volume ------------------------------------------------------------ #
    vol = windowed().encode(x=x())
    bars = vol.mark_bar(opacity=0.8, cornerRadius=1).encode(
        y=alt.Y("Volume:Q", title="Shares traded", axis=alt.Axis(format="~s", **_Y_AXIS)),
        color=_up_down(p, "datum.Close >= datum.Open"),
        tooltip=[alt.Tooltip("Date:T", format="%d %b %Y"), alt.Tooltip("Volume:Q", format=",.0f")],
    )
    avg = vol.mark_line(color=p["muted"], strokeDash=[4, 3], strokeWidth=1.8).encode(y="VolAvg30:Q")
    volume_panel = alt.layer(bars, avg, *callout(vol, "Volume", "max", "Busiest", ",.0f", -10, p["accent"])).properties(
        title=_panel_title("Volume: how many shares changed hands (dashed line = usual 30-day level)"),
    )

    # --- RSI --------------------------------------------------------------- #
    rsi_scale = alt.Scale(domain=[0, 100], nice=False)
    rsi = windowed().encode(x=x())
    zone_up = alt.Chart(pd.DataFrame([{"Lo": 0, "Hi": 30}])).mark_rect(x=0, x2="width", fill=p["up"], fillOpacity=0.13).encode(y=alt.Y("Lo:Q", scale=rsi_scale), y2="Hi:Q")
    zone_down = alt.Chart(pd.DataFrame([{"Lo": 70, "Hi": 100}])).mark_rect(x=0, x2="width", fill=p["down"], fillOpacity=0.13).encode(y=alt.Y("Lo:Q", scale=rsi_scale), y2="Hi:Q")
    zone_marks = alt.layer(zone_up, zone_down)
    guides = alt.Chart(pd.DataFrame({"y": [30, 70]})).mark_rule(color=p["muted"], strokeDash=[4, 4], opacity=0.7).encode(y=alt.Y("y:Q", scale=rsi_scale))
    captions = alt.Chart(pd.DataFrame([{"y": 85, "Text": "Overheated zone (70+): buyers may be tired, a dip is likely"}, {"y": 15, "Text": "Washed-out zone (below 30): sellers may be tired, a bounce is possible"}])).mark_text(
        x=8, align="left", fontSize=11, color=p["muted"]
    ).encode(y=alt.Y("y:Q", scale=rsi_scale), text="Text:N")
    rsi_line = rsi.mark_line(color=p["accent"], strokeWidth=2.2).encode(
        y=alt.Y("RSI:Q", title="RSI (0 to 100)", scale=rsi_scale, axis=alt.Axis(values=[0, 30, 50, 70, 100], **_Y_AXIS)),
        tooltip=[alt.Tooltip("Date:T", format="%d %b %Y"), alt.Tooltip("RSI:Q", format=".1f")],
    )
    rsi_now = newest(rsi).transform_calculate(Text="'RSI: ' + format(datum.RSI, '.0f')")
    rsi_panel = alt.layer(
        zone_marks, guides, captions, rsi_line,
        rsi_now.mark_point(filled=True, size=60, color=p["accent"]).encode(y=alt.Y("RSI:Q", scale=rsi_scale)),
        rsi_now.mark_text(x="width", dx=8, align="left", baseline="middle", fontSize=11, fontWeight=600, color=p["accent"]).encode(y=alt.Y("RSI:Q", scale=rsi_scale), text="Text:N"),
    ).properties(title=_panel_title("RSI: a 0 to 100 gauge of how fast the price has been rising or falling"))

    # --- MACD -------------------------------------------------------------- #
    macd = windowed().encode(x=x())
    hist = macd.mark_bar(opacity=0.65, cornerRadius=1).encode(
        y=alt.Y("Hist:Q", title="MACD", axis=alt.Axis(**_Y_AXIS)),
        color=_up_down(p, "datum.Hist >= 0"),
        tooltip=[alt.Tooltip("Date:T", format="%d %b %Y"), alt.Tooltip("MACD:Q", format=".2f"), alt.Tooltip("Signal:Q", format=".2f"), alt.Tooltip("Hist:Q", format=".2f")],
    )
    macd_line = macd.mark_line(color=p["accent"], strokeWidth=2).encode(y="MACD:Q")
    signal_line = macd.mark_line(color=p["accent2"], strokeWidth=2, strokeDash=[5, 3]).encode(y="Signal:Q")
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=p["muted"], opacity=0.6).encode(y="y:Q")
    top_hint = alt.Chart(pd.DataFrame({"t": ["Green bars: buying pressure is building"]})).mark_text(x="width", dx=-8, y=6, align="right", baseline="top", fontSize=11, color=p["up"]).encode(text="t:N")
    bottom_hint = alt.Chart(pd.DataFrame({"t": ["Red bars: selling pressure is building"]})).mark_text(x="width", dx=-8, y="height", dy=-6, align="right", baseline="bottom", fontSize=11, color=p["down"]).encode(text="t:N")
    macd_now = newest(macd)
    above = float(df["MACD"].iloc[-1]) >= float(df["Signal"].iloc[-1])  # whichever line ends higher gets its label above, the other below
    macd_label = dict(x="width", dx=8, align="left", baseline="middle", fontSize=11, fontWeight=600)
    macd_panel = alt.layer(
        hist, zero, macd_line, signal_line, top_hint, bottom_hint,
        macd_now.transform_calculate(Text="'MACD line'").mark_text(dy=-9 if above else 9, color=p["accent"], **macd_label).encode(y="MACD:Q", text="Text:N"),
        macd_now.transform_calculate(Text="'Signal line'").mark_text(dy=9 if above else -9, color=p["accent2"], **macd_label).encode(y="Signal:Q", text="Text:N"),
    ).properties(title=_panel_title("MACD: is buying or selling momentum getting stronger?"))

    panels = [(price_panel, 460), (volume_panel, 170), (rsi_panel, 200), (macd_panel, 220)]
    pad = {"left": 5, "top": 5, "bottom": 5, "right": 150}  # same on every panel so the date axes line up
    return [style_chart(chart.properties(padding=pad), height) for chart, height in panels]


def relative_performance(stock: pd.DataFrame, index: pd.DataFrame, symbol: str, sessions: int, height: int = 300):
    """Stock and NEPSE closes rebased to 100 at the start of the window."""
    joined = stock[["Date", "Close"]].merge(index[["Date", "Close"]], on="Date", suffixes=("_s", "_i")).tail(sessions)
    if len(joined) < 2:
        return None
    p = palette()
    wide = pd.DataFrame({"Date": joined["Date"], symbol: joined["Close_s"] / joined["Close_s"].iloc[0] * 100, "NEPSE": joined["Close_i"] / joined["Close_i"].iloc[0] * 100})
    long = wide.melt("Date", var_name="Series", value_name="Rebased")
    ends = long[long["Date"] == long["Date"].max()].assign(Label=lambda d: d.apply(lambda r: f'{r["Series"]} {r["Rebased"] - 100:+.1f}%', axis=1))
    colors = alt.Scale(domain=[symbol, "NEPSE"], range=[p["accent"], p["muted"]])
    lo, hi = float(long["Rebased"].min()), float(long["Rebased"].max())
    pad = (hi - lo) * 0.12 or 1.0
    base = alt.Chart(long).encode(x=_date_x(wide, labels=True), color=alt.Color("Series:N", scale=colors, legend=alt.Legend(orient="top", title=None)))
    line = base.mark_line(strokeWidth=2.2).encode(
        y=alt.Y("Rebased:Q", title="Rebased to 100", scale=alt.Scale(domain=[lo - pad, hi + pad], nice=False, zero=False)),
        tooltip=["Series", alt.Tooltip("Date:T", format="%d %b %Y"), alt.Tooltip("Rebased:Q", format=".1f")],
    )
    labels = alt.Chart(ends).mark_text(**_label_marks(p, align="right", dx=-6, dy=-10)).encode(x="Date:T", y="Rebased:Q", text="Label:N", color=alt.Color("Series:N", scale=colors, legend=None))
    return style_chart(alt.layer(line, labels), height)


def payout_history(df: pd.DataFrame, height: int = 280):
    p = palette()
    base = alt.Chart(df).encode(
        x=alt.X("Fiscal year:N", sort=df["Fiscal year"].tolist(), title="Fiscal year (BS)", axis=alt.Axis(labelAngle=-40)),
        y=alt.Y("Cash %:Q", title="Cash dividend (% of paid-up value)", scale=alt.Scale(padding=18)),
    )
    bars = base.mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, color=p["accent"]).encode(tooltip=["Fiscal year", alt.Tooltip("Cash %:Q", format=".2f")])
    text = base.mark_text(**_label_marks(p, align="center", dy=-8)).encode(text=alt.Text("Cash %:Q", format=".1f"))
    return style_chart(alt.layer(bars, text), height)


def factor_bars(factors, height: int = 300):
    """Weighted contribution of each factor to the 0-100 score, centred on neutral."""
    p = palette()
    rows = [{"Factor": f.name, "Points": f.score * f.weight / 2, "Stance": f.stance} for f in factors if f.score is not None]
    df = pd.DataFrame(rows)
    base = alt.Chart(df).encode(y=alt.Y("Factor:N", sort=None, title=None, axis=alt.Axis(labelLimit=200)), x=alt.X("Points:Q", title="Points added to or removed from a neutral 50", scale=alt.Scale(padding=40)))
    bars = base.mark_bar(cornerRadiusEnd=8, size=18).encode(
        color=alt.condition(alt.datum.Points >= 0, alt.value(p["up"]), alt.value(p["down"])),
        tooltip=["Factor", alt.Tooltip("Points:Q", format="+.1f"), "Stance"],
    )
    pos = base.mark_text(**_label_marks(p, align="left", dx=6)).encode(text=alt.Text("Points:Q", format="+.1f")).transform_filter(alt.datum.Points >= 0)
    neg = base.mark_text(**_label_marks(p, align="right", dx=-6)).encode(text=alt.Text("Points:Q", format="+.1f")).transform_filter(alt.datum.Points < 0)
    return style_chart(alt.layer(bars, pos, neg), height)
