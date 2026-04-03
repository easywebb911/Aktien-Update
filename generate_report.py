#!/usr/bin/env python3
"""
Daily Stock Squeeze Report Generator
Identifies top 10 short squeeze candidates from global markets (US, DE, GB, CA).
Data sources: Yahoo Finance Screener (primary) + Finviz (fallback) + yfinance (enrichment).
News titles and summaries are translated to German.
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
from deep_translator import GoogleTranslator

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


# ===========================================================================
# 1a. YAHOO FINANCE SCREENER  (primary — direct JSON API, no yf.Screener)
# ===========================================================================

# Markets to scan: region code → list of predefined screener IDs
_YF_SCREENERS: dict[str, list[str]] = {
    "US": ["most_shorted_stocks", "small_cap_gainers", "aggressive_small_caps"],
    "DE": ["most_shorted_stocks", "small_cap_gainers"],   # XETRA / Frankfurt
    "GB": ["most_shorted_stocks", "small_cap_gainers"],   # London Stock Exchange
    "CA": ["most_shorted_stocks", "small_cap_gainers"],   # Toronto Stock Exchange
}

_YF_SCREENER_URL = (
    "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved"
)


def _translate(text: str) -> str:
    """Translate text to German via Google Translate (free, no key required)."""
    if not text or len(text.strip()) < 4:
        return text
    try:
        return GoogleTranslator(source="auto", target="de").translate(text[:4900])
    except Exception as exc:
        log.debug("Translation skipped: %s", exc)
        return text


def _fetch_yf_screener(screener_id: str, region: str = "US", count: int = 100) -> list[dict]:
    """Call one Yahoo Finance predefined screener via raw HTTP. No crumb needed."""
    params = {
        "formatted": "false",
        "scrIds": screener_id,
        "count": str(count),
        "region": region,
        "lang": "en-US",
    }
    try:
        resp = requests.get(
            _YF_SCREENER_URL, params=params, headers=HTTP_HEADERS, timeout=20
        )
        resp.raise_for_status()
        data = resp.json()
        results = (data.get("finance") or {}).get("result") or []
        quotes  = results[0].get("quotes", []) if results else []
        log.info("  Yahoo screener [%s] '%s': %d quotes", region, screener_id, len(quotes))
        return quotes
    except Exception as exc:
        log.warning("  Yahoo screener [%s] '%s' failed: %s", region, screener_id, exc)
        return []


def get_yahoo_screener_candidates() -> list[dict]:
    """
    Fetch a broad candidate pool from Yahoo Finance screeners across all configured
    regions (US, DE, GB, CA). Strict filters are applied in the enrichment step.
    """
    result: list[dict] = []
    seen:   set[str]   = set()

    def _add_quotes(quotes: list, region: str) -> None:
        for q in quotes:
            t = q.get("symbol", "").strip().upper()
            # Accept alphanumeric tickers incl. dots/dashes for international (e.g. BMW.DE, VOD.L)
            if not t or not re.match(r'^[A-Z0-9][A-Z0-9.\-]{0,14}$', t) or t in seen:
                continue
            price   = float(q.get("regularMarketPrice") or 0)
            mkt_cap = q.get("marketCap") or q.get("intradayMarketCap")
            if price < MIN_PRICE:
                continue
            if mkt_cap and float(mkt_cap) > MAX_MARKET_CAP:
                continue
            seen.add(t)
            sf_raw = float(q.get("shortPercentOfFloat") or 0)
            result.append({
                "ticker":       t,
                "market":       region,
                "market_cap":   float(mkt_cap) if mkt_cap else None,
                "market_cap_s": fmt_cap(mkt_cap),
                "price":        price,
                "change":       float(q.get("regularMarketChangePercent") or 0),
                # shortPercentOfFloat from Yahoo is decimal (0.25 = 25 %)
                "short_float":  sf_raw * 100 if sf_raw <= 1.0 else sf_raw,
                "short_ratio":  float(q.get("shortRatio") or 0),
                "rel_volume":   0.0,  # filled from history in enrichment
                "company_name": q.get("shortName") or q.get("longName") or t,
                "sector":       q.get("sector") or "N/A",
            })

    log.info("Querying Yahoo Finance screeners across %d regions …", len(_YF_SCREENERS))
    for region, screener_ids in _YF_SCREENERS.items():
        for sid in screener_ids:
            _add_quotes(_fetch_yf_screener(sid, region=region), region)
            time.sleep(0.5)

    log.info("Yahoo screener pool: %d unique tickers", len(result))
    return result


def get_finviz_candidates(max_pages: int = 6) -> list[dict]:
    """
    Scrape Finviz Ownership screener (v=141) — fallback when Yahoo screener fails.
    Note: Finviz may block cloud-runner IPs; use Yahoo screener as primary.
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


