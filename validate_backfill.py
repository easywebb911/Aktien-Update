#!/usr/bin/env python3
"""
validate_backfill.py — Score-Validierungs-Backfill-Skript
==========================================================

Liest backtest_history.json (READ-ONLY), fetcht via yfinance fehlende
OHLC-Daten und ETF-Baselines, und schreibt eine erweiterte Sicht als
validation_dataset.json.

Zweck: Grundlage für Score-Performance-Auswertung (Bahn A2).
Aufruf: python validate_backfill.py
Output: validation_dataset.json im Repo-Root

HINWEIS pool_size:
    Das Feld pool_size in backtest_history.json spiegelt den Pool-Zustand
    zum Zeitpunkt des ERSTEN Loggings eines Tickers an einem Tag wider,
    nicht den finalen Tagesstand. Bei mehreren Daily-Runs am selben Datum
    können Einträge desselben Tages unterschiedliche pool_size-Werte
    tragen. pool_size wird in validation_dataset.json unverändert
    durchgereicht. Auswertungen mit Pool-Relativ-Position sollten dies
    als Limitation berücksichtigen.

HINWEIS source:
    Einträge mit source="bootstrap" haben einen vereinfachten Score
    (_score_simple), der NICHT dem Production-Score entspricht.
    Bahn A2 muss bootstrap- und live-Einträge separat auswerten.

Idempotent: Mehrfache Ausführung produziert gleiches Ergebnis
(bei gleichem yfinance-Datenstand).
"""
from __future__ import annotations

import json
import logging
import statistics
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("validate_backfill")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)

# ── Pfade ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent
BACKTEST_FILE = REPO_ROOT / "backtest_history.json"
OUTPUT_FILE = REPO_ROOT / "validation_dataset.json"

# ── Konstanten ───────────────────────────────────────────────────────────────
BENCHMARKS = ["SPY", "XBI"]
RETURN_WINDOWS = [1, 3, 5, 10]          # Handelstage
T5_MIN_DAYS = 5                          # Mindest-Vorlauf für T+5
T10_MIN_DAYS = 10                        # Mindest-Vorlauf für T+10
SUCCESS_STRICT_RETURN = 0.20             # +20 % bis T+5
SUCCESS_STRICT_DRAWDOWN = -0.10          # ohne -10 % Drawdown vorher
SUCCESS_CLASSIC_RETURN = 0.10            # +10 % bis T+5
SUCCESS_SHARPE_THRESHOLD = 0.50          # sharpe_t5_proxy > 0.5
DATE_FORMATS = ["%d.%m.%Y", "%Y-%m-%d"]


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _parse_date(s: str) -> date:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unbekanntes Datumsformat: {s!r}")


def _trading_days_since(entry_date: date, ref: date) -> int:
    """Grobe Schätzung: Handelstage zwischen entry_date und ref."""
    if ref <= entry_date:
        return 0
    delta = (ref - entry_date).days
    # ~5/7 der Kalendertage sind Handelstage (Wochenenden abziehen)
    return int(delta * 5 / 7)


def _safe_pct(new_val: float | None, old_val: float | None) -> float | None:
    if new_val is None or old_val is None or old_val == 0:
        return None
    return (new_val - old_val) / abs(old_val)


def _nth_close(closes: list[float | None], n: int) -> float | None:
    """Gibt Close an Handelstag-Index n zurück (0-basiert)."""
    if n < len(closes) and closes[n] is not None:
        return closes[n]
    return None


def _nth_low(lows: list[float | None], n: int) -> float | None:
    if n < len(lows) and lows[n] is not None:
        return lows[n]
    return None


# ── Kern-Berechnungen ────────────────────────────────────────────────────────

def _compute_drawdown(entry_price: float,
                      lows: list[float | None],
                      n_days: int) -> float | None:
    """Maximaler Drawdown von entry_price bis Handelstag n_days (inkl.)."""
    relevant = [l for l in lows[:n_days + 1] if l is not None]
    if not relevant:
        return None
    min_low = min(relevant)
    return (min_low - entry_price) / entry_price  # negativ = Drawdown


