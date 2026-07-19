"""Mock-Tests für ``scripts/purge_material_8k_events.py`` (§6c B0-1 Rückweg).

FIXTURE-ONLY (Temp-Datei) — kein Kontakt mit echter ``backtest_history.json``.

Beweist die KERN-INVARIANTE des isolierten Rückwegs:
- (A) Der Purge entfernt EXAKT den Key ``material_8k_events`` aus jedem Record.
- (B) JEDER andere Key/Wert bleibt byte-identisch (Referenz = dieselbe
      Datei ohne dieses eine Feld, mit identischer Serialisierung).
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

import purge_material_8k_events as P  # noqa: E402  (scripts/ = Skript-Dir, auto in sys.path)

_fails: list[str] = []


def _check(name, cond, msg=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {msg}")
        _fails.append(name)


def _fixture():
    return [
        {"date": "01.11.2025", "ticker": "LENZ", "score": 60.1,
         "max_gain_pct": 12.3, "conviction_score": 55,
         "material_8k_events": {"collected": True, "reason": None,
                                "cik": "0001815776", "truncated": False,
                                "events": [{"acceptance_datetime": "2025-11-05T16:05:00.000Z",
                                            "accession": "a-1", "cik": "0001815776",
                                            "item_codes": ["7.01", "9.01"],
                                            "matched_terms": ["received FDA approval"]}]}},
        {"date": "01.11.2025", "ticker": "AAPL", "score": 40.0,
         "max_gain_pct": 0.0,
         "material_8k_events": {"collected": True, "reason": None, "cik": "0000320193",
                                "truncated": False, "events": []}},
        # Alt-Record OHNE das Feld — muss unangetastet bleiben:
        {"date": "20.10.2025", "ticker": "ZBIO", "score": 33.3,
         "max_gain_pct": 5.5, "vix_level": 18.2},
    ]


def test_purge_isolated():
    orig = _fixture()
    work = copy.deepcopy(orig)
    _, n = P.purge_records(work)
    _check("A1 zwei Records mit Feld entfernt", n == 2, n)
    _check("A2 Feld nach Purge weg",
           all("material_8k_events" not in r for r in work))
    # B: jeder andere Key/Wert identisch zur Referenz (orig ohne das Feld)
    ref = [{k: v for k, v in r.items() if k != "material_8k_events"} for r in orig]
    _check("B1 alle übrigen Felder byte-identisch (deep equal)", work == ref, )
    # C: Alt-Record (Index 2) komplett unverändert
    _check("C1 Alt-Record ohne Feld unangetastet", work[2] == orig[2])


def test_file_roundtrip_and_modes():
    orig = _fixture()
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as fh:
        json.dump(orig, fh, indent=2, ensure_ascii=False)
        path = fh.name

    # DRY-RUN darf NICHTS ändern
    before = pathlib.Path(path).read_text(encoding="utf-8")
    rc = P.main(["--path", path])
    after_dry = pathlib.Path(path).read_text(encoding="utf-8")
    _check("D1 Dry-Run exit 0", rc == 0)
    _check("D2 Dry-Run schreibt nicht (byte-identisch)", before == after_dry)

    # LIVE schreibt; Ergebnis == Referenz-Serialisierung ohne das Feld
    rc2 = P.main(["--live", "--path", path])
    _check("D3 Live exit 0", rc2 == 0)
    purged = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    ref = [{k: v for k, v in r.items() if k != "material_8k_events"} for r in orig]
    _check("B2 Live-Ergebnis == Referenz ohne Feld", purged == ref, )

    # Byte-Vergleich gegen eine frisch serialisierte Referenz-Datei
    ref_bytes = json.dumps(ref, indent=2, ensure_ascii=False)
    _check("B3 Live-Datei byte-identisch zur Referenz-Serialisierung",
           pathlib.Path(path).read_text(encoding="utf-8") == ref_bytes)
    pathlib.Path(path).unlink(missing_ok=True)


def test_failsoft():
    _, n = P.purge_records([])
    _check("E1 leere History → 0 popped", n == 0)
    rc = P.main(["--live", "--path", "/nonexistent/xyz_backtest.json"])
    _check("E2 fehlende Datei → exit 1 (kein Crash)", rc == 1)
    # kaputtes JSON
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
    print("✓ Alle Tests bestanden (purge_material_8k_events: isolierter Key-Pop, "
          "übrige Felder byte-identisch, Alt-Records unangetastet, Dry-Run/Live, "
          "fail-soft).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
