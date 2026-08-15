"""Mock-Tests für den Backtest-History-Schreibpfad — NaN-Wurzel-Fix (15.08.2026).

Hintergrund: die 15.08.2026-Diagnose fand 8 nackte JSON-``NaN``-Token in
``backtest_history.json`` (2 Felder × 4 Records), die der Browser-
``JSON.parse`` ablehnt ("SyntaxError: The string did not match the
expected pattern"). Wurzel: ``_extract_hist_5d`` (generate_report.py)
liest yfinance-OHLCV-Zellen via ``row.get("Volume", 0) or 0`` — eine
vorhandene-aber-NaN-Zelle wird NICHT ersetzt (``.get(key, default)``
greift nur bei fehlendem Label; ``NaN or 0`` bleibt ``NaN``, weil NaN in
Python truthy ist). Die NaN lief unbemerkt durch zwei weitere Guards
(``_compute_rvol_buildup_5d``/``_compute_vol_stability_5d``, beide
``<= 0``-Form) bis in ``_compute_coiled_spring_score`` (``is None``-Form),
wo sie sich sogar zu einem STILLEN Fake-``0.0`` auflöste, bevor
``_save_backtest_history`` sie ungeprüft via ``json.dump`` schrieb.

Dieser PR fixt NUR den Schreibpfad für ZUKÜNFTIGE Records. Die vier
bereits betroffenen Bestands-Records (ARCT/COLL/GO/IBTA, 13.08.2026)
werden hier bewusst NICHT angefasst (eigener PR, §4-Flagging nötig).

Tests:
  1. ``_extract_hist_5d`` (Replik, Quelltext-Deckung gegen generate_report.py):
     NaN/Inf in EINER Zelle verwirft den GESAMTEN Tag (nicht nur die
     Zelle); < 5 gültige Tage → leere Liste; alle-valide unverändert.
  2. ``_save_backtest_history`` (echte Extraktion aus backtest_history.py):
     schreibt atomar (tmp + os.replace), keine .tmp-Leiche danach.
  3. ``_sanitize_backtest_entries_for_write`` (echte Extraktion): NaN/Inf
     → null, mit Pflicht-Log (Ticker/Datum/Feldpfad), auch verschachtelt;
     saubere Records bleiben unverändert + kein Log.
  4. End-to-End-Mechanik (Exzellenz-Selbstprüfung Punkt 1 des Auftrags):
     eine NaN-Volumenzelle darf am Ende weder als NaN noch als stille
     0.0 landen, sondern als ``None`` — durch den ECHTEN Pfad
     (Extraktion → Buildup/Stability → CoiledSpring → Sanitizer), nicht
     am Guard vorbei.

Ausführung: ``python scripts/mock_test_backtest_history_writepath.py``.
"""
from __future__ import annotations

import json
import logging
import math
import pathlib
import re
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

src_gr = (ROOT / "generate_report.py").read_text(encoding="utf-8")
src_bh = (ROOT / "backtest_history.py").read_text(encoding="utf-8")


# === Source-Extraktion (backtest_history.py) — kein Import (zieht yfinance) ==

def _extract(func_def: str) -> str:
    pat = rf"^def {re.escape(func_def)}\([\s\S]+?(?=^def\s|^class\s|^# ====)"
    m = re.search(pat, src_bh, re.MULTILINE)
    assert m, f"{func_def} nicht in backtest_history.py gefunden"
    return m.group(0)


helpers_src = (
    _extract("_finite")
    + "\n"
    + _extract("_compute_rvol_buildup_5d")
    + "\n"
    + _extract("_compute_vol_stability_5d")
    + "\n"
    + _extract("_compute_coiled_spring_score")
    + "\n"
    + _extract("_sanitize_backtest_entries_for_write")
    + "\n"
    + _extract("_save_backtest_history")
)

ns: dict = {
    "json": json,
    "math": math,
    "log": logging.getLogger("mock_test_backtest_history_writepath"),
}
exec(
    "from config import (\n"
    "    EARLINESS_TREND_LOG_WINDOW_DAYS,\n"
    "    EARLINESS_TREND_SI_SLOPE_CAP,\n"
    "    EARLINESS_TREND_VOL_STAB_CAP,\n"
    ")\n" + helpers_src,
    ns,
)
_finite         = ns["_finite"]
_rvol_buildup   = ns["_compute_rvol_buildup_5d"]
_vol_stability  = ns["_compute_vol_stability_5d"]
_coiled_spring  = ns["_compute_coiled_spring_score"]
_sanitize_fn    = ns["_sanitize_backtest_entries_for_write"]
_save_fn        = ns["_save_backtest_history"]


