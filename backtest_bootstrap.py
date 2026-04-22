#!/usr/bin/env python3
"""Einmaliges Bootstrap-Skript für historische Backtesting-Daten.

Sammelt für eine feste Liste bekannter Squeeze-Kandidaten die letzten
LOOKBACK_DAYS Handelstage aus yfinance, berechnet pro Tag einen
vereinfachten Score aus RVOL + Momentum + geschätztem Short Float und
füllt die 3/5/10-Tage-Returns direkt aus der Kurs-History (im Gegensatz
zum täglichen Pipeline-Run, der Returns erst nach Ablauf der Fenster
nachtragen kann).

Nur potenzielle Signal-Tage (RVOL ≥ RVOL_MIN) werden eingepflegt;
bestehende (ticker, date)-Einträge werden übersprungen. Alle neuen
Einträge tragen ``source: "bootstrap"`` zur Unterscheidung von echten
Daily-Run-Einträgen.

Ausführung (einmalig):
    python backtest_bootstrap.py
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

from config import BACKTEST_FILE, BACKTEST_RETURN_WINDOWS

log = logging.getLogger("backtest_bootstrap")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(message)s",
                    datefmt="%H:%M:%S")

# ── Parameter ───────────────────────────────────────────────────────────────
BOOTSTRAP_TICKERS = [
    # Bestehend (PROG/FFIE wurden nach delisting-Fehlern entfernt)
    "GME", "AMC", "BBBY", "KOSS", "MULN", "CLOV",
    "NMAX", "MSTR", "SPCE", "SIGA", "HIMS", "QUBT",
    # WallStreetBets 2021
    "BB", "NOK", "EXPR", "NAKD", "SNDL",
    # EV-Squeezes 2020–2022
    "NKLA", "RIDE", "WKHS", "GOEV",
    # Weitere klassische Squeezes
    "ATER", "BGFV", "OPAD", "IRBT",
    "DWAC", "PHUN", "SPRT", "GREE",
    # Aktuelle Short-Kandidaten
    "RDDT", "ACHR", "JOBY", "BYND",
    "HOOD", "SOFI", "CHPT", "NVAX",
    # Fintech/Crypto-nahe
    "VERB", "CRON", "TLRY", "ACB",
]
LOOKBACK_DAYS = 365   # Kalendertage Rückschau
RVOL_MIN      = 1.5   # nur potenzielle Signal-Tage
MA_WINDOW     = 20    # 20-Handelstage-Durchschnitt für RVOL


def _load_history() -> list[dict]:
    path = Path(BACKTEST_FILE)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        log.error("%s ist corrupt — bricht ab", BACKTEST_FILE)
        sys.exit(1)


def _save_history(entries: list[dict]) -> None:
    Path(BACKTEST_FILE).write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _score_simple(sf: float, rvol: float, mom: float) -> float:
    """Vereinfachter Score 0–100: SF (40) + RVOL (30) + Momentum (30).

    Mirrort die Sättigungen von ``score()`` in generate_report.py, ohne
    Float-Größe, DTC, Kombi-Bonus und FINRA-Trend-Bonus — diese sind
    retroaktiv nicht verlässlich rekonstruierbar.
    """
    sf_pts  = min(sf / 50.0, 1.0) * 40
    rv_pts  = min(max((rvol - 1.0) / 2.0, 0.0), 1.0) * 30
    mom_pts = min(max(mom, 0.0) / 8.0, 1.0) * 30
    return round(sf_pts + rv_pts + mom_pts, 2)


def _process_ticker(ticker: str, existing_keys: set[tuple]) -> list[dict]:
    """Lädt Info + History, erzeugt Bootstrap-Einträge für Signal-Tage."""
    try:
        tk   = yf.Ticker(ticker)
        info = tk.info or {}
    except Exception as exc:  # noqa: BLE001 — yfinance wirft diverses
        log.warning("  %s: info-Fetch fehlgeschlagen: %s", ticker, exc)
        info = {}

    # Aktuelle Werte als Schätzung für historische Tage (FINRA-Snapshot
    # pro Handelstag ist für einen einmaligen Bootstrap zu teuer).
    sf_raw = info.get("shortPercentOfFloat")
    if sf_raw is None:
        sf_est = 0.0
    else:
        sf_est = float(sf_raw) * 100 if float(sf_raw) <= 1.0 else float(sf_raw)
    dtc_est = float(info.get("shortRatio") or 0.0)

    # Extra MA_WINDOW+Puffer Kalendertage laden, damit der erste Rückschau-Tag
    # bereits einen gültigen 20-Tage-Durchschnitt hat.
    start = (datetime.now()
             - timedelta(days=LOOKBACK_DAYS + MA_WINDOW + 20)).date()
    try:
        hist = tk.history(start=start, interval="1d", auto_adjust=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("  %s: history-Fetch fehlgeschlagen: %s", ticker, exc)
        return []
    if hist is None or hist.empty:
        log.warning("  %s: keine History (möglicherweise delisted)", ticker)
        return []
    if "Close" not in hist or "Volume" not in hist:
        log.warning("  %s: History ohne Close/Volume", ticker)
        return []

    closes  = hist["Close"]
    volumes = hist["Volume"]
    cutoff_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).date()

    out: list[dict] = []
    n = len(hist)
    for i in range(MA_WINDOW, n):
        d = hist.index[i].date()
        if d < cutoff_date:
            continue

        vol = float(volumes.iloc[i]) if volumes.iloc[i] else 0.0
        prev_vols = volumes.iloc[i - MA_WINDOW:i]
        avg_vol = float(prev_vols.mean()) if len(prev_vols) else 0.0
        if avg_vol <= 0 or vol <= 0:
            continue
        rvol = vol / avg_vol
        if rvol < RVOL_MIN:
            continue

        close_today = float(closes.iloc[i])
        close_prev  = float(closes.iloc[i - 1])
        if close_today <= 0 or close_prev <= 0:
            continue
        mom = (close_today / close_prev - 1) * 100

        date_str = d.strftime("%d.%m.%Y")
        key = (ticker, date_str)
        if key in existing_keys:
            continue

        # Returns direkt aus zukünftiger History berechnen (Bootstrap-Vorteil)
        returns: dict[str, float | None] = {}
        for win in BACKTEST_RETURN_WINDOWS:
            fut_idx = i + win
            if fut_idx < n:
                fut_close = float(closes.iloc[fut_idx])
                returns[f"return_{win}d"] = round(
                    (fut_close / close_today - 1) * 100, 2
                )
            else:
                returns[f"return_{win}d"] = None

        entry = {
            "date":        date_str,
            "ticker":      ticker,
            "score":       _score_simple(sf_est, rvol, mom),
            "entry_price": round(close_today, 4),
            "short_float": round(sf_est, 2),
            "dtc":         round(dtc_est, 2),
            "rvol":        round(rvol, 3),
            "si_trend":    "no_data",
            "return_3d":   returns.get("return_3d"),
            "return_5d":   returns.get("return_5d"),
            "return_10d":  returns.get("return_10d"),
            "source":      "bootstrap",
        }
        out.append(entry)
        existing_keys.add(key)

    return out


def main() -> None:
    # Eingabeliste kann Duplikate enthalten (CLOV ist 2× gelistet)
    tickers = list(dict.fromkeys(BOOTSTRAP_TICKERS))
    log.info("Bootstrap-Run: %d Ticker, Rückschau %d Tage, RVOL ≥ %.1f",
             len(tickers), LOOKBACK_DAYS, RVOL_MIN)

    history = _load_history()
    existing_keys = {(e.get("ticker"), e.get("date")) for e in history}
    log.info("backtest_history.json: %d bestehende Einträge", len(history))

    total_new = 0
    for ticker in tickers:
        log.info("→ %s …", ticker)
        new = _process_ticker(ticker, existing_keys)
        log.info("   %d neue Einträge", len(new))
        history.extend(new)
        total_new += len(new)

    # Deterministische Sortierung (Datum, Ticker) für saubere Git-Diffs
    def _sortkey(e: dict):
        try:
            return (datetime.strptime(e.get("date", ""), "%d.%m.%Y").date(),
                    e.get("ticker", ""))
        except ValueError:
            return (datetime.min.date(), e.get("ticker", ""))

    history.sort(key=_sortkey)
    _save_history(history)
    log.info("FERTIG: %d neue Bootstrap-Einträge, total %d",
             total_new, len(history))


if __name__ == "__main__":
    main()
