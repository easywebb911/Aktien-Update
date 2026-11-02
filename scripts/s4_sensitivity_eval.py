#!/usr/bin/env python3
"""§4-Exit-B.1 — vorab registrierte Sensitivitätsprüfung (Postclose-Halbzeile).

Registriert am 02.11.2026 VOR jedem Ergebnis (Zählerstand n=242/250, keine
``eval_results.jsonl`` vorhanden) — siehe SESSION_HANDOVER.md,
„§4-Protokolleintrag 02.11.2026 — Sensitivitätsprüfung“. Dieses Skript ist
der festgeschriebene RECHENWEG dazu. Es ist ein reines Lese-/Rechenskript:

  * ändert ``scripts/freeze_eval.py`` NICHT und ruft dessen eingefrorene
    Funktion ``evaluate_exit_b1_family`` unverändert auf (gleiche
    Population-Bedingung, gleiche Kriterien, gleicher Bootstrap-Seed),
  * entfernt vorher NUR die Records, deren Entry-Tag ein betroffener
    Lauf-Tag ist (Kriterium K1/K2 unten),
  * schreibt NICHT in ``eval_results.jsonl`` (das gehört dem Auto-Lauf),
    sondern — nur mit ``--write`` — in die eigene Datei
    ``eval_results_sensitivity.jsonl``.

Ohne ``--write`` wird nur auf stdout ausgegeben. Das Skript läuft NICHT
automatisch (kein Workflow, kein Auto-Lauf-Hook); es wird erst NACH dem
Hauptergebnis bewusst ausgeführt.

Kriterium „betroffener Lauf-Tag“ (Entry-Tag = ``date``-Feld des Records =
US/Eastern-Handelstag des Postclose-Laufs, ``report_date`` in
``generate_report.py``):

  K1 (ab Entry-Tag 01.10.2026, Quelle ``hist_5d_gap_log.jsonl``):
     Anzahl VERSCHIEDENER Ticker mit ``reason == "nonfinite_cell"``,
     ``"Close"`` in ``missing_cells`` und ``dropped_day`` == Entry-Tag, in
     Läufen, deren ``run_ts`` in US/Eastern um/nach 16:00 des Entry-Tags
     liegt (Postclose) — betroffen bei ``>= K1_MIN_TICKERS`` (20).
  K2 (Entry-Tage 15.07.2026 bis einschließlich 30.09.2026 — vor dem Gap-Log;
     der früheste §4-Record ist vom 21.07.2026 — Quelle
     ``backtest_history.json``, Schema v4, bei gekürzten Tagen der Git-
     Stand der Datei): Anteil der Records des Tages mit
     ``vol_stability_5d is None`` — betroffen bei ``>= K2_MIN_SHARE`` (0.8).
     (Vor 15.07. bewusst nicht angewandt: 14.–20.05.2026 wären K2-Treffer,
     aber nur weil das Feld damals neu war — und dort liegt kein §4-Record.)

Für Entry-Tage bis einschließlich ``FROZEN_UNTIL`` (30.10.2026) ist die
daraus am 02.11.2026 abgeleitete Liste ``EXCLUDED_DAYS_FROZEN`` bindend
(die Quell-Logs werden gekürzt: Gap-Log 30 Tage, Backtest 90 Tage). Für
spätere Entry-Tage gilt K1 auf dem Gap-Log zum Auswertungszeitpunkt; ist
ein solcher Tag dort nicht mehr prüfbar (älter als
``GAP_LOG_CUTOFF_DAYS - 1`` Tage), bricht das Skript mit „nicht prüfbar“
ab, statt den Tag still einzuschließen.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

ET = ZoneInfo("America/New_York")

K1_MIN_TICKERS = 20
K2_MIN_SHARE = 0.8
FROZEN_UNTIL = date(2026, 10, 30)
GAP_LOG_CUTOFF_DAYS = 30  # identisch zu hist_5d_gap_log.CUTOFF_DAYS

# Am 02.11.2026 aus K1/K2 abgeleitet (Repo-Stand origin/main f6eb81ba,
# Juli-Tage aus backtest_history.json @ f5a80d81). BINDEND für Entry-Tage
# bis einschließlich FROZEN_UNTIL.
EXCLUDED_DAYS_FROZEN: frozenset[str] = frozenset({
    # K2 (vol_stability_5d leer bei >= 80 % der Records des Tages)
    "2026-09-01", "2026-09-21", "2026-09-23", "2026-09-24",
    "2026-09-28", "2026-09-29", "2026-09-30",
    # K1 (>= 20 Ticker mit leerem Close am Entry-Tag im Postclose-Lauf)
    "2026-10-01", "2026-10-02", "2026-10-06", "2026-10-07", "2026-10-08",
    "2026-10-09", "2026-10-13", "2026-10-19", "2026-10-21", "2026-10-22",
    "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30",
})

SENS_RESULTS_FILE = "eval_results_sensitivity.jsonl"
SENS_VARIANT = "s4_sensitivity_postclose_halfrow_2026-11-02"


class NichtPruefbar(Exception):
    """Ein Entry-Tag nach FROZEN_UNTIL ist im Gap-Log nicht mehr prüfbar."""


def _entry_iso(rec: dict) -> str | None:
    """``date`` (TT.MM.JJJJ) → ISO-String, sonst None."""
    try:
        return datetime.strptime(str(rec.get("date", "")), "%d.%m.%Y").date().isoformat()
    except (TypeError, ValueError):
        return None


def k1_affected_days(gap_rows: list[dict]) -> dict[str, int]:
    """K1-Zählung je Entry-Tag: ``{iso_tag: anzahl_verschiedener_ticker}``
    (nur Postclose-Läufe, nur Close-leer am Entry-Tag). Pure Funktion."""
    tickers: dict[str, set] = {}
    for d in gap_rows:
        try:
            ts = datetime.fromisoformat(str(d["run_ts"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        if ts.tzinfo is None:
            continue
        et = ts.astimezone(ET)
        if et.hour < 16:
            continue
        day = et.date().isoformat()
        if (d.get("reason") == "nonfinite_cell"
                and str(d.get("dropped_day") or "")[:10] == day
                and "Close" in (d.get("missing_cells") or [])):
            tickers.setdefault(day, set()).add(d.get("ticker"))
    return {k: len(v) for k, v in tickers.items()}


def excluded_days_for(entry_days: set[str], gap_rows: list[dict] | None,
                      now: datetime) -> set[str]:
    """Bindende Ausschlussmenge für die gegebenen Entry-Tage: eingefrorene
    Liste bis FROZEN_UNTIL, danach K1. Wirft ``NichtPruefbar`` für einen
    Tag nach FROZEN_UNTIL, der im Gap-Log nicht mehr prüfbar ist."""
    out = {d for d in entry_days if d in EXCLUDED_DAYS_FROZEN}
    later = sorted(d for d in entry_days if date.fromisoformat(d) > FROZEN_UNTIL)
    if not later:
        return out
    if gap_rows is None:
        raise NichtPruefbar(f"Gap-Log fehlt — Entry-Tage {later} nicht prüfbar")
    today = now.astimezone(ET).date()
    stale = [d for d in later if (today - date.fromisoformat(d)).days > GAP_LOG_CUTOFF_DAYS - 1]
    if stale:
        raise NichtPruefbar(f"Entry-Tage {stale} älter als Gap-Log-Fenster — nicht prüfbar")
    counts = k1_affected_days(gap_rows)
    out |= {d for d in later if counts.get(d, 0) >= K1_MIN_TICKERS}
    return out


def filter_population(rows: list[dict], excluded: set[str]) -> list[dict]:
    """Entfernt ausschließlich Records mit Entry-Tag in ``excluded``."""
    return [r for r in rows if _entry_iso(r) not in excluded]


def combine_verdict(main_verdict: str, sens_verdict: str) -> str:
    """Entscheidungsregel (Protokolleintrag 02.11.2026), je Test:
    „belegt“ = freeze_eval-Verdikt "Beleg"; „bedingt“/„Unklar“ = nicht belegt.
    Die Sensitivität kann nur abschwächen, nie aufwerten."""
    if main_verdict != "Beleg":
        return "nicht belegt"
    if sens_verdict == "Beleg":
        return "belegt"
    return "belegt, aber nicht robust"


def run_sensitivity(rows: list[dict], *, gap_rows: list[dict] | None,
                    now: datetime) -> dict:
    """Rechnet die Sensitivität mit der eingefrorenen Funktion. Pure bis auf
    den Import von freeze_eval (keine Datei-Schreibzugriffe)."""
    import freeze_eval as fe  # eingefroren, unverändert genutzt
    days = {d for d in (_entry_iso(r) for r in rows) if d}
    excluded = excluded_days_for(days, gap_rows, now)
    kept = filter_population(rows, excluded)
    result = fe.evaluate_exit_b1_family(kept, now=now)
    result["sensitivity"] = {
        "variant": SENS_VARIANT,
        "excluded_days": sorted(excluded),
        "n_rows_in": len(rows),
        "n_rows_kept": len(kept),
        "k1_min_tickers": K1_MIN_TICKERS,
        "k2_min_share": K2_MIN_SHARE,
        "frozen_until": FROZEN_UNTIL.isoformat(),
    }
    return result


def _read_jsonl(path: pathlib.Path) -> list[dict] | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            out = []
            for line in fh:
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
            return out
    except FileNotFoundError:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true",
                    help=f"Ergebnis an {SENS_RESULTS_FILE} anhängen (sonst nur Ausgabe)")
    args = ap.parse_args(argv)

    import freeze_eval as fe
    import health_check as hc

    now = datetime.now(timezone.utc)
    rows = _read_jsonl(ROOT / hc.MATURED_EXPORT_FILE) or []
    gap_rows = _read_jsonl(ROOT / "hist_5d_gap_log.jsonl")
    try:
        res = run_sensitivity(rows, gap_rows=gap_rows, now=now)
    except NichtPruefbar as exc:
        print(f"NICHT PRÜFBAR: {exc}")
        return 2

    main_rows = [r for r in (_read_jsonl(ROOT / "eval_results.jsonl") or [])
                 if r.get("family") == res["family"]]
    main_by_id = {r.get("test_id"): r.get("verdict") for r in main_rows}

    flat = fe._flatten_family_result(res)
    for row in flat:
        row["sensitivity"] = res["sensitivity"]
        mv = main_by_id.get(row.get("test_id"))
        row["main_verdict"] = mv
        row["combined_verdict"] = combine_verdict(mv, row.get("verdict")) if mv else None
        print(json.dumps({k: row.get(k) for k in ("test_id", "verdict", "main_verdict",
                                                   "combined_verdict")}, ensure_ascii=False))
    print(json.dumps(res["sensitivity"], ensure_ascii=False))
    if args.write:
        fe._append_results(str(ROOT / SENS_RESULTS_FILE), flat)
        print(f"geschrieben: {SENS_RESULTS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
