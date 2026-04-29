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
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dt_time, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import requests
import yfinance as yf

from config import *   # zentrale Konstanten (Schwellen, Score-Gewichte, Timeouts, Pfade)

# Konstanten (Alert-Schwellen, Score-Gewichte, Trigger, Keywords, Pfade)
# kommen aus config.py — Anpassungen dort vornehmen.

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


def get_alert_threshold(phase: str) -> int:
    """Gibt die phasenabhängige Alert-Schwelle zurück (Fix 2)."""
    return {
        "Regulär":     ALERT_THRESHOLD_REGULAR,
        "Pre-Market":  ALERT_THRESHOLD_PREMARKET,
        "After-Hours": ALERT_THRESHOLD_AFTERHOURS,
        "Geschlossen": ALERT_THRESHOLD_CLOSED,
    }.get(phase, ALERT_THRESHOLD_REGULAR)


# ── index.html parsen → Top-10-Ticker ─────────────────────────────────────────

def parse_top_tickers() -> list[str]:
    """Extrahiert Ticker aus dem aktuellen index.html.

    Filtert Phantom-Einträge („TICKER", Platzhalter, Flag-Emoji-Reste) und
    akzeptiert nur valide Symbole: 1–6 Zeichen, nur Buchstaben/Zahlen.
    """
    if not INDEX_HTML.exists():
        log.error("index.html nicht gefunden.")
        return []
    html = INDEX_HTML.read_text(encoding="utf-8")
    tickers = re.findall(r'<span class="ticker">([^<]+)</span>', html)
    clean: list[str] = []
    for raw in tickers:
        # Ticker-Symbol extrahieren (ohne Flag-Emoji, Whitespace etc.)
        m = re.search(r'[A-Z0-9][A-Z0-9.\-]*', raw.strip().upper())
        if not m:
            continue
        t = m.group().split(".")[0]   # US-Ticker ohne Exchange-Suffix
        # Phantom-Ticker herausfiltern: kein Platzhalter, nur Buchstaben/Zahlen,
        # Länge 1–6 — verhindert dass z.B. "TICKER" aus Template-Resten in die
        # Pipeline gelangt und FINRA/Reddit-Queries verschmutzt.
        if t == "TICKER" or not re.match(r"^[A-Z0-9]{1,6}$", t):
            continue
        if t not in clean:
            clean.append(t)
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


# Schützt den Alert-Block (is_on_cooldown-Check + send_alert + set_cooldown)
# gegen Doppel-Alerts, falls der Block jemals aus mehreren Threads erreicht
# wird. Aktuell ist der Versand sequenziell, aber der Lock härtet die
# Check-then-Act-Sequenz für künftige Parallelisierung ab.
_alert_lock = threading.Lock()


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
    # Kombinierte app_data.json aktualisieren — Browser-PWA kann dann mit einem
    # einzigen fetch('app_data.json') beide Datensätze laden.
    try:
        if not GENERATE_APP_DATA_JSON:
            return
    except NameError:
        # Falls Flag nicht importiert — still skip
        return
    try:
        score_history_path = Path("score_history.json")
        if score_history_path.exists():
            score_history = json.loads(score_history_path.read_text(encoding="utf-8"))
        else:
            score_history = {}
    except (OSError, json.JSONDecodeError):
        score_history = {}
    payload = {
        "score_history": score_history,
        "agent_signals": signals,
        "generated_at":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    Path("app_data.json").write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )


# ── Backtest-History: return_3d/5d/10d nachführen ────────────────────────────

