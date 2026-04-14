#!/usr/bin/env python3
"""
KI-Agent — ki_agent.py

Läuft alle 30 Minuten, 24/7.
Überwacht die aktuellen Top-10-Kandidaten auf Squeeze-Trigger aus mehreren
kostenlosen Quellen und sendet Alert-E-Mails bei relevanten Signalen.

Datenquellen:
  1. Yahoo Finance (yfinance)   — Kurs, Intraday-Volumen, Rel. Volumen, Spanne
  2. Yahoo Finance News RSS     — Schlagzeilen
  3. Reddit (public JSON API)   — Erwähnungen + Sentiment in WSB/stocks/shortsqueeze
  4. SEC EDGAR RSS              — neue 8-K-Meldungen, inhaltlich gewichtet
  5. Finviz News RSS            — alternative Nachrichtenquelle
  6. yfinance calendar          — Earnings-Datum je Ticker
  7. FDA Press Release RSS      — PDUFA-Meldungen (kein Bot-Schutz)
  8. OpenInsider RSS            — Insider-Käufe (letzte 30 Tage)
  9. FINRA Daily Short Volume   — Short-Volumenanteil je Ticker (kostenlos)
 10. SEC Form 4                 — Insider-Transaktionsmeldungen (7-Tage-Fenster)

Outputs:
  agent_signals.json  — Signal-Score + insider_buy-Flag je Ticker, gelesen von der Website
  agent_state.json    — Cooldown-Tracking, committet nach jedem Run
"""

import json
import logging
import os
import re
import smtplib
import time
import xml.etree.ElementTree as ET
from datetime import datetime, time as dt_time, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

# ── Konfiguration — alle Schwellen hier ändern, nirgendwo sonst ──────────────
ALERT_THRESHOLD         = 25      # Score ≥ → Alert senden
ALERT_THRESHOLD_STRONG  = 70      # Score ≥ → Starker Alert (⚡⚡)
ALERT_COOLDOWN_HOURS    = 2       # Mindeststunden zwischen zwei Alerts je Ticker

# Score-Punkte je Signal
SCORE_PRICE_UP_3        = 15      # Kursanstieg ≥ 3 % intraday
SCORE_PRICE_UP_7        = 25      # Kursanstieg ≥ 7 % intraday (ersetzt 15)
SCORE_RVOL_2X           = 15      # Rel. Volumen ≥ 2×
SCORE_RVOL_4X           = 25      # Rel. Volumen ≥ 4× (ersetzt 15)
SCORE_INTRADAY_RANGE    = 10      # (Hoch−Tief)/Open ≥ 5 %
SCORE_REDDIT_5          = 10      # Reddit-Erwähnungen ≥ 5 in 4h
SCORE_REDDIT_15         = 20      # Reddit-Erwähnungen ≥ 15 in 4h (ersetzt 10)
SCORE_REDDIT_SENTIMENT  = 10      # Positiver Sentiment-Score ≥ 0.3
SCORE_SEC_8K            = 15      # Neue 8-K-Meldung in letzten 24h
SCORE_SEC_8K_RELEVANT   = 25      # 8-K mit Earnings/FDA-Keywords → erhöhter Bonus
SCORE_NEWS_KEYWORD      = 10      # News-Keyword-Treffer (je Treffer, max 20 Pkt)

# Auslöse-Schwellen (Trigger)
TRIGGER_PRICE_UP_3      = 2.0     # Kursanstieg ab 2 % → SCORE_PRICE_UP_3
TRIGGER_PRICE_UP_7      = 5.0     # Kursanstieg ab 5 % → SCORE_PRICE_UP_7
TRIGGER_RVOL_2X         = 1.5     # Rel. Volumen ab 1,5× → SCORE_RVOL_2X
TRIGGER_RVOL_4X         = 3.0     # Rel. Volumen ab 3× → SCORE_RVOL_4X

# Earnings-Nähe-Punkte (Tage bis Earnings)
SCORE_EARNINGS_NEAR     = 25      # Earnings in ≤ EARNINGS_NEAR_DAYS Tagen
SCORE_EARNINGS_MID      = 15      # Earnings in ≤ EARNINGS_MID_DAYS Tagen
SCORE_EARNINGS_FAR      = 8       # Earnings in ≤ EARNINGS_FAR_DAYS Tagen
EARNINGS_NEAR_DAYS      = 3
EARNINGS_MID_DAYS       = 7
EARNINGS_FAR_DAYS       = 30

# FDA PDUFA-Nähe-Punkte
SCORE_PDUFA_NEAR        = 25      # PDUFA in 1–7 Tagen
SCORE_PDUFA_MID         = 15      # PDUFA in 8–30 Tagen

# Konfidenz-Berechnung
MAX_SIGNAL_TYPES        = 6   # Anzahl der betrachteten Signalkategorien
CONFIDENCE_CAP_SINGLE   = 40  # max. Konfidenz wenn nur 1 Signaltyp aktiv
CONFIDENCE_MIN_MULTI    = 70  # min. Konfidenz wenn ≥ 3 Signaltypen aktiv

# Tägliche Zusammenfassung (Optimierung 14)
SEND_DAILY_SUMMARY       = True   # Tages-Zusammenfassung um ~16:30 ET senden
DAILY_SUMMARY_HOUR_ET    = 16     # Stunde (ET) für Zusammenfassung
DAILY_SUMMARY_MINUTE_ET  = 30     # Minute (ET) für Zusammenfassung
DAILY_SUMMARY_WINDOW_MIN = 5      # ±Minuten Toleranzfenster

NEWS_KEYWORDS = {
    "squeeze", "short squeeze", "short interest",
    "analyst upgrade", "earnings beat",
    "short seller", "covering", "gamma squeeze", "options activity",
    "unusual volume", "breakout", "catalyst", "fda approval",
    "merger", "acquisition", "buyout", "takeover", "partnership",
    "contract", "revenue beat", "guidance raised", "insider buying",
    "institutional buying", "short covering", "forced liquidation",
    "margin call", "halt", "circuit breaker", "activist investor",
}
SEC_RELEVANT_KEYWORDS = {
    "earnings", "revenue", "results", "approval", "fda",
    "pdufa", "nda", "bla", "guidance", "outlook",
}
REDDIT_POSITIVE   = {"squeeze", "moon", "calls", "breakout", "short"}
REDDIT_NEGATIVE   = {"puts", "short", "crash", "dump"}
REDDIT_SUBS       = ["wallstreetbets", "stocks", "shortsqueeze"]
REDDIT_LOOKBACK_H = 4

