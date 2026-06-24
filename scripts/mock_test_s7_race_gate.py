"""Mock-Tests für das S7-Race-Gate (Bug-Fix 23.06.2026).

S7 (agent_signals ∩ top10 ≥ 5) feuerte architektonisch im Daily-Run, BEVOR
dessen async Auto-Trigger-ki_agent-Tick die frische (rotierte) Top-10 abdeckt
— 22/30d Fälle, ALLE selbstgeheilt, 0 echte Treffer (Diagnose 23.06.).

Fix (Variante B): S7 SUPPRESS nur bei POSITIVER Bestätigung, dass seit dem
vorigen Daily-Run schon ein ki_agent-Tick lief (Auto-Trigger-Kette intakt →
Rotation-Race). Sonst FEUERN — insbesondere wenn KEIN Tick seit dem vorigen
Run lief (14.05.-Bug-Klasse: Kette gebrochen). Fehlt/unparsebar ein Timestamp
→ konservativ FEUERN (14.05.-Schutz nie aushebeln).

Zeitstempel-TZ bewusst gemischt: agent_signals.updated ist Berlin-ISO
(+02:00), last_daily_run_ts ist UTC ('Z'). Der Vergleich muss korrekt über
TZ-Grenzen rechnen (beide → tz-aware via fromisoformat).

Kategorie A: stdlib + config + zoneinfo, deterministisch (kein now()),
env-frei, CI-gate-bar.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


TOP10 = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ"]
DISJOINT = {"P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y"}   # 0 overlap
OVERLAP5 = {"AAA", "BBB", "CCC", "DDD", "EEE", "ZZ1", "ZZ2"}    # 5 overlap


def _s7(fails) -> bool:
    return any(f.get("id") == "S7" for f in fails)


def _eval(*, agent_keys, ag_updated, prev_run):
    """S7-isolierter Aufruf: top10 gesetzt, ki_agent_only=False, html_path=None
    (S9 übersprungen). Andere Invariants dürfen feuern — wir prüfen NUR S7."""
    return hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        agent_signal_keys=agent_keys,
        agent_signals_updated=ag_updated,
        prev_daily_run_ts=prev_run,
        ki_agent_only=False,
        html_path=None,
    )


def main() -> int:
    # ── Test 1: Tick NACH vorigem Daily-Run, 0/10 → SUPPRESS (22.06-17:22) ──
    # prev daily-run 12:27 UTC, Auto-Trigger-Tick 14:28+02:00 (=12:28 UTC > 12:27)
    f1 = _eval(agent_keys=DISJOINT,
               ag_updated="2026-06-22T14:28:00+02:00",
               prev_run="2026-06-22T12:27:00Z")
    _check("01 Tick seit vorigem Run + 0/10 → SUPPRESS (22.06-17:22-Race)",
           not _s7(f1))

    # ── Test 2: KEIN Tick seit vorigem Run, 0/10 → FEUERN (14.05.-Bug) ──────
    # prev daily-run 12:27 UTC, letzter Tick erst Vortag 23:00+02:00 (=21:00 UTC Vortag)
    f2 = _eval(agent_keys=DISJOINT,
               ag_updated="2026-06-21T23:00:00+02:00",
               prev_run="2026-06-22T12:27:00Z")
    _check("02 Kein Tick seit vorigem Run + 0/10 → FEUERN (14.05.-Bug-Klasse)",
           _s7(f2))

    # ── Test 3: Überlappung ≥5 → SUPPRESS unabhängig von Timestamps ─────────
    f3a = _eval(agent_keys=OVERLAP5,
                ag_updated="2026-06-21T23:00:00+02:00",  # stale tick
                prev_run="2026-06-22T12:27:00Z")
    f3b = _eval(agent_keys=OVERLAP5, ag_updated=None, prev_run=None)
    _check("03 Überlappung ≥5 → KEIN S7 (auch bei stale/fehlenden Timestamps)",
           not _s7(f3a) and not _s7(f3b))

    # ── Test 4: Erstrun ohne voriger Daily-Run-Anker → FEUERN (konservativ) ─
    f4 = _eval(agent_keys=DISJOINT,
               ag_updated="2026-06-22T14:28:00+02:00",
               prev_run=None)
    _check("04 Erstrun (prev_daily_run_ts absent) + 0/10 → FEUERN (sicher)",
           _s7(f4))

    # ── Test 5: agent_signals.updated absent → FEUERN (konservativ) ─────────
    f5 = _eval(agent_keys=DISJOINT, ag_updated=None,
               prev_run="2026-06-22T12:27:00Z")
    _check("05 agent_signals.updated absent + 0/10 → FEUERN (sicher)", _s7(f5))

    # ── Test 6: unparsebarer Timestamp → FEUERN (konservativ) ───────────────
    f6 = _eval(agent_keys=DISJOINT, ag_updated="garbage",
               prev_run="2026-06-22T12:27:00Z")
    _check("06 unparsebarer Timestamp + 0/10 → FEUERN (sicher)", _s7(f6))

    # ── Test 7: Tick EXAKT == prev_run (nicht '>') → FEUERN (Grenze) ────────
    f7 = _eval(agent_keys=DISJOINT,
               ag_updated="2026-06-22T12:27:00Z",
               prev_run="2026-06-22T12:27:00Z")
    _check("07 Tick == prev_run (kein striktes >) → FEUERN (Grenzfall)", _s7(f7))

    # ── Test 8: TZ-Korrektheit — Berlin-Tick knapp NACH UTC-prev-run ────────
    # 12:28+02:00 = 10:28 UTC < 12:27 UTC → KEIN Tick danach → FEUERN.
    f8 = _eval(agent_keys=DISJOINT,
               ag_updated="2026-06-22T12:28:00+02:00",   # = 10:28 UTC
               prev_run="2026-06-22T12:27:00Z")           # = 12:27 UTC
    _check("08 TZ: Berlin 12:28+02 (=10:28 UTC) < prev 12:27 UTC → FEUERN",
           _s7(f8))

    # ── Test 9: Mehrtages-Ausfall → S7 feuert (komplementär zu S8, kein Konflikt)
    f9 = _eval(agent_keys=DISJOINT,
               ag_updated="2026-06-19T12:00:00+02:00",   # 4 Tage alt
               prev_run="2026-06-22T12:27:00Z")
    _check("09 Mehrtages-Ausfall + 0/10 → FEUERN (S8-26h-Backstop komplementär)",
           _s7(f9))

    # ── Test 10: Determinismus — gleicher Input → gleiches Ergebnis ─────────
    r1 = _s7(_eval(agent_keys=DISJOINT, ag_updated="2026-06-22T14:28:00+02:00",
                   prev_run="2026-06-22T12:27:00Z"))
    r2 = _s7(_eval(agent_keys=DISJOINT, ag_updated="2026-06-22T14:28:00+02:00",
                   prev_run="2026-06-22T12:27:00Z"))
    _check("10 Determinismus: Suppress-Pfad zweimal identisch", r1 == r2 == False)

    # ── Source-Asserts: Wiring im generate_report + ki_agent-Preservation ──
    SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    KI = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
    _check("11 generate_report schreibt last_daily_run_ts in app_data",
           '"last_daily_run_ts":' in SRC)
    _check("12 generate_report reicht agent_signals_updated + prev_daily_run_ts durch",
           "agent_signals_updated=_ag_updated_for_check" in SRC
           and "prev_daily_run_ts=_prev_daily_run_ts_for_check" in SRC)
    _check("13 prev-Anker aus _prev_app_data (vor dem Write gelesen)",
           "_prev_app_data.get(\"last_daily_run_ts\")" in SRC)
    # ki_agent.save_signals darf last_daily_run_ts NICHT explizit überschreiben
    # (sonst ginge der Anker bei jedem Tick verloren) — muss via **existing
    # preserviert werden.
    _check("14 ki_agent überschreibt last_daily_run_ts NICHT (via **existing preserviert)",
           "last_daily_run_ts" not in KI)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle S7-Race-Gate-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
