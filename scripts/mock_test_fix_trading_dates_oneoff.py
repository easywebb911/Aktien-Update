"""Mock-Tests für ``scripts/fix_trading_dates_oneoff.py`` (Wächter-Befund
26.10.2026 — Einmal-Korrektur verschobener Handelstag-Labels).

FIXTURE-ONLY — arbeitet auf temporären Kopien in ``tempfile.mkdtemp()``,
rührt NIEMALS die echten Repo-Dateien an.

Verifiziert:
- (A) Verschobener Eintrag (date != ET-Datum des eigenen ts_utc) wird auf
  das korrekte ET-Datum korrigiert.
- (B) Bereits korrekter Eintrag bleibt unverändert (``already_correct``,
  kein Schreib-Trigger).
- (C) Eintrag OHNE Zeitstempel-Feld bleibt unverändert (``no_ts``) — das
  ist der dokumentierte Verzicht auf Korrektur bei fehlender Zeitstempel-
  Spur.
- (D) Echte Kollision (zwei inhaltlich verschiedene Zeilen landen nach
  Korrektur auf demselben vollen Key) wird NICHT überschrieben, sondern
  gemeldet — beide Zeilen bleiben unverändert in der Datei stehen.
- (E) Idempotenz: ein zweiter Lauf auf dem bereits korrigierten File
  findet 0 weitere Korrekturen und ändert den Datei-Hash NICHT.
- (F) ``.bak``-Backup wird nur angelegt, wenn tatsächlich etwas korrigiert
  wurde, und enthält den VORHERIGEN Inhalt.
- (G) ``--dry-run`` schreibt nichts (Datei-Hash unverändert trotz
  gemeldeter Korrekturen).
- (H) ``report_dict_of_points`` ist rein lesend (keine Mutation) und
  erkennt den anomalen Datums-Count (gemergter Handelstag) korrekt.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from fix_trading_dates_oneoff import (  # noqa: E402
    _sha256,
    fix_jsonl,
    report_dict_of_points,
)


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def _write_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def _test_shift_and_already_correct_and_no_ts():
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        p = tmp / "fixture_a.jsonl"
        rows = [
            # A: verschobener Eintrag — ts_utc 23.10. 00:30 UTC -> ET 22.10.
            {"date": "2026-10-23", "run_phase": "postclose",
             "ts_utc": "2026-10-23T00:30:00+00:00", "val": 1},
            # B: bereits korrekt — ts_utc 22.10. 22:00 UTC -> ET 22.10.
            {"date": "2026-10-22", "run_phase": "ki_agent_tick",
             "ts_utc": "2026-10-22T22:00:00+00:00", "val": 2},
            # C: ohne Zeitstempel-Feld -> unveraendert
            {"date": "2026-10-23", "run_phase": "premarket", "val": 3},
        ]
        _write_jsonl(p, rows)
        stats = fix_jsonl(p, "ts_utc", ("run_phase",))

        _check("A1 genau 1 Korrektur erkannt", stats["corrected"] == 1,
               detail=f"corrected={stats['corrected']}")
        _check("A2 genau 1 bereits korrekt", stats["already_correct"] == 1,
               detail=f"already_correct={stats['already_correct']}")
        _check("C1 genau 1 ohne Zeitstempel (no_ts)", stats["no_ts"] == 1,
               detail=f"no_ts={stats['no_ts']}")
        _check("A3 keine Kollisionen", stats["collisions"] == 0)

        out_rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        _check("A4 Zeile 0 (verschoben) jetzt date=2026-10-22",
               out_rows[0]["date"] == "2026-10-22",
               detail=f"got={out_rows[0]['date']}")
        _check("B1 Zeile 1 (bereits korrekt) unveraendert date=2026-10-22",
               out_rows[1]["date"] == "2026-10-22")
        _check("C2 Zeile 2 (ohne ts) unveraendert date=2026-10-23",
               out_rows[2]["date"] == "2026-10-23")
        _check("F1 .bak-Backup wurde angelegt (corrected > 0)",
               p.with_suffix(p.suffix + ".bak").exists())
        bak_rows = [json.loads(l) for l in
                    p.with_suffix(p.suffix + ".bak").read_text(encoding="utf-8").splitlines()
                    if l.strip()]
        _check("F2 .bak enthaelt den VORHERIGEN (unkorrigierten) Inhalt",
               bak_rows[0]["date"] == "2026-10-23")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _test_collision_not_overwritten():
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        p = tmp / "fixture_collision.jsonl"
        rows = [
            # Zeile 0: bereits auf dem Ziel-Key, bleibt stehen.
            {"date": "2026-10-22", "run_phase": "ki_agent_tick",
             "ts_utc": "2026-10-22T04:47:00+00:00", "n": 10},
            # Zeile 1: wuerde nach Korrektur auf DENSELBEN Key (date=22,
            # run_phase=ki_agent_tick) landen, hat aber ANDEREN Inhalt (n=99)
            # -> echte Kollision, NICHT ueberschreiben.
            {"date": "2026-10-23", "run_phase": "ki_agent_tick",
             "ts_utc": "2026-10-23T00:02:00+00:00", "n": 99},
        ]
        _write_jsonl(p, rows)
        hash_before = _sha256(p)
        stats = fix_jsonl(p, "ts_utc", ("run_phase",))

        _check("D1 Kollision erkannt (1 Paar)", stats["collisions"] == 1,
               detail=f"collisions={stats['collisions']}")
        _check("D2 0 tatsaechliche Korrekturen (Kollision blockiert)",
               stats["corrected"] == 0,
               detail=f"corrected={stats['corrected']}")
        hash_after = _sha256(p)
        _check("D3 Datei-Hash unveraendert (nichts ueberschrieben)",
               hash_before == hash_after)
        out_rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        _check("D4 beide Zeilen inhaltlich unveraendert stehen geblieben",
               out_rows[0]["n"] == 10 and out_rows[1]["n"] == 99 and
               out_rows[1]["date"] == "2026-10-23")
        _check("D5 kein .bak angelegt (corrected == 0)",
               not p.with_suffix(p.suffix + ".bak").exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _test_idempotency():
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        p = tmp / "fixture_idem.jsonl"
        rows = [
            {"date": "2026-10-23", "run_phase": "postclose",
             "ts_utc": "2026-10-23T00:30:00+00:00", "val": 1},
        ]
        _write_jsonl(p, rows)
        first = fix_jsonl(p, "ts_utc", ("run_phase",))
        _check("E1 erster Lauf korrigiert 1 Eintrag", first["corrected"] == 1)
        hash_after_first = _sha256(p)

        second = fix_jsonl(p, "ts_utc", ("run_phase",))
        _check("E2 zweiter Lauf korrigiert 0 Eintraege (idempotent)",
               second["corrected"] == 0,
               detail=f"corrected={second['corrected']}")
        hash_after_second = _sha256(p)
        _check("E3 Datei-Hash nach zweitem Lauf unveraendert",
               hash_after_first == hash_after_second)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _test_dry_run_writes_nothing():
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        p = tmp / "fixture_dryrun.jsonl"
        rows = [
            {"date": "2026-10-23", "run_phase": "postclose",
             "ts_utc": "2026-10-23T00:30:00+00:00", "val": 1},
        ]
        _write_jsonl(p, rows)
        hash_before = _sha256(p)
        stats = fix_jsonl(p, "ts_utc", ("run_phase",), dry_run=True)
        _check("G1 --dry-run meldet trotzdem die Korrektur",
               stats["corrected"] == 1)
        hash_after = _sha256(p)
        _check("G2 --dry-run schreibt NICHTS (Hash unveraendert)",
               hash_before == hash_after)
        _check("G3 --dry-run legt KEIN .bak an",
               not p.with_suffix(p.suffix + ".bak").exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _test_report_dict_of_points_readonly_and_detects_anomaly():
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        p = tmp / "fixture_dict.json"
        # 5 "normale" Handelstage mit je 2 Tickern + 1 gemergter Tag (10-20)
        # mit 4 Tickern -> Median=2, 4 > 2*1.3 -> anomal.
        normal_dates = ["2026-10-14", "2026-10-15", "2026-10-16",
                        "2026-10-19", "2026-10-21"]
        data: dict[str, list[dict]] = {}
        for i, tk in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE"]):
            data[tk] = [{"date": d} for d in normal_dates[:2]] if i == 0 else [
                {"date": normal_dates[i % len(normal_dates)]}]
        # Deterministisch und lesbar: Ticker -> Liste von Punkten, je 1 pro
        # normalem Tag (2 Ticker/Tag) + 4 Ticker am gemergten Tag 10-20.
        data = {
            "T1": [{"date": "2026-10-14"}, {"date": "2026-10-20"}],
            "T2": [{"date": "2026-10-14"}, {"date": "2026-10-20"}],
            "T3": [{"date": "2026-10-15"}, {"date": "2026-10-20"}],
            "T4": [{"date": "2026-10-15"}, {"date": "2026-10-20"}],
            "T5": [{"date": "2026-10-16"}],
            "T6": [{"date": "2026-10-16"}],
            "T7": [{"date": "2026-10-19"}],
            "T8": [{"date": "2026-10-19"}],
            "T9": [{"date": "2026-10-21"}],
            "T10": [{"date": "2026-10-21"}],
        }
        p.write_text(json.dumps(data), encoding="utf-8")
        hash_before = _sha256(p)
        stats = report_dict_of_points(p)
        hash_after = _sha256(p)
        _check("H1 report_dict_of_points schreibt NICHT (Hash unveraendert)",
               hash_before == hash_after)
        _check("H2 total_points korrekt gezaehlt", stats["total_points"] == 14,
               detail=f"total_points={stats['total_points']}")
        _check("H3 anomaler Tag 2026-10-20 (4 Ticker vs Median=2) erkannt",
               "2026-10-20" in stats.get("anomal_dates", {}),
               detail=f"anomal_dates={stats.get('anomal_dates')}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    _test_shift_and_already_correct_and_no_ts()
    _test_collision_not_overwritten()
    _test_idempotency()
    _test_dry_run_writes_nothing()
    _test_report_dict_of_points_readonly_and_detects_anomaly()

    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (Verschiebung, bereits-korrekt, ohne-ts, "
          "Kollision-Schutz, Idempotenz, --dry-run, Report-only-Lesepfad).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
