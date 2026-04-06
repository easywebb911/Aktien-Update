#!/usr/bin/env python3
"""
KI-Agent — ki_agent.py

Läuft alle 15 Minuten während der US-Handelszeiten (Mo–Fr, 09:25–16:05 ET).
Überwacht die aktuellen Top-10-Kandidaten auf Squeeze-Trigger aus mehreren
kostenlosen Quellen und sendet Alert-E-Mails bei relevanten Signalen.

Datenquellen:
  1. Yahoo Finance (yfinance)   — Kurs, Intraday-Volumen, Rel. Volumen, Spanne
  2. Yahoo Finance News RSS     — Schlagzeilen
  3. Reddit (public JSON API)   — Erwähnungen + Sentiment in WSB/stocks/shortsqueeze
  4. SEC EDGAR RSS              — neue 8-K-Meldungen (US only)
  5. Finviz News RSS            — alternative Nachrichtenquelle

Outputs:
  agent_signals.json  — Signal-Score je Ticker, gelesen von der Website
  agent_state.json    — Cooldown-Tracking, committet nach jedem Run
"""

import json
import logging
import os
import re
import smtplib
import time
import xml.etree.ElementTree as ET
from datetime import datetime, time, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yfinance as yf

# ── Konfiguration — alle Schwellen hier ändern, nirgendwo sonst ──────────────
ALERT_THRESHOLD         = 40      # Score ≥ → Alert senden
ALERT_THRESHOLD_STRONG  = 70      # Score ≥ → Starker Alert (⚡⚡)
ALERT_COOLDOWN_HOURS    = 2       # Mindeststunden zwischen zwei Alerts je Ticker

# Test-Modus: True → Handelszeiten-Prüfung wird übersprungen
IGNORE_TRADING_HOURS    = False

# Handelsfenster in Eastern Time (NY) — Puffer je 5 Minuten vor/nach Börsenglocke
MARKET_OPEN             = time(9, 25)   # NYSE öffnet 09:30 ET
MARKET_CLOSE            = time(16, 5)   # NYSE schließt 16:00 ET

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
SCORE_NEWS_KEYWORD      = 10      # News-Keyword-Treffer (je Treffer, max 20 Pkt)

NEWS_KEYWORDS     = {"squeeze", "short squeeze", "short interest",
                     "analyst upgrade", "earnings beat"}
REDDIT_POSITIVE   = {"squeeze", "moon", "calls", "breakout", "short"}
REDDIT_NEGATIVE   = {"puts", "short", "crash", "dump"}
REDDIT_SUBS       = ["wallstreetbets", "stocks", "shortsqueeze"]
REDDIT_LOOKBACK_H = 4

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


# ── Zeitzonen-Hilfsfunktionen ─────────────────────────────────────────────────

def now_berlin() -> datetime:
    return datetime.now(BERLIN)


def is_trading_hours() -> bool:
    """True während US-Handelszeiten (Mo–Fr, MARKET_OPEN–MARKET_CLOSE ET).

    Verwendet America/New_York — korrekt für EST (UTC−5) und EDT (UTC−4),
    unabhängig von MEZ/MESZ-Umstellung in Deutschland.
    """
    now_et = datetime.now(EASTERN)
    if now_et.weekday() >= 5:
        return False
    return MARKET_OPEN <= now_et.time() < MARKET_CLOSE


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
            f"https://www.reddit.com/r/{sub}/search.json"
            f"?q={ticker}&sort=new&restrict_sr=1&limit=25&t=day"
        )
        try:
            resp = requests.get(url, headers=REDDIT_HEADERS, timeout=12)
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
            log.debug("Reddit %s/%s: %s", sub, ticker, exc)

    sentiment = 0.0
    if total_posts > 0:
        total_kw = pos_score + neg_score
        sentiment = round((pos_score - neg_score) / total_kw, 3) if total_kw > 0 else 0.0

    return {"count": total_posts, "sentiment": sentiment}


# ── Datenquelle 4: SEC EDGAR RSS ─────────────────────────────────────────────

def fetch_sec_8k(ticker: str) -> bool:
    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcompany&CIK={ticker}&type=8-K"
        "&dateb=&owner=include&count=5&search_text=&output=atom"
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=12)
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
                    return True
            except Exception:
                continue
    except Exception as exc:
        log.debug("EDGAR %s: %s", ticker, exc)
    return False


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


# ── Signal-Score berechnen ────────────────────────────────────────────────────

