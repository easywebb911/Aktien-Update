#!/usr/bin/env python3
"""
Daily Stock Squeeze Report Generator
Identifies top 10 short squeeze candidates from US markets.
Data sources: Finviz (screener) + Yahoo Finance / yfinance (prices, news).
"""

import os
import re
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import yfinance as yf
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MIN_SHORT_FLOAT = 15.0   # %
MIN_REL_VOLUME  = 1.5    # × 20-day avg
MAX_MARKET_CAP  = 10e9   # $10 B
MIN_PRICE       = 1.0    # USD


# ===========================================================================
# 1. FINVIZ SCREENER
# ===========================================================================

def _parse_market_cap(s: str):
    """'1.5B' → 1_500_000_000  |  '-' → None"""
    if not s or s == "-":
        return None
    s = s.strip()
    mult = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}
    if s[-1] in mult:
        try:
            return float(s[:-1]) * mult[s[-1]]
        except ValueError:
            return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _parse_pct(s: str) -> float:
    if not s or s == "-":
        return 0.0
    try:
        return float(s.replace("%", "").strip())
    except ValueError:
        return 0.0


def _parse_float(s: str) -> float:
    if not s or s == "-":
        return 0.0
    try:
        return float(s.replace(",", "").strip())
    except ValueError:
        return 0.0


def get_finviz_candidates(max_pages: int = 6) -> list[dict]:
    """
    Scrape Finviz Ownership screener (v=141).
    Filters applied here: Short Float >15 %, Price >$1.
    Volume and market-cap filters are applied after.
    Returns list of candidate dicts.
    """
    candidates: list[dict] = []
    col_map: dict[str, int] | None = None

    for page in range(max_pages):
        row_start = page * 20 + 1
        url = (
            "https://finviz.com/screener.ashx"
            f"?v=141&f=sh_short_o{int(MIN_SHORT_FLOAT)},sh_price_o{int(MIN_PRICE)}"
            f"&o=-shortfloat&r={row_start}"
        )
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.error("Finviz request failed: %s", exc)
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Locate the data table by finding the one whose first row contains "Ticker"
        table = None
        for t in soup.find_all("table"):
            first_tr = t.find("tr")
            if first_tr and any("Ticker" in td.get_text() for td in first_tr.find_all("td")):
                table = t
                break

        if table is None:
            log.warning("Screener table not found on page %d – stopping.", page + 1)
            break

        all_rows = table.find_all("tr")
        if not all_rows:
            break

        # Build column map from header row (first time)
        if col_map is None:
            headers = [td.get_text(strip=True) for td in all_rows[0].find_all("td")]
            col_map = {h: i for i, h in enumerate(headers)}
            log.debug("Finviz columns: %s", headers)

        data_rows = all_rows[1:]
        if not data_rows:
            break

        page_added = 0
        for row in data_rows:
            cells = row.find_all("td")
            if len(cells) < 10:
                continue

            def cell(name: str, default: str = "") -> str:
                idx = col_map.get(name, -1)
                return cells[idx].get_text(strip=True) if 0 <= idx < len(cells) else default

            ticker = cell("Ticker")
            if not ticker or not ticker.replace(".", "").isalnum():
                continue

            mkt_cap     = _parse_market_cap(cell("Market Cap"))
            short_float = _parse_pct(cell("Float Short"))
            short_ratio = _parse_float(cell("Short Ratio"))
            rel_vol     = _parse_float(cell("Rel Volume"))
            price       = _parse_float(cell("Price"))
            change      = _parse_pct(cell("Change"))

            # Hard filters
            if price < MIN_PRICE:
                continue
            if short_float < MIN_SHORT_FLOAT:
                continue
            if rel_vol < MIN_REL_VOLUME:
                continue
            if mkt_cap and mkt_cap > MAX_MARKET_CAP:
                continue

            candidates.append({
                "ticker":       ticker,
                "market_cap":   mkt_cap,
                "market_cap_s": cell("Market Cap"),
                "short_float":  short_float,
                "short_ratio":  short_ratio,
                "rel_volume":   rel_vol,
                "price":        price,
                "change":       change,
            })
            page_added += 1

        log.info("Finviz page %d: +%d → %d total", page + 1, page_added, len(candidates))
        time.sleep(1.5)  # polite rate-limit

    return candidates