# OpenInsider — Insider-Käufe
INSIDER_LOOKBACK_DAYS   = 30      # Tage zurück für Insider-Käufe
SCORE_INSIDER_BUY       = 20      # Insider-Kauf (beliebiger Insider)
SCORE_INSIDER_CSUITE    = 30      # C-Suite Insider-Kauf (CEO/CFO/President/etc.)

# FINRA Daily Short Sale Volume
FINRA_DAILY_SSR_MID     = 0.50    # Short-Volumenanteil ≥ 50 % → mittleres Signal
FINRA_DAILY_SSR_HIGH    = 0.70    # Short-Volumenanteil ≥ 70 % → starkes Signal
SCORE_FINRA_SSR_MID     = 15
SCORE_FINRA_SSR_HIGH    = 25

# SEC Form 4 — Insider-Transaktionen
FORM4_LOOKBACK_DAYS     = 7
SCORE_FORM4_ANY         = 10      # Beliebige Form-4-Einreichung
SCORE_FORM4_PURCHASE    = 20      # Form-4 mit Kauf ("Purchase"/"Acquisition")

# ── Dateipfade ────────────────────────────────────────────────────────────────
STATE_FILE   = Path("agent_state.json")
SIGNALS_FILE = Path("agent_signals.json")
INDEX_HTML   = Path("index.html")
PWA_URL      = "https://easywebb911.github.io/Aktien-Update/"