def _trading_days_elapsed(entry_date_str: str, today: datetime.date = None) -> int:
    """Zählt Mo–Fr-Tage strikt NACH dem Entry-Datum bis heute (inklusive).
    Feiertage werden vereinfacht ignoriert — Wochenenden reichen für eine
    robuste Heuristik (3/5/10 Tage vs. ggf. 4/6/12 bei Feiertagen ist OK).
    """
    try:
        start = datetime.strptime(entry_date_str, "%d.%m.%Y").date()
    except ValueError:
        return -1
    today = today or datetime.now(timezone.utc).date()
    n = 0
    d = start
    while d < today:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def update_backtest_returns() -> None:
    """Füllt T+0 und T+1 Return-Felder sobald genug Handelstage vergangen sind.

    Für jeden daily-Eintrag werden bei jedem Aufruf nachgetragen:
      • ``entry_price_t1``             — Close am nächsten Handelstag
      • ``return_{win}d`` (T+0)        — Close[entry + win] / entry_price
      • ``return_{win}d_t1`` (T+1)     — Close[entry + 1 + win] / entry_price_t1

    Holt ~90 Handelstage History pro Ticker und liest die benötigten Close-
    Werte an den konkreten Handelstag-Offsets ab. Idempotent — bereits
    gefüllte Felder werden nicht überschrieben.
    """
    try:
        if not BACKTEST_ENABLED:
            return
    except NameError:
        return
    path = Path(BACKTEST_FILE)
    if not path.exists():
        return
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("backtest_history.json ist corrupt — übersprungen")
        return
    if not isinstance(entries, list) or not entries:
        return

    today = datetime.now(timezone.utc).date()

    def _needs_update(e: dict) -> bool:
        elapsed = _trading_days_elapsed(e.get("date", ""), today)
        if elapsed < 0:
            return False
        if e.get("entry_price_t1") is None and elapsed >= 1:
            return True
        for win in BACKTEST_RETURN_WINDOWS:
            if e.get(f"return_{win}d") is None and elapsed >= win:
                return True
            if e.get(f"return_{win}d_t1") is None and elapsed >= win + 1:
                return True
        return False

    pending = [e for e in entries if _needs_update(e)]
    tickers = sorted({e["ticker"] for e in pending})
    if not tickers:
        return

    log.info("Backtest-Returns: %d Ticker mit fälligen Windows (T+0 oder T+1)",
             len(tickers))
    try:
        hist = yf.download(tickers, period="90d", auto_adjust=True,
                           progress=False, threads=True)
    except Exception as exc:
        log.warning("Backtest-Returns yf.download failed: %s", exc)
        return

    def _closes_for(ticker: str):
        try:
            df = hist if len(tickers) == 1 else hist[ticker]
            closes = df["Close"].dropna() if "Close" in df else None
            return closes
        except (KeyError, ValueError, AttributeError):
            return None

    n_filled = 0
    for e in pending:
        closes = _closes_for(e["ticker"])
        if closes is None or len(closes) == 0:
            continue
        try:
            entry_dt = datetime.strptime(e.get("date", ""), "%d.%m.%Y").date()
        except ValueError:
            continue
        # Position des Entry-Datums im History-Index finden
        idx_dates = [ts.date() for ts in closes.index]
        ei = next((i for i, d in enumerate(idx_dates) if d == entry_dt), -1)
        if ei < 0:
            continue

        def _close_at(offset: int) -> float | None:
            pos = ei + offset
            if 0 <= pos < len(closes):
                return float(closes.iloc[pos])
            return None

        entry_price = float(e.get("entry_price") or 0) or (_close_at(0) or 0)
        close_t1    = _close_at(1)

        if e.get("entry_price_t1") is None and close_t1 is not None:
            e["entry_price_t1"] = round(close_t1, 4)
            n_filled += 1

        for win in BACKTEST_RETURN_WINDOWS:
            k0 = f"return_{win}d"
            if e.get(k0) is None and entry_price > 0:
                c = _close_at(win)
                if c is not None:
                    e[k0] = round((c / entry_price - 1) * 100, 2)
                    n_filled += 1
                    log.info("  %s [%s] T+0 %dd-Return: %+.2f%%",
                             e["ticker"], e.get("date"), win, e[k0])
            k1 = f"return_{win}d_t1"
            if (e.get(k1) is None and close_t1 is not None and close_t1 > 0):
                c = _close_at(1 + win)
                if c is not None:
                    e[k1] = round((c / close_t1 - 1) * 100, 2)
                    n_filled += 1
                    log.info("  %s [%s] T+1 %dd-Return: %+.2f%%",
                             e["ticker"], e.get("date"), win, e[k1])

    if n_filled > 0:
        path.write_text(json.dumps(entries, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        print(f"Backtest-Returns aktualisiert: {n_filled} Felder gefüllt",
              flush=True)


# ── Datenquelle 1: yfinance ───────────────────────────────────────────────────

def fetch_yfinance(tickers: list[str]) -> dict[str, dict]:
    """Batch-Download für alle Ticker. Gibt Dict ticker→Daten zurück.

    Schritt 1: 5-Tage-Tagesbalken für Avg-Volumen, letzten regulären Close
               und Intraday-Spanne.
    Schritt 2 (wenn USE_PREPOST_DATA): 1-Minuten-Bars mit prepost=True für
               aktuellen Kurs auch in Pre-Market / After-Hours.
               chg_pct wird gegen den letzten regulären Close berechnet.
    """
    if not tickers:
        return {}
    results: dict[str, dict] = {}

    # ── Schritt 1: Tagesbalken (reguläre Session, 5 Tage) ───────────────────
    try:
        hist  = yf.download(
            tickers, period="5d", auto_adjust=True,
            threads=True, progress=False,
        )
        multi = len(tickers) > 1
        for t in tickers:
            try:
                df = hist[t] if multi else hist
                if df is None or df.empty or len(df) < 2:
                    continue
                df = df.dropna(subset=["Close", "Volume"])
                avg_vol        = float(df["Volume"].iloc[:-1].mean())
                cur_vol        = float(df["Volume"].iloc[-1])
                rvol           = round(cur_vol / avg_vol, 2) if avg_vol > 0 else 0.0
                last_reg_close = float(df["Close"].iloc[-1])
                prev_close     = float(df["Close"].iloc[-2])
                high_          = float(df["High"].iloc[-1])
                low_           = float(df["Low"].iloc[-1])
                open_          = float(df["Open"].iloc[-1])
                intraday       = round((high_ - low_) / open_ * 100, 2) if open_ > 0 else 0.0
                chg_pct        = (
                    round((last_reg_close - prev_close) / prev_close * 100, 2)
                    if prev_close > 0 else 0.0
                )
                results[t] = {
                    "price":          round(last_reg_close, 2),
                    "last_reg_close": round(last_reg_close, 2),
                    "chg_pct":        chg_pct,
                    "rvol":           rvol,
                    "intraday":       intraday,
                }
            except Exception as exc:
                log.debug("yfinance daily slice %s: %s", t, exc)
    except Exception as exc:
        log.warning("yfinance Tagesbalken Fehler: %s", exc)

    # ── Schritt 2: fast_info.last_price → aktueller Kurs inkl. Pre/Post-Market ─
    # Zuverlässiger als 1m-Bars: liefert den letzten verfügbaren Kurs auch
    # außerhalb der regulären Handelszeiten (After-Hours / Pre-Market).
    # Nach Börsenschluss kann last_price None/0 sein → Fallback auf
    # regularMarketChangePercent aus fast_info, sonst stiller 0.0%-Fallback.
    if USE_PREPOST_DATA:
        for t in tickers:
            try:
                fi = yf.Ticker(t).fast_info
            except Exception as exc:
                log.debug("fast_info %s: %s", t, exc)
                continue
            try:
                current_price = fi.last_price
            except Exception:
                current_price = None
            if current_price and current_price > 0:
                base = results.get(t, {}).get("last_reg_close")
                if base and base > 0:
                    chg_pct = round((current_price - base) / base * 100, 2)
                else:
                    chg_pct = results.get(t, {}).get("chg_pct", 0.0)
                if t in results:
                    results[t]["price"]   = round(current_price, 2)
                    results[t]["chg_pct"] = chg_pct
                else:
                    results[t] = {
                        "price":          round(current_price, 2),
                        "last_reg_close": round(current_price, 2),
                        "chg_pct":        chg_pct,
                        "rvol":           0.0,
                        "intraday":       0.0,
                    }
                log.debug("fast_info %s: last_price=%.2f chg=%.1f%%",
                          t, current_price, chg_pct)
                continue
            # Kein Live-Kurs → Fallback auf regularMarketChangePercent.
            reg_chg = None
            for attr in ("regular_market_change_percent",
                         "regularMarketChangePercent"):
                try:
                    v = getattr(fi, attr, None)
                    if v is not None:
                        reg_chg = float(v)
                        break
                except Exception:
                    continue
            if t not in results:
                results[t] = {
                    "price":          0.0,
                    "last_reg_close": 0.0,
                    "chg_pct":        round(reg_chg, 2) if reg_chg is not None else 0.0,
                    "rvol":           0.0,
                    "intraday":       0.0,
                }
            elif reg_chg is not None and not results[t].get("chg_pct"):
                results[t]["chg_pct"] = round(reg_chg, 2)

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

def fetch_sec_8k(ticker: str) -> tuple[bool, str, datetime | None]:
    """Returns (has_recent_8k, title_of_8k, filing_dt).

    filing_dt ist der UTC-Zeitstempel der Meldung — wird für den
    Earnings-Sofort-Alert (Fix 3) genutzt um die 2h-Aktualität zu prüfen.
    """
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
            return False, "", None
        resp.raise_for_status()
        text = re.sub(r' xmlns="[^"]+"', "", resp.text, count=1)
        root = ET.fromstring(text)
        for entry in root.findall("entry"):
            updated = entry.findtext("updated") or ""
            try:
                filing_dt = datetime.fromisoformat(updated)
                if filing_dt.tzinfo is None:
                    filing_dt = filing_dt.replace(tzinfo=timezone.utc)
                if filing_dt > cutoff:
                    title = entry.findtext("title") or ""
                    return True, title, filing_dt
            except Exception:
                continue
    except Exception as exc:
        pass
    return False, "", None


# ── Datenquellen 5/8/9/10/11: Generischer RSS-Fetcher ────────────────────────

def fetch_rss_news(url: str, ticker: str, max_results: int = 5) -> list[str]:
    """Generisch: lädt RSS-Feed und gibt bis zu max_results Titel zurück.

    `url` darf {ticker} / {TICKER} als Platzhalter enthalten; Template-Parameter
    werden via str.format ersetzt. Bei Fehlern wird eine leere Liste zurückgegeben.
    """
    try:
        resp = requests.get(
            url.format(ticker=ticker, TICKER=ticker.upper()),
            headers=HTTP_HEADERS, timeout=5,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        return [
            (item.findtext("title") or "")
            for item in list(root.iter("item"))[:max_results]
        ]
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


def _finra_parse_file(url: str, base_symbols: set[str]) -> dict[str, dict[str, int]]:
    """Lädt eine einzelne FINRA-CDN-Datei und parsed sie in {sym: {sv, tv}}.

    Bei HTTP-Fehlern oder nicht-parsebarem Inhalt → leeres Dict (kein Raise).
    Header wird per Substring-Match erkannt (robust gegen Spalten-Umordnung);
    Fallback auf fixe Indizes (1, 2, 4) wenn Header nicht interpretierbar.
    """
    filename = url.rsplit("/", 1)[-1]
    partial: dict[str, dict[str, int]] = {}
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=15)
        if resp.status_code == 404:
            return partial
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        log.debug("FINRA %s: %s", filename, exc)
        return partial

    lines = resp.text.splitlines()
    if not lines:
        return partial
    header = [h.strip().lower() for h in lines[0].split("|")]
    try:
        sym_idx = next(i for i, h in enumerate(header)
                       if "symbol" in h or "ticker" in h)
        sv_idx  = next(i for i, h in enumerate(header)
                       if "shortvol" in h.replace(" ", "") and "exempt" not in h)
        tv_idx  = next(i for i, h in enumerate(header)
                       if "totalvol" in h.replace(" ", ""))
    except StopIteration:
        # Fixes CDN column order fallback (Date|Symbol|ShortVol|Exempt|TotalVol|Market)
        sym_idx, sv_idx, tv_idx = 1, 2, 4

    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) <= max(sym_idx, sv_idx, tv_idx):
            continue
        sym = parts[sym_idx].strip().upper()
        if sym not in base_symbols:
            continue
        try:
            sv = int(parts[sv_idx].strip().replace(",", ""))
        except ValueError:
            continue
        try:
            tv = int(parts[tv_idx].strip().replace(",", ""))
        except ValueError:
            tv = 0
        if sv <= 0:
            continue
        entry = partial.setdefault(sym, {"sv": 0, "tv": 0})
        entry["sv"] += sv
        entry["tv"] += tv
    log.info("FINRA %s: %d relevante Rohzeilen geparsed", filename, len(partial))
    return partial


def fetch_finra_ssr(tickers: list[str]) -> dict[str, float]:
    """Lädt FINRA Daily Short Sale Volume aus ALLEN drei CDN-Dateien parallel
    und gibt {SYMBOL: ratio} zurück.

    ratio = Summe(ShortVolume) / Summe(TotalVolume) über CNMS + FNSQ + FNQC.
    Gecacht pro Datum. Hintergrund: einzelne Tier-2/3-Ticker sind oft nur in
    FNSQ bzw. FNQC enthalten, nicht in CNMS — CNMS-only führte zu 0 Matches.
    """
    global _FINRA_SSR_CACHE

    today = datetime.now(timezone.utc).date()
    # Beide Seiten konsequent auf Großbuchstaben normalisieren + Phantom-Ticker
    # („TICKER" aus Template-Resten) entfernen, damit der Abgleich nicht 0
    # relevante Ticker produziert.
    base_symbols = {
        t.strip().upper().split(".")[0]
        for t in tickers
        if t and t.strip().upper() != "TICKER"
    }
    base_symbols.discard("")
    log.info("FINRA SSR: suche %d normalisierte Symbole: %s",
             len(base_symbols), sorted(base_symbols))

    # Try today and up to 4 prior days (weekends / holidays)
    for days_back in range(5):
        date     = today - timedelta(days=days_back)
        date_str = date.strftime("%Y%m%d")

        if date_str in _FINRA_SSR_CACHE:
            log.debug("FINRA SSR Cache-Hit für %s", date_str)
            return _FINRA_SSR_CACHE[date_str]

        urls = [
            f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date_str}.txt",
            f"https://cdn.finra.org/equity/regsho/daily/FNSQshvol{date_str}.txt",
            f"https://cdn.finra.org/equity/regsho/daily/FNQCshvol{date_str}.txt",
        ]
        merged: dict[str, dict[str, int]] = {}
        any_ok = False
        with ThreadPoolExecutor(max_workers=3) as ex:
            for partial in ex.map(lambda u: _finra_parse_file(u, base_symbols),
                                  urls):
                if partial:
                    any_ok = True
                for sym, entry in partial.items():
                    m = merged.setdefault(sym, {"sv": 0, "tv": 0})
                    m["sv"] += entry["sv"]
                    m["tv"] += entry["tv"]

        if not any_ok:
            # Alle 3 URLs haben 404 geliefert → Datum existiert noch nicht,
            # einen Tag zurück springen.
            continue

        result: dict[str, float] = {
            sym: round(entry["sv"] / entry["tv"], 4)
            for sym, entry in merged.items()
            if entry["tv"] > 0 and entry["sv"] > 0
        }
        log.info("FINRA SSR Daten geladen (%s, 3 Dateien merged): "
                 "%d relevante Ticker", date_str, len(result))
        _FINRA_SSR_CACHE[date_str] = result
        return result

    log.info("FINRA SSR: keine Daten verfügbar (letzte 5 Tage).")
    empty: dict[str, float] = {}
    _FINRA_SSR_CACHE[today.strftime("%Y%m%d")] = empty
    return empty


