#!/usr/bin/env python3
"""Einmal-Backfill-Skript: ``max_gain_pct`` auf Alt-Records in
``backtest_history.json`` retroaktiv füllen (Hypothese-C-Vorbau, Stufe 3).

STUFE 1 — nur Skript + Dry-Run + Test. Live-Lauf ist Stufe 2 mit separater
Anordnung.

MECHANIK (aus Diagnose 02.07.2026):
    Load  → Filter  → Bulk-Fetch  → Compute  → Atomic-Write.

- Load: ``backtest_history.json`` read-only.
- Filter: ``schema_v == 4`` UND ``"max_gain_pct" NOT in e`` (idempotent) UND
  ``≥ 10`` Trading-Days reif ab ``entry_date``.
- Bulk-Fetch: EIN ``yf.download(unique_tickers, earliest_edate−14d..today,
  threads=True, auto_adjust=True)``-Call. Fail-soft pro Ticker (leer → skip
  + Log). Konsistent zum Rolling-Update-Semantik im Live-Pfad
  (``backtest_history._append_backtest_entries`` Z. 805–878, gleiche
  Slice-Mechanik).
- Pro Target: ``df_since = df[df.index.date >= edate].iloc[:11]`` (identisch
  zum Rolling-Update-Fenster, ≤ 10 Handelstage ab Entry) →
  ``_compute_max_gain_pct(df_since)`` (importiert aus
  ``backtest_history.py``, NICHT dupliziert — Drift-Schutz).
- **NUR ``e["max_gain_pct"]`` wird gesetzt.** Kein anderes Feld angerührt.
- Atomic Write: ``tmp + os.replace`` NUR am Ende (entweder-oder-nichts).

RACE-SCHUTZ (Stufe-2-Live-Lauf, doppelt):
    1. ``fcntl.flock`` (exclusive, non-blocking) auf ``backtest_history.json``
       für die gesamte Read→Compute→Write-Sequenz. Release nach Write.
    2. Zeitfenster-Guard: Live-Lauf verweigert innerhalb ±30 Min um die
       schweren Cron-Writes (06:17 UTC Premarket / 21:17 UTC Postclose Daily-
       Run — beide schreiben Backtest-Records). Der ki_agent-Hourly-Tick
       (xx:17 UTC, ``update_backtest_returns``) ist strukturell nicht per
       Zeitfenster ausschließbar (24×/Tag) — dagegen schützt ausschließlich
       flock.

DRY-RUN (Default, Stufe 1):
    ``python scripts/backfill_max_gain_pct.py``  → dry-run (default)
    ``python scripts/backfill_max_gain_pct.py --live`` → Stufe-2-Live-Lauf
        (verlangt --live explizit; ansonsten kein Schreibversuch).

Dry-Run:
    - Druckt: N Ziel-Records, M unique Tickers, Fenster earliest..today, plus
      Preview für 5 Records (Ticker, entry_date, berechneter max_gain_pct).
    - SCHREIBT NICHTS, kein flock nötig.

Exit-Codes:
    0 = alles ok (dry-run oder live).
    1 = Fehler (Filter-Konflikt, flock-fail, yf-Ausfall, Cron-Window-Block).

Idempotent: mehrfacher Lauf überspringt bereits gefüllte Records. Kein
retroaktives Overwrite. Alle Guards additiv zum Live-Pfad-Verhalten.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import sys
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger("backfill_max_gain")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)

BACKTEST_FILE = ROOT / "backtest_history.json"

MIN_REIFE_TRADING_DAYS = 10          # ≤10-Handelstage-Fenster muss voll sein.
BULK_FETCH_LOOKBACK_DAYS = 14        # ~10 Trading-Days = 14 Kalender-Days Puffer.
CRON_BLOCK_WINDOW_MINUTES = 30       # ±30 Min um 06:17 UTC und 21:17 UTC.
CRON_HEAVY_SLOTS = (                 # nur die Backtest-schreibenden Slots.
    (6, 17),                         # Premarket Daily-Run.
    (21, 17),                        # Postclose Daily-Run.
)

# ─────────────────────────────────────────────────────────────────────────────
# Pure-Logik-Helfer (kein yfinance/pandas-Import — CI-Slot-A-kompatibel).
# ─────────────────────────────────────────────────────────────────────────────


def parse_entry_date(s: str) -> date | None:
    """Akzeptiert ``DD.MM.YYYY`` (Backtest-Format) und ``YYYY-MM-DD``."""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def trading_days_since(entry_date: date, ref: date) -> int:
    """Anzahl Mo–Fr strikt zwischen entry_date (exkl.) und ref (inkl.).

    Feiertage werden vereinfacht NICHT abgezogen — analog
    ``ki_agent._trading_days_elapsed`` (etablierte 5/7-Heuristik). Der
    Reifegrad-Filter darf konservativ Records skippen (5–10 Feiertage/Jahr
    → maximal 1–2 Records mit ≥10-Kalender-Tag-Alter fälschlich als reif).
    """
    if ref <= entry_date:
        return 0
    n = 0
    d = entry_date
    while d < ref:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def select_targets(
    history: list[dict],
    today: date,
    *,
    min_reife: int = MIN_REIFE_TRADING_DAYS,
) -> list[tuple[int, dict, date]]:
    """Filtert Alt-Records, die max_gain_pct-Backfill brauchen.

    Kriterien (ALLE müssen erfüllt sein):
      - ``backtest_schema_version == 4`` (Loader-Bindung, kein Bump)
      - ``"max_gain_pct"`` NICHT im Record (Idempotenz-Guard)
      - Entry-Datum parsebar
      - Reifegrad: ``trading_days_since(entry_date, today) >= min_reife``
        (Fenster ≤ 10 Handelstage voll → keine 0.0-Semantik-Overload-Records)

    Returnt ``[(original_index, entry_dict_ref, entry_date), ...]`` in
    unveränderter Reihenfolge. ``entry_dict_ref`` ist der ORIGINAL-Reference
    aus der ``history``-Liste — spätere Mutation via ``apply_backfill_result``
    wirkt in-place.
    """
    targets: list[tuple[int, dict, date]] = []
    for i, e in enumerate(history):
        if not isinstance(e, dict):
            continue
        if e.get("backtest_schema_version") != 4:
            continue
        if "max_gain_pct" in e:
            continue
        edate = parse_entry_date(e.get("date", ""))
        if edate is None:
            continue
        if trading_days_since(edate, today) < min_reife:
            continue
        targets.append((i, e, edate))
    return targets


def apply_backfill_result(entry: dict, mg: float | None) -> bool:
    """Setzt ``entry["max_gain_pct"] = mg`` — GENAU EIN FELD, sonst nichts.

    Returnt ``True`` wenn geschrieben. ``False`` wenn ``mg is None``
    (Guard analog Rolling-Update-Pfad in ``backtest_history.py:828``).

    **Post-Condition (getestet):** genau ein Key ist neu — ``max_gain_pct``.
    Alle anderen Keys unverändert, keine Reihenfolge-Änderung, kein
    tieferliegender Container mutiert.
    """
    if mg is None:
        return False
    entry["max_gain_pct"] = mg
    return True


def in_cron_block_window(
    now_utc: datetime | None = None,
    *,
    window_min: int = CRON_BLOCK_WINDOW_MINUTES,
    slots: tuple[tuple[int, int], ...] = CRON_HEAVY_SLOTS,
) -> tuple[bool, str]:
    """Prüft, ob ``now_utc`` innerhalb ±window_min um einen Cron-Heavy-Slot
    liegt (06:17 UTC Premarket / 21:17 UTC Postclose).

    Returnt ``(blocked, reason)``. ``blocked=True`` bedeutet: Live-Lauf
    verweigern (Race-Risiko mit paralleler Cron-Write auf
    ``backtest_history.json``). Kein Ki_Agent-hourly-Schutz — dagegen wirkt
    ausschließlich flock.

    Parameter ``now_utc`` ist injizierbar für deterministische Tests.
    ``now_utc=None`` → ``datetime.now(timezone.utc)``.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    now_min = now_utc.hour * 60 + now_utc.minute
    for h, m in slots:
        slot_min = h * 60 + m
        # Distanz zyklisch über 24×60 = 1440 Minuten hinweg berechnen.
        diff = abs(now_min - slot_min)
        diff = min(diff, 1440 - diff)
        if diff < window_min:
            return (
                True,
                f"in ±{window_min}min um {h:02d}:{m:02d} UTC "
                f"(now={now_utc.strftime('%H:%M')} UTC, diff={diff}min)",
            )
    return (False, "")