def _compute_sharpe(closes: list[float | None], n_days: int) -> float | None:
    """Rohe Sharpe-Proxy: Gesamt-Return / StdDev der Tages-Returns."""
    valid = [c for c in closes[:n_days + 1] if c is not None]
    if len(valid) < 3:
        return None
    daily_rets = [
        (valid[i] - valid[i - 1]) / valid[i - 1]
        for i in range(1, len(valid))
    ]
    if len(daily_rets) < 2:
        return None
    stdev = statistics.stdev(daily_rets)
    if stdev == 0:
        return None
    total_ret = (valid[-1] - valid[0]) / valid[0]
    return total_ret / stdev


def _compute_success(
    return_5d: float | None,
    max_drawdown: float | None,
    sharpe: float | None,
) -> tuple[bool | None, bool | None, bool | None]:
    """Gibt (success_strict, success_classic, success_sharpe) zurück."""
    if return_5d is None:
        strict, classic = None, None
    else:
        classic = return_5d >= SUCCESS_CLASSIC_RETURN
        if max_drawdown is None:
            strict = None
        else:
            strict = (return_5d >= SUCCESS_STRICT_RETURN and
                      max_drawdown >= SUCCESS_STRICT_DRAWDOWN)
    sharpe_ok = None if sharpe is None else sharpe > SUCCESS_SHARPE_THRESHOLD
    return strict, classic, sharpe_ok


# ── Bulk-Fetch ───────────────────────────────────────────────────────────────

def _bulk_fetch(tickers: list[str], start: date, end: date) -> dict:
    """
    Fetcht OHLC für alle Ticker + Benchmarks in einem einzigen
    yf.download-Call. Gibt ein Dict {ticker: {"dates":[], "opens":[],
    "highs":[], "lows":[], "closes":[]}} zurück.
    """
    import yfinance as yf
    import pandas as pd

    all_tickers = list(set(tickers) | set(BENCHMARKS))
    log.info("yf.download: %d Symbole, %s → %s …", len(all_tickers), start, end)

    raw = yf.download(
        tickers=all_tickers,
        start=start.strftime("%Y-%m-%d"),
        end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
        progress=False,
        group_by="ticker",
        auto_adjust=True,
        threads=True,
    )
    log.info("yf.download abgeschlossen.")

    result: dict[str, dict] = {}

    for tkr in all_tickers:
        try:
            if len(all_tickers) == 1:
                df = raw
            else:
                df = raw[tkr] if tkr in raw.columns.get_level_values(0) else pd.DataFrame()

            if df is None or df.empty:
                result[tkr] = {}
                continue

            df = df.dropna(subset=["Close"])
            result[tkr] = {
                "dates":  [d.date() for d in df.index],
                "opens":  df["Open"].tolist(),
                "highs":  df["High"].tolist(),
                "lows":   df["Low"].tolist(),
                "closes": df["Close"].tolist(),
            }
        except Exception as exc:
            log.warning("Fetch-Fehler %s: %s", tkr, exc)
            result[tkr] = {}

    return result


def _get_series_from(tkr_data: dict,
                     entry_date: date,
                     n_days: int) -> tuple[list, list, list, list]:
    """
    Gibt (closes, opens, highs, lows) ab entry_date für n_days
    Handelstage zurück. Fehlende Tage → None.
    """
    if not tkr_data:
        return [None] * (n_days + 1), [None] * (n_days + 1), \
               [None] * (n_days + 1), [None] * (n_days + 1)

    dates = tkr_data["dates"]
    try:
        start_idx = next(i for i, d in enumerate(dates) if d >= entry_date)
    except StopIteration:
        return [None] * (n_days + 1), [None] * (n_days + 1), \
               [None] * (n_days + 1), [None] * (n_days + 1)

    closes = []
    opens = []
    highs = []
    lows = []
    for offset in range(n_days + 1):
        idx = start_idx + offset
        if idx < len(dates):
            closes.append(tkr_data["closes"][idx])
            opens.append(tkr_data["opens"][idx])
            highs.append(tkr_data["highs"][idx])
            lows.append(tkr_data["lows"][idx])
        else:
            closes.append(None)
            opens.append(None)
            highs.append(None)
            lows.append(None)
    return closes, opens, highs, lows


# ── Pro-Eintrag-Verarbeitung ─────────────────────────────────────────────────