# ===========================================================================
# 2. YFINANCE ENRICHMENT
# ===========================================================================

def get_yfinance_data(ticker: str) -> dict:
    try:
        stk  = yf.Ticker(ticker)
        info = stk.info or {}
        hist = stk.history(period="30d")

        avg_vol_20 = float(hist["Volume"].tail(20).mean()) if len(hist) >= 5 else 0.0
        cur_vol    = float(hist["Volume"].iloc[-1])         if len(hist) >= 1 else 0.0
        vol_ratio  = cur_vol / avg_vol_20 if avg_vol_20 > 0 else 0.0

        return {
            "company_name": info.get("longName") or info.get("shortName") or ticker,
            "sector":       info.get("sector", "N/A"),
            "market_cap":   info.get("marketCap"),
            "short_ratio":  info.get("shortRatio") or 0.0,
            "short_float_yf": (info.get("shortPercentOfFloat") or 0.0) * 100,
            "52w_high":     info.get("fiftyTwoWeekHigh"),
            "52w_low":      info.get("fiftyTwoWeekLow"),
            "avg_vol_20d":  avg_vol_20,
            "cur_vol":      cur_vol,
            "vol_ratio":    vol_ratio,
        }
    except Exception as exc:
        log.warning("yfinance error for %s: %s", ticker, exc)
        return {}


def get_yahoo_news(ticker: str, n: int = 3) -> list[dict]:
    try:
        stk  = yf.Ticker(ticker)
        raw  = (stk.news or [])[:n]
        news = []
        for item in raw:
            # yfinance ≥ 0.2.x nests content inside item["content"]
            content = item.get("content", item)
            pub_ts = (
                content.get("pubDate")
                or content.get("providerPublishTime")
                or item.get("providerPublishTime")
                or 0
            )
            if isinstance(pub_ts, str):
                # ISO format "2025-04-01T12:00:00Z"
                try:
                    pub_ts = int(datetime.fromisoformat(pub_ts.rstrip("Z")).timestamp())
                except Exception:
                    pub_ts = 0
            ts_str = (
                datetime.fromtimestamp(int(pub_ts)).strftime("%d.%m.%Y %H:%M")
                if pub_ts else ""
            )
            news.append({
                "title":     content.get("title") or item.get("title") or "",
                "publisher": (content.get("provider", {}) or {}).get("displayName")
                              or content.get("publisher")
                              or item.get("publisher") or "",
                "link":      (content.get("canonicalUrl", {}) or {}).get("url")
                              or content.get("link")
                              or item.get("link") or "#",
                "time":      ts_str,
            })
        return news
    except Exception as exc:
        log.warning("News error for %s: %s", ticker, exc)
        return []


# ===========================================================================
# 3. SCORING & ANALYSIS
# ===========================================================================

def score(stock: dict) -> float:
    """Weighted squeeze score 0–100."""
    sf  = min(stock.get("short_float", 0) / 100.0, 1.0) * 40   # 40 %
    sr  = min(stock.get("short_ratio", 0) / 20.0,  1.0) * 30   # 30 %
    rv  = min((stock.get("rel_volume", 0) - 1.0) / 4.0, 1.0) * 30  # 30 %
    return round(sf + sr + rv, 2)


def fmt_cap(v) -> str:
    if not v:
        return "N/A"
    v = float(v)
    if v >= 1e9:
        return f"${v/1e9:.1f} B"
    if v >= 1e6:
        return f"${v/1e6:.0f} M"
    return f"${v:,.0f}"


def risk_assessment(stock: dict) -> tuple[str, str, str]:
    """Returns (level_de, hex_color, reason)."""
    pts = 0
    reasons = []

    sf = stock.get("short_float", 0)
    if sf > 40:
        pts += 2
        reasons.append(
            f"Extrem hohes Short-Interesse ({sf:.1f} %) bedeutet massive Squeeze-Gefahr, "
            "aber auch starke Kursausschläge in beide Richtungen."
        )
    elif sf > 25:
        pts += 1
        reasons.append(f"Hohes Short-Interesse ({sf:.1f} %) erhöht die Volatilität deutlich.")

    cap = stock.get("market_cap") or stock.get("yf_market_cap")
    if cap:
        if cap < 300e6:
            pts += 2
            reasons.append(
                f"Micro-Cap ({fmt_cap(cap)}) – geringe Liquidität, Kursmanipulation möglich."
            )
        elif cap < 2e9:
            pts += 1
            reasons.append(f"Small-Cap ({fmt_cap(cap)}) mit eingeschränkter Liquidität.")

    rv = stock.get("rel_volume", 0)
    if rv > 5:
        pts += 1
        reasons.append(
            f"Extremer Volumenanstieg ({rv:.1f}×) kann auf koordiniertes Kaufinteresse hinweisen."
        )

    if pts >= 3:
        return "HOCH",   "#ef4444", " ".join(reasons[:2])
    if pts >= 1:
        return "MITTEL", "#f59e0b", " ".join(reasons[:2])
    return  "NIEDRIG", "#22c55e", "Moderates Risikoprofil für einen Squeeze-Kandidaten."


