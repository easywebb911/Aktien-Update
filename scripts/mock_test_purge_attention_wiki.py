"""Mock-Tests für ``scripts/purge_attention_wiki.py`` (Rückweg attention_wiki).

FIXTURE-ONLY (Temp-Dateien) — kein Kontakt mit echter ``backtest_history.json``.

Beweist die Kern-Invariante des isolierten Rückwegs:
- (A) Purge entfernt EXAKT den Key ``attention_wiki`` aus jedem Record.
- (B) JEDER andere Key/Wert bleibt byte-identisch.
- (C) Alt-Records ohne das Feld unangetastet (pop no-op).
- (D) Dry-Run schreibt/löscht NICHTS; --live schreibt + löscht wiki_ticker_map.json.
- (E) fail-soft bei fehlender/kaputter Datei.
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import purge_attention_wiki as P  # noqa: E402

_fails: list[str] = []


def _check(name, cond, msg=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {msg}")
        _fails.append(name)


def _fixture():
    return [
        {"date": "01.11.2025", "ticker": "AI", "score": 60.1, "max_gain_pct": 12.3,
         "attention_wiki": {"substrate": "en", "article_qid": "Q104081972",
                            "article_title": "C3.ai", "views_t_minus_1": 1200,
                            "views_t": 1500, "views_t_backfilled_at": "2026-…Z",
                            "baseline_30d_median": 900.0, "baseline_30d_n": 30,
                            "delta_ratio": 1.33}},
        {"date": "01.11.2025", "ticker": "WRLD", "score": 40.0, "max_gain_pct": 0.0,
         "attention_wiki": {"substrate": "none", "article_qid": None,
                            "article_title": None, "views_t_minus_1": None,
                            "views_t": None, "views_t_backfilled_at": None,
                            "baseline_30d_median": None, "baseline_30d_n": None,
                            "delta_ratio": None}},
        # Alt-Record OHNE das Feld — muss unangetastet bleiben:
        {"date": "20.10.2025", "ticker": "ZBIO", "score": 33.3, "vix_level": 18.2},
    ]


def test_purge_isolated():
    orig = _fixture()
    work = copy.deepcopy(orig)
    _, n = P.purge_records(work)
    _check("A1 zwei Records mit Feld entfernt", n == 2, n)
    _check("A2 Feld nach Purge weg", all("attention_wiki" not in r for r in work))
    ref = [{k: v for k, v in r.items() if k != "attention_wiki"} for r in orig]
    _check("B1 alle übrigen Felder byte-identisch (deep equal)", work == ref)
    _check("C1 Alt-Record ohne Feld unangetastet", work[2] == orig[2])


def test_file_roundtrip_and_map_delete():
    orig = _fixture()
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as fh:
        json.dump(orig, fh, indent=2, ensure_ascii=False)
        path = fh.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as fh:
        json.dump({"AI": {"qid": "Q104081972", "substrate": "en"}}, fh)
        map_path = fh.name

    # DRY-RUN darf NICHTS ändern/löschen
    before = pathlib.Path(path).read_text(encoding="utf-8")
    rc = P.main(["--path", path, "--map-path", map_path])
    _check("D1 Dry-Run exit 0", rc == 0)
    _check("D2 Dry-Run schreibt nicht", before == pathlib.Path(path).read_text(encoding="utf-8"))
    _check("D3 Dry-Run löscht Map nicht", pathlib.Path(map_path).exists())

    # LIVE schreibt + löscht die Map
    rc2 = P.main(["--live", "--path", path, "--map-path", map_path])
    _check("D4 Live exit 0", rc2 == 0)
    purged = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    ref = [{k: v for k, v in r.items() if k != "attention_wiki"} for r in orig]
    _check("B2 Live-Ergebnis == Referenz ohne Feld", purged == ref)
    ref_bytes = json.dumps(ref, indent=2, ensure_ascii=False)
    _check("B3 Live-Datei byte-identisch zur Referenz-Serialisierung",
           pathlib.Path(path).read_text(encoding="utf-8") == ref_bytes)
    _check("D5 Live löscht wiki_ticker_map.json", not pathlib.Path(map_path).exists())
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
    test_file_roundtrip_and_map_delete()
    test_failsoft()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (purge_attention_wiki: isolierter Key-Pop, "
          "byte-identisch, Map-Löschung, Dry-Run/Live, fail-soft).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
