"""Interactive TradingView-style charts built on Lightweight Charts (Apache-2.0, bundled in assets/).

Each panel is a small self-contained HTML page for an iframe. Panels on the same page share a BroadcastChannel so
zooming, panning and the crosshair move together.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

_ASSETS = Path(__file__).parent / "assets"
HEIGHTS = {"price": 500, "rsi": 190, "macd": 210}

_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;background:transparent;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
#c{position:relative;width:100%;height:__H__px}
#lg{position:absolute;left:10px;top:8px;z-index:5;font-size:12px;line-height:1.55;color:__TEXT__;pointer-events:none;
background:__LEGENDBG__;padding:4px 9px;border-radius:9px;font-variant-numeric:tabular-nums;max-width:calc(100% - 100px)}
#lg b{font-weight:600}.u{color:__UP__}.d{color:__DOWN__}.m{color:__MUTED__}
</style></head><body><div id="c"><div id="lg"></div></div>
<script>__LIB__</script>
<script>
const CFG = __CFG__;
const P = CFG.palette;
const el = document.getElementById('c'), lg = document.getElementById('lg');
const id = Math.random().toString(36).slice(2);
const chart = LightweightCharts.createChart(el, {
  autoSize: true,
  layout: {background: {type: 'solid', color: 'transparent'}, textColor: P.muted, fontFamily: 'Inter, system-ui, sans-serif', fontSize: 12},
  grid: {vertLines: {color: P.line}, horzLines: {color: P.line}},
  rightPriceScale: {borderColor: P.line, minimumWidth: 74, scaleMargins: CFG.margins},
  timeScale: {borderColor: P.line, rightOffset: 6, barSpacing: 9, minBarSpacing: 2, timeVisible: false, fixRightEdge: false},
  crosshair: {mode: 0,
    vertLine: {color: P.muted, width: 1, style: 3, labelBackgroundColor: P.accent},
    horzLine: {color: P.muted, width: 1, style: 3, labelBackgroundColor: P.accent}},
  localization: {dateFormat: 'dd MMM yyyy'},
});
const f2 = x => (x === undefined || x === null) ? '–' : Number(x).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const f0 = x => (x === undefined || x === null) ? '–' : Math.round(x).toLocaleString('en-US');
let main, lookup = {}, legend = () => '';

if (CFG.kind === 'price') {
  const candles = chart.addCandlestickSeries({
    upColor: P.up, downColor: P.down, borderVisible: false, wickUpColor: P.up, wickDownColor: P.down,
    priceLineColor: P.accent, priceLineStyle: 2,
  });
  candles.setData(CFG.candles);
  main = candles;
  const vol = chart.addHistogramSeries({priceFormat: {type: 'volume'}, priceScaleId: '', lastValueVisible: false, priceLineVisible: false});
  vol.priceScale().applyOptions({scaleMargins: {top: 0.82, bottom: 0}});
  vol.setData(CFG.volume);
  const lines = CFG.averages.map(a => {
    const s = chart.addLineSeries({color: a.color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false});
    s.setData(a.data);
    return {s, a};
  });
  CFG.levels.forEach(l => candles.createPriceLine({price: l.price, color: l.color, lineWidth: l.width, lineStyle: l.style, axisLabelVisible: true, title: l.title}));
  if (CFG.markers.length) candles.setMarkers(CFG.markers);
  CFG.candles.forEach((c, i) => { lookup[c.time] = c.close; c.i = i; });
  const byTime = {}; CFG.candles.forEach((c, i) => byTime[c.time] = i);
  legend = param => {
    const t = param && param.time ? param.time : CFG.candles[CFG.candles.length - 1].time;
    const i = byTime[t]; const c = CFG.candles[i]; const prev = CFG.candles[i - 1];
    if (!c) return '';
    const chg = prev ? (c.close / prev.close - 1) * 100 : 0;
    const cls = c.close >= c.open ? 'u' : 'd';
    const v = CFG.volume[i];
    const avgs = lines.map(({a}) => { const p = a.data[i]; return p && p.value !== undefined ? `<span style="color:${a.color}">${a.name} <b>${f2(p.value)}</b></span>` : ''; }).join(' &nbsp;');
    return `<div><span class="m">${CFG.symbol}</span> &nbsp;<span class="m">O</span> <b class="${cls}">${f2(c.open)}</b> <span class="m">H</span> <b class="${cls}">${f2(c.high)}</b> <span class="m">L</span> <b class="${cls}">${f2(c.low)}</b> <span class="m">C</span> <b class="${cls}">${f2(c.close)}</b> <b class="${cls}">${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%</b> &nbsp;<span class="m">Vol</span> <b>${f0(v && v.value)}</b></div><div>${avgs}</div>`;
  };
} else if (CFG.kind === 'rsi') {
  const zone = (base, value, top, bottom) => {
    const s = chart.addBaselineSeries({baseValue: {type: 'price', price: base}, topLineColor: 'transparent', bottomLineColor: 'transparent',
      topFillColor1: top, topFillColor2: top, bottomFillColor1: bottom, bottomFillColor2: bottom, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false});
    s.setData(CFG.times.map(t => ({time: t, value})));
  };
  zone(70, 100, P.downFill, 'transparent');
  zone(30, 0, 'transparent', P.upFill);
  const rsi = chart.addLineSeries({color: P.accent, lineWidth: 2, priceLineVisible: false, autoscaleInfoProvider: () => ({priceRange: {minValue: 0, maxValue: 100}})});
  rsi.setData(CFG.rsi);
  [30, 50, 70].forEach(v => rsi.createPriceLine({price: v, color: P.muted, lineWidth: 1, lineStyle: 2, axisLabelVisible: v !== 50, title: ''}));
  main = rsi;
  CFG.rsi.forEach(p => { if (p.value !== undefined) lookup[p.time] = p.value; });
  const byTime = {}; CFG.rsi.forEach((p, i) => byTime[p.time] = i);
  legend = param => {
    const t = param && param.time ? param.time : CFG.times[CFG.times.length - 1];
    const p = CFG.rsi[byTime[t]]; const v = p && p.value;
    const zoneTxt = v === undefined ? '' : v >= 70 ? 'overheated' : v <= 30 ? 'washed out' : v >= 55 ? 'bullish zone' : v >= 45 ? 'neutral' : 'weak';
    return `<span class="m">RSI (14)</span> <b>${f2(v)}</b> <span class="m">${zoneTxt}</span>`;
  };
} else {
  const hist = chart.addHistogramSeries({priceLineVisible: false, lastValueVisible: false});
  hist.setData(CFG.hist);
  const macd = chart.addLineSeries({color: P.accent, lineWidth: 2, priceLineVisible: false, lastValueVisible: false});
  macd.setData(CFG.macd);
  const sig = chart.addLineSeries({color: P.accent2, lineWidth: 2, lineStyle: 2, priceLineVisible: false, lastValueVisible: false});
  sig.setData(CFG.signal);
  macd.createPriceLine({price: 0, color: P.muted, lineWidth: 1, lineStyle: 0, axisLabelVisible: false, title: ''});
  main = macd;
  CFG.macd.forEach(p => { if (p.value !== undefined) lookup[p.time] = p.value; });
  const byTime = {}; CFG.macd.forEach((p, i) => byTime[p.time] = i);
  legend = param => {
    const t = param && param.time ? param.time : CFG.times[CFG.times.length - 1];
    const i = byTime[t];
    const m = CFG.macd[i] && CFG.macd[i].value, s = CFG.signal[i] && CFG.signal[i].value, h = CFG.hist[i] && CFG.hist[i].value;
    const cls = h >= 0 ? 'u' : 'd';
    return `<span class="m">MACD</span> <b style="color:${P.accent}">${f2(m)}</b> &nbsp;<span class="m">Signal</span> <b style="color:${P.accent2}">${f2(s)}</b> &nbsp;<span class="m">Histogram</span> <b class="${cls}">${h > 0 ? '+' : ''}${f2(h)}</b>`;
  };
}

lg.innerHTML = legend(null);
chart.subscribeCrosshairMove(param => { lg.innerHTML = legend(param); });
const n = CFG.times.length;
let quiet = true;  // true while the code, not the user, is moving the view
const home = () => { quiet = true; chart.timeScale().setVisibleLogicalRange({from: n - CFG.bars - 0.5, to: n + 5}); setTimeout(() => { quiet = false; }, 150); };
home();
[60, 250, 700].forEach(ms => setTimeout(home, ms));

// keep every panel on the page in step: zoom, pan and crosshair
if ('BroadcastChannel' in window) {
  const bc = new BroadcastChannel(CFG.channel);
  let applying = false, dragging = false, lastUser = 0;
  const touch = () => { lastUser = Date.now(); };
  el.addEventListener('wheel', touch, {passive: true, capture: true});
  el.addEventListener('pointerdown', () => { dragging = true; touch(); }, true);
  window.addEventListener('pointerup', () => { dragging = false; touch(); });
  chart.timeScale().subscribeVisibleLogicalRangeChange(r => {
    if (!r || applying || quiet) return;
    if (!dragging && Date.now() - lastUser > 500) return;
    bc.postMessage({t: 'range', id, from: r.from, to: r.to});
  });
  bc.onmessage = e => {
    const m = e.data;
    if (m.id === id) return;
    if (m.t === 'range') {
      const cur = chart.timeScale().getVisibleLogicalRange();
      if (cur && Math.abs(cur.from - m.from) < 0.01 && Math.abs(cur.to - m.to) < 0.01) return;
      applying = true; chart.timeScale().setVisibleLogicalRange({from: m.from, to: m.to});
      setTimeout(() => { applying = false; }, 60);
    } else if (m.t === 'cross') {
      const v = lookup[m.time];
      if (v !== undefined) chart.setCrosshairPosition(v, m.time, main);
    } else if (m.t === 'leave') {
      chart.clearCrosshairPosition();
    }
  };
  el.addEventListener('mousemove', ev => {
    const x = ev.clientX - el.getBoundingClientRect().left;
    const time = chart.timeScale().coordinateToTime(x);
    if (time) bc.postMessage({t: 'cross', id, time});
  });
  el.addEventListener('mouseleave', () => bc.postMessage({t: 'leave', id}));
}
</script></body></html>"""