BERLIN  = ZoneInfo("Europe/Berlin")
EASTERN = ZoneInfo("America/New_York")

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
REDDIT_HEADERS = {"User-Agent": "SqueezeAgent/1.0"}
SEC_HEADERS    = {"User-Agent": "SqueezeReport/1.0 github-actions@squeeze-report.com"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


# ── Zeitzonen-Hilfsfunktionen ─────────────────────────────────────────────────

def now_berlin() -> datetime:
    return datetime.now(BERLIN)


def get_market_phase() -> str:
    """Gibt die aktuelle US-Marktphase zurück (Eastern Time)."""
    now_et = datetime.now(EASTERN)
    if now_et.weekday() >= 5:
        return "Geschlossen"
    mins = now_et.hour * 60 + now_et.minute
    if 4 * 60 <= mins < 9 * 60 + 30:
        return "Pre-Market"
    if 9 * 60 + 30 <= mins < 16 * 60:
        return "Regulär"
    if 16 * 60 <= mins < 20 * 60:
        return "After-Hours"
    return "Geschlossen"


# ── index.html parsen → Top-10-Ticker ─────────────────────────────────────────

def parse_top_tickers() -> list[str]:
    """Extrahiert Ticker aus dem aktuellen index.html."""
    if not INDEX_HTML.exists():
        log.error("index.html nicht gefunden.")
        return []
    html = INDEX_HTML.read_text(encoding="utf-8")
    tickers = re.findall(r'<span class="ticker">([^<]+)</span>', html)
    # Ticker können Flag-Emoji enthalten — nur ASCII-Buchstaben/Zahlen/./-
    clean = []
    for t in tickers:
        m = re.search(r'[A-Z0-9][A-Z0-9.\-]+', t.strip().upper())
        if m and m.group() not in clean:
            clean.append(m.group())
    log.info("Top-Ticker aus index.html: %s", clean)
    return clean


# ── Zustand laden/speichern ───────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_run": None, "cooldowns": {}}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def is_on_cooldown(ticker: str, state: dict) -> bool:
    ts = state.get("cooldowns", {}).get(ticker)
    if not ts:
        return False
    last = datetime.fromisoformat(ts)
    return (now_berlin() - last).total_seconds() < ALERT_COOLDOWN_HOURS * 3600


def set_cooldown(ticker: str, state: dict) -> None:
    state.setdefault("cooldowns", {})[ticker] = now_berlin().isoformat()


# ── Signale laden/speichern ───────────────────────────────────────────────────

def load_signals() -> dict:
    if SIGNALS_FILE.exists():
        try:
            return json.loads(SIGNALS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"updated": None, "run_info": {}, "signals": {}}


def save_signals(signals: dict) -> None:
    SIGNALS_FILE.write_text(
        json.dumps(signals, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Datenquelle 1: yfinance ───────────────────────────────────────────────────

def fetch_yfinance(tickers: list[str]) -> dict[str, dict]:
    """Batch-Download für alle Ticker. Gibt Dict ticker→Daten zurück."""
    if not tickers:
        return {}
    results: dict[str, dict] = {}
    try:
        hist = yf.download(
            tickers, period="5d", auto_adjust=True,
            threads=True, progress=False,
        )
        multi = len(tickers) > 1
        for t in tickers:
            try:
                df = hist[t] if multi else hist
                if df is None or df.empty or len(df) < 2:
                    continue
                df = df.dropna(subset=["Close","Volume"])
                avg_vol  = float(df["Volume"].iloc[:-1].mean())
                cur_vol  = float(df["Volume"].iloc[-1])
                rvol     = round(cur_vol / avg_vol, 2) if avg_vol > 0 else 0.0
                close    = float(df["Close"].iloc[-1])
                prev     = float(df["Close"].iloc[-2])
                chg_pct  = round((close - prev) / prev * 100, 2) if prev > 0 else 0.0
                high_    = float(df["High"].iloc[-1])
                low_     = float(df["Low"].iloc[-1])
                open_    = float(df["Open"].iloc[-1])
                intraday = round((high_ - low_) / open_ * 100, 2) if open_ > 0 else 0.0
                results[t] = {
                    "price":    round(close, 2),
                    "chg_pct":  chg_pct,
                    "rvol":     rvol,
                    "intraday": intraday,
                }
            except Exception as exc:
                log.debug("yfinance slice %s: %s", t, exc)
    except Exception as exc:
        log.warning("yfinance batch Fehler: %s", exc)
    return results


# ── Datenquelle 2: Yahoo Finance News RSS ─────────────────────────────────────

def fetch_yahoo_news(ticker: str) -> list[str]:
    """Gibt bis zu 5 Schlagzeilen aus dem Yahoo Finance RSS-Feed zurück."""
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}"
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        titles = []
        for item in root.iter("item"):
            title = item.findtext("title") or ""
            if title:
                titles.append(title)
            if len(titles) >= 5:
                break
        return titles
    except Exception as exc:
        log.debug("Yahoo RSS %s: %s", ticker, exc)
        return []


# ── Datenquelle 3: Reddit öffentliche JSON-API ────────────────────────────────

def fetch_reddit_mentions(ticker: str) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=REDDIT_LOOKBACK_H)
    total_posts  = 0
    pos_score    = 0
    neg_score    = 0

    for sub in REDDIT_SUBS:
        url = (
            f"https://old.reddit.com/r/{sub}/search.json"
            f"?q={ticker}&sort=new&restrict_sr=1&limit=25&t=day"
        )
        try:
            resp = requests.get(url, headers=REDDIT_HEADERS, timeout=12)
            if resp.status_code == 403:
                log.info("Reddit: geblockt — Score 0.")
                return {"count": 0, "sentiment": 0.0, "blocked": True}
            resp.raise_for_status()
            posts = resp.json().get("data", {}).get("children", [])
            for post in posts:
                d = post.get("data", {})
                created = d.get("created_utc", 0)
                if datetime.fromtimestamp(created, tz=timezone.utc) < cutoff:
                    continue
                text = (
                    (d.get("title") or "") + " " + (d.get("selftext") or "")
                ).lower()
                if ticker.lower() not in text and ticker.split(".")[0].lower() not in text:
                    continue
                total_posts += 1
                words = re.findall(r"\w+", text)
                pos_score += sum(1 for w in words if w in REDDIT_POSITIVE)
                neg_score += sum(1 for w in words if w in REDDIT_NEGATIVE)
            time.sleep(0.5)
        except Exception as exc:
            pass

    sentiment = 0.0
    if total_posts > 0:
        total_kw = pos_score + neg_score
        sentiment = round((pos_score - neg_score) / total_kw, 3) if total_kw > 0 else 0.0

    return {"count": total_posts, "sentiment": sentiment}


# ── Datenquelle 4: SEC EDGAR RSS ─────────────────────────────────────────────

def fetch_sec_8k(ticker: str) -> tuple[bool, str]:
    """Returns (has_recent_8k, title_of_8k). Title is '' if none found."""
    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcompany&CIK={ticker}&type=8-K"
        "&dateb=&owner=include&count=5&search_text=&output=atom"
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    time.sleep(0.5)
    try:
        resp = requests.get(url, headers=SEC_HEADERS, timeout=12)
        if resp.status_code == 403:
            log.debug("EDGAR %s: 403 geblockt — übersprungen.", ticker)
            return False, ""
        resp.raise_for_status()
        text = re.sub(r' xmlns="[^"]+"', "", resp.text, count=1)
        root = ET.fromstring(text)
        for entry in root.findall("entry"):
            updated = entry.findtext("updated") or ""
            try:
                dt = datetime.fromisoformat(updated)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt > cutoff:
                    title = entry.findtext("title") or ""
                    return True, title
            except Exception:
                continue
    except Exception as exc:
        pass
    return False, ""


# ── Datenquelle 5: Finviz News RSS ────────────────────────────────────────────

def fetch_finviz_news(ticker: str) -> list[str]:
    url = f"https://finviz.com/rss.ashx?t={ticker}"
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        titles = []
        for item in root.iter("item"):
            title = item.findtext("title") or ""
            if title:
                titles.append(title)
            if len(titles) >= 5:
                break
        return titles
    except Exception as exc:
        log.debug("Finviz RSS %s: %s", ticker, exc)
        return []


# ── Datenquelle 8: Google News RSS ───────────────────────────────────────────

def fetch_google_news(ticker: str) -> list[str]:
    base = ticker.split(".")[0]
    url = f"https://news.google.com/rss/search?q={base}+stock&hl=en-US&gl=US&ceid=US:en"
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        titles = []
        for item in root.iter("item"):
            title = item.findtext("title") or ""
            if title:
                titles.append(title)
            if len(titles) >= 5:
                break
        return titles
    except Exception:
        return []


# ── Datenquelle 9: Unusual Whales RSS ────────────────────────────────────────

def fetch_unusual_whales(ticker: str) -> list[str]:
    base = ticker.split(".")[0]
    url = f"https://unusualwhales.com/rss/ticker/{base}"
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        titles = []
        for item in root.iter("item"):
            title = item.findtext("title") or ""
            if title:
                titles.append(title)
            if len(titles) >= 5:
                break
        return titles
    except Exception:
        return []


# ── Datenquelle 10: MarketBeat RSS ───────────────────────────────────────────

def fetch_marketbeat_news(ticker: str) -> list[str]:
    base = ticker.split(".")[0]
    url = f"https://www.marketbeat.com/stocks/NASDAQ/{base}/rss/"
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        titles = []
        for item in root.iter("item"):
            title = item.findtext("title") or ""
            if title:
                titles.append(title)
            if len(titles) >= 5:
                break
        return titles
    except Exception:
        return []


# ── Datenquelle 11: Seeking Alpha RSS ────────────────────────────────────────

def fetch_seeking_alpha_news(ticker: str) -> list[str]:
    base = ticker.split(".")[0]
    url = f"https://seekingalpha.com/api/sa/combined/{base}.xml"
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        titles = []
        for item in root.iter("item"):
            title = item.findtext("title") or ""
            if title:
                titles.append(title)
            if len(titles) >= 5:
                break
        return titles
    except Exception:
        return []


# ── Datenquelle 6: Earnings-Datum via yfinance ───────────────────────────────

def fetch_earnings_date(ticker: str) -> tuple[int | None, str | None]:
    """Gibt (Tage_bis_Earnings, Datum_String_DE) zurück oder (None, None)."""
    try:
        cal = yf.Ticker(ticker).calendar
        if cal is None:
            return None, None
        # Neuere yfinance: DataFrame mit Dates als Spalten oder als dict
        dates: list = []
        if isinstance(cal, pd.DataFrame) and not cal.empty:
            # Spalten sind Timestamps/Dates — nimm alle als Kandidaten
            dates = list(cal.columns)
        elif isinstance(cal, dict):
            raw = cal.get("Earnings Date") or cal.get("earningsDate") or []
            if not isinstance(raw, list):
                raw = [raw]
            dates = raw
        today = datetime.now(EASTERN).date()
        for d in dates:
            try:
                edate = pd.Timestamp(d).date()
                days = (edate - today).days
                if days >= 0:
                    return days, edate.strftime("%d.%m.%Y")
            except Exception:
                continue
    except Exception as exc:
        log.debug("Earnings-Datum %s: %s", ticker, exc)
    return None, None


# ── Datenquelle 7: FDA Press Release RSS ─────────────────────────────────────

_FDA_RSS      = "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml"
_PDUFA_KW     = {"pdufa", "approv", "nda", "bla"}
_TICKER_PAT   = re.compile(r'\b([A-Z]{2,6})\b')
_SKIP_WORDS   = {
    "FDA", "NDA", "BLA", "IND", "USA", "NEW", "THE", "FOR", "AND",
    "WITH", "DRUG", "NOT", "ITS", "HAS", "ARE", "CAN", "MAY",
}


def fetch_fda_calendar() -> dict[str, str]:
    """Gibt {TICKER: 'YYYY-MM-DD'} aus dem FDA Press Release RSS zurück.

    Sucht nach Einträgen der letzten 30 Tage, die PDUFA/Approval-Keywords
    im Titel enthalten, und extrahiert Ticker-ähnliche Symbole.
    Gibt leeres Dict zurück falls RSS nicht erreichbar.
    """
    from email.utils import parsedate_to_datetime

    try:
        resp = requests.get(_FDA_RSS, headers=HTTP_HEADERS, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        results: dict[str, str] = {}
        today = datetime.now(timezone.utc).date()
        cutoff = today - timedelta(days=30)

        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            pub_date_str = (item.findtext("pubDate") or "").strip()

            if not any(kw in title.lower() for kw in _PDUFA_KW):
                continue

            try:
                pub_date = parsedate_to_datetime(pub_date_str).date()
            except Exception:
                pub_date = today

            if pub_date < cutoff:
                continue

            for m in _TICKER_PAT.finditer(title):
                sym = m.group(1)
                if sym not in _SKIP_WORDS:
                    results[sym] = pub_date.isoformat()

        log.info("FDA Press Release RSS: %d PDUFA-relevante Einträge geparst.", len(results))
        return results
    except Exception as exc:
        log.info("FDA RSS nicht erreichbar: %s", exc)
        pass
        return {}


# ── Datenquelle 8: OpenInsider RSS ───────────────────────────────────────────

def fetch_openinsider(ticker: str) -> dict:
    """Sucht Insider-Käufe via OpenInsider RSS (letzte INSIDER_LOOKBACK_DAYS Tage).

    Returns {'count': int, 'csuite': bool}.
    Nur für US-Ticker sinnvoll.
    """
    from email.utils import parsedate_to_datetime

    base = ticker.split(".")[0]
    url = f"https://openinsider.com/rss?s={base}"
    cutoff = datetime.now(timezone.utc) - timedelta(days=INSIDER_LOOKBACK_DAYS)
    CSUITE_TITLES = {"ceo", "cfo", "coo", "president", "chairman", "chief"}

    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        count = 0
        csuite = False

        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip().lower()
            desc  = (item.findtext("description") or "").strip().lower()
            combined = title + " " + desc

            # Date check via pubDate
            pub_str = (item.findtext("pubDate") or "").strip()
            if pub_str:
                try:
                    pub_date = parsedate_to_datetime(pub_str)
                    if pub_date.tzinfo is None:
                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                    if pub_date < cutoff:
                        continue
                except Exception:
                    pass

            # Must indicate a purchase; skip pure sales
            is_purchase = "purchase" in combined or " buy " in combined
            is_sale     = "sale" in combined and "purchase" not in combined
            if not is_purchase or is_sale:
                continue

            count += 1
            if any(t in combined for t in CSUITE_TITLES):
                csuite = True

        return {"count": count, "csuite": csuite}
    except Exception:
        return {"count": 0, "csuite": False}


# ── Datenquelle 9: FINRA Daily Short Sale Volume ─────────────────────────────

_FINRA_SSR_CACHE: dict[str, dict[str, float]] = {}


def fetch_finra_ssr(tickers: list[str]) -> dict[str, float]:
    """Lädt FINRA Daily Short Sale Volume und gibt {SYMBOL: ratio} zurück.

    ratio = ShortVolume / TotalVolume.
    Gecacht pro Datum — wird einmalig pro Agent-Run geladen.
    URL: https://cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt
    """
    global _FINRA_SSR_CACHE

    today = datetime.now(timezone.utc).date()
    base_symbols = {t.split(".")[0].upper() for t in tickers}

    # Try today and up to 4 prior days (weekends / holidays)
    for days_back in range(5):
        date     = today - timedelta(days=days_back)
        date_str = date.strftime("%Y%m%d")

        if date_str in _FINRA_SSR_CACHE:
            log.debug("FINRA SSR Cache-Hit für %s", date_str)
            return _FINRA_SSR_CACHE[date_str]

        url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date_str}.txt"
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=15)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()

            result: dict[str, float] = {}
            for line in resp.text.strip().split("\n")[1:]:  # skip header
                parts = line.split("|")
                if len(parts) < 5:
                    continue
                sym = parts[1].strip().upper()
                if sym not in base_symbols:
                    continue
                try:
                    short_vol = int(parts[2])
                    total_vol = int(parts[4])
                    if total_vol > 0:
                        result[sym] = round(short_vol / total_vol, 4)
                except (ValueError, IndexError):
                    continue

            log.info("FINRA SSR Daten geladen (%s): %d relevante Ticker", date_str, len(result))
            _FINRA_SSR_CACHE[date_str] = result
            return result
        except Exception as exc:
            log.debug("FINRA SSR %s: %s", date_str, exc)
            continue

    log.info("FINRA SSR: keine Daten verfügbar (letzte 5 Tage).")
    empty: dict[str, float] = {}
    _FINRA_SSR_CACHE[today.strftime("%Y%m%d")] = empty
    return empty