def get_yahoo_news(ticker: str, n: int = 2) -> list[dict]:
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
                try:
                    pub_ts = int(datetime.fromisoformat(pub_ts.rstrip("Z")).timestamp())
                except Exception:
                    pub_ts = 0
            ts_str = (
                datetime.fromtimestamp(int(pub_ts)).strftime("%d.%m.%Y %H:%M")
                if pub_ts else ""
            )
            title_orig = content.get("title") or item.get("title") or ""
            # Raw summary / description from the article (if provided by yfinance)
            raw_summary = (
                content.get("summary")
                or content.get("description")
                or item.get("summary")
                or ""
            ).strip()

            news.append({
                "title":       _translate(title_orig) if title_orig else "",
                "title_orig":  title_orig,
                "summary_raw": raw_summary,         # original English summary
                "publisher":   (content.get("provider", {}) or {}).get("displayName")
                                or content.get("publisher")
                                or item.get("publisher") or "",
                "link":        (content.get("canonicalUrl", {}) or {}).get("url")
                                or content.get("link")
                                or item.get("link") or "#",
                "time":        ts_str,
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
    """Return a complete German-language summary of the most important news item."""
    if not news_list:
        return "Keine aktuellen Nachrichten verfügbar."
    top = news_list[0]
    # Prefer the raw English summary field (longer text) for translation
    raw = top.get("summary_raw", "").strip()
    if raw and len(raw) > 80:
        translated = _translate(raw[:2000])
        if translated and len(translated) > 40:
            return translated  # no truncation – show complete summary
    # Fallback: translate the headline of the top article into a complete sentence
    title_orig = top.get("title_orig") or top.get("title", "")
    if not title_orig:
        return "Keine Nachrichteninhalte verfügbar."
    translated = _translate(title_orig)
    return translated if translated else title_orig


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
    for n in s.get("news", [])[:2]:
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
        <span class="mkt">{s.get('market','US')}</span>
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

    n       = max(len(stocks), 1)  # guard against ZeroDivisionError
    avg_sf  = sum(s["short_float"] for s in stocks) / n
    avg_sr  = sum(s["short_ratio"]  for s in stocks) / n
    avg_rv  = sum(s["rel_volume"]   for s in stocks) / n
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
/* Score info */
.info-box{{background:var(--bg3);border:1px solid var(--brd);border-radius:10px;padding:14px 18px;margin-bottom:14px}}
.info-box h3{{font-size:.72rem;text-transform:uppercase;letter-spacing:.5px;color:var(--acc);margin-bottom:10px}}
.info-box ul{{list-style:none;display:flex;flex-direction:column;gap:5px}}
.info-box li{{font-size:.8rem;color:#8899bb;line-height:1.5;padding-left:14px;position:relative}}
.info-box li::before{{content:"–";position:absolute;left:0;color:var(--acc)}}
.info-box li strong{{color:#c8d4f0}}
.info-cols{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
@media(max-width:640px){{.info-cols{{grid-template-columns:1fr}}}}
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
.mkt{{font-size:.68rem;font-weight:700;color:#4a9eff;background:#0d1d38;padding:1px 7px;border-radius:10px;letter-spacing:.3px}}
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
/* Action bar */
.abar{{background:#080c18;border-bottom:1px solid var(--brd);padding:12px 28px}}
.abar-inner{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;max-width:1100px;margin:0 auto}}
.btn{{display:inline-flex;align-items:center;justify-content:center;min-height:48px;padding:0 22px;border:none;border-radius:10px;font-size:.95rem;font-weight:700;cursor:pointer;transition:opacity .15s,transform .1s;-webkit-tap-highlight-color:transparent;touch-action:manipulation;white-space:nowrap}}
.btn:active:not(:disabled){{transform:scale(.96)}}
.btn:disabled{{opacity:.5;cursor:not-allowed;transform:none}}
.btn-green{{background:#16a34a;color:#fff}}.btn-green:hover:not(:disabled){{background:#15803d}}
.btn-blue{{background:#2563eb;color:#fff}}.btn-blue:hover:not(:disabled){{background:#1d4ed8}}
.tok-rl{{font-size:.78rem;color:var(--sub);text-decoration:none;padding:4px 8px;border-radius:6px;margin-left:4px}}
.tok-rl:hover{{color:var(--acc)}}
.tok-sec{{background:#0d1327;border:1px solid var(--brd);border-radius:10px;padding:14px 16px;margin-top:12px;max-width:640px}}
.tok-hint{{font-size:.82rem;color:#8899bb;margin-bottom:10px;line-height:1.5}}
.tok-row{{display:flex;gap:10px;flex-wrap:wrap}}
.tok-inp{{flex:1;min-width:200px;background:#070c1a;border:1px solid var(--brd);border-radius:8px;color:var(--txt);padding:0 13px;height:48px;font-size:.88rem;font-family:monospace}}
.tok-inp:focus{{outline:2px solid var(--acc);outline-offset:1px}}
.amsg{{margin-top:12px;padding:11px 15px;border-radius:8px;font-size:.83rem;line-height:1.5;max-width:740px}}
.amsg-success{{background:#052a14;border:1px solid #166534;color:#86efac}}
.amsg-error{{background:#2a0808;border:1px solid #991b1b;color:#fca5a5}}
.amsg-info{{background:#0c1a30;border:1px solid var(--brd);color:#93c5fd}}
</style>
</head>
<body>
<div class="hdr">
  <h1>Squeeze <span>Report</span></h1>
  <div class="hdr-meta">
    <strong>{report_date}</strong>
    US · DE · GB · CA · Top-10 Squeeze-Kandidaten · {now_str}
  </div>
</div>
<div class="abar">
  <div class="abar-inner">
    <button id="btn-reload" class="btn btn-green" onclick="reloadPage()">&#8635;&ensp;Seite neu laden</button>
    <button id="btn-recalc" class="btn btn-blue" onclick="triggerWorkflow()">&#9881;&ensp;Jetzt neu berechnen</button>
    <a href="#" class="tok-rl" id="tok-rl" onclick="resetToken();return false;">Token zurücksetzen</a>
  </div>
  <div id="tok-sec" class="tok-sec" style="display:none">
    <p class="tok-hint">Bitte GitHub Token eingeben (wird nur lokal im Browser gespeichert und nie an Dritte übertragen – ausschließlich an die offizielle GitHub API).</p>
    <div class="tok-row">
      <input type="password" id="tok-inp" class="tok-inp"
             placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
             onkeydown="if(event.key==='Enter')saveTokenAndDispatch()">
      <button class="btn btn-blue" onclick="saveTokenAndDispatch()">Speichern &amp; starten</button>
    </div>
  </div>
  <div id="amsg" class="amsg" style="display:none"></div>
</div>
<div class="wrap">
  <div class="sbar">
    <div class="ss"><div class="sl">Kandidaten</div><div class="sv">Top 10</div></div>
    <div class="ss"><div class="sl">Ø Short Float</div><div class="sv">{avg_sf:.1f}%</div></div>
    <div class="ss"><div class="sl">Ø Short Ratio</div><div class="sv">{avg_sr:.1f}d</div></div>
    <div class="ss"><div class="sl">Ø Rel. Volumen</div><div class="sv">{avg_rv:.1f}×</div></div>
  </div>
  <div class="info-cols">
    <div class="info-box">
      <h3>Score (0–100) – Zusammensetzung</h3>
      <ul>
        <li><strong>40 % Short Float</strong> – Anteil leerverkaufter Aktien am Streubesitz; je höher, desto stärker der potenzielle Squeeze-Druck</li>
        <li><strong>30 % Short Ratio</strong> – Tage, die Leerverkäufer zum vollständigen Eindecken brauchen; hohe Werte erhöhen das Kapitulationsrisiko</li>
        <li><strong>30 % Rel. Volumen</strong> – Heutiges Handelsvolumen geteilt durch 20-Tage-Durchschnitt; Volumenspitzen signalisieren erhöhtes Kaufinteresse</li>
      </ul>
    </div>
    <div class="info-box">
      <h3>Filterkriterien</h3>
      <ul>
        <li><strong>Short Float &gt; 15 %</strong> – Mindest-Leerverkaufsquote als Squeeze-Voraussetzung</li>
        <li><strong>Kurs &gt; $1</strong> – Ausschluss von Penny Stocks mit extremem Manipulationsrisiko</li>
        <li><strong>Marktkapitalisierung &lt; $10 Mrd.</strong> – Fokus auf Small- &amp; Mid-Caps mit höherem Squeeze-Potenzial</li>
        <li><strong>Rel. Volumen ≥ 1,5×</strong> – Mindestaktivität (wird bei &lt; 5 Treffern automatisch auf 1,0× gelockert)</li>
      </ul>
    </div>
    <div class="info-box">
      <h3>Risikobewertung</h3>
      <ul>
        <li><strong style="color:#22c55e">NIEDRIG</strong> – Moderates Short-Interesse, ausreichende Liquidität</li>
        <li><strong style="color:#f59e0b">MITTEL</strong> – Erhöhtes Short-Interesse (&gt; 25 %) oder Small-Cap (&lt; $2 Mrd.)</li>
        <li><strong style="color:#ef4444">HOCH</strong> – Extremes Short-Interesse (&gt; 40 %) und/oder Micro-Cap (&lt; $300 Mio.); starke Kursausschläge möglich</li>
        <li><strong>Empfehlung:</strong> Nur mit kleinen Positionen und engem Stop-Loss handeln</li>
      </ul>
    </div>
  </div>
  <div class="disc">
    ⚠ <strong>Disclaimer:</strong> Dieser Report dient ausschließlich Informationszwecken
    und stellt keine Anlageberatung dar. Short-Squeeze-Kandidaten sind hochspekulative
    Investments mit erhöhtem Verlustrisiko. Keine Kauf- oder Verkaufsempfehlung.
  </div>
  {cards}
</div>
<div class="ftr">
  Automatisch generiert am {report_date} · Quellen: Yahoo Finance (US/DE/GB/CA), Finviz · Übersetzung: Google Translate · Keine Anlageberatung
</div>
<script>
// ── Accordion ────────────────────────────────────────────────────────────
function tog(id){{
  document.getElementById('c'+id).classList.toggle('open');
  document.getElementById('d'+id).classList.toggle('active');
}}
window.addEventListener('DOMContentLoaded',()=>tog(1));

// ── GitHub Actions Config ─────────────────────────────────────────────────
// Falls du das Repo geforkt oder umbenannt hast, hier anpassen:
const GH_OWNER    = 'easywebb911';
const GH_REPO     = 'Aktien-update';
const GH_WORKFLOW = 'daily-squeeze-report.yml';
const GH_BRANCH   = 'main';
const TOK_KEY     = 'ghpat_squeeze';
// ─────────────────────────────────────────────────────────────────────────

function reloadPage() {{
  const btn = document.getElementById('btn-reload');
  btn.disabled = true;
  btn.textContent = 'Wird geladen\u2026';
  window.location.reload();
}}

function triggerWorkflow() {{
  const token = localStorage.getItem(TOK_KEY);
  if (!token) {{ showTokenInput(); return; }}
  dispatchWorkflow(token);
}}

function showTokenInput() {{
  document.getElementById('tok-sec').style.display = 'block';
  document.getElementById('amsg').style.display = 'none';
  setTimeout(() => document.getElementById('tok-inp').focus(), 60);
}}

async function saveTokenAndDispatch() {{
  const token = document.getElementById('tok-inp').value.trim();
  if (!token) return;
  localStorage.setItem(TOK_KEY, token);
  document.getElementById('tok-sec').style.display = 'none';
  document.getElementById('tok-inp').value = '';
  await dispatchWorkflow(token);
}}

async function dispatchWorkflow(token) {{
  const btn  = document.getElementById('btn-recalc');
  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Wird gestartet\u2026';
  try {{
    const r = await fetch(
      `https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/actions/workflows/${{GH_WORKFLOW}}/dispatches`,
      {{
        method: 'POST',
        headers: {{
          'Authorization': `Bearer ${{token}}`,
          'Accept': 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
          'Content-Type': 'application/json',
        }},
        body: JSON.stringify({{ ref: GH_BRANCH }}),
      }}
    );
    if (r.status === 204) {{
      showMsg('success',
        'Neuberechnung gestartet \u2013 der Report ist in ca.\u00a02\u20133\u00a0Minuten aktuell. ' +
        'Danach bitte \u201eSeite neu laden\u201c dr\u00fccken.');
    }} else if (r.status === 401 || r.status === 403) {{
      localStorage.removeItem(TOK_KEY);
      showMsg('error',
        `Token ung\u00fcltig oder fehlende Berechtigung (HTTP ${{r.status}}). ` +
        'Token wurde entfernt \u2013 bitte beim n\u00e4chsten Versuch neu eingeben.');
    }} else {{
      const body = await r.text().catch(() => '');
      showMsg('error', `Fehler HTTP ${{r.status}}: ${{body.slice(0,200)}}`);
    }}
  }} catch(e) {{
    showMsg('error', `Netzwerkfehler: ${{e.message}}`);
  }} finally {{
    btn.disabled = false;
    btn.textContent = orig;
  }}
}}

function resetToken() {{
  localStorage.removeItem(TOK_KEY);
  document.getElementById('tok-sec').style.display = 'none';
  showMsg('info',
    'Token zur\u00fcckgesetzt. Beim n\u00e4chsten Klick auf \u201eJetzt neu berechnen\u201c ' +
    'wirst du erneut nach dem Token gefragt.');
}}

function showMsg(type, text) {{
  const el = document.getElementById('amsg');
  el.className = `amsg amsg-${{type}}`;
  el.textContent = text;
  el.style.display = 'block';
  if (type !== 'error') setTimeout(() => {{ el.style.display = 'none'; }}, 13000);
}}
</script>
</body>
</html>"""


# ===========================================================================
# 5. ERROR PAGE HELPER
# ===========================================================================

def _write_error_page(report_date: str, message: str) -> None:
    """Write a minimal error page when no data could be retrieved."""
    html = f"""<!DOCTYPE html><html lang="de">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Squeeze Report – {report_date}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
background:#07090f;color:#dde4f5;display:flex;align-items:center;
justify-content:center;min-height:100vh;margin:0}}
.box{{background:#111827;border:1px solid #1e2d4a;border-radius:12px;
padding:36px 44px;max-width:500px;text-align:center}}
.err{{color:#ef4444;font-size:1.15rem;font-weight:700;margin-bottom:12px}}
p{{color:#8899bb;font-size:.88rem;line-height:1.65}}
</style></head>
<body><div class="box">
<div class="err">&#9888; Datenabruf fehlgeschlagen</div>
<p>{message}<br><br>Datum: {report_date}</p>
</div></body></html>"""
    with open("index.html", "w", encoding="utf-8") as fh:
        fh.write(html)
    log.info("Error page written to index.html")


# ===========================================================================
# 6. MAIN
# ===========================================================================

def main():
    berlin = ZoneInfo("Europe/Berlin")
    report_date = datetime.now(berlin).strftime("%d.%m.%Y")
    log.info("=== Squeeze Report %s ===", report_date)

    # --- Step 1: Get candidate pool ---
    # Primary: Yahoo Finance Screener (reliable from GitHub Actions runners)
    log.info("Step 1 – Yahoo Finance Screener …")
    candidates = get_yahoo_screener_candidates()

    if not candidates:
        # Fallback: Finviz (may be blocked on cloud IPs, but worth trying)
        log.warning("Yahoo screener returned 0 results. Trying Finviz as fallback …")
        candidates = get_finviz_candidates(max_pages=6)

    log.info("Candidate pool: %d tickers", len(candidates))

    if not candidates:
        log.error("Both screeners failed. Writing error page.")
        _write_error_page(report_date,
            "Screener-Verbindung fehlgeschlagen (Yahoo Finance &amp; Finviz). "
            "Bitte manuell neu starten.")
        return

    # Pre-sort by whatever data we have so we enrich the most promising first
    for c in candidates:
        c["score"] = score(c)
    candidates.sort(key=lambda x: x["score"], reverse=True)
    pool = candidates[:40]

    # --- Step 2: yfinance enrichment (all real filtering happens here) ---
    log.info("Step 2 – Enriching %d candidates with yfinance …", len(pool))
    enriched = []
    for i, c in enumerate(pool):
        t = c["ticker"]
        log.info("  [%d/%d] %s", i + 1, len(pool), t)
        yfd = get_yfinance_data(t)

        # Overwrite with accurate yfinance values
        c.update({
            "company_name":  yfd.get("company_name") or c.get("company_name", t),
            "sector":        yfd.get("sector") or c.get("sector", "N/A"),
            "yf_market_cap": yfd.get("market_cap"),
            "52w_high":      yfd.get("52w_high"),
            "52w_low":       yfd.get("52w_low"),
            "avg_vol_20d":   yfd.get("avg_vol_20d", 0),
            "cur_vol":       yfd.get("cur_vol", 0),
        })
        yf_sf = yfd.get("short_float_yf", 0)
        if yf_sf > 0:
            c["short_float"] = yf_sf
        yf_sr = yfd.get("short_ratio", 0)
        if yf_sr > 0:
            c["short_ratio"] = yf_sr
        if yfd.get("vol_ratio", 0) > 0:
            c["rel_volume"] = yfd["vol_ratio"]

        # Hard filters (now with accurate data)
        cap = c.get("yf_market_cap") or c.get("market_cap")
        if cap and cap > MAX_MARKET_CAP:
            log.info("    skip %s: cap %s > $10B", t, fmt_cap(cap))
            time.sleep(0.25)
            continue
        if c["short_float"] < MIN_SHORT_FLOAT:
            log.info("    skip %s: short_float %.1f%% < %.0f%%",
                     t, c["short_float"], MIN_SHORT_FLOAT)
            time.sleep(0.25)
            continue

        c["score"] = score(c)
        enriched.append(c)
        time.sleep(0.4)

    enriched.sort(key=lambda x: x["score"], reverse=True)

    # Apply volume filter; relax automatically if too few results
    top10 = [c for c in enriched if c.get("rel_volume", 0) >= MIN_REL_VOLUME][:10]
    if len(top10) < 5:
        log.warning(
            "Only %d pass rel_volume ≥ %.1f×. Relaxing to 1.0× …",
            len(top10), MIN_REL_VOLUME,
        )
        top10 = enriched[:10]

    if not top10:
        log.error("No candidates survived all filters.")
        _write_error_page(report_date,
            "Keine Aktien erfüllen aktuell alle Filterkriterien "
            "(Short Float &gt;15 %, Preis &gt;$1, Marktkapitalisierung &lt;$10 Mrd.).")
        return

    # --- Step 3: News ---
    log.info("Step 3 – Fetching news for %d stocks …", len(top10))
    for s in top10:
        s["news"] = get_yahoo_news(s["ticker"])
        time.sleep(0.3)

    # --- Step 4: HTML ---
    log.info("Step 4 – Generating HTML report …")
    html = generate_html(top10, report_date)

    with open("index.html", "w", encoding="utf-8") as fh:
        fh.write(html)

    log.info("Report written → index.html")
    log.info("Top 10: %s", [s["ticker"] for s in top10])


if __name__ == "__main__":
    main()