def _enrich_entry(entry: dict,
                  tkr_data: dict,
                  spy_data: dict,
                  xbi_data: dict,
                  today: date) -> dict:
    """
    Nimmt einen backtest_history-Eintrag und reichert ihn an.
    Gibt den erweiterten Eintrag zurück.
    """
    out = dict(entry)  # shallow copy, original unverändert

    entry_date = _parse_date(entry["date"])
    entry_price = entry.get("entry_price") or entry.get("entry_price_t1")
    trading_days_available = _trading_days_since(entry_date, today)

    # ── Datenqualität vorklären ───────────────────────────────────────────
    if not tkr_data:
        out["data_quality"] = "delisted"
        out["missing_fields"] = ["all_ohlc"]
        out["return_1d"] = None
        out["return_1d_t1"] = None
        out["min_low_t0_to_t5"] = None
        out["max_drawdown_t0_to_t5"] = None
        out["high_t5"] = None
        out["low_t5"] = None
        out["stdev_returns_t0_to_t5"] = None
        out["sharpe_t5_proxy"] = None
        for bench in ("spy", "xbi"):
            for w in RETURN_WINDOWS:
                out[f"{bench}_return_{w}d"] = None
        out["excess_return_5d_vs_spy"] = None
        out["excess_return_5d_vs_xbi"] = None
        out["success_strict"] = None
        out["success_classic"] = None
        out["success_sharpe"] = None
        return out

    if trading_days_available < T5_MIN_DAYS:
        out["data_quality"] = "too_recent"
    else:
        out["data_quality"] = "complete"  # vorläufig; wird ggf. auf partial gesetzt

    # ── OHLC-Serien holen ────────────────────────────────────────────────
    closes, opens, highs, lows = _get_series_from(tkr_data, entry_date, 11)

    # ── Basis-Returns (aus backtest_history übernehmen falls vorhanden) ──
    # Wir berechnen return_1d neu aus OHLC (konsistenter)
    c0 = _nth_close(closes, 0)
    c1 = _nth_close(closes, 1)
    c2 = _nth_close(closes, 2)

    out["return_1d"] = _safe_pct(c1, c0)
    out["return_1d_t1"] = _safe_pct(c2, c1)

    # ── T+5 Felder ───────────────────────────────────────────────────────
    missing = []
    if trading_days_available < T5_MIN_DAYS:
        out["min_low_t0_to_t5"] = None
        out["max_drawdown_t0_to_t5"] = None
        out["high_t5"] = None
        out["low_t5"] = None
        out["stdev_returns_t0_to_t5"] = None
        out["sharpe_t5_proxy"] = None
        missing += ["min_low_t0_to_t5", "max_drawdown_t0_to_t5",
                    "high_t5", "low_t5", "stdev_returns_t0_to_t5",
                    "sharpe_t5_proxy"]
    else:
        lows_t5 = [_nth_low(lows, i) for i in range(6)]
        out["min_low_t0_to_t5"] = min(
            (l for l in lows_t5 if l is not None), default=None)

        if entry_price and out["min_low_t0_to_t5"] is not None:
            out["max_drawdown_t0_to_t5"] = _compute_drawdown(
                entry_price, lows, 5)
        else:
            out["max_drawdown_t0_to_t5"] = None

        out["high_t5"] = max(
            (h for h in [highs[5]] if h is not None), default=None)
        out["low_t5"] = lows[5] if lows[5] is not None else None

        # stdev und sharpe aus Close-Reihe
        closes_t5 = [_nth_close(closes, i) for i in range(6)]
        valid_closes = [c for c in closes_t5 if c is not None]
        if len(valid_closes) >= 3:
            daily_rets = [
                (valid_closes[i] - valid_closes[i - 1]) / valid_closes[i - 1]
                for i in range(1, len(valid_closes))
            ]
            out["stdev_returns_t0_to_t5"] = (
                statistics.stdev(daily_rets) if len(daily_rets) >= 2 else None)
        else:
            out["stdev_returns_t0_to_t5"] = None
            missing.append("stdev_returns_t0_to_t5")

        # sharpe_proxy aus return_5d (bestehend) / stdev
        ret5 = entry.get("return_5d")
        if ret5 is not None and out["stdev_returns_t0_to_t5"]:
            out["sharpe_t5_proxy"] = ret5 / out["stdev_returns_t0_to_t5"]
        else:
            out["sharpe_t5_proxy"] = None
            if ret5 is None:
                missing.append("sharpe_t5_proxy")

    # ── Benchmark-Returns ────────────────────────────────────────────────
    for bench_name, bench_data in (("spy", spy_data), ("xbi", xbi_data)):
        b_closes, _, _, _ = _get_series_from(bench_data, entry_date, 11)
        b_c0 = _nth_close(b_closes, 0)
        for w in RETURN_WINDOWS:
            b_cw = _nth_close(b_closes, w)
            key = f"{bench_name}_return_{w}d"
            val = _safe_pct(b_cw, b_c0)
            out[key] = val
            if val is None and trading_days_available >= w:
                missing.append(key)

    ret5 = entry.get("return_5d")
    out["excess_return_5d_vs_spy"] = (
        _safe_pct(1 + (ret5 or 0), 1 + (out.get("spy_return_5d") or 0))
        if ret5 is not None and out.get("spy_return_5d") is not None
        else None
    )
    out["excess_return_5d_vs_xbi"] = (
        _safe_pct(1 + (ret5 or 0), 1 + (out.get("xbi_return_5d") or 0))
        if ret5 is not None and out.get("xbi_return_5d") is not None
        else None
    )

    # ── Erfolgs-Indikatoren ───────────────────────────────────────────────
    strict, classic, sharpe_ok = _compute_success(
        ret5,
        out.get("max_drawdown_t0_to_t5"),
        out.get("sharpe_t5_proxy"),
    )
    out["success_strict"] = strict
    out["success_classic"] = classic
    out["success_sharpe"] = sharpe_ok

    # ── Datenqualität finalisieren ────────────────────────────────────────
    out["missing_fields"] = missing
    if out["data_quality"] != "too_recent" and missing:
        out["data_quality"] = "partial"

    return out