# ── Datenquelle 10: SEC Form 4 ────────────────────────────────────────────────

def fetch_sec_form4(ticker: str) -> tuple[bool, str]:
    """Sucht SEC Form 4 (Insider-Transaktionen) in den letzten FORM4_LOOKBACK_DAYS Tagen.

    Returns (has_recent_form4, title). Title is '' if none found.
    Nur für US-Ticker; nutzt dieselbe EDGAR-Infrastruktur wie fetch_sec_8k.
    """
    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcompany&CIK={ticker}&type=4"
        "&dateb=&owner=include&count=5&search_text=&output=atom"
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=FORM4_LOOKBACK_DAYS)
    time.sleep(0.3)
    try:
        resp = requests.get(url, headers=SEC_HEADERS, timeout=12)
        if resp.status_code == 403:
            log.debug("EDGAR Form4 %s: 403 geblockt — übersprungen.", ticker)
            return False, ""
        resp.raise_for_status()
        text = re.sub(r' xmlns="[^"]+"', "", resp.text, count=1)
        root = ET.fromstring(text)
        for entry in root.findall("entry"):
            updated = entry.findtext("updated") or ""
            try:
                dt = datetime.fromisoformat(updated)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt > cutoff:
                    title = entry.findtext("title") or ""
                    return True, title
            except Exception:
                continue
    except Exception as exc:
        log.debug("EDGAR Form4 %s: %s", ticker, exc)
    return False, ""


