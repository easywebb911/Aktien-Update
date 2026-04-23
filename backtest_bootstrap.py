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


def _fill_t1_fields(entry: dict, t1_idx: int, closes, n: int) -> bool:
    """Füllt fehlende T+1-Felder eines bestehenden Eintrags.

    Ändert ``entry`` in-place. Gibt True zurück, wenn mindestens ein Feld
    tatsächlich gefüllt wurde. Bereits vorhandene (nicht-None) Werte werden
    nicht überschrieben — idempotent bei wiederholten Aufrufen.
    """
    if t1_idx >= n:
        return False
    close_t1 = float(closes.iloc[t1_idx])
    if close_t1 <= 0:
        return False
    changed = False
    if entry.get("entry_price_t1") is None:
        entry["entry_price_t1"] = round(close_t1, 4)
        changed = True
    for win in BACKTEST_RETURN_WINDOWS:
        k = f"return_{win}d_t1"
        if entry.get(k) is None:
            fut_idx = t1_idx + win
            if fut_idx < n:
                fut_close = float(closes.iloc[fut_idx])
                entry[k] = round((fut_close / close_t1 - 1) * 100, 2)
                changed = True
    return changed


def _process_ticker(
    ticker: str,
    existing_by_key: dict[tuple, dict],
) -> tuple[list[dict], int]:
    """Lädt Info + History, erzeugt Bootstrap-Einträge für Signal-Tage.

    Zwei Aufgaben:
      1. Update-Pass: Für bestehende Einträge dieses Tickers werden fehlende
         T+1-Felder aus der historischen Kurs-Kurve nachgefüllt (in-place).
      2. Signal-Detection: Neue Einträge für RVOL≥1.5-Tage, die noch nicht im
         File sind.

    Rückgabe ``(neue_einträge, n_updated)``.
    """
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
        return [], 0
    if hist is None or hist.empty:
        log.warning("  %s: keine History (möglicherweise delisted)", ticker)
        return [], 0
    if "Close" not in hist or "Volume" not in hist:
        log.warning("  %s: History ohne Close/Volume", ticker)
        return [], 0

    closes  = hist["Close"]
    volumes = hist["Volume"]
    n = len(hist)

    # ── Pass 1: Update bestehende Einträge (T+1-Nachfüllung) ────────────────
    date_to_idx = {hist.index[k].date(): k for k in range(n)}
    n_updated = 0
    for (t, date_str), entry in existing_by_key.items():
        if t != ticker:
            continue
        # Nur updaten wenn mindestens ein T+1-Feld fehlt
        if (entry.get("entry_price_t1") is not None
                and all(entry.get(f"return_{w}d_t1") is not None
                        for w in BACKTEST_RETURN_WINDOWS)):
            continue
        try:
            entry_dt = datetime.strptime(date_str, "%d.%m.%Y").date()
        except (ValueError, TypeError):
            continue
        ei = date_to_idx.get(entry_dt)
        if ei is None:
            continue
        if _fill_t1_fields(entry, ei + 1, closes, n):
            n_updated += 1

    # ── Pass 2: Neue Signal-Tage (RVOL ≥ 1.5, noch nicht im File) ───────────
    cutoff_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).date()
    out: list[dict] = []
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
        if key in existing_by_key:
            continue

        # Returns direkt aus zukünftiger History berechnen (Bootstrap-Vorteil).
        # T+0: Einstieg am Signal-Tag (Close des Tages, unrealistisch aber
        #      Referenz-Wert).
        # T+1: Einstieg am nächsten Handelstag (realistischer, Signal
        #      wird erst nach Börsenschluss sichtbar).
        returns: dict[str, float | None] = {}
        t1_idx = i + 1
        close_t1 = float(closes.iloc[t1_idx]) if t1_idx < n else None
        for win in BACKTEST_RETURN_WINDOWS:
            fut_idx = i + win
            returns[f"return_{win}d"] = (
                round((float(closes.iloc[fut_idx]) / close_today - 1) * 100, 2)
                if fut_idx < n and close_today > 0 else None
            )
            fut_idx_t1 = t1_idx + win
            returns[f"return_{win}d_t1"] = (
                round((float(closes.iloc[fut_idx_t1]) / close_t1 - 1) * 100, 2)
                if close_t1 is not None and close_t1 > 0 and fut_idx_t1 < n
                else None
            )

        entry = {
            "date":          date_str,
            "ticker":        ticker,
            "score":         _score_simple(sf_est, rvol, mom),
            "entry_price":   round(close_today, 4),
            "entry_price_t1": round(close_t1, 4) if close_t1 is not None else None,
            "short_float":   round(sf_est, 2),
            "dtc":           round(dtc_est, 2),
            "rvol":          round(rvol, 3),
            "si_trend":      "no_data",
            "return_3d":     returns.get("return_3d"),
            "return_5d":     returns.get("return_5d"),
            "return_10d":    returns.get("return_10d"),
            "return_3d_t1":  returns.get("return_3d_t1"),
            "return_5d_t1":  returns.get("return_5d_t1"),
            "return_10d_t1": returns.get("return_10d_t1"),
            "source":      "bootstrap",
        }
        out.append(entry)
        existing_by_key[key] = entry

    return out, n_updated


def main() -> None:
    # Eingabeliste kann Duplikate enthalten (CLOV ist 2× gelistet)
    tickers = list(dict.fromkeys(BOOTSTRAP_TICKERS))
    log.info("Bootstrap-Run: %d Ticker, Rückschau %d Tage, RVOL ≥ %.1f",
             len(tickers), LOOKBACK_DAYS, RVOL_MIN)

    history = _load_history()
    # Dict aus Referenzen: erlaubt In-Place-Updates an bestehenden Einträgen
    # (Nachfüllen fehlender T+1-Felder).
    existing_by_key: dict[tuple, dict] = {
        (e.get("ticker"), e.get("date")): e for e in history
    }
    log.info("backtest_history.json: %d bestehende Einträge", len(history))

    total_new = 0
    total_updated = 0
    for ticker in tickers:
        log.info("→ %s …", ticker)
        new, n_updated = _process_ticker(ticker, existing_by_key)
        log.info("   %d neue Einträge", len(new))
        if n_updated:
            log.info("   %s: %d bestehende Einträge mit T+1-Daten nachgefüllt",
                     ticker, n_updated)
        history.extend(new)
        total_new += len(new)
        total_updated += n_updated

    # Deterministische Sortierung (Datum, Ticker) für saubere Git-Diffs
    def _sortkey(e: dict):
        try:
            return (datetime.strptime(e.get("date", ""), "%d.%m.%Y").date(),
                    e.get("ticker", ""))
        except ValueError:
            return (datetime.min.date(), e.get("ticker", ""))

    history.sort(key=_sortkey)
    _save_history(history)
    log.info("FERTIG: %d neue Bootstrap-Einträge · %d bestehende mit "
             "T+1-Daten nachgefüllt · total %d",
             total_new, total_updated, len(history))


if __name__ == "__main__":
    main()
