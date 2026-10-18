"""Liquid-glass theme with light and dark modes, plus HTML component builders."""

from __future__ import annotations

import base64
import html
from collections.abc import Iterable, Sequence
from urllib.parse import quote

import altair as alt
import pandas as pd
import streamlit as st

PALETTES = {
    "light": {
        "bg": "#eef2fb", "bg2": "#f9fbff", "text": "#0f172a", "muted": "#64748b",
        "card": "rgba(255,255,255,0.62)", "card_border": "rgba(255,255,255,0.9)",
        "shadow": "0 14px 44px -16px rgba(37,72,170,0.22)", "line": "rgba(15,23,42,0.08)",
        "accent": "#3b6cff", "accent2": "#12b5c4", "accent_soft": "rgba(59,108,255,0.12)", "accent_rgb": "59,108,255",
        "up": "#0e9f6e", "down": "#e5484d", "up_rgb": "14,159,110", "down_rgb": "229,72,77",
        "blob1": "rgba(99,132,255,0.50)", "blob2": "rgba(18,181,196,0.40)", "blob3": "rgba(176,140,255,0.38)",
        "input": "rgba(255,255,255,0.85)", "pop": "#ffffff", "gloss": "rgba(255,255,255,0.9)",
        "k_ipo": "37,99,235", "k_local": "13,148,136", "k_right": "147,51,234", "k_fpo": "234,88,12", "k_mf": "219,39,119", "k_deb": "71,85,105",
        "scheme": "light",
    },
    "dark": {
        "bg": "#070b18", "bg2": "#0d1326", "text": "#e8edff", "muted": "#93a0c2",
        "card": "rgba(24,33,62,0.55)", "card_border": "rgba(255,255,255,0.10)",
        "shadow": "0 16px 48px -16px rgba(0,0,0,0.65)", "line": "rgba(255,255,255,0.08)",
        "accent": "#7b9bff", "accent2": "#38d6e0", "accent_soft": "rgba(123,155,255,0.16)", "accent_rgb": "123,155,255",
        "up": "#34d399", "down": "#fb7185", "up_rgb": "52,211,153", "down_rgb": "251,113,133",
        "blob1": "rgba(79,110,255,0.42)", "blob2": "rgba(34,211,238,0.22)", "blob3": "rgba(167,139,250,0.30)",
        "input": "rgba(255,255,255,0.07)", "pop": "#141c36", "gloss": "rgba(255,255,255,0.14)",
        "k_ipo": "96,165,250", "k_local": "45,212,191", "k_right": "192,132,252", "k_fpo": "251,146,60", "k_mf": "244,114,182", "k_deb": "148,163,184",
        "scheme": "dark",
    },
}

BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@500;600&display=swap');

html, body, .stApp { font-family: 'Inter', system-ui, sans-serif; color: var(--text); color-scheme: var(--scheme); }
.stApp, [data-testid="stAppViewContainer"] { background: linear-gradient(160deg, var(--bg) 0%, var(--bg2) 100%) fixed; }
[data-testid="stAppViewContainer"], [data-testid="stMain"] { background: transparent; }

/* liquid background blobs */
.stApp::before, .stApp::after {
  content: ""; position: fixed; z-index: 0; pointer-events: none; filter: blur(70px); opacity: 0.9;
  width: 52vmax; height: 52vmax; border-radius: 42% 58% 61% 39% / 45% 38% 62% 55%;
  animation: drift 26s ease-in-out infinite alternate;
}
.stApp::before { top: -18vmax; left: -12vmax; background: radial-gradient(circle at 30% 30%, var(--blob1), transparent 65%); }
.stApp::after { right: -16vmax; bottom: -20vmax; background: radial-gradient(circle at 60% 60%, var(--blob2), transparent 62%), radial-gradient(circle at 30% 70%, var(--blob3), transparent 60%); animation-duration: 32s; animation-direction: alternate-reverse; }
@keyframes drift {
  0% { transform: translate(0, 0) rotate(0deg); border-radius: 42% 58% 61% 39% / 45% 38% 62% 55%; }
  50% { transform: translate(5vmax, 3vmax) rotate(40deg); border-radius: 58% 42% 38% 62% / 55% 61% 39% 45%; }
  100% { transform: translate(-3vmax, 6vmax) rotate(80deg); border-radius: 39% 61% 52% 48% / 62% 45% 55% 38%; }
}
@media (prefers-reduced-motion: reduce) { .stApp::before, .stApp::after { animation: none; } }

.block-container { max-width: 1520px; padding-top: 5.4rem; padding-bottom: 4rem; padding-left: 2.5rem; padding-right: 2.5rem; position: relative; z-index: 1; }
[data-testid="stHeader"] { background: color-mix(in srgb, var(--bg) 45%, transparent); backdrop-filter: blur(18px) saturate(160%); border-bottom: 1px solid var(--line); }

/* centered pill navbar; icons inherit the link colour so they stay visible in dark mode */
[data-testid="stHeader"] .rc-overflow { justify-content: center; gap: 2px; }
[data-testid="stTopNavLink"] { border-radius: 999px !important; padding: 7px 14px !important; background: transparent !important; transition: background 0.2s, color 0.2s, box-shadow 0.2s; }
[data-testid="stTopNavLink"], [data-testid="stTopNavLink"] *, [data-testid="stTopNavLink"] p { color: var(--muted) !important; font-weight: 600; }
[data-testid="stTopNavLink"]:hover { background: var(--accent_soft) !important; }
[data-testid="stTopNavLink"]:hover, [data-testid="stTopNavLink"]:hover * { color: var(--text) !important; }
[data-testid="stTopNavLink"][aria-current="page"] { background: linear-gradient(135deg, var(--accent), var(--accent2)) !important; box-shadow: 0 8px 20px -8px var(--accent); }
[data-testid="stTopNavLink"][aria-current="page"], [data-testid="stTopNavLink"][aria-current="page"] * { color: #fff !important; }
footer, #MainMenu { visibility: hidden; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
hr { border-color: var(--line) !important; }

/* native widgets */
[data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"] *, [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] *, [role="radiogroup"] label, [role="radiogroup"] label * { color: var(--text) !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * { color: var(--muted) !important; }
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {
  background: var(--input) !important; border: 1px solid var(--card_border) !important; border-radius: 14px !important; box-shadow: 0 2px 12px -6px rgba(0,0,0,0.25);
}
[data-baseweb="input"] input, [data-baseweb="select"] * , input, textarea { color: var(--text) !important; -webkit-text-fill-color: var(--text) !important; background: transparent !important; caret-color: var(--text); }
input::placeholder, textarea::placeholder, [data-baseweb="select"] [aria-live] , [data-baseweb="select"] input::placeholder { color: var(--muted) !important; -webkit-text-fill-color: var(--muted) !important; opacity: 1 !important; }
[data-baseweb="input"] svg, [data-baseweb="select"] svg, [data-testid="stTextInput"] svg { fill: var(--muted) !important; color: var(--muted) !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within { border-color: var(--accent) !important; box-shadow: 0 0 0 3px var(--accent_soft) !important; }
[data-baseweb="popover"] > div, [data-baseweb="menu"], ul[role="listbox"] { background: var(--pop) !important; border: 1px solid var(--line); border-radius: 14px !important; }
[data-baseweb="popover"] li, [data-baseweb="popover"] li * { color: var(--text) !important; }
[data-baseweb="popover"] li:hover { background: var(--accent_soft) !important; }
[data-testid="stNumberInput"] button { background: transparent !important; color: var(--text) !important; }
[data-testid="stNumberInputContainer"], [data-testid="stTextInputRootElement"], [data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"], [data-testid="stTextArea"] > div > div {
  background: var(--input) !important; border: 1px solid var(--card_border) !important; border-radius: 14px !important; box-shadow: 0 2px 12px -6px rgba(0,0,0,0.25);
}
[data-testid="stNumberInputContainer"]:focus-within, [data-testid="stTextInputRootElement"]:focus-within, [data-testid="stSelectbox"] [role="group"]:focus-within { border-color: var(--accent) !important; box-shadow: 0 0 0 3px var(--accent_soft) !important; }
[data-testid="stNumberInputContainer"] *, [data-testid="stSelectbox"] [role="group"] *, [data-testid="stTextInputRootElement"] * { color: var(--text) !important; -webkit-text-fill-color: var(--text) !important; }
[data-testid="stNumberInputContainer"] svg, [data-testid="stSelectbox"] svg { fill: var(--muted) !important; color: var(--muted) !important; }
[data-testid="stNumberInputContainer"] button { background: transparent !important; }
[role="listbox"], [role="option"], [data-testid="stSelectboxVirtualDropdown"] { background: var(--pop) !important; color: var(--text) !important; }
[role="option"]:hover, [role="option"][aria-selected="true"] { background: var(--accent_soft) !important; }
[data-testid="stSlider"] *, [data-testid="stSliderThumbValue"], [data-testid="stSliderTickBar"] * { color: var(--text) !important; }
[data-testid="stSliderTickBar"] * { color: var(--muted) !important; }
[data-testid="stCheckbox"] *, [data-testid="stToggle"] *, [data-testid="stRadio"] * { color: var(--text) !important; }
[data-testid="stAlert"] { border-radius: 14px; }
[data-testid="stCode"], [data-testid="stCode"] pre { background: var(--card) !important; border: 1px solid var(--card_border); border-radius: 14px; }
[data-testid="stCode"] code, [data-testid="stCode"] code span { color: var(--text) !important; background: transparent !important; }
[data-testid="stSlider"] [role="slider"] { background: var(--accent) !important; }

[data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button, [data-testid="stLinkButton"] a {
  background: linear-gradient(135deg, var(--accent), var(--accent2)); color: #fff !important; border: 0; border-radius: 999px; font-weight: 600;
  padding: 0.45rem 1.1rem; box-shadow: 0 10px 24px -10px var(--accent), inset 0 1px 0 rgba(255,255,255,0.35); transition: transform 0.2s, box-shadow 0.2s, filter 0.2s;
}
[data-testid="stButton"] button p, [data-testid="stFormSubmitButton"] button p, [data-testid="stLinkButton"] a p { color: #fff !important; }
[data-testid="stButton"] button:hover, [data-testid="stFormSubmitButton"] button:hover, [data-testid="stLinkButton"] a:hover { transform: translateY(-1px); filter: brightness(1.06); box-shadow: 0 14px 28px -10px var(--accent); }

[role="tablist"] { gap: 4px; padding: 5px; width: fit-content; max-width: 100%; border-radius: 999px; background: var(--card); border: 1px solid var(--card_border); backdrop-filter: blur(16px); box-shadow: var(--shadow); }
[data-testid="stTab"] { border-radius: 999px !important; padding: 0.45rem 1.05rem !important; color: var(--muted) !important; transition: background 0.25s, color 0.25s; }
[data-testid="stTab"] p, [data-testid="stTab"] div { font-weight: 600; font-size: 0.86rem; color: inherit !important; }
[data-testid="stTab"][aria-selected="true"] { background: linear-gradient(135deg, var(--accent), var(--accent2)); color: #fff !important; box-shadow: 0 8px 20px -8px var(--accent); }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"], [data-testid="stTabHighlight"], [data-testid="stTabBorder"], .react-aria-SelectionIndicator, [role="tablist"]::after { display: none !important; }
[data-testid="stTabs"] > div:first-child { overflow: visible; }

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-thumb { background: var(--line); border-radius: 8px; }

/* brand bar */
.brand { display: flex; align-items: center; gap: 12px; }
.brandbar { display: flex; align-items: center; flex-wrap: wrap; gap: 14px 26px; }
.mkt { display: inline-flex; align-items: center; gap: 9px; padding: 7px 14px; border-radius: 999px; background: var(--card); border: 1px solid var(--card_border); backdrop-filter: blur(12px); font-size: 0.8rem; }
.mkt b { font-weight: 650; }
.mkt span { color: var(--muted); }
.mkt .md { width: 9px; height: 9px; border-radius: 50%; flex: none; background: var(--down); box-shadow: 0 0 0 3px rgba(var(--down_rgb), 0.18); }
.mkt.open .md { background: var(--up); box-shadow: 0 0 0 3px rgba(var(--up_rgb), 0.2); animation: pulse 2s ease-in-out infinite; }
.mkt.pre .md { background: #f59e0b; box-shadow: 0 0 0 3px rgba(245,158,11,0.22); }
.mkt.open b { color: var(--up); } .mkt.closed b { color: var(--down); } .mkt.pre b { color: #d99100; }
.brand .mark { width: 56px; height: 56px; flex: none; filter: drop-shadow(0 8px 12px rgba(216,27,60,0.32)); }
.brand .mark svg { display: block; width: 100%; height: 100%; }
.brand .name { font-weight: 700; font-size: 1.35rem; letter-spacing: -0.01em; display: flex; align-items: baseline; gap: 10px; }
.brand .name .np { font-family: 'Noto Sans Devanagari', 'Inter', sans-serif; font-size: 0.95rem; font-weight: 600; color: #d81b3c; letter-spacing: 0; }
.av { position: relative; overflow: hidden; display: inline-grid; place-items: center; flex: none; border-radius: 50%; color: #fff; font-weight: 700; letter-spacing: 0.02em; box-shadow: inset 0 1px 0 rgba(255,255,255,0.35), 0 4px 10px -4px rgba(0,0,0,0.35); }
.av-img { position: absolute; inset: 0; width: 100%; height: 100%; box-sizing: border-box; padding: 11%; object-fit: contain; background: #fff; border-radius: 50%; }
.symrow { display: inline-flex; align-items: center; gap: 9px; }
.symcell { display: flex; align-items: center; gap: 10px; }
.stock-head .who-id { display: flex; align-items: center; gap: 16px; }
.brand .tag { font-size: 0.72rem; color: var(--muted); }

/* typography */
.hero { padding: 4px 0 18px; }
.hero h1 { font-size: clamp(1.7rem, 3vw, 2.5rem); font-weight: 700; letter-spacing: -0.03em; margin: 0 0 6px; line-height: 1.15; }
.hero h1 span { background: linear-gradient(120deg, var(--accent), var(--accent2)); -webkit-background-clip: text; background-clip: text; color: transparent; }
.hero p { color: var(--muted); max-width: 720px; margin: 0 0 12px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { font-size: 0.76rem; padding: 5px 12px; border-radius: 999px; background: var(--card); border: 1px solid var(--card_border); color: var(--muted); display: inline-flex; align-items: center; gap: 7px; backdrop-filter: blur(10px); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--up); box-shadow: 0 0 0 4px rgba(var(--up_rgb), 0.18); animation: pulse 2s ease-in-out infinite; }
@keyframes pulse { 50% { box-shadow: 0 0 0 8px rgba(var(--up_rgb), 0); } }
.sec { display: flex; align-items: baseline; gap: 10px; margin: 30px 0 12px; }
.sec h3 { font-size: 1.05rem; font-weight: 650; letter-spacing: -0.01em; margin: 0; }
.sec span { font-size: 0.78rem; color: var(--muted); }

/* glass cards */
.card {
  position: relative; background: var(--card); border: 1px solid var(--card_border); border-radius: 22px; padding: 16px 18px; height: 100%;
  backdrop-filter: blur(20px) saturate(170%); -webkit-backdrop-filter: blur(20px) saturate(170%);
  box-shadow: var(--shadow), inset 0 1px 0 var(--gloss); transition: transform 0.3s cubic-bezier(.2,.8,.2,1), box-shadow 0.3s;
}
.card:hover { transform: translateY(-3px); }
.card.flat:hover { transform: none; }
.card.stat { min-height: 124px; }
.label { font-size: 0.74rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }
.value { font-size: 1.45rem; font-weight: 700; letter-spacing: -0.02em; margin: 6px 0 2px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.value.xl { font-size: 1.9rem; }
.sub { font-size: 0.8rem; color: var(--muted); font-variant-numeric: tabular-nums; }
.up { color: var(--up); } .down { color: var(--down); } .flat { color: var(--muted); }
.pill { display: inline-flex; align-items: center; gap: 4px; padding: 2px 9px; border-radius: 999px; font-size: 0.78rem; font-weight: 600; font-variant-numeric: tabular-nums; }
.pill.up { background: rgba(var(--up_rgb), 0.14); } .pill.down { background: rgba(var(--down_rgb), 0.14); } .pill.flat { background: var(--line); }
.spark { position: absolute; right: 16px; top: 16px; width: 84px; height: 34px; display: flex; align-items: flex-end; gap: 3px; }
.spark i { flex: 1; border-radius: 3px; min-height: 3px; }

/* tables */
.tbl-wrap { overflow-x: auto; border-radius: 16px; }
.tbl { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 0.86rem; font-variant-numeric: tabular-nums; }
.tbl th { text-align: left; font-weight: 600; font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; padding: 8px 10px 10px; border-bottom: 1px solid var(--line); white-space: nowrap; position: sticky; top: 0; background: transparent; }
.tbl td { padding: 10px 10px; border-bottom: 1px solid var(--line); white-space: nowrap; }
.tbl tr:last-child td { border-bottom: 0; }
.tbl tbody tr:hover td { background: var(--accent_soft); }
.tbl .r { text-align: right; } .tbl th.r { text-align: right; }
.tbl .sym { font-weight: 650; color: var(--accent); }
.tbl .wrap { white-space: normal; min-width: 180px; }
.rng { display: inline-block; vertical-align: middle; position: relative; width: 70px; height: 6px; border-radius: 6px; background: var(--line); margin-right: 8px; }
.rng i { position: absolute; top: -3px; width: 12px; height: 12px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--accent2)); transform: translateX(-50%); box-shadow: 0 2px 8px -2px var(--accent); }
.bar { display: block; height: 4px; border-radius: 4px; margin-top: 4px; }

/* badges */
.badge { font-size: 0.72rem; font-weight: 600; padding: 3px 10px; border-radius: 999px; white-space: nowrap; }
.badge.open { color: var(--up); background: rgba(var(--up_rgb), 0.14); }
.badge.soon { color: #b7791f; background: rgba(245,158,11,0.16); }
.badge.closed { color: var(--muted); background: var(--line); }
.badge.bad { color: var(--down); background: rgba(var(--down_rgb), 0.14); }
.badge.accent { color: var(--accent); background: var(--accent_soft); }

/* issue categories: IPO is the solid, most prominent one */
.kind { --kc: var(--accent_rgb); font-size: 0.72rem; font-weight: 700; padding: 3px 10px; border-radius: 999px; white-space: nowrap; color: rgb(var(--kc)); background: rgba(var(--kc), 0.15); border: 1px solid rgba(var(--kc), 0.35); }
.kind.ipo { --kc: var(--k_ipo); color: #fff; background: linear-gradient(135deg, rgb(var(--kc)), rgba(var(--kc), 0.72)); border-color: transparent; box-shadow: 0 6px 14px -6px rgb(var(--kc)); }
.kind.local { --kc: var(--k_local); } .kind.right { --kc: var(--k_right); } .kind.fpo { --kc: var(--k_fpo); } .kind.mf { --kc: var(--k_mf); } .kind.deb { --kc: var(--k_deb); }
.card.kc { border-left: 4px solid rgb(var(--kc)); }
.card.kc.ipo { --kc: var(--k_ipo); } .card.kc.local { --kc: var(--k_local); } .card.kc.right { --kc: var(--k_right); } .card.kc.fpo { --kc: var(--k_fpo); } .card.kc.mf { --kc: var(--k_mf); } .card.kc.deb { --kc: var(--k_deb); }
.legend { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 4px 0 8px; }
.tbl .sym a { color: var(--accent); }
.tbl .nm { display: block; font-weight: 400; font-size: 0.74rem; color: var(--muted); max-width: 200px; overflow: hidden; text-overflow: ellipsis; }
.ipo-sym a { color: var(--text); }
.ipo-sym a:hover { color: var(--accent); }

/* breadth */
.breadth { display: flex; height: 12px; border-radius: 12px; overflow: hidden; gap: 3px; margin: 14px 0 10px; }
.breadth i { display: block; height: 100%; border-radius: 12px; }

/* heat tiles */
.heat { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.tile { border-radius: 20px; padding: 14px 16px; border: 1px solid var(--card_border); backdrop-filter: blur(14px); transition: transform 0.25s; box-shadow: inset 0 1px 0 var(--gloss); }
.tile:hover { transform: scale(1.03); }
.tile .t-name { font-size: 0.82rem; font-weight: 600; }
.tile .t-pct { font-size: 1.25rem; font-weight: 700; margin-top: 4px; }
.tile .t-val { font-size: 0.76rem; color: var(--muted); }

/* ipo + generic key/value */
.ipo-sym { font-size: 1.2rem; font-weight: 700; letter-spacing: -0.01em; }
.ipo-name { color: var(--muted); font-size: 0.85rem; margin: 2px 0 12px; min-height: 2.5em; }
.kv { display: flex; justify-content: space-between; gap: 10px; font-size: 0.82rem; padding: 6px 0; border-top: 1px solid var(--line); font-variant-numeric: tabular-nums; }
.kv span:first-child { color: var(--muted); } .kv span:last-child { text-align: right; font-weight: 500; }
.card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }

/* news */
.news-item { padding: 12px 6px; border-bottom: 1px solid var(--line); }
.news-item:last-child { border-bottom: 0; }
.news-item a.t { display: block; color: var(--text); font-weight: 550; line-height: 1.4; margin: 6px 0 2px; }
.news-item a.t:hover { color: var(--accent); text-decoration: none; }
.news-meta { font-size: 0.74rem; color: var(--muted); display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }

.empty { text-align: center; padding: 34px 10px; color: var(--muted); }
.empty .big { font-size: 1.05rem; font-weight: 650; color: var(--text); margin-bottom: 6px; }
.step { display: flex; gap: 12px; align-items: flex-start; padding: 8px 0; }
.step .n { flex: none; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; font-size: 0.76rem; font-weight: 700; color: #fff; background: linear-gradient(135deg, var(--accent), var(--accent2)); }
.disclaimer { font-size: 0.74rem; color: var(--muted); border-top: 1px solid var(--line); margin-top: 36px; padding-top: 14px; line-height: 1.6; }

/* stock page */
.stock-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 14px; padding: 4px 0 14px; }
.stock-head h1 { font-size: clamp(1.8rem, 3.2vw, 2.7rem); font-weight: 700; letter-spacing: -0.03em; margin: 0; line-height: 1.1; }
.stock-head .co { color: var(--muted); margin-top: 4px; }
.stock-head .px { text-align: right; }
.stock-head .px .big { font-size: clamp(1.8rem, 3vw, 2.5rem); font-weight: 700; letter-spacing: -0.03em; font-variant-numeric: tabular-nums; line-height: 1.1; }
.verdict { display: flex; flex-direction: column; gap: 10px; }
.verdict .rating { font-size: 2rem; font-weight: 750; letter-spacing: -0.03em; line-height: 1.1; }
.verdict .score { font-size: 0.8rem; color: var(--muted); font-variant-numeric: tabular-nums; }
.verdict p { margin: 0; font-size: 0.9rem; line-height: 1.55; }
.meter { position: relative; height: 10px; border-radius: 10px; margin: 6px 0 2px; background: linear-gradient(90deg, var(--down), #f5a524 50%, var(--up)); }
.meter i { position: absolute; top: -5px; width: 6px; height: 20px; border-radius: 4px; background: var(--text); transform: translateX(-50%); box-shadow: 0 0 0 3px var(--card_border); }
.meter-scale { display: flex; justify-content: space-between; font-size: 0.7rem; color: var(--muted); }
.warn { font-size: 0.82rem; padding: 8px 12px; border-radius: 12px; background: rgba(245,158,11,0.13); color: var(--text); margin-top: 6px; line-height: 1.5; }
.verdict .rating.flat { color: #d99100; }
.who { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 4px; }
.who > div { padding: 10px 12px; border-radius: 12px; background: var(--accent_soft); }
.who b { display: block; margin-top: 3px; font-size: 1rem; font-weight: 650; }
.who b.flat { color: #d99100; }
@media (max-width: 520px) { .who { grid-template-columns: 1fr; } }
.factor-score { display: inline-block; position: relative; width: 90px; height: 6px; border-radius: 6px; background: var(--line); vertical-align: middle; }
.factor-score i { position: absolute; top: 0; height: 100%; border-radius: 6px; }
.tbl td.detail { white-space: normal; min-width: 320px; color: var(--muted); }
.lvl { display: flex; justify-content: space-between; padding: 7px 0; border-top: 1px solid var(--line); font-size: 0.86rem; font-variant-numeric: tabular-nums; }
.lvl:first-of-type { border-top: 0; }
.lvl span:first-child { color: var(--muted); }
.lvl b { font-weight: 650; }
.note { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; padding: 12px 18px 14px; border-radius: 16px; background: var(--card); border: 1px solid var(--card_border); }
.note p { margin: 5px 0 0; font-size: 0.84rem; line-height: 1.6; }
.card.insight { border-left: 4px solid var(--line); }
.card.insight.up { border-left-color: var(--up); } .card.insight.down { border-left-color: var(--down); } .card.insight.flat { border-left-color: #d99100; }
.card.insight p { margin: 8px 0 0; font-size: 0.88rem; line-height: 1.6; }
.pts { margin: 8px 0 0; padding-left: 18px; font-size: 0.85rem; line-height: 1.6; }
.pts li { margin-bottom: 6px; }
.pts.up li::marker { color: var(--up); } .pts.down li::marker { color: var(--down); }
@media (max-width: 820px) { .note { grid-template-columns: 1fr; gap: 10px; } }
"""


def init_mode() -> None:
    if "dark" not in st.session_state:
        st.session_state["dark"] = st.query_params.get("theme") == "dark"


def is_dark() -> bool:
    return bool(st.session_state.get("dark", False))


def palette() -> dict[str, str]:
    return PALETTES["dark" if is_dark() else "light"]


def inject_css() -> None:
    variables = "".join(f"--{k}: {v};" for k, v in palette().items())
    st.markdown(f"<style>:root {{{variables}}}{BASE_CSS}</style>", unsafe_allow_html=True)


def _sync_query() -> None:
    if st.session_state.get("dark"):
        st.query_params["theme"] = "dark"
    elif "theme" in st.query_params:
        del st.query_params["theme"]


# Nepal's crimson and blue, two Himalayan peaks, a rising line and the flag's sun, kept as plain shapes so it survives HTML sanitising.
LOGO_SVG = (
    '<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Share Gyan">'
    '<rect x="2" y="2" width="44" height="44" rx="13" fill="#d81b3c" stroke="#003893" stroke-width="3"/>'
    '<polygon points="7,37 18,17 24,27 31,12 41,37" fill="#ffffff"/>'
    '<polygon points="31,12 36.4,22 31,20.5 26.6,22" fill="#d9e3ff"/>'
    '<polyline points="9,36 19,29 26,32 39,20" fill="none" stroke="#003893" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="39" cy="20" r="2.6" fill="#003893"/>'
    '<circle cx="12" cy="11" r="3" fill="#ffffff"/>'
    "</svg>"
)
# st.html strips inline <svg>, so the header embeds the logo as an image data URI instead.
LOGO_URI = "data:image/svg+xml;base64," + base64.b64encode(LOGO_SVG.encode()).decode()


def market_chip(status: dict) -> str:
    return (
        f'<span class="mkt {esc(status["state"])}"><i class="md"></i><b>{esc(status["label"])}</b>'
        f'<span>{esc(status["detail"])} · Nepal time</span></span>'
    )


def header(subtitle: str, status: dict | None = None) -> None:
    left, refresh, mode = st.columns([12, 1, 2], vertical_alignment="center")
    with left:
        chip = market_chip(status) if status else ""
        render(
            f'<div class="brandbar"><div class="brand"><img class="mark" src="{LOGO_URI}" alt="Share Gyan logo"><div><div class="name">Share Gyan <span class="np">शेयर ज्ञान</span></div>'
            f'<div class="tag">{esc(subtitle)}</div></div></div>{chip}</div>'
        )
    with refresh:
        if st.button(":material/refresh:", help="Re-scrape the sources now", key="refresh"):
            st.cache_data.clear()
            st.rerun()
    with mode:
        st.toggle("Dark", key="dark", help="Switch between light and dark", on_change=_sync_query)


def render(markup: str) -> None:
    st.html(markup)


def show_chart(chart) -> None:
    st.altair_chart(chart, theme=None, width="stretch")


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def num(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}"


def nepali_amount(value: float) -> str:
    for threshold, unit in ((1e11, "Kharba"), (1e9, "Arba"), (1e7, "Crore"), (1e5, "Lakh")):
        if abs(value) >= threshold:
            return f"{value / threshold:,.2f} {unit}"
    return f"{value:,.0f}"


def tone(value: float) -> str:
    return "up" if value > 0 else "down" if value < 0 else "flat"


def arrow(value: float) -> str:
    return "▲" if value > 0 else "▼" if value < 0 else "•"


def pill(change: float, pct: float | None = None, digits: int = 2) -> str:
    text = f"{abs(change):,.{digits}f}" if pct is None else f"{abs(change):,.{digits}f} ({abs(pct):.2f}%)"
    return f'<span class="pill {tone(change)}">{arrow(change)} {text}</span>'


def pct_pill(pct: float) -> str:
    return f'<span class="pill {tone(pct)}">{arrow(pct)} {abs(pct):.2f}%</span>'


def tag(text: str, kind: str = "accent") -> str:
    return f'<span class="badge {kind}">{esc(text)}</span>'


def status_tag(status: str) -> str:
    key = status.lower()
    kind = "open" if key == "open" else "soon" if ("soon" in key or "upcoming" in key) else "closed"
    return tag(status, kind)


def allotment_tag(status: str) -> str:
    key = status.lower()
    kind = "open" if key == "allotted" else "bad" if key == "not allotted" or "reject" in key else "soon"
    return tag(status, kind)


KIND_CLASS = {"IPO": "ipo", "IPO (Local)": "local", "Right": "right", "FPO": "fpo", "Mutual fund": "mf", "Debenture": "deb"}


def kind_for(text: str) -> str:
    """Map free text such as MeroShare's share type onto one of KIND_CLASS."""
    key = (text or "").lower()
    if "right" in key:
        return "Right"
    if "fpo" in key:
        return "FPO"
    if "mutual" in key or key == "mf":
        return "Mutual fund"
    if "debenture" in key or "bond" in key:
        return "Debenture"
    if "local" in key:
        return "IPO (Local)"
    return "IPO" if "ipo" in key else text


def kind_tag(kind: str) -> str:
    return f'<span class="kind {KIND_CLASS.get(kind, "")}">{esc(kind)}</span>'


def kind_legend() -> str:
    return f'<div class="legend">{"".join(kind_tag(k) for k in KIND_CLASS)}</div>'


def stock_url(symbol: str) -> str:
    # Relative so it resolves beside the current page, including under a base path.
    theme = "&theme=dark" if is_dark() else ""
    return f"stock?symbol={quote(symbol, safe='')}{theme}"


def symbol_link(symbol: str) -> str:
    return f'<a href="{esc(stock_url(symbol))}" target="_self" title="Open {esc(symbol)} analysis">{esc(symbol)}</a>'


def avatar(symbol: str, size: int = 26) -> str:
    """Company logo when one is known, over a letter badge that shows if the image is missing or fails to load."""
    from share_gyan import data  # imported late: data does not depend on theme, but theme is imported first

    hue = sum(ord(c) * (i + 3) for i, c in enumerate(symbol)) * 37 % 360
    letters = "".join(c for c in symbol if c.isalnum())[:2].upper() or "?"
    logo = data.logos().get(symbol.upper())
    img = f'<img class="av-img" src="{esc(logo)}" alt="" loading="lazy" referrerpolicy="no-referrer">' if logo else ""
    return (
        f'<span class="av" style="width:{size}px;height:{size}px;font-size:{size * 0.38:.1f}px;'
        f'background:linear-gradient(135deg,hsl({hue} 68% 52%),hsl({(hue + 35) % 360} 70% 40%))">{esc(letters)}{img}</span>'
    )


def symbol_badge(symbol: str, size: int = 26) -> str:
    return f'<span class="symrow">{avatar(symbol, size)}{symbol_link(symbol)}</span>'


# --------------------------------------------------------------------------- #
# Components
# --------------------------------------------------------------------------- #


def hero(title: str, accent_word: str = "", subtitle: str = "", chips: Sequence[str] = ()) -> str:
    heading = f'{esc(title)} <span>{esc(accent_word)}</span>' if accent_word else esc(title)
    sub = f"<p>{esc(subtitle)}</p>" if subtitle else ""
    chip_html = f'<div class="chips">{"".join(f"<span class=chip>{c}</span>" for c in chips)}</div>' if chips else ""
    return f'<div class="hero"><h1>{heading}</h1>{sub}{chip_html}</div>'


def live_chip(text: str) -> str:
    return f'<span class="dot"></span>{esc(text)}'


def section(title: str, sub: str = "") -> str:
    meta = f"<span>{esc(sub)}</span>" if sub else ""
    return f'<div class="sec"><h3>{esc(title)}</h3>{meta}</div>'


def sparkline(values: Sequence[float], up: bool) -> str:
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    color = "var(--up)" if up else "var(--down)"
    last = max(len(values) - 1, 1)
    bars = "".join(
        f'<i style="height:{20 + (v - lo) / span * 80:.0f}%;background:{color};opacity:{0.3 + 0.7 * i / last:.2f}"></i>'
        for i, v in enumerate(values)
    )
    return f'<div class="spark">{bars}</div>'


def stat_card(label: str, value: str, change: float | None = None, pct: float | None = None, note: str = "",
              spark: Sequence[float] | None = None, xl: bool = False) -> str:
    delta = f'<div class="sub">{pill(change, pct)}</div>' if change is not None else ""
    note_html = f'<div class="sub">{esc(note)}</div>' if note else ""
    spark_html = sparkline(spark, (change or 0) >= 0) if spark else ""
    return (
        f'<div class="card stat"><div class="label">{esc(label)}</div>'
        f'<div class="value{" xl" if xl else ""}">{esc(value)}</div>{delta}{note_html}{spark_html}</div>'
    )


def breadth_card(advanced: int, declined: int, unchanged: int) -> str:
    total = max(advanced + declined + unchanged, 1)
    mood = "Bullish" if advanced > declined * 1.3 else "Bearish" if declined > advanced * 1.3 else "Mixed"
    cls = {"Bullish": "up", "Bearish": "down"}.get(mood, "flat")
    seg = lambda n, color: f'<i style="width:{n / total * 100:.1f}%;background:{color}"></i>'  # noqa: E731
    return (
        f'<div class="card"><div class="label">Market breadth</div><div class="value {cls}">{mood}</div>'
        f'<div class="breadth">{seg(advanced, "var(--up)")}{seg(unchanged, "var(--line)")}{seg(declined, "var(--down)")}</div>'
        f'<div class="sub"><span class="up">{advanced} advanced</span> · {unchanged} flat · <span class="down">{declined} declined</span></div></div>'
    )


def _cell(kind: str, value, row: pd.Series) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return "—"
    if kind == "sym":
        name = row.get("Company")
        sub = f'<span class="nm" title="{esc(name)}">{esc(name)}</span>' if isinstance(name, str) and name else ""
        return f'<div class="symcell">{avatar(value)}<div>{symbol_link(value)}{sub}</div></div>'
    if kind == "symlink":
        return symbol_badge(value, 24)
    if kind == "html":
        return str(value)  # callers pass markup built with esc()/tag()
    if kind == "kind":
        return kind_tag(str(value))
    if kind == "allot":
        return allotment_tag(str(value))
    if kind == "num":
        return num(value)
    if kind == "int":
        return f"{value:,.0f}"
    if kind == "money":
        return nepali_amount(value)
    if kind == "chg":
        return f'<span class="{tone(value)}">{value:+,.2f}</span>'
    if kind == "pct":
        return pct_pill(value)
    if kind == "date":
        return pd.Timestamp(value).strftime("%d %b %Y")
    if kind == "status":
        return status_tag(str(value))
    if kind == "range":
        return f'<span class="rng"><i style="left:{value:.0f}%"></i></span>{value:.0f}%'
    if kind == "wrap":
        return f'<div class="wrap">{esc(value)}</div>'
    return esc(value)


_RIGHT = {"num", "int", "money", "chg", "pct", "range"}


def data_table(df: pd.DataFrame, cols: Sequence[tuple[str, str, str]], empty: str = "Nothing to show.") -> str:
    """Render selected DataFrame columns as an HTML table. cols = (column, header, kind)."""
    if df is None or df.empty:
        return empty_state("No data", empty)
    head = "".join(f'<th class="{"r" if k in _RIGHT else ""}">{esc(h)}</th>' for _, h, k in cols)
    body = []
    for _, row in df.iterrows():
        cells = "".join(
            f'<td class="{"r " if k in _RIGHT else ""}{"sym" if k in ("sym", "symlink") else ""}">{_cell(k, row[c], row)}</td>' for c, _, k in cols
        )
        body.append(f"<tr>{cells}</tr>")
    return f'<div class="card flat" style="padding:8px 10px"><div class="tbl-wrap"><table class="tbl"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div></div>'


def mover_table(df: pd.DataFrame, metric: str = "pct") -> str:
    last = ("Turnover", "Turnover", "money") if metric == "turnover" else ("% Change", "Change", "pct")
    return data_table(df, [("Symbol", "Symbol", "sym"), ("LTP", "LTP", "num"), last])


def heat_tiles(df: pd.DataFrame) -> str:
    p = palette()
    tiles = []
    for _, r in df.sort_values("% Change", ascending=False).iterrows():
        pct = r["% Change"]
        rgb = p["up_rgb"] if pct >= 0 else p["down_rgb"]
        alpha = min(0.10 + abs(pct) / 1.6 * 0.30, 0.42)
        tiles.append(
            f'<div class="tile" style="background:linear-gradient(145deg, rgba({rgb},{alpha:.2f}), var(--card))">'
            f'<div class="t-name">{esc(r["Sector"])}</div><div class="t-pct {tone(pct)}">{arrow(pct)} {abs(pct):.2f}%</div>'
            f'<div class="t-val">{num(r["Index"])}</div></div>'
        )
    return f'<div class="heat">{"".join(tiles)}</div>'


def news_list(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return empty_state("No stories", "Nothing matches right now.")
    items = []
    for _, r in df.iterrows():
        when = pd.Timestamp(r["Date"]).strftime("%d %b %Y")
        items.append(
            f'<div class="news-item"><div class="news-meta">{tag(r["Category"])}<span>{when}</span><span>{esc(r["Source"])}</span></div>'
            f'<a class="t" href="{esc(r["Url"])}" target="_blank" rel="noopener noreferrer">{esc(r["Title"])}</a></div>'
        )
    return f'<div class="card flat" style="padding:6px 14px">{"".join(items)}</div>'


def ipo_card(symbol: str, company: str, status: str, rows: Sequence[tuple[str, str]], kind: str | None = None) -> str:
    kv = "".join(f'<div class="kv"><span>{esc(k)}</span><span>{esc(v)}</span></div>' for k, v in rows)
    kc = f" kc {KIND_CLASS[kind]}" if kind in KIND_CLASS else ""
    badge = kind_tag(kind) if kind else ""
    return (
        f'<div class="card{kc}"><div class="card-head"><div class="ipo-sym">{symbol_badge(symbol, 32)}</div>{status_tag(status)}</div>'
        f'<div style="margin:6px 0 4px">{badge}</div><div class="ipo-name">{esc(company)}</div>{kv}</div>'
    )


def empty_state(title: str, message: str) -> str:
    return f'<div class="card flat empty"><div class="big">{esc(title)}</div><div>{esc(message)}</div></div>'


def disclaimer(fetched_at=None) -> str:
    stamp = f" Last scraped {fetched_at:%d %b %Y, %H:%M}." if fetched_at else ""
    return (
        '<div class="disclaimer">Data is scraped live from ShareSansar and Merolagani and cached for a few minutes. Company logos are loaded from Arthakendra and belong to their owners.'
        f"{stamp} For information only, not investment advice. Verify prices, dates and IPO results on the official NEPSE, SEBON and CDSC portals.</div>"
    )


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #


def themed(chart):
    p = palette()
    return (
        chart.configure_view(stroke=None)
        .configure_axis(labelColor=p["muted"], titleColor=p["muted"], gridColor=p["line"], domainColor=p["line"], tickColor=p["line"], labelFontSize=12, titleFontSize=12)
        .configure_legend(labelColor=p["muted"], titleColor=p["muted"])
    )


def style_chart(chart, height: int = 320):
    return themed(chart.properties(height=height, background="transparent"))


def area_gradient() -> alt.Gradient:
    rgb = palette()["accent_rgb"]
    return alt.Gradient(
        gradient="linear",
        stops=[alt.GradientStop(color=f"rgba({rgb},0.38)", offset=0), alt.GradientStop(color=f"rgba({rgb},0)", offset=1)],
        x1=1, x2=1, y1=1, y2=0,
    )
