"""Mock-Tests für ``scripts/backfill_entry_past_return_5d.py``.

FIXTURE-ONLY — kein Kontakt mit ``backtest_history.json``, kein echter yfinance-
Call. Deckt die pure-Python-Slice ab (Filter/Idempotenz/atomic-write/Ein-Feld-
Invariante/Cron-Guard/CLI-Dry-Run/Gate-Urteil). Die yfinance-abhängigen
Funktionen (``bulk_fetch_ohlc``, ``build_df_upto``, ``extract_entry_closes``,
``compute_and_apply_backfill``, ``run_consistency_gate``, ``_do_undo``) sind
pandas-abhängig → Source-Inspektion statt Live-Lauf (§8u).

Verifiziert:
- (A) parse_entry_date
- (B) select_targets: v4-Filter, **is-None-Semantik** (absent UND present-None
      beide Targets), non-null skip, KEIN Reifegrad (recent = Target), pre-v4
      ausgeschlossen, Datum-Parse-Toleranz, Nicht-dict-Toleranz
- (C) apply_backfill_result: Ein-Feld-Invariante, None→False
- (D) atomic_write_json: tmp+replace
- (E) in_cron_block_window: 06:17/21:17 UTC ±30
- (F) CLI-Default = Dry-Run (kein Write)
- (G) Import-Isolation: _compute_entry_past_return_5d IMPORTIERT nicht dupliziert;
      NUR entry_past_return_5d gesetzt; NIE entry_price als Zähler
- (H) classify_outcome: filled/no_data/few_bars (strikte None-Semantik)
- (I) gate_passed: PASS nur bei 0 Mismatch UND ≥ Floor verifiziert
- (J) Idempotenz: 2. select_targets nach Fill → 0
- (K) Konsistenz-Gate + Rückweg + Look-Ahead source-verankert
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import backfill_entry_past_return_5d as bpr  # noqa: E402

_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail and not cond:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def _make_entry(**overrides):
    e = {
        "date": "01.06.2026", "ticker": "TESTX", "score": 75,
        "entry_price": 10.50, "backtest_schema_version": 4, "rvol": 3.2,
        "return_10d": 12.3, "market_regime": "neutral", "vix_level": 15.2,
    }
    e.update(overrides)
    return e


def main():
    print("── (A) parse_entry_date ──────────────────────────────────────")
    _check("A1 DD.MM.YYYY", bpr.parse_entry_date("01.06.2026") == date(2026, 6, 1))
    _check("A2 YYYY-MM-DD", bpr.parse_entry_date("2026-06-01") == date(2026, 6, 1))
    _check("A3 garbage → None", bpr.parse_entry_date("x") is None)
    _check("A4 leer → None", bpr.parse_entry_date("") is None)

    print("── (B) select_targets: is-None + kein Reifegrad + v4-only ─────")
    history = [
        # 0: v4, KEY ABSENT (kein entry_past_return_5d) → TARGET
        _make_entry(date="01.06.2026", ticker="AAA"),
        # 1: v4, present-None → TARGET (zweiter Versuch)
        _make_entry(date="02.06.2026", ticker="BBB", entry_past_return_5d=None),
        # 2: v4, non-null → SKIP (idempotent, nie überschreiben)
        _make_entry(date="03.06.2026", ticker="CCC", entry_past_return_5d=4.2),
        # 3: schema_v=3 → SKIP (pre-v4 ausgeschlossen)
        _make_entry(date="01.06.2026", ticker="DDD", backtest_schema_version=3,
                    entry_past_return_5d=None),
        # 4: schema_v fehlt → SKIP
        {"date": "01.06.2026", "ticker": "EEE"},
        # 5: v4, RECENT (heute) OHNE Wert → TARGET (KEIN Reifegrad-Filter!)
        _make_entry(date=date.today().strftime("%d.%m.%Y"), ticker="FFF"),
        # 6: v4, kaputtes Datum → SKIP
        _make_entry(date="not-a-date", ticker="GGG"),
        # 7: not-a-dict → SKIP
        "junk",
    ]
    targets = bpr.select_targets(history)
    tkrs = {e.get("ticker") for _, e, _ in targets}
    _check("B1 Targets = {AAA, BBB, FFF} (absent+None+recent)",
           tkrs == {"AAA", "BBB", "FFF"}, f"got {tkrs}")
    _check("B2 non-null CCC NICHT Target", "CCC" not in tkrs)
    _check("B3 pre-v4 DDD NICHT Target (v4-only scope)", "DDD" not in tkrs)
    _check("B4 recent FFF IST Target (kein Reifegrad-Filter)", "FFF" in tkrs)
    for i, e, _ in targets:
        _check(f"B5-idx{i} Reference-Identität mit history[i]", e is history[i])
    # collect_nonnull_records → nur CCC
    nn = bpr.collect_nonnull_records(history)
    _check("B6 collect_nonnull_records = {CCC}",
           {e.get("ticker") for _, e, _ in nn} == {"CCC"})

    print("── (C) apply_backfill_result: Ein-Feld-Invariante ────────────")
    e = _make_entry(ticker="HHH")
    keys_before = list(e.keys())
    vals_before = {k: json.dumps(v, sort_keys=True) for k, v in e.items()}
    rc = bpr.apply_backfill_result(e, -4.85)
    _check("C1 return True bei val=-4.85", rc is True)
    _check("C2 entry_past_return_5d exakt gesetzt", e["entry_past_return_5d"] == -4.85)
    for k in keys_before:
        _check(f"C3-{k} unverändert",
               json.dumps(e[k], sort_keys=True) == vals_before[k])
    _check("C4 genau ein neuer Key",
           set(e.keys()) - set(keys_before) == {"entry_past_return_5d"})
    e2 = _make_entry(ticker="III")
    kb2 = set(e2.keys())
    _check("C5 return False bei None", bpr.apply_backfill_result(e2, None) is False)
    _check("C6 kein Feld bei None", set(e2.keys()) == kb2)

    print("── (D) atomic_write_json ─────────────────────────────────────")
    with tempfile.TemporaryDirectory() as td:
        target = pathlib.Path(td) / "bt.json"
        data = [_make_entry(ticker="JJJ"), _make_entry(ticker="KKK")]
        target.write_text('[{"old": true}]', encoding="utf-8")
        bpr.atomic_write_json(target, data)
        rb = json.loads(target.read_text(encoding="utf-8"))
        _check("D1 vollständig gelesen", isinstance(rb, list) and len(rb) == 2)
        _check("D2 Roundtrip", rb == data)
        tmp = target.with_suffix(target.suffix + ".eprbackfill.tmp")
        _check("D3 tmp weg", not tmp.exists())

    print("── (E) in_cron_block_window ──────────────────────────────────")
    def _utc(hh, mm): return datetime(2026, 7, 2, hh, mm, tzinfo=timezone.utc)
    _check("E1 06:17 BLOCKED", bpr.in_cron_block_window(_utc(6, 17))[0])
    _check("E2 05:47 FREE (Grenze exkl.)", not bpr.in_cron_block_window(_utc(5, 47))[0])
    _check("E3 05:48 BLOCKED", bpr.in_cron_block_window(_utc(5, 48))[0])
    _check("E4 21:17 BLOCKED", bpr.in_cron_block_window(_utc(21, 17))[0])
    _check("E5 12:00 FREE", not bpr.in_cron_block_window(_utc(12, 0))[0])
    _check("E6 23:30 FREE (zyklisch, kein Slot)", not bpr.in_cron_block_window(_utc(23, 30))[0])

    print("── (F) CLI-Default = Dry-Run (kein Write) ────────────────────")
    with tempfile.TemporaryDirectory() as td:
        target = pathlib.Path(td) / "bt.json"
        data = [_make_entry(date="01.06.2026", ticker="LLL"),
                _make_entry(date="02.06.2026", ticker="MMM", entry_past_return_5d=10.0),
                _make_entry(date="03.06.2026", ticker="NNN")]
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        before = target.read_bytes()
        res = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "backfill_entry_past_return_5d.py"),
             "--path", str(target)],
            capture_output=True, text=True)
        _check("F1 Dry-Run Exit 0", res.returncode == 0, res.stderr[-400:])
        _check("F2 Datei byte-identisch (kein Write)", before == target.read_bytes())
        _check("F3 Log enthält 'DRY-RUN'", "DRY-RUN" in res.stderr)
        _check("F4 keine tmp-Datei",
               not target.with_suffix(target.suffix + ".eprbackfill.tmp").exists())

    print("── (G) Import-Isolation + kein entry_price als Zähler ─────────")
    src = (ROOT / "scripts" / "backfill_entry_past_return_5d.py").read_text(encoding="utf-8")
    _check("G1 kein `def _compute_entry_past_return_5d` (kein Duplikat)",
           "def _compute_entry_past_return_5d" not in src)
    _check("G2 Import aus backtest_history",
           "from backtest_history import _compute_entry_past_return_5d" in src)
    _check("G3 NUR entry_past_return_5d gesetzt (via FIELD-Konstante)",
           'entry[FIELD] = val' in src and 'entry["score"]' not in src
           and 'entry["return_' not in src)
    _extract_body = src.split("def extract_entry_closes")[1].split("\ndef ")[0]
    _check("G4 Zähler = Adj-Close iloc[-1] aus Fetch; KEIN entry_price-ZUGRIFF",
           '["Close"].iloc[-1]' in _extract_body
           and '["entry_price"]' not in _extract_body
           and '"entry_price")' not in _extract_body,
           "extract_entry_closes darf entry_price nicht LESEN (Docstring-Warnung ok)")
    _check("G5 Cron-Slots (6,17)+(21,17)", "(6, 17)" in src and "(21, 17)" in src)

    print("── (H) classify_outcome (strikte None-Semantik) ──────────────")
    _check("H1 val≠None → filled",
           bpr.classify_outcome(6, 3.5) == bpr.OUTCOME_FILLED)
    _check("H2 val None + <6 Bars → few_bars",
           bpr.classify_outcome(3, None) == bpr.OUTCOME_FEW_BARS)
    _check("H3 val None + ≥6 Bars → no_data",
           bpr.classify_outcome(10, None) == bpr.OUTCOME_NO_DATA)
    _check("H4 val 0.0 → filled (echte Null-Bewegung, KEIN 0.0-Overload)",
           bpr.classify_outcome(6, 0.0) == bpr.OUTCOME_FILLED)
    _check("H5 3 distinkte Konstanten",
           len({bpr.OUTCOME_FILLED, bpr.OUTCOME_NO_DATA, bpr.OUTCOME_FEW_BARS}) == 3)

    print("── (I) gate_passed: PASS nur bei 0 Mismatch UND ≥ Floor ──────")
    _check("I1 0 Mismatch + genug verifiziert → PASS",
           bpr.gate_passed(30, 30, 0)[0] is True)
    _check("I2 1 Mismatch → FAIL",
           bpr.gate_passed(30, 29, 1)[0] is False)
    _check("I3 zu wenige verifiziert (< Floor) → FAIL (inkonklusiv)",
           bpr.gate_passed(10, 10, 0)[0] is False)
    _check("I4 exakt Floor → PASS",
           bpr.gate_passed(bpr.GATE_MIN_VERIFY, bpr.GATE_MIN_VERIFY, 0)[0] is True)

    print("── (J) Idempotenz ────────────────────────────────────────────")
    hist2 = [_make_entry(date="01.06.2026", ticker="AAA")]
    t1 = bpr.select_targets(hist2)
    for _, e, _ in t1:
        e["entry_past_return_5d"] = 7.0
    _check("J1 nach Fill: select_targets = 0",
           len(bpr.select_targets(hist2)) == 0)

    print("── (K) Gate/Rückweg/Look-Ahead source-verankert ──────────────")
    _check("K1 Konsistenz-Gate als harte Live-Vorbedingung (Abort bei FAIL)",
           "GATE FAILED" in src and "run_consistency_gate" in src)
    _check("K2 --undo-Rückweg vorhanden (chirurgisch)",
           '"--undo"' in src and "_do_undo" in src)
    _check("K3 Rückwärts-Slice (index.date <= edate), nicht vorwärts",
           "df.index.date <= edate" in src)
    _check("K4 EXPLORATIV/IN-SAMPLE-Framing im Docstring (kein Overselling)",
           "IN-SAMPLE" in src and "NICHT" in src and "OoS" in src)

    print("── (L) --undo Manifest-basiert: OoS-Record SURVIVES (Guardian-Fix) ──")
    # KERN: _do_undo darf NUR Manifest-Records nullen, NIE einen vorwärts
    # gesammelten Live-Record — auch wenn dessen Wert identisch aussieht.
    hist_undo = [
        # backfill-gefüllt (im Manifest) → muss genullt werden
        _make_entry(date="14.05.2026", ticker="OLD1", entry_past_return_5d=8.8),
        _make_entry(date="20.05.2026", ticker="OLD2", entry_past_return_5d=-3.1),
        # VORWÄRTS gesammelt (NICHT im Manifest), gleicher Wert wie OLD1 →
        # Recompute-Ansatz hätte das mit-genullt; Manifest-Ansatz NICHT.
        _make_entry(date="14.07.2026", ticker="FWD", entry_past_return_5d=8.8),
    ]
    manifest = [{"ticker": "OLD1", "date": "14.05.2026"},
                {"ticker": "OLD2", "date": "20.05.2026"}]
    n_undone = bpr._do_undo(hist_undo, manifest)
    _check("L1 exakt 2 Manifest-Records genullt", n_undone == 2, f"got {n_undone}")
    _check("L2 OLD1 → None", hist_undo[0]["entry_past_return_5d"] is None)
    _check("L3 OLD2 → None", hist_undo[1]["entry_past_return_5d"] is None)
    _check("L4 FWD (vorwärts, NICHT im Manifest) BLEIBT 8.8 (OoS geschützt!)",
           hist_undo[2]["entry_past_return_5d"] == 8.8)
    # leeres Manifest → nichts genullt (kein Raten)
    hist2 = [_make_entry(ticker="X", entry_past_return_5d=5.0)]
    _check("L5 leeres Manifest → 0 genullt", bpr._do_undo(hist2, []) == 0)
    _check("L6 X unangetastet bei leerem Manifest",
           hist2[0]["entry_past_return_5d"] == 5.0)
    # merge_manifest: Union + Dedup
    merged = bpr.merge_manifest(
        [{"ticker": "A", "date": "01.01.2026"}],
        [{"ticker": "A", "date": "01.01.2026"}, {"ticker": "B", "date": "02.01.2026"}])
    _check("L7 merge_manifest dedupliziert (A einmal, B neu)",
           len(merged) == 2
           and {(m["ticker"], m["date"]) for m in merged}
               == {("A", "01.01.2026"), ("B", "02.01.2026")})
    # load_manifest: fehlende Datei → []
    _check("L8 load_manifest(nicht-existent) → []",
           bpr.load_manifest(pathlib.Path("/nonexistent/xyz.json")) == [])
    # source: --undo verweigert ohne Manifest; kein Recompute im undo
    _check("L9 --undo verweigert ohne Manifest (kein Raten)",
           "Kein Manifest" in src)
    _check("L10 _do_undo nutzt KEINEN Recompute (rein Manifest/Dict)",
           "_compute_entry_past_return_5d" not in
           src.split("def _do_undo")[1].split("\ndef ")[0])

    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (Filter/is-None/kein-Reifegrad/Ein-Feld/"
          "atomic/Cron/Dry-Run/Import-Isolation/Gate-Urteil/Idempotenz).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