# ── Datenquelle 11: StockTwits Sentiment (öffentliche Read-API) ──────────────

def fetch_stocktwits_sentiment(ticker: str) -> dict:
    """Liest die letzten Messages aus https://api.stocktwits.com/api/2/streams/symbol/.

    Rückgabe-Dict::
        {"bull_ratio": 0..1 | None,   # bull / (bull + bear); None wenn keine Daten
         "msg_per_h":  int,            # Messages innerhalb der letzten Stunde
         "n_total":    int,            # Anzahl bewerteter Messages
         "n_bull":     int,
         "n_bear":     int}

    Bei HTTP-Fehler, Rate-Limit (429) oder Timeout → leeres Dict
    (``{"bull_ratio": None, "msg_per_h": 0, ...}``). Niemals Raise.
    """
    if not STOCKTWITS_ENABLED or not ticker:
        return {"bull_ratio": None, "msg_per_h": 0, "n_total": 0,
                "n_bull": 0, "n_bear": 0}
    sym = ticker.split(".")[0].upper()
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{sym}.json"
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=STOCKTWITS_TIMEOUT)
        if resp.status_code != 200:
            log.debug("StockTwits %s HTTP %d", ticker, resp.status_code)
            return {"bull_ratio": None, "msg_per_h": 0, "n_total": 0,
                    "n_bull": 0, "n_bear": 0}
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.debug("StockTwits %s fetch failed: %s", ticker, exc)
        return {"bull_ratio": None, "msg_per_h": 0, "n_total": 0,
                "n_bull": 0, "n_bear": 0}

    messages = (data.get("messages") or [])[:30]
    n_bull = n_bear = 0
    msg_per_h = 0
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    for m in messages:
        # Sentiment auswerten (bull/bear; None wenn Verfasser keinen Tag setzt)
        sent = ((m.get("entities") or {}).get("sentiment") or {}).get("basic")
        if not sent:
            sent = (m.get("sentiment") or {}).get("basic") if isinstance(
                m.get("sentiment"), dict) else None
        if sent == "Bullish":
            n_bull += 1
        elif sent == "Bearish":
            n_bear += 1
        # Nachrichten-Volumen-Indikator: Messages innerhalb der letzten Stunde
        try:
            ts = datetime.fromisoformat(
                str(m.get("created_at", "")).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= one_hour_ago:
                msg_per_h += 1
        except (ValueError, TypeError):
            continue

    n_total = n_bull + n_bear
    bull_ratio = (n_bull / n_total) if n_total > 0 else None
    return {"bull_ratio": bull_ratio, "msg_per_h": msg_per_h,
            "n_total": n_total, "n_bull": n_bull, "n_bear": n_bear}


def _stocktwits_pts(st: dict | None) -> int:
    """Score-Beitrag aus StockTwits-Sentiment-Dict — gemeinsame Logik für
    compute_signal() und für die agent_signals.json-Persistenz (Frontend)."""
    if not st or st.get("n_total", 0) < 3:
        return 0
    bull = st.get("bull_ratio")
    if bull is None:
        return 0
    msgh = st.get("msg_per_h", 0)
    if bull > 0.70 and msgh > 10:
        return STOCKTWITS_BULL_STRONG
    if bull > 0.60:
        return STOCKTWITS_BULL_WEAK
    if (1 - bull) > 0.70:
        return -STOCKTWITS_BEAR_MALUS
    return 0


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


# ── KI-Sentiment via Claude Haiku (Fallback: Keyword-Zählung) ────────────────

def claude_sentiment_score(ticker: str, news: list[str]) -> tuple[int | None, str]:
    """Bewertet die letzten KI_SENTIMENT_HEADLINES Schlagzeilen via Claude Haiku.

    Rückgabe:
      (score, reason)  — score ist 0..KI_SENTIMENT_MAX_SCORE, reason ein Satz
      (None, "")       — API-Key fehlt oder Aufruf schlug fehl → Keyword-Fallback

    Billiger Call: Haiku 4.5, max_tokens=50, ~0.001 USD pro Ticker.
    Alle Fehler (Timeout, JSON-Parse, HTTP ≠ 200) führen zu None → Fallback.
    """
    if not KI_SENTIMENT_ENABLED:
        return None, ""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None, ""
    headlines = [h for h in (news or []) if h][:KI_SENTIMENT_HEADLINES]
    if not headlines:
        return None, ""
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":          api_key,
                "anthropic-version":  "2023-06-01",
                "content-type":       "application/json",
            },
            json={
                "model":      KI_SENTIMENT_MODEL,
                "max_tokens": KI_SENTIMENT_MAX_TOKENS,
                "system":     ("Bewerte diese Schlagzeilen für einen "
                               f"Short-Squeeze-Kandidaten. Antworte NUR mit "
                               f"JSON: {{\"score\": 0-{KI_SENTIMENT_MAX_SCORE}, "
                               "\"reason\": \"ein Satz\"}}"),
                "messages": [{
                    "role":    "user",
                    "content": f"Ticker {ticker}\n" + "\n".join(
                        f"- {h}" for h in headlines),
                }],
            },
            timeout=8,
        )
        if resp.status_code != 200:
            log.debug("%s Haiku-Call HTTP %d: %s", ticker, resp.status_code,
                      resp.text[:200])
            return None, ""
        data = resp.json()
        # Content ist eine Liste von Blöcken; wir nehmen den ersten text-Block.
        blocks = data.get("content") or []
        text   = next((b.get("text", "") for b in blocks
                       if b.get("type") == "text"), "")
        # Robust parsen: JSON könnte mit ```json```-Fence kommen
        text   = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(),
                        flags=re.MULTILINE)
        parsed = json.loads(text)
        score  = int(parsed.get("score", 0))
        reason = str(parsed.get("reason", ""))[:120]
        score  = max(0, min(score, KI_SENTIMENT_MAX_SCORE))
        return score, reason
    except (requests.RequestException, json.JSONDecodeError, ValueError,
            TypeError, KeyError) as exc:
        log.debug("%s Haiku-Call fehlgeschlagen: %s", ticker, exc)
        return None, ""


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
    stocktwits: dict | None = None,
    prev_rvol: float = 0.0,
) -> tuple[int, list[str], int]:
    score   = 0
    drivers = []

    # ── Per-Komponenten-Tracking für Diagnose-Print ──────────────────────────
    kurs_pts    = 0
    vol_pts     = 0
    news_pts    = 0
    earn_pts    = 0
    insider_pts = 0
    ssr_pts     = 0
    sec_pts     = 0

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
        kurs_pts = SCORE_PRICE_UP_7
        score += kurs_pts
        drivers.append(f"Kurs +{chg:.1f}%")
        sig_kurs = True
    elif chg >= TRIGGER_PRICE_UP_3:
        kurs_pts = SCORE_PRICE_UP_3
        score += kurs_pts
        drivers.append(f"Kurs +{chg:.1f}%")
        sig_kurs = True

    if rvol >= TRIGGER_RVOL_4X:
        vol_pts = SCORE_RVOL_4X
        score += vol_pts
        drivers.append(f"Volumen {rvol:.1f}×")
        sig_vol = True
    elif rvol >= TRIGGER_RVOL_2X:
        vol_pts = SCORE_RVOL_2X
        score += vol_pts
        drivers.append(f"Volumen {rvol:.1f}×")
        sig_vol = True

    # RVOL High-Alert: extra Bonus bei extremem Volumen (zusätzlich zu den
    # bestehenden 2×/4×-Punkten). 5× hat Vorrang vor 3× — kein Doppelbonus.
    if rvol >= RVOL_EXTREME_THRESHOLD:
        score += RVOL_EXTREME_BONUS
        vol_pts += RVOL_EXTREME_BONUS
        drivers.append(f"🚀 Massives Volumen {rvol:.1f}×+")
        print(f"{ticker} RVOL-Extreme +{RVOL_EXTREME_BONUS} Pkt ({rvol:.1f}×)",
              flush=True)
        sig_vol = True
    elif rvol >= RVOL_HIGH_THRESHOLD:
        score += RVOL_HIGH_BONUS
        vol_pts += RVOL_HIGH_BONUS
        drivers.append(f"⚡ Extremes Volumen {rvol:.1f}×+")
        print(f"{ticker} RVOL-High +{RVOL_HIGH_BONUS} Pkt ({rvol:.1f}×)",
              flush=True)
        sig_vol = True

    # RVOL-Velocity: vergleicht aktuellen RVOL mit dem aus dem vorigen
    # KI-Agent-Run (2 h zurück). Sprung um Faktor ≥ RVOL_VELOCITY_FACTOR
    # signalisiert beschleunigtes Trade-Volumen → klassisches Squeeze-
    # Vorläufer-Pattern. Nur ausgewertet wenn der aktuelle RVOL absolut
    # bereits relevant ist (≥ RVOL_VELOCITY_MIN).
    if (rvol >= RVOL_VELOCITY_MIN and prev_rvol > 0
            and rvol / prev_rvol >= RVOL_VELOCITY_FACTOR):
        score += RVOL_VELOCITY_BONUS
        vol_pts += RVOL_VELOCITY_BONUS
        drivers.append(f"📈 RVOL-Velocity: {prev_rvol:.1f}× → {rvol:.1f}×")
        print(f"{ticker} RVOL-Velocity +{RVOL_VELOCITY_BONUS} Pkt "
              f"({prev_rvol:.1f}× → {rvol:.1f}×, ×{rvol/prev_rvol:.2f})",
              flush=True)
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
        score    += pts
        news_pts += pts
        drivers.append("SEC 8-K")
        sig_news = True
        print(f"{ticker} SEC 8-K: '{sec_title}' → +{pts} Pkt "
              f"(earnings/FDA-relevant: {'ja' if is_relevant else 'nein'})")

    # Bevorzugt: KI-Sentiment via Claude Haiku; Fallback Keyword-Zählung.
    _ai_score, _ai_reason = claude_sentiment_score(ticker, news)
    if _ai_score is not None:
        _ai_capped = min(_ai_score, KI_SENTIMENT_MAX_SCORE)
        score    += _ai_capped
        news_pts += _ai_capped
        if _ai_capped > 0:
            drivers.append(
                f"News-KI {_ai_capped}/{KI_SENTIMENT_MAX_SCORE}"
                + (f": {_ai_reason}" if _ai_reason else "")
            )
            sig_news = True
        print(f"{ticker} KI-Sentiment: {_ai_capped}/{KI_SENTIMENT_MAX_SCORE} "
              f"({_ai_reason[:80]!r})")
    else:
        kw_pts = 0
        kw_hits: list[str] = []
        all_headlines = " ".join(news).lower()
        for kw in NEWS_KEYWORDS:
            if kw in all_headlines and kw_pts < 30:
                kw_pts += SCORE_NEWS_KEYWORD
                kw_hits.append(kw)
        if kw_pts > 0:
            _kw_capped = min(kw_pts, 30)
            score    += _kw_capped
            news_pts += _kw_capped
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
            score     += pts
            earn_pts  += pts
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
            score     += pts
            earn_pts  += pts
            drivers.append(f"FDA PDUFA in {fda_days}d")
            sig_insider = True
            print(f"{ticker} FDA PDUFA in {fda_days} Tagen → +{pts} Pkt")

    # OpenInsider — Insider-Käufe
    if insider and insider.get("count", 0) > 0:
        ic      = insider["count"]
        ic_cs   = insider.get("csuite", False)
        pts     = SCORE_INSIDER_CSUITE if ic_cs else SCORE_INSIDER_BUY
        label   = "C-Suite Insider-Kauf" if ic_cs else f"Insider-Kauf ({ic}×)"
        score       += pts
        insider_pts += pts
        drivers.append(label)
        sig_insider = True
        print(f"{ticker} OpenInsider: {ic} Käufe, C-Suite: {ic_cs} → +{pts} Pkt")

    # FINRA Daily Short Sale Volume
    if finra_ssr_ratio >= FINRA_DAILY_SSR_HIGH:
        ssr_pts  = SCORE_FINRA_SSR_HIGH
        score   += ssr_pts
        drivers.append(f"FINRA Short-Vol {finra_ssr_ratio:.0%}")
        sig_insider = True
        print(f"{ticker} FINRA SSR: {finra_ssr_ratio:.1%} → +{ssr_pts} Pkt")
    elif finra_ssr_ratio >= FINRA_DAILY_SSR_MID:
        ssr_pts  = SCORE_FINRA_SSR_MID
        score   += ssr_pts
        drivers.append(f"FINRA Short-Vol {finra_ssr_ratio:.0%}")
        sig_insider = True
        print(f"{ticker} FINRA SSR: {finra_ssr_ratio:.1%} → +{ssr_pts} Pkt")

    # SEC Form 4 — Insider-Transaktionen
    if has_form4:
        form4_lower  = form4_title.lower()
        is_purchase  = "purchase" in form4_lower or "acquisition" in form4_lower
        pts          = SCORE_FORM4_PURCHASE if is_purchase else SCORE_FORM4_ANY
        score   += pts
        sec_pts += pts
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

    # ── StockTwits Sentiment-Beitrag ─────────────────────────────────────────
    st_pts = _stocktwits_pts(stocktwits)
    if st_pts != 0 and stocktwits:
        bull = stocktwits.get("bull_ratio")
        msgh = stocktwits.get("msg_per_h", 0)
        score += st_pts
        sign = "+" if st_pts > 0 else ""
        drivers.append(
            f"StockTwits {round((bull or 0) * 100)}% bull "
            f"({stocktwits.get('n_total', 0)} msgs, {msgh}/h) {sign}{st_pts}"
        )
        if st_pts > 0:
            sig_news = True
        print(f"{ticker} StockTwits: {round((bull or 0) * 100)}% bullish, "
              f"{msgh} Nachrichten/h → {sign}{st_pts} Pkt", flush=True)

    # ── Perfect-Storm Multiplikator: gestaffelter Score-Boost wenn mehrere
    # Trigger gleichzeitig aktiv sind (RVOL/Kurs/News/Earnings) ──────────────
    active_triggers = sum([
        rvol >= COMBO_RVOL_MIN,
        abs(chg) >= COMBO_CHG_MIN,
        news_pts >= COMBO_NEWS_MIN,
        earnings_days is not None and earnings_days <= 7,
    ])
    if active_triggers >= 4:
        combo_mult = COMBO_MULT_4
        score = score * COMBO_MULT_4
        drivers.append(f"⚡ Perfect Storm: {active_triggers}/4 Trigger aktiv")
        print(f"{ticker} Perfect-Storm ×{COMBO_MULT_4}: 4/4 Trigger", flush=True)
    elif active_triggers >= 3:
        combo_mult = COMBO_MULT_3
        score = score * COMBO_MULT_3
        drivers.append(f"{active_triggers}/4 Trigger")
        print(f"{ticker} Combo ×{COMBO_MULT_3}: 3/4 Trigger", flush=True)
    elif active_triggers >= 2:
        combo_mult = COMBO_MULT_2
        score = score * COMBO_MULT_2
        print(f"{ticker} Combo ×{COMBO_MULT_2}: 2/4 Trigger (silent)", flush=True)
    else:
        combo_mult = 1.0

    total = min(int(round(score)), 100)
    print(
        f"{ticker}: Kurs={chg:.1f}% ({kurs_pts}Pkt), RVOL={rvol:.1f}× ({vol_pts}Pkt), "
        f"News={news_pts}Pkt, Earnings={earn_pts}Pkt, OpenInsider={insider_pts}Pkt, "
        f"FINRA_SSR={ssr_pts}Pkt, SEC={sec_pts}Pkt, StockTwits={st_pts}Pkt = {total}Pkt",
        flush=True,
    )
    print(f"{ticker} Konfidenz: {confidence}% ({n_types}/{MAX_SIGNAL_TYPES} Signaltypen aktiv)",
          flush=True)

    # meta exposes Komponenten/Multiplikatoren für persistente Logging-
    # Zwecke (backtest_history.json Schema-Erweiterung, Bahn B).
    meta = {"combo_mult": combo_mult, "active_triggers": active_triggers}
    return total, drivers, confidence, meta


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


