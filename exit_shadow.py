"""Exit-Shadow-Log — pures stdlib-Kernmodul (NUR Sammeln, kein Live-Effekt).

Sammelt pro Handelstag pro offener Position den ``exit_state`` (Composite-
Pressure + 6 Trigger-Sub-Scores) + den nachfolgenden Kursverlauf
(``forward_3d/5d/10d``) für eine spätere Exit-Signal-Edge-Auswertung
(Pendant zum Entry-Shadow #336). Append-only ``exit_shadow_log.jsonl``,
eigene Datei — KEIN Schema-Bump, KEIN S10/expected_keys, vom Digest NICHT
gelesen.

★ KONVENTION (kritisch — Vorzeichen NICHT verwechseln):
   ``forward_Nd = (close[signal+N] − close[signal]) / close[signal] × 100``
   **NEGATIVER forward_Nd = GUTES Exit-Signal** (Kurs FIEL nach der
   Verkaufs-Warnung). Positiver = Fehlsignal (Kurs stieg trotz Warnung —
   der 08.06.-Fall PDYN/IONQ). Eine Vorzeichen-Verwechslung kehrt die
   gesamte Auswertung um.

★ SAMPLE-CAVEAT (vor jeder späteren Auswertung beachten):
   Exit-Trigger rechnen NUR für offene Positionen (~8). Das Sample ist
   inhärent DÜNN + hoch autokorreliert (dieselbe Position täglich = keine
   unabhängigen Punkte). Bis ~Ende Juli ~150 Records, statistisch
   LOW-POWER. Das wird KEIN robuster AUC (wie Setup-Score n~1200), sondern
   ein qualitativer Erstblick („feuert ein Trigger chronisch falsch?").
   Überinterpretation eines dünnen Samples vermeiden (Wächter-Block-Lehre
   04.06.).

Reines Anhängen ohnehin berechneter Werte — NULL Touch an exit_state,
Push-Pipeline, Ratchet (peak_score/peak_pnl), Score oder Trading.
"""
from __future__ import annotations

import json
import logging
from datetime import time
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

EXIT_SHADOW_LOG = "exit_shadow_log.jsonl"
SCHEMA_V_EXIT_SHADOW = 1
_EASTERN = ZoneInfo("America/New_York")
_MKT_CLOSE = time(16, 0)

# Die 6 Phase-2-Exit-Trigger (Reihenfolge stabil; Quelle: _compute_exit_state).
_TRIGGER_NAMES = (
    "score_decay", "profit_lock", "overheated",
    "setup_erosion", "catalyst", "trend_break",
)
# Forward-Return-Horizonte (Handelstage nach dem Signal).
_FORWARD_HORIZONS = (3, 5, 10)


def should_log_exit_shadow(run_phase: str, now_et) -> bool:
    """Gate (pure): NUR settled-postclose loggen — ``run_phase=="postclose"``
    UND ``now_et >= 16:00 ET``. Sonst Skip (premarket/pre-close/off-schedule
    → nicht-finale Trigger-Preise verschmutzen das Sample).

    ``now_et`` ist ein tz-aware ET-Zeitpunkt. ``.time()`` auf tz-aware
    datetime liefert naive time → Vergleich gegen ``_MKT_CLOSE``.
    """
    if run_phase != "postclose":
        return False
    try:
        return now_et.time() >= _MKT_CLOSE
    except (AttributeError, TypeError):
        return False


def build_exit_shadow_record(ticker: str, report_date: str, run_phase: str,
                             exit_state: dict, signal_price) -> dict:
    """PURE: flacht ``exit_state`` zu einem Shadow-Record. Pro Trigger nur
    die 4 Kernfelder ``{score, warn, crit, available}`` (Detail-Felder wie
    ma21/drop_pct/reason werden NICHT geloggt). ``forward_*`` initial None
    (Backfill füllt später). ``available`` default True (der available-Pfad
    der Trigger trägt keinen expliziten Key; nur der unavailable-Pfad)."""
    trig_src = exit_state.get("triggers") or {}
    triggers = {}
    for name in _TRIGGER_NAMES:
        t = trig_src.get(name) or {}
        triggers[name] = {
            "score":     t.get("score", 0),
            "warn":      bool(t.get("warn", False)),
            "crit":      bool(t.get("crit", False)),
            "available": bool(t.get("available", True)),
        }
    rec = {
        "schema_v":        SCHEMA_V_EXIT_SHADOW,
        "date":            report_date,
        "ticker":          ticker,
        "run_phase":       run_phase,
        "computed_at":     exit_state.get("computed_at"),
        "exit_pressure":   exit_state.get("exit_pressure"),
        "current_pnl_pct": exit_state.get("current_pnl_pct"),
        "current_score":   exit_state.get("current_score"),
        "peak_pnl_pct":    exit_state.get("peak_pnl_pct_since_entry"),
        "peak_score":      exit_state.get("peak_score_since_entry"),
        "signal_price":    signal_price,
        "triggers":        triggers,
    }
    for n in _FORWARD_HORIZONS:
        rec[f"forward_{n}d"] = None
    return rec


