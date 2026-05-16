"""Mock-Tests fuer RS-vs-Sektor Cleanup (16.05.2026).

Hintergrund: Tote Pfade entfernt — rel_strength_sector, sector_etf,
SECTOR_ETF_MAP, SECTOR_ETF_DEFAULT, SECTOR_ETFS_ALL, USE_SECTOR_RS,
Sektor-ETF-yf.download-Block, _sector_rs_row-Helper. Replacement
durch RS_SPY-Pipeline lebt separat (_rs_spy_pts / _rs_spy_row_html).

Tests (Source-Inspektion):
  1. rel_strength_sector kommt im Source nicht mehr vor
  2. sector_etf-Key (Stock-Dict) nicht mehr im Source
  3. SECTOR_ETF_MAP nicht mehr in config.py
  4. SECTOR_ETF_DEFAULT nicht mehr in config.py
  5. SECTOR_ETFS_ALL nicht mehr in config.py
  6. USE_SECTOR_RS nicht mehr in config.py
  7. Replacement _rs_spy_pts hat ≥ 4 Call-Sites (Regression-Schutz)
  8. _sector_rs_row-Helper nicht definiert
  9. Sektor-ETF-yf.download-Block (Z. 15267-15298) entfernt
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
CFG = (ROOT / "config.py").read_text(encoding="utf-8")
KIA = (ROOT / "ki_agent.py").read_text(encoding="utf-8")


def test_01_rel_strength_sector_removed() -> None:
    assert "rel_strength_sector" not in GR, \
        "rel_strength_sector noch in generate_report.py"
    assert "rel_strength_sector" not in CFG, \
        "rel_strength_sector noch in config.py"
    assert "rel_strength_sector" not in KIA, \
        "rel_strength_sector noch in ki_agent.py"


def test_02_sector_etf_key_removed() -> None:
    # Stock-Dict-Key '"sector_etf"' darf nicht mehr vorkommen
    assert '"sector_etf"' not in GR, '"sector_etf" Key noch in generate_report.py'
    assert "'sector_etf'" not in GR, "'sector_etf' Key noch in generate_report.py"


def test_03_sector_etf_map_removed() -> None:
    assert "SECTOR_ETF_MAP" not in CFG, "SECTOR_ETF_MAP noch in config.py"
    assert "SECTOR_ETF_MAP" not in GR, "SECTOR_ETF_MAP noch in generate_report.py"


def test_04_sector_etf_default_removed() -> None:
    assert "SECTOR_ETF_DEFAULT" not in CFG, "SECTOR_ETF_DEFAULT noch in config.py"
    assert "SECTOR_ETF_DEFAULT" not in GR, "SECTOR_ETF_DEFAULT noch in generate_report.py"


def test_05_sector_etfs_all_removed() -> None:
    assert "SECTOR_ETFS_ALL" not in CFG, "SECTOR_ETFS_ALL noch in config.py"
    assert "SECTOR_ETFS_ALL" not in GR, "SECTOR_ETFS_ALL noch in generate_report.py"


def test_06_use_sector_rs_removed() -> None:
    assert "USE_SECTOR_RS" not in CFG, "USE_SECTOR_RS noch in config.py"
    assert "USE_SECTOR_RS" not in GR, "USE_SECTOR_RS noch in generate_report.py"


def test_07_rs_spy_pts_call_sites_intact() -> None:
    # Replacement-Pipeline muss weiterhin verdrahtet sein (Regression-Schutz)
    n_calls = len(re.findall(r"\b_rs_spy_pts\b", GR))
    assert n_calls >= 4, \
        f"_rs_spy_pts hat nur {n_calls} Call-Sites (erwartet >= 4)"


def test_08_sector_rs_row_helper_removed() -> None:
    # Helper-Definition + Aufrufe nicht mehr vorhanden
    assert "_sector_rs_row" not in GR, \
        "_sector_rs_row noch in generate_report.py"


def test_09_sector_etf_download_block_removed() -> None:
    # Charakteristische Marker des entfernten yf.download-Blocks
    assert "Sektor-ETF 20T-Perf" not in GR, \
        "Sektor-ETF-Log-Zeile noch im Source"
    assert "_sector_perf_20d" not in GR, \
        "_sector_perf_20d-Variable noch im Source"
    assert "Sektor-ETF yf.download timeout" not in GR, \
        "Sektor-ETF-Timeout-Log noch im Source"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 rel_strength_sector entfernt",     test_01_rel_strength_sector_removed),
        ("02 sector_etf-Key entfernt",          test_02_sector_etf_key_removed),
        ("03 SECTOR_ETF_MAP entfernt",          test_03_sector_etf_map_removed),
        ("04 SECTOR_ETF_DEFAULT entfernt",      test_04_sector_etf_default_removed),
        ("05 SECTOR_ETFS_ALL entfernt",         test_05_sector_etfs_all_removed),
        ("06 USE_SECTOR_RS entfernt",           test_06_use_sector_rs_removed),
        ("07 _rs_spy_pts >= 4 Call-Sites",      test_07_rs_spy_pts_call_sites_intact),
        ("08 _sector_rs_row-Helper entfernt",   test_08_sector_rs_row_helper_removed),
        ("09 Sektor-ETF-Download-Block weg",    test_09_sector_etf_download_block_removed),
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
