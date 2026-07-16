#!/usr/bin/env python3
"""Einmal-Backfill: ``entry_past_return_5d`` auf v4-Alt-Records in
``backtest_history.json`` retroaktiv füllen (Paper C / Hypothese-A Stufe B).

════════════════════════════════════════════════════════════════════════════
ZWECK (EHRLICH — kein Overselling):
    EXPLORATIVER Beschleuniger für Paper C (Momentum: „trennt der Past-Return
    vor Entry die Forward-Returns?"). Die backgefüllten Alt-Records sind
    **retrospektiv / IN-SAMPLE** — sie de-risken die Momentum-Hypothese
    („ist die Beziehung überhaupt da?"), ERSETZEN aber NICHT den vorregistrierten
    Vorwärts-OoS-Test. Die ab 13.07. VORWÄRTS gesammelten Records bleiben die
    **konfirmatorische** Evidenz. Backgefüllte und vorwärts-gesammelte Records
    dürfen in der konfirmatorischen Auswertung **NICHT gepoolt** werden
    (In-Sample-Falle, SESSION_HANDOVER §8z1-Klasse). Der Backfill ist
    look-ahead-SICHER (nur Pre-Entry-Preise), aber sein Beweiswert ist
    exploratorisch, nicht konfirmatorisch.

MECHANIK (aus Diagnose 16.07.2026, Präzedenz backfill_max_gain_pct.py #401):
    Load → Filter → [KONSISTENZ-GATE] → Bulk-Fetch → Compute → Atomic-Write.

- Load: ``backtest_history.json`` read-only.
- Filter (SCOPE = v4-only): ``schema_v == 4`` UND
  ``e.get("entry_past_return_5d") is None`` (deckt **absent UND present-None** —
  die pre-fix-None-Records bekommen einen zweiten Versuch; **abweichend** von
  #401, das key-Abwesenheit prüfte, weil hier zwei Nicht-Wert-Zustände
  koexistieren). Non-null wird NIE überschrieben (Idempotenz). Die 1478 pre-v4-
  Records sind BEWUSST ausgeschlossen (andere Score-Ära pre-#346, anderes
  Selektions-Regime — nicht schema-konsistent zum v4-Kern).
- **KEIN Reifegrad-Filter** (der Past-Return ist ab Entry-Tag berechenbar —
  anders als max_gain, das ≥10 Handelstage NACH Entry braucht).
- **KONSISTENZ-GATE (HARTE VORBEDINGUNG vor jedem Live-Write):** rechnet die
  bereits-non-null Records (13.–15.07.) mit demselben Backfill-Pfad nach und
  urteilt auf der **Diff-VERTEILUNG** (nicht per starrem ±0.01 pro Record).
  Kalibriert nach der Messung 16.07. (31 exakt / 1 Ausreißer AMCX 0.05, median
  0.0 = Daten-Artefakt durch Yahoo-Revision frischer Referenz-Bars): PASS ⇔
  median-|diff| < 0.001 (Systematik-Wächter) UND ≤ 1 Ausreißer > 0.01 UND kein
  Ausreißer ≥ 0.5 pp UND ≥ 20 verifiziert. Fängt systematische Verschiebung,
  mehrere/große Ausreißer, zu-wenig-Daten weiter sicher; lässt ein einzelnes
  kleines Bar-Revisions-Artefakt durch. Details/Begründung in ``gate_passed``.
  ABORT → KEIN Write. Reiner Read (Idempotenz-Filter fasst non-null nicht an).
- Bulk-Fetch: EIN ``yf.download(unique_tickers, earliest−14d..latest+1d,
  threads=True, auto_adjust=True)``-Call. Fail-soft pro Ticker.
- Slice RÜCKWÄRTS: ``df_upto = df[df.index.date <= edate]``; bei ``len >= 6``:
  ``close_at_entry = iloc[-1]``, ``close_5td_before = iloc[-6]``. **BEIDE
  Adj-Close aus DERSELBEN Fetch — NIE das Record-``entry_price`` als Zähler**
  (Split-Epochen-Mismatch, ``_compute_entry_past_return_5d``-Docstring-Pflicht).
- Compute: ``_compute_entry_past_return_5d`` wird IMPORTIERT (nicht dupliziert —
  Drift-Schutz wie #401).
- **NUR ``e["entry_past_return_5d"]`` wird gesetzt.** Kein anderes Feld.
- Atomic Write: ``tmp + os.replace`` NUR am Ende.

RACE-SCHUTZ (Live, doppelt, 1:1 von #401):
    1. ``fcntl.flock`` (exclusive, non-blocking) für Read→Compute→Write.
    2. Cron-Fenster-Guard: ±30 min um 06:17/21:17 UTC (Backtest-schreibende
       Daily-Runs). ki_agent-hourly (xx:17) → nur flock.

RÜCKWEG (dokumentiert, kein „wir schauen dann"): der Live-Lauf setzt GENAU EIN
    Feld auf ~400 Records UND schreibt ein **MANIFEST**
    (``backfill_entry_past_return_5d_manifest.json``) mit den (ticker, date) der
    tatsächlich befüllten Records. Rückweg = **``--undo``-Flag**: setzt
    ``entry_past_return_5d`` **ausschließlich für die Manifest-Records** auf
    ``None`` zurück (kein Recompute-Vergleich!). WARUM Manifest statt Recompute
    (Guardian-Finding 16.07.): vorwärts gesammelte Live-Records entstehen über
    DIESELBE Formel/Preisquelle → ein Recompute-Match wäre für sie der Normalfall
    → ``--undo`` hätte die konfirmatorisch (seit 13.07.) gesammelten OoS-Records
    MIT-genullt. Das Manifest ist die einzige verlässliche Provenienz; ohne
    Manifest verweigert ``--undo`` (kein Raten). Beide Files werden co-committet.
    git-revert des Daten-Commits ist NICHT der Weg (würfe parallele ki_agent-/
    Daily-Run-Writes desselben Commits mit weg).

DRY-RUN (Default):
    ``python scripts/backfill_entry_past_return_5d.py``            → dry-run
    ``python scripts/backfill_entry_past_return_5d.py --fetch-in-dry-run``
        → dry-run MIT Fetch: zeigt Preview-Werte + KONSISTENZ-GATE + Alignment.
    ``python scripts/backfill_entry_past_return_5d.py --live``     → Live (Gate
        als harte Vorbedingung; Abort bei Gate-Fail).
    ``python scripts/backfill_entry_past_return_5d.py --undo``     → Rückweg.

Exit-Codes: 0 = ok · 1 = Fehler (Gate-Fail, flock-fail, yf-Ausfall, Cron-Block).
Idempotent: mehrfacher Lauf überspringt bereits gefüllte Records.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger("backfill_entry_past_return_5d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)

BACKTEST_FILE = ROOT / "backtest_history.json"
MANIFEST_FILE = ROOT / "backfill_entry_past_return_5d_manifest.json"

FIELD = "entry_past_return_5d"
N_BARS_NEEDED = 6                    # iloc[-1] (Entry) + iloc[-6] (5 TD davor).
BULK_FETCH_LOOKBACK_DAYS = 14        # 5 Trading-Days = 14 Kalender-Days Puffer.
CRON_BLOCK_WINDOW_MINUTES = 30       # ±30 Min um 06:17 und 21:17 UTC.
CRON_HEAVY_SLOTS = ((6, 17), (21, 17))
GATE_TOLERANCE = 0.01                # |recompute − stored| > 0.01 = „Ausreißer".
GATE_MIN_VERIFY = 20                 # min. verifizierte non-null Records für Pass.
# Verteilungs-Kalibrierung (Messung 16.07.: 31 exakt / 1 Ausreißer AMCX 0.05,
# median 0.0 → Daten-Artefakt, kein systematischer Fehler). Siehe gate_passed.
GATE_MEDIAN_MAX = 0.001              # median-|diff| darunter = kein MEHRHEITS-Drift.
GATE_MEAN_MAX = 0.003               # mean-|diff| der Inlier (≤ tol) darunter = kein
                                     # MINDERHEITS-Drift (Guardian-Finding 16.07.:
                                     # median fängt nur > 50 %; mean fängt auch
                                     # < 50 % uniforme Sub-0.01-Verschiebungen).
GATE_MAX_OUTLIERS = 1                # max. so viele Records > GATE_TOLERANCE.
GATE_OUTLIER_HARD_CAP = 0.5          # ein Ausreißer ≥ 0.5 pp = echter Bruch, nie ok.

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


def select_targets(history: list[dict]) -> list[tuple[int, dict, date]]:
    """Filtert v4-Alt-Records, die entry_past_return_5d-Backfill brauchen.

    Kriterien (ALLE):
      - ``backtest_schema_version == 4`` (Loader-Bindung, kein Bump; SCOPE
        v4-only — pre-v4 bewusst ausgeschlossen).
      - ``e.get("entry_past_return_5d") is None`` — **is-None** statt
        Key-Abwesenheit (#401): deckt absent (1898) UND present-None (50);
        die 50 pre-fix-None bekommen einen zweiten Versuch. Non-null → skip.
      - Entry-Datum parsebar.

    KEIN Reifegrad-Filter — der Past-Return ist ab Entry-Tag berechenbar.

    Returnt ``[(original_index, entry_dict_ref, entry_date), ...]`` in
    Original-Reihenfolge; ``entry_dict_ref`` ist die In-place-Referenz.
    """
    targets: list[tuple[int, dict, date]] = []
    for i, e in enumerate(history):
        if not isinstance(e, dict):
            continue
        if e.get("backtest_schema_version") != 4:
            continue
        if e.get(FIELD) is not None:      # is-None-Semantik (absent ODER None)
            continue
        edate = parse_entry_date(e.get("date", ""))
        if edate is None:
            continue
        targets.append((i, e, edate))
    return targets


def collect_nonnull_records(history: list[dict]) -> list[tuple[int, dict, date]]:
    """Records mit bereits gesetztem (non-null) entry_past_return_5d + parsebarem
    Datum — die Referenzmenge für das Konsistenz-Gate (13.–15.07.)."""
    out: list[tuple[int, dict, date]] = []
    for i, e in enumerate(history):
        if not isinstance(e, dict):
            continue
        if e.get(FIELD) is None:
            continue
        edate = parse_entry_date(e.get("date", ""))
        if edate is None:
            continue
        out.append((i, e, edate))
    return out


def apply_backfill_result(entry: dict, val: float | None) -> bool:
    """Setzt ``entry[FIELD] = val`` — GENAU EIN FELD, sonst nichts.

    Returnt ``True`` wenn geschrieben, ``False`` wenn ``val is None`` (IPO < 6
    Bars / Delisting / Fetch-Miss → kein Write, Feld bleibt None/absent).
    Post-Condition (getestet): genau ein Key neu (``entry_past_return_5d``),
    alle anderen byte-identisch.
    """
    if val is None:
        return False
    entry[FIELD] = val
    return True


# Klassifikation am Compute-Ausgang (analog #401-classify_outcome, aber an die
# strikte None-Semantik von entry_past_return_5d angepasst — KEIN 0.0-Overload).
OUTCOME_FILLED = "filled"        # Wert berechnet (nicht None) → geschrieben.
OUTCOME_NO_DATA = "no_data"      # kein Bulk-Slot / leerer df → skip.
OUTCOME_FEW_BARS = "few_bars"    # df da, aber < 6 Bars vor Entry (IPO-Kante) → None.


def classify_outcome(df_len: int, val: float | None) -> str:
    """Pure Klassifikation (kein Side-Effect). ``df_len`` = Bars in df_upto."""
    if val is not None:
        return OUTCOME_FILLED
    if df_len < N_BARS_NEEDED:
        return OUTCOME_FEW_BARS
    return OUTCOME_NO_DATA


def in_cron_block_window(
    now_utc: datetime | None = None,
    *,
    window_min: int = CRON_BLOCK_WINDOW_MINUTES,
    slots: tuple[tuple[int, int], ...] = CRON_HEAVY_SLOTS,
) -> tuple[bool, str]:
    """``(blocked, reason)`` — True innerhalb ±window_min um einen Cron-Heavy-
    Slot (06:17/21:17 UTC). Zyklische Distanz über Mitternacht. Injizierbar."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    now_min = now_utc.hour * 60 + now_utc.minute
    for h, m in slots:
        slot_min = h * 60 + m
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
    """Atomic Write via ``tmp + os.replace`` (POSIX-atomar), Format identisch
    zum Live-Pfad (``ensure_ascii=False, indent=2``)."""
    tmp = path.with_suffix(path.suffix + ".eprbackfill.tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(tmp, path)


# ─────────────────────────────────────────────────────────────────────────────
# yfinance-abhängige Sektion — kein Import in Slot A des Tests.
# ─────────────────────────────────────────────────────────────────────────────


def bulk_fetch_ohlc(tickers: list[str], start: date, end: date) -> dict[str, Any]:
    """EIN yf.download-Call für alle unique Tickers, auto_adjust=True. Fail-soft
    pro Ticker → ``{ticker: DataFrame | None}`` (None = Fehler/delisted/leer)."""
    import yfinance as yf  # noqa: F401  (pandas indirekt)

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


def build_df_upto(df: Any, edate: date) -> Any:
    """RÜCKWÄRTS-Slice: alle Bars mit ``index.date <= edate`` (inkl. Entry-Tag).
    Spiegel zum FORWARD-Slice in #401 (dort ``>= edate``)."""
    return df[df.index.date <= edate]


def extract_entry_closes(df_upto: Any) -> tuple[float | None, float | None, date | None]:
    """(close_at_entry, close_5td_before, last_bar_date) aus dem RÜCKWÄRTS-Slice.

    **BEIDE Closes sind Adj-Close aus DERSELBEN auto_adjust-Fetch** — NIE das
    Record-``entry_price`` (Split-Epochen-Mismatch, Docstring-Pflicht).
    ``close_5td_before`` ist None bei < 6 Bars (IPO-Kante). ``last_bar_date``
    dient dem Alignment-Check (== edate erwartet, da Entry = Postclose-Handelstag).
    """
    if df_upto is None or len(df_upto) < 1:
        return None, None, None
    last_bar_date = df_upto.index[-1].date()
    close_at_entry = float(df_upto["Close"].iloc[-1])
    close_5td_before = (
        float(df_upto["Close"].iloc[-N_BARS_NEEDED])
        if len(df_upto) >= N_BARS_NEEDED else None
    )
    return close_at_entry, close_5td_before, last_bar_date


def compute_and_apply_backfill(
    targets: list[tuple[int, dict, date]],
    bulk: dict[str, Any],
) -> tuple[int, int, int, int, list[dict]]:
    """Iteriert Targets, holt Rückwärts-Slice, ruft den IMPORTIERTEN
    ``_compute_entry_past_return_5d``, wendet an.

    Returnt ``(n_filled, n_skipped, n_few_bars, n_misaligned, filled_keys)``:
      - n_filled     = Records mit entry_past_return_5d gesetzt.
      - n_skipped    = kein Bulk-Slot / leerer df / val None (IPO/Delisting).
      - n_few_bars   = Untermenge skipped: df da, aber < 6 Bars vor Entry.
      - n_misaligned = df da, aber letzter Bar-Tag ≠ edate (Entry-Tag ohne Bar;
        diagnostisch — Live-Pfad ankert dort identisch, kein Divergenz-Risiko).
      - filled_keys  = ``[{"ticker", "date"}, ...]`` der TATSÄCHLICH befüllten
        Records — das Manifest für den chirurgischen ``--undo``. NUR diese
        Identitäten dürfen zurückgesetzt werden; ein Wert-Recompute-Vergleich
        wäre FALSCH (vorwärts gesammelte Live-Records matchen dieselbe Formel
        und würden mit-genullt → Guardian-Finding 16.07.).
    """
    from backtest_history import _compute_entry_past_return_5d

    n_filled = n_skipped = n_few_bars = n_misaligned = 0
    filled_keys: list[dict] = []
    for i, entry, edate in targets:
        tkr = entry.get("ticker")
        df = bulk.get(tkr) if tkr else None
        if df is None or df.empty:
            n_skipped += 1
            continue
        try:
            df_upto = build_df_upto(df, edate)
        except Exception as exc:
            n_skipped += 1
            log.warning("skip idx=%d ticker=%s: slice fail %s", i, tkr, exc)
            continue
        cae, c5, last_bar = extract_entry_closes(df_upto)
        if last_bar is not None and last_bar != edate:
            n_misaligned += 1
        val = _compute_entry_past_return_5d(cae, c5)
        if apply_backfill_result(entry, val):
            n_filled += 1
            filled_keys.append({"ticker": tkr, "date": entry.get("date")})
        else:
            n_skipped += 1
            if len(df_upto) < N_BARS_NEEDED:
                n_few_bars += 1
    return n_filled, n_skipped, n_few_bars, n_misaligned, filled_keys


def gate_passed(rows: list[dict]) -> tuple[bool, str]:
    """KONSISTENZ-GATE-URTEIL auf der Diff-VERTEILUNG aller Referenz-Records
    (``rows`` = Ausgabe von ``gate_diff_distribution``). Read-only.

    KALIBRIERUNG (Messung 16.07., BELEG statt Bequemlichkeit): der `dry-run-
    fetch` ergab n=32, **exakt(<0.001)=31, ein Ausreißer AMCX 0.05, median 0.0**.
    Die Referenz-Records sind die JÜNGSTEN Bars (13.–15.07.) — Yahoo revidiert
    frische Bars nachträglich (AMCX 08.07.-Nenner minimal revidiert → 5.11→5.16),
    während die Backfill-TARGETS ältere, SETTLED Bars (14.05.–10.07.) sind. Ein
    starres ±0.01 würde solche legitimen Einzel-Revisions-Artefakte als Fehler
    werten. Deshalb kalibriert — aber KEIN Gummi-Gate:

    PASS ⇔ ALLE fünf:
      (1) ≥ ``GATE_MIN_VERIFY`` (20) Records recompute-verifiziert (sonst
          inkonklusiv — „kann nicht bestätigen → nicht schreiben").
      (2) **median-|diff| < ``GATE_MEDIAN_MAX`` (0.001)** — MEHRHEITS-Wächter:
          eine Verschiebung, die > 50 % der Records betrifft, hebt den median →
          FAIL, selbst wenn jeder Einzel-Diff < 0.01 läge („AMCX ist nur die
          Spitze"-Fall).
      (3) **mean-|diff| der INLIER (Diffs ≤ tol) < ``GATE_MEAN_MAX`` (0.003)** —
          MINDERHEITS-Wächter (Guardian-Finding 16.07.): der median ist blind für
          eine uniforme Sub-0.01-Verschiebung, die < 50 % der Records betrifft
          (median bleibt dann im Null-Block). Der Mittelwert der Inlier fängt
          genau das — ohne vom einen erlaubten Ausreißer verzerrt zu werden (der
          ist per Definition kein Inlier).
      (4) ≤ ``GATE_MAX_OUTLIERS`` (1) Records mit |diff| > ``GATE_TOLERANCE``
          (0.01) — ein einzelnes Bar-Revisions-Artefakt ok, zwei+ nicht.
      (5) KEIN Ausreißer ≥ ``GATE_OUTLIER_HARD_CAP`` (0.5 pp) — großer Sprung =
          echter Bruch (Split/Verwechslung/Fehlberechnung), blockt IMMER.

    Was das Gate fängt: MEHRHEITS-Drift (median), MINDERHEITS-Drift kleiner
    Magnitude (mean-Inlier), mehrere Ausreißer, ein großer Ausreißer, zu wenige
    verifizierte Records. Was es bewusst DURCHLÄSST: EIN einzelnes (<0.5 pp)
    Revisions-Artefakt bei ansonsten flacher (median~0, mean-Inlier~0) Verteilung.
    Ehrliche Restlücke: ein winziger uniformer Drift (deutlich < 0.003 mean) über
    eine kleine Minderheit bleibt untersichtbar — Magnitude aber vernachlässigbar
    und für dieses explorative S10_OBSERVED-Feld akzeptiert.
    """
    diffs = sorted(r["diff"] for r in rows if r.get("diff") is not None)
    n_ver = len(diffs)
    n_none = sum(1 for r in rows if r.get("diff") is None)
    if n_ver < GATE_MIN_VERIFY:
        return False, (f"nur {n_ver} Records verifiziert (< {GATE_MIN_VERIFY} "
                       f"Floor; {n_none} ohne Recompute) — inkonklusiv, kein Write.")
    median = diffs[n_ver // 2]
    outliers = [d for d in diffs if d > GATE_TOLERANCE]
    inliers = [d for d in diffs if d <= GATE_TOLERANCE]
    mean_inlier = round(sum(inliers) / len(inliers), 6) if inliers else 0.0
    if median >= GATE_MEDIAN_MAX:
        return False, (f"median-|diff|={median} ≥ {GATE_MEDIAN_MAX} → MEHRHEITS-"
                       f"Verschiebung (kein Einzel-Artefakt) → STOPP.")
    if mean_inlier >= GATE_MEAN_MAX:
        return False, (f"mean-|diff|(Inlier)={mean_inlier} ≥ {GATE_MEAN_MAX} → "
                       f"MINDERHEITS-Verschiebung (uniformer Sub-tol-Drift) → STOPP.")
    if len(outliers) > GATE_MAX_OUTLIERS:
        return False, (f"{len(outliers)} Ausreißer > {GATE_TOLERANCE} "
                       f"(max {GATE_MAX_OUTLIERS} erlaubt) → nicht Einzel-Artefakt.")
    big = [d for d in outliers if d >= GATE_OUTLIER_HARD_CAP]
    if big:
        return False, (f"Ausreißer {max(big)} ≥ {GATE_OUTLIER_HARD_CAP} pp → "
                       f"echter Bruch (Split/Verwechslung), kein Revisions-Rauschen.")
    return True, (f"{n_ver} verifiziert · median={median} · mean-Inlier={mean_inlier} "
                  f"· {len(outliers)} Einzel-Artefakt(e) ≤ {GATE_OUTLIER_HARD_CAP} pp "
                  f"→ Daten-Artefakt (frische Bar-Revision), kein systematischer Fehler.")


def gate_diff_distribution(
    history: list[dict], bulk: dict[str, Any],
) -> list[dict]:
    """DIAGNOSE (NUR Logging, KEINE Gate-Logik/Toleranz-Berührung): volle
    Diff-Verteilung ALLER Referenz-Records — pro Record ``ticker/date/stored/
    recomputed/diff`` PLUS beide Bar-Details (Zähler ``iloc[-1]`` + Nenner
    ``iloc[-6]`` je Datum+Adj-Close), damit „Einzelfall/Daten-Artefakt vs.
    systematische Verschiebung" MESSBAR wird (statt nur Mismatches zu sehen) und
    die Daten-Revisions-Hypothese am konkreten Bar prüfbar ist. Ändert NICHTS am
    Gate-Urteil — wird ausschließlich im dry-run-fetch-Pfad aufgerufen.
    """
    from backtest_history import _compute_entry_past_return_5d
    rows: list[dict] = []
    for _i, e, edate in collect_nonnull_records(history):
        tkr = e.get("ticker")
        stored = e.get(FIELD)
        row = {"ticker": tkr, "date": e.get("date"), "stored": stored,
               "recomputed": None, "diff": None,
               "num_date": None, "num_close": None,
               "den_date": None, "den_close": None}
        df = bulk.get(tkr) if tkr else None
        if df is not None and not df.empty:
            up = build_df_upto(df, edate)
            cae, c5, last_bar = extract_entry_closes(up)
            rec = _compute_entry_past_return_5d(cae, c5)
            row["recomputed"] = rec
            row["diff"] = None if (rec is None or stored is None) \
                else round(abs(rec - stored), 4)
            if last_bar is not None:
                row["num_date"] = last_bar.isoformat()
            if cae is not None:
                row["num_close"] = round(cae, 4)
            if len(up) >= N_BARS_NEEDED:
                row["den_date"] = up.index[-N_BARS_NEEDED].date().isoformat()
            if c5 is not None:
                row["den_close"] = round(c5, 4)
        rows.append(row)
    return rows


def summarize_diffs(rows: list[dict]) -> dict:
    """Pure Verteilungs-Summary über die ``diff``-Werte (None ausgeschlossen):
    Buckets exakt (< 0.001) / klein (0.001..GATE_TOLERANCE) / über-Toleranz, plus
    min/median/max und Anzahl ohne Recompute. Deterministisch, kein I/O."""
    diffs = sorted(r["diff"] for r in rows if r.get("diff") is not None)
    n = len(diffs)
    no_rec = sum(1 for r in rows if r.get("diff") is None)
    if n == 0:
        return {"n": 0, "exact": 0, "small": 0, "over_tol": 0,
                "min": None, "median": None, "max": None, "no_recompute": no_rec}
    return {
        "n": n,
        "exact": sum(1 for d in diffs if d < 0.001),
        "small": sum(1 for d in diffs if 0.001 <= d <= GATE_TOLERANCE),
        "over_tol": sum(1 for d in diffs if d > GATE_TOLERANCE),
        "min": diffs[0], "median": diffs[n // 2], "max": diffs[-1],
        "no_recompute": no_rec,
    }


def preview_targets(
    targets: list[tuple[int, dict, date]],
    bulk: dict[str, Any] | None,
    n: int = 5,
) -> list[dict]:
    """Dry-Run-Preview: berechnet FIELD für die ersten ``n`` Targets (falls Bulk
    da) — schreibt NICHTS."""
    if bulk is None:
        return [
            {"idx": i, "ticker": e.get("ticker"), "date": e.get("date"),
             "entry_date": edate.isoformat(), "val": "(Fetch übersprungen)"}
            for i, e, edate in targets[:n]
        ]

    from backtest_history import _compute_entry_past_return_5d

    preview: list[dict] = []
    for i, e, edate in targets[:n]:
        tkr = e.get("ticker")
        df = bulk.get(tkr) if tkr else None
        if df is None or df.empty:
            val: Any = None
            outcome = OUTCOME_NO_DATA
        else:
            try:
                df_upto = build_df_upto(df, edate)
                cae, c5, _ = extract_entry_closes(df_upto)
                val = _compute_entry_past_return_5d(cae, c5)
                outcome = classify_outcome(len(df_upto), val)
            except Exception as exc:
                val = f"(err: {exc})"
                outcome = OUTCOME_NO_DATA
        preview.append({"idx": i, "ticker": tkr, "date": e.get("date"),
                        "entry_date": edate.isoformat(), "val": val,
                        "outcome": outcome})
    return preview


def _union_fetch_window(
    targets: list[tuple[int, dict, date]],
    gate_recs: list[tuple[int, dict, date]],
) -> tuple[list[str], date, date]:
    """Unique Tickers + Fetch-Fenster über Targets ∪ Gate-Records (eine Fetch
    deckt Fill + Gate mit derselben Adjust-Epoche)."""
    tickers = sorted({e.get("ticker") for _, e, _ in (targets + gate_recs)
                      if e.get("ticker")})
    all_dates = [ed for _, _, ed in (targets + gate_recs)]
    start = min(all_dates) - timedelta(days=BULK_FETCH_LOOKBACK_DAYS)
    end = max(all_dates)
    return tickers, start, end


# ─────────────────────────────────────────────────────────────────────────────
# CLI / Main.
# ─────────────────────────────────────────────────────────────────────────────


def _do_undo(history: list[dict], manifest: list[dict]) -> int:
    """--undo: setzt entry_past_return_5d **ausschließlich** bei den Records
    zurück, die der ``--live``-Lauf laut MANIFEST tatsächlich befüllt hat
    (Match über ``ticker`` + ``date``).

    KRITISCH (Guardian-Finding 16.07.): ein Wert-Recompute-Vergleich wäre FALSCH
    — vorwärts gesammelte Live-Records entstehen über DIESELBE Formel/Preisquelle
    und würden den Recompute ebenso matchen → ``--undo`` hätte die konfirmatorisch
    (seit 13.07.) gesammelten OoS-Records mit-genullt. Das Manifest ist die
    einzige verlässliche Provenienz-Quelle; ohne Manifest wird NICHT geraten.

    Reine Dict-Operation (kein yfinance/Recompute) → voll unit-testbar. Returnt
    Anzahl zurückgesetzt.
    """
    keys = {(m.get("ticker"), m.get("date")) for m in manifest if isinstance(m, dict)}
    if not keys:
        return 0
    n = 0
    for e in history:
        if not isinstance(e, dict):
            continue
        if (e.get("ticker"), e.get("date")) in keys and e.get(FIELD) is not None:
            e[FIELD] = None
            n += 1
    return n


def load_manifest(path: pathlib.Path) -> list[dict]:
    """Backfill-Manifest (Liste ``{ticker, date}``). Fehlende Datei → []."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as exc:
        log.warning("Manifest-Load fail (%s) → leer.", exc)
        return []


def merge_manifest(existing: list[dict], new_keys: list[dict]) -> list[dict]:
    """Union der Manifest-Einträge über (ticker, date) — akkumuliert über
    mehrere ``--live``-Läufe, dedupliziert. Pure."""
    seen = {(m.get("ticker"), m.get("date")) for m in existing if isinstance(m, dict)}
    out = list(existing)
    for k in new_keys:
        key = (k.get("ticker"), k.get("date"))
        if key not in seen:
            seen.add(key)
            out.append({"ticker": k.get("ticker"), "date": k.get("date")})
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--live", action="store_true",
                   help="Live-Lauf: schreibt nach backtest_history.json "
                        "(Gate als harte Vorbedingung). Ohne Flag = Dry-Run.")
    p.add_argument("--undo", action="store_true",
                   help="Rückweg: gefüllte Werte auf None zurücksetzen "
                        "(chirurgisch, nur Backfill-erzeugte Werte).")
    p.add_argument("--path", default=str(BACKTEST_FILE),
                   help=f"Pfad zu backtest_history.json (default: {BACKTEST_FILE})")
    p.add_argument("--fetch-in-dry-run", action="store_true",
                   help="Dry-Run MIT Fetch: Preview-Werte + Konsistenz-Gate + "
                        "Alignment (default: nur Metadaten).")
    args = p.parse_args(argv)

    path = pathlib.Path(args.path).resolve()
    if not path.exists():
        log.error("File not found: %s", path)
        return 1

    mode = "UNDO" if args.undo else ("LIVE" if args.live else "DRY-RUN")
    log.info("Modus: %s | Ziel-Datei: %s", mode, path)

    if (args.live or args.undo):
        blocked, reason = in_cron_block_window()
        if blocked:
            log.error("%s-Lauf verweigert: %s", mode, reason)
            log.error("Warten bis außerhalb ±30min um 06:17 / 21:17 UTC.")
            return 1

    try:
        history = load_history(path)
    except Exception as exc:
        log.error("Load fail: %s", exc)
        return 1
    log.info("Loaded %d records from %s", len(history), path.name)

    targets = select_targets(history)
    gate_recs = collect_nonnull_records(history)
    log.info("Targets (v4 UND %s is None): %d | Gate-Referenz (non-null): %d",
             FIELD, len(targets), len(gate_recs))

    if not args.undo and not targets:
        log.info("Nichts zu tun — alle v4-Records tragen bereits %s.", FIELD)
        return 0

    tickers, fetch_start, fetch_end = _union_fetch_window(targets, gate_recs)
    log.info("Bulk-Fetch-Fenster: %s .. %s | %d unique Tickers",
             fetch_start, fetch_end, len(tickers))

    # ── DRY-RUN ─────────────────────────────────────────────────────────────
    if not args.live and not args.undo:
        bulk = None
        if args.fetch_in_dry_run:
            log.info("--fetch-in-dry-run: Preview + Gate + Alignment mit echtem Fetch.")
            bulk = bulk_fetch_ohlc(tickers, fetch_start, fetch_end)
        preview = preview_targets(targets, bulk, n=5)
        log.info("─" * 60)
        log.info("DRY-RUN Preview (erste 5 Targets):")
        for row in preview:
            log.info("  idx=%d ticker=%s date=%s edate=%s → %s=%s (%s)",
                     row["idx"], row["ticker"], row["date"], row["entry_date"],
                     FIELD, row["val"], row.get("outcome", ""))
        if bulk is not None:
            # EINE Recompute-Quelle (rows) für Verdikt + Ausreißer-Log + Verteilung.
            rows = gate_diff_distribution(history, bulk)
            ok, msg = gate_passed(rows)
            log.info("─" * 60)
            log.info("KONSISTENZ-GATE: %s — %s", "PASS" if ok else "FAIL", msg)
            for m in sorted((r for r in rows
                             if r["diff"] is None or r["diff"] > GATE_TOLERANCE),
                            key=lambda x: (x["diff"] is None, -(x["diff"] or 0.0)))[:10]:
                log.warning("  Ausreißer/None: %s %s stored=%s recomputed=%s |diff|=%s",
                            m["ticker"], m["date"], m["stored"],
                            m["recomputed"], m["diff"])
            # Alignment über ALLE Targets (nicht nur Preview).
            n_mis = sum(
                1 for _, e, ed in targets
                if (df := bulk.get(e.get("ticker"))) is not None and not df.empty
                and (lb := extract_entry_closes(build_df_upto(df, ed))[2]) is not None
                and lb != ed
            )
            log.info("Alignment: %d/%d Targets mit Entry-Tag OHNE Bar "
                     "(letzter Bar ≠ edate; Live-Pfad ankert dort identisch → "
                     "kein Divergenz-Risiko, nur Diagnose).", n_mis, len(targets))
            # ── DIAGNOSE: volle Gate-Diff-Verteilung (NUR Logging) — dieselbe
            #    `rows`-Quelle wie das Verdikt oben (kein zweiter Recompute).
            summ = summarize_diffs(rows)
            log.info("─" * 60)
            log.info("GATE-DIFF-VERTEILUNG (alle %d Referenz-Records · Diagnose · "
                     "|diff| absteigend):", len(rows))
            for r in sorted(rows, key=lambda x: (x["diff"] is None,
                                                 -(x["diff"] or 0.0))):
                log.info("  %-7s %-12s stored=%-8s recomp=%-8s |diff|=%-7s "
                         "[Zähler %s=%s / Nenner %s=%s]",
                         r["ticker"], r["date"], r["stored"], r["recomputed"],
                         r["diff"], r["num_date"], r["num_close"],
                         r["den_date"], r["den_close"])
            log.info("SUMMARY: n=%d · exakt(<0.001)=%d · 0.001–%.2f=%d · >%.2f=%d "
                     "· min=%s median=%s max=%s · ohne-recompute=%d",
                     summ["n"], summ["exact"], GATE_TOLERANCE, summ["small"],
                     GATE_TOLERANCE, summ["over_tol"], summ["min"],
                     summ["median"], summ["max"], summ["no_recompute"])
            log.info("DEUTUNG: exakt≈n + nur Einzel-Ausreißer >tol → Daten-"
                     "Artefakt (Bar-Revision) · viele knapp unter tol → "
                     "systematische Verschiebung (dann STOPP + fixen).")
        log.info("─" * 60)
        log.info("DRY-RUN: %d Targets, %d unique Tickers, Fenster %s..%s. "
                 "KEINE Schreibvorgänge.", len(targets), len(tickers),
                 fetch_start, fetch_end)
        if not args.fetch_in_dry_run:
            log.info("Für Gate-Ergebnis: --fetch-in-dry-run. Für Live: --live "
                     "(nur außerhalb ±30min um 06:17/21:17 UTC).")
        return 0

    # ── LIVE / UNDO (flock) ─────────────────────────────────────────────────
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
            log.error("flock failed (paralleler Writer aktiv?): %s. Abgebrochen.", exc)
            return 1
        log.info("flock erworben (exklusiv, non-blocking).")

        try:
            history = load_history(path)
        except Exception as exc:
            log.error("Re-Load unter flock fail: %s", exc)
            return 1

        # ── UNDO (KEIN Fetch nötig — Manifest-basiert, kein Recompute) ───────
        if args.undo:
            manifest = load_manifest(MANIFEST_FILE)
            if not manifest:
                log.error("Kein Manifest (%s) — nichts sicher rückgängig zu "
                          "machen. Ein Recompute-basierter Undo würde auch "
                          "vorwärts gesammelte OoS-Records treffen (Guardian-"
                          "Finding). Kein Write.", MANIFEST_FILE.name)
                return 1
            n_undone = _do_undo(history, manifest)
            log.info("UNDO: %d Manifest-Records auf None zurückgesetzt.", n_undone)
            if n_undone == 0:
                log.info("Manifest-Records tragen bereits None. Kein Write.")
                return 0
            try:
                atomic_write_json(path, history)
                atomic_write_json(MANIFEST_FILE, [])   # Manifest leeren
            except Exception as exc:
                log.error("Atomic-Write fail: %s", exc)
                return 1
            log.info("Atomic Write (UNDO) erfolgreich: %s + Manifest geleert.", path)
            return 0

        # Fetch (union) unter flock — Gate + Fill aus derselben Epoche.
        bulk = bulk_fetch_ohlc(tickers, fetch_start, fetch_end)

        # ── KONSISTENZ-GATE (HARTE VORBEDINGUNG) ─────────────────────────────
        rows = gate_diff_distribution(history, bulk)
        ok, msg = gate_passed(rows)
        log.info("KONSISTENZ-GATE: %s — %s", "PASS" if ok else "FAIL", msg)
        if not ok:
            for m in sorted((r for r in rows
                             if r["diff"] is None or r["diff"] > GATE_TOLERANCE),
                            key=lambda x: (x["diff"] is None, -(x["diff"] or 0.0)))[:20]:
                log.error("  Ausreißer/None: %s %s stored=%s recomputed=%s |diff|=%s",
                          m["ticker"], m["date"], m["stored"],
                          m["recomputed"], m["diff"])
            log.error("GATE FAILED → KEIN Write. Ursache prüfen (Verteilung: "
                      "median-Drift = systematisch, mehrere/große Ausreißer = "
                      "Bruch), erst bei Gate-PASS erneut --live.")
            return 1

        # ── Fill ─────────────────────────────────────────────────────────────
        targets = select_targets(history)
        n_filled, n_skipped, n_few, n_mis, filled_keys = \
            compute_and_apply_backfill(targets, bulk)
        log.info("Backfill: %d/%d Records mit %s gefüllt (%d skipped: "
                 "no-data/delisted/IPO<6bars; davon %d few-bars). "
                 "Alignment: %d Entry-Tage ohne Bar.",
                 n_filled, len(targets), FIELD, n_skipped, n_few, n_mis)
        if n_filled == 0:
            log.warning("Keine Records gefüllt — Skip Write.")
            return 0
        # Manifest (Provenienz für --undo): akkumulierte Union der befüllten
        # (ticker, date) — die EINZIGE verlässliche Rückweg-Quelle.
        manifest = merge_manifest(load_manifest(MANIFEST_FILE), filled_keys)
        try:
            atomic_write_json(path, history)
            atomic_write_json(MANIFEST_FILE, manifest)
        except Exception as exc:
            log.error("Atomic-Write fail: %s", exc)
            return 1
        log.info("Atomic Write erfolgreich: %s (+ Manifest %d Einträge).",
                 path, len(manifest))
        return 0
    finally:
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        lock_fh.close()


if __name__ == "__main__":
    sys.exit(main())