def short_situation(stock: dict) -> str:
    parts = []
    sf = stock.get("short_float", 0)
    sr = stock.get("short_ratio", 0)
    rv = stock.get("rel_volume", 0)
    chg = stock.get("change", 0)

    if sf > 30:
        parts.append(f"Mit {sf:.1f} % Short Float ist das Leerverkaufsinteresse sehr hoch.")
    else:
        parts.append(f"Short Float von {sf:.1f} % liegt deutlich über dem Marktdurchschnitt.")

    if sr > 5:
        parts.append(
            f"Die Short Ratio von {sr:.1f} Tagen zeigt, dass Leerverkäufer mehrere Handelstage "
            "zum Eindecken benötigen würden – dies verstärkt den Squeeze-Druck."
        )

    if rv >= 2.0:
        parts.append(
            f"Das Handelsvolumen liegt bei {rv:.1f}× dem 20-Tage-Durchschnitt, "
            "was auf erhöhtes Kaufinteresse und mögliche Short-Eindeckungen hindeutet."
        )
    if chg > 5:
        parts.append(
            f"Der Kursanstieg von +{chg:.1f} % heute könnte Margin Calls bei Leerverkäufern auslösen."
        )
    elif chg < -3:
        parts.append(
            f"Der Kursrückgang von {chg:.1f} % könnte das Short-Interesse kurzfristig erhöhen."
        )

    return " ".join(parts) if parts else "Keine eindeutigen Trendsignale erkennbar."


def news_summary(news_list: list[dict]) -> str:
    if not news_list:
        return "Keine aktuellen Nachrichten verfügbar."
    titles = [n["title"] for n in news_list if n.get("title")]
    if not titles:
        return "Keine Nachrichtentitel verfügbar."
    joined = " – ".join(titles[:3])
    return joined if len(joined) <= 400 else joined[:397] + "…"


# ===========================================================================
# 4. HTML REPORT
# ===========================================================================