# ── Signal-Score berechnen ────────────────────────────────────────────────────

def compute_signal(
    ticker: str,
    yf_data: dict,
    news: list[str],
    reddit: dict,
    has_8k: bool,
    sec_title: str,
    earnings_days: int | None,
    fda_days: int | None,
    insider: dict | None = None,
    finra_ssr_ratio: float = 0.0,
    has_form4: bool = False,
    form4_title: str = "",
) -> tuple[int, list[str], int]:
    score   = 0
    drivers = []

    # ── 6 Signalkategorien für Konfidenz-Berechnung ──────────────────────────
    sig_kurs    = False  # 1. Kursbewegung
    sig_vol     = False  # 2. Volumen
    sig_spanne  = False  # 3. Intraday-Spanne
    sig_reddit  = False  # 4. Reddit
    sig_news    = False  # 5. News / SEC 8-K
    sig_insider = False  # 6. Insider / Termine (SEC Form4, Earnings, FDA, FINRA-SSR)

    chg  = yf_data.get("chg_pct", 0.0)
    rvol = yf_data.get("rvol", 0.0)
    intr = yf_data.get("intraday", 0.0)

    if chg >= TRIGGER_PRICE_UP_7:
        score += SCORE_PRICE_UP_7
        drivers.append(f"Kurs +{chg:.1f}%")
        sig_kurs = True
    elif chg >= TRIGGER_PRICE_UP_3:
        score += SCORE_PRICE_UP_3
        drivers.append(f"Kurs +{chg:.1f}%")
        sig_kurs = True

    if rvol >= TRIGGER_RVOL_4X:
        score += SCORE_RVOL_4X
        drivers.append(f"Volumen {rvol:.1f}×")
        sig_vol = True
    elif rvol >= TRIGGER_RVOL_2X:
        score += SCORE_RVOL_2X
        drivers.append(f"Volumen {rvol:.1f}×")
        sig_vol = True

    if intr >= 5:
        score += SCORE_INTRADAY_RANGE
        drivers.append(f"Spanne {intr:.1f}%")
        sig_spanne = True

    rc = reddit.get("count", 0)
    rs = reddit.get("sentiment", 0.0)
    if rc >= 15:
        score += SCORE_REDDIT_15
        drivers.append(f"Reddit +{rc} Erwähnungen")
        sig_reddit = True
    elif rc >= 5:
        score += SCORE_REDDIT_5
        drivers.append(f"Reddit +{rc} Erwähnungen")
        sig_reddit = True
    if rs >= 0.3:
        score += SCORE_REDDIT_SENTIMENT
        drivers.append(f"Reddit-Sentiment {rs:.2f}")
        sig_reddit = True

    if has_8k:
        title_lower = sec_title.lower()
        is_relevant = any(kw in title_lower for kw in SEC_RELEVANT_KEYWORDS)
        pts = SCORE_SEC_8K_RELEVANT if is_relevant else SCORE_SEC_8K
        score += pts
        drivers.append("SEC 8-K")
        sig_news = True
        print(f"{ticker} SEC 8-K: '{sec_title}' → +{pts} Pkt "
              f"(earnings/FDA-relevant: {'ja' if is_relevant else 'nein'})")

    kw_pts = 0
    kw_hits: list[str] = []
    all_headlines = " ".join(news).lower()
    for kw in NEWS_KEYWORDS:
        if kw in all_headlines and kw_pts < 20:
            kw_pts += SCORE_NEWS_KEYWORD
            kw_hits.append(kw)
    if kw_pts > 0:
        score += min(kw_pts, 20)
        drivers.append(f"News: {', '.join(kw_hits)}")
        sig_news = True

    # Earnings-Nähe
    if earnings_days is not None:
        if earnings_days <= EARNINGS_NEAR_DAYS:
            pts = SCORE_EARNINGS_NEAR
        elif earnings_days <= EARNINGS_MID_DAYS:
            pts = SCORE_EARNINGS_MID
        elif earnings_days <= EARNINGS_FAR_DAYS:
            pts = SCORE_EARNINGS_FAR
        else:
            pts = 0
        if pts > 0:
            score += pts
            drivers.append(f"Earnings in {earnings_days}d")
            sig_insider = True
            print(f"{ticker} Earnings in {earnings_days} Tagen → +{pts} Pkt")

    # FDA PDUFA-Nähe
    if fda_days is not None:
        if fda_days <= 7:
            pts = SCORE_PDUFA_NEAR
        elif fda_days <= 30:
            pts = SCORE_PDUFA_MID
        else:
            pts = 0
        if pts > 0:
            score += pts
            drivers.append(f"FDA PDUFA in {fda_days}d")
            sig_insider = True
            print(f"{ticker} FDA PDUFA in {fda_days} Tagen → +{pts} Pkt")

    # OpenInsider — Insider-Käufe
    if insider and insider.get("count", 0) > 0:
        ic      = insider["count"]
        ic_cs   = insider.get("csuite", False)
        pts     = SCORE_INSIDER_CSUITE if ic_cs else SCORE_INSIDER_BUY
        label   = "C-Suite Insider-Kauf" if ic_cs else f"Insider-Kauf ({ic}×)"
        score  += pts
        drivers.append(label)
        sig_insider = True
        print(f"{ticker} OpenInsider: {ic} Käufe, C-Suite: {ic_cs} → +{pts} Pkt")

    # FINRA Daily Short Sale Volume
    if finra_ssr_ratio >= FINRA_DAILY_SSR_HIGH:
        score += SCORE_FINRA_SSR_HIGH
        drivers.append(f"FINRA Short-Vol {finra_ssr_ratio:.0%}")
        sig_insider = True
        print(f"{ticker} FINRA SSR: {finra_ssr_ratio:.1%} → +{SCORE_FINRA_SSR_HIGH} Pkt")
    elif finra_ssr_ratio >= FINRA_DAILY_SSR_MID:
        score += SCORE_FINRA_SSR_MID
        drivers.append(f"FINRA Short-Vol {finra_ssr_ratio:.0%}")
        sig_insider = True
        print(f"{ticker} FINRA SSR: {finra_ssr_ratio:.1%} → +{SCORE_FINRA_SSR_MID} Pkt")

    # SEC Form 4 — Insider-Transaktionen
    if has_form4:
        form4_lower  = form4_title.lower()
        is_purchase  = "purchase" in form4_lower or "acquisition" in form4_lower
        pts          = SCORE_FORM4_PURCHASE if is_purchase else SCORE_FORM4_ANY
        score       += pts
        drivers.append("SEC Form 4 (Kauf)" if is_purchase else "SEC Form 4")
        sig_insider = True
        print(f"{ticker} SEC Form 4: '{form4_title}' → +{pts} Pkt "
              f"(Kauf: {'ja' if is_purchase else 'nein'})")

    # ── Konfidenz-Berechnung ─────────────────────────────────────────────────
    n_types   = sum([sig_kurs, sig_vol, sig_spanne, sig_reddit, sig_news, sig_insider])
    base_conf = round(n_types / MAX_SIGNAL_TYPES * 100)
    if n_types <= 1:
        confidence = min(base_conf, CONFIDENCE_CAP_SINGLE)
    elif n_types >= 3:
        confidence = max(base_conf, CONFIDENCE_MIN_MULTI)
    else:
        confidence = base_conf

    print(f"{ticker} Konfidenz: {confidence}% ({n_types}/{MAX_SIGNAL_TYPES} Signaltypen aktiv)",
          flush=True)

    return min(score, 100), drivers, confidence