@lru_cache(maxsize=1)
def _library() -> str:
    return (_ASSETS / "lightweight-charts.js").read_text(encoding="utf-8").replace("</script>", "<\\/script>")


def _series(dates: list[str], values: pd.Series) -> list[dict]:
    """One point per date; gaps become whitespace points so every panel keeps the same time index."""
    return [{"time": d} if pd.isna(v) else {"time": d, "value": round(float(v), 4)} for d, v in zip(dates, values)]


def _level(price: float, colour: str, title: str, style: int = 2, width: int = 1) -> dict:
    return {"price": round(price, 2), "color": colour, "title": title, "style": style, "width": width}


def build(kind: str, df: pd.DataFrame, palette: dict, plan=None, symbol: str = "", bars: int = 63, channel: str = "sg") -> tuple[str, int]:
    """HTML and iframe height for one panel: kind is 'price' (candles with volume), 'rsi' or 'macd'."""
    dates = [d.strftime("%Y-%m-%d") for d in df["Date"]]
    p = palette
    pal = {
        "up": p["up"], "down": p["down"], "muted": p["muted"], "line": p["line"], "accent": p["accent"], "accent2": p["accent2"],
        "upFill": f'rgba({p["up_rgb"]},0.14)', "downFill": f'rgba({p["down_rgb"]},0.14)',
    }
    cfg: dict = {"kind": kind, "palette": pal, "times": dates, "bars": min(bars, len(df)), "channel": channel, "symbol": symbol, "height": HEIGHTS[kind]}

    if kind == "price":
        cfg["margins"] = {"top": 0.1, "bottom": 0.2}
        cfg["candles"] = [
            {"time": d, "open": round(float(o), 2), "high": round(float(h), 2), "low": round(float(lo), 2), "close": round(float(c), 2)}
            for d, o, h, lo, c in zip(dates, df["Open"], df["High"], df["Low"], df["Close"])
        ]
        cfg["volume"] = [
            {"time": d, "value": float(v), "color": (p["up"] if c >= o else p["down"]) + "88"}
            for d, v, o, c in zip(dates, df["Volume"].fillna(0), df["Open"], df["Close"])
        ]
        names = [("SMA20", "20-day", p["accent"]), ("SMA50", "50-day", p["accent2"])] + ([("SMA200", "200-day", p["muted"])] if len(df) > 150 else [])
        cfg["averages"] = [{"name": label, "color": colour, "data": _series(dates, df[col])} for col, label, colour in names]
        window = df.tail(cfg["bars"])
        hi_row, lo_row = window.loc[window["High"].idxmax()], window.loc[window["Low"].idxmin()]
        cfg["markers"] = sorted(
            [
                {"time": hi_row["Date"].strftime("%Y-%m-%d"), "position": "aboveBar", "color": p["up"], "shape": "arrowDown", "text": f'High {hi_row["High"]:,.1f}'},
                {"time": lo_row["Date"].strftime("%Y-%m-%d"), "position": "belowBar", "color": p["down"], "shape": "arrowUp", "text": f'Low {lo_row["Low"]:,.1f}'},
            ],
            key=lambda m: m["time"],
        )
        levels: list[dict] = []
        if plan is not None:
            price = float(df["Close"].iloc[-1])
            for value, colour, title in (
                (plan.target2, p["up"], "Target 2"), (plan.target1, p["up"], "Target 1"),
                (plan.entry_high, p["accent"], "Buy zone"), (plan.entry_low, p["accent"], "Buy zone"), (plan.stop, p["down"], "Stop"),
            ):
                if price * 0.7 <= value <= price * 1.35:
                    levels.append(_level(value, colour, title, style=3 if title == "Buy zone" else 2))
        cfg["levels"] = levels
    elif kind == "rsi":
        cfg["margins"] = {"top": 0.1, "bottom": 0.1}
        cfg["rsi"] = _series(dates, df["RSI"])
    else:
        cfg["margins"] = {"top": 0.12, "bottom": 0.12}
        cfg["macd"], cfg["signal"] = _series(dates, df["MACD"]), _series(dates, df["Signal"])
        cfg["hist"] = [
            {"time": d, "value": round(float(v), 4), "color": (p["up"] if v >= 0 else p["down"]) + "AA"} if pd.notna(v) else {"time": d}
            for d, v in zip(dates, df["Hist"])
        ]

    height = HEIGHTS[kind]
    html = (
        _PAGE.replace("__H__", str(height))
        .replace("__TEXT__", p["text"]).replace("__MUTED__", p["muted"]).replace("__UP__", p["up"]).replace("__DOWN__", p["down"])
        .replace("__LEGENDBG__", p["card"]).replace("__LIB__", _library()).replace("__CFG__", json.dumps(cfg, allow_nan=False))
    )
    return html, height + 4
