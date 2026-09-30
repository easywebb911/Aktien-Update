"""Mock-Tests für ``hist_5d_gap_log.py`` (Folge-PR zu #561, 30.09.2026).

Testet das Modul DIREKT (nicht über ``_extract_hist_5d`` — das deckt
``scripts/mock_test_hist5d_diagnostic_logging.py`` Tests H-K ab). Style
analog ``mock_test_score_inflation_log.py`` (reale Tempfiles, expliziter
``path=``-Parameter bei jedem Aufruf — siehe Modul-Docstring von
``hist_5d_gap_log`` zur bewussten ``None``-Sentinel-Abweichung).

Sieben Szenarien:
  1. Schema-Vollständigkeit: alle Felder korrekt belegt (schema_v, run_ts,
     ticker, reason, dropped_day, missing_cells, n_days, window)
  2. Append-only: zwei Aufrufe hängen an, überschreiben nicht
  3. dropped_day/missing_cells-Default (None/[]) wenn nicht übergeben
     (die beiden "insufficient_*"-reason-Fälle)
  4. Prune: 35 Tage alter Eintrag fällt raus, 25 Tage alter bleibt
  5. Edge: leere/fehlende Datei → read_all()==[]，prune_log()==0
  6. Edge: kaputte JSONL-Zeile in der Mitte → bleibt erhalten (Operator
     entscheidet), nachfolgende Einträge bleiben lesbar
  7. Schreibfehler (OSError, z.B. Verzeichnis statt Datei als path) →
     record_gap() liefert False, kein Re-Raise

Ausführung: ``python scripts/mock_test_hist_5d_gap_log.py``.
Exit 0 bei Erfolg, 1 bei Fund.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hist_5d_gap_log as hgl  # noqa: E402

_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK  {name}")
    else:
        _fails.append(f"{name}" + (f" — {detail}" if detail else ""))
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))


def _dt(year, month, day, hour, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _read_lines(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ── 1 — Schema-Vollständigkeit ──────────────────────────────────────────────

def test_1_schema_complete():
    with tempfile.TemporaryDirectory() as d:
        p = str(pathlib.Path(d) / "gap.jsonl")
        ok = hgl.record_gap(
            "WOLF", "nonfinite_cell",
            dropped_day="2026-09-29", missing_cells=["Close", "Volume"],
            run_ts=_dt(2026, 9, 30, 0, 33), path=p,
        )
        _check("1 record_gap liefert True", ok is True)
        entries = _read_lines(pathlib.Path(p))
        _check("1 genau 1 Eintrag", len(entries) == 1, repr(entries))
        if entries:
            e = entries[0]
            expected_keys = {"schema_v", "run_ts", "ticker", "reason",
                              "dropped_day", "missing_cells", "n_days", "window"}
            _check("1 alle erwarteten Keys vorhanden",
                   expected_keys <= set(e.keys()), repr(e))
            _check("1 schema_v == 1", e.get("schema_v") == 1, repr(e))
            _check("1 run_ts korrekt formatiert",
                   e.get("run_ts") == "2026-09-30T00:33:00Z", repr(e))
            _check("1 ticker/reason korrekt",
                   e.get("ticker") == "WOLF" and e.get("reason") == "nonfinite_cell",
                   repr(e))
            _check("1 dropped_day als String",
                   e.get("dropped_day") == "2026-09-29", repr(e))
            _check("1 missing_cells als Liste",
                   e.get("missing_cells") == ["Close", "Volume"], repr(e))


# ── 2 — Append-only ──────────────────────────────────────────────────────────

def test_2_append_only():
    with tempfile.TemporaryDirectory() as d:
        p = str(pathlib.Path(d) / "gap.jsonl")
        hgl.record_gap("AAA", "nonfinite_cell", dropped_day="2026-09-28",
                        missing_cells=["High"], run_ts=_dt(2026, 9, 28, 10), path=p)
        hgl.record_gap("BBB", "nonfinite_cell", dropped_day="2026-09-29",
                        missing_cells=["Low"], run_ts=_dt(2026, 9, 29, 10), path=p)
        entries = _read_lines(pathlib.Path(p))
        _check("2 zwei Einträge, keiner überschrieben", len(entries) == 2, repr(entries))
        _check("2 Reihenfolge erhalten (AAA, BBB)",
               [e["ticker"] for e in entries] == ["AAA", "BBB"], repr(entries))


# ── 3 — Defaults für dropped_day/missing_cells bei summary-reasons ─────────

def test_3_summary_reason_defaults():
    with tempfile.TemporaryDirectory() as d:
        p = str(pathlib.Path(d) / "gap.jsonl")
        hgl.record_gap("GRPN", "insufficient_raw_days", n_days=3, window=5,
                        run_ts=_dt(2026, 9, 30, 0), path=p)
        entries = _read_lines(pathlib.Path(p))
        _check("3 genau 1 Eintrag", len(entries) == 1, repr(entries))
        if entries:
            e = entries[0]
            _check("3 dropped_day ist None (nicht übergeben)",
                   e.get("dropped_day") is None, repr(e))
            _check("3 missing_cells ist leere Liste (nicht übergeben)",
                   e.get("missing_cells") == [], repr(e))
            _check("3 n_days/window korrekt",
                   e.get("n_days") == 3 and e.get("window") == 5, repr(e))


# ── 4 — Prune: alt raus, jung bleibt ────────────────────────────────────────

def test_4_prune_removes_old_keeps_recent():
    with tempfile.TemporaryDirectory() as d:
        p = str(pathlib.Path(d) / "gap.jsonl")
        now = datetime.now(timezone.utc)
        old_ts = now - timedelta(days=35)
        recent_ts = now - timedelta(days=25)
        hgl.record_gap("OLD", "nonfinite_cell", dropped_day="x",
                        missing_cells=["Close"], run_ts=old_ts, path=p)
        hgl.record_gap("RECENT", "nonfinite_cell", dropped_day="y",
                        missing_cells=["Close"], run_ts=recent_ts, path=p)
        n_removed = hgl.prune_log(max_days=30, path=p)
        _check("4 genau 1 Eintrag entfernt", n_removed == 1, n_removed)
        entries = _read_lines(pathlib.Path(p))
        _check("4 nur RECENT bleibt übrig",
               len(entries) == 1 and entries[0]["ticker"] == "RECENT", repr(entries))


# ── 5 — Edge: leere/fehlende Datei ──────────────────────────────────────────

def test_5_missing_file_is_empty_and_safe():
    with tempfile.TemporaryDirectory() as d:
        p = str(pathlib.Path(d) / "does_not_exist.jsonl")
        _check("5 read_all auf fehlende Datei -> []", hgl.read_all(path=p) == [])
        _check("5 prune_log auf fehlende Datei -> 0", hgl.prune_log(max_days=30, path=p) == 0)


# ── 6 — Edge: kaputte Zeile bleibt erhalten ────────────────────────────────

def test_6_corrupted_line_preserved_on_prune():
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "gap.jsonl"
        now = datetime.now(timezone.utc)
        good_old = json.dumps({"schema_v": 1, "run_ts": (now - timedelta(days=40))
                               .strftime("%Y-%m-%dT%H:%M:%SZ"), "ticker": "OLD"})
        bad_line = "{not valid json"
        good_recent = json.dumps({"schema_v": 1, "run_ts": (now - timedelta(days=1))
                                  .strftime("%Y-%m-%dT%H:%M:%SZ"), "ticker": "RECENT"})
        p.write_text(good_old + "\n" + bad_line + "\n" + good_recent + "\n", encoding="utf-8")
        n_removed = hgl.prune_log(max_days=30, path=str(p))
        lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        _check("6 kaputte Zeile bleibt in der Datei (Operator entscheidet)",
               any("not valid json" in l for l in lines), repr(lines))
        _check("6 RECENT bleibt, OLD ist raus",
               any("RECENT" in l for l in lines) and not any(
                   ('"ticker": "OLD"') in l for l in lines),
               repr(lines))
        _check("6 read_all skippt die kaputte Zeile ohne Crash",
               len(hgl.read_all(path=str(p))) == 1)


# ── 7 — Schreibfehler fail-soft ─────────────────────────────────────────────

def test_7_write_error_is_fail_soft():
    with tempfile.TemporaryDirectory() as d:
        # Ein Verzeichnis als "path" -> open(..., "a") wirft IsADirectoryError
        # (Unterklasse von OSError) -> record_gap muss False liefern, nicht crashen.
        dir_path = d
        ok = hgl.record_gap("X", "nonfinite_cell", dropped_day="x",
                            missing_cells=["Close"], path=dir_path)
        _check("7 record_gap auf Verzeichnis-Pfad -> False, kein Crash", ok is False)


def main() -> int:
    tests = [
        test_1_schema_complete,
        test_2_append_only,
        test_3_summary_reason_defaults,
        test_4_prune_removes_old_keeps_recent,
        test_5_missing_file_is_empty_and_safe,
        test_6_corrupted_line_preserved_on_prune,
        test_7_write_error_is_fail_soft,
    ]
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001 — Test-Harness, nicht Prod
            _fails.append(f"{t.__name__}: unexpected {type(exc).__name__}: {exc}")
            print(f"  FAIL {t.__name__}: unexpected {type(exc).__name__}: {exc}")

    print()
    if _fails:
        print(f"{len(_fails)} FAIL:")
        for f in _fails:
            print("  -", f)
        return 1
    print(f"Alle {len(tests)} hist_5d_gap_log-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
