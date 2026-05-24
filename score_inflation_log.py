"""Single-Source-of-Truth für Score-Inflation-Persistenz.

Hintergrund: Bestandsaufnahme Mai 2026 hat gezeigt, dass Setup-Scores
über den US-Handelstag systematisch steigen (DFDV +17 / INDI +12 Punkte
zwischen US-Open und Pre-Close). Hauptverdacht: ``rel_volume`` wächst
monoton durch den Tag (Today-Volume / 20d-Avg); sekundär ``change_2d/3d``-
getriebene Bonus-Schwellen.

Damit nach 3-5 Trading-Tagen messbar ist, welcher Sub-Score wie viel
Intraday-Delta trägt, schreibt der Daily-Run pro Top-10-Ticker eine
Append-Only-Zeile in ``score_inflation_log.jsonl`` (JSON Lines).

Modul-Speicherort: Repo-Root (analog ``push_history.py``), weil zur
Laufzeit vom Daily-Run eingebunden — kein Tool-Skript.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

LOG_FILE = "score_inflation_log.jsonl"
CUTOFF_DAYS = 30   # Einträge älter als 30 Tage werden geprunt
_EASTERN = ZoneInfo("America/New_York")

# Schema-Version-Marker (PR-β, 16.05.2026).
# v1: ursprüngliches Format (12.05.–16.05.2026, kein schema_v-Marker).
# v2: ergänzt drivers_raw.rel_volume_normalized (hypothetischer Wert mit
#     RVOL_NORMALIZATION_ENABLED=True, ohne globalen Flag zu setzen).
# Reader (z. B. Diagnose-Skripte) sollen `entry.get("schema_v", 1)` lesen,
# damit Bestands-Einträge ohne Marker als v1 erkannt werden.
SCHEMA_V = 2


def _session_phase(dt_utc: datetime) -> str:
    """Mappe UTC-Timestamp auf US-Handels-Phase.

    Verwendet US-Eastern-Time (DST-aware), nicht eine fixe UTC-Schwelle —
    während EST (Winter) verschieben sich alle UTC-Schwellen um eine
    Stunde später; der User-Spec (vor 13:30 UTC = premarket) ist die
    EDT-Projektion (Sommer).

    Phasen (in Eastern-Time):
      - premarket: vor 09:30 ET
      - open:      09:30-11:00 ET   (erste 1,5 h nach Open)
      - midday:    11:00-15:00 ET
      - preclose:  15:00-16:00 ET   (letzte Stunde)
      - postclose: nach 16:00 ET
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    et = dt_utc.astimezone(_EASTERN)
    minutes = et.hour * 60 + et.minute
    if minutes < 9 * 60 + 30:
        return "premarket"
    if minutes < 11 * 60:
        return "open"
    if minutes < 15 * 60:
        return "midday"
    if minutes < 16 * 60:
        return "preclose"
    return "postclose"


def _safe_float(v: Any, default: float | None = None) -> float | None:
    """``float(v)`` oder default — None bei nicht-konvertierbarem Input."""
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _normalize_si_trend(raw: str | None) -> str:
    """Mappe ``finra_data.trend`` (up/down/sideways/no_data) auf das
    User-Schema (up/down/flat)."""
    if raw in ("up", "down"):
        return raw
    if raw == "sideways":
        return "flat"
    return "flat"   # no_data → flat (konservativ, kein eigener Status)


def _finra_combo_active(stock: dict) -> bool:
    """Replikat der Kombinations-Bonus-Logik aus ``score()``.

    Bonus feuert bei n_combo >= 3 von {SF>=30, DTC>=5, RVOL>=2, SI-Trend=up}.
    Dieser Helper persistiert das BOOL-Flag, nicht den Punktwert (der
    steht zusätzlich in ``score_struct/catalyst/timing``-Aggregaten).
    """
    finra = stock.get("finra_data") or {}
    sf = _safe_float(stock.get("short_float", 0)) or 0.0
    sr = _safe_float(stock.get("short_ratio", 0)) or 0.0
    rv = _safe_float(stock.get("rel_volume", 0)) or 0.0
    n_combo = sum([
        sf >= 30,
        sr >= 5,
        rv >= 2.0,
        finra.get("trend") == "up",
    ])
    return n_combo >= 3