def load_history(path: pathlib.Path) -> list[dict]:
    """Read-only Load. Wirft bei fehlender Datei / kaputtem JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: pathlib.Path, data: list[dict]) -> None:
    """Atomic Write via ``tmp + os.replace`` (POSIX-atomar).

    Format entspricht dem Live-Pfad ``_append_backtest_entries``-Write
    (``json.dumps(..., ensure_ascii=False, indent=2)``). Kein `default=str`
    — Records sind bereits JSON-serializable (Zahlen/Strings/None).
    """
    tmp = path.with_suffix(path.suffix + ".backfill.tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(tmp, path)


# ─────────────────────────────────────────────────────────────────────────────
# yfinance-abhängige Sektion — kein Import in Slot A des Tests.
# ─────────────────────────────────────────────────────────────────────────────


def bulk_fetch_ohlc(
    tickers: list[str], start: date, end: date
) -> dict[str, Any]:
    """EIN yf.download-Call für alle unique Tickers. Fail-soft pro Ticker.

    Returnt ``{ticker: DataFrame | None}``. ``None`` = Fetch-Fehler /
    delisted / leerer DataFrame → wird im Compute-Loop übersprungen.
    """
    import yfinance as yf
    import pandas as pd

    log.info(
        "yf.download: %d unique tickers, %s → %s (auto_adjust=True, threads=True)",
        len(tickers), start.isoformat(), end.isoformat(),
    )
    try:
        raw = yf.download(
            tickers=" ".join(tickers),
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
        )
    except Exception as exc:
        log.error("Bulk-Fetch failed: %s", exc)
        return {t: None for t in tickers}

    result: dict[str, Any] = {}
    for tkr in tickers:
        try:
            if len(tickers) == 1:
                df = raw
            else:
                df = raw[tkr] if tkr in raw.columns.get_level_values(0) else None
            if df is None or df.empty:
                result[tkr] = None
                continue
            result[tkr] = df.dropna(subset=["Close"])
        except Exception as exc:
            log.warning("Ticker-Slice fail %s: %s", tkr, exc)
            result[tkr] = None
    return result


def build_df_since(df: Any, edate: date, n_bars: int = 11) -> Any:
    """Slice ``df`` auf die ersten ≤ n_bars Bars ab ``edate`` (inklusive).

    Identisch zum Rolling-Update-Muster ``backtest_history.py:826``:
    ``df_since = df[df.index.date >= edate].iloc[:11]``.
    """
    return df[df.index.date >= edate].iloc[:n_bars]


def compute_and_apply_backfill(
    targets: list[tuple[int, dict, date]],
    bulk: dict[str, Any],
) -> tuple[int, int]:
    """Iteriert Targets, holt Slice, ruft _compute_max_gain_pct, wendet an.

    Nutzt den **importierten** Helper aus ``backtest_history`` — KEINE
    Duplizierung (Drift-Schutz per Test A5 in mock_test_max_gain_pct.py).

    Returnt ``(n_filled, n_skipped)``. `n_skipped` zählt Fälle mit
    fehlendem Bulk-Slot / leerem df_since / `mg is None`.
    """
    from backtest_history import _compute_max_gain_pct

    n_filled = 0
    n_skipped = 0
    for i, entry, edate in targets:
        tkr = entry.get("ticker")
        df = bulk.get(tkr) if tkr else None
        if df is None or df.empty:
            n_skipped += 1
            log.debug("skip idx=%d ticker=%s: no bulk data", i, tkr)
            continue
        try:
            df_since = build_df_since(df, edate)
        except Exception as exc:
            n_skipped += 1
            log.warning("skip idx=%d ticker=%s: slice fail %s", i, tkr, exc)
            continue
        mg = _compute_max_gain_pct(df_since)
        if apply_backfill_result(entry, mg):
            n_filled += 1
        else:
            n_skipped += 1
    return n_filled, n_skipped


def preview_targets(
    targets: list[tuple[int, dict, date]],
    bulk: dict[str, Any] | None,
    n: int = 5,
) -> list[dict]:
    """Für Dry-Run-Ausgabe: berechnet max_gain_pct für die ersten ``n``
    Targets (falls Bulk verfügbar) — schreibt NICHTS in die Records.

    Bei ``bulk is None`` (Fetch übersprungen im Dry-Run-Preview-Mode) wird
    ``mg = "(Fetch übersprungen)"`` gesetzt.
    """
    if bulk is None:
        return [
            {
                "idx": i,
                "ticker": e.get("ticker"),
                "date": e.get("date"),
                "entry_date": edate.isoformat(),
                "mg": "(Fetch übersprungen)",
            }
            for i, e, edate in targets[:n]
        ]

    from backtest_history import _compute_max_gain_pct

    preview: list[dict] = []
    for i, e, edate in targets[:n]:
        tkr = e.get("ticker")
        df = bulk.get(tkr) if tkr else None
        if df is None or df.empty:
            mg: Any = None
        else:
            try:
                df_since = build_df_since(df, edate)
                mg = _compute_max_gain_pct(df_since)
            except Exception as exc:
                mg = f"(err: {exc})"
        preview.append(
            {
                "idx": i,
                "ticker": tkr,
                "date": e.get("date"),
                "entry_date": edate.isoformat(),
                "mg": mg,
            }
        )
    return preview


# ─────────────────────────────────────────────────────────────────────────────
# CLI / Main.
# ─────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="Stufe-2-Live-Lauf: schreibt tatsächlich in backtest_history.json. "
             "Ohne diesen Flag = Dry-Run (Default, kein Schreibversuch).",
    )
    p.add_argument(
        "--path",
        default=str(BACKTEST_FILE),
        help=f"Pfad zu backtest_history.json (default: {BACKTEST_FILE})",
    )
    p.add_argument(
        "--fetch-in-dry-run",
        action="store_true",
        help="Auch im Dry-Run yfinance-Fetch für die 5 Preview-Records "
             "durchführen (default: nein — Preview zeigt nur Metadaten).",
    )
    args = p.parse_args(argv)

    path = pathlib.Path(args.path).resolve()
    if not path.exists():
        log.error("File not found: %s", path)
        return 1

    log.info("Modus: %s | Ziel-Datei: %s", "LIVE" if args.live else "DRY-RUN", path)

    # ── Cron-Window-Guard (nur Live) ────────────────────────────────────────
    if args.live:
        blocked, reason = in_cron_block_window()
        if blocked:
            log.error("Live-Lauf verweigert: %s", reason)
            log.error("Warten bis außerhalb ±30min um 06:17 / 21:17 UTC.")
            return 1

    # ── Load ────────────────────────────────────────────────────────────────
    try:
        history = load_history(path)
    except Exception as exc:
        log.error("Load fail: %s", exc)
        return 1
    log.info("Loaded %d records from %s", len(history), path.name)

    # ── Filter ──────────────────────────────────────────────────────────────
    today = date.today()
    targets = select_targets(history, today)
    log.info(
        "Targets: %d (schema_v==4 UND max_gain_pct absent UND reif ≥ %d Trading-Days)",
        len(targets), MIN_REIFE_TRADING_DAYS,
    )
    if not targets:
        log.info("Nichts zu tun — alle reifen v4-Records tragen bereits max_gain_pct.")
        return 0

    unique_tickers = sorted({e.get("ticker") for _, e, _ in targets if e.get("ticker")})
    entry_dates = [ed for _, _, ed in targets]
    earliest, latest = min(entry_dates), max(entry_dates)
    fetch_start = earliest - timedelta(days=BULK_FETCH_LOOKBACK_DAYS)
    fetch_end = today
    log.info(
        "Bulk-Fetch-Fenster: %s .. %s | %d unique Tickers",
        fetch_start, fetch_end, len(unique_tickers),
    )

    # ── DRY-RUN-Zweig ───────────────────────────────────────────────────────
    if not args.live:
        bulk = None
        if args.fetch_in_dry_run:
            log.info("--fetch-in-dry-run gesetzt: Preview mit echtem Bulk-Fetch.")
            bulk = bulk_fetch_ohlc(unique_tickers, fetch_start, fetch_end)
        preview = preview_targets(targets, bulk, n=5)
        log.info("─" * 60)
        log.info("DRY-RUN Preview (erste 5 Targets):")
        for row in preview:
            log.info(
                "  idx=%d ticker=%s date=%s edate=%s → mg=%s",
                row["idx"], row["ticker"], row["date"], row["entry_date"], row["mg"],
            )
        log.info("─" * 60)
        log.info(
            "DRY-RUN Zusammenfassung: %d Targets, %d unique Tickers, "
            "Fenster %s..%s. Keine Schreibvorgänge durchgeführt.",
            len(targets), len(unique_tickers), earliest, latest,
        )
        log.info(
            "Für Live-Lauf: python scripts/backfill_max_gain_pct.py --live "
            "(nur außerhalb ±30min um 06:17/21:17 UTC).",
        )
        return 0

    # ── LIVE-Zweig ──────────────────────────────────────────────────────────
    # flock: exklusiv, non-blocking → falls Daily-Run/ki_agent gerade
    # schreibt, sauber abbrechen statt zu blockieren.
    import fcntl

    try:
        lock_fh = path.open("a+b")
    except OSError as exc:
        log.error("Lock-Open fail: %s", exc)
        return 1
    try:
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            log.error(
                "flock failed (paralleler Writer aktiv?): %s. Backfill "
                "abgebrochen — später erneut versuchen.", exc,
            )
            return 1

        log.info("flock erworben (exklusiv, non-blocking).")

        # Re-Load unter flock (Daily-Run könnte zwischen erstem Load und
        # flock-Erwerb geschrieben haben). Filter neu bewerten.
        try:
            history = load_history(path)
        except Exception as exc:
            log.error("Re-Load unter flock fail: %s", exc)
            return 1
        targets = select_targets(history, today)
        log.info("Re-Targets unter flock: %d", len(targets))
        if not targets:
            log.info("Nach Re-Load nichts mehr zu tun. Kein Write.")
            return 0

        # ── Bulk-Fetch + Compute ─────────────────────────────────────────────
        bulk = bulk_fetch_ohlc(unique_tickers, fetch_start, fetch_end)
        n_filled, n_skipped = compute_and_apply_backfill(targets, bulk)
        log.info(
            "Backfill: %d/%d Records mit max_gain_pct gefüllt (%d skipped: "
            "no-data / delisted / len<2)",
            n_filled, len(targets), n_skipped,
        )

        if n_filled == 0:
            log.warning("Keine Records gefüllt — Skip Write.")
            return 0

        # ── Atomic Write ─────────────────────────────────────────────────────
        try:
            atomic_write_json(path, history)
        except Exception as exc:
            log.error("Atomic-Write fail: %s", exc)
            return 1
        log.info("Atomic Write erfolgreich: %s", path)
        return 0
    finally:
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        lock_fh.close()


if __name__ == "__main__":
    sys.exit(main())
