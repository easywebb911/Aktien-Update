"""Mock-Tests fuer RVOL-Normalisierungs-Helper (PR-alpha, 16.05.2026).

Hintergrund (Score-Inflation-Empirik Schritt 1):
20d-Avg-RVOL ist im premarket-Run strukturell unter-skaliert (today_vol
kumuliert intraday, 20d-Nenner fix). Mean Drift premarket→postclose
+3.87 Pkt, Spitzen +40.2 Pkt (DMRC 13.05.2026).

Helper `_normalize_rvol` (generate_report.py) korrigiert das phasen-
abhaengig, ist aber per Default DEAKTIVIERT (`RVOL_NORMALIZATION_ENABLED
= False`). PR-alpha liefert nur Helper + Konstanten + Feature-Flag —
Aktivierung erst in PR-gamma nach 14 d Empirik-Datensammlung (PR-beta).

Tests (pythonische Replikation der dokumentierten Helper-Semantik plus
Source-Inspektion):
  1. Konstanten in config.py existieren (Default RVOL_NORMALIZATION_ENABLED=False)
  2. Helper im Source vorhanden, Signatur korrekt
  3. Source: 3 Call-Sites in generate_report.py rufen _normalize_rvol
  4. Source: alte Inline-Division `cur_vol / avg_vol ... else 0.0` weg
  5. Feature-Flag OFF: returnt raw / avg (Status quo)
  6. Feature-Flag ON premarket (10:00 UTC): scaler = 0.10
  7. Feature-Flag ON intraday (16:00 UTC = 2.5h ab Open): scaler = max(2.5/6.5, 0.10)
  8. Feature-Flag ON postclose-Wallclock (21:00 UTC): scaler = 1.0
  9. Feature-Flag ON, run_phase="postclose" override: scaler = 1.0 unabhaengig now_utc
 10. Edge: avg_20d == 0  -> 0.0
 11. Edge: avg_20d is None -> 0.0
 12. Edge: raw_vol is None -> 0.0
 13. Edge: raw_vol negativ -> 0.0
 14. Übergang genau 13:30 UTC (= US Open): intraday-Pfad, hours_elapsed=0 → Floor 0.10
 15. Übergang genau 13:29 UTC: premarket-Pfad
 16. Übergang genau 20:00 UTC: postclose-Pfad (kein Skalierer)
 17. Übergang genau 19:59 UTC: intraday-Pfad
 18. Default-Verhalten ohne explizite now_utc: nutzt datetime.now(utc)
 19. CLAUDE.md hat neue Sektion „RVOL-Normalisierung" mit Status OFF
"""
from __future__ import annotations

import pathlib
import re
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
CFG = (ROOT / "config.py").read_text(encoding="utf-8")
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


# ── Pure-Replikation des Helpers (testet Doku-Contract) ──────────────────────

_US_OPEN_MIN_UTC  = 13 * 60 + 30
_US_CLOSE_MIN_UTC = 20 * 60


def normalize_rvol_replicate(
    raw_vol,
    avg_20d,
    *,
    run_phase=None,
    now_utc=None,
    enabled=False,
    premarket_scaler=0.10,
    intraday_min_frac=0.10,
):
    """Pythonische 1:1-Replikation der Helper-Semantik in generate_report.py."""
    try:
        raw = float(raw_vol) if raw_vol is not None else 0.0
        avg = float(avg_20d) if avg_20d is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    if raw <= 0 or avg <= 0:
        return 0.0
    if not enabled:
        return raw / avg
    if run_phase == "postclose":
        return raw / avg
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    mins = now_utc.hour * 60 + now_utc.minute
    if mins < _US_OPEN_MIN_UTC:
        scaler = premarket_scaler
    elif mins < _US_CLOSE_MIN_UTC:
        hours_elapsed = (mins - _US_OPEN_MIN_UTC) / 60.0
        scaler = max(hours_elapsed / 6.5, intraday_min_frac)
    else:
        scaler = 1.0
    denom = avg * scaler
    return raw / denom if denom > 0 else 0.0


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_01_config_constants_exist() -> None:
    assert "RVOL_NORMALIZATION_ENABLED = False" in CFG, \
        "Default ENABLED=False fehlt oder ist nicht False"
    assert "PREMARKET_RVOL_SCALER      = 0.10" in CFG
    assert "INTRADAY_RVOL_MIN_FRAC     = 0.10" in CFG


def test_02_helper_signature_in_source() -> None:
    assert "def _normalize_rvol(" in GR, "Helper fehlt"
    # Signatur mit raw_vol, avg_20d, run_phase, now_utc
    sig_block = GR[GR.find("def _normalize_rvol("): GR.find("def _normalize_rvol(") + 400]
    assert "raw_vol" in sig_block
    assert "avg_20d" in sig_block
    assert "run_phase" in sig_block
    assert "now_utc" in sig_block


