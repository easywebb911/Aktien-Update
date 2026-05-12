"""Mock-Tests für das score_history.json-Pruning.

Verifiziert den Fix gegen den lexikographischen String-Vergleich auf
DD.MM.YYYY (Mai 2026). Vorher wurde `"12.05.2026" >= "28.04.2026"`
zeichenweise als False ausgewertet → alle Mai-Einträge bei jedem
Load/Save gedroppt.

Tests:
  1. _parse_de_date — gültige + ungültige Strings
  2. Load: gemischte April/Mai-History → Mai bleibt, alte April-Front weg
  3. Save: dieselbe Pruning-Logik beim Schreiben
  4. Edge: leere History
  5. Edge: einziger Eintrag exakt am Cutoff
  6. Edge: kaputtes Datumsformat (ISO statt DE) → skip + Warning
  7. Round-Trip: load → save → load reproduziert die Daten

Ausführung: ``python scripts/mock_test_score_history_pruning.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from datetime import date, timedelta
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import generate_report as gr  # noqa: E402
from config import SCORE_HISTORY_DAYS  # noqa: E402


# Anker-„Heute": Dienstag 12.05.2026. Cutoff = 12.05 − 14d = 28.04.2026.
ANCHOR_TODAY = date(2026, 5, 12)
EXPECTED_CUTOFF = ANCHOR_TODAY - timedelta(days=SCORE_HISTORY_DAYS)


class _FrozenDate(date):
    """date.today() == ANCHOR_TODAY, alles andere unverändert."""

    @classmethod
    def today(cls) -> "_FrozenDate":
        return cls(ANCHOR_TODAY.year, ANCHOR_TODAY.month, ANCHOR_TODAY.day)


def _with_frozen_today(fn):
    """Patcht generate_report.date so, dass today() den Anker liefert.
    arithmetik (date - timedelta) bleibt unverändert."""
    def wrapper():
        with patch.object(gr, "date", _FrozenDate):
            fn()
    return wrapper


def _write_history_file(path: pathlib.Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _set_history_file(tmp_path: pathlib.Path):
    """Patcht SCORE_HISTORY_FILE auf eine temporäre Datei."""
    return patch.object(gr, "SCORE_HISTORY_FILE", str(tmp_path))


def test_parse_de_date_valid():
    assert gr._parse_de_date("12.05.2026") == date(2026, 5, 12)
    assert gr._parse_de_date("01.01.2025") == date(2025, 1, 1)
    assert gr._parse_de_date("28.04.2026") == date(2026, 4, 28)


def test_parse_de_date_invalid():
    assert gr._parse_de_date("") is None
    assert gr._parse_de_date("2026-05-12") is None  # ISO statt DE
    assert gr._parse_de_date("32.13.2026") is None  # ungültiger Tag/Monat
    assert gr._parse_de_date("garbage") is None


@_with_frozen_today
def test_load_keeps_may_drops_old_april():
    """April-Einträge älter als cutoff (=28.04.2026) raus, Mai bleibt.

    Vor Fix: ALLE Mai-Einträge wurden lexikographisch < "28.04.2026" eingestuft
    und gedroppt. Test schlägt fehl, wenn Bug zurückkehrt.
    """
    history = {
        "INDI": [
            ["27.04.2026", 53.4],   # vor Cutoff — raus
            ["28.04.2026", 60.0],   # exakt am Cutoff — bleibt
            ["30.04.2026", 80.2],   # nach Cutoff — bleibt
            ["11.05.2026", 70.8],   # Mai — bleibt (war Bug-Symptom)
            ["12.05.2026", 65.4],   # Mai — bleibt
        ],
    }
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td) / "score_history.json"
        _write_history_file(tmp, history)
        with _set_history_file(tmp):
            loaded = gr._load_score_history()
    indi = loaded["INDI"]
    dates_kept = [e["date"] for e in indi]
    assert "27.04.2026" not in dates_kept, dates_kept
    assert "28.04.2026" in dates_kept, dates_kept
    assert "30.04.2026" in dates_kept, dates_kept
    assert "11.05.2026" in dates_kept, dates_kept
    assert "12.05.2026" in dates_kept, dates_kept
    assert len(indi) == 4, dates_kept


@_with_frozen_today
def test_save_keeps_may_drops_old_april():
    """Save-Pfad pruned identisch zu Load-Pfad."""
    history_in_memory = {
        "INDI": [
            {"date": "27.04.2026", "score": 53.4, "drivers": []},
            {"date": "28.04.2026", "score": 60.0, "drivers": []},
            {"date": "11.05.2026", "score": 70.8, "drivers": ["RVOL 3.1×"]},
            {"date": "12.05.2026", "score": 65.4, "drivers": []},
        ],
    }
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td) / "score_history.json"
        with _set_history_file(tmp):
            gr._save_score_history(history_in_memory, _dirty=True)
        with open(tmp, "r", encoding="utf-8") as fh:
            written = json.load(fh)
    rows = written["INDI"]
    dates_kept = [r[0] for r in rows]
    assert "27.04.2026" not in dates_kept, dates_kept
    assert "28.04.2026" in dates_kept, dates_kept
    assert "11.05.2026" in dates_kept, dates_kept
    assert "12.05.2026" in dates_kept, dates_kept
    # 3-Tuple für drivers-haltige Einträge
    indi_11 = next(r for r in rows if r[0] == "11.05.2026")
    assert indi_11[2] == ["RVOL 3.1×"], indi_11


@_with_frozen_today
def test_load_empty_history():
    """Datei existiert nicht → leeres Dict, kein Crash."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td) / "does_not_exist.json"
        with _set_history_file(tmp):
            loaded = gr._load_score_history()
    assert loaded == {}, loaded


