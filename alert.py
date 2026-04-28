#!/usr/bin/env python3
"""
Squeeze Alert Monitor — alert.py

Läuft alle 15 Minuten während der US-Handelszeiten (Mo–Fr 09:30–16:00 ET).
Vergleicht aktuelle yfinance-Daten gegen die Tages-Baseline aus dem
9-Uhr-Morgenreport (index.html) und verschickt Alarm-E-Mails bei
Schwellenwertüberschreitungen.
"""

import json
import logging
import os
import re
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yfinance as yf

from config import NTFY_ENABLED, NTFY_TOPIC

# ---------------------------------------------------------------------------
# Alarm-Schwellenwerte — hier konfigurieren, nirgendwo sonst
# ---------------------------------------------------------------------------

# Punkte: Score-Anstieg vs. Morgen-Baseline löst Alarm aus
ALERT_SCORE_DELTA = 10

# Faktor: Rel. Volumen-Anstieg vs. Baseline (0.5 = +50 %)
ALERT_VOLUME_DELTA = 0.50

# Prozent: Kursanstieg vs. Baseline-Preis löst Alarm aus
ALERT_PRICE_DELTA = 3.0

# Punkte: Mindest-Score eines neuen Kandidaten (nicht in Baseline) für Alarm
ALERT_NEW_CANDIDATE_SCORE = 70

# Minuten: Mindestabstand zwischen zwei Alarmen für dieselbe Aktie
ALERT_COOLDOWN_MINUTES = 60

# ---------------------------------------------------------------------------
# Dateipfade & Konstanten
# ---------------------------------------------------------------------------
BASELINE_FILE   = Path("baseline.json")
LAST_ALERT_FILE = Path("last_alert.json")
INDEX_HTML      = Path("index.html")
PWA_URL         = "https://easywebb911.github.io/Aktien-update/"

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Marktzeiten-Check
# ---------------------------------------------------------------------------

def is_market_open() -> bool:
    """True wenn US-Markt aktuell geöffnet ist (09:30–16:00 ET, Mo–Fr)."""
    now = datetime.now(EASTERN)
    if now.weekday() >= 5:
        return False
    open_  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_ = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_ <= now < close_


# ---------------------------------------------------------------------------
# Score-Berechnung (spiegelt generate_report.py exakt wider)
# ---------------------------------------------------------------------------

def compute_score(sf: float, sr: float, rel_vol: float, chg_pct: float) -> float:
    """Squeeze-Score identisch zu generate_report.py score()."""
    rv_raw = min((rel_vol - 1.0) / 4.0, 1.0)
    if sf == 0 and sr == 0:
        momentum = min(abs(chg_pct) / 15.0, 1.0) * 20
        return round(min(rv_raw * 30 + momentum, 50.0), 2)
    return round(
        min(sf  / 100.0, 1.0) * 35 +
        min(sr  /  20.0, 1.0) * 25 +
        rv_raw * 25 +
        min(abs(chg_pct) / 15.0, 1.0) * 15,
        2,
    )


# ---------------------------------------------------------------------------
# index.html parsen → Baseline-Kandidaten
# ---------------------------------------------------------------------------

def parse_index_html() -> list[dict]:
    """Extrahiert Top-10-Ticker + Score + Preis aus dem aktuellen index.html."""
    if not INDEX_HTML.exists():
        log.error("index.html nicht gefunden — Baseline kann nicht erstellt werden.")
        return []

    html = INDEX_HTML.read_text(encoding="utf-8")
    cards = re.findall(
        r'<article class="card"[^>]*id="c(\d+)"[^>]*>(.*?)</article>',
        html, re.DOTALL,
    )
    result = []
    for rank, block in cards:
        m_ticker = re.search(r'<span class="ticker">([^<]+)</span>', block)
        if not m_ticker:
            continue
        ticker = m_ticker.group(1).strip()

        m_score = re.search(r'<span class="score-num"[^>]*>([0-9.]+)</span>', block)
        score = float(m_score.group(1)) if m_score else 0.0

        m_price = re.search(r'<span class="price-tag"[^>]*>\$([0-9.]+)', block)
        price = float(m_price.group(1)) if m_price else 0.0

        result.append({
            "rank":       int(rank),
            "ticker":     ticker,
            "score":      score,
            "price":      price,
            "rel_volume": 0.0,  # wird beim Baseline-Aufbau per yfinance befüllt
        })

    log.info("index.html: %d Kandidaten geparst.", len(result))
    return result


# ---------------------------------------------------------------------------
# Baseline laden / neu erstellen
# ---------------------------------------------------------------------------