def test_03_three_call_sites() -> None:
    n_calls = len(re.findall(r"_normalize_rvol\(", GR))
    # 3 Call-Sites + 1 def. Erlaubt: >=4 (def + min. 3 Aufrufe)
    assert n_calls >= 4, f"Erwarte >=4 Vorkommnisse (def + 3 Aufrufe), gefunden {n_calls}"


def test_04_no_legacy_inline_division() -> None:
    # Die drei alten Patterns muessen weg sein
    # Pattern 1: vol_ratio  = cur_vol / avg_vol_20 if avg_vol_20 > 0 else 0.0
    # Pattern 2/3: vol_r   = cur_vol / avg_vol if avg_vol > 0 else 0.0
    assert "vol_ratio  = cur_vol / avg_vol_20 if avg_vol_20 > 0 else 0.0" not in GR
    assert "vol_r   = cur_vol / avg_vol if avg_vol > 0 else 0.0" not in GR


def test_19_claude_md_section() -> None:
    assert "## RVOL-Normalisierung" in CMD, "CLAUDE.md-Sektion fehlt"
    sec_start = CMD.find("## RVOL-Normalisierung")
    sec_end = CMD.find("\n## ", sec_start + 5)
    sec = CMD[sec_start:sec_end] if sec_end > 0 else CMD[sec_start:]
    assert "OFF" in sec or "deaktiviert" in sec.lower(), \
        "Default-OFF nicht dokumentiert"
    assert "PR-α" in sec or "PR-alpha" in sec or "Phase 1" in sec
    assert "PR-β" in sec or "PR-beta" in sec or "14" in sec  # Daten-Sammlung
    assert "PR-γ" in sec or "PR-gamma" in sec or "Aktivierung" in sec


# ── Funktional ───────────────────────────────────────────────────────────────

def test_05_flag_off_returns_raw_per_avg() -> None:
    # Standardfall, Flag aus → raw / avg, unabhaengig von now_utc/run_phase
    r = normalize_rvol_replicate(5_000_000, 1_000_000,
                                  now_utc=datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
                                  enabled=False)
    assert abs(r - 5.0) < 1e-9


def test_06_flag_on_premarket_scaler_010() -> None:
    # 10:00 UTC, ENABLED=True, run_phase=premarket → scaler=0.10
    r = normalize_rvol_replicate(1_000_000, 1_000_000,
                                  run_phase="premarket",
                                  now_utc=datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
                                  enabled=True)
    # 1_000_000 / (1_000_000 × 0.10) = 10.0
    assert abs(r - 10.0) < 1e-9, f"Erwarte 10.0, got {r}"


def test_07_flag_on_intraday_scaler_dynamic() -> None:
    # 16:00 UTC = 2.5 h nach US Open. scaler = max(2.5/6.5, 0.10) = 0.3846...
    r = normalize_rvol_replicate(1_000_000, 1_000_000,
                                  run_phase="premarket",
                                  now_utc=datetime(2026, 5, 16, 16, 0, tzinfo=timezone.utc),
                                  enabled=True)
    expected = 1.0 / max(2.5 / 6.5, 0.10)  # ≈ 2.6
    assert abs(r - expected) < 1e-6, f"Erwarte {expected}, got {r}"


def test_08_flag_on_postclose_no_scaler() -> None:
    # 21:00 UTC, run_phase=premarket aber Wallclock past close → scaler=1.0
    r = normalize_rvol_replicate(3_000_000, 1_000_000,
                                  run_phase="premarket",
                                  now_utc=datetime(2026, 5, 16, 21, 0, tzinfo=timezone.utc),
                                  enabled=True)
    assert abs(r - 3.0) < 1e-9


def test_09_run_phase_postclose_override() -> None:
    # run_phase=postclose zwingt Status-quo-Pfad auch bei intraday-Wallclock
    r = normalize_rvol_replicate(3_000_000, 1_000_000,
                                  run_phase="postclose",
                                  now_utc=datetime(2026, 5, 16, 16, 0, tzinfo=timezone.utc),
                                  enabled=True)
    assert abs(r - 3.0) < 1e-9


def test_10_avg_zero() -> None:
    assert normalize_rvol_replicate(1_000_000, 0, enabled=False) == 0.0
    assert normalize_rvol_replicate(1_000_000, 0, enabled=True,
                                     now_utc=datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)) == 0.0


def test_11_avg_none() -> None:
    assert normalize_rvol_replicate(1_000_000, None, enabled=False) == 0.0
    assert normalize_rvol_replicate(1_000_000, None, enabled=True,
                                     now_utc=datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)) == 0.0


