"""Single-Source-of-Truth für State-Invariant-Persistenz (Phase 1).

Hintergrund: der score_history-Pruning-Bug (PR #119) blieb 11 Tage
unentdeckt, obwohl Symptome im Git-Log sichtbar waren. Der KI-Score-
Drift heute (14.05.2026) — agent_signals.json hatte alte Top-10,
Daily-Run rendert ohne KI-Score — wurde nur durch User-Report bemerkt.
Beide Klassen: Pipeline grün, Artefakt kaputt.

Dieses Modul wertet 7 State-Invariants nach jedem Daily-Run und nach
jedem ki_agent-Tick aus und schreibt eine Append-Only-Zeile pro Run
in ``health_check_log.jsonl``. Phase 1 ist silent Logging — kein Push.
Digest-Workflow (Phase 3) liest die Datei später und aggregiert.

Spec: ``docs/health_check_spec.md``. Schwellen: ``config.py``-
Konstanten ``HEALTH_CHECK_*``.

Modul-Speicherort: Repo-Root (analog ``score_inflation_log.py``,
``push_history.py``), weil zur Laufzeit vom Daily-Run und ki_agent
eingebunden — kein Tool-Skript.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import config  # für getattr-IST-Read im Konsistenz-Wächter (Projekt C)
from config import (
    CONSISTENCY_EXPECTED_STATE,
    DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES,
    HEALTH_CHECK_CUTOFF_DAYS,
    HEALTH_CHECK_S2_MIN_TICKERS,
    HEALTH_CHECK_S5_MIN_INFLATION_LINES,
    HEALTH_CHECK_S6_MIN_MONSTER_NONZERO,
    HEALTH_CHECK_S7_MIN_AGENT_OVERLAP,
    HEALTH_CHECK_S8_MAX_AGE_HOURS,
    HEALTH_CHECK_S14_MAX_AGE_HOURS,
    HEALTH_CHECK_S11_MAX_WORKDAYS_NO_PREMARKET,
    HEALTH_CHECK_S12_MAX_WORKDAYS_NO_POSTCLOSE,
    S10_MUSS_FIELDS,
    S10_LAG_FIELDS,
    S10_OBSERVED_FIELDS,
    S10_WINDOW_SIZE,
    S10_MUSS_MIN_N,
    S10_LAG_MIN_AGED_N,
)

# Digest-State-Datei für S8-Invariant (single source of truth über
# Digest-Push-Health). Lese-only — geschrieben von
# scripts/health_check_digest.py.
DIGEST_STATE_FILE = "health_check_digest_state.json"

# Score-Inflation-Log-Datei für S11/S12-Invarianten (Phasen-Sammel-
# Frequenz). Analog DIGEST_STATE_FILE — Modul-Attribut, damit Tests die
# Datei via ``patch.object(hc, "SCORE_INFLATION_LOG_FILE", ...)`` umlenken
# können. Lese-only — geschrieben von score_inflation_log.py.
SCORE_INFLATION_LOG_FILE = "score_inflation_log.jsonl"

# Gist-Pull-State-Datei für S14-Invariant (Gist-Pull-Liveness). Analog
# DIGEST_STATE_FILE — Modul-Attribut, damit Tests die Datei via
# ``patch.object(hc, "GIST_PULL_STATE_FILE", ...)`` umlenken können.
# Lese-only — geschrieben von scripts/pull_gist_data.py (#310), NUR im
# HTTP-Gist-Erfolgszweig. Schreiblogik NICHT von hier verändern.
GIST_PULL_STATE_FILE = "gist_pull_state.json"

log = logging.getLogger(__name__)

LOG_FILE = "health_check_log.jsonl"
SCHEMA_V = 1

# Phase 2 — Provider-Health-Persistenz (analog state_fails-Logging).
# Eine Zeile pro Provider pro Run. Schema siehe Spec:
# docs/health_check_spec.md Z. 86–101.
LOG_FILE_PROVIDER = "provider_health.jsonl"
SCHEMA_V_PROVIDER = 1


def _today_iso_from_ts(run_ts: datetime) -> str:
    """ISO-Datum (YYYY-MM-DD) im US-Eastern-Slot. Match zur Daily-Run-
    Persistenz in ``score_history.json``, die ebenfalls ET-Datum nutzt."""
    if run_ts.tzinfo is None:
        run_ts = run_ts.replace(tzinfo=timezone.utc)
    # ET-Datum, weil score_history "DD.MM.YYYY"-Strings im ET-Slot schreibt.
    # Hier reicht UTC-Date für die crit-Invariant — der ki_agent-Run um
    # 02:56 UTC ist noch der gestrige ET-Tag, würde S1 fälschlich failen.
    # Lösung: wir konvertieren in ET nur wenn benötigt; hier UTC-iso als
    # Default, der Caller kann today_iso überschreiben.
    return run_ts.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _score_history_has_today(score_history: dict | None,
                             ticker: str,
                             today_iso: str) -> bool:
    """``score_history[ticker]`` letzter Eintrag hat heutiges Datum?

    Akzeptiert beide Formate: 2-Tuple ``[date, score]`` und 3-Tuple
    ``[date, score, drivers]``. Datum kann ISO oder ``DD.MM.YYYY`` sein
    — beide auf ISO normalisieren für den Vergleich.
    """
    if not score_history or not isinstance(score_history, dict):
        return False
    entries = score_history.get(ticker) or []
    if not entries:
        return False
    last = entries[-1]
    if isinstance(last, dict):
        raw = last.get("date") or ""
    elif isinstance(last, (list, tuple)) and last:
        raw = last[0]
    else:
        return False
    if not isinstance(raw, str):
        return False
    iso = _normalize_date(raw)
    return iso == today_iso


def _normalize_date(raw: str) -> str:
    """``DD.MM.YYYY`` oder ``YYYY-MM-DD`` → ISO ``YYYY-MM-DD``."""
    if "-" in raw and len(raw) >= 10:
        return raw[:10]
    if "." in raw:
        try:
            d, m, y = raw.split(".")
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        except (ValueError, TypeError):
            return raw
    return raw


def _digest_age_hours(now_utc: datetime,
                       state_path: str | None = None) -> float | None:
    """Alter (in Stunden) seit dem letzten erfolgreichen Digest-Workflow-Lauf.

    Liest ``last_successful_run`` (ISO-Timestamp) aus
    ``health_check_digest_state.json`` und gibt das Alter relativ zu
    ``now_utc`` zurück. Returnt ``None`` wenn:
    - Datei fehlt (S8 wird übersprungen, S2/S3 würden vorher schon
      einen frischen Setup-Stand zeigen)
    - Feld fehlt / nicht parsebar / ``None`` (Erstaufsetzen)
    - JSON kaputt

    Damit S8 erst dann warnt, wenn die Pipeline schon mal erfolgreich
    war — keine false positives beim Erstaufsetzen.

    **Referenz-Wechsel 29.05.2026:** vorher las S8 ``last_digest_sent``
    (YYYY-MM-DD) und nahm Mitternacht UTC des Datums als Referenz. Das
    erzeugte bei stabilem Cron-Drift (Digest fährt regulär ~12:00 UTC
    durch statt 08:47 UTC) einen systematischen ~12 h Bias gegenüber
    der echten Push-Zeit. Beleg: am 29.05 um 11:41Z mass S8 35.7 h
    (Mitternacht 28.05 → 29.05 11:41 UTC), obwohl der echte Abstand
    zur 28.05 12:04Z-Push-Zeit nur 23.6 h betrug → täglicher false-
    positive S8-warn um den Vormittag.

    ``last_successful_run`` ist ein **ISO-Timestamp** (Sekunden-Auflösung)
    und gibt die echte Workflow-Lauf-Zeit — keine Mitternacht-
    Konvention. Konsistent mit der Spec (Liveness-Marker für „Digest-
    Workflow lief zuletzt durch"). Geschrieben EXKLUSIV von
    ``scripts/health_check_digest.py:307`` (überprüft per Vorab-Grep),
    daher echter Digest-Liveness-Marker (kein häufig-aktualisierendes
    Fremdsystem hält das Feld künstlich frisch).

    ``_already_sent_today`` (mehrfach-Trigger-Schutz im Digest-Script)
    nutzt weiterhin ``last_digest_sent`` (YYYY-MM-DD) — Zwei-Felder-
    Architektur ist bewusst, beide Felder werden vom selben Workflow-
    Lauf-Block geschrieben.

    ``state_path`` wird zur Aufruf-Zeit aus dem Modul-Attribut gelesen
    (kein Default-Argument-Binding), damit Tests die Datei via
    ``patch.object(hc, "DIGEST_STATE_FILE", ...)`` umlenken können.
    """
    path = state_path if state_path is not None else DIGEST_STATE_FILE
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    raw = state.get("last_successful_run")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        # ISO-8601 mit/ohne ``Z``-Suffix. Python 3.11+ akzeptiert ``Z``
        # nativ; defensive auf +00:00 normalisieren für ältere Releases.
        run_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    # Sicherstellen, dass run_dt timezone-aware ist (kann naiv sein wenn
    # ein Schreibpfad mal ohne Z geschrieben hat).
    if run_dt.tzinfo is None:
        run_dt = run_dt.replace(tzinfo=timezone.utc)
    delta = now_utc - run_dt
    return delta.total_seconds() / 3600.0


def _iso_marker_age_hours(now_utc: datetime, path: str,
                          field: str) -> float | None:
    """Alter (h) seit einem ISO-UTC-Liveness-Marker-Feld in einer State-Datei.

    Kanonische, wiederverwendbare Parsing-Logik — algorithmisch identisch zu
    ``_digest_age_hours`` (S8), aber generisch über ``path`` + ``field``.
    Genutzt von ``_gist_pull_age_hours`` (S14). ``_digest_age_hours`` (S8)
    behält bewusst seine eigene Inline-Kopie, weil ``test_12`` in
    ``mock_test_s8_last_successful_run.py`` die S8-Funktion per Source-
    Inspektion an ``state.get("last_successful_run")`` im eigenen Body bindet
    — eine spätere Vereinheitlichung müsste diesen Test mit-generalisieren.

    Returnt ``None`` (= Invariant SKIP, kein Fail) bei: Datei fehlt, JSON
    kaputt, Feld fehlt/``None``/nicht-str, Timestamp unparsebar. tz-naiver
    Timestamp → defensive als UTC interpretiert. Reine Funktion ohne
    Side-Effects; gleicher Input → gleiches Ergebnis (deterministisch).
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    raw = state.get(field)
    if not isinstance(raw, str) or not raw:
        return None
    try:
        # ISO-8601 mit/ohne ``Z``-Suffix (Python 3.11+ akzeptiert ``Z`` nativ;
        # defensive auf +00:00 normalisieren für ältere Releases).
        marker_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if marker_dt.tzinfo is None:
        marker_dt = marker_dt.replace(tzinfo=timezone.utc)
    return (now_utc - marker_dt).total_seconds() / 3600.0


def _gist_pull_age_hours(now_utc: datetime,
                         state_path: str | None = None) -> float | None:
    """Alter (h) seit dem letzten erfolgreichen Gist-Pull (S14-Liveness).

    Liest ``last_successful_gist_pull`` (ISO-UTC) aus
    ``gist_pull_state.json`` (geschrieben von ``scripts/pull_gist_data.py``
    NUR im HTTP-Gist-Erfolgszweig, #310). ``None`` → S14 SKIP (Datei fehlt
    vor dem ersten erfolgreichen Pull / Feld null / unparsebar) — keine
    false positives beim Erstaufsetzen, exakt analog S8.

    ``state_path`` wird zur Aufruf-Zeit aus dem Modul-Attribut gelesen,
    damit Tests die Datei via ``patch.object(hc, "GIST_PULL_STATE_FILE",
    ...)`` oder direktes ``state_path``-Argument umlenken können.
    """
    path = state_path if state_path is not None else GIST_PULL_STATE_FILE
    return _iso_marker_age_hours(now_utc, path, "last_successful_gist_pull")


def _last_phase_run_age_workdays(
    target_run_phase: str,
    target_tsp: str,
    now_utc: datetime,
    log_path: str | None = None,
) -> int | None:
    """Werktage (Mo–Fr) seit dem letzten ECHTEN Phasen-Run im
    ``score_inflation_log.jsonl``.

    Definition „echter Phasen-Run": ``run_phase == target_run_phase``
    UND ``trading_session_phase == target_tsp`` (z. B. ``premarket``+
    ``premarket`` oder ``postclose``+``postclose``). Damit werden
    gedriftete Crons (run_phase=premarket aber tsp=open/midday) korrekt
    NICHT als echter premarket-Run gezählt.

    Werktag-Zählung Mo–Fr ab dem Tag NACH dem letzten Run-Datum bis
    ``now_utc`` (inkl.) — analog ``ki_agent._trading_days_elapsed`` /
    ``_s10_trading_days_elapsed``. Feiertage werden vereinfacht ignoriert;
    durch das absence-of-write-Muster sicher: an Feiertagen/Wochenenden
    feuern Crons strukturell nicht, daher entstehen keine false-positives.

    Returnt ``None`` wenn:
    - Datei fehlt (Erstaufsetzen — analog ``_digest_age_hours``)
    - keine matchende Zeile vorhanden
    - JSON/Datums-Parse-Fehler

    ``log_path`` wird zur Aufruf-Zeit aus dem Modul-Attribut gelesen
    (kein Default-Argument-Binding), damit Tests die Datei via
    ``patch.object(hc, "SCORE_INFLATION_LOG_FILE", ...)`` umlenken können.
    """
    path = log_path if log_path is not None else SCORE_INFLATION_LOG_FILE
    if not os.path.exists(path):
        return None
    latest_ts: str | None = None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (row.get("run_phase") == target_run_phase
                        and row.get("trading_session_phase") == target_tsp):
                    ts = row.get("run_ts")
                    if (isinstance(ts, str)
                            and (latest_ts is None or ts > latest_ts)):
                        latest_ts = ts
    except OSError:
        return None
    if not latest_ts:
        return None
    try:
        last_dt = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    last_date = last_dt.date()
    today = now_utc.date()
    if last_date >= today:
        return 0
    n = 0
    d = last_date
    while d < today:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


# ── S10 — Daten-Integritäts-Check (Phase 1, minimal) ──────────────────────


def _s10_trading_days_elapsed(entry_date_str: str,
                               today: date | None = None) -> int:
    """Strikt Mo–Fr nach ``entry_date`` zählen (analog
    ``ki_agent._trading_days_elapsed``). Returnt -1 bei nicht parsebar.

    Wir duplizieren die Funktion bewusst hier, damit ``health_check.py``
    keine Cross-Import-Abhängigkeit zu ``ki_agent.py`` aufbauen muss
    (ki_agent importiert seinerseits health_check).
    """
    try:
        start = datetime.strptime(entry_date_str, "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return -1
    today = today or datetime.now(timezone.utc).date()
    n = 0
    d = start
    while d < today:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def _s10_load_v4_entries(bh_path: str = "backtest_history.json"
                         ) -> list[dict]:
    """Lädt backtest_history.json, filtert auf schema_v=4 + Wochenend-Filter.

    Wochenend-Filter: Einträge mit ``date.weekday() >= 5`` werden
    ausgeklammert. Die 96 Bestands-Leichen aus manuellen Sa/So-Triggern
    würden sonst LAG-Pfad permanent false-positive machen. PR #244 hat
    den Schreibschutz eingebaut, aber Bestandseinträge bleiben.

    Returnt 0 Einträge bei FileNotFound/Parse-Fehler — Caller skipt S10.
    """
    if not os.path.exists(bh_path):
        return []
    try:
        with open(bh_path, "r", encoding="utf-8") as fh:
            bh = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(bh, list):
        return []
    v4: list[dict] = []
    for e in bh:
        if not isinstance(e, dict):
            continue
        if e.get("backtest_schema_version") != 4:
            continue
        d_str = e.get("date", "")
        try:
            d_obj = datetime.strptime(d_str, "%d.%m.%Y").date()
        except (TypeError, ValueError):
            continue
        if d_obj.weekday() >= 5:
            continue  # Wochenend-Filter
        v4.append(e)
    return v4


def _s10_check_muss_field(entries: list[dict], field: str,
                           warn_pct: float, crit_pct: float,
                           window: int, min_n: int) -> dict | None:
    """Letzte ``window`` Einträge: wie viele Prozent haben das Feld auf
    ``None``? ``is None`` (nicht ``not v``) — sonst false-positive bei
    legitim-0-Werten wie ``score_trend_bonus=0.0``.

    Returnt None wenn n < min_n oder pct < warn_pct.
    """
    recent = entries[-window:] if window > 0 else entries
    n = len(recent)
    if n < min_n:
        return None
    n_null = sum(1 for e in recent if e.get(field) is None)
    pct = 100.0 * n_null / n if n > 0 else 0.0
    if pct >= crit_pct:
        sev = "crit"
    elif pct >= warn_pct:
        sev = "warn"
    else:
        return None
    return {
        "severity": sev, "field": field, "n": n, "n_null": n_null,
        "pct": pct,
    }


def _s10_check_lag_field(entries: list[dict], field: str,
                          lag_trading_days: int, warn_pct: float,
                          min_aged_n: int,
                          today: date | None = None) -> dict | None:
    """Einträge älter als ``lag_trading_days`` Trading-Tage: wie viele
    Prozent haben das Feld noch ``None``?

    Returnt None wenn aged_n < min_aged_n oder pct < warn_pct.
    LAG-Felder werden NIE als crit klassifiziert — fehlende Outcomes
    sind ärgerlich, nicht akut (kein Push-Block).
    """
    aged = [
        e for e in entries
        if _s10_trading_days_elapsed(e.get("date", ""), today)
            >= lag_trading_days
    ]
    n = len(aged)
    if n < min_aged_n:
        return None
    n_null = sum(1 for e in aged if e.get(field) is None)
    pct = 100.0 * n_null / n if n > 0 else 0.0
    if pct < warn_pct:
        return None
    return {
        "severity": "warn", "field": field, "n_aged": n, "n_null": n_null,
        "pct": pct, "lag": lag_trading_days,
    }


def _s10_check_unknown_fields(entries: list[dict]) -> set[str]:
    """Auto-Detect-WARN: welche Feld-Keys tauchen in V4-Einträgen auf,
    die weder in MUSS noch LAG noch OBSERVED stehen?

    Schema-Erweiterer wird durch den WARN gezwungen, das Feld zu
    klassifizieren — Premium-Ziel-Prinzip: das System bemerkt, was es
    nicht versteht.
    """
    known = (set(S10_MUSS_FIELDS.keys())
             | set(S10_LAG_FIELDS.keys())
             | set(S10_OBSERVED_FIELDS))
    seen: set[str] = set()
    for e in entries:
        seen |= set(e.keys())
    return seen - known


def evaluate_s10_data_integrity(bh_path: str = "backtest_history.json",
                                 today: date | None = None,
                                 ) -> list[dict]:
    """S10 main entry. Returnt Liste von Fail-Dicts im Standard-Format.

    Pure-Wrapper für leichtere Mock-Tests (Caller kann ``bh_path`` auf
    Test-Fixture umlenken). Wird von ``evaluate_state_invariants`` mit
    Default-Pfad aufgerufen.
    """
    v4 = _s10_load_v4_entries(bh_path)
    if not v4:
        # Kein V4-Eintrag (oder Datei fehlt) → S10 nichts zu sagen.
        # Kein Fail emittieren — S2 hat den Universum-Check eh schon.
        return []
    out: list[dict] = []
    # MUSS-Felder
    for field, cfg in S10_MUSS_FIELDS.items():
        res = _s10_check_muss_field(
            v4, field,
            warn_pct=cfg["warn_pct"], crit_pct=cfg["crit_pct"],
            window=S10_WINDOW_SIZE, min_n=S10_MUSS_MIN_N,
        )
        if res is None:
            continue
        out.append({
            "id":       "S10",
            "severity": res["severity"],
            "detail":   (f"MUSS-Feld {field!r}: {res['n_null']}/{res['n']} "
                         f"null ({res['pct']:.0f}%) in letzten "
                         f"{S10_WINDOW_SIZE} V4-Einträgen — "
                         f"Daten-Pipeline füllt nicht"),
        })
    # LAG-Felder
    for field, cfg in S10_LAG_FIELDS.items():
        res = _s10_check_lag_field(
            v4, field,
            lag_trading_days=cfg["lag_trading_days"],
            warn_pct=cfg["warn_pct"], min_aged_n=S10_LAG_MIN_AGED_N,
            today=today,
        )
        if res is None:
            continue
        out.append({
            "id":       "S10",
            "severity": res["severity"],
            "detail":   (f"LAG-Feld {field!r}: {res['n_null']}/{res['n_aged']} "
                         f"gealterte Einträge (≥ {res['lag']} Trading-Tage) "
                         f"haben kein Outcome ({res['pct']:.0f}%) — "
                         f"Rolling-Update-Pipeline füllt nicht"),
        })
    # Auto-Detect: unbekannte Felder
    unknown = _s10_check_unknown_fields(v4)
    if unknown:
        sample = ", ".join(sorted(unknown)[:5])
        more   = f" und {len(unknown) - 5} weitere" if len(unknown) > 5 else ""
        out.append({
            "id":       "S10",
            "severity": "warn",
            "detail":   (f"Unklassifizierte Felder in V4-backtest_history "
                         f"({len(unknown)}): {sample}{more} — "
                         f"in S10_MUSS_FIELDS / S10_LAG_FIELDS / "
                         f"S10_OBSERVED_FIELDS klassifizieren"),
        })
    return out


# ── S13: Daten-Reife-Gate (30.06.-Auswertungen) ─────────────────────────────


def _drg_count_mature(entries: list[dict]) -> tuple[int, int]:
    """Zählt (reif_return_5d, reif_return_10d) in einer Eintragsliste.

    „reif" = das jeweilige Forward-Label ist nicht ``None`` (Outcome
    gefüllt). Beide Felder werden GETRENNT gezählt — die 30.06.-Auswertung
    ist noch NICHT als Code codifiziert (kein Modul liest backtest_history
    für die Edge-Auswertung), darum melden wir return_5d UND return_10d
    parallel statt eine der beiden Definitionen vorwegzunehmen.
    """
    r5 = sum(1 for e in entries if e.get("return_5d") is not None)
    r10 = sum(1 for e in entries if e.get("return_10d") is not None)
    return r5, r10


def _consistency_checks(expected_state: dict,
                        actual_state: dict | None = None,
                        ) -> tuple[list[str], list[dict]]:
    """Konsistenz-Wächter (Projekt C): Soll vs. Ist je deklarierter
    config-Konstante. Pure.

    ``expected_state``: ``{config_const_name: soll_wert}`` (Single-Source
    ``CONSISTENCY_EXPECTED_STATE``). ``actual_state`` optional für Tests
    (Drift simulieren ohne config-Monkeypatch); ``None`` → IST live via
    ``getattr(config, name)``.

    Returnt ``(status_parts, fails)``: ``status_parts`` = kompakte
    ``name=ist/soll [OK|DRIFT]``-Strings (immer da), ``fails`` = ein
    warn-Fail (id ``S13``) PRO driftendem Wert (gleiche Form wie heute).

    Nur STABILE, getattr-lesbare Konstanten gehören in ``expected_state``
    — keine volatilen Tunables (Conviction-Schwellen), keine Crons/Literale
    (Sonderlogik, anderweitig abgedeckt durch S11/S12 + Provider-Health).
    """
    status_parts: list[str] = []
    fails: list[dict] = []
    for name, soll in expected_state.items():
        ist = (actual_state[name] if actual_state is not None
               else getattr(config, name, None))
        ok = (ist == soll)
        status_parts.append(f"{name}={ist!r}/{soll!r} [{'OK' if ok else 'DRIFT'}]")
        if not ok:
            fails.append({
                "id": "S13", "severity": "warn",
                "detail": (
                    f"Soll-Ist-Drift {name}: Soll={soll!r}, Ist={ist!r} — "
                    f"deklarierter Config-Zustand weicht vom realen ab"),
            })
    return status_parts, fails


def evaluate_data_maturity_gate(
    bh_path: str = "backtest_history.json",
    *,
    expected_state: dict | None = None,
    actual_state: dict | None = None,
) -> dict:
    """Daten-Reife-Gate (S13) + Konsistenz-Wächter (Projekt C). Rein lesend.

    Zählt die Stichproben-Reife in ``backtest_history.json`` (3 Zeilen) UND
    gleicht deklarierte SOLL-config-Zustände gegen den IST ab (4. Zeile +
    Drift-Warns). Ändert NICHTS am Score / an Filtern / an der Auswertung.

    Reife-Definition (kritisch — exakt wie die geplante Auswertung):
      - V2-only = ``backtest_schema_version == 4`` (S10-Loader-Filter,
        Single-Source ``_s10_load_v4_entries``).
      - Setup-Edge-Bucket = ``score >= 70``.
      - „reif" = Forward-Label ``return_5d`` / ``return_10d`` nicht None.
      Da die 30.06.-Auswertungslogik noch NICHT als Code existiert, werden
      return_5d UND return_10d getrennt gemeldet (keine Vorwegnahme).

    Konsistenz-Wächter: ``expected_state`` (Default
    ``CONSISTENCY_EXPECTED_STATE``) — Soll vs. Ist (live via getattr) je
    config-Konstante; ein warn-Fail pro Drift. ``actual_state`` nur für
    Tests (Drift-Injektion ohne config-Monkeypatch).

    Returnt ``{"status_lines": [str, str, str, str], "fails": [<warn>...]}``:
      - ``status_lines`` = 4 immer-vorhandene Report-Zeilen (3 Reife + 1
        Konsistenz), die der Aufrufer „laufend" loggt — auch ohne Warnung.
      - ``fails`` = Standard-Fail-Dicts (id ``S13``), nur bei Soll-Ist-Drift.
    """
    if expected_state is None:
        expected_state = CONSISTENCY_EXPECTED_STATE
    v4 = _s10_load_v4_entries(bh_path)

    # 1) SETUP-EDGE (≥70-Bucket, schema_v==4) — reine Counts (RVOL-Soll-Check
    #    ist in den Konsistenz-Wächter überführt, nicht doppeln).
    ge70 = [e for e in v4 if (e.get("score") or 0) >= 70]
    s_r5, s_r10 = _drg_count_mature(ge70)
    setup_line = (
        f"Setup-Edge (≥70, schema_v4): vorhanden={len(ge70)} "
        f"reif_5d={s_r5} reif_10d={s_r10}"
    )

    # 2) ENTRY-AUC (entry_score, schema_v==4) — Modul-Start 10.06.
    entry = [e for e in v4 if e.get("entry_score") is not None]
    if entry:
        e_r5, e_r10 = _drg_count_mature(entry)
        entry_line = (
            f"Entry-AUC (entry_score): vorhanden={len(entry)} "
            f"reif_5d={e_r5} reif_10d={e_r10}"
        )
    else:
        entry_line = "Entry-AUC (entry_score): Modul ungebaut, n=0"

    # 3) CTB-EDGE (cost_to_borrow, schema_v==4) — Persistenz-PR offen.
    ctb = [e for e in v4 if e.get("cost_to_borrow") is not None]
    if ctb:
        c_r5, c_r10 = _drg_count_mature(ctb)
        ctb_line = (
            f"CTB-Edge (cost_to_borrow): mit_CTB={len(ctb)} "
            f"reif_5d={c_r5} reif_10d={c_r10}"
        )
    else:
        ctb_line = "CTB-Edge (cost_to_borrow): Persistenz ungebaut, n=0"

    # 4) KONSISTENZ-WÄCHTER (Projekt C) — Soll vs. Ist je config-Konstante.
    cons_parts, fails = _consistency_checks(expected_state, actual_state)
    consistency_line = "Konsistenz-Wächter: " + " · ".join(cons_parts)

    return {
        "status_lines": [setup_line, entry_line, ctb_line, consistency_line],
        "fails": fails,
    }


# ── State-Invariants ────────────────────────────────────────────────────────


def evaluate_state_invariants(
    *,
    top10_tickers: list[str] | None = None,
    setup_scores: dict | None = None,
    monster_scores: dict | None = None,
    positions: dict | None = None,
    score_history: dict | None = None,
    today_iso: str | None = None,
    run_phase: str = "premarket",
    n_inflation_lines: int | None = None,
    n_backtest_appended: int | None = None,
    backtest_has_today: bool | None = None,
    agent_signal_keys: set[str] | list[str] | None = None,
    ki_agent_only: bool = False,
    now_utc: datetime | None = None,
    html_path: str | None = None,
) -> list[dict]:
    """Bewertet alle 8 State-Invariants. Returnt Liste von Fail-Dicts.

    Jeder Fail-Eintrag: ``{"id": "S<n>", "severity": "crit"|"warn",
    "detail": "<string>"}``.

    ``ki_agent_only=True``: nur S2/S3/S6/S8/S14 werden bewertet (S1/S4/S5/S7
    sind ki_agent-Tick irrelevant — agent_signals.json wird vom Tick
    selbst geschrieben, also wäre S7 ein Tautologie-Pass; S1/S4/S5
    sind Daily-Run-Outputs). S8 und S14 laufen in beiden Pfaden, weil die
    Digest-Stale- bzw. Gist-Pull-Liveness-Diagnose nicht von der Phase
    abhängt (S14 sogar mit ~1 h Detektionslatenz im stündlichen Tick).

    Spec: ``docs/health_check_spec.md`` Sektion „State-Invariants".
    """
    fails: list[dict] = []
    tickers = list(top10_tickers or [])

    # === S1 (crit) — score_history hat heutige Einträge für Top-10 =========
    if not ki_agent_only:
        if not tickers:
            fails.append({
                "id": "S1", "severity": "crit",
                "detail": "Top-10-Liste leer — score_history-Check übersprungen",
            })
        elif today_iso:
            missing = [t for t in tickers
                       if not _score_history_has_today(score_history, t, today_iso)]
            if missing:
                fails.append({
                    "id": "S1", "severity": "crit",
                    "detail": (f"score_history ohne heutigen Eintrag für "
                               f"{len(missing)}/{len(tickers)} Top-10-Ticker: "
                               f"{', '.join(missing[:5])}"),
                })

    # === S2 (crit) — setup_scores ≥ HEALTH_CHECK_S2_MIN_TICKERS ============
    sc = setup_scores or {}
    if len(sc) < HEALTH_CHECK_S2_MIN_TICKERS:
        fails.append({
            "id": "S2", "severity": "crit",
            "detail": (f"setup_scores enthält {len(sc)} Tickers, "
                       f"Schwelle ≥ {HEALTH_CHECK_S2_MIN_TICKERS}"),
        })

    # === S3 (crit) — Positionen haben current_price ========================
    pos = positions or {}
    if pos:
        missing_price = []
        for ticker, payload in pos.items():
            if not isinstance(payload, dict):
                continue
            cp = payload.get("current_price")
            if cp is None:
                missing_price.append(ticker)
        if missing_price:
            fails.append({
                "id": "S3", "severity": "crit",
                "detail": (f"current_price fehlt bei {len(missing_price)} "
                           f"Position(en): {', '.join(missing_price[:5])}"),
            })

    # === S4 (warn) — backtest_history-Disziplin (Tages-Invariante) =========
    # premarket: WARN wenn dieser Run fälschlich appended hat (Run-Basis).
    # postclose: WARN nur wenn der HEUTIGE Trading-Tag insgesamt KEINEN
    # Eintrag in backtest_history hat (Tages-Basis). Re-Trigger am selben
    # Tag (n_backtest_appended=0, weil _append_backtest_entries idempotent
    # dedupliziert) sind dann kein False-Positive mehr.
    if not ki_agent_only:
        if (run_phase == "premarket"
                and n_backtest_appended is not None
                and n_backtest_appended > 0):
            fails.append({
                "id": "S4", "severity": "warn",
                "detail": (f"backtest_history wuchs in premarket-Run um "
                           f"{n_backtest_appended} Eintrag/Einträge"),
            })
        elif (run_phase == "postclose"
                and backtest_has_today is False):
            # Wochenend-Gate (30.05.2026): postclose-Cron läuft Mo-Fr
            # (``17 21 * * 1-5``). An Sa/So existiert per Design KEIN
            # postclose-Append → S4 würde sonst strukturell für jeden
            # Wochenend-postclose-Run feuern (manueller dispatch, late-
            # cron-Drift mit Berlin-Mitternacht-Übertritt etc.). Gate
            # prüft das DATUM, für das der Eintrag fehlt (today_iso,
            # bewusst NICHT ``datetime.now()`` — sonst greift es bei
            # Fr-22:24Z-Runs mit today_iso=Sa am falschen Tag).
            # Catch-Wert Mo-Fr unverändert.
            # Restkante: US-Feiertage (Memorial Day etc.) bleiben blind —
            # bewusst keine fragile Feiertags-Liste hier; konsistent zu
            # ``ki_agent._trading_days_elapsed`` und
            # ``_last_phase_run_age_workdays`` die ebenfalls nur Mo-Fr
            # filtern. S12 fängt Mehrtages-Drift werktags-robust.
            _skip_weekend = False
            if today_iso:
                try:
                    _wd = datetime.strptime(today_iso, "%Y-%m-%d").weekday()
                    _skip_weekend = _wd >= 5  # 5=Sa, 6=So
                except (ValueError, TypeError):
                    # Parse-Fehler → defensive: altes Verhalten beibehalten
                    # (lieber Wochenend-Lärm in Edge-Case als stilles Skip
                    # des ganzen Mo-Fr-Catch-Werts).
                    _skip_weekend = False
            if not _skip_weekend:
                fails.append({
                    "id": "S4", "severity": "warn",
                    "detail": (f"backtest_history ohne Eintrag für "
                               f"{today_iso or 'heute'} (postclose)"),
                })

    # === S5 (warn) — score_inflation_log ≥ N Zeilen pro Run ===============
    if not ki_agent_only and n_inflation_lines is not None:
        if n_inflation_lines < HEALTH_CHECK_S5_MIN_INFLATION_LINES:
            fails.append({
                "id": "S5", "severity": "warn",
                "detail": (f"score_inflation_log: {n_inflation_lines} neue "
                           f"Zeile(n), Schwelle ≥ "
                           f"{HEALTH_CHECK_S5_MIN_INFLATION_LINES}"),
            })

    # === S6 (warn) — monster_scores: ≥ N Tickers > 0 =======================
    ms = monster_scores or {}
    n_nonzero = sum(1 for v in ms.values()
                    if isinstance(v, (int, float)) and v > 0)
    if n_nonzero < HEALTH_CHECK_S6_MIN_MONSTER_NONZERO:
        fails.append({
            "id": "S6", "severity": "warn",
            "detail": (f"monster_scores: {n_nonzero} Tickers > 0, "
                       f"Schwelle ≥ {HEALTH_CHECK_S6_MIN_MONSTER_NONZERO}"),
        })

    # === S7 (warn) — agent_signals ∩ top10 ≥ N =============================
    if not ki_agent_only and tickers:
        ag_keys = set(agent_signal_keys or [])
        overlap = ag_keys & set(tickers)
        if len(overlap) < HEALTH_CHECK_S7_MIN_AGENT_OVERLAP:
            fails.append({
                "id": "S7", "severity": "warn",
                "detail": (f"agent_signals ∩ top10: {len(overlap)} von "
                           f"{len(tickers)} Top-10-Ticker, Schwelle ≥ "
                           f"{HEALTH_CHECK_S7_MIN_AGENT_OVERLAP}. Möglicher "
                           f"Daily-Run-/KI-Agent-Drift — neuer Tick fällig"),
            })

    # === S9 (crit/warn) — HTML-Sanity-Check (Frontend-Awareness Phase 1a) ==
    # Liest den gerenderten ``index.html`` und prüft 4 deterministische
    # Klassen-Counts (article, card-cockpit, cockpit-price, cockpit-pillar).
    # Fängt stille DOM-Degradation durch Selektor-Mismatch (PR #199/226/235-
    # Bugklasse). Phase 1a: nur Top-Counts; Pro-Card-Assertions kommen in
    # Phase 1b.
    #
    # Fail-soft: jede Exception im Check selbst (Import, File-Read, Parse)
    # wird zu WARN — ein Bug im S9-Check darf NIE den Daily-Run blockieren.
    # Im ki_agent-Tick wird S9 NICHT ausgeführt (KI-Tick rendert kein HTML).
    if not ki_agent_only and html_path:
        try:
            from scripts.check_html_assertions import evaluate_html_assertions
            with open(html_path, "r", encoding="utf-8") as _fh:
                _html = _fh.read()
            _html_fails = evaluate_html_assertions(_html)
            if _html_fails:
                _worst = "crit" if any(f.get("severity") == "crit"
                                       for f in _html_fails) else "warn"
                _first = _html_fails[0].get("detail", "?")
                fails.append({
                    "id":       "S9",
                    "severity": _worst,
                    "detail":   (f"HTML-Sanity: {len(_html_fails)} Fail(s). "
                                 f"Erster: {_first}"),
                })
        except Exception as _s9_exc:
            fails.append({
                "id":       "S9",
                "severity": "warn",
                "detail":   (f"S9-Check selbst fehlgeschlagen: "
                             f"{_s9_exc!r}"),
            })

    # === S10 (warn/crit) — Daten-Integritäts-Check (Phase 1, additiv) ======
    # Erkennt MUSS-Felder die dauerhaft null bleiben (hist_5d-Bug-Klasse —
    # 3 Trend-Felder zu 100 % null seit PR #142, eine Woche unbemerkt) und
    # LAG-Felder die nach ihrem Trading-Tag-Lag immer noch kein Outcome
    # haben (rolling-Update-Bug-Klasse).
    #
    # WARN-Tier, KEIN Push-Block (anders als S9). Daily-Digest aggregiert
    # 3-in-Folge wie bei S1-S7. Fail-soft via try/except — ein Bug im
    # S10-Check selbst darf den Daily-Run NIE blockieren. Im ki_agent-Tick
    # wird S10 NICHT ausgeführt (rendert keine Backtest-Daten neu).
    if not ki_agent_only:
        try:
            _s10_fails = evaluate_s10_data_integrity()
            fails.extend(_s10_fails)
        except Exception as _s10_exc:
            fails.append({
                "id":       "S10",
                "severity": "warn",
                "detail":   (f"S10-Check selbst fehlgeschlagen: "
                             f"{_s10_exc!r}"),
            })

    # === S13 (warn, Status-Reporter) — Daten-Reife-Gate 30.06. =============
    # Meldet „laufend" (log.info) die Reife der drei 30.06.-Stichproben
    # (Setup-Edge ≥70/schema_v4, Entry-AUC, CTB-Edge) PLUS den Konsistenz-
    # Wächter (Projekt C): Soll vs. Ist je config-Konstante aus
    # CONSISTENCY_EXPECTED_STATE. Warnt NUR bei Soll-Ist-Drift (ein warn pro
    # driftendem Wert). Rein lesend, kein Score-/Filter-Touch. Status-Zeilen
    # sind IMMER da (auch ohne Fail). Fail-soft + nur Daily-Run (analog S10).
    if not ki_agent_only:
        try:
            _drg = evaluate_data_maturity_gate()
            for _line in _drg["status_lines"]:
                log.info("[Daten-Reife 30.06.] %s", _line)
            fails.extend(_drg["fails"])
        except Exception as _s13_exc:
            fails.append({
                "id":       "S13",
                "severity": "warn",
                "detail":   (f"S13-Gate selbst fehlgeschlagen: "
                             f"{_s13_exc!r}"),
            })

    # === S8 (warn) — Digest-Push-Pipeline frisch ===========================
    # Erkennt silent Digest-Fails (15.05.2026: ntfy-Send fehlgeschlagen,
    # Workflow lief grün durch, kein Push). Wenn last_digest_sent älter
    # als HEALTH_CHECK_S8_MAX_AGE_HOURS (26 h) ist, wurde mindestens ein
    # geplanter Slot verpasst. None = noch nie erfolgreich → übersprungen
    # (keine false positives beim Erstaufsetzen).
    now_for_s8 = now_utc or datetime.now(timezone.utc)
    age_h = _digest_age_hours(now_for_s8)
    if age_h is not None and age_h > HEALTH_CHECK_S8_MAX_AGE_HOURS:
        fails.append({
            "id": "S8", "severity": "warn",
            "detail": (f"kein erfolgreicher Digest-Push seit "
                       f"{age_h:.1f} h (Schwelle "
                       f"{HEALTH_CHECK_S8_MAX_AGE_HOURS} h) — "
                       f"silent ntfy-Fail oder Cron-Drop"),
        })

    # === S14 (warn) — Gist-Pull-Liveness (Composite) =======================
    # Fängt die Stille-Tod-Klasse vom 02.06.2026: ein toter GIST_TOKEN ließ
    # den Gist-Read über Tage scheitern, der Recovery-Fallback überbrückte
    # still (Geister-Positionen → Geister-Exit-Pushes). Der Marker
    # last_successful_gist_pull (gist_pull_state.json) wird NUR im HTTP-Gist-
    # Erfolgszweig geschrieben (#310) → er altert genau bei anhaltendem
    # Gist-Read-Fehler. COMPOSITE-LIVENESS: S14 altert auch bei mehrtägigem
    # ki_agent-/daily-Cron-Drop (andere Fehlerklasse) — der Detail-Text sagt
    # daher „Gist-Pull seit N h nicht erfolgreich", NICHT „Token tot".
    # None = Datei fehlt (vor erstem Pull) / Feld null/unparsebar → SKIP
    # (kein false-positive beim Erstaufsetzen, exakt analog S8). Läuft in
    # BEIDEN Pfaden (ungated wie S8): im ki_agent-Tick liest der Hook den
    # nicht-aktualisierten alten Working-Tree-Marker → ~1 h Detektionslatenz
    # statt ~1 Tag (daily-only). NICHT abgedeckt (bewusst, separater PR):
    # Body-Korruption (HTTP-200 + kaputtes squeeze_data.json → Marker
    # fälschlich frisch) — andere Fehlerklasse, _extract_data unberührt.
    gist_age_h = _gist_pull_age_hours(now_for_s8)
    if gist_age_h is not None and gist_age_h > HEALTH_CHECK_S14_MAX_AGE_HOURS:
        fails.append({
            "id": "S14", "severity": "warn",
            "detail": (f"kein erfolgreicher Gist-Pull seit "
                       f"{gist_age_h:.1f} h (Schwelle "
                       f"{HEALTH_CHECK_S14_MAX_AGE_HOURS} h) — "
                       f"Token-Tod oder mehrtägiger Workflow-Ausfall "
                       f"(Composite-Liveness)"),
        })

    # === S11 (warn) — premarket-Sammel-Frequenz ============================
    # Erkennt stillen Tod der premarket-Sammlung: wenn mehrere Werktage
    # ohne echten premarket-Run vergangen sind. „Echter premarket-Run" =
    # ``run_phase == 'premarket' AND trading_session_phase == 'premarket'``
    # (gedriftete Crons mit tsp=open/midday zählen nicht als premarket).
    # Quelle: score_inflation_log.jsonl. ``date`` in backtest_history ist
    # KEIN Beweis (s. Diagnose 28.05.2026 — Manual-Frühdispatch um 02:53Z).
    # None = Datei/Match fehlt → SKIP (kein false-positive beim Erstaufsetzen,
    # analog S8). Nur im Daily-Run-Pfad sinnvoll (analog S5).
    if not ki_agent_only:
        s11_age_wd = _last_phase_run_age_workdays(
            "premarket", "premarket", now_for_s8)
        if (s11_age_wd is not None
                and s11_age_wd > HEALTH_CHECK_S11_MAX_WORKDAYS_NO_PREMARKET):
            fails.append({
                "id": "S11", "severity": "warn",
                "detail": (f"kein echter premarket-Run "
                           f"(run_phase==tsp=='premarket') seit "
                           f"{s11_age_wd} Werktagen (Schwelle "
                           f"{HEALTH_CHECK_S11_MAX_WORKDAYS_NO_PREMARKET}) — "
                           f"Cron-Drift/-Drop oder Sammlung gestorben"),
            })

    # === S12 (crit, NUR-REPORTING) — postclose-Sammel-Frequenz =============
    # Analog S11 für postclose. ``severity='crit'`` wegen Datenverlust-
    # Risiko: jeder gedroppte postclose = permanent verlorener Backtest-
    # EOD-Snapshot (s. Diagnose 28.05.2026: 27.05.-21:17-Cron-Drop hat
    # einen 27.05.-EOD-Append irreversibel zerstört, kein Backfill-Pfad).
    #
    # EXIT-SCHUTZ — KRITISCH: der einzige blockierende ``sys.exit``-Pfad
    # in ``generate_report.py:16128–16131`` filtert EXPLIZIT auf
    # ``id == "S9"``:
    #   ``any(f.get("id") == "S9" and f.get("severity") == "crit" ...)``
    # S12 mit ``id='S12'`` wird strukturell NICHT in den Block-Pfad
    # aufgenommen — egal mit welcher severity. Diese Architektur ist die
    # kanonische Trennung; S1/S2/S3 (ebenfalls crit) blockieren aus dem
    # gleichen Grund nicht. Beim Refactor des Exit-Pfads das
    # ``id == "S9"``-Filter UNBEDINGT beibehalten oder explizit eine
    # id-Whitelist einführen (z. B. ``id in {"S9"}``) — niemals auf
    # ``severity == "crit"`` allein umstellen, sonst würde S12 plötzlich
    # blockieren und ein fehlender postclose würde künftige Runs anhalten.
    if not ki_agent_only:
        s12_age_wd = _last_phase_run_age_workdays(
            "postclose", "postclose", now_for_s8)
        if (s12_age_wd is not None
                and s12_age_wd > HEALTH_CHECK_S12_MAX_WORKDAYS_NO_POSTCLOSE):
            fails.append({
                "id": "S12", "severity": "crit",
                "detail": (f"kein echter postclose-Run "
                           f"(run_phase==tsp=='postclose') seit "
                           f"{s12_age_wd} Werktagen (Schwelle "
                           f"{HEALTH_CHECK_S12_MAX_WORKDAYS_NO_POSTCLOSE}) — "
                           f"Backtest-EOD-Append fehlt; jeder gedroppte "
                           f"postclose ist permanenter Datenverlust"),
            })

    return fails


# ── Persistenz ─────────────────────────────────────────────────────────────


def record_run(state_fails: list[dict],
               run_phase: str,
               run_ts: datetime | None = None,
               path: str = LOG_FILE) -> bool:
    """Append-only-Eintrag in ``health_check_log.jsonl``.

    Schema: ``{run_ts, run_phase, schema_v, state_fails, provider_fails}``.
    ``provider_fails`` ist in Phase 1 immer ``[]`` (Phase 2 füllt das).

    Fail-soft: Schreibfehler werden geloggt, nicht re-raised — der
    Daily-Run darf nie wegen Health-Check-Logging crashen.

    Returnt ``True`` bei erfolgreichem Write, ``False`` bei Fehler.
    """
    if run_ts is None:
        run_ts = datetime.now(timezone.utc)
    entry = {
        "run_ts":         run_ts.astimezone(timezone.utc)
                                .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_phase":      run_phase,
        "schema_v":       SCHEMA_V,
        "state_fails":    list(state_fails or []),
        "provider_fails": [],
    }
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        log.info("health_check: %d state-fail(s) für run_phase=%s persistiert",
                 len(entry["state_fails"]), run_phase)
        return True
    except OSError as exc:
        log.warning("health_check: Schreibfehler an %s — übersprungen: %s",
                    path, exc)
        return False


def prune_log(max_days: int = HEALTH_CHECK_CUTOFF_DAYS,
              path: str = LOG_FILE) -> int:
    """Entfernt Einträge älter als ``max_days`` Tage.

    Atomic ``tmp + os.replace``. Kaputte JSONL-Zeilen bleiben erhalten
    (analog ``score_inflation_log.prune_log``) — keine stillen Daten-
    verluste durch Parse-Bugs.

    Returnt Anzahl entfernter Zeilen (0 bei Fehler oder leerer Diff).
    """
    if not os.path.exists(path):
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    kept: list[str] = []
    n_seen = 0
    n_bad = 0
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
                    if ts_str.endswith("Z"):
                        ts_str = ts_str[:-1] + "+00:00"
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    n_bad += 1
                    log.warning("health_check: kaputte Zeile übersprungen "
                                "(behält sie bis Manual-Cleanup): %s", exc)
                    kept.append(line)
                    continue
                if ts >= cutoff:
                    kept.append(line)
    except OSError as exc:
        log.warning("health_check: Prune-Read-Fehler — übersprungen: %s", exc)
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
        log.warning("health_check: Prune-Write-Fehler — Datei unverändert: %s", exc)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return 0
    log.info("health_check: %d Einträge (älter als %d Tage) geprunt",
             n_removed, max_days)
    return n_removed


def read_all(path: str = LOG_FILE) -> list[dict]:
    """Diagnose-Helper: alle Einträge als Liste. Kaputte Zeilen geskippt."""
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


# ── High-Level-Aufrufer (für Hook-Points) ──────────────────────────────────


def run_and_record(*,
                   run_phase: str,
                   ki_agent_only: bool = False,
                   run_ts: datetime | None = None,
                   path: str = LOG_FILE,
                   **invariant_kwargs: Any) -> list[dict]:
    """Convenience-Wrapper für Hook-Points.

    Ruft ``evaluate_state_invariants`` und ``record_run`` in einem
    fail-soft-Block. Try/except umschließt beide Aufrufe — kein
    Daily-Run darf wegen Health-Check crashen. Returnt die Liste der
    state_fails (leer bei Exception).
    """
    try:
        fails = evaluate_state_invariants(
            run_phase=run_phase,
            ki_agent_only=ki_agent_only,
            **invariant_kwargs,
        )
    except Exception as exc:
        log.warning("health_check: evaluate_state_invariants crashte — "
                    "Daily-Run läuft weiter: %s", exc)
        return []
    try:
        prune_log(path=path)
    except Exception as exc:
        log.debug("health_check: prune_log fehlgeschlagen: %s", exc)
    record_run(fails, run_phase=run_phase, run_ts=run_ts, path=path)
    return fails


# ── Provider-Health (Phase 2) ──────────────────────────────────────────────


def record_provider_call(provider: str,
                         tier: int,
                         latency_ms: int,
                         http_status: int | None,
                         item_count: int,
                         error: str | None = None,
                         coverage_pct: float | None = None,
                         nan_pct: float | None = None,
                         run_phase: str = "premarket",
                         run_ts: datetime | None = None,
                         path: str = LOG_FILE_PROVIDER) -> bool:
    """Append-only-Eintrag pro Provider-Call in ``provider_health.jsonl``.

    Schema gemäß Spec ``docs/health_check_spec.md`` Z. 86–101:
    ``{run_ts, run_phase, provider, tier, http_status, latency_ms,
       item_count, coverage_pct, nan_pct, error, schema_v}``.

    Fail-soft: Schreibfehler werden geloggt, nicht re-raised — kein
    Daily-Run/KI-Agent-Crash wegen Health-Check-Logging.

    Returnt ``True`` bei erfolgreichem Write, ``False`` bei Fehler.
    """
    if run_ts is None:
        run_ts = datetime.now(timezone.utc)
    entry = {
        "run_ts":       run_ts.astimezone(timezone.utc)
                              .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_phase":    run_phase,
        "provider":     provider,
        "tier":         int(tier),
        "http_status":  http_status,
        "latency_ms":   int(latency_ms) if latency_ms is not None else None,
        "item_count":   int(item_count) if item_count is not None else 0,
        "coverage_pct": coverage_pct,
        "nan_pct":      nan_pct,
        "error":        error,
        "schema_v":     SCHEMA_V_PROVIDER,
    }
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        log.debug("provider_health: %s tier=%d items=%d latency=%dms",
                  provider, tier, entry["item_count"], entry["latency_ms"] or 0)
        return True
    except OSError as exc:
        log.warning("provider_health: Schreibfehler an %s — übersprungen: %s",
                    path, exc)
        return False


def prune_provider_log(max_days: int = HEALTH_CHECK_CUTOFF_DAYS,
                       path: str = LOG_FILE_PROVIDER) -> int:
    """Entfernt Einträge älter als ``max_days`` Tage. Analog ``prune_log``:
    atomic ``tmp + os.replace``, kaputte Zeilen bleiben erhalten.

    Returnt Anzahl entfernter Zeilen (0 bei Fehler oder leerer Diff).
    """
    if not os.path.exists(path):
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    kept: list[str] = []
    n_seen = 0
    n_bad = 0
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
                    if ts_str.endswith("Z"):
                        ts_str = ts_str[:-1] + "+00:00"
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    n_bad += 1
                    log.warning("provider_health: kaputte Zeile übersprungen "
                                "(behält sie bis Manual-Cleanup): %s", exc)
                    kept.append(line)
                    continue
                if ts >= cutoff:
                    kept.append(line)
    except OSError as exc:
        log.warning("provider_health: Prune-Read-Fehler — übersprungen: %s", exc)
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
        log.warning("provider_health: Prune-Write-Fehler — Datei unverändert: %s",
                    exc)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return 0
    log.info("provider_health: %d Einträge (älter als %d Tage) geprunt",
             n_removed, max_days)
    return n_removed


def read_all_provider(path: str = LOG_FILE_PROVIDER) -> list[dict]:
    """Diagnose-Helper: alle Provider-Einträge als Liste. Kaputte Zeilen
    geskippt (kein Crash). Für CLI-Diagnose und Tests."""
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


# ── Per-Call-Akkumulator-Pattern (extrahiert aus PR 2, generalisiert PR 3) ─
#
# Wird von Tier-2/3-Providern genutzt, die N-mal pro Run aufgerufen werden
# (Finnhub, Stockanalysis, StockTwits, UOA, News-RSS, EDGAR-pro-Ticker).
# main() emittiert am Ende eine konsolidierte Zeile pro Provider, sofern
# der Akkumulator ``calls > 0`` zeigt (call_attempted-Gating).


def provider_acct_reset(acct: dict) -> None:
    """Setzt Akkumulator-Felder zurück. Aufruf in main()-Start für
    saubere Test-Wiederholbarkeit."""
    for k in ("latency_ms", "calls", "failures", "successes"):
        if k in acct:
            acct[k] = 0
    # Variante E (19.05.2026): first-fail-wins-Repr für Aggregator-
    # Emit-Sites. Beim Reset auf None setzen damit der nächste Run
    # einen frischen Fail-String sehen kann.
    acct["last_error_repr"] = None


def provider_acct_record(acct: dict, latency_ms: int, success: bool,
                          last_error_repr: str | None = None) -> None:
    """Akkumuliert per-Call-Metriken. Wird aus dem ``finally``-Block
    von ``instrument_provider_call`` aufgerufen.

    ``last_error_repr`` (Variante E, 19.05.2026): optionale Exception-
    Repräsentation des ersten Fails im Akkumulations-Fenster. Wird nur
    gesetzt wenn der bestehende Wert ``None`` ist (first-fail-wins —
    spätere Fails überschreiben nicht, sonst maskieren transient-
    Probleme den Wurzel-Fehler). Emit-Sites verwenden den String als
    informativeren Ersatz für die ``N/M calls failed``-Aggregat-Zeile.
    """
    acct["latency_ms"] += int(latency_ms)
    acct["calls"]      += 1
    if success:
        acct["successes"] += 1
    else:
        acct["failures"] += 1
    if last_error_repr and not acct.get("last_error_repr"):
        acct["last_error_repr"] = last_error_repr


def instrument_provider_call(acct: dict, fn, *args,
                              success_check=None, **kwargs):
    """Wrapper-Helper: misst Latency + Success-Bool, akkumuliert in
    ``acct`` und propagiert Exceptions. Pattern: try/except/raise/finally.

    ``success_check`` ist optional. Erwartet eine Funktion
    ``(result) -> bool``. Bei None wird die Default-Heuristik genutzt:
    Erfolg = nicht raised AND ``result is not None`` AND (für dict/list/
    tuple/set: ``len(result) > 0``; sonst: truthiness von result).

    Für Tier-3-Provider, deren fail-soft-Returns dieselbe Struktur wie
    Erfolgs-Returns haben (z. B. StockTwits-Dict mit allen Werten None,
    UOA-Tuple ``(0, [], {})``, SEC-Tuple ``(False, "", None)``),
    sollte ein expliziter ``success_check`` mitgegeben werden — sonst
    wertet der Wrapper jeden Call als erfolgreich.
    """
    t0 = time.perf_counter()
    result = None
    raised = False
    exc_obj: BaseException | None = None
    try:
        result = fn(*args, **kwargs)
        return result
    except Exception as _exc:
        raised = True
        exc_obj = _exc
        raise
    finally:
        try:
            if raised:
                ok = False
            elif success_check is not None:
                try:
                    ok = bool(success_check(result))
                except Exception:
                    ok = False
            else:
                ok = (result is not None) and (
                    result if not isinstance(result, (dict, list, tuple, set))
                    else len(result) > 0
                )
            # Variante E (19.05.2026): bei Exception einen kompakten Repr
            # für die Aggregator-Emit-Site bauen. Bei requests.HTTPError
            # zusätzlich den HTTP-Status anhängen. Greift NICHT für
            # Fetcher, die Exceptions intern catchen und None returnen —
            # dort sieht der Wrapper kein Exception-Objekt.
            _last_err = None
            if exc_obj is not None:
                _base = f"{type(exc_obj).__name__}: {str(exc_obj)[:120]}"
                _resp = getattr(exc_obj, "response", None)
                _status = (getattr(_resp, "status_code", None)
                           if _resp is not None else None)
                _last_err = (f"{_base} [HTTP {_status}]"
                             if _status is not None else _base)
            provider_acct_record(
                acct,
                int((time.perf_counter() - t0) * 1000),
                success=bool(ok),
                last_error_repr=_last_err,
            )
        except Exception:
            pass   # Accumulator-Fehler bricht Pipeline nicht


# ── Phase 3: Digest-Aggregation (Tool-Helper, kein Laufzeit-Hook) ──────────
#
# Diese Funktionen sind pure und werden vom Digest-Workflow
# (scripts/health_check_digest.py) aufgerufen. Trennen Aggregations-
# Logik (testbar Pythonisch) von I/O + ntfy-Send (Skript-Level).
#
# Konsekutiv-Counter laut User-Klärung 15.05.2026: separate State-
# Datei ``health_check_digest_state.json`` (statt
# ``agent_state.json["provider_health_state"]``), damit ki_agent +
# Daily-Run keinen Race auf den Counter haben.


# Provider-Schwellen für Coverage-basierte Fails (Spec Z. 124).
DIGEST_COVERAGE_THRESHOLD_TIER1 = 80.0   # < 80 % → fail sofort
DIGEST_COVERAGE_THRESHOLD_TIER23 = 50.0  # < 50 % → fail (+ consecutive für T2/T3)
DIGEST_CONSECUTIVE_THRESHOLD = 3         # 3-in-Folge für Tier 2/3
DIGEST_STALE_DAYS = 7                    # Counter-Reset nach 7 d Inaktivität


def aggregate_state_fails(entries: list[dict]) -> list[dict]:
    """Aggregiert State-Fails über ein Zeitfenster von Einträgen.

    Pro State-Invariant (S1–S7) wird die Maximal-Severity gemeldet,
    plus die Anzahl Vorkommnisse im Fenster. Bei mehrfachen Treffern
    desselben Invariants wird der jüngste detail-String genutzt
    (Spec: „X Runs in Folge" sichtbar via count).

    Returnt Liste von Fail-Dicts in stabiler Reihenfolge (S1 → S7).
    """
    by_id: dict[str, dict] = {}
    for e in entries or []:
        for f in (e.get("state_fails") or []):
            fid = f.get("id")
            if not fid:
                continue
            sev = f.get("severity", "warn")
            cur = by_id.get(fid)
            if cur is None:
                by_id[fid] = {
                    "id":       fid,
                    "severity": sev,
                    "detail":   f.get("detail", ""),
                    "count":    1,
                }
            else:
                # crit überschreibt warn
                if sev == "crit" and cur["severity"] != "crit":
                    cur["severity"] = "crit"
                cur["detail"] = f.get("detail", cur["detail"])  # jüngster
                cur["count"]  += 1
    # Stabile Reihenfolge S1 → S7
    return sorted(by_id.values(), key=lambda f: f["id"])


def aggregate_provider_fails(entries: list[dict],
                              counters: dict | None = None,
                              tier_map: dict | None = None,
                              now_ts: datetime | None = None,
                              ) -> list[dict]:
    """Aggregiert Provider-Fails + verwaltet Konsekutiv-Counter.

    Pro Provider werden die Einträge des 24-h-Fensters chronologisch
    durchgegangen. ``counters`` ist das Dict aus
    ``health_check_digest_state.json["consecutive_failures"]`` —
    wird in-place mutiert.

    Trigger-Bedingungen pro Tier (Spec Z. 124):
      - Tier 1: ``http_status != 200`` ODER ``coverage_pct < 80``
                → sofort, kein Counter-Increment nötig
      - Tier 2/3: gleiche Bedingung, aber erst ab
                  ``DIGEST_CONSECUTIVE_THRESHOLD`` Konsekutiv-Fails

    Ein erfolgreicher Run (http_status=200 UND coverage≥50/80) reset
    den Counter auf 0. Provider, die im Fenster gar nicht erschienen
    sind, behalten ihren Counter bis ``DIGEST_STALE_DAYS`` Tage —
    danach wird er auf 0 gesetzt (z. B. Provider deaktiviert).

    Returnt Liste von Fail-Dicts in stabiler Reihenfolge (alphabetisch
    nach Provider-Key).
    """
    counters  = counters if counters is not None else {}
    tier_map  = tier_map or {}
    now_ts    = now_ts or datetime.now(timezone.utc)
    consecutive = counters.setdefault("consecutive_failures", {})
    last_seen   = counters.setdefault("last_seen", {})

    # Gruppieren chronologisch pro Provider
    by_provider: dict[str, list[dict]] = {}
    for e in entries or []:
        prov = e.get("provider")
        if not prov:
            continue
        by_provider.setdefault(prov, []).append(e)

    fails: list[dict] = []
    for prov, rows in by_provider.items():
        rows.sort(key=lambda r: r.get("run_ts", ""))
        tier = int(tier_map.get(prov, rows[-1].get("tier", 3)))
        last_seen[prov] = rows[-1].get("run_ts", now_ts.strftime("%Y-%m-%dT%H:%M:%SZ"))
        for row in rows:
            http_ok = row.get("http_status") == 200
            cov     = row.get("coverage_pct")
            cov_threshold = (DIGEST_COVERAGE_THRESHOLD_TIER1 if tier == 1
                             else DIGEST_COVERAGE_THRESHOLD_TIER23)
            cov_fail = (cov is not None) and (cov < cov_threshold)
            row_fail = (not http_ok) or cov_fail
            if row_fail:
                consecutive[prov] = consecutive.get(prov, 0) + 1
            else:
                consecutive[prov] = 0

        n_consec = consecutive.get(prov, 0)
        if n_consec <= 0:
            continue
        last_row = rows[-1]
        reason   = (last_row.get("error")
                    or (f"coverage {last_row.get('coverage_pct')}%"
                        if last_row.get("coverage_pct") is not None
                           and last_row["coverage_pct"] < (
                               DIGEST_COVERAGE_THRESHOLD_TIER1 if tier == 1
                               else DIGEST_COVERAGE_THRESHOLD_TIER23
                           )
                        else f"HTTP {last_row.get('http_status')}"))
        if tier == 1:
            severity = "crit"
            fails.append({
                "provider":    prov,
                "tier":        tier,
                "severity":    severity,
                "reason":      reason,
                "consecutive": n_consec,
            })
        elif n_consec >= DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES.get(
                prov, DIGEST_CONSECUTIVE_THRESHOLD):
            severity = "warn"
            fails.append({
                "provider":    prov,
                "tier":        tier,
                "severity":    severity,
                "reason":      reason,
                "consecutive": n_consec,
            })

    # Stale-Counter-Reset (Drift-Schutz): Provider, die seit > N Tagen
    # nicht erschienen sind, bekommen Counter auf 0 (z. B. ENABLED=False
    # für stockanalysis dauerhaft → Counter sollte nicht ewig stale bleiben).
    cutoff = now_ts - timedelta(days=DIGEST_STALE_DAYS)
    for prov in list(consecutive.keys()):
        seen = last_seen.get(prov)
        if not seen:
            continue
        try:
            ts_str = seen[:-1] + "+00:00" if seen.endswith("Z") else seen
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if ts < cutoff:
            consecutive[prov] = 0

    return sorted(fails, key=lambda f: f["provider"])


def _parse_ts(s: str) -> datetime | None:
    """ISO-UTC-String → aware datetime, oder None bei Parse-Fehler."""
    if not s:
        return None
    try:
        ts_str = s[:-1] + "+00:00" if s.endswith("Z") else s
        ts = datetime.fromisoformat(ts_str)
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def provider_liveness(entries: list[dict],
                      tier_map: dict | None = None,
                      config_flags: dict | None = None,
                      now_ts: datetime | None = None) -> dict:
    """Pro Provider-Key: ``"live"`` | ``"stale"`` | ``"disabled"`` — für die
    dynamische Datenquellen-Anzeige (REIN ANZEIGE, kein Score-Effekt).

    Nutzt dieselbe row_fail-/Konsekutiv-/Stale-Logik wie
    ``aggregate_provider_fails`` (DIGEST_CONSECUTIVE_THRESHOLD,
    DIGEST_STALE_DAYS, Coverage-Schwellen) — KEINE neue Diskriminator-Logik:

      - ``disabled``: ``config_flags[key]`` ist explizit ``False`` (ENABLED-
        Flag aus, z. B. stocktwits/earningswhispers — schreiben keine Zeile,
        dürfen NICHT als „tot" gelten). Hat Vorrang vor allem anderen.
      - ``stale``: Provider hat ≥ Schwelle Konsekutiv-Fails (Tier 2/3) bzw.
        einen Fail (Tier 1) im jüngsten Lauf-Lauf, ODER ist seit
        > DIGEST_STALE_DAYS gar nicht mehr erschienen (kein Log, aber Flag
        nicht aus → echtes Verstummen statt bewusst-aus).
      - ``live``: jüngster Lauf erfolgreich (http 200 + coverage ok).

    Provider ohne Telemetrie-Einträge UND ohne disabled-Flag → ``stale``
    (verstummt). Anti-Flacker: ein 1-Lauf-Hiccup hebt den Konsekutiv-Counter
    nicht über die Schwelle → bleibt ``live``.

    ``config_flags``: ``{provider_key: bool}`` (True=an, False=aus). Fehlt ein
    Key → kein Gate (behandelt wie nicht abschaltbar).
    """
    tier_map = tier_map or {}
    config_flags = config_flags or {}
    now_ts = now_ts or datetime.now(timezone.utc)
    cutoff = now_ts - timedelta(days=DIGEST_STALE_DAYS)

    by_provider: dict[str, list[dict]] = {}
    for e in entries or []:
        prov = e.get("provider")
        if not prov:
            continue
        by_provider.setdefault(prov, []).append(e)

    out: dict[str, str] = {}
    # Union aus Telemetrie-Keys + Flag-Keys + Tier-Map-Keys, damit auch
    # nie-geloggte (disabled) Provider einen Status bekommen.
    all_keys = set(by_provider) | set(config_flags) | set(tier_map)
    for prov in all_keys:
        # 1) disabled hat Vorrang — config-Flag explizit False.
        if config_flags.get(prov) is False:
            out[prov] = "disabled"
            continue
        rows = by_provider.get(prov)
        if not rows:
            # Kein Log + nicht disabled → verstummt.
            out[prov] = "stale"
            continue
        rows.sort(key=lambda r: r.get("run_ts", ""))
        tier = int(tier_map.get(prov, rows[-1].get("tier", 3)))
        # Letzter Eintrag zu alt (> Stale-Tage) → verstummt.
        last_ts = _parse_ts(rows[-1].get("run_ts", ""))
        if last_ts is not None and last_ts < cutoff:
            out[prov] = "stale"
            continue
        # Konsekutiv-Fail-Zähler (identische row_fail-Definition wie
        # aggregate_provider_fails) über die jüngsten Läufe.
        cov_threshold = (DIGEST_COVERAGE_THRESHOLD_TIER1 if tier == 1
                         else DIGEST_COVERAGE_THRESHOLD_TIER23)
        n_consec = 0
        for row in rows:
            cov = row.get("coverage_pct")
            cov_fail = (cov is not None) and (cov < cov_threshold)
            row_fail = (row.get("http_status") != 200) or cov_fail
            n_consec = n_consec + 1 if row_fail else 0
        threshold = (1 if tier == 1
                     else DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES.get(
                         prov, DIGEST_CONSECUTIVE_THRESHOLD))
        out[prov] = "stale" if n_consec >= threshold else "live"
    return out


def format_digest_body(state_fails: list[dict],
                       provider_fails: list[dict],
                       *,
                       n_runs: int,
                       last_run_iso: str | None,
                       digest_date: str) -> tuple[str, str, str, str | None]:
    """Komponiert den ntfy-Body laut Spec Z. 175–211.

    Returnt ``(body, title, priority, tags)``.

    Drei Klassen:
      - „📭 Health-Check ohne Daten"  (leere JSONL → Frischbild oder
                                       Run-Ausfall) — high
      - „⚠️ Health-Check-Digest"      (≥ 1 crit ODER ≥ 3 warn) — high
      - „✅ Health-Check OK"          (sonst) — default
    """
    if n_runs == 0:
        body = (
            f"📭 Health-Check ohne Daten {digest_date}\n"
            f"0 Runs in den letzten 24h gefunden. Daily-Run oder "
            f"ki_agent liefen nicht — JSONL-Files leer."
        )
        return body, "📭 Health-Check ohne Daten", "high", "warning"

    n_crit = sum(1 for f in state_fails if f["severity"] == "crit")
    n_crit += sum(1 for f in provider_fails if f["severity"] == "crit")
    n_warn = sum(1 for f in state_fails if f["severity"] == "warn")
    n_warn += sum(1 for f in provider_fails if f["severity"] == "warn")

    fails_present = (n_crit >= 1) or (n_warn >= 3)

    if not fails_present:
        body = (
            f"✅ Health-Check OK {digest_date}\n"
            f"24h ohne Fails. {n_runs} Runs geprüft (Daily-Run + ki_agent).\n"
            f"Letzter Run: {last_run_iso or '—'}"
        )
        return body, "✅ Health-Check OK", "default", None

    n_ok = max(0, n_runs - n_crit - n_warn)
    lines = [
        f"⚠️ Health-Check-Digest {digest_date}",
        f"🔴 {n_crit} crit · 🟡 {n_warn} warn · ✅ {n_ok} ok",
        "",
    ]
    if state_fails:
        lines.append("State-Fails:")
        for f in state_fails:
            tail = (f" ({f['count']} Runs in Folge)"
                    if f.get("count", 1) > 1 else "")
            lines.append(f"  • {f['id']}: {f.get('detail','')}{tail}")
        lines.append("")
    if provider_fails:
        lines.append("Provider-Fails:")
        for f in provider_fails:
            tail = (f" ({f['consecutive']} Runs in Folge)"
                    if f.get("consecutive", 0) > 1 else "")
            lines.append(f"  • {f['provider']} (Tier {f['tier']}): "
                         f"{f.get('reason','')}{tail}")
        lines.append("")
    lines.append(f"Letzter erfolgreicher Run: {last_run_iso or '—'}")
    body = "\n".join(lines).rstrip() + "\n"
    return body, "⚠️ Health-Check-Digest", "high", "warning"