# ── E-Mail-Versand ────────────────────────────────────────────────────────────

def send_alert(
    ticker: str,
    score: int,
    drivers: list[str],
    yf_data: dict,
    reddit: dict,
    news: list[str],
    upcoming_event: str | None = None,
    insider: dict | None = None,
    confidence: int = 0,
    n_types: int = 0,
) -> bool:
    mail_to   = os.environ.get("MAIL_TO", "").strip()
    mail_pass = os.environ.get("MAIL_PASSWORD", "").strip()
    mail_from = os.environ.get("MAIL_FROM", mail_to).strip()

    if not mail_to or not mail_pass:
        log.warning("MAIL_TO / MAIL_PASSWORD nicht gesetzt — kein E-Mail für %s.", ticker)
        return False

    uhrzeit   = now_berlin().strftime("%H:%M")
    prefix    = "⚡⚡" if score >= ALERT_THRESHOLD_STRONG else "⚡"
    subject   = f"{prefix} Squeeze-Alert — {ticker} — Score {score}/100 — {uhrzeit}"

    chg   = yf_data.get("chg_pct", 0.0)
    rvol  = yf_data.get("rvol", 0.0)
    price = yf_data.get("price", 0.0)
    sign  = "+" if chg >= 0 else ""
    top_headline = news[0] if news else "—"
    driver_str   = " + ".join(drivers) if drivers else "—"
    sentiment    = reddit.get("sentiment", 0.0)
    rc           = reddit.get("count", 0)

    event_block = (
        f"⚠️  Wichtiger Termin: {upcoming_event} — erhöhtes Squeeze-Potential\n\n"
        if upcoming_event else ""
    )

    insider_block = ""
    if insider and insider.get("count", 0) > 0:
        ic         = insider["count"]
        csuite_str = " (C-Suite)" if insider.get("csuite") else ""
        insider_block = (
            f"🏦 Insider-Käufe:   {ic} in den letzten {INSIDER_LOOKBACK_DAYS} Tagen"
            f"{csuite_str}\n\n"
        )

    conf_line = (
        f"Konfidenz:        {confidence}% ({n_types} von {MAX_SIGNAL_TYPES} Signaltypen aktiv)\n"
        if confidence > 0 else ""
    )

    body = (
        f"{prefix} SQUEEZE-ALERT: {ticker}\n"
        f"{'=' * 55}\n\n"
        f"{event_block}"
        f"{insider_block}"
        f"Score:            {score}/100\n"
        f"{conf_line}"
        f"Treiber:          {driver_str}\n\n"
        f"Kurs:             ${price:.2f}  ({sign}{chg:.1f}% heute)\n"
        f"Rel. Volumen:     {rvol:.1f}×\n"
        f"Reddit:           {rc} Erwähnungen | Sentiment {sentiment:+.2f}\n"
        f"Neueste Meldung:  {top_headline}\n\n"
        f"→ Website: {PWA_URL}\n\n"
        f"---\n"
        f"Cooldown: {ALERT_COOLDOWN_HOURS}h zwischen zwei Alerts je Aktie."
    )

    msg = MIMEMultipart()
    msg["From"]    = mail_from
    msg["To"]      = mail_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(mail_from, mail_pass)
            srv.sendmail(mail_from, [mail_to], msg.as_string())
        log.info("✉ Alert gesendet: %s Score=%d", ticker, score)
        return True
    except Exception as exc:
        log.error("E-Mail Fehler %s: %s", ticker, exc)
        return False


# ── Tägliche Zusammenfassung ──────────────────────────────────────────────────

def _is_summary_window() -> bool:
    """Gibt True zurück wenn wir im ±DAILY_SUMMARY_WINDOW_MIN Fenster um 16:30 ET sind."""
    now_et = datetime.now(EASTERN)
    target = now_et.replace(
        hour=DAILY_SUMMARY_HOUR_ET,
        minute=DAILY_SUMMARY_MINUTE_ET,
        second=0,
        microsecond=0,
    )
    diff_min = abs((now_et - target).total_seconds()) / 60
    return diff_min <= DAILY_SUMMARY_WINDOW_MIN