# ── Haupt-Pipeline ───────────────────────────────────────────────────────────

def run(backtest_file: Path = BACKTEST_FILE,
        output_file: Path = OUTPUT_FILE) -> dict:
    """
    Haupt-Einstiegspunkt. Gibt Summary-Dict zurück.
    """
    # Einlesen
    if not backtest_file.exists():
        log.error("backtest_history.json nicht gefunden: %s", backtest_file)
        sys.exit(1)

    with backtest_file.open(encoding="utf-8") as f:
        history: list[dict] = json.load(f)

    log.info("Eingelesen: %d Einträge aus %s", len(history), backtest_file)

    today = date.today()
    tickers = list({e["ticker"] for e in history})
    dates = [_parse_date(e["date"]) for e in history]
    earliest = min(dates)
    fetch_start = earliest - timedelta(days=14)

    # Bulk-Fetch
    bulk = _bulk_fetch(tickers, fetch_start, today)
    spy_data = bulk.get("SPY", {})
    xbi_data = bulk.get("XBI", {})

    # Anreichern
    enriched = []
    counters: dict[str, int] = {
        "complete": 0, "partial": 0, "delisted": 0, "too_recent": 0}

    for i, entry in enumerate(history):
        tkr = entry["ticker"]
        tkr_data = bulk.get(tkr, {})
        out = _enrich_entry(entry, tkr_data, spy_data, xbi_data, today)
        enriched.append(out)
        counters[out["data_quality"]] = counters.get(out["data_quality"], 0) + 1

        if (i + 1) % 100 == 0:
            log.info("  Fortschritt: %d / %d …", i + 1, len(history))

    # Schreiben
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2,
                  default=str)

    log.info("Geschrieben: %s (%.1f KB)", output_file,
             output_file.stat().st_size / 1024)

    # Summary
    n_success_classic = sum(
        1 for e in enriched if e.get("success_classic") is True)
    n_success_strict = sum(
        1 for e in enriched if e.get("success_strict") is True)
    complete_entries = [e for e in enriched if e["data_quality"] == "complete"]
    ret5_vals = [e["return_5d"] for e in complete_entries
                 if e.get("return_5d") is not None]
    spy5_vals = [e["spy_return_5d"] for e in complete_entries
                 if e.get("spy_return_5d") is not None]
    mean_ret5 = statistics.mean(ret5_vals) if ret5_vals else None
    mean_spy5 = statistics.mean(spy5_vals) if spy5_vals else None

    summary = {
        "total_entries": len(history),
        "data_quality": counters,
        "unique_tickers": len(tickers),
        "success_classic_count": n_success_classic,
        "success_strict_count": n_success_strict,
        "mean_return_5d_complete": mean_ret5,
        "mean_spy_return_5d_complete": mean_spy5,
    }

    log.info("─── Summary ───────────────────────────────────────")
    log.info("  Gesamt:          %d Einträge", summary["total_entries"])
    log.info("  data_quality:    %s", counters)
    log.info("  success_classic: %d", n_success_classic)
    log.info("  success_strict:  %d", n_success_strict)
    if mean_ret5 is not None:
        log.info("  mean return_5d (complete): %.2f%%", mean_ret5 * 100)
    if mean_spy5 is not None:
        log.info("  mean SPY_5d    (complete): %.2f%%", mean_spy5 * 100)
    log.info("───────────────────────────────────────────────────")

    return summary


# ── Selbsttest ───────────────────────────────────────────────────────────────

def _test_validate_backfill() -> None:
    """
    Mock-basierter Selbsttest — KEIN yfinance-Call.
    Prüft Kernlogik mit synthetischen Daten.
    """
    errors: list[str] = []

    # 1) max_drawdown-Berechnung
    lows = [10.0, 9.5, 8.5, 9.0, 9.8, 10.2]
    dd = _compute_drawdown(10.0, lows, 5)
    assert dd is not None and abs(dd - (-0.15)) < 0.001, \
        f"max_drawdown erwartet -0.15, bekam {dd}"

    # 2) success_strict: +25% T+5 aber -12% Drawdown → False
    strict, classic, _ = _compute_success(0.25, -0.12, None)
    assert strict is False, f"success_strict erwartet False, bekam {strict}"

    # 3) success_strict: +21% T+5 ohne Drawdown → True
    strict, classic, _ = _compute_success(0.21, -0.05, None)
    assert strict is True, f"success_strict erwartet True, bekam {strict}"

    # 4) success_classic: +12% → True
    _, classic, _ = _compute_success(0.12, None, None)
    assert classic is True, f"success_classic erwartet True, bekam {classic}"

    # 5) success_classic: +9% → False
    _, classic, _ = _compute_success(0.09, None, None)
    assert classic is False, f"success_classic erwartet False, bekam {classic}"

    # 6) success_sharpe: proxy > 0.5
    _, _, sharpe_ok = _compute_success(None, None, 0.7)
    assert sharpe_ok is True, f"success_sharpe erwartet True, bekam {sharpe_ok}"
    _, _, sharpe_ok = _compute_success(None, None, 0.3)
    assert sharpe_ok is False, f"success_sharpe erwartet False, bekam {sharpe_ok}"

    # 7) excess_return-Berechnung
    ret_ticker = 0.20   # +20%
    ret_spy = 0.05      # +5%
    excess = _safe_pct(1 + ret_ticker, 1 + ret_spy)
    assert excess is not None and abs(excess - (1.20/1.05 - 1)) < 0.001, \
        f"excess_return falsch: {excess}"

    # 8) data_quality "too_recent": trading_days < T5_MIN_DAYS
    # Simuliert über _trading_days_since
    today = date.today()
    entry_date_recent = today - timedelta(days=2)
    td = _trading_days_since(entry_date_recent, today)
    assert td < T5_MIN_DAYS, f"too_recent-Check: {td} sollte < {T5_MIN_DAYS}"

    # 9) _safe_pct Edge-Cases
    assert _safe_pct(None, 10.0) is None
    assert _safe_pct(10.0, None) is None
    assert _safe_pct(10.0, 0.0) is None
    assert abs(_safe_pct(11.0, 10.0) - 0.10) < 0.001

    # 10) _nth_close / _nth_low Bounds
    assert _nth_close([1.0, 2.0], 5) is None
    assert _nth_low([1.0, None, 3.0], 1) is None

    if errors:
        print("SELBSTTEST FEHLGESCHLAGEN:")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print("OK: Alle Selbsttest-Checks bestanden (10 Checks).")


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--test" in sys.argv:
        _test_validate_backfill()
    else:
        run()