def test_12_raw_none() -> None:
    assert normalize_rvol_replicate(None, 1_000_000, enabled=False) == 0.0
    assert normalize_rvol_replicate(None, 1_000_000, enabled=True,
                                     now_utc=datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)) == 0.0


def test_13_raw_negative() -> None:
    assert normalize_rvol_replicate(-1, 1_000_000, enabled=True,
                                     now_utc=datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)) == 0.0


def test_14_boundary_1330_utc() -> None:
    # Genau 13:30 UTC = US Open → intraday-Pfad, hours_elapsed=0 → Floor 0.10
    r = normalize_rvol_replicate(1_000_000, 1_000_000,
                                  now_utc=datetime(2026, 5, 16, 13, 30, tzinfo=timezone.utc),
                                  enabled=True)
    # scaler = max(0/6.5, 0.10) = 0.10 → 1.0 / 0.10 = 10.0
    assert abs(r - 10.0) < 1e-9


def test_15_boundary_1329_utc() -> None:
    # 13:29 UTC = premarket
    r = normalize_rvol_replicate(1_000_000, 1_000_000,
                                  now_utc=datetime(2026, 5, 16, 13, 29, tzinfo=timezone.utc),
                                  enabled=True)
    assert abs(r - 10.0) < 1e-9  # 1 / 0.10


def test_16_boundary_2000_utc() -> None:
    # 20:00 UTC = postclose
    r = normalize_rvol_replicate(1_000_000, 1_000_000,
                                  now_utc=datetime(2026, 5, 16, 20, 0, tzinfo=timezone.utc),
                                  enabled=True)
    assert abs(r - 1.0) < 1e-9  # scaler 1.0


def test_17_boundary_1959_utc() -> None:
    # 19:59 UTC = intraday, hours_elapsed = (19*60+59 - 13*60-30)/60 = 6.483..
    r = normalize_rvol_replicate(1_000_000, 1_000_000,
                                  now_utc=datetime(2026, 5, 16, 19, 59, tzinfo=timezone.utc),
                                  enabled=True)
    mins = 19 * 60 + 59
    h = (mins - _US_OPEN_MIN_UTC) / 60.0
    expected = 1.0 / max(h / 6.5, 0.10)
    assert abs(r - expected) < 1e-6


def test_18_default_now_utc_does_not_crash() -> None:
    # Ohne explizite now_utc nutzt der Helper datetime.now(timezone.utc)
    r = normalize_rvol_replicate(1_000_000, 1_000_000, enabled=True)
    # Resultat hängt von Wallclock ab — testet nur dass kein Crash und sinnvoller Wert
    assert isinstance(r, float)
    assert r > 0  # bei valider Eingabe immer > 0


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 config-Konstanten existieren",         test_01_config_constants_exist),
        ("02 Helper-Signatur im Source",            test_02_helper_signature_in_source),
        ("03 drei Call-Sites in generate_report",   test_03_three_call_sites),
        ("04 keine Legacy-Inline-Division",         test_04_no_legacy_inline_division),
        ("05 Flag OFF: raw / avg",                  test_05_flag_off_returns_raw_per_avg),
        ("06 Flag ON premarket: scaler 0.10",       test_06_flag_on_premarket_scaler_010),
        ("07 Flag ON intraday: dynamischer Scaler", test_07_flag_on_intraday_scaler_dynamic),
        ("08 Flag ON postclose-Wallclock",          test_08_flag_on_postclose_no_scaler),
        ("09 run_phase=postclose override",         test_09_run_phase_postclose_override),
        ("10 avg_20d == 0 → 0.0",                   test_10_avg_zero),
        ("11 avg_20d is None → 0.0",                test_11_avg_none),
        ("12 raw_vol is None → 0.0",                test_12_raw_none),
        ("13 raw_vol < 0 → 0.0",                    test_13_raw_negative),
        ("14 Übergang 13:30 UTC (intraday-Floor)",  test_14_boundary_1330_utc),
        ("15 Übergang 13:29 UTC (premarket)",       test_15_boundary_1329_utc),
        ("16 Übergang 20:00 UTC (postclose)",       test_16_boundary_2000_utc),
        ("17 Übergang 19:59 UTC (intraday)",        test_17_boundary_1959_utc),
        ("18 ohne now_utc kein Crash",              test_18_default_now_utc_does_not_crash),
        ("19 CLAUDE.md-Sektion vorhanden",          test_19_claude_md_section),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
        except AssertionError as exc:
            print(f"  FAIL {name}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
            failed += 1
    print()
    print(f"Total: {len(tests)} | Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
