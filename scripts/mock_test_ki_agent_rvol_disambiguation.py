"""Mock-Tests fuer ki_agent.py RVOL-Disambiguation (16.05.2026).

Hintergrund (Diagnose 16.05.2026):
ki_agent.py:455 berechnete frueher `rvol = today_vol / mean(letzte 4 Vortage)`
und persistierte das als JSON-Key "rvol". generate_report.py:_hist_stats
berechnet parallel `rel_volume = today_vol / mean(letzte 20 Vortage)`.

Beide Formeln messen unterschiedliche Dinge:
- 4d: kurzfristiger Trend-Bruch (Anomaly-Push-Basis)
- 20d: absolute Anomalie vs. Langzeit-Baseline (Setup-Score-Basis)

Empirik n=10 zeigte 20d/4d-Faktor zwischen 0.29 und 1.56 — keine
Vereinheitlichung moeglich ohne ticker-spezifische Recalibration.

Refactor:
- Variable + JSON-Key umbenannt: rvol -> rvol_4d (Bedeutung klarer)
- rvol_20d additiv als neues Feld (rein logging, kein Trigger)
- period="5d" -> "1mo" um beide Mittel aus einem Fetch zu derivieren
- Anomaly-Schwellen UNVERAENDERT (rvol_4d bleibt Trigger-Basis)
- Frontend-Reader (3 Stellen) mit Backward-compat-Fallback auf "rvol"

Tests:
  1. fetch_yfinance: period="1mo" (vorher "5d")
  2. fetch_yfinance: rvol_4d-Berechnung nutzt iloc[-4:] (letzte 4 prior)
  3. fetch_yfinance: rvol_20d-Berechnung nutzt iloc[:-1] mit >=15-Filter
  4. fetch_yfinance: Result-Dict hat rvol_4d + rvol_20d (kein "rvol"-Key)
  5. fetch_yfinance: fast_info-Fallback-Pfade setzen rvol_4d=0.0 + rvol_20d=None
  6. compute_signal: Parameter heisst prev_rvol_4d (vorher prev_rvol)
  7. compute_signal: Liest rvol_4d aus yf_data
  8. compute_signal: Alle Trigger-Schwellen lesen rvol_4d (TRIGGER_RVOL_*,
     RVOL_HIGH/EXTREME, RVOL_VELOCITY_*, COMBO_RVOL_MIN)
  9. send_ntfy_alert: Liest rvol_4d aus yf_data
 10. detect_anomalies: rvol_today_4d und rvol_prev_4d (umbenannt)
 11. detect_anomalies: Liest signal.get("rvol_4d")
 12. signal-Dict in _process_ticker hat rvol_4d + rvol_20d (kein bare "rvol")
 13. compute_signal-Caller uebergibt prev_rvol_4d (alte Signatur weg)
 14. generate_report.py: 3 Frontend-Reader haben Backward-compat-Fallback
 15. CLAUDE.md: Sektion "RVOL-Definitionen" existiert mit Schema-Block
 16. Pythonische Replikation: rvol_4d-Berechnung gegen Mini-DataFrame
 17. Pythonische Replikation: rvol_20d=None bei < 15 prior days
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
KI = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


# ── Source-Inspektion ────────────────────────────────────────────────────────

def _fetch_yfinance_block() -> str:
    start = KI.find("def fetch_yfinance(")
    assert start > 0, "fetch_yfinance nicht gefunden"
    end = KI.find("\ndef ", start + 10)
    assert end > start
    return KI[start:end]


def _compute_signal_block() -> str:
    start = KI.find("def compute_signal(")
    assert start > 0
    end = KI.find("\ndef ", start + 10)
    assert end > start
    return KI[start:end]


def _detect_anomalies_block() -> str:
    start = KI.find("def detect_anomalies(")
    assert start > 0
    end = KI.find("\ndef ", start + 10)
    assert end > start
    return KI[start:end]


def _signal_dict_block() -> str:
    """signal = {...}-Dict in _process_ticker."""
    start = KI.find("\n    signal = {")
    assert start > 0
    end = KI.find("\n    }", start)
    assert end > start
    return KI[start:end]


def test_01_fetch_period_1mo() -> None:
    block = _fetch_yfinance_block()
    assert 'period="1mo"' in block, "period wurde nicht auf 1mo umgestellt"
    assert 'period="5d"' not in block, "altes period=5d noch vorhanden"


def test_02_rvol_4d_uses_last4_prior() -> None:
    block = _fetch_yfinance_block()
    # iloc[-4:] auf prior_vols (= letzte 4 vor heute)
    assert "prior_vols.iloc[-4:]" in block, "4d-Slice fehlt"
    assert "avg_vol_4d" in block, "avg_vol_4d-Variable fehlt"
    assert "rvol_4d        = round(cur_vol / avg_vol_4d, 2)" in block


def test_03_rvol_20d_uses_full_prior_with_min15() -> None:
    block = _fetch_yfinance_block()
    assert "len(prior_vols) >= 15" in block, "Min-15-Filter fehlt"
    assert "rvol_20d    = round(cur_vol / avg_vol_20d, 2)" in block
    assert "rvol_20d    = None" in block, "None-Fallback fehlt"


def test_04_result_dict_has_both_keys_no_bare_rvol() -> None:
    block = _fetch_yfinance_block()
    assert '"rvol_4d":' in block
    assert '"rvol_20d":' in block
    # Kein bare "rvol" Key
    assert re.search(r'"rvol"\s*:', block) is None, \
        "Bare \"rvol\"-Key noch in fetch_yfinance"


def test_05_fast_info_fallback_paths() -> None:
    block = _fetch_yfinance_block()
    # Beide Fallback-Pfade muessen rvol_4d=0.0 + rvol_20d=None setzen
    fallback_count_4d = block.count('"rvol_4d":        0.0')
    fallback_count_20d = block.count('"rvol_20d":       None')
    assert fallback_count_4d == 2, \
        f"Erwarte 2 rvol_4d=0.0 Fallbacks, gefunden {fallback_count_4d}"
    assert fallback_count_20d == 2, \
        f"Erwarte 2 rvol_20d=None Fallbacks, gefunden {fallback_count_20d}"


def test_06_compute_signal_param_renamed() -> None:
    block = _compute_signal_block()
    assert "prev_rvol_4d: float = 0.0" in block, \
        "Parameter prev_rvol_4d fehlt"
    # Alter Parameter prev_rvol darf nicht mehr existieren
    assert re.search(r'\bprev_rvol\b\s*:', block) is None, \
        "Alter Parameter prev_rvol noch da"


def test_07_compute_signal_reads_rvol_4d() -> None:
    block = _compute_signal_block()
    assert 'rvol_4d = yf_data.get("rvol_4d", 0.0)' in block, \
        "rvol_4d-Read fehlt"


def test_08_all_trigger_thresholds_read_rvol_4d() -> None:
    block = _compute_signal_block()
    # Alle 6 Trigger-Vergleiche muessen rvol_4d nutzen
    checks = [
        "rvol_4d >= TRIGGER_RVOL_4X",
        "rvol_4d >= TRIGGER_RVOL_2X",
        "rvol_4d >= RVOL_EXTREME_THRESHOLD",
        "rvol_4d >= RVOL_HIGH_THRESHOLD",
        "rvol_4d >= RVOL_VELOCITY_MIN",
        "rvol_4d >= COMBO_RVOL_MIN",
    ]
    for c in checks:
        assert c in block, f"Trigger fehlt: {c}"
    # Velocity-Vergleich gegen prev_rvol_4d
    assert "rvol_4d / prev_rvol_4d" in block


def test_09_send_alert_reads_rvol_4d() -> None:
    # send_alert (E-Mail-Body-Builder) liest yf_data.rvol_4d
    start = KI.find("def send_alert(")
    assert start > 0, "send_alert nicht gefunden"
    end = KI.find("\ndef ", start + 10)
    block = KI[start:end]
    assert 'rvol_4d = yf_data.get("rvol_4d", 0.0)' in block, \
        "send_alert liest nicht rvol_4d"
    assert "{rvol_4d:.1f}×" in block, "Body-Format nutzt nicht rvol_4d"


def test_10_detect_anomalies_var_names_4d() -> None:
    block = _detect_anomalies_block()
    assert "rvol_today_4d = float(signal.get(\"rvol_4d\")" in block
    assert "rvol_prev_4d = float((prev_signal or {}).get(\"rvol_4d\")" in block


def test_11_detect_anomalies_thresholds_use_4d() -> None:
    block = _detect_anomalies_block()
    # RVOL-Explosion-Trigger
    assert "rvol_today_4d >= ANOMALY_RVOL_TODAY" in block
    assert "rvol_today_4d / rvol_prev_4d >= ANOMALY_RVOL_VS_YESTERDAY" in block
    # Gap+Hold-Trigger
    assert "rvol_today_4d >= ANOMALY_GAP_RVOL" in block


def test_12_signal_dict_has_both_keys() -> None:
    block = _signal_dict_block()
    assert '"rvol_4d":        yfd.get("rvol_4d", 0.0)' in block
    assert '"rvol_20d":       yfd.get("rvol_20d")' in block
    # Kein bare "rvol"-Key
    assert re.search(r'"rvol"\s*:', block) is None, \
        "Bare \"rvol\"-Key noch im signal-Dict"


def test_13_caller_passes_prev_rvol_4d() -> None:
    # Caller-Site: prev_rvol_4d=float(old_sigs.get(...).get("rvol_4d", 0))
    pattern = r'prev_rvol_4d\s*=\s*float\(old_sigs\.get\(ticker,\s*\{\}\)\.get\("rvol_4d",\s*0\)\s*or\s*0\)'
    assert re.search(pattern, KI), "Caller passt prev_rvol_4d nicht korrekt"


def test_14_frontend_readers_have_backward_compat() -> None:
    # 3 Frontend-Reader in generate_report.py: Insights-Chip, Statuszeile,
    # Drawer-RVOL-Zeile — alle bevorzugen rvol_4d mit Fallback auf rvol
    # Pattern: (s && s.rvol_4d != null) ? s.rvol_4d : (s && s.rvol != null) ? s.rvol : null
    # bzw. die sig.-Variante.
    pattern_s = r's\.rvol_4d\s*!=\s*null\)\s*\?\s*s\.rvol_4d\s*:\s*\(s\s*&&\s*s\.rvol\s*!=\s*null\)\s*\?\s*s\.rvol'
    pattern_sig = r'sig\.rvol_4d\s*!=\s*null\)\s*\?\s*sig\.rvol_4d\s*:\s*\(sig\s*&&\s*sig\.rvol\s*!=\s*null\)\s*\?\s*sig\.rvol'
    s_matches = len(re.findall(pattern_s, GR))
    sig_matches = len(re.findall(pattern_sig, GR))
    assert s_matches >= 2, \
        f"Erwarte >=2 s.rvol_4d-Backward-compat-Patterns, gefunden {s_matches}"
    assert sig_matches >= 1, \
        f"Erwarte >=1 sig.rvol_4d-Backward-compat-Pattern, gefunden {sig_matches}"


def test_15_claude_md_section_exists() -> None:
    assert "## RVOL-Definitionen" in CMD, \
        "CLAUDE.md-Sektion 'RVOL-Definitionen' fehlt"
    # Schema-Block mit beiden Feldern
    section_start = CMD.find("## RVOL-Definitionen")
    section_end = CMD.find("## Anomalie-Push-System", section_start)
    section = CMD[section_start:section_end]
    assert "`rvol_4d`" in section
    assert "`rvol_20d`" in section
    assert "rel_volume" in section
    # Empirik-Verweis (16.05.2026)
    assert "16.05.2026" in section


# ── Pythonische Replikation ──────────────────────────────────────────────────

def test_16_rvol_4d_calc_replication() -> None:
    """Replikation der rvol_4d-Berechnung gegen Mini-Daten."""
    # Simuliere 22 Tage Volumen (period="1mo")
    volumes = [1_000_000] * 22
    cur_vol = 5_000_000  # heutiger Wert
    volumes[-1] = cur_vol  # letzte Zeile ist heute
    # prior_vols = alles ausser letzte
    prior_vols = volumes[:-1]
    last4 = prior_vols[-4:]  # iloc[-4:]
    avg_vol_4d = sum(last4) / len(last4)  # = 1_000_000
    rvol_4d = round(cur_vol / avg_vol_4d, 2)
    assert rvol_4d == 5.0, f"Erwarte 5.0, got {rvol_4d}"


def test_17_rvol_20d_none_for_short_history() -> None:
    """Bei < 15 prior days muss rvol_20d = None sein."""
    # Simuliere nur 10 Tage Daten -> prior_vols hat 9 Eintraege -> < 15
    volumes = [1_000_000] * 10
    cur_vol = 5_000_000
    volumes[-1] = cur_vol
    prior_vols = volumes[:-1]
    # Replikation der Source-Logik
    if len(prior_vols) >= 15:
        avg_vol_20d = sum(prior_vols) / len(prior_vols)
        rvol_20d = round(cur_vol / avg_vol_20d, 2)
    else:
        rvol_20d = None
    assert rvol_20d is None


def test_18_rvol_20d_valid_for_sufficient_history() -> None:
    """Bei >= 15 prior days wird rvol_20d berechnet."""
    volumes = [1_000_000] * 21
    cur_vol = 3_000_000
    volumes[-1] = cur_vol
    prior_vols = volumes[:-1]  # 20 Eintraege
    assert len(prior_vols) >= 15
    avg_vol_20d = sum(prior_vols) / len(prior_vols)
    rvol_20d = round(cur_vol / avg_vol_20d, 2)
    assert rvol_20d == 3.0


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 fetch_yfinance period=1mo",            test_01_fetch_period_1mo),
        ("02 rvol_4d uses last-4 prior",            test_02_rvol_4d_uses_last4_prior),
        ("03 rvol_20d uses full prior with >=15",   test_03_rvol_20d_uses_full_prior_with_min15),
        ("04 result-dict has rvol_4d + rvol_20d",   test_04_result_dict_has_both_keys_no_bare_rvol),
        ("05 fast_info fallback paths",             test_05_fast_info_fallback_paths),
        ("06 compute_signal param renamed",         test_06_compute_signal_param_renamed),
        ("07 compute_signal reads rvol_4d",         test_07_compute_signal_reads_rvol_4d),
        ("08 trigger thresholds all rvol_4d",       test_08_all_trigger_thresholds_read_rvol_4d),
        ("09 send_alert reads rvol_4d",             test_09_send_alert_reads_rvol_4d),
        ("10 detect_anomalies var names",           test_10_detect_anomalies_var_names_4d),
        ("11 detect_anomalies thresholds 4d",       test_11_detect_anomalies_thresholds_use_4d),
        ("12 signal-dict has both keys",            test_12_signal_dict_has_both_keys),
        ("13 caller passes prev_rvol_4d",           test_13_caller_passes_prev_rvol_4d),
        ("14 frontend backward-compat",             test_14_frontend_readers_have_backward_compat),
        ("15 CLAUDE.md section exists",             test_15_claude_md_section_exists),
        ("16 rvol_4d calc replication",             test_16_rvol_4d_calc_replication),
        ("17 rvol_20d=None for short history",      test_17_rvol_20d_none_for_short_history),
        ("18 rvol_20d valid for sufficient hist",   test_18_rvol_20d_valid_for_sufficient_history),
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