def send_ntfy_alert(ticker: str, ki_score: int, drivers,
                    production_score: float | None = None,
                    monster_score: float | None = None) -> None:
    """ntfy.sh Push-Notification — parallel zur E-Mail. Fail-soft.

    ``ki_score`` ist der KI-Signal-Score aus ``compute_signal``.
    ``production_score`` ist der Setup-Score aus ``score_history.json``.
    ``monster_score`` ist die kombinierte Bewertung (siehe ``_monster_score``).

    Body-Format:
      • Monster + Setup vorhanden → ``🔥 Monster N | Setup N* | KI N – drivers\\n*Setup-Score vom letzten Daily-Run``
      • nur Setup vorhanden       → ``🚀 Score N* | KI-Signal N – drivers\\n*Setup-Score vom letzten Daily-Run``
      • beide fehlend             → ``🚀 KI-Signal N – drivers``

    Der Stern + Fußnote weisen darauf hin, dass der Setup-Score ein
    Snapshot-Wert aus ``score_history.json`` ist (letzter Daily-Run) und
    nicht in Echtzeit mit dem aktuellen KI-Score berechnet wurde.

    Topic leer oder ``NTFY_ENABLED=False`` → no-op (graceful skip).
    """
    if not NTFY_ENABLED or not NTFY_TOPIC:
        return
    if isinstance(drivers, list):
        drivers_str = " + ".join(drivers) if drivers else "—"
    else:
        drivers_str = str(drivers) if drivers else "—"
    setup_footnote = "\n*Setup-Score vom letzten Daily-Run"
    if monster_score is not None and production_score is not None:
        body = (f"{ticker} 🔥 Monster {monster_score:.0f} | "
                f"Setup {production_score:.0f}* | KI {ki_score} – {drivers_str}"
                f"{setup_footnote}")
    elif production_score is not None:
        body = (f"{ticker} 🚀 Score {production_score:.1f}* | "
                f"KI-Signal {ki_score} – {drivers_str}"
                f"{setup_footnote}")
    else:
        body = f"{ticker} 🚀 KI-Signal {ki_score} – {drivers_str}"
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=body.encode("utf-8"),
            headers={
                "Title": f"Squeeze Alert: {ticker}",
                "Priority": "high",
                "Tags": "chart_with_upwards_trend",
            },
            timeout=5,
        )
    except Exception as exc:
        log.warning("ntfy push fehlgeschlagen für %s: %s", ticker, exc)