def _build_entry(stock: dict, run_ts: datetime,
                 sub_scores: dict | None,
                 run_phase: str | None = None,
                 normalize_rvol_fn=None) -> dict:
    """Komponiere eine JSONL-Zeile aus dem Stock-Dict.

    ``sub_scores`` ist das Ergebnis von ``_compute_sub_scores(stock)`` —
    wird vom Caller übergeben, damit dieses Modul keinen Zirkel-Import
    auf ``generate_report`` braucht.

    ``run_phase`` ist die Workflow-Phase (``premarket``/``postclose``,
    siehe Zwei-Run-Architektur 12.05.2026). Ergänzt das vorhandene
    ``trading_session_phase``, das aus dem Wall-Clock-ET-Zeitpunkt
    abgeleitet wird — die beiden Felder messen unterschiedliche
    Dinge: ``run_phase`` ist die intentional gewählte Phase des
    Workflows, ``trading_session_phase`` ist der tatsächliche ET-
    Slot zur Ausführungszeit. Inflations-Analyse vergleicht primär
    nach ``run_phase``, ``trading_session_phase`` bleibt für Detail-
    Audit erhalten.

    ``normalize_rvol_fn`` (PR-β, Schema v2): wenn übergeben, wird der
    hypothetische normalisierte RVOL-Wert berechnet und in
    ``drivers_raw.rel_volume_normalized`` persistiert. Empirik-Daten-
    sammlung für PR-γ-Aktivierungs-Entscheidung — der Live-Wert
    ``rel_volume`` bleibt unverändert (status quo, ENABLED=False).
    Callable-Injection vermeidet Zirkel-Import auf ``generate_report``.
    """
    finra = stock.get("finra_data") or {}
    sub = sub_scores or {}
    rel_vol_live = _safe_float(stock.get("rel_volume"))
    rel_vol_norm = None
    if normalize_rvol_fn is not None:
        avg_20d = _safe_float(stock.get("avg_vol_20d"))
        if rel_vol_live is not None and avg_20d is not None and avg_20d > 0:
            # rel_volume = cur_vol / avg_20d (status quo, ENABLED=False),
            # also cur_vol = rel_volume × avg_20d — verlustfrei rückgewandelt.
            cur_vol = rel_vol_live * avg_20d
            try:
                rel_vol_norm = normalize_rvol_fn(
                    cur_vol, avg_20d,
                    run_phase=run_phase,
                    now_utc=run_ts,
                    force_enabled=True,
                )
            except Exception as exc:
                log.debug("score_inflation_log: normalize_rvol fehlgeschlagen für %s: %s",
                          stock.get("ticker"), exc)
                rel_vol_norm = None
    return {
        "schema_v": SCHEMA_V,
        "run_ts":  run_ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_phase": run_phase,
        "ticker":  stock.get("ticker"),
        "score_total":    _safe_float(stock.get("score"), 0.0),
        "score_raw":      _safe_float(stock.get("score_raw"), 0.0),
        "score_smoothed": _safe_float(stock.get("score_smoothed")),
        "sub_scores": {
            "struct":              _safe_float(sub.get("struct")),
            "catalyst":            _safe_float(sub.get("catalyst")),
            "timing":              _safe_float(sub.get("timing")),
            "struct_max":          sub.get("struct_max"),
            "catalyst_max":        sub.get("catalyst_max"),
            "timing_max":          sub.get("timing_max"),
            "turnover_pts":        sub.get("turnover_pts"),
            "gap_pts":             sub.get("gap_pts"),
            "rs_spy_pts":          sub.get("rs_spy_pts"),
            "earliness_pts":       _safe_float(stock.get("earliness_pts"), 0.0),
            "score_trend_bonus":   _safe_float(stock.get("score_trend_bonus_pts"), 0.0),
            "agent_boost_factor":  _safe_float(stock.get("agent_boost_factor"), 1.0),
            "late_runner_active":  bool(stock.get("late_runner") or False),
        },
        "drivers_raw": {
            "rel_volume":            rel_vol_live,
            "rel_volume_normalized": rel_vol_norm,
            "change_2d":             _safe_float(stock.get("change_2d")),
            "change_3d":             _safe_float(stock.get("change_3d")),
            "rsi14":                 _safe_float(stock.get("rsi14")),
            "short_float":           _safe_float(stock.get("short_float")),
            "days_to_cover":         _safe_float(stock.get("short_ratio")),
            "finra_si_trend":        _normalize_si_trend(finra.get("trend")),
            "finra_combo_active":    _finra_combo_active(stock),
            "finra_bonus_pts":       int(_safe_float(stock.get("finra_bonus_pts"), 0) or 0),
        },
        "trading_session_phase": _session_phase(run_ts),
    }