def merge_exit_shadow(existing: list, new_records: list) -> list:
    """PURE Re-Write-by-(ticker, date): ersetzt für jedes (ticker, date) den
    bestehenden Record durch den neuen (letzter postclose-Run des Tages
    gewinnt) — KEIN Duplikat-Append. Defensiv: bereits gesetzte ``forward_*``
    des alten Records werden in den neuen übernommen (schützt gegen den
    Edge-Fall, dass ein Backfill lief und danach ein Same-Day-Re-Run den
    Record ersetzt — auf demselben Handelstag sind forward_* aber ohnehin
    noch None, da kein Horizont fällig).
    """
    new_keys = {(r.get("ticker"), r.get("date")) for r in new_records}
    old_by_key = {(e.get("ticker"), e.get("date")): e for e in (existing or [])}
    merged = [e for e in (existing or [])
              if (e.get("ticker"), e.get("date")) not in new_keys]
    for r in new_records:
        old = old_by_key.get((r.get("ticker"), r.get("date")))
        if old:
            for n in _FORWARD_HORIZONS:
                k = f"forward_{n}d"
                if old.get(k) is not None and r.get(k) is None:
                    r[k] = old[k]
        merged.append(r)
    return merged


def forward_fields_to_fill(record: dict, sig_idx: int, n_closes: int) -> dict:
    """PURE Backfill-Entscheidung für EINEN Record. Returnt {field: fwd_idx}
    für jeden Horizont, der (a) noch None ist UND (b) dessen Bar
    (``sig_idx + N``) im Fenster vorhanden ist (Horizont erreicht).

    ⚠ ABBRUCH-/Skalierungs-Garantie: ein Record mit gesetztem
    ``forward_10d`` ist FERTIG → leeres Dict (NIE wieder anfassen). Der
    Backfill iteriert so nur über UNVOLLSTÄNDIGE Records, nicht über die
    wachsende Historie. ``sig_idx < 0`` (Signal-Datum nicht im 90d-Fenster)
    → leeres Dict (bleibt dauerhaft None — kann nicht mehr gefüllt werden).
    """
    out: dict[str, int] = {}
    if sig_idx is None or sig_idx < 0:
        return out
    for n in _FORWARD_HORIZONS:
        field = f"forward_{n}d"
        if record.get(field) is not None:
            continue
        fwd_idx = sig_idx + n
        if 0 <= fwd_idx < n_closes:
            out[field] = fwd_idx
    return out


def is_record_complete(record: dict) -> bool:
    """Record fertig = letzter Horizont gefüllt → vom Backfill überspringen."""
    return record.get(f"forward_{_FORWARD_HORIZONS[-1]}d") is not None


def compute_forward_return(sig_close: float, fwd_close: float):
    """PURE: ``(fwd − sig)/sig × 100``. NEGATIV = Kurs fiel = gutes Exit-
    Signal. None bei ``sig_close <= 0``."""
    try:
        if sig_close is None or fwd_close is None or sig_close <= 0:
            return None
        return round((float(fwd_close) - float(sig_close)) / float(sig_close) * 100.0, 2)
    except (TypeError, ValueError):
        return None


def write_exit_shadow_records(new_records: list, path: str = EXIT_SHADOW_LOG) -> int:
    """I/O-Wrapper: lädt bestehende JSONL, merged Re-Write-by-(ticker,date),
    schreibt zurück. Fail-soft. Returnt Anzahl neuer Records (>0 = geschrieben).
    Eine Zeile pro Record (JSONL)."""
    if not new_records:
        return 0
    existing = _load_jsonl(path)
    merged = merge_exit_shadow(existing, new_records)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            for rec in merged:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("exit_shadow_log Schreibfehler — übersprungen: %s", exc)
        return 0
    return len(new_records)


def _load_jsonl(path: str) -> list:
    """Lädt JSONL → Liste. Silently [] bei fehlend; kaputte Zeilen
    überspringen (defensiv, kein Datenverlust der übrigen)."""
    out: list = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    return out