def _load_production_scores() -> dict[str, float]:
    """Liest neuesten Production-Score pro Ticker aus ``score_history.json``.

    Format-tolerant (alt: dict-per-entry, neu: [date, score]-Tuple-per-entry).
    Einträge sind chronologisch sortiert; ``entries[-1]`` ist neuester Wert.
    Bei Fehler oder fehlender Datei → leeres Dict (Caller nutzt Fallback).
    """
    try:
        path = Path("score_history.json")
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    result: dict[str, float] = {}
    for ticker, entries in raw.items():
        if not entries:
            continue
        latest = entries[-1]
        try:
            if isinstance(latest, dict):
                score = latest.get("score")
            elif isinstance(latest, (list, tuple)) and len(latest) >= 2:
                score = latest[1]
            else:
                continue
            if score is None:
                continue
            result[ticker] = float(score)
        except (TypeError, ValueError):
            continue
    return result


def _monster_score(setup_score, ki_score):
    """Monster-Score-Berechnung — identisch zu Frontend ``apply_monster_score``.

    setup_score = Production-Score aus ``score_history.json``.
    ki_score    = KI-Signal-Score aus ``compute_signal``.

    Returns ``None`` wenn ``setup_score`` ``None`` ist (Ticker noch nicht in
    score_history); ansonsten gewichteter Score (0-100).
    """
    if setup_score is None:
        return None
    if ki_score is None:
        return setup_score
    if ki_score >= 60:
        return min(100, round(setup_score * 1.20))
    if ki_score < 25:
        return round(setup_score * 0.80)
    return setup_score


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
    n_active = sum(1 for _, s in scored if s.get("score", 0) >= ALERT_THRESHOLD_REGULAR)
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
        flag       = " ⚡" if score >= ALERT_THRESHOLD_REGULAR else ""
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