def record_top10_inflation(stocks: Iterable[dict],
                           sub_scores_fn,
                           run_ts: datetime | None = None,
                           path: str = LOG_FILE,
                           run_phase: str | None = None,
                           normalize_rvol_fn=None) -> int:
    """Append-only-Logger für Top-10-Ticker.

    Schreibt eine Zeile pro Stock in ``path`` (JSON Lines). Bei Schreib-
    fehler: structured log + return 0, kein Re-Raise (Daily-Run darf
    nicht wegen Log-Fehler crashen).

    ``sub_scores_fn(stock) -> dict`` ist die ``_compute_sub_scores``-
    Funktion aus ``generate_report`` — als Callable übergeben, damit
    dieses Modul keinen Zirkel-Import braucht.

    ``run_phase`` (``premarket`` / ``postclose``) wird in jeden Eintrag
    persistiert — ist der Schlüssel für die Inflations-Vergleichs-
    Analyse: gleicher Ticker, premarket vs. postclose desselben
    Tages = direkte Messung der Intra-Day-Score-Inflation.

    ``normalize_rvol_fn`` (PR-β, 16.05.2026): Callable
    ``(raw_vol, avg_20d, *, run_phase, now_utc, force_enabled) -> float``,
    typischerweise ``generate_report._normalize_rvol``. Wenn gesetzt,
    schreibt der Logger zusätzlich ``drivers_raw.rel_volume_normalized``
    in jede Zeile — den hypothetischen Wert mit ``ENABLED=True``,
    Empirik-Basis für PR-γ-Skalierer-Validierung. Status-quo-Verhalten
    bleibt unverändert (``rel_volume`` zeigt weiterhin den Live-Wert).

    Returnt die Anzahl erfolgreich geschriebener Zeilen.
    """
    if run_ts is None:
        run_ts = datetime.now(timezone.utc)
    n_written = 0
    try:
        with open(path, "a", encoding="utf-8") as fh:
            for stock in stocks:
                try:
                    sub = sub_scores_fn(stock) if sub_scores_fn else None
                    entry = _build_entry(stock, run_ts, sub,
                                          run_phase=run_phase,
                                          normalize_rvol_fn=normalize_rvol_fn)
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    n_written += 1
                except Exception as exc:
                    log.warning("score_inflation_log: Eintrag für %s übersprungen: %s",
                                stock.get("ticker"), exc)
        log.info("score_inflation_log: %d Zeilen an %s angehängt (phase=%s)",
                 n_written, path, _session_phase(run_ts))
    except OSError as exc:
        log.warning("score_inflation_log: Schreibfehler an %s — übersprungen: %s",
                    path, exc)
    return n_written


def prune_log(max_days: int = CUTOFF_DAYS, path: str = LOG_FILE) -> int:
    """Entferne Einträge älter als ``max_days`` Kalendertage.

    Liest die ganze Datei, filtert per ``run_ts`` (ISO-Datum, korrekt
    geparst — NICHT lexikographisch wie der gefixte score_history-Bug),
    schreibt das Resultat atomar zurück (tmpfile + rename).

    Kaputte JSONL-Zeilen werden geskippt (Warning geloggt) — nachfolgende
    Zeilen bleiben lesbar. Fail-soft: bei Schreibfehler returnt 0,
    Datei bleibt unverändert.

    Returnt die Anzahl beim Prune entfernter Zeilen (negativ = mehr
    geschrieben als gelesen ist nicht möglich → 0).
    """
    if not os.path.exists(path):
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    kept: list[str] = []
    n_seen = 0
    n_bad  = 0
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                n_seen += 1
                try:
                    obj = json.loads(line)
                    ts_str = obj.get("run_ts", "")
                    # Tolerant gegen "Z"-Suffix und +HH:MM-Offsets.
                    if ts_str.endswith("Z"):
                        ts_str_iso = ts_str[:-1] + "+00:00"
                    else:
                        ts_str_iso = ts_str
                    ts = datetime.fromisoformat(ts_str_iso)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    n_bad += 1
                    log.warning("score_inflation_log: kaputte Zeile übersprungen "
                                "(behält sie aber bis Manual-Cleanup): %s", exc)
                    # Kaputte Zeilen NICHT droppen — sonst könnte ein
                    # Parse-Bug stille Datenverluste produzieren. Stattdessen
                    # weitergeben und Operator entscheiden lassen.
                    kept.append(line)
                    continue
                if ts >= cutoff:
                    kept.append(line)
    except OSError as exc:
        log.warning("score_inflation_log: Prune-Read-Fehler — übersprungen: %s", exc)
        return 0

    n_removed = n_seen - (len(kept) - n_bad)
    if n_removed <= 0:
        return 0

    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            for line in kept:
                fh.write(line + "\n")
        os.replace(tmp_path, path)
    except OSError as exc:
        log.warning("score_inflation_log: Prune-Write-Fehler — Datei unverändert: %s", exc)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return 0
    log.info("score_inflation_log: %d Einträge (älter als %d Tage) geprunt",
             n_removed, max_days)
    return n_removed


def read_all(path: str = LOG_FILE) -> list[dict]:
    """Tool-Helper: liest alle Einträge zurück als Liste. Kaputte Zeilen
    werden geskippt (kein Crash). Für CLI-Diagnose und Tests."""
    if not os.path.exists(path):
        return []
    entries: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries
