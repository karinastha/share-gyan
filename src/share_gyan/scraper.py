"""Live scrapers for ShareSansar and Merolagani.

Share Gyan Nepal renders its data client-side through a private, header-gated API,
so it is linked from the app but not scraped.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SS = "https://www.sharesansar.com"
ML = "https://eng.merolagani.com"

_SESSION = requests.Session()
_SESSION.headers.update(
    {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
)
_SESSION.mount("https://", HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.4, status_forcelist=(500, 502, 503, 504))))
_TIMEOUT = (5, 20)


def _get(url: str, params: dict | None = None, ajax: bool = False) -> requests.Response:
    headers = {"X-Requested-With": "XMLHttpRequest"} if ajax else None
    resp = _SESSION.get(url, params=params, headers=headers, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp


def _soup(url: str, params: dict | None = None) -> BeautifulSoup:
    return BeautifulSoup(_get(url, params).text, "lxml")


def num(text: object) -> float | None:
    cleaned = re.sub(r"[^\d.\-]", "", str(text or ""))
    try:
        return float(cleaned)
    except ValueError:
        return None


def _text(node: Tag | None) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)) if node else ""


def _table(table: Tag) -> pd.DataFrame:
    rows = [[_text(c) for c in tr.find_all(["th", "td"])] for tr in table.find_all("tr")]
    rows = [r for r in rows if r]
    if not rows:
        return pd.DataFrame()
    head, body = rows[0], [r for r in rows[1:] if len(r) == len(rows[0])]
    return pd.DataFrame(body, columns=head)


def _sections(soup: BeautifulSoup) -> dict[str, Tag]:
    """Map the nearest preceding heading text (lower-cased) to each table."""
    out: dict[str, Tag] = {}
    for table in soup.find_all("table"):
        heading = table.find_previous(["h2", "h3", "h4"])
        if heading:
            out.setdefault(_text(heading).lower(), table)
    return out


def _strip_link(html: str) -> str:
    return BeautifulSoup(html or "", "lxml").get_text(" ", strip=True)


def _href(html: str) -> str:
    a = BeautifulSoup(html or "", "lxml").find("a")
    return a.get("href", "") if a else ""


def company_url(symbol: str) -> str:
    return f"{SS}/company/{symbol.lower()}"


AK = "https://arthakendra.com"


def sharesansar_company_info(symbol: str) -> dict[str, str]:
    """Basic profile rows from a ShareSansar company page, which exists even for scrips that are not trading yet."""
    soup = _soup(company_url(symbol))
    info: dict[str, str] = {}
    for tr in soup.find_all("tr"):
        cells = [_text(c) for c in tr.find_all(["th", "td"])]
        if len(cells) == 2 and cells[0] and len(cells[0]) < 40 and cells[1] not in ("", "-"):
            info.setdefault(cells[0], cells[1])
        if len(info) >= 12:
            break
    if not info.get("Name"):
        raise ValueError(f"{symbol} not found on ShareSansar")
    return info


def arthakendra_logos() -> dict[str, str]:
    """Symbol to company logo URL, read from the public Arthakendra listed-securities page (one request)."""
    html = _get(f"{AK}/stock-market/listed-securities").text
    logos: dict[str, str] = {}
    for m in re.finditer(r'<a href="/stock-market/company/([A-Za-z0-9]+)"[^>]*>(.*?)</a>', html, re.S):
        img = re.search(r'<img src="(https://cdn\.arthakendra\.com/sharehub/[^"]+)"', m.group(2))
        if img:
            logos.setdefault(m.group(1).upper(), img.group(1))
    if not logos:
        raise ValueError("No logos found on Arthakendra")
    return logos


def _as_of(soup: BeautifulSoup) -> str:
    m = re.search(r"As of\s*:?\s*(\d{4}-\d{2}-\d{2})", soup.get_text(" "))
    return m.group(1) if m else ""


# --------------------------------------------------------------------------- #
# ShareSansar
# --------------------------------------------------------------------------- #


def sharesansar_market() -> dict:
    soup = _soup(f"{SS}/market")
    secs = _sections(soup)

    idx = _table(secs["indices"])
    indices = pd.DataFrame(
        {
            "Name": idx["Index"].str.replace(" Index", "", regex=False),
            "Open": idx["Open"].map(num),
            "High": idx["High"].map(num),
            "Low": idx["Low"].map(num),
            "Close": idx["Close"].map(num),
            "Change": idx["Point Change"].map(num),
            "Pct": idx["% Change"].map(num),
            "Turnover": idx["Turnover"].map(num),
        }
    )

    fx = _table(secs["foreign exchange"])
    forex = pd.DataFrame({"Currency": fx["Currency"], "Buy": fx["Buy"].map(num), "Sell": fx["Sell"].map(num)})

    bullion = []
    for tr in secs["bullion price"].find_all("tr"):
        txt = _text(tr)
        m = re.match(r"(.+?)\s+Rs\.?\s*([\d,]+)/tola\s*([+-])?\s*\(?\s*([\d,]+)", txt)
        if m:
            change = num(m.group(4)) or 0.0
            bullion.append({"Name": m.group(1), "Price": num(m.group(2)), "Change": -change if m.group(3) == "-" else change})

    return {
        "as_of": _as_of(soup),
        "indices": indices,
        "forex": forex,
        "bullion": pd.DataFrame(bullion),
    }


def sharesansar_sectors() -> pd.DataFrame:
    secs = _sections(_soup(SS))
    raw = _table(secs["sub indices"])
    name = raw.iloc[:, 0].str.replace(r"\s*(SubIndex|Index)$", "", regex=True)
    df = pd.DataFrame(
        {
            "Sector": name,
            "Open": raw["Open"].map(num),
            "High": raw["High"].map(num),
            "Low": raw["Low"].map(num),
            "Index": raw["Close"].map(num),
            "Turnover": raw["Turnover"].map(num),
            "Change": raw["Point"].map(num),
            "% Change": raw["% Change"].map(num),
            "52W High": raw["52 Week High"].map(num),
            "52W Low": raw["52 Week Low"].map(num),
        }
    )
    span = (df["52W High"] - df["52W Low"]).replace(0, pd.NA)
    df["52W Position"] = ((df["Index"] - df["52W Low"]) / span * 100).astype(float).round(1)
    return df


def sharesansar_mergers() -> pd.DataFrame:
    secs = _sections(_soup(SS))
    raw = _table(secs["mergers & acquisitions"])
    return raw.drop(columns=[c for c in raw.columns if c in ("S.N.", "Trading")], errors="ignore")


def sharesansar_board() -> tuple[str, pd.DataFrame]:
    soup = _soup(f"{SS}/today-share-price")
    raw = _table(soup.find("table", id="headFixed"))
    df = pd.DataFrame(
        {
            "Symbol": raw["Symbol"],
            "Open": raw["Open"].map(num),
            "High": raw["High"].map(num),
            "Low": raw["Low"].map(num),
            "LTP": raw["LTP"].map(num),
            "VWAP": raw["VWAP"].map(num),
            "Volume": raw["Vol"].map(num),
            "Prev Close": raw["Prev. Close"].map(num),
            "Turnover": raw["Turnover"].map(num),
            "Trades": raw["Trans."].map(num),
            "Change": raw["Diff"].map(num),
            "% Change": raw["Diff %"].map(num),
            "52W High": raw["52 Weeks High"].map(num),
            "52W Low": raw["52 Weeks Low"].map(num),
        }
    )
    return _as_of(soup), df.dropna(subset=["LTP"]).reset_index(drop=True)


def _datatable(path: str, **params) -> list[dict]:
    payload = _get(f"{SS}/{path}", {"draw": 1, "start": 0, **params}, ajax=True).json()
    return payload.get("data", [])


def _status(opening: str, closing: str) -> str:
    if not opening:
        return "Coming soon"
    today = date.today().isoformat()
    if today < opening:
        return "Upcoming"
    if today <= (closing or opening):
        return "Open"
    return "Closed"


# Issue-type codes used by ShareSansar's existing-issues tabs.
ISSUE_TYPES = {"IPO": 1, "IPO (Local)": 5, "Right": 3, "FPO": 2, "Mutual fund": 4, "Debenture": 7}


def sharesansar_issues(kind: str, length: int = 50) -> pd.DataFrame:
    rows = []
    for r in _datatable("existing-issues", length=length, type=ISSUE_TYPES[kind]):
        opening, closing = r.get("opening_date") or "", r.get("closing_date") or ""
        rows.append(
            {
                "Symbol": _strip_link(r["company"]["symbol"]),
                "Company": _strip_link(r["company"]["companyname"]),
                "Url": _href(r["company"]["symbol"]),
                "Units": num(r.get("total_units")),
                "Price": num(r.get("issue_price")),
                "Opens": pd.to_datetime(opening or None),
                "Closes": pd.to_datetime(closing or None),
                "Allotment": pd.to_datetime(r.get("final_date") or None),
                "Listing": pd.to_datetime(r.get("listing_date") or None),
                "Manager": r.get("issue_manager") or "",
                "Status": _status(opening, closing),
            }
        )
    return pd.DataFrame(rows)


def sharesansar_all_issues() -> dict[str, pd.DataFrame]:
    def load(kind: str) -> pd.DataFrame:
        try:
            return sharesansar_issues(kind)
        except Exception:
            if kind == "IPO":
                raise
            return pd.DataFrame()

    with ThreadPoolExecutor(max_workers=6) as pool:
        return dict(zip(ISSUE_TYPES, pool.map(load, ISSUE_TYPES)))


def sharesansar_upcoming(length: int = 50) -> pd.DataFrame:
    rows = []
    for r in _datatable("upcoming-issue", length=length, type=1):
        rows.append(
            {
                "Symbol": _strip_link(r["company"]["symbol"]),
                "Company": _strip_link(r["company"]["companyname"]),
                "Url": _href(r["company"]["symbol"]),
                "Sector": (r["company"].get("sector") or {}).get("sectorname", ""),
                "Units": num(r.get("total_units")),
                "Amount": num(r.get("amount")),
                "Manager": r.get("issue_manager") or "",
                "Applied": pd.to_datetime(r.get("application_date") or None),
                "SEBON": pd.to_datetime(r.get("date_sebon") or None),
            }
        )
    return pd.DataFrame(rows)


def sharesansar_companies() -> pd.DataFrame:
    """Symbol, full name, sector and page link for every listed security."""
    soup = _soup(f"{SS}/company-list")
    sectors = {o["value"]: _text(o) for o in soup.select("select#sector option") if o.get("value")}

    def load(sector_id: str) -> list[dict]:
        out, start = [], 0
        while True:
            payload = _get(f"{SS}/company-list", {"draw": 1, "start": start, "length": 50, "sector": sector_id}, ajax=True).json()
            rows = payload.get("data", [])
            for r in rows:
                symbol = _strip_link(r["symbol"])
                out.append(
                    {"Symbol": symbol, "Company": _strip_link(r["companyname"]), "Sector": sectors[sector_id], "Url": _href(r["symbol"]) or company_url(symbol)}
                )
            start += 50
            if not rows or start >= payload.get("recordsTotal", 0):
                return out

    with ThreadPoolExecutor(max_workers=6) as pool:
        parts = pool.map(load, sectors)
    df = pd.DataFrame([row for part in parts for row in part])
    return df.drop_duplicates("Symbol").reset_index(drop=True)


def sharesansar_dividends(length: int = 40) -> pd.DataFrame:
    rows = []
    for r in _datatable("proposed-dividend", length=length, type="LATEST", duration=""):
        rows.append(
            {
                "Symbol": _strip_link(r["symbol"]),
                "Company": _strip_link(r["companyname"]),
                "Url": _href(r["symbol"]),
                "Bonus %": num(r.get("bonus_share")),
                "Cash %": num(r.get("cash_dividend")),
                "Total %": num(r.get("total_dividend")),
                "LTP": num(r.get("close")),
                "Book close": re.sub(r"\s*\[.*?\]", "", r.get("bookclose_date") or "").strip(),
                "Year": r.get("year") or "",
                "Published": pd.to_datetime(r.get("published_date") or None),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["Cash Yield %"] = (df["Cash %"] / df["LTP"] * 100).round(2)
    return df.sort_values("Published", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Merolagani
# --------------------------------------------------------------------------- #


_HISTORY_FIELDS = ["published_date", "open", "high", "low", "close", "per_change", "traded_quantity", "traded_amount"]


def sharesansar_stock_history(symbol: str, sessions: int = 500) -> pd.DataFrame:
    """Unadjusted daily OHLC, shares traded and turnover for one scrip, as actually traded."""
    page_url = company_url(symbol)
    soup = _soup(page_url)
    token, company_id = soup.find("meta", attrs={"name": "_token"}), soup.find(id="companyid")
    if not token or not company_id:
        raise ValueError(f"No ShareSansar price history for {symbol}")
    headers = {"X-CSRF-Token": token["content"], "X-Requested-With": "XMLHttpRequest", "Referer": page_url}

    def page(start: int) -> list[dict]:
        form = {"company": _text(company_id), "draw": 1, "start": start, "length": 50, "search[value]": "", "search[regex]": "false", "order[0][column]": 0, "order[0][dir]": "desc"}
        for i, field in enumerate(_HISTORY_FIELDS):
            form.update({f"columns[{i}][data]": field, f"columns[{i}][name]": "", f"columns[{i}][searchable]": "true", f"columns[{i}][orderable]": "false"})
        resp = _SESSION.post(f"{SS}/company-price-history", data=form, headers=headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("data", [])

    with ThreadPoolExecutor(max_workers=5) as pool:
        rows = [r for part in pool.map(page, range(0, sessions, 50)) for r in part]
    if not rows:
        raise ValueError(f"No ShareSansar price history for {symbol}")
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime([r["published_date"] for r in rows]),
            "Open": [num(r["open"]) for r in rows],
            "High": [num(r["high"]) for r in rows],
            "Low": [num(r["low"]) for r in rows],
            "Close": [num(r["close"]) for r in rows],
            "Volume": [num(r["traded_quantity"]) for r in rows],
            "Turnover": [num(r["traded_amount"]) for r in rows],
        }
    )
    return df.dropna(subset=["Open", "High", "Low", "Close"]).drop_duplicates("Date").sort_values("Date").reset_index(drop=True)


def _chart(symbol: str, days: int) -> pd.DataFrame:
    now = int(time.time())
    start = now - days * 86400
    params = {
        "type": "get_advanced_chart",
        "symbol": symbol,
        "resolution": "1D",
        "rangeStartDate": start,
        "rangeEndDate": now,
        "from": start,
        "to": now,
        "isAdjust": 1,
    }
    d = json.loads(_get(f"{ML}/handlers/TechnicalChartHandler.ashx", params).text)
    if "t" not in d:
        raise ValueError(f"No price history for {symbol}")
    df = pd.DataFrame({"Date": pd.to_datetime(d["t"], unit="s").normalize(), "Open": d["o"], "High": d["h"], "Low": d["l"], "Close": d["c"], "V": d["v"]})
    return df.drop_duplicates("Date").reset_index(drop=True)


def merolagani_history(days: int = 420) -> pd.DataFrame:
    return _chart("NEPSE", days).rename(columns={"V": "Turnover"})


def merolagani_stock_history(symbol: str, days: int = 800) -> pd.DataFrame:
    """Daily OHLC and traded volume (shares) for one scrip."""
    return _chart(symbol, days).rename(columns={"V": "Volume"})


def _lead_num(text: str) -> float | None:
    m = re.search(r"-?\d[\d,]*\.?\d*", text or "")
    return float(m.group().replace(",", "")) if m else None


def _fy(text: str) -> str:
    m = re.search(r"FY:\s*(\d+[-/]\d+)", text or "")
    return m.group(1) if m else ""


def _cash_dividends(soup: BeautifulSoup) -> pd.DataFrame:
    panel = soup.find("tr", id="dividend-panel")
    rows = []
    for tr in panel.find_all("tr") if panel else []:
        text = _text(tr)
        m = re.search(r"(-?\d[\d.]*)\s*%", text)
        if m and _fy(text):
            rows.append({"Fiscal year": _fy(text), "Cash %": float(m.group(1))})
    if not rows:
        return pd.DataFrame(columns=["Fiscal year", "Cash %"])
    return pd.DataFrame(rows).groupby("Fiscal year", as_index=False)["Cash %"].sum().sort_values("Fiscal year").reset_index(drop=True)


def merolagani_company(symbol: str) -> dict:
    """Fundamentals and payout history from a Merolagani company page."""
    soup = _soup(f"{ML}/CompanyDetail.aspx", {"symbol": symbol})
    fields: dict[str, str] = {}
    for tr in soup.find_all("tr"):
        th, td = tr.find("th", recursive=False), tr.find("td", recursive=False)
        if th and td and len(tr.find_all("td", recursive=False)) == 1:
            fields.setdefault(_text(th), _text(td))
    if not fields.get("Company Name"):
        raise ValueError(f"{symbol} not found on Merolagani")

    low_high = re.findall(r"\d[\d,]*\.?\d*", fields.get("52 Weeks High - Low", ""))
    high_52, low_52 = (num(low_high[0]), num(low_high[1])) if len(low_high) >= 2 else (None, None)
    return {
        "name": fields["Company Name"],
        "sector": fields.get("Sector", ""),
        "listed_shares": _lead_num(fields.get("Listed Shares", "")),
        "paid_up": _lead_num(fields.get("Paidup Value", "")) or 100.0,
        "price": _lead_num(fields.get("Market Price", "")),
        "high_52": high_52,
        "low_52": low_52,
        "avg_180": _lead_num(fields.get("180 Day Average", "")),
        "avg_120": _lead_num(fields.get("120 Day Average", "")),
        "yield_1y": _lead_num(fields.get("1 Year Yield", "")),
        "eps": _lead_num(fields.get("EPS", "")),
        "eps_period": re.sub(r"^\s*-?[\d,.]+\s*", "", fields.get("EPS", "")).strip("() "),
        "pe": _lead_num(fields.get("P/E Ratio", "")),
        "book_value": _lead_num(fields.get("Book Value", "")),
        "pbv": _lead_num(fields.get("PBV", "")),
        "dividend": _lead_num(fields.get("% Dividend", "")),
        "bonus": _lead_num(fields.get("% Bonus", "")),
        "avg_volume_30": _lead_num(fields.get("30-Day Avg Volume", "")),
        "market_cap": _lead_num(fields.get("Market Capitalization", "")),
        "dividends": _cash_dividends(soup),
    }


def merolagani_sector_flow() -> pd.DataFrame:
    d = _get(f"{ML}/handlers/webrequesthandler.ashx", {"type": "market_summary"}).json()
    return pd.DataFrame(d["sector"]["detail"]).rename(columns={"s": "Sector", "t": "Turnover", "q": "Volume"})


def merolagani_summary() -> dict:
    d = _get(f"{ML}/handlers/webrequesthandler.ashx", {"type": "market_summary"}).json()["overall"]
    return {
        "turnover": num(d["t"]),
        "shares": num(d["q"]),
        "transactions": num(d["tn"]),
        "scrips": num(d["st"]),
        "market_cap": num(d["mc"]),
        "float_cap": num(d["fc"]),
    }


def merolagani_corporate() -> dict[str, pd.DataFrame]:
    soup = _soup(f"{ML}/Index.aspx")
    out = {"agm": pd.DataFrame(), "right": pd.DataFrame()}
    for table in soup.find_all("table"):
        raw = _table(table)
        cols = list(raw.columns)
        if "AGM Date" in cols:
            out["agm"] = pd.DataFrame(
                {
                    "Symbol": raw["Company"],
                    "Fiscal year": raw["Fiscal Year"],
                    "Book close": pd.to_datetime(raw["Bookclose Date"], format="%b %d, %Y", errors="coerce"),
                    "AGM": pd.to_datetime(raw["AGM Date"], format="%b %d, %Y", errors="coerce"),
                }
            )
        elif "Right Share (Ratio)" in cols:
            out["right"] = pd.DataFrame({"Symbol": raw["Company"], "Fiscal year": raw["Fiscal Year"], "Ratio": raw["Right Share (Ratio)"]})
    return out


# --------------------------------------------------------------------------- #
# News
# --------------------------------------------------------------------------- #

_SS_NEWS = {
    "General": ["latest"],
    "IPO": ["ipo-fpo-news"],
    "Allotment": ["share-allotment"],
    "Dividend": ["dividend-right-bonus"],
    "Analysis": ["exclusive", "weekly-analysis", "financial-analysis"],
}
_ML_NEWS = {"Market": 6, "Company": 7, "Economy": 8, "Hydropower": 9}


def _ss_news(category: str, slug: str) -> list[dict]:
    soup = _soup(f"{SS}/category/{slug}")
    items = []
    for h in soup.select("h4.featured-news-title"):
        link = h.find_parent("a")
        if not link or not link.get("href"):
            continue
        stamp = _text(link.parent.find("span", class_="text-org"))
        try:
            when = datetime.strptime(stamp, "%A, %B %d, %Y")
        except ValueError:
            when = pd.NaT
        items.append({"Title": _text(h), "Url": link["href"], "Date": when, "Category": category, "Source": "ShareSansar"})
    return items


def _ml_news(category: str, news_id: int) -> list[dict]:
    soup = _soup(f"{ML}/NewsList.aspx", {"id": news_id, "type": "latest"})
    items = []
    for h in soup.select("h4.media-title"):
        link = h.find("a")
        if not link or not link.get("href"):
            continue
        label = h.find_next("span", class_="media-label")
        try:
            when = datetime.strptime(_text(label), "%b %d, %Y %I:%M %p")
        except ValueError:
            when = pd.NaT
        items.append({"Title": _text(link), "Url": f"{ML}{link['href']}" if link["href"].startswith("/") else link["href"], "Date": when, "Category": category, "Source": "Merolagani"})
    return items


def news() -> pd.DataFrame:
    jobs = [(_ss_news, cat, slug) for cat, slugs in _SS_NEWS.items() for slug in slugs]
    jobs += [(_ml_news, cat, nid) for cat, nid in _ML_NEWS.items()]
    items: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for part in pool.map(lambda j: _safe_list(*j), jobs):
            items.extend(part)
    df = pd.DataFrame(items)
    if df.empty:
        return df
    df = df.drop_duplicates("Url").dropna(subset=["Date"])
    return df.sort_values("Date", ascending=False).reset_index(drop=True)


def _safe_list(fn, cat, key) -> list[dict]:
    try:
        return fn(cat, key)
    except Exception:
        return []