def _process_ticker(ticker: str, shared: dict) -> dict:
    """Berechnet Signal + Alert-Daten für einen Ticker.

    Reine Funktion ohne Schreibzugriffe auf shared state. ``shared`` ist ein
    read-only Bündel mit ``yf_batch``, ``fda_calendar``, ``finra_ssr_data``,
    ``today_et``, ``old_sigs``, ``phase``, ``alert_threshold``.

    Wird von der parallelen Ticker-Verarbeitung in ``main()`` aufgerufen.
    Alle Counter-Updates und Alert-Versand passieren post-pool sequenziell.
    """
    yf_batch       = shared["yf_batch"]
    fda_calendar   = shared["fda_calendar"]
    finra_ssr_data = shared["finra_ssr_data"]
    today_et       = shared["today_et"]
    old_sigs       = shared["old_sigs"]

    log.info("Prüfe %s …", ticker)
    yfd = yf_batch.get(ticker, {})
    if not yfd:
        log.debug("  Keine yfinance-Daten für %s", ticker)

    yahoo_news  = fetch_yahoo_news(ticker)
    base        = ticker.split(".")[0]
    finviz_news = fetch_rss_news("https://finviz.com/rss.ashx?t={ticker}", ticker)
    google_news = fetch_rss_news(
        "https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en",
        base,
    )
    uw_news = fetch_rss_news("https://unusualwhales.com/rss/ticker/{ticker}", base)
    mb_news = fetch_rss_news("https://www.marketbeat.com/stocks/NASDAQ/{ticker}/rss/", base)
    sa_news = fetch_rss_news("https://seekingalpha.com/api/sa/combined/{ticker}.xml", base)
    news = yahoo_news + finviz_news + google_news + uw_news + mb_news + sa_news
    print(f"{ticker} Quellen: Yahoo={len(yahoo_news)}, Google={len(google_news)}, "
          f"UnusualWhales={len(uw_news)}, MarketBeat={len(mb_news)}, "
          f"SeekingAlpha={len(sa_news)}", flush=True)

    reddit: dict = {"count": 0, "sentiment": 0.0}
    reddit_ok = True
    reddit_blocked = False
    try:
        reddit = fetch_reddit_mentions(ticker)
        if reddit.get("blocked"):
            reddit_blocked = True
    except Exception as exc:
        log.debug("Reddit Fehler %s: %s", ticker, exc)
        reddit_ok = False

    has_8k    = False
    sec_title = ""
    sec_8k_dt: datetime | None = None
    sec_ok    = True
    sec_rel_hit = False
    is_us     = "." not in ticker
    if is_us:
        try:
            has_8k, sec_title, sec_8k_dt = fetch_sec_8k(ticker)
            if has_8k:
                title_lower = sec_title.lower()
                if any(kw in title_lower for kw in SEC_RELEVANT_KEYWORDS):
                    sec_rel_hit = True
        except Exception as exc:
            log.debug("SEC Fehler %s: %s", ticker, exc)
            sec_ok = False

    insider: dict = {"count": 0, "csuite": False}
    if is_us:
        try:
            insider = fetch_openinsider(ticker)
        except Exception as exc:
            log.debug("OpenInsider Fehler %s: %s", ticker, exc)

    base_sym        = ticker.split(".")[0].upper()
    finra_ssr_ratio = finra_ssr_data.get(base_sym, 0.0)

    has_form4   = False
    form4_title = ""
    if is_us:
        try:
            has_form4, form4_title = fetch_sec_form4(ticker)
        except Exception as exc:
            log.debug("Form 4 Fehler %s: %s", ticker, exc)

    earnings_days: int | None = None
    earnings_date_str: str | None = None
    try:
        earnings_days, earnings_date_str = fetch_earnings_date(ticker)
    except Exception as exc:
        log.debug("Earnings Fehler %s: %s", ticker, exc)

    fda_days: int | None = None
    fda_date_str: str | None = None
    base_ticker = ticker.split(".")[0].upper()
    if base_ticker in fda_calendar:
        try:
            fda_iso  = fda_calendar[base_ticker]
            fda_date = datetime.strptime(fda_iso, "%Y-%m-%d").date()
            fda_days = (fda_date - today_et).days
            fda_date_str = fda_date.strftime("%d.%m.%Y")
        except Exception as exc:
            log.debug("FDA-Datum Parse %s: %s", ticker, exc)

    stocktwits_data = fetch_stocktwits_sentiment(ticker)

    score, drivers, confidence, _meta = compute_signal(
        ticker, yfd, news, reddit, has_8k, sec_title,
        earnings_days, fda_days,
        insider=insider, finra_ssr_ratio=finra_ssr_ratio,
        has_form4=has_form4, form4_title=form4_title,
        stocktwits=stocktwits_data,
        prev_rvol=float(old_sigs.get(ticker, {}).get("rvol", 0) or 0),
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

    upcoming_event: str | None = None
    if earnings_days is not None and earnings_days <= 7 and earnings_date_str:
        upcoming_event = f"Earnings in {earnings_days} Tagen ({earnings_date_str})"
    elif fda_days is not None and 0 <= fda_days <= 7 and fda_date_str:
        upcoming_event = f"FDA PDUFA in {fda_days} Tagen ({fda_date_str})"

    drivers_with_event = (
        [upcoming_event] + drivers if upcoming_event else drivers
    )

    _st_payload = None
    if stocktwits_data and stocktwits_data.get("n_total", 0) >= 3:
        _st_payload = {
            "bull_ratio": stocktwits_data.get("bull_ratio"),
            "msg_per_h":  stocktwits_data.get("msg_per_h", 0),
            "n_total":    stocktwits_data.get("n_total", 0),
            "pts":        _stocktwits_pts(stocktwits_data),
        }

    signal = {
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
        "stocktwits":     _st_payload,
        "combo_mult":     _meta.get("combo_mult", 1.0),
        "active_triggers": _meta.get("active_triggers", 0),
    }

    flags = {
        "reddit_ok":     reddit_ok,
        "reddit_blocked": reddit_blocked,
        "sec_ok":        sec_ok,
        "earnings_hit":  earnings_days is not None and earnings_days <= EARNINGS_FAR_DAYS,
        "fda_hit":       fda_days is not None and 0 <= fda_days <= 30,
        "sec_rel_hit":   sec_rel_hit,
        "insider_hit":   insider.get("count", 0) > 0,
        "finra_ssr_hit": finra_ssr_ratio >= FINRA_DAILY_SSR_MID,
        "form4_hit":     has_form4,
    }

    return {
        "ticker":         ticker,
        "signal":         signal,
        "score":          score,
        "drivers":        drivers,
        "confidence":     confidence,
        "n_active_types": n_active_types,
        "yfd":            yfd,
        "reddit":         reddit,
        "insider":        insider,
        "news":           news,
        "has_8k":         has_8k,
        "sec_title":      sec_title,
        "sec_8k_dt":      sec_8k_dt,
        "earnings_days":  earnings_days,
        "earnings_date_str": earnings_date_str,
        "fda_days":       fda_days,
        "fda_date_str":   fda_date_str,
        "upcoming_event": upcoming_event,
        "flags":          flags,
    }


def _test_process_ticker_isolation() -> None:
    """Selbsttest: zwei Ticker werden parallel verarbeitet ohne Cross-Talk.

    Aufruf::

        python -c 'import ki_agent as k; k._test_process_ticker_isolation()'

    Stubt alle externen Calls per ``unittest.mock.patch`` und führt zwei
    ``_process_ticker``-Aufrufe in einem 2-Worker-Pool gleichzeitig aus.
    """
    from unittest.mock import patch

    shared = {
        "yf_batch":       {"AAA": {"price": 10.0, "chg_pct": 5.0, "rvol": 2.0},
                            "BBB": {"price": 20.0, "chg_pct": -3.0, "rvol": 1.5}},
        "fda_calendar":   {},
        "finra_ssr_data": {"AAA": 0.4, "BBB": 0.6},
        "today_et":       datetime.now(EASTERN).date(),
        "old_sigs":       {},
        "phase":          "Trading",
        "alert_threshold": 999,  # niemals Alert in Test
    }

    def _per_ticker_news(t):
        return [f"{t}-news-1", f"{t}-news-2"]
    def _per_ticker_rss(url, t, max_results=5):
        return [f"{t}-rss-{url[:10]}"]
    def _per_ticker_reddit(t):
        return {"count": 1, "sentiment": 0.1, "blocked": False}
    def _per_ticker_sec_8k(t):
        return False, "", None
    def _per_ticker_insider(t):
        return {"count": 0, "csuite": False}
    def _per_ticker_form4(t):
        return False, ""
    def _per_ticker_earnings(t):
        return None, None
    def _per_ticker_stocktwits(t):
        return {"n_total": 0}
    def _per_ticker_signal(t, *args, **kwargs):
        # Score baut auf Ticker auf, damit Cross-Talk erkennbar wäre.
        score = 50 if t == "AAA" else 30
        return score, [f"{t}-driver"], 60, {"combo_mult": 1.0, "active_triggers": 1}

    with patch.object(__import__("ki_agent"), "fetch_yahoo_news", _per_ticker_news), \
         patch.object(__import__("ki_agent"), "fetch_rss_news", _per_ticker_rss), \
         patch.object(__import__("ki_agent"), "fetch_reddit_mentions", _per_ticker_reddit), \
         patch.object(__import__("ki_agent"), "fetch_sec_8k", _per_ticker_sec_8k), \
         patch.object(__import__("ki_agent"), "fetch_openinsider", _per_ticker_insider), \
         patch.object(__import__("ki_agent"), "fetch_sec_form4", _per_ticker_form4), \
         patch.object(__import__("ki_agent"), "fetch_earnings_date", _per_ticker_earnings), \
         patch.object(__import__("ki_agent"), "fetch_stocktwits_sentiment", _per_ticker_stocktwits), \
         patch.object(__import__("ki_agent"), "compute_signal", _per_ticker_signal):
        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = {ex.submit(_process_ticker, t, shared): t for t in ["AAA", "BBB"]}
            results = {}
            for f in as_completed(futs):
                t = futs[f]
                results[t] = f.result()

    assert "AAA" in results and "BBB" in results, "beide Ticker müssen Result haben"
    assert results["AAA"]["ticker"] == "AAA", "Ticker-Identität AAA korrupt"
    assert results["BBB"]["ticker"] == "BBB", "Ticker-Identität BBB korrupt"
    assert results["AAA"]["score"] == 50, f"AAA score erwartet 50, erhalten {results['AAA']['score']}"
    assert results["BBB"]["score"] == 30, f"BBB score erwartet 30, erhalten {results['BBB']['score']}"
    assert results["AAA"]["yfd"]["price"] == 10.0, "AAA yfd-Daten korrupt"
    assert results["BBB"]["yfd"]["price"] == 20.0, "BBB yfd-Daten korrupt"
    print("OK: _process_ticker isoliert pro Ticker, kein Cross-Talk.")


def main() -> None:
    t_start = time.time()
    phase            = get_market_phase()
    alert_threshold  = get_alert_threshold(phase)   # Fix 2
    print(f"Marktphase: {phase} — Alert-Schwelle: {alert_threshold}", flush=True)

    now_str = now_berlin().strftime("%H:%M Uhr")
    log.info("=== KI-Agent Start %s — %s (Schwelle: %d) ===",
             now_berlin().strftime("%Y-%m-%d %H:%M"), phase, alert_threshold)

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

    shared = {
        "yf_batch":        yf_batch,
        "fda_calendar":    fda_calendar,
        "finra_ssr_data":  finra_ssr_data,
        "today_et":        today_et,
        "old_sigs":        old_sigs,
        "phase":           phase,
        "alert_threshold": alert_threshold,
    }

    _t_pool = time.time()
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_process_ticker, t, shared): t for t in tickers}
        for future in as_completed(futures):
            t = futures[future]
            try:
                results[t] = future.result()
            except Exception as exc:
                log.warning("Ticker %s fehlgeschlagen: %s", t, exc)
    log.info("KI-Agent parallelisiert: %d Ticker in %.1fs (max_workers=8)",
             len(tickers), time.time() - _t_pool)

    # Production-Scores einmalig laden — werden für Counter (Monster-Schwelle)
    # UND Alert-Versand benötigt. _load_production_scores liest score_history.json.
    prod_scores = _load_production_scores()

    # Counter und new_signals aus den Worker-Ergebnissen aggregieren.
    # Alert-Schwelle: monster_score >= 70 (ersetzt phasenabhängige
    # Setup-Schwellen 20/25/35).
    for t in tickers:
        r = results.get(t)
        if not r:
            continue
        new_signals[t] = r["signal"]
        flags = r["flags"]
        if not flags["reddit_ok"]:    reddit_ok = False
        if flags["reddit_blocked"]:   reddit_blocked = True
        if not flags["sec_ok"]:       sec_ok = False
        if flags["earnings_hit"]:     n_earnings  += 1
        if flags["fda_hit"]:          n_fda       += 1
        if flags["sec_rel_hit"]:      n_sec_rel   += 1
        if flags["insider_hit"]:      n_insider   += 1
        if flags["finra_ssr_hit"]:    n_finra_ssr += 1
        if flags["form4_hit"]:        n_form4     += 1
        monster = _monster_score(prod_scores.get(t), r["score"])
        if monster is not None and monster >= 70:
            n_signals += 1

    # Alerts sequenziell in Original-Ticker-Reihenfolge versenden — die SMTP-
    # Verbindung pro send_alert() ist isoliert, aber Gmail rate-limit'et
    # parallele Logins; sequenziell ist robuster. set_cooldown mutiert state,
    # dieser Block ist single-threaded.
    for ticker in tickers:
        r = results.get(ticker)
        if not r:
            continue
        score          = r["score"]
        drivers        = r["drivers"]
        confidence     = r["confidence"]
        n_active_types = r["n_active_types"]
        yfd            = r["yfd"]
        reddit         = r["reddit"]
        insider        = r["insider"]
        news           = r["news"]
        has_8k         = r["has_8k"]
        sec_8k_dt      = r["sec_8k_dt"]
        earnings_days  = r["earnings_days"]
        upcoming_event = r["upcoming_event"]
        setup_sc       = prod_scores.get(ticker)
        monster        = _monster_score(setup_sc, score)

        # Cooldown-Check + Alert + set_cooldown atomar: verhindert Doppel-Alert,
        # falls der Versand jemals parallelisiert wird (zwei Threads sähen
        # sonst is_on_cooldown=False, bevor einer set_cooldown aufruft).
        with _alert_lock:
            earnings_immediate = False
            if (EARNINGS_IMMEDIATE_ALERT
                    and phase == "After-Hours"
                    and earnings_days is not None
                    and 0 <= earnings_days <= 1
                    and not is_on_cooldown(ticker, state)):
                cutoff_fresh = datetime.now(timezone.utc) - timedelta(hours=EARNINGS_IMMEDIATE_HOURS)
                is_8k_fresh  = (
                    has_8k and sec_8k_dt is not None and sec_8k_dt >= cutoff_fresh
                )
                has_earnings_news = any("earnings" in h.lower() for h in news)
                if is_8k_fresh or has_earnings_news:
                    earnings_immediate = True
                    log.info("  %s Earnings-Sofort-Alert (Earnings in %dd, 8K-frisch: %s, News: %s)",
                             ticker, earnings_days, is_8k_fresh, has_earnings_news)
                    send_ntfy_alert(ticker, score, drivers,
                                    production_score=setup_sc, monster_score=monster)
                    sent = send_alert(
                        ticker, score, drivers, yfd, reddit, news,
                        upcoming_event=upcoming_event or f"Earnings in {earnings_days} Tagen — Sofort-Alert",
                        insider=insider,
                        confidence=confidence,
                        n_types=n_active_types,
                    )
                    if sent:
                        set_cooldown(ticker, state)
                        n_alerts += 1

            if (monster is not None and monster >= 70
                    and not is_on_cooldown(ticker, state)
                    and not earnings_immediate):
                send_ntfy_alert(ticker, score, drivers,
                                production_score=setup_sc, monster_score=monster)
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

    # Backtest-Returns nachführen: fälligen return_3d/5d/10d-Feldern den
    # aktuellen Close-Preis zuweisen. Idempotent; kein Einfluss wenn nichts fällig.
    try:
        update_backtest_returns()
    except Exception as exc:
        log.warning("update_backtest_returns Fehler: %s", exc)

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
