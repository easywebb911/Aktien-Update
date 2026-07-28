"""Mock-Tests für ``scripts/purge_ssr_restriction.py`` (Rule-201-Rückweg).

FIXTURE-ONLY (Temp-Datei) — kein Kontakt mit echter ``backtest_history.json``.

Beweist die KERN-INVARIANTE des isolierten Rückwegs:
- (A) Der Purge entfernt EXAKT den Key ``ssr_restriction`` aus jedem Record.
- (B) JEDER andere Key/Wert bleibt byte-identisch.
- (C) Alt-Records ohne das Feld bleiben unangetastet (pop no-op).
- (D) Dry-Run schreibt NICHTS; --live schreibt.
- (E) purge_records-Zähler korrekt; fail-soft bei fehlender/kaputter Datei.
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import purge_ssr_restriction as P  # noqa: E402

_fails: list[str] = []


def _check(name, cond, msg=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {msg}")
        _fails.append(name)


def _fixture():
    return [
        {"date": "27.07.2026", "ticker": "FRESH", "score": 60.1,
         "max_gain_pct": 12.3,
         "ssr_restriction": {"collected": True, "reason": None,
                             "source": "cboe_cumulative", "restricted_t": True,
                             "triggered_today": True, "carry_over": False,
                             "trigger_date": "2026-07-27",
                             "trigger_time_et": "14:18:01", "end_date": None,
                             "rescinded_date": None,
                             "fetched_at": "2026-07-27T22:05:00Z",
                             "source_latest_trigger": "2026-07-27 15:00:00"}},
        {"date": "27.07.2026", "ticker": "AAPL", "score": 40.0,
         "max_gain_pct": 0.0,
         "ssr_restriction": {"collected": True, "reason": None,
                             "source": "cboe_cumulative", "restricted_t": False,
                             "triggered_today": False, "carry_over": False,
                             "trigger_date": None, "trigger_time_et": None,
                             "end_date": None, "rescinded_date": None,
                             "fetched_at": "2026-07-27T22:05:00Z",
                             "source_latest_trigger": "2026-07-27 15:00:00"}},
        # Alt-Record OHNE das Feld — muss unangetastet bleiben:
        {"date": "20.07.2026", "ticker": "ZBIO", "score": 33.3,
         "max_gain_pct": 5.5, "vix_level": 18.2},
    ]


def test_purge_isolated():
    orig = _fixture()
    work = copy.deepcopy(orig)
    _, n = P.purge_records(work)
    _check("A1 zwei Records mit Feld entfernt", n == 2, n)
    _check("A2 Feld nach Purge weg",
           all("ssr_restriction" not in r for r in work))
    ref = [{k: v for k, v in r.items() if k != "ssr_restriction"} for r in orig]
    _check("B1 alle übrigen Felder byte-identisch (deep equal)", work == ref)
    _check("C1 Alt-Record ohne Feld unangetastet", work[2] == orig[2])


def test_file_roundtrip_and_modes():
    orig = _fixture()
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as fh:
        json.dump(orig, fh, indent=2, ensure_ascii=False)
        path = fh.name

    before = pathlib.Path(path).read_text(encoding="utf-8")
    rc = P.main(["--path", path])
    after_dry = pathlib.Path(path).read_text(encoding="utf-8")
    _check("D1 Dry-Run exit 0", rc == 0)
    _check("D2 Dry-Run schreibt nicht (byte-identisch)", before == after_dry)

    rc2 = P.main(["--live", "--path", path])
    _check("D3 Live exit 0", rc2 == 0)
    purged = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    ref = [{k: v for k, v in r.items() if k != "ssr_restriction"} for r in orig]
    _check("B2 Live-Ergebnis == Referenz ohne Feld", purged == ref)

    ref_bytes = json.dumps(ref, indent=2, ensure_ascii=False)
    _check("B3 Live-Datei byte-identisch zur Referenz-Serialisierung",
           pathlib.Path(path).read_text(encoding="utf-8") == ref_bytes)
    pathlib.Path(path).unlink(missing_ok=True)


def test_failsoft():
    _, n = P.purge_records([])
    _check("E1 leere History → 0 popped", n == 0)
    rc = P.main(["--live", "--path", "/nonexistent/xyz_backtest.json"])
    _check("E2 fehlende Datei → exit 1 (kein Crash)", rc == 1)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write("{not json")
        bad = fh.name
    rc2 = P.main(["--live", "--path", bad])
    _check("E3 kaputtes JSON → exit 1 (kein Crash)", rc2 == 1)
    pathlib.Path(bad).unlink(missing_ok=True)


def main():
    test_purge_isolated()
    test_file_roundtrip_and_modes()
    test_failsoft()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (purge_ssr_restriction: isolierter Key-Pop, "
          "übrige Felder byte-identisch, Alt-Records unangetastet, Dry-Run/Live, "
          "fail-soft).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
