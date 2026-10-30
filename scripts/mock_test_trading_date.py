"""Mock-Tests für ``trading_date.us_trading_date`` / ``us_trading_date_iso``
(Wächter-Befund 26.10.2026 — siehe trading_date.py-Modul-Docstring).

FIXTURE-ONLY — keine Netzwerkzugriffe, kein Kontakt mit Live-Dateien.

Verifiziert:
- (A) 00:30 UTC-Lauf (nach Mitternacht, vor US/Eastern-Mitternacht) liefert
  den VORTAG (ET), nicht den UTC-Kalendertag — das ist exakt der Bug, den
  der Helper beheben soll.
- (B) 22:00 UTC-Lauf (vor Mitternacht beidseitig) liefert denselben Tag auf
  UTC UND ET — Kontrollprobe, dass der Helper im unkritischen Fall nichts
  verändert.
- (C) US-Sommerzeit-Ende (01.11.2026, 2 Uhr ET) — EDT (UTC-4) vs. EST
  (UTC-5) Grenzfall: ein Zeitpunkt kurz vor und kurz nach der Umstellung
  liefert weiterhin das korrekte ET-Kalenderdatum.
- (D) ``now_utc=None``-Default nutzt ``datetime.now(timezone.utc)`` (keine
  Exception, Typ ``date``).
- (E) Naive datetime (kein tzinfo) wird als UTC interpretiert (Caller-
  Vertrag aus dem Docstring).
- (F) ``us_trading_date_iso`` liefert exakt den ISO-String von (A).
- (G) Isolations-Beleg: der Helper wird nirgends in Score-/Filter-/Push-/
  Exit-/Backtest-Pfaden referenziert (reine Datums-Hilfsfunktion).
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trading_date import us_trading_date, us_trading_date_iso  # noqa: E402


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def _test_after_midnight_utc_before_midnight_et():
    # 23.10.2026 00:30 UTC == 22.10.2026 20:30 ET (EDT, UTC-4) — noch
    # derselbe US-Handelstag wie der postclose-Lauf am 22.10.
    now_utc = datetime(2026, 10, 23, 0, 30, tzinfo=timezone.utc)
    got = us_trading_date(now_utc)
    _check(
        "A 00:30 UTC (23.10.) -> Vortag ET (22.10.)",
        got == date(2026, 10, 22),
        detail=f"got={got}",
    )


def _test_evening_run_same_day():
    # 22.10.2026 22:00 UTC == 22.10.2026 18:00 ET — gleicher Tag beidseitig.
    now_utc = datetime(2026, 10, 22, 22, 0, tzinfo=timezone.utc)
    got = us_trading_date(now_utc)
    _check(
        "B 22:00 UTC (22.10.) -> gleicher Tag ET (22.10.)",
        got == date(2026, 10, 22),
        detail=f"got={got}",
    )


def _test_dst_boundary():
    # US-Sommerzeit-Ende 01.11.2026 02:00 ET (2 Uhr lokal faellt auf 3 Uhr
    # zurueck) -> 01.11.2026 06:00 UTC ist die letzte EDT-Minute davor.
    before = datetime(2026, 11, 1, 5, 59, tzinfo=timezone.utc)  # noch EDT (UTC-4) -> 01:59 ET
    after = datetime(2026, 11, 1, 6, 1, tzinfo=timezone.utc)   # schon EST (UTC-5) -> 01:01 ET
    got_before = us_trading_date(before)
    got_after = us_trading_date(after)
    _check(
        "C1 kurz vor DST-Ende (05:59 UTC) -> 01.11. ET",
        got_before == date(2026, 11, 1),
        detail=f"got={got_before}",
    )
    _check(
        "C2 kurz nach DST-Ende (06:01 UTC) -> weiterhin 01.11. ET",
        got_after == date(2026, 11, 1),
        detail=f"got={got_after}",
    )
    # Frueher Morgen nach UTC-Mitternacht, VOR dem DST-Switch (noch EDT):
    # 01.11.2026 03:30 UTC == 31.10.2026 23:30 ET (EDT) -> Vortag.
    early_before_switch = datetime(2026, 11, 1, 3, 30, tzinfo=timezone.utc)
    got_early = us_trading_date(early_before_switch)
    _check(
        "C3 03:30 UTC (01.11., vor DST-Switch) -> Vortag ET (31.10.)",
        got_early == date(2026, 10, 31),
        detail=f"got={got_early}",
    )


def _test_default_now():
    got = us_trading_date()
    _check(
        "D now_utc=None nutzt datetime.now(timezone.utc), liefert date",
        isinstance(got, date),
        detail=f"type={type(got)}",
    )


def _test_naive_datetime_treated_as_utc():
    naive = datetime(2026, 10, 23, 0, 30)  # kein tzinfo
    aware = datetime(2026, 10, 23, 0, 30, tzinfo=timezone.utc)
    _check(
        "E naive datetime == aware UTC-datetime (gleiches Ergebnis)",
        us_trading_date(naive) == us_trading_date(aware),
    )


def _test_iso_string_matches():
    now_utc = datetime(2026, 10, 23, 0, 30, tzinfo=timezone.utc)
    got = us_trading_date_iso(now_utc)
    _check(
        "F us_trading_date_iso liefert ISO-String des korrekten ET-Datums",
        got == "2026-10-22",
        detail=f"got={got}",
    )


def _test_score_isolation():
    forbidden_funcs = [
        "def compute_conviction_score",
        "def apply_conviction_scores",
        "def score(",
        "def score_bonus(",
        "def apply_monster_score",
        "def apply_agent_boost",
        "def apply_late_runner_penalty",
        "def apply_score_smoothing",
        "def _compute_sub_scores",
        "def compute_exit_score",
        "def process_exit_signals",
    ]
    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    import re

    for func_sig in forbidden_funcs:
        m = re.search(re.escape(func_sig), gr_src)
        if not m:
            continue
        start = m.start()
        # Body grob bis zur naechsten Top-Level-def/class (Einzug 0) scannen.
        rest = gr_src[start:]
        lines = rest.splitlines()
        body_lines = [lines[0]]
        for ln in lines[1:]:
            if ln and not ln[0].isspace() and (ln.startswith("def ") or ln.startswith("class ")):
                break
            body_lines.append(ln)
        body = "\n".join(body_lines)
        _check(
            f"G {func_sig!r} referenziert trading_date NICHT",
            "trading_date" not in body,
        )


def main():
    _test_after_midnight_utc_before_midnight_et()
    _test_evening_run_same_day()
    _test_dst_boundary()
    _test_default_now()
    _test_naive_datetime_treated_as_utc()
    _test_iso_string_matches()
    _test_score_isolation()

    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (UTC-Mitternacht-Grenzfall, DST-Grenze, "
          "Default/naive-Verhalten, Score-Isolation).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
