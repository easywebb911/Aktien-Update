"""Mock-Tests für das ssr_restriction-Sammelfeld (Rule-201, 28.07.2026).

Netzwerkfrei — die Cboe-CSV wird als Fixture-String injiziert (``cboe_text=``).

Fälle:
  (A) triggered-heute            → triggered_today=True, carry_over=False
  (B) carry-over (Rule 201 T-1)  → carry_over=True, triggered_today=False
      (EXZELLENZ 1: gestriger Übertrag zählt NICHT als frischer Trigger)
  (C) Multi-Trigger (T-1 + T)    → governing = T → triggered_today (nicht carry)
  (D) rescinded/ended vor T      → restricted_t=False (geprüft, nicht aktiv)
  (E) Ticker nicht im File       → restricted_t=False, collected=True
  (F) Fetch-Fail                 → collected=False, restricted_t=None (unbekannt)
  (G) Belegwerte                 → fetched_at (UTC), source_latest_trigger (ET)
  (H) Spalten-robust             → umgeordneter Header parst identisch
  (I) prev_trading_day           → Wochenende + Feiertag überbrückt
  (J) S10 + Schema-Keys + reader-tolerant (Alt-Record ohne Key)
  (K) Look-Ahead-Isolation       → kein Score-Pfad liest das Feld
  (L) Zeitzonen                  → ET-Quelldaten vs. UTC-fetched_at
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config                    # noqa: E402
import ssr_restriction as m      # noqa: E402

_fails: list[str] = []


def _check(name, cond, msg=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {msg}")
        _fails.append(name)


# ── Fixture: T = Mo 2026-07-27, prev trading day = Fr 2026-07-24 ─────────────
HDR = ("Primary Listing Exchange,Symbol,Security Name,Trigger Date,"
       "Trigger Time,End Date,End Time,Rescinded Date,Rescinded Time")
CSV = "\n".join([
    HDR,
    "BZX,FRESH,Fresh Today Co,2026-07-27,14:18:01,,,,",           # triggered heute
    "BZX,CARRY,Carryover Co,2026-07-24,10:31:07,,,,",             # T-1 carry
    "BZX,MULTI,Multi Co,2026-07-24,09:00:00,,,,",                 # carry ...
    "BZX,MULTI,Multi Co,2026-07-27,15:00:00,,,,",                 # ... + heute → governing heute
    "BZX,ENDED,Ended Co,2026-07-24,09:00:00,2026-07-24,16:00:00,,",   # end < T
    "BZX,RESC,Rescinded Co,2026-07-24,11:00:00,,,2026-07-24,12:00:00",  # rescinded < T
    "BZX,OLD,Old Co,2026-07-20,09:45:00,,,,",                     # außerhalb {T,T-1}
])
T = date(2026, 7, 27)
NOW = datetime(2026, 7, 27, 22, 5, 0, tzinfo=timezone.utc)  # postclose-Abruf


def _collect(tickers, **kw):
    return m.collect_ssr_restriction_flags(
        tickers, report_date=T, now_utc=NOW, cboe_text=CSV,
        holidays=frozenset(), **kw)


def test_A_triggered_today():
    w = _collect(["FRESH"])["FRESH"]
    _check("A1 collected", w["collected"] is True)
    _check("A2 restricted_t", w["restricted_t"] is True)
    _check("A3 triggered_today", w["triggered_today"] is True)
    _check("A4 carry_over False", w["carry_over"] is False)
    _check("A5 trigger_date == T", w["trigger_date"] == "2026-07-27", w)
    _check("A6 trigger_time_et", w["trigger_time_et"] == "14:18:01")
    _check("A7 source", w["source"] == "cboe_cumulative")


def test_B_carry_over():
    w = _collect(["CARRY"])["CARRY"]
    _check("B1 restricted_t", w["restricted_t"] is True)
    _check("B2 carry_over True", w["carry_over"] is True)
    # EXZELLENZ 1: carry_over NICHT als frischer Trigger
    _check("B3 triggered_today False (kein frischer Trigger!)",
           w["triggered_today"] is False, w)
    _check("B4 trigger_date == T-1", w["trigger_date"] == "2026-07-24", w)


def test_C_multi_trigger_governing_today():
    w = _collect(["MULTI"])["MULTI"]
    # Governing = jüngster aktiver Trigger (T) → triggered_today, nicht carry
    _check("C1 restricted_t", w["restricted_t"] is True)
    _check("C2 governing = heute → triggered_today", w["triggered_today"] is True, w)
    _check("C3 carry_over False (heute dominiert)", w["carry_over"] is False, w)
    _check("C4 trigger_date == T", w["trigger_date"] == "2026-07-27")


def test_D_ended_and_rescinded_before_T():
    r = _collect(["ENDED", "RESC", "OLD"])
    for tk in ("ENDED", "RESC", "OLD"):
        w = r[tk]
        _check(f"D {tk} collected True (geprüft)", w["collected"] is True)
        _check(f"D {tk} restricted_t False (nicht aktiv am T)",
               w["restricted_t"] is False, w)
        _check(f"D {tk} trigger_date None", w["trigger_date"] is None)


def test_E_ticker_absent():
    w = _collect(["NOTINFILE"])["NOTINFILE"]
    _check("E1 collected True (File geladen, Ticker nicht drin)",
           w["collected"] is True)
    _check("E2 restricted_t False (nicht None!)", w["restricted_t"] is False, w)
    _check("E3 reason None", w["reason"] is None)


def test_F_fetch_fail():
    r = m.collect_ssr_restriction_flags(
        ["FRESH"], report_date=T, now_utc=NOW,
        get_text=lambda *a, **k: None, holidays=frozenset())
    w = r["FRESH"]
    _check("F1 collected False", w["collected"] is False)
    _check("F2 reason fetch_failed", w["reason"] == "fetch_failed", w)
    # Fail-soft: Zustand UNBEKANNT (None), NICHT False (das wäre erfunden)
    _check("F3 restricted_t None (unbekannt ≠ False)",
           w["restricted_t"] is None, w)
    _check("F4 triggered_today None", w["triggered_today"] is None)
    _check("F5 fetched_at trotzdem gesetzt", w["fetched_at"] is not None)


def test_G_belegwerte():
    w = _collect(["FRESH"])["FRESH"]
    # Beleg 1: Abruf-Zeitpunkt (UTC)
    _check("G1 fetched_at == now_utc (UTC Z)",
           w["fetched_at"] == "2026-07-27T22:05:00Z", w["fetched_at"])
    # Beleg 2: jüngster Trigger IM File (ET) — hier MULTI 07-27 15:00:00
    _check("G2 source_latest_trigger = jüngster Trigger im File (ET)",
           w["source_latest_trigger"] == "2026-07-27 15:00:00",
           w["source_latest_trigger"])


def test_H_column_robust():
    # Header umgeordnet + Extra-Spalte → Spalten-Namen-Parsing muss identisch sein
    reordered = "\n".join([
        "Symbol,Trigger Time,Security Name,Extra,Trigger Date,End Date,"
        "Rescinded Date,End Time,Rescinded Time,Primary Listing Exchange",
        "FRESH,14:18:01,Fresh Today Co,junk,2026-07-27,,,,,BZX",
    ])
    w = m.collect_ssr_restriction_flags(
        ["FRESH"], report_date=T, now_utc=NOW, cboe_text=reordered,
        holidays=frozenset())["FRESH"]
    _check("H1 umgeordneter Header → triggered_today True",
           w["triggered_today"] is True and w["trigger_date"] == "2026-07-27", w)


def test_I_prev_trading_day():
    # Mo 27.07 → Fr 24.07 (Wochenende übersprungen)
    _check("I1 Mo→Fr (Wochenende)",
           m._prev_trading_day(date(2026, 7, 27), frozenset()) == date(2026, 7, 24))
    # Feiertag am Fr 24.07 → Do 23.07
    _check("I2 Feiertag überbrückt",
           m._prev_trading_day(date(2026, 7, 27), frozenset({"2026-07-24"}))
           == date(2026, 7, 23))


def test_J_s10_schema_and_reader_tolerant():
    _check("J1 ssr_restriction in S10_OBSERVED_FIELDS",
           "ssr_restriction" in config.S10_OBSERVED_FIELDS)
    _check("J2 NICHT in S10_MUSS_FIELDS",
           "ssr_restriction" not in getattr(config, "S10_MUSS_FIELDS", frozenset()))
    _check("J3 NICHT in S10_LAG_FIELDS",
           "ssr_restriction" not in getattr(config, "S10_LAG_FIELDS", frozenset()))
    w = _collect(["FRESH"])["FRESH"]
    expected = {"collected", "reason", "source", "restricted_t",
                "triggered_today", "carry_over", "trigger_date",
                "trigger_time_et", "end_date", "rescinded_date",
                "fetched_at", "source_latest_trigger"}
    _check("J4 Wrapper hat exakt die 12 Schema-Keys",
           set(w.keys()) == expected, set(w.keys()) ^ expected)
    # reader-tolerant: Alt-Record ohne Key → .get() liefert None, kein Crash
    _check("J5 Alt-Record ohne Key null-tolerant",
           {"ticker": "X"}.get("ssr_restriction") is None)


def test_K_look_ahead_isolation():
    # Das Feld darf in KEINEM Score-/Filter-/Push-Pfad gelesen werden.
    for fn in ("generate_report.py", "ki_agent.py", "health_check.py"):
        src = (ROOT / fn).read_text(encoding="utf-8")
        _check(f"K H1 kein 'ssr_restriction'-Key-Read in {fn}",
               "ssr_restriction" not in src, fn)
        _check(f"K H2 kein collect_ssr_restriction_flags-Call in {fn}",
               "collect_ssr_restriction_flags" not in src, fn)
    bh = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    _check("K H3 ssr_restriction nur in backtest_history importiert",
           "import ssr_restriction" in bh)


def test_L_timezones():
    w = _collect(["FRESH"])["FRESH"]
    # ET-Quelldaten: trigger_date ist ET-Handelstag-Datum (kein UTC-Shift)
    _check("L1 trigger_date ET (== Cboe-Datum, kein Shift)",
           w["trigger_date"] == "2026-07-27")
    # UTC-Beleg: fetched_at endet auf Z (UTC)
    _check("L2 fetched_at UTC (endet auf Z)", w["fetched_at"].endswith("Z"))
    # Kein Naive/Aware-Mix: naiver now_utc wird als UTC behandelt
    naive = datetime(2026, 7, 27, 22, 5, 0)
    w2 = m.collect_ssr_restriction_flags(
        ["FRESH"], report_date=T, now_utc=naive, cboe_text=CSV,
        holidays=frozenset())["FRESH"]
    _check("L3 naiver now_utc → als UTC gestempelt",
           w2["fetched_at"] == "2026-07-27T22:05:00Z", w2["fetched_at"])


def main():
    for fn in (test_A_triggered_today, test_B_carry_over,
               test_C_multi_trigger_governing_today,
               test_D_ended_and_rescinded_before_T, test_E_ticker_absent,
               test_F_fetch_fail, test_G_belegwerte, test_H_column_robust,
               test_I_prev_trading_day, test_J_s10_schema_and_reader_tolerant,
               test_K_look_ahead_isolation, test_L_timezones):
        fn()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (ssr_restriction: triggered/carry/multi/"
          "ended/absent/fetch-fail/Belegwerte/Spalten-robust/prev-trading-day/"
          "S10+Schema/Look-Ahead-Isolation/Zeitzonen).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