def load_or_create_baseline() -> dict:
    """
    Lädt die Tages-Baseline. Falls keine aktuelle Baseline vorhanden ist,
    wird sie aus index.html (Morgenreport) + aktuellem rel_volume erstellt.
    """
    today = datetime.now(BERLIN).strftime("%Y-%m-%d")

    if BASELINE_FILE.exists():
        data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        if data.get("date") == today:
            log.info("Baseline von heute geladen (%d Kandidaten).",
                     len(data.get("candidates", [])))
            return data
        log.info("Baseline veraltet (%s) — wird neu erstellt.", data.get("date", "?"))

    # Baseline aus index.html aufbauen
    candidates = parse_index_html()
    if not candidates:
        return {"date": today, "candidates": []}

    log.info("Baseline: rel_volume per yfinance befüllen …")
    for c in candidates:
        try:
            hist = yf.Ticker(c["ticker"]).history(period="5d")
            if len(hist) >= 2:
                avg = float(hist["Volume"].iloc[:-1].mean())
                cur = float(hist["Volume"].iloc[-1])
                c["rel_volume"] = round(cur / avg, 2) if avg > 0 else 0.0
        except Exception as exc:
            log.debug("  yfinance Fehler %s: %s", c["ticker"], exc)
        time.sleep(0.3)

    baseline = {"date": today, "candidates": candidates}
    BASELINE_FILE.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("Baseline gespeichert: %d Kandidaten.", len(candidates))
    return baseline


# ---------------------------------------------------------------------------
# Aktuelle Live-Daten per yfinance
# ---------------------------------------------------------------------------

def fetch_live(ticker: str) -> dict:
    """Holt aktuellen Kurs, rel_volume und Score-Komponenten per yfinance."""
    try:
        stk  = yf.Ticker(ticker)
        info = stk.info or {}
        hist = stk.history(period="5d")

        avg_vol = float(hist["Volume"].iloc[:-1].mean()) if len(hist) >= 2 else 0.0
        cur_vol = float(hist["Volume"].iloc[-1])         if len(hist) >= 1 else 0.0
        rel_vol = round(cur_vol / avg_vol, 2)            if avg_vol > 0 else 0.0

        price   = float(
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or (float(hist["Close"].iloc[-1]) if len(hist) >= 1 else 0.0)
        )
        chg_pct = float(info.get("regularMarketChangePercent") or 0.0)
        sf      = float(info.get("shortPercentOfFloat") or 0.0) * 100
        sr      = float(info.get("shortRatio") or 0.0)

        return {
            "ticker":      ticker,
            "price":       round(price, 2),
            "change_pct":  round(chg_pct, 2),
            "rel_volume":  rel_vol,
            "short_float": round(sf, 2),
            "short_ratio": round(sr, 2),
            "score":       compute_score(sf, sr, rel_vol, chg_pct),
        }
    except Exception as exc:
        log.warning("fetch_live Fehler %s: %s", ticker, exc)
        return {}


# ---------------------------------------------------------------------------
# Yahoo-Screener-Schnellscan für neue Kandidaten
# ---------------------------------------------------------------------------