class _FakeLog:
    """Zeichnet log.warning-Aufrufe auf, ohne echtes Logging-Setup."""
    def __init__(self):
        self.warnings: list[str] = []

    def warning(self, msg, *args):
        self.warnings.append(msg % args if args else msg)


# === 1 — _extract_hist_5d (Replik + Quelltext-Deckung) ======================
#
# _extract_hist_5d ist eine NESTED Closure in generate_report.py (kein
# Top-Level-``def`` → nicht via Regex-Extraktion + exec erreichbar wie die
# backtest_history.py-Helper). Die Replik unten ist Zeile für Zeile
# identisch zur echten Implementierung; Quelltext-Assertions unten
# verriegeln, dass die echte Implementierung nicht divergiert.

EARLINESS_TREND_LOG_WINDOW_DAYS = 5


def _extract_hist_5d(df) -> list:
    """Replik von generate_report._extract_hist_5d (Quelltext-Deckung s.u.)."""
    try:
        tail = df.tail(EARLINESS_TREND_LOG_WINDOW_DAYS)
        if len(tail) < EARLINESS_TREND_LOG_WINDOW_DAYS:
            return []
        out = []
        for _, row in tail.iterrows():
            try:
                vol = float(row.get("Volume"))
                hi  = float(row.get("High"))
                lo  = float(row.get("Low"))
                cl  = float(row.get("Close"))
            except (TypeError, ValueError):
                continue
            if not (_finite(vol) and _finite(hi) and _finite(lo) and _finite(cl)):
                continue
            out.append({"volume": vol, "high": hi, "low": lo, "close": cl})
        if len(out) < EARLINESS_TREND_LOG_WINDOW_DAYS:
            return []
        return out
    except Exception:
        return []