@_with_frozen_today
def test_load_single_entry_at_cutoff():
    """Einziger Eintrag exakt am Cutoff-Datum bleibt erhalten."""
    cutoff_str = EXPECTED_CUTOFF.strftime("%d.%m.%Y")
    history = {"FOO": [[cutoff_str, 42.0]]}
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td) / "score_history.json"
        _write_history_file(tmp, history)
        with _set_history_file(tmp):
            loaded = gr._load_score_history()
    assert loaded == {"FOO": [{"date": cutoff_str, "score": 42.0,
                               "drivers": []}]}, loaded


@_with_frozen_today
def test_load_skips_broken_date_format():
    """ISO-Format / Garbage in einem Eintrag → skip, kein Crash."""
    history = {
        "BAR": [
            ["2026-05-11", 70.0],   # ISO statt DE — skip
            ["garbage",   65.0],     # unparsbar — skip
            ["12.05.2026", 80.0],    # gültig — bleibt
        ],
    }
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td) / "score_history.json"
        _write_history_file(tmp, history)
        with _set_history_file(tmp):
            loaded = gr._load_score_history()
    assert "BAR" in loaded, loaded
    dates_kept = [e["date"] for e in loaded["BAR"]]
    assert dates_kept == ["12.05.2026"], dates_kept


@_with_frozen_today
def test_round_trip_load_save_load():
    """Daten überleben load → save → load unverändert."""
    history = {
        "INDI": [
            ["29.04.2026", 73.4],
            ["12.05.2026", 80.2, ["RVOL 3.1×", "Reddit +47"]],
        ],
        "DFDV": [
            ["11.05.2026", 76.6],
        ],
    }
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td) / "score_history.json"
        _write_history_file(tmp, history)
        with _set_history_file(tmp):
            loaded_1 = gr._load_score_history()
            gr._save_score_history(loaded_1, _dirty=True)
            loaded_2 = gr._load_score_history()
    assert loaded_1 == loaded_2, (loaded_1, loaded_2)
    indi_drv = next(e for e in loaded_2["INDI"] if e["date"] == "12.05.2026")
    assert indi_drv["drivers"] == ["RVOL 3.1×", "Reddit +47"], indi_drv


def main():
    tests = [
        ("_parse_de_date: valid DE strings",            test_parse_de_date_valid),
        ("_parse_de_date: invalid inputs return None",  test_parse_de_date_invalid),
        ("Load: April-Front weg, Mai bleibt",           test_load_keeps_may_drops_old_april),
        ("Save: April-Front weg, Mai bleibt",           test_save_keeps_may_drops_old_april),
        ("Load: leere History → {}",                    test_load_empty_history),
        ("Load: Eintrag exakt am Cutoff bleibt",        test_load_single_entry_at_cutoff),
        ("Load: kaputtes Datumsformat → skip + Warn",   test_load_skips_broken_date_format),
        ("Round-Trip load → save → load idempotent",    test_round_trip_load_save_load),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {name}\n      {exc}")
        except Exception as exc:
            failed += 1
            print(f"  ✗ {name}\n      Unexpected: {type(exc).__name__}: {exc}")
    print()
    if failed:
        print(f"{failed} Test(s) fehlgeschlagen.")
        sys.exit(1)
    print(f"{len(tests)} Tests bestanden.")
    sys.exit(0)


if __name__ == "__main__":
    main()