def fetch_screener_candidates(region: str = "US", count: int = 25) -> list[dict]:
    """
    Schneller Screener-Aufruf (kein yfinance, nur JSON-API) für Neukandidaten-Check.
    Gibt Rohdaten zurück — nur für US-Markt, da dort Short-Float-Daten verfügbar.
    """
    url = "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved"
    results = []
    for screener_id in ("most_shorted_stocks", "small_cap_gainers"):
        try:
            resp = requests.get(
                url,
                params={"scrIds": screener_id, "count": str(count),
                        "region": region, "lang": "en-US", "formatted": "false"},
                headers=HTTP_HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            data   = resp.json()
            quotes = ((data.get("finance") or {})
                      .get("result") or [{}])[0].get("quotes", [])
            for q in quotes:
                t  = (q.get("symbol") or "").strip().upper()
                sf = float(q.get("shortPercentOfFloat") or 0.0)
                if sf <= 1.0:
                    sf *= 100           # Yahoo liefert manchmal Dezimalwert
                results.append({
                    "ticker":      t,
                    "short_float": round(sf, 2),
                    "short_ratio": float(q.get("shortRatio") or 0.0),
                    "price":       float(q.get("regularMarketPrice") or 0.0),
                    "change_pct":  float(q.get("regularMarketChangePercent") or 0.0),
                    "rel_volume":  0.0,  # wird per yfinance befüllt falls nötig
                })
        except Exception as exc:
            log.debug("Screener %s/%s: %s", region, screener_id, exc)
        time.sleep(0.5)
    return results


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

def load_last_alerts() -> dict:
    if LAST_ALERT_FILE.exists():
        return json.loads(LAST_ALERT_FILE.read_text(encoding="utf-8"))
    return {}


def save_last_alerts(data: dict) -> None:
    LAST_ALERT_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def is_on_cooldown(ticker: str, last_alerts: dict) -> bool:
    entry = last_alerts.get(ticker)
    if not entry:
        return False
    last_time = datetime.fromisoformat(entry["time"])
    elapsed_min = (datetime.now(BERLIN) - last_time).total_seconds() / 60
    return elapsed_min < ALERT_COOLDOWN_MINUTES


# ---------------------------------------------------------------------------
# E-Mail-Versand
# ---------------------------------------------------------------------------

def send_alert_email(
    ticker: str,
    reason: str,
    live: dict,
    base: dict,
) -> bool:
    """Schickt Alarm-E-Mail per Gmail SMTP (App-Passwort)."""
    mail_to   = os.environ.get("MAIL_TO", "").strip()
    mail_pass = os.environ.get("MAIL_PASSWORD", "").strip()
    mail_from = os.environ.get("MAIL_FROM", mail_to).strip()

    if not mail_to or not mail_pass:
        log.warning("MAIL_TO / MAIL_PASSWORD nicht gesetzt — kein E-Mail für %s.", ticker)
        return False

    now_str     = datetime.now(BERLIN).strftime("%d.%m.%Y %H:%M Uhr")
    score_delta = live.get("score", 0) - base.get("score", 0)
    sign        = "+" if score_delta >= 0 else ""

    subject = f"⚠️ Squeeze-Alarm — {ticker} — {reason[:60]} — {datetime.now(BERLIN).strftime('%H:%M')}"

    body = (
        f"Squeeze-Alarm: {ticker}\n"
        f"{'=' * 50}\n\n"
        f"Auslöser:     {reason}\n"
        f"Zeitpunkt:    {now_str}\n\n"
        f"Score:        {live.get('score', 0):.1f} Pkt  "
        f"({sign}{score_delta:.1f} vs. Morgen-Baseline {base.get('score', 0):.1f})\n"
        f"Kurs:         ${live.get('price', 0):.2f}  "
        f"({'+'if live.get('change_pct',0)>=0 else ''}"
        f"{live.get('change_pct', 0):.1f} % heute)\n"
        f"Rel. Volumen: {live.get('rel_volume', 0):.1f}×  "
        f"(Baseline: {base.get('rel_volume', 0):.1f}×)\n"
        f"Short Float:  {live.get('short_float', 0):.1f} %\n\n"
        f"→ Website: {PWA_URL}\n\n"
        f"---\n"
        f"Dieser Alarm wird maximal einmal pro {ALERT_COOLDOWN_MINUTES} Minuten "
        f"pro Aktie gesendet."
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
        log.info("✉  Alarm-E-Mail gesendet: %s — %s", ticker, reason[:60])
        return True
    except Exception as exc:
        log.error("E-Mail-Fehler für %s: %s", ticker, exc)
        return False


# ---------------------------------------------------------------------------
# Alarm auslösen + Cooldown aktualisieren
# ---------------------------------------------------------------------------

def send_ntfy_alert(ticker: str, score: int, drivers) -> None:
    """ntfy.sh Push-Notification — parallel zur E-Mail. Fail-soft.

    ``drivers`` darf ``list[str]`` oder ``str`` sein. Topic leer oder
    ``NTFY_ENABLED=False`` → no-op (graceful skip).
    """
    if not NTFY_ENABLED or not NTFY_TOPIC:
        return
    if isinstance(drivers, list):
        drivers_str = " + ".join(drivers) if drivers else "—"
    else:
        drivers_str = str(drivers) if drivers else "—"
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=f"{ticker} 🚀 Score {score} – {drivers_str}".encode("utf-8"),
            headers={
                "Title": f"Squeeze Alert: {ticker}",
                "Priority": "high",
                "Tags": "chart_with_upwards_trend",
            },
            timeout=5,
        )
    except Exception as exc:
        log.warning("ntfy push fehlgeschlagen für %s: %s", ticker, exc)


def trigger_alert(
    ticker: str,
    reason: str,
    live: dict,
    base: dict,
    last_alerts: dict,
) -> bool:
    """Sendet E-Mail und setzt Cooldown. Gibt True zurück wenn E-Mail rausging."""
    send_ntfy_alert(ticker, live.get("score", 0), reason)
    sent = send_alert_email(ticker, reason, live, base)
    if sent:
        last_alerts[ticker] = {
            "time":   datetime.now(BERLIN).isoformat(),
            "reason": reason,
        }
        save_last_alerts(last_alerts)
    return sent


# ---------------------------------------------------------------------------
# Hauptlogik
# ---------------------------------------------------------------------------

def main() -> None:
    if not is_market_open():
        log.info("Markt geschlossen — nichts zu tun.")
        return

    log.info("=== Squeeze-Alert %s ===", datetime.now(BERLIN).strftime("%Y-%m-%d %H:%M"))

    baseline     = load_or_create_baseline()
    base_list    = baseline.get("candidates", [])
    base_tickers = {c["ticker"] for c in base_list}

    if not base_list:
        log.warning("Keine Baseline-Kandidaten — Abbruch.")
        return

    last_alerts = load_last_alerts()

    # ------------------------------------------------------------------
    # 1–3: Baseline-Kandidaten auf Score / Volumen / Kurs überwachen
    # ------------------------------------------------------------------
    for base in base_list:
        ticker = base["ticker"]
        log.info("Prüfe %s …", ticker)

        if is_on_cooldown(ticker, last_alerts):
            log.info("  %s im Cooldown — übersprungen.", ticker)
            time.sleep(0.2)
            continue

        live = fetch_live(ticker)
        if not live:
            time.sleep(0.5)
            continue

        # Alarm 1: Score-Anstieg
        score_delta = live["score"] - base.get("score", 0)
        if score_delta >= ALERT_SCORE_DELTA:
            reason = (
                f"Score stieg um {score_delta:.1f} Pkt seit dem Morgen-Report "
                f"({base.get('score', 0):.1f} → {live['score']:.1f})"
            )
            if trigger_alert(ticker, reason, live, base, last_alerts):
                time.sleep(0.4)
                continue

        # Alarm 2: Volumen-Schub
        base_rv  = base.get("rel_volume", 0.0)
        live_rv  = live["rel_volume"]
        if base_rv > 0:
            rv_change = (live_rv - base_rv) / base_rv
            if rv_change >= ALERT_VOLUME_DELTA:
                reason = (
                    f"Rel. Volumen stieg um {rv_change * 100:.0f} % "
                    f"({base_rv:.1f}× → {live_rv:.1f}×)"
                )
                if trigger_alert(ticker, reason, live, base, last_alerts):
                    time.sleep(0.4)
                    continue

        # Alarm 3: Kursanstieg
        base_price = base.get("price", 0.0)
        if base_price > 0:
            price_delta_pct = (live["price"] - base_price) / base_price * 100
            if price_delta_pct >= ALERT_PRICE_DELTA:
                reason = (
                    f"Kurs stieg um {price_delta_pct:.1f} % seit dem Morgen-Report "
                    f"(${base_price:.2f} → ${live['price']:.2f})"
                )
                trigger_alert(ticker, reason, live, base, last_alerts)

        time.sleep(0.4)

    # ------------------------------------------------------------------
    # 4: Neue Kandidaten mit Score ≥ ALERT_NEW_CANDIDATE_SCORE (US only)
    # ------------------------------------------------------------------
    log.info("Screener-Schnellscan auf neue Kandidaten …")
    screener_hits = fetch_screener_candidates(region="US", count=25)

    new_tickers = [
        h for h in screener_hits
        if h["ticker"]
        and h["ticker"] not in base_tickers
        and not is_on_cooldown(h["ticker"], last_alerts)
    ]

    # Nur die vielversprechendsten (Short Float > 20 %) per yfinance prüfen
    promising = sorted(
        [h for h in new_tickers if h["short_float"] >= 20.0],
        key=lambda x: x["short_float"],
        reverse=True,
    )[:5]

    for hit in promising:
        ticker = hit["ticker"]
        log.info("  Neukandidaten-Check: %s (SF %.1f %%)", ticker, hit["short_float"])
        live = fetch_live(ticker)
        if not live:
            time.sleep(0.4)
            continue
        if live["score"] >= ALERT_NEW_CANDIDATE_SCORE:
            reason = (
                f"Neuer Kandidat mit Score {live['score']:.1f} Pkt "
                f"(SF {live['short_float']:.1f} %, RV {live['rel_volume']:.1f}×)"
            )
            trigger_alert(ticker, reason, live, {}, last_alerts)
        time.sleep(0.4)

    log.info("Alert-Lauf abgeschlossen.")


if __name__ == "__main__":
    main()