def _card(i: int, s: dict) -> str:
    risk_lv, risk_col, risk_txt = risk_assessment(s)
    sit_txt  = short_situation(s)
    news_sum = news_summary(s.get("news", []))

    chg_cls = "pos" if s.get("change", 0) >= 0 else "neg"
    chg_pfx = "+" if s.get("change", 0) >= 0 else ""
    sc       = min(int(s["score"]), 100)
    cap_val  = s.get("yf_market_cap") or s.get("market_cap")

    news_html = ""
    for n in s.get("news", [])[:3]:
        news_html += (
            f'<div class="ni">'
            f'<a href="{n.get("link","#")}" target="_blank" rel="noopener noreferrer">'
            f'{n.get("title","")}</a>'
            f'<span class="nm">{n.get("publisher","")} · {n.get("time","")}</span>'
            f'</div>'
        )
    if not news_html:
        news_html = '<div class="ni">Keine Nachrichten verfügbar.</div>'

    return f"""
<div class="card" id="c{i}">
  <div class="ch" onclick="tog({i})">
    <div class="rnk">#{i}</div>
    <div class="cm">
      <div class="ct">
        <span class="tk">{s['ticker']}</span>
        <span class="cn">{s.get('company_name', '')}</span>
        <span class="sec">{s.get('sector','')}</span>
      </div>
      <div class="mtr">
        <span class="m"><span class="ml">Kurs</span><span class="mv">${s.get('price',0):.2f}</span></span>
        <span class="m"><span class="ml">Änd.</span><span class="mv {chg_cls}">{chg_pfx}{s.get('change',0):.2f}%</span></span>
        <span class="m"><span class="ml">Short Float</span><span class="mv hi">{s.get('short_float',0):.1f}%</span></span>
        <span class="m"><span class="ml">Short Ratio</span><span class="mv">{s.get('short_ratio',0):.1f}d</span></span>
        <span class="m"><span class="ml">Rel. Vol.</span><span class="mv">{s.get('rel_volume',0):.1f}×</span></span>
        <span class="badge" style="color:{risk_col};border-color:{risk_col}40;background:{risk_col}18">{risk_lv}</span>
      </div>
    </div>
    <div class="sc">
      <div class="sl">Score</div>
      <div class="sv">{s['score']:.1f}</div>
      <div class="sb"><div class="sf" style="width:{sc}%"></div></div>
    </div>
    <div class="arr" id="a{i}">▼</div>
  </div>
  <div class="cd" id="d{i}">
    <div class="dg">
      <div class="ds">
        <h4>Marktdaten</h4>
        <table class="dt">
          <tr><td>Marktkapitalisierung</td><td>{fmt_cap(cap_val)}</td></tr>
          <tr><td>52W-Hoch / -Tief</td><td>${s.get('52w_high') or 0:.2f} / ${s.get('52w_low') or 0:.2f}</td></tr>
          <tr><td>Sektor</td><td>{s.get('sector','N/A')}</td></tr>
          <tr><td>Ø Volumen 20T</td><td>{s.get('avg_vol_20d',0):,.0f}</td></tr>
          <tr><td>Heutiges Volumen</td><td>{s.get('cur_vol',0):,.0f}</td></tr>
        </table>
      </div>
      <div class="ds">
        <h4>Short-Analyse</h4>
        <p class="at">{sit_txt}</p>
        <h4 style="margin-top:16px">Risikobewertung</h4>
        <div class="rd" style="border-left-color:{risk_col}">
          <strong style="color:{risk_col}">{risk_lv}</strong>
          <p>{risk_txt}</p>
        </div>
      </div>
      <div class="ds">
        <h4>Aktuelle Nachrichten</h4>
        {news_html}
        <h4 style="margin-top:14px">Zusammenfassung</h4>
        <p class="at">{news_sum}</p>
      </div>
    </div>
  </div>
</div>"""