def send_daily_summary(
    signals: dict[str, dict],
    tickers: list[str],
    phase: str,
    t_elapsed: float,
    n_alerts: int,
) -> bool:
    """Sendet die tägliche Zusammenfassung aller überwachten Ticker per E-Mail."""
    mail_to   = os.environ.get("MAIL_TO", "").strip()
    mail_pass = os.environ.get("MAIL_PASSWORD", "").strip()
    mail_from = os.environ.get("MAIL_FROM", mail_to).strip()

    if not mail_to or not mail_pass:
        log.warning("MAIL_TO / MAIL_PASSWORD nicht gesetzt — keine Tages-Zusammenfassung.")
        return False

    today_str = now_berlin().strftime("%d.%m.%Y")

    # Top-Ticker nach Score sortieren
    scored = sorted(
        [(t, signals.get(t, {})) for t in tickers],
        key=lambda x: x[1].get("score", 0),
        reverse=True,
    )
    n_active = sum(1 for _, s in scored if s.get("score", 0) >= ALERT_THRESHOLD)
    top_ticker = scored[0][0] if scored else "—"
    top_score  = scored[0][1].get("score", 0) if scored else 0

    subject = (
        f"📊 Tages-Zusammenfassung {today_str} — "
        f"{n_active} Signale — Top: {top_ticker} ({top_score}/100)"
    )

    lines = [
        f"📊 TAGES-ZUSAMMENFASSUNG — {today_str}",
        "=" * 55,
        f"Marktphase: {phase}",
        f"Laufzeit:   {t_elapsed}s | Alerts gesendet: {n_alerts}",
        "",
        f"{'Ticker':<10} {'Score':>5}  {'Konfidenz':>9}  {'Treiber'}",
        "-" * 70,
    ]
    for ticker, sig in scored:
        score      = sig.get("score", 0)
        conf       = sig.get("confidence")
        conf_str   = f"{conf}%" if conf is not None else "—"
        drivers    = sig.get("drivers", "—")
        flag       = " ⚡" if score >= ALERT_THRESHOLD else ""
        lines.append(f"{ticker:<10} {score:>5}/100  {conf_str:>9}  {drivers}{flag}")

    lines += [
        "",
        f"→ Website: {PWA_URL}",
        "",
        "---",
        f"Zusammenfassung automatisch um {DAILY_SUMMARY_HOUR_ET}:{DAILY_SUMMARY_MINUTE_ET:02d} ET generiert.",
    ]

    body = "\n".join(lines)
    msg  = MIMEMultipart()
    msg["From"]    = mail_from
    msg["To"]      = mail_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(mail_from, mail_pass)
            srv.sendmail(mail_from, [mail_to], msg.as_string())
        log.info("✉ Tages-Zusammenfassung gesendet (%d Ticker, Top: %s %d/100)",
                 len(tickers), top_ticker, top_score)
        return True
    except Exception as exc:
        log.error("E-Mail Tages-Zusammenfassung Fehler: %s", exc)
        return False


# ── Hauptlogik ────────────────────────────────────────────────────────────────

def main() -> None:
    t_start = time.time()
    phase   = get_market_phase()
    print(f"Marktphase: {phase}", flush=True)

    now_str = now_berlin().strftime("%H:%M Uhr")
    log.info("=== KI-Agent Start %s — %s ===", now_berlin().strftime("%Y-%m-%d %H:%M"), phase)

    tickers = parse_top_tickers()
    if not tickers:
        log.warning("Keine Ticker gefunden — Abbruch.")
        return

    state      = load_state()
    old_sigs   = load_signals()
    new_signals: dict[str, dict] = {}

    log.info("yfinance Batch-Download für %d Ticker …", len(tickers))
    yf_batch = fetch_yfinance(tickers)

    log.info("FDA Press Release RSS wird abgerufen …")
    fda_calendar = fetch_fda_calendar()
    today_et = datetime.now(EASTERN).date()

    log.info("FINRA Daily Short Volume wird geladen …")
    finra_ssr_data = fetch_finra_ssr(tickers)

    reddit_ok      = True
    reddit_blocked = False
    sec_ok         = True
    n_alerts     = 0
    n_signals    = 0
    n_earnings   = 0
    n_fda        = 0
    n_sec_rel    = 0
    n_insider    = 0
    n_finra_ssr  = 0
    n_form4      = 0

    for ticker in tickers:
        log.info("Prüfe %s …", ticker)
        yfd = yf_batch.get(ticker, {})
        if not yfd:
            log.debug("  Keine yfinance-Daten für %s", ticker)

        yahoo_news  = fetch_yahoo_news(ticker)
        finviz_news = fetch_finviz_news(ticker)
        google_news, uw_news, mb_news, sa_news = [], [], [], []
        try:
            google_news = fetch_google_news(ticker)
        except Exception:
            pass
        try:
            uw_news = fetch_unusual_whales(ticker)
        except Exception:
            pass
        try:
            mb_news = fetch_marketbeat_news(ticker)
        except Exception:
            pass
        try:
            sa_news = fetch_seeking_alpha_news(ticker)
        except Exception:
            pass
        news = yahoo_news + finviz_news + google_news + uw_news + mb_news + sa_news
        print(f"{ticker} Quellen: Yahoo={len(yahoo_news)}, Google={len(google_news)}, "
              f"UnusualWhales={len(uw_news)}, MarketBeat={len(mb_news)}, "
              f"SeekingAlpha={len(sa_news)}", flush=True)

        reddit: dict = {"count": 0, "sentiment": 0.0}
        try:
            reddit = fetch_reddit_mentions(ticker)
            if reddit.get("blocked"):
                reddit_blocked = True
        except Exception as exc:
            log.debug("Reddit Fehler %s: %s", ticker, exc)
            reddit_ok = False

        has_8k    = False
        sec_title = ""
        is_us     = "." not in ticker
        if is_us:
            try:
                has_8k, sec_title = fetch_sec_8k(ticker)
                if has_8k:
                    title_lower = sec_title.lower()
                    if any(kw in title_lower for kw in SEC_RELEVANT_KEYWORDS):
                        n_sec_rel += 1
            except Exception as exc:
                log.debug("SEC Fehler %s: %s", ticker, exc)
                sec_ok = False

        # OpenInsider — Insider-Käufe
        insider: dict = {"count": 0, "csuite": False}
        if is_us:
            try:
                insider = fetch_openinsider(ticker)
                if insider.get("count", 0) > 0:
                    n_insider += 1
            except Exception as exc:
                log.debug("OpenInsider Fehler %s: %s", ticker, exc)

        # FINRA Daily Short Volume
        base_sym        = ticker.split(".")[0].upper()
        finra_ssr_ratio = finra_ssr_data.get(base_sym, 0.0)
        if finra_ssr_ratio >= FINRA_DAILY_SSR_MID:
            n_finra_ssr += 1

        # SEC Form 4 — Insider-Transaktionen
        has_form4   = False
        form4_title = ""
        if is_us:
            try:
                has_form4, form4_title = fetch_sec_form4(ticker)
                if has_form4:
                    n_form4 += 1
            except Exception as exc:
                log.debug("Form 4 Fehler %s: %s", ticker, exc)

        # Earnings-Datum
        earnings_days: int | None = None
        earnings_date_str: str | None = None
        try:
            earnings_days, earnings_date_str = fetch_earnings_date(ticker)
            if earnings_days is not None and earnings_days <= EARNINGS_FAR_DAYS:
                n_earnings += 1
        except Exception as exc:
            log.debug("Earnings Fehler %s: %s", ticker, exc)

        # FDA PDUFA-Datum aus Kalender
        fda_days: int | None = None
        fda_date_str: str | None = None
        base_ticker = ticker.split(".")[0].upper()
        if base_ticker in fda_calendar:
            try:
                fda_iso  = fda_calendar[base_ticker]
                fda_date = datetime.strptime(fda_iso, "%Y-%m-%d").date()
                fda_days = (fda_date - today_et).days
                fda_date_str = fda_date.strftime("%d.%m.%Y")
                if 0 <= fda_days <= 30:
                    n_fda += 1
            except Exception as exc:
                log.debug("FDA-Datum Parse %s: %s", ticker, exc)

        score, drivers, confidence = compute_signal(
            ticker, yfd, news, reddit, has_8k, sec_title,
            earnings_days, fda_days,
            insider=insider, finra_ssr_ratio=finra_ssr_ratio,
            has_form4=has_form4, form4_title=form4_title,
        )
        n_active_types = sum([
            any(d.startswith("Kurs") for d in drivers),
            any(d.startswith("Volumen") for d in drivers),
            any(d.startswith("Spanne") for d in drivers),
            any(d.startswith("Reddit") for d in drivers),
            any(d.startswith(("News", "SEC 8-K")) for d in drivers),
            any(d.startswith(("Earnings", "FDA", "Insider", "C-Suite", "FINRA", "SEC Form")) for d in drivers),
        ])
        log.info("  %s Score=%d Konfidenz=%d%% Treiber=%s",
                 ticker, score, confidence, " | ".join(drivers))

        # upcoming_event: nächster Termin ≤ 7 Tage (Earnings vor FDA)
        upcoming_event: str | None = None
        if earnings_days is not None and earnings_days <= 7 and earnings_date_str:
            upcoming_event = f"Earnings in {earnings_days} Tagen ({earnings_date_str})"
        elif fda_days is not None and 0 <= fda_days <= 7 and fda_date_str:
            upcoming_event = f"FDA PDUFA in {fda_days} Tagen ({fda_date_str})"

        # Termin-Hinweis als erster Treiber im Tooltip
        drivers_with_event = (
            [upcoming_event] + drivers if upcoming_event else drivers
        )

        new_signals[ticker] = {
            "score":          score,
            "confidence":     confidence,
            "drivers":        " + ".join(drivers_with_event) if drivers_with_event else "",
            "price":          yfd.get("price", 0.0),
            "chg_pct":        yfd.get("chg_pct", 0.0),
            "rvol":           yfd.get("rvol", 0.0),
            "earnings":       (f"in {earnings_days} Tagen ({earnings_date_str})"
                               if earnings_days is not None else None),
            "fda_date":       (f"PDUFA {fda_date_str}"
                               if fda_date_str else None),
            "upcoming_event": upcoming_event,
            "insider_buy":    insider.get("count", 0) > 0,
        }

        if score >= ALERT_THRESHOLD:
            n_signals += 1

        if score >= ALERT_THRESHOLD and not is_on_cooldown(ticker, state):
            sent = send_alert(
                ticker, score, drivers, yfd, reddit, news,
                upcoming_event=upcoming_event,
                insider=insider,
                confidence=confidence,
                n_types=n_active_types,
            )
            if sent:
                set_cooldown(ticker, state)
                n_alerts += 1

    t_elapsed = round(time.time() - t_start, 1)
    out = {
        "updated": now_berlin().isoformat(),
        "run_info": {
            "tickers_checked": len(tickers),
            "signals_active":  n_signals,
            "alerts_sent":     n_alerts,
            "elapsed_s":       t_elapsed,
            "market_phase":    phase,
        },
        "signals": new_signals,
    }

    save_signals(out)
    log.info("agent_signals.json aktualisiert.")

    state["last_run"] = now_berlin().isoformat()

    # ── Tägliche Zusammenfassung um 16:30 ET ────────────────────────────────
    if SEND_DAILY_SUMMARY and _is_summary_window():
        today_iso = now_berlin().date().isoformat()
        last_summary = state.get("last_daily_summary", "")
        if last_summary != today_iso:
            log.info("Tages-Zusammenfassung wird gesendet …")
            sent_summary = send_daily_summary(
                new_signals, tickers, phase, t_elapsed, n_alerts,
            )
            if sent_summary:
                state["last_daily_summary"] = today_iso
        else:
            log.debug("Tages-Zusammenfassung bereits heute gesendet — übersprungen.")

    save_state(state)

    print(
        f"Agent-Run {now_str}: {len(tickers)} Ticker geprüft, "
        f"{n_signals} Signale, {n_alerts} Alerts gesendet | "
        f"Reddit: {'geblockt' if reddit_blocked else ('ok' if reddit_ok else 'fail')} | "
        f"SEC: {'ok' if sec_ok else 'fail'} | "
        f"Termine: Earnings={n_earnings} Treffer, FDA={n_fda} Treffer, "
        f"SEC-relevant={n_sec_rel} Treffer | "
        f"Insider: {n_insider} Treffer, FINRA-SSR: {n_finra_ssr} Treffer, "
        f"Form4: {n_form4} Treffer | "
        f"Laufzeit: {t_elapsed}s",
        flush=True,
    )


if __name__ == "__main__":
    main()
