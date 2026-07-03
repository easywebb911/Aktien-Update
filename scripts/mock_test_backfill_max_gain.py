"""Mock-Tests für ``scripts/backfill_max_gain_pct.py``.

FIXTURE-ONLY — kein Kontakt mit ``backtest_history.json`` oder anderen Live-
Dateien; kein echter yfinance-Call. Deckt die pure-Python-Slice des Skripts ab
(Filter-Logik, Idempotenz, atomic-write-Pfad, Ein-Feld-Invariante,
Cron-Fenster-Guard). Die yfinance-abhängigen Funktionen (``bulk_fetch_ohlc``,
``compute_and_apply_backfill``) sind hier NICHT abgedeckt — sie leben in der
gleichen Klasse wie ``mock_test_max_gain_pct.py`` Slot B (pandas-abhängig,
CI-Slot-skip).

Verifiziert:
- (A) parse_entry_date / trading_days_since
- (B) select_targets: schema_v4-Filter, "already-has-max_gain_pct"-Idempotenz,
      Reifegrad-≥10, Datum-Parse-Fehler-Toleranz
- (C) apply_backfill_result: Ein-Feld-Invariante (nur ``max_gain_pct`` gesetzt,
      alle anderen Keys unverändert byte-identisch), None→False Guard
- (D) atomic_write_json: tmp-Datei-Zwischenstufe, ersetzt Ziel-Datei atomar,
      keine Half-Writes bei fehlgeschlagenem Format
- (E) in_cron_block_window: 06:17 UTC / 21:17 UTC ±30 Min = geblockt,
      12:00 UTC = frei, Distanz-Berechnung zyklisch über Mitternacht
- (F) CLI-Default = Dry-Run (kein --live-Flag → kein Schreibversuch)
- (G) Idempotenz: 2. select_targets nach Filling → leere Liste
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

import backfill_max_gain_pct as bmg  # noqa: E402


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def _make_entry(**overrides):
    """Basis-Alt-Record mit realistischen v4-Feldern (analog Live-Schema)."""
    e = {
        "date": "01.06.2026",
        "ticker": "TESTX",
        "score": 75,
        "entry_price": 10.50,
        "backtest_schema_version": 4,
        "rvol": 3.2,
        "return_3d": None,
        "return_5d": None,
        "return_10d": None,
        "max_drawdown_pct": -5.5,
        "market_regime": "neutral",
        "vix_level": 15.2,
    }
    e.update(overrides)
    return e


def main():
    # ═══════════════════════════════════════════════════════════════════════
    # (A) parse_entry_date / trading_days_since
    # ═══════════════════════════════════════════════════════════════════════
    print("── (A) parse_entry_date + trading_days_since ─────────────────")

    _check("A1 parse DD.MM.YYYY", bmg.parse_entry_date("01.06.2026") == date(2026, 6, 1))
    _check("A2 parse YYYY-MM-DD", bmg.parse_entry_date("2026-06-01") == date(2026, 6, 1))
    _check("A3 parse invalid → None", bmg.parse_entry_date("garbage") is None)
    _check("A4 parse leer → None", bmg.parse_entry_date("") is None)

    # Mo 15.06.2026 → Mo 29.06.2026 = 10 Trading-Days (2 volle Wochen)
    _check(
        "A5 trading_days_since Mo→Mo+14d = 10",
        bmg.trading_days_since(date(2026, 6, 15), date(2026, 6, 29)) == 10,
    )
    _check(
        "A6 trading_days_since gleicher Tag = 0",
        bmg.trading_days_since(date(2026, 6, 15), date(2026, 6, 15)) == 0,
    )
    _check(
        "A7 trading_days_since ref<entry = 0",
        bmg.trading_days_since(date(2026, 6, 15), date(2026, 6, 10)) == 0,
    )

    # ═══════════════════════════════════════════════════════════════════════
    # (B) select_targets — Filter-Logik
    # ═══════════════════════════════════════════════════════════════════════
    print("── (B) select_targets Filter ─────────────────────────────────")

    today = date(2026, 7, 2)
    history = [
        # 0: v4, reif, kein max_gain_pct → TARGET
        _make_entry(date="01.06.2026", ticker="AAA"),
        # 1: v4 aber bereits max_gain_pct → SKIP (idempotent)
        _make_entry(date="02.06.2026", ticker="BBB", max_gain_pct=25.5),
        # 2: schema_v=3 → SKIP
        _make_entry(date="01.06.2026", ticker="CCC", backtest_schema_version=3),
        # 3: schema_v fehlt → SKIP
        {"date": "01.06.2026", "ticker": "DDD", "score": 50},
        # 4: v4, aber < 10 Trading-Days reif (Entry 30.06., today 02.07.)
        _make_entry(date="30.06.2026", ticker="EEE"),
        # 5: v4, kaputtes Datum → SKIP
        _make_entry(date="not-a-date", ticker="FFF"),
        # 6: v4, reif, kein max_gain_pct → TARGET
        _make_entry(date="01.05.2026", ticker="GGG"),
        # 7: Not-a-dict → SKIP defensiv
        "junk",
    ]

    targets = bmg.select_targets(history, today)
    _check(
        "B1 exakt 2 Targets (AAA, GGG)",
        len(targets) == 2,
        f"got {len(targets)}",
    )
    tkrs = {e.get("ticker") for _, e, _ in targets}
    _check("B2 Target-Tickers = {AAA, GGG}", tkrs == {"AAA", "GGG"}, f"got {tkrs}")

    # Target-Index-Konsistenz — Records müssen in-place mutierbar sein.
    for i, e, _ in targets:
        _check(
            f"B3-idx{i} Reference-Identität mit history[i]",
            e is history[i],
        )

    # Idempotenz nach Fake-Fill: 2. select_targets → 0
    for i, e, _ in targets:
        e["max_gain_pct"] = 42.0
    targets_after = bmg.select_targets(history, today)
    _check(
        "B4 nach Fake-Fill: select_targets liefert 0 (idempotent)",
        len(targets_after) == 0,
        f"got {len(targets_after)}",
    )

    # ═══════════════════════════════════════════════════════════════════════
    # (C) apply_backfill_result — Ein-Feld-Invariante
    # ═══════════════════════════════════════════════════════════════════════
    print("── (C) apply_backfill_result: Ein-Feld-Invariante ────────────")

    e = _make_entry(ticker="HHH")
    keys_before = list(e.keys())
    values_before = {k: json.dumps(v, sort_keys=True) for k, v in e.items()}

    rc = bmg.apply_backfill_result(e, 33.75)
    _check("C1 return True bei mg=33.75", rc is True)
    _check("C2 max_gain_pct exakt gesetzt", e["max_gain_pct"] == 33.75)

    # ALLE anderen Keys müssen byte-identisch bleiben.
    for k in keys_before:
        _check(
            f"C3-{k} unverändert nach Backfill",
            json.dumps(e[k], sort_keys=True) == values_before[k],
            f"was {values_before[k]}, now {json.dumps(e[k], sort_keys=True)}",
        )
    _check(
        "C4 genau ein neuer Key (max_gain_pct)",
        set(e.keys()) - set(keys_before) == {"max_gain_pct"},
    )

    # None-Guard: kein Write, kein Feld.
    e2 = _make_entry(ticker="III")
    keys_before2 = set(e2.keys())
    rc2 = bmg.apply_backfill_result(e2, None)
    _check("C5 return False bei mg=None", rc2 is False)
    _check("C6 kein Feld hinzugefügt bei None", set(e2.keys()) == keys_before2)

    # ═══════════════════════════════════════════════════════════════════════
    # (D) atomic_write_json — tmp+replace, kein Half-Write
    # ═══════════════════════════════════════════════════════════════════════
    print("── (D) atomic_write_json ─────────────────────────────────────")

    with tempfile.TemporaryDirectory() as td:
        target = pathlib.Path(td) / "bt.json"
        data = [_make_entry(ticker="JJJ"), _make_entry(ticker="KKK")]

        # Ziel-Datei mit „alter" Version anlegen (simuliert bestehende Datei)
        target.write_text('[{"old": true}]', encoding="utf-8")

        bmg.atomic_write_json(target, data)

        read_back = json.loads(target.read_text(encoding="utf-8"))
        _check(
            "D1 Datei nach atomic_write vollständig gelesen",
            isinstance(read_back, list) and len(read_back) == 2,
        )
        _check(
            "D2 Inhalt entspricht data (Roundtrip)",
            read_back == data,
        )

        # tmp-Datei sollte NICHT mehr existieren (os.replace hat aufgeräumt)
        tmp = target.with_suffix(target.suffix + ".backfill.tmp")
        _check("D3 tmp-Datei nach Write nicht mehr da", not tmp.exists())

    # ═══════════════════════════════════════════════════════════════════════
    # (E) in_cron_block_window — Zeitfenster-Guard
    # ═══════════════════════════════════════════════════════════════════════
    print("── (E) in_cron_block_window ──────────────────────────────────")

    def _utc(hh, mm):
        return datetime(2026, 7, 2, hh, mm, 0, tzinfo=timezone.utc)

    # Premarket-Slot 06:17 UTC ±30 min = [05:47, 06:47)
    blocked, _ = bmg.in_cron_block_window(_utc(6, 17))
    _check("E1 06:17 UTC BLOCKED (Slot-Mitte)", blocked)
    # Semantik: `diff < window_min` (offene Grenzen) → effektiv (05:47, 06:47).
    blocked, _ = bmg.in_cron_block_window(_utc(5, 47))
    _check("E2 05:47 UTC FREE (Slot-Untergrenze exklusiv, diff=30=window)",
           not blocked)
    blocked, _ = bmg.in_cron_block_window(_utc(5, 48))
    _check("E3 05:48 UTC BLOCKED (knapp innerhalb, diff=29<30)", blocked)
    blocked, _ = bmg.in_cron_block_window(_utc(6, 46))
    _check("E4 06:46 UTC BLOCKED (kurz vor Ende, diff=29<30)", blocked)
    blocked, _ = bmg.in_cron_block_window(_utc(5, 46))
    _check("E5 05:46 UTC FREE (knapp außerhalb, diff=31>30)", not blocked)

    # Postclose-Slot 21:17 UTC ±30 min
    blocked, _ = bmg.in_cron_block_window(_utc(21, 17))
    _check("E6 21:17 UTC BLOCKED (Slot-Mitte)", blocked)
    blocked, _ = bmg.in_cron_block_window(_utc(12, 0))
    _check("E7 12:00 UTC FREE (Tag-Mitte)", not blocked)
    blocked, _ = bmg.in_cron_block_window(_utc(0, 30))
    _check("E8 00:30 UTC FREE (Nacht)", not blocked)

    # Zyklische Distanz-Berechnung (kein Cron-Slot bei 23:00 UTC)
    blocked, _ = bmg.in_cron_block_window(_utc(23, 30))
    _check("E9 23:30 UTC FREE (kein Slot nahe)", not blocked)

    # ═══════════════════════════════════════════════════════════════════════
    # (F) CLI-Default = Dry-Run, Fehlen von --live → kein Schreibversuch
    # ═══════════════════════════════════════════════════════════════════════
    print("── (F) CLI-Default = Dry-Run ─────────────────────────────────")

    with tempfile.TemporaryDirectory() as td:
        target = pathlib.Path(td) / "bt.json"
        # Realistisches Fixture: 3 Records, davon 2 als Targets
        data = [
            _make_entry(date="01.06.2026", ticker="LLL"),
            _make_entry(date="02.06.2026", ticker="MMM", max_gain_pct=10.0),
            _make_entry(date="03.06.2026", ticker="NNN"),
        ]
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        content_before = target.read_bytes()

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "backfill_max_gain_pct.py"),
             "--path", str(target)],
            capture_output=True, text=True,
        )
        _check("F1 Dry-Run Exit-Code 0", result.returncode == 0,
               f"stderr:\n{result.stderr[-400:]}")

        # Die Datei DARF NICHT geändert worden sein (auch nicht Byte-touch)
        content_after = target.read_bytes()
        _check("F2 Dry-Run: Ziel-Datei byte-identisch (kein Write)",
               content_before == content_after)

        # Log-Output enthält DRY-RUN-Marker
        _check("F3 Log enthält 'DRY-RUN'", "DRY-RUN" in result.stderr,
               f"stderr:\n{result.stderr[-400:]}")

        # keine tmp-Datei entstanden
        tmp = target.with_suffix(target.suffix + ".backfill.tmp")
        _check("F4 keine tmp-Datei im Dry-Run", not tmp.exists())

    # ═══════════════════════════════════════════════════════════════════════
    # (H) classify_outcome — Guardian-Finding-1: thin-slice vs echter Null-Gain
    # ═══════════════════════════════════════════════════════════════════════
    print("── (H) classify_outcome (Guardian-Finding 1) ──────────────────")

    # 4 Klassen: none / thin_slice / filled_zero / filled
    _check(
        "H1 mg=None → OUTCOME_NONE (unabhängig df_len)",
        bmg.classify_outcome(0, None) == bmg.OUTCOME_NONE
        and bmg.classify_outcome(10, None) == bmg.OUTCOME_NONE,
    )

    _check(
        "H2 mg=0.0 + df_len=0 → OUTCOME_THIN_SLICE (leerer Slice)",
        bmg.classify_outcome(0, 0.0) == bmg.OUTCOME_THIN_SLICE,
    )
    _check(
        "H3 mg=0.0 + df_len=1 → OUTCOME_THIN_SLICE (nur Entry-Tag-Bar)",
        bmg.classify_outcome(1, 0.0) == bmg.OUTCOME_THIN_SLICE,
    )
    _check(
        "H4 mg=0.0 + df_len=2 → OUTCOME_FILLED_ZERO (echter Null-Gain, min-Bars)",
        bmg.classify_outcome(2, 0.0) == bmg.OUTCOME_FILLED_ZERO,
    )
    _check(
        "H5 mg=0.0 + df_len=10 → OUTCOME_FILLED_ZERO (echter Null-Gain, volles Fenster)",
        bmg.classify_outcome(10, 0.0) == bmg.OUTCOME_FILLED_ZERO,
    )
    _check(
        "H6 mg=25.5 + df_len=5 → OUTCOME_FILLED (echter Gewinn)",
        bmg.classify_outcome(5, 25.5) == bmg.OUTCOME_FILLED,
    )
    _check(
        "H7 mg=0.01 + df_len=1 → OUTCOME_FILLED (≠0.0, Klassifikation unabh. von len)",
        bmg.classify_outcome(1, 0.01) == bmg.OUTCOME_FILLED,
    )
    # Konstanten sind verschieden (kein Alias-Fehler)
    outcomes = {bmg.OUTCOME_NONE, bmg.OUTCOME_THIN_SLICE,
                bmg.OUTCOME_FILLED_ZERO, bmg.OUTCOME_FILLED}
    _check("H8 4 distinkte OUTCOME_*-Konstanten", len(outcomes) == 4)

    # Source-Grep: compute_and_apply_backfill trägt den Zähler
    src = (ROOT / "scripts" / "backfill_max_gain_pct.py").read_text(encoding="utf-8")
    _check(
        "H9 compute_and_apply_backfill returnt 3-Tupel (n_filled, n_skipped, n_thin_slice)",
        "n_thin_slice: int = 0" in src or "n_thin_slice = 0" in src,
    )
    _check(
        "H10 Live-Log-Zeile für thin-slice vorhanden (log.warning bei > 0)",
        "n_thin_slice > 0" in src and "log.warning" in src,
    )

    # ═══════════════════════════════════════════════════════════════════════
    # (G) Import-Isolation — _compute_max_gain_pct wird IMPORTIERT nicht dupliziert
    # ═══════════════════════════════════════════════════════════════════════
    print("── (G) Import-Isolation — Drift-Schutz ───────────────────────")

    src = (ROOT / "scripts" / "backfill_max_gain_pct.py").read_text(encoding="utf-8")
    _check(
        "G1 kein `def _compute_max_gain_pct` im Skript (kein Duplikat)",
        "def _compute_max_gain_pct" not in src,
        "der Helper wird aus backtest_history importiert, nicht dupliziert",
    )
    _check(
        "G2 Import 'from backtest_history import _compute_max_gain_pct' vorhanden",
        "from backtest_history import _compute_max_gain_pct" in src,
    )
    _check(
        "G3 Nur EIN Feld gesetzt (grep 'entry[\"max_gain_pct\"]' oder ähnliches — kein anderes e[...]-Set)",
        'entry["max_gain_pct"] = mg' in src
        and 'entry["max_drawdown_pct"]' not in src
        and 'entry["score"]' not in src
        and 'entry["return_' not in src,
    )
    _check(
        "G4 Cron-Slots-Konstante enthält (6,17) und (21,17)",
        "(6, 17)" in src and "(21, 17)" in src,
    )

    # ── Ergebnis ─────────────────────────────────────────────────────────────
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print(f"✓ Alle Tests bestanden (Filter/Idempotenz/Ein-Feld-Invariante/"
          f"atomic-write/Cron-Guard/CLI-Dry-Run-Default/Import-Isolation).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