class _FakeRow(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


class _FakeDF:
    """Minimal-Stand-in für ein pandas-tail()/iterrows()-Objekt."""
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def tail(self, n):
        return _FakeDF(self._rows[-n:])

    def __len__(self):
        return len(self._rows)

    def iterrows(self):
        return ((i, _FakeRow(r)) for i, r in enumerate(self._rows))


def _make_valid_rows(n=5):
    return [
        {"Volume": 1_000_000 + i, "High": 10.5 + i, "Low": 9.5 + i, "Close": 10.0 + i}
        for i in range(n)
    ]


def test_extract_hist_5d_all_valid_unchanged():
    """Regression: der Normalfall (alle Zellen endlich) bleibt unverändert."""
    df = _FakeDF(_make_valid_rows(5))
    result = _extract_hist_5d(df)
    assert len(result) == 5, result
    assert result[0] == {"volume": 1_000_000.0, "high": 10.5, "low": 9.5, "close": 10.0}


def test_extract_hist_5d_single_nan_volume_drops_whole_day():
    rows = _make_valid_rows(5)
    rows[2]["Volume"] = float("nan")
    df = _FakeDF(rows)
    result = _extract_hist_5d(df)
    assert result == [], (
        "eine NaN-Zelle mitten im Fenster muss den GESAMTEN Tag verwerfen, "
        f"nicht nur die Zelle -> < 5 gültige Tage -> leere Liste; bekam {result!r}")


def test_extract_hist_5d_partial_field_nan_drops_whole_day_not_cell():
    """Die ehrlichere Variante: NaN NUR in 'close' (3 andere Felder valide)
    entfernt trotzdem den GESAMTEN Tag — kein Fake-Wert für die eine
    kaputte Zelle, kein 4-von-5-Tage-Fenster mit Lücke."""
    rows = _make_valid_rows(5)
    rows[0]["Close"] = float("nan")
    df = _FakeDF(rows)
    result = _extract_hist_5d(df)
    assert result == [], result


def test_extract_hist_5d_inf_cell_also_dropped():
    rows = _make_valid_rows(5)
    rows[4]["High"] = float("inf")
    df = _FakeDF(rows)
    assert _extract_hist_5d(df) == []


def test_extract_hist_5d_insufficient_raw_rows_returns_empty():
    """< 5 Rohtage (bestehendes Verhalten, unverändert)."""
    df = _FakeDF(_make_valid_rows(3))
    assert _extract_hist_5d(df) == []


def test_extract_hist_5d_missing_column_treated_as_invalid_day():
    """Fehlende Spalte -> row.get(...) liefert None -> float(None) wirft
    TypeError -> Tag wird verworfen (nicht als 0.0 vorgetäuscht)."""
    rows = _make_valid_rows(5)
    del rows[1]["Volume"]
    df = _FakeDF(rows)
    assert _extract_hist_5d(df) == []


def test_extract_hist_5d_source_no_longer_has_or_zero_gotcha():
    """Quelltext-Deckung: die alte 'row.get(\"Volume\", 0) or 0'-Falle
    (NaN ist truthy -> keine Ersetzung) ist aus generate_report.py raus."""
    assert 'row.get("Volume", 0) or 0)' not in src_gr
    assert 'row.get("High",   0) or 0)' not in src_gr
    assert 'row.get("Low",    0) or 0)' not in src_gr
    assert 'row.get("Close",  0) or 0)' not in src_gr


def test_extract_hist_5d_source_uses_finite_guard():
    """Quelltext-Deckung: _extract_hist_5d prüft jede Zelle mit _finite()."""
    seg = src_gr[src_gr.find("def _extract_hist_5d("):
                  src_gr.find("def _hist_stats(")]
    assert seg, "generate_report.py-Struktur verändert — Segment-Suche angepasst?"
    assert "_finite(vol) and _finite(hi) and _finite(lo) and _finite(cl)" in seg
    assert "if len(out) < EARLINESS_TREND_LOG_WINDOW_DAYS:" in seg


# === 2 — _save_backtest_history: atomarer Write ==============================

def test_save_backtest_history_writes_atomically():
    tmpdir = tempfile.mkdtemp(prefix="bt_writepath_")
    try:
        target = pathlib.Path(tmpdir) / "backtest_history.json"
        ns["BACKTEST_FILE"] = str(target)
        entries = [{"date": "01.01.2026", "ticker": "TEST", "score": 50.0}]
        _save_fn(entries)
        assert target.exists(), "Zieldatei wurde nicht geschrieben"
        tmp_leftover = pathlib.Path(str(target) + ".tmp")
        assert not tmp_leftover.exists(), (
            "tmp-Datei nicht aufgeräumt — os.replace wurde nicht erreicht?")
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data == entries, data
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_save_backtest_history_source_uses_os_replace():
    """Quelltext-Deckung: kein reines open(BACKTEST_FILE, 'w') mehr direkt
    auf dem Zielpfad — Schreib-Sicherheit analog den Schwester-Writern."""
    assert "os.replace(tmp, BACKTEST_FILE)" in src_bh
    seg = src_bh[src_bh.find("def _save_backtest_history("):
                 src_bh.find("def _load_wiki_ticker_map(")]
    assert 'open(BACKTEST_FILE, "w"' not in seg, (
        "_save_backtest_history schreibt noch direkt aufs Ziel statt auf tmp")


# === 3 — _sanitize_backtest_entries_for_write: LAUTES zweites Netz ==========

def test_sanitizer_replaces_nan_with_null_and_logs():
    fake_log = _FakeLog()
    ns["log"] = fake_log
    entries = [{
        "date": "13.08.2026", "ticker": "ARCT", "score": 71.72,
        "rvol_buildup_5d": float("nan"),
        "vol_stability_5d": float("nan"),
        "coiled_spring_score": 0.0,
    }]
    sanitized = _sanitize_fn(entries)
    assert sanitized[0]["rvol_buildup_5d"] is None
    assert sanitized[0]["vol_stability_5d"] is None
    assert sanitized[0]["coiled_spring_score"] == 0.0, "echte 0.0 darf nicht angefasst werden"
    assert len(fake_log.warnings) == 2, fake_log.warnings
    assert any("ARCT" in w and "13.08.2026" in w and "rvol_buildup_5d" in w
               for w in fake_log.warnings), fake_log.warnings
    assert any("ARCT" in w and "vol_stability_5d" in w for w in fake_log.warnings), fake_log.warnings


def test_sanitizer_replaces_inf_with_null_and_logs():
    fake_log = _FakeLog()
    ns["log"] = fake_log
    entries = [{"date": "01.01.2026", "ticker": "INFX", "x": float("inf")}]
    sanitized = _sanitize_fn(entries)
    assert sanitized[0]["x"] is None
    assert len(fake_log.warnings) == 1
    assert "INFX" in fake_log.warnings[0]


def test_sanitizer_handles_nested_dict_field_path():
    fake_log = _FakeLog()
    ns["log"] = fake_log
    entries = [{
        "date": "14.08.2026", "ticker": "ZZZZ",
        "entry_components": {"rvol_buildup_5d": float("nan"), "si_trend_5d": 75.0},
    }]
    sanitized = _sanitize_fn(entries)
    assert sanitized[0]["entry_components"]["rvol_buildup_5d"] is None
    assert sanitized[0]["entry_components"]["si_trend_5d"] == 75.0
    assert len(fake_log.warnings) == 1
    assert "entry_components.rvol_buildup_5d" in fake_log.warnings[0], fake_log.warnings
    assert "ZZZZ" in fake_log.warnings[0] and "14.08.2026" in fake_log.warnings[0]


def test_sanitizer_handles_nan_inside_tuple():
    """Guardian-Finding 15.08.2026: Tupel fielen vorher durch alle
    isinstance-Checks unverändert durch (kein Live-Risiko im heutigen
    Datenmodell, aber eine strukturelle Lücke im 'letzten Netz'). Nach
    dem Fix wird ein Tupel wie eine Liste rekursiert und als Liste
    zurückgegeben (JSON kennt ohnehin keine Tupel)."""
    fake_log = _FakeLog()
    ns["log"] = fake_log
    entries = [{"date": "15.08.2026", "ticker": "TUPX", "pair": (1.0, float("nan"))}]
    sanitized = _sanitize_fn(entries)
    assert sanitized[0]["pair"] == [1.0, None], sanitized[0]["pair"]
    assert len(fake_log.warnings) == 1
    assert "pair[1]" in fake_log.warnings[0], fake_log.warnings


def test_sanitizer_no_op_and_silent_on_clean_entries():
    """LAUT nur beim Treffer — sauberer Bestand erzeugt KEIN Log."""
    fake_log = _FakeLog()
    ns["log"] = fake_log
    entries = [{"date": "01.01.2026", "ticker": "OK", "score": 42.0,
                "sub": {"x": 1}, "lst": [1, 2, {"y": 3.0}]}]
    sanitized = _sanitize_fn(entries)
    assert sanitized == entries
    assert fake_log.warnings == []


def test_sanitizer_source_never_silent():
    """Quelltext-Deckung: der Sanitizer ruft log.warning — kein stiller Pfad."""
    seg = src_bh[src_bh.find("def _sanitize_backtest_entries_for_write("):
                 src_bh.find("def _save_backtest_history(")]
    assert "log.warning(" in seg
    assert "ticker=%s date=%s field=%s value=%r" in seg


# === 4 — End-to-End-Mechanik (Selbstprüfung Punkt 1) ========================

def test_end_to_end_nan_volume_cell_yields_none_not_nan_not_fake_zero():
    """SELBSTPRÜFUNG (Exzellenz-Punkt 1 des Auftrags 15.08.2026): eine
    NaN-Volumenzelle im 5-Tage-Fenster darf am Ende weder als NaN NOCH
    als stille 0.0 im Record landen, sondern als None — durch den
    ECHTEN Pfad (Extraktion -> Buildup/Stability -> CoiledSpring ->
    Sanitizer-Serialisierung), nicht am Guard vorbei."""
    rows = _make_valid_rows(5)
    rows[2]["Volume"] = float("nan")
    df = _FakeDF(rows)

    hist_5d = _extract_hist_5d(df)
    assert hist_5d == [], "NaN-Zelle muss den ganzen Tag verwerfen -> Fenster unvollständig"

    volumes_5d = [d.get("volume", 0) for d in hist_5d]
    highs_5d   = [d.get("high",   0) for d in hist_5d]
    lows_5d    = [d.get("low",    0) for d in hist_5d]
    closes_5d  = [d.get("close",  0) for d in hist_5d]

    rvol_buildup  = _rvol_buildup(volumes_5d, 1_000_000)
    vol_stability = _vol_stability(highs_5d, lows_5d, closes_5d)
    coiled_spring = _coiled_spring(vol_stability, 0.10)

    assert rvol_buildup is None, rvol_buildup
    assert vol_stability is None, vol_stability
    assert coiled_spring is None, (
        f"coiled_spring muss None sein, nicht der stille Fake-Wert {coiled_spring!r}")

    record = {
        "date": "15.08.2026", "ticker": "TESTNAN",
        "rvol_buildup_5d": rvol_buildup,
        "vol_stability_5d": vol_stability,
        "coiled_spring_score": coiled_spring,
    }
    fake_log = _FakeLog()
    ns["log"] = fake_log
    sanitized = _sanitize_fn([record])
    payload = json.dumps(sanitized)
    assert "NaN" not in payload, payload
    assert sanitized[0]["rvol_buildup_5d"] is None
    assert sanitized[0]["vol_stability_5d"] is None
    assert sanitized[0]["coiled_spring_score"] is None
    # Sanitizer darf hier NICHT greifen (die Werte sind bereits sauber
    # None durch den echten Pfad) -> kein Log-Treffer, kein zweites Netz nötig
    assert fake_log.warnings == [], (
        "der echte Pfad sollte NaN gar nicht erst bis zum Sanitizer durchlassen — "
        f"unerwarteter Sanitizer-Treffer: {fake_log.warnings}")


def test_end_to_end_all_valid_produces_real_numbers_not_none():
    """Gegenprobe zur End-to-End-Kette: ohne NaN-Zelle liefert derselbe
    Pfad echte Zahlen (kein Overreach der Härtung)."""
    rows = _make_valid_rows(5)
    df = _FakeDF(rows)
    hist_5d = _extract_hist_5d(df)
    assert len(hist_5d) == 5

    volumes_5d = [d.get("volume", 0) for d in hist_5d]
    highs_5d   = [d.get("high",   0) for d in hist_5d]
    lows_5d    = [d.get("low",    0) for d in hist_5d]
    closes_5d  = [d.get("close",  0) for d in hist_5d]

    rvol_buildup  = _rvol_buildup(volumes_5d, 1_000_000)
    vol_stability = _vol_stability(highs_5d, lows_5d, closes_5d)
    coiled_spring = _coiled_spring(vol_stability, 0.10)

    assert rvol_buildup is not None
    assert vol_stability is not None
    assert coiled_spring is not None


# === Runner ==================================================================

def main() -> None:
    tests = [
        # _extract_hist_5d
        ("extract_hist_5d: alle valide -> unverändert",         test_extract_hist_5d_all_valid_unchanged),
        ("extract_hist_5d: NaN-Volume -> ganzer Tag verworfen",  test_extract_hist_5d_single_nan_volume_drops_whole_day),
        ("extract_hist_5d: NaN nur in 1 Feld -> ganzer Tag weg", test_extract_hist_5d_partial_field_nan_drops_whole_day_not_cell),
        ("extract_hist_5d: Inf-Zelle -> ebenfalls verworfen",    test_extract_hist_5d_inf_cell_also_dropped),
        ("extract_hist_5d: < 5 Rohtage -> leer",                 test_extract_hist_5d_insufficient_raw_rows_returns_empty),
        ("extract_hist_5d: fehlende Spalte -> Tag verworfen",    test_extract_hist_5d_missing_column_treated_as_invalid_day),
        ("Quelltext: 'or 0'-Falle entfernt",                     test_extract_hist_5d_source_no_longer_has_or_zero_gotcha),
        ("Quelltext: _finite()-Guard vorhanden",                 test_extract_hist_5d_source_uses_finite_guard),
        # _save_backtest_history
        ("save_backtest_history: atomarer Write (tmp+replace)",  test_save_backtest_history_writes_atomically),
        ("Quelltext: os.replace statt direktem open('w')",       test_save_backtest_history_source_uses_os_replace),
        # _sanitize_backtest_entries_for_write
        ("sanitizer: NaN -> null + Log",                         test_sanitizer_replaces_nan_with_null_and_logs),
        ("sanitizer: Inf -> null + Log",                         test_sanitizer_replaces_inf_with_null_and_logs),
        ("sanitizer: verschachtelter Feldpfad im Log",           test_sanitizer_handles_nested_dict_field_path),
        ("sanitizer: NaN in Tupel wird erfasst",                 test_sanitizer_handles_nan_inside_tuple),
        ("sanitizer: sauberer Bestand -> No-Op, kein Log",       test_sanitizer_no_op_and_silent_on_clean_entries),
        ("Quelltext: Sanitizer loggt, ist nie still",            test_sanitizer_source_never_silent),
        # End-to-End
        ("E2E: NaN-Zelle -> None (kein NaN, kein Fake-0.0)",     test_end_to_end_nan_volume_cell_yields_none_not_nan_not_fake_zero),
        ("E2E: valide Kette liefert echte Zahlen",               test_end_to_end_all_valid_produces_real_numbers_not_none),
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
