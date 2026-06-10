"""Boundary-Mock-Test für den Vintage-Guard (M1, Backtest-Append-Schutz).

Kategorie A: env-frei (yfinance/config gestubbt), zeit-INJIZIERT (kein
Wallclock-Leak), deterministisch, CI-gate-bar. Prüft die PURE
``_vintage_gate_decision`` über alle Boundary-Fälle + DST + die
Beobachtbarkeit des Bar-Lag-False-Skips über ``_log_vintage_skip`` +
die existing_keys-bei-Skip-Garantie (Skip schreibt NICHT).

Bezug: Diagnose 09.06.2026 (11/11 Cluster = Pre-Open). Gate-Logik:
append nur wenn now_et >= report_date@16:00 ET UND bar_date == report_date;
fehlendes bar_date → append (Missing-Regel, konservativ).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ── yfinance-Stub vor Import (backtest_history importiert yf modul-weit) ────
if "yfinance" not in sys.modules:
    _yf = types.ModuleType("yfinance")
    _yf.download = lambda *a, **k: None
    _yf.Ticker = lambda *a, **k: None
    sys.modules["yfinance"] = _yf

import backtest_history as bh  # noqa: E402

ET = ZoneInfo("America/New_York")
_fails: list[str] = []


def _check(name: str, got, want) -> None:
    if got == want:
        print(f"  OK  {name}")
    else:
        _fails.append(f"{name}: got {got!r}, want {want!r}")
        print(f"  FAIL {name}: got {got!r}, want {want!r}")


def _et(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def _from_utc(y, mo, d, h, mi):
    """UTC-Zeitpunkt → ET-konvertiert (für DST-Beweis: gleiche UTC, je nach
    Saison anderes ET)."""
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).astimezone(ET)


# report_date Mo 08.06.2026 (Handelstag); Vortags-Bar = Fr 05.06.2026.
RD = "08.06.2026"
BAR_RD = "2026-06-08"   # == report_date
BAR_PRIOR = "2026-06-05"


print("=== 1 — Boundary-Fälle (pure _vintage_gate_decision) ===")
# Pre-Open: 00:33 ET, Bar = Vortag
_check("01 pre_open (00:33 ET, bar=Fr)",
       bh._vintage_gate_decision(RD, BAR_PRIOR, _et(2026, 6, 8, 0, 33)),
       ("skip", "pre_open"))
# Legit Post-Close: 17:17 ET, Bar == report_date
_check("02 legit post-close (17:17 ET, bar==rd)",
       bh._vintage_gate_decision(RD, BAR_RD, _et(2026, 6, 8, 17, 17)),
       ("append", "ok"))
# Intraday-only: 15:42 ET (vor Close), Bar == report_date (in-progress)
_check("03 intraday before_close (15:42 ET, bar==rd)",
       bh._vintage_gate_decision(RD, BAR_RD, _et(2026, 6, 8, 15, 42)),
       ("skip", "before_close"))
# Feiertag: 17:17 ET (Zeit OK), aber Bar = Vortag (Session existierte nicht)
_check("04 holiday (17:17 ET, bar=prior)",
       bh._vintage_gate_decision(RD, BAR_PRIOR, _et(2026, 6, 8, 17, 17)),
       ("skip", "holiday_or_prior_bar"))
# Bar-Lag (DIE kritische Lücke): legitimer Post-Close-Run um 22:00 UTC
# (=18:00 ET, post-close), aber yfinance-Bar noch Vortag → selbe reason wie
# Feiertag. NUR über now_et im Log unterscheidbar (siehe Test 3).
_blag_now = _from_utc(2026, 6, 8, 22, 0)   # 22:00 UTC = 18:00 EDT
_check("05 bar-lag post-close (22:00 UTC=18:00 ET, bar=prior)",
       bh._vintage_gate_decision(RD, BAR_PRIOR, _blag_now),
       ("skip", "holiday_or_prior_bar"))
# Missing bar_date → append (Missing-Regel)
_check("06 missing bar (17:17 ET, bar=None)",
       bh._vintage_gate_decision(RD, None, _et(2026, 6, 8, 17, 17)),
       ("append", "missing_bar"))
_check("06b missing bar (unparsbar)",
       bh._vintage_gate_decision(RD, "garbage", _et(2026, 6, 8, 17, 17)),
       ("append", "missing_bar"))
# Garbage report_date → kein Gate
_check("07 garbage report_date → append",
       bh._vintage_gate_decision("not-a-date", BAR_PRIOR, _et(2026, 6, 8, 17, 17))[0],
       "append")

print("\n=== 2 — Exakte 16:00-ET-Grenze (>= Close = append) ===")
_check("08 15:59 ET → skip",
       bh._vintage_gate_decision(RD, BAR_RD, _et(2026, 6, 8, 15, 59)),
       ("skip", "before_close"))
_check("09 16:00 ET exakt → append",
       bh._vintage_gate_decision(RD, BAR_RD, _et(2026, 6, 8, 16, 0)),
       ("append", "ok"))

print("\n=== 3 — DST: gleiche UTC, je nach Saison andere ET-Entscheidung ===")
# 20:30 UTC: Juni (EDT, UTC-4) = 16:30 ET → append · Januar (EST, UTC-5)
# = 15:30 ET → skip. Beweist DST-korrekte ET-Auflösung (zoneinfo).
_check("10 EDT 20:30 UTC=16:30 ET → append",
       bh._vintage_gate_decision("08.06.2026", "2026-06-08", _from_utc(2026, 6, 8, 20, 30)),
       ("append", "ok"))
_check("11 EST 20:30 UTC=15:30 ET → skip (before_close)",
       bh._vintage_gate_decision("15.01.2026", "2026-01-15", _from_utc(2026, 1, 15, 20, 30)),
       ("skip", "before_close"))
# Gegenprobe EST: 21:30 UTC = 16:30 EST → append
_check("12 EST 21:30 UTC=16:30 ET → append",
       bh._vintage_gate_decision("15.01.2026", "2026-01-15", _from_utc(2026, 1, 15, 21, 30)),
       ("append", "ok"))

print("\n=== 4 — Bar-Lag-Beobachtbarkeit über _log_vintage_skip (now_utc) ===")
_tmp = tempfile.mktemp(suffix=".jsonl")
_orig = bh._VINTAGE_GUARD_LOG
try:
    bh._VINTAGE_GUARD_LOG = _tmp
    # harmloser Pre-Open-Skip (04:33 UTC) vs. verdächtiger Post-Close-Skip
    bh._log_vintage_skip(RD, BAR_PRIOR, _from_utc(2026, 6, 8, 4, 33),
                         "pre_open", 8)
    bh._log_vintage_skip(RD, BAR_PRIOR, _blag_now, "holiday_or_prior_bar", 8)
    recs = [json.loads(l) for l in open(_tmp) if l.strip()]
    _check("13 zwei Log-Zeilen geschrieben", len(recs), 2)
    _check("14 Pre-Open-Skip now_utc ~04:33", recs[0]["now_utc"][11:16], "04:33")
    _check("15 Bar-Lag-Skip now_utc ~22:00 (verdächtig sichtbar)",
           recs[1]["now_utc"][11:16], "22:00")
    _check("16 Bar-Lag reason = holiday_or_prior_bar (nur now_utc trennt)",
           recs[1]["reason"], "holiday_or_prior_bar")
finally:
    bh._VINTAGE_GUARD_LOG = _orig
    if os.path.exists(_tmp):
        os.unlink(_tmp)

print("\n=== 5 — existing_keys-bei-Skip: Time-Gate-Skip schreibt NICHT ===")
# Pre-Open-Run → _append muss 0 zurückgeben OHNE _save_backtest_history zu
# rufen (→ existing_keys bleibt unbelegt → späterer Run appended frisch).
_save_calls = []
_orig_save = bh._save_backtest_history
_orig_load = bh._load_backtest_history
_orig_enabled = bh.BACKTEST_ENABLED
_tmp_log = tempfile.mktemp(suffix=".jsonl")
_orig_vg = bh._VINTAGE_GUARD_LOG
try:
    bh.BACKTEST_ENABLED = True
    bh._VINTAGE_GUARD_LOG = _tmp_log
    bh._save_backtest_history = lambda *a, **k: _save_calls.append(1)
    bh._load_backtest_history = lambda *a, **k: []
    fake_top10 = [{"ticker": "AAA", "bar_date": BAR_PRIOR, "price": 1.0},
                  {"ticker": "BBB", "bar_date": BAR_PRIOR, "price": 2.0}]
    n = bh._append_backtest_entries(
        fake_top10, RD, pool_size=10,
        compute_sub_scores_fn=lambda *a, **k: {},
        safe_float_fn=float,
        now_et=_et(2026, 6, 8, 0, 33))   # Pre-Open
    _check("17 Pre-Open-Run: n_added == 0", n, 0)
    _check("18 Pre-Open-Run: _save NICHT gerufen (kein Write → existing_keys frei)",
           len(_save_calls), 0)
finally:
    bh._save_backtest_history = _orig_save
    bh._load_backtest_history = _orig_load
    bh.BACKTEST_ENABLED = _orig_enabled
    bh._VINTAGE_GUARD_LOG = _orig_vg
    if os.path.exists(_tmp_log):
        os.unlink(_tmp_log)

print()
if _fails:
    print(f"{len(_fails)} FAIL:")
    for f in _fails:
        print("  -", f)
    sys.exit(1)
print("Alle Vintage-Guard-Boundary-Tests bestanden.")