def generate_html(stocks: list[dict], report_date: str) -> str:
    cards = "\n".join(_card(i + 1, s) for i, s in enumerate(stocks))

    avg_sf  = sum(s["short_float"] for s in stocks) / len(stocks)
    avg_sr  = sum(s["short_ratio"]  for s in stocks) / len(stocks)
    avg_rv  = sum(s["rel_volume"]   for s in stocks) / len(stocks)
    now_str = datetime.now(ZoneInfo("Europe/Berlin")).strftime("%H:%M Uhr")

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Squeeze Report – {report_date}</title>
<style>
:root{{--bg:#07090f;--bg2:#0e1120;--bg3:#131929;--brd:#1e2d4a;--acc:#4a9eff;--txt:#dde4f5;--sub:#6677a0;}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--txt);min-height:100vh}}
a{{color:var(--acc)}}
/* Header */
.hdr{{background:linear-gradient(135deg,#111d3a 0%,#0a1020 100%);border-bottom:1px solid var(--brd);padding:20px 28px;display:flex;align-items:center;justify-content:space-between}}
.hdr h1{{font-size:1.5rem;font-weight:800;color:#fff;letter-spacing:-.5px}}.hdr h1 span{{color:var(--acc)}}
.hdr-meta{{text-align:right;font-size:.82rem;color:var(--sub)}}.hdr-meta strong{{color:#aabbd4;display:block;font-size:.95rem}}
/* Layout */
.wrap{{max-width:1100px;margin:0 auto;padding:22px 14px}}
/* Summary bar */
.sbar{{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}}
.ss{{background:var(--bg3);border:1px solid var(--brd);border-radius:10px;padding:12px 18px;flex:1;min-width:130px}}
.ss .sl{{font-size:.7rem;color:var(--sub);text-transform:uppercase;letter-spacing:.5px}}
.ss .sv{{font-size:1.35rem;font-weight:700;color:var(--acc);margin-top:3px}}
/* Disclaimer */
.disc{{background:#1a1400;border:1px solid #3a2f00;border-radius:8px;padding:11px 15px;margin-bottom:20px;font-size:.78rem;color:#b8a850;line-height:1.5}}
/* Card */
.card{{background:var(--bg2);border:1px solid var(--brd);border-radius:12px;margin-bottom:10px;overflow:hidden;transition:border-color .2s}}
.card:hover{{border-color:#2a4a8a}}
.ch{{display:flex;align-items:center;padding:14px 18px;cursor:pointer;gap:14px;user-select:none}}
.rnk{{font-size:1.05rem;font-weight:700;color:var(--acc);min-width:32px}}
.cm{{flex:1}}
.ct{{display:flex;align-items:baseline;gap:9px;margin-bottom:7px;flex-wrap:wrap}}
.tk{{font-size:1.15rem;font-weight:800;color:#fff;font-family:'Courier New',monospace}}
.cn{{font-size:.82rem;color:var(--sub)}}
.sec{{font-size:.72rem;color:#3d4f72;background:#141e33;padding:1px 7px;border-radius:10px}}
.mtr{{display:flex;gap:14px;flex-wrap:wrap;align-items:center}}
.m{{display:flex;flex-direction:column;gap:1px}}
.ml{{font-size:.66rem;color:#3d4f72;text-transform:uppercase;letter-spacing:.4px}}
.mv{{font-size:.9rem;font-weight:600;color:#c8d4f0}}
.pos{{color:#22c55e}}.neg{{color:#ef4444}}.hi{{color:#f59e0b}}
.badge{{padding:3px 9px;border-radius:20px;font-size:.7rem;font-weight:700;letter-spacing:.4px;border:1px solid}}
/* Score */
.sc{{text-align:right;min-width:76px}}
.sl{{font-size:.66rem;color:#3d4f72;text-transform:uppercase}}
.sv{{font-size:1.35rem;font-weight:700;color:var(--acc)}}
.sb{{width:76px;height:3px;background:#1a2a45;border-radius:2px;margin-top:4px}}
.sf{{height:100%;background:linear-gradient(90deg,#4a9eff,#9b5cf6);border-radius:2px}}
.arr{{color:#3d4f72;font-size:.85rem;transition:transform .25s;margin-left:4px}}
.card.open .arr{{transform:rotate(180deg)}}
/* Details */
.cd{{display:none;padding:0 18px 18px;border-top:1px solid var(--brd)}}
.cd.active{{display:block}}
.dg{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;padding-top:14px}}
@media(max-width:720px){{.dg{{grid-template-columns:1fr}}.sc{{display:none}}}}
.ds h4{{font-size:.72rem;text-transform:uppercase;letter-spacing:.5px;color:var(--acc);margin-bottom:9px}}
.dt{{width:100%;font-size:.82rem;border-collapse:collapse}}
.dt td{{padding:4px 0;border-bottom:1px solid #111d33}}
.dt td:first-child{{color:var(--sub)}}
.dt td:last-child{{text-align:right;font-weight:600}}
.ni{{margin-bottom:9px;font-size:.82rem;line-height:1.5}}
.ni a{{color:var(--acc);text-decoration:none}}
.ni a:hover{{text-decoration:underline}}
.nm{{display:block;font-size:.7rem;color:#3d4f72;margin-top:1px}}
.at{{font-size:.82rem;line-height:1.65;color:#8899bb}}
.rd{{padding:9px 12px;background:#0a1020;border-left:3px solid;border-radius:0 6px 6px 0;font-size:.82rem}}
.rd p{{margin-top:3px;color:#7788aa;line-height:1.5}}
/* Footer */
.ftr{{text-align:center;padding:22px;color:#3d4f72;font-size:.75rem;border-top:1px solid var(--brd);margin-top:36px}}
</style>
</head>
<body>
<div class="hdr">
  <h1>Squeeze <span>Report</span></h1>
  <div class="hdr-meta">
    <strong>{report_date}</strong>
    US-Märkte · Top-10 Squeeze-Kandidaten · {now_str}
  </div>
</div>
<div class="wrap">
  <div class="sbar">
    <div class="ss"><div class="sl">Kandidaten</div><div class="sv">Top 10</div></div>
    <div class="ss"><div class="sl">Ø Short Float</div><div class="sv">{avg_sf:.1f}%</div></div>
    <div class="ss"><div class="sl">Ø Short Ratio</div><div class="sv">{avg_sr:.1f}d</div></div>
    <div class="ss"><div class="sl">Ø Rel. Volumen</div><div class="sv">{avg_rv:.1f}×</div></div>
  </div>
  <div class="disc">
    ⚠ <strong>Disclaimer:</strong> Dieser Report dient ausschließlich Informationszwecken
    und stellt keine Anlageberatung dar. Short-Squeeze-Kandidaten sind hochspekulative
    Investments mit erhöhtem Verlustrisiko. Keine Kauf- oder Verkaufsempfehlung.
  </div>
  {cards}
</div>
<div class="ftr">
  Automatisch generiert am {report_date} · Quellen: Finviz, Yahoo Finance · Keine Anlageberatung
</div>
<script>
function tog(id){{
  const card=document.getElementById('c'+id);
  const det=document.getElementById('d'+id);
  card.classList.toggle('open');
  det.classList.toggle('active');
}}
// Open first card by default
window.addEventListener('DOMContentLoaded',()=>tog(1));
</script>
</body>
</html>"""


# ===========================================================================
# 5. MAIN
# ===========================================================================

def main():
    berlin = ZoneInfo("Europe/Berlin")
    report_date = datetime.now(berlin).strftime("%d.%m.%Y")
    log.info("=== Squeeze Report %s ===", report_date)

    # --- Step 1: Finviz candidates ---
    log.info("Fetching Finviz screener data …")
    candidates = get_finviz_candidates(max_pages=6)

    if len(candidates) < 5:
        log.warning(
            "Only %d candidates found with rel_volume ≥ %.1f×. "
            "Relaxing volume threshold to 1.0× for fallback.",
            len(candidates), MIN_REL_VOLUME,
        )
        # Fallback: relax volume filter
        global MIN_REL_VOLUME
        MIN_REL_VOLUME = 1.0
        candidates = get_finviz_candidates(max_pages=6)

    log.info("Total candidates from Finviz: %d", len(candidates))

    # Initial score & sort; take top 30 for yfinance enrichment
    for c in candidates:
        c["score"] = score(c)
    candidates.sort(key=lambda x: x["score"], reverse=True)
    pool = candidates[:30]

    # --- Step 2: yfinance enrichment ---
    log.info("Enriching %d stocks with yfinance …", len(pool))
    enriched = []
    for i, c in enumerate(pool):
        t = c["ticker"]
        log.info("  [%d/%d] %s", i + 1, len(pool), t)
        yfd = get_yfinance_data(t)
        c.update({
            "company_name": yfd.get("company_name", t),
            "sector":       yfd.get("sector", "N/A"),
            "yf_market_cap":yfd.get("market_cap"),
            "short_ratio":  yfd.get("short_ratio") or c.get("short_ratio", 0),
            "52w_high":     yfd.get("52w_high"),
            "52w_low":      yfd.get("52w_low"),
            "avg_vol_20d":  yfd.get("avg_vol_20d", 0),
            "cur_vol":      yfd.get("cur_vol", 0),
        })
        # Use yfinance vol ratio if available and better
        if yfd.get("vol_ratio", 0) > 0:
            c["rel_volume"] = yfd["vol_ratio"]

        # Re-check market cap with yfinance data
        cap = c.get("yf_market_cap") or c.get("market_cap")
        if cap and cap > MAX_MARKET_CAP:
            log.info("  Skipping %s: market cap %s > $10 B", t, fmt_cap(cap))
            time.sleep(0.3)
            continue

        c["score"] = score(c)
        enriched.append(c)
        time.sleep(0.4)

    enriched.sort(key=lambda x: x["score"], reverse=True)
    top10 = enriched[:10]

    if not top10:
        log.error("No stocks passed all filters. Falling back to Finviz-only top 10.")
        top10 = candidates[:10]

    # --- Step 3: News ---
    log.info("Fetching news for top 10 …")
    for s in top10:
        s["news"] = get_yahoo_news(s["ticker"])
        time.sleep(0.3)

    # --- Step 4: HTML ---
    log.info("Generating HTML report …")
    html = generate_html(top10, report_date)

    os.makedirs("docs", exist_ok=True)
    out = "docs/index.html"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)

    log.info("Report written to %s", out)
    log.info("Top 10: %s", [s["ticker"] for s in top10])


if __name__ == "__main__":
    main()