def compute_signal(
    yf_data: dict,
    news: list[str],
    reddit: dict,
    has_8k: bool,
) -> tuple[int, list[str]]:
    score   = 0
    drivers = []

    chg  = yf_data.get("chg_pct", 0.0)
    rvol = yf_data.get("rvol", 0.0)
    intr = yf_data.get("intraday", 0.0)

    if chg >= 7:
        score += SCORE_PRICE_UP_7
        drivers.append(f"Kurs +{chg:.1f}%")
    elif chg >= 3:
        score += SCORE_PRICE_UP_3
        drivers.append(f"Kurs +{chg:.1f}%")

    if rvol >= 4:
        score += SCORE_RVOL_4X
        drivers.append(f"Volumen {rvol:.1f}×")
    elif rvol >= 2:
        score += SCORE_RVOL_2X
        drivers.append(f"Volumen {rvol:.1f}×")

    if intr >= 5:
        score += SCORE_INTRADAY_RANGE
        drivers.append(f"Spanne {intr:.1f}%")

    rc = reddit.get("count", 0)
    rs = reddit.get("sentiment", 0.0)
    if rc >= 15:
        score += SCORE_REDDIT_15
        drivers.append(f"Reddit +{rc} Erwähnungen")
    elif rc >= 5:
        score += SCORE_REDDIT_5
        drivers.append(f"Reddit +{rc} Erwähnungen")
    if rs >= 0.3:
        score += SCORE_REDDIT_SENTIMENT
        drivers.append(f"Reddit-Sentiment {rs:.2f}")

    if has_8k:
        score += SCORE_SEC_8K
        drivers.append("SEC 8-K")

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

    return min(score, 100), drivers


# ── E-Mail-Versand ────────────────────────────────────────────────────────────

def send_alert(
    ticker: str,
    score: int,
    drivers: list[str],
    yf_data: dict,
    reddit: dict,
    news: list[str],
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

    body = (
        f"{prefix} SQUEEZE-ALERT: {ticker}\n"
        f"{'=' * 55}\n\n"
        f"Score:            {score}/100\n"
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


# ── Hauptlogik ────────────────────────────────────────────────────────────────

def main() -> None:
    t_start = time.time()

    if not IGNORE_TRADING_HOURS and not is_trading_hours():
        log.info("Außerhalb der Handelszeiten (%s–%s ET) — nichts zu tun.",
                 MARKET_OPEN.strftime("%H:%M"), MARKET_CLOSE.strftime("%H:%M"))
        return

    now_str = now_berlin().strftime("%H:%M Uhr")
    log.info("=== KI-Agent Start %s ===", now_berlin().strftime("%Y-%m-%d %H:%M"))

    tickers = parse_top_tickers()
    if not tickers:
        log.warning("Keine Ticker gefunden — Abbruch.")
        return

    state      = load_state()
    old_sigs   = load_signals()
    new_signals: dict[str, dict] = {}

    log.info("yfinance Batch-Download für %d Ticker …", len(tickers))
    yf_batch = fetch_yfinance(tickers)

    reddit_ok = True
    sec_ok    = True
    n_alerts  = 0
    n_signals = 0

    for ticker in tickers:
        log.info("Prüfe %s …", ticker)
        yfd = yf_batch.get(ticker, {})
        if not yfd:
            log.debug("  Keine yfinance-Daten für %s", ticker)

        news = fetch_yahoo_news(ticker)
        if not news:
            news = fetch_finviz_news(ticker)

        reddit: dict = {"count": 0, "sentiment": 0.0}
        try:
            reddit = fetch_reddit_mentions(ticker)
        except Exception as exc:
            log.debug("Reddit Fehler %s: %s", ticker, exc)
            reddit_ok = False

        has_8k = False
        is_us  = "." not in ticker
        if is_us:
            try:
                has_8k = fetch_sec_8k(ticker)
            except Exception as exc:
                log.debug("SEC Fehler %s: %s", ticker, exc)
                sec_ok = False

        score, drivers = compute_signal(yfd, news, reddit, has_8k)
        log.info("  %s Score=%d Treiber=%s", ticker, score, " | ".join(drivers))

        new_signals[ticker] = {
            "score":    score,
            "drivers":  " + ".join(drivers) if drivers else "",
            "price":    yfd.get("price", 0.0),
            "chg_pct":  yfd.get("chg_pct", 0.0),
            "rvol":     yfd.get("rvol", 0.0),
        }

        if score >= ALERT_THRESHOLD:
            n_signals += 1

        if score >= ALERT_THRESHOLD and not is_on_cooldown(ticker, state):
            sent = send_alert(ticker, score, drivers, yfd, reddit, news)
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
        },
        "signals": new_signals,
    }

    sigs_dirty = json.dumps(old_sigs.get("signals", {}), sort_keys=True) != \
                 json.dumps(new_signals, sort_keys=True)

    if sigs_dirty:
        save_signals(out)
        log.info("agent_signals.json aktualisiert.")
    else:
        log.info("agent_signals.json unverändert — kein Schreiben.")

    state["last_run"] = now_berlin().isoformat()
    save_state(state)

    print(
        f"Agent-Run {now_str}: {len(tickers)} Ticker geprüft, "
        f"{n_signals} Signale, {n_alerts} Alerts gesendet | "
        f"Reddit: {'ok' if reddit_ok else 'fail'} | "
        f"SEC: {'ok' if sec_ok else 'fail'} | "
        f"Laufzeit: {t_elapsed}s",
        flush=True,
    )


if __name__ == "__main__":
    main()
