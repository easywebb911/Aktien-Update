"""Mock-Tests für Earliness-Komponente 3 (Pre-Market-Volume).

Testet ``compute_earliness_pts`` aus generate_report.py mit präparierten
Stock-Dicts; FINRA-Komponenten sind so gewählt, dass sie nicht feuern,
damit der PM-Vol-Pfad isoliert bewertet werden kann.

Ausführung: ``python scripts/mock_test_earliness_pm_vol.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# generate_report.py importiert Drittpakete (yfinance, requests, …) beim
# Modul-Load. Wir extrahieren ``compute_earliness_pts`` per Source-Slice
# und führen es in einem isolierten Namespace aus, der nur die nötigen
# config-Konstanten + ein Logger-Stub bereitstellt.
import re

src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
m = re.search(
    r"^def compute_earliness_pts\([\s\S]+?(?=^def\s|^class\s|^# ====)",
    src, re.MULTILINE,
)
assert m, "compute_earliness_pts in generate_report.py nicht gefunden"
helper_src = m.group(0)


class _Log:
    def info(self, *a, **k):  # noqa: D401
        pass
    def debug(self, *a, **k):
        pass
    def warning(self, *a, **k):
        pass


ns: dict = {"log": _Log()}
exec(
    "from config import (EARLINESS_PTS_MAX, EARLINESS_ACCEL_PTS, "
    "EARLINESS_VELOCITY_PTS, EARLINESS_VELOCITY_THRESHOLD, "
    "EARLINESS_MAX_CHANGE_5D_PCT, EARLINESS_MAX_RSI, "
    "EARLINESS_PM_VOL_LOW_PCT, EARLINESS_PM_VOL_HIGH_PCT, "
    "EARLINESS_PM_VOL_PTS_LOW, EARLINESS_PM_VOL_PTS_HIGH)\n"
    + helper_src,
    ns,
)
compute_earliness_pts = ns["compute_earliness_pts"]
EARLINESS_PTS_MAX        = ns["EARLINESS_PTS_MAX"]
EARLINESS_PM_VOL_PTS_LOW  = ns["EARLINESS_PM_VOL_PTS_LOW"]
EARLINESS_PM_VOL_PTS_HIGH = ns["EARLINESS_PM_VOL_PTS_HIGH"]


def _expect(cond, msg):
    if not cond:
        raise AssertionError("ASSERT: " + msg)


def _base_stock(**overrides) -> dict:
    """Stock-Dict mit so gewählten FINRA-Werten, dass accel/velocity NICHT
    feuern — damit der PM-Vol-Pfad isoliert ist.
    """
    s = {
        "ticker":            "TEST",
        "si_accel":          False,            # accel_match=False
        "si_velocity":       0,                # velocity_match=False
        "change_5d":         2.0,              # < 5 (Filter passierbar)
        "rsi14":             45.0,
        "premarket_volume":  0.0,
        "avg_vol_20d":       1_000_000,
        "cur_open":          11.0,             # +10 % overnight
        "prev_close":        10.0,
    }
    s.update(overrides)
    return s


def test_no_pm_data_returns_zero():
    s = _base_stock(premarket_volume=0.0)
    compute_earliness_pts([s])
    _expect(s["earliness_pts"] == 0,
            f"pts sollte 0 sein bei pm_vol=0, war {s['earliness_pts']}")
    _expect(s["earliness_breakdown"]["pm_vol_match"] is False,
            "pm_vol_match muss False sein bei pm_vol=0")
    print("PASS  test_no_pm_data_returns_zero")


def test_ratio_below_low_threshold():
    # pm_vol = 1 % vom avg → unter 3 % LOW → 0 Punkte
    s = _base_stock(premarket_volume=10_000)  # 10k / 1M = 1 %
    compute_earliness_pts([s])
    _expect(s["earliness_pts"] == 0,
            f"pts sollte 0 sein bei ratio=1%, war {s['earliness_pts']}")
    _expect(s["earliness_breakdown"]["pm_vol_match"] is False,
            "pm_vol_match darf bei <LOW nicht aktiv sein")
    print("PASS  test_ratio_below_low_threshold")


def test_ratio_in_low_band():
    # 5 % vom avg → ≥3 %, <8 % → +1
    s = _base_stock(premarket_volume=50_000)
    compute_earliness_pts([s])
    _expect(s["earliness_pts"] == EARLINESS_PM_VOL_PTS_LOW,
            f"pts sollte {EARLINESS_PM_VOL_PTS_LOW} sein, war {s['earliness_pts']}")
    _expect(s["earliness_breakdown"]["pm_vol_match"] is True,
            "pm_vol_match muss True sein bei ratio in LOW-Band")
    print("PASS  test_ratio_in_low_band")


def test_ratio_at_high_threshold():
    # 8 % vom avg → ≥8 % HIGH → +2
    s = _base_stock(premarket_volume=80_000)
    compute_earliness_pts([s])
    _expect(s["earliness_pts"] == EARLINESS_PM_VOL_PTS_HIGH,
            f"pts sollte {EARLINESS_PM_VOL_PTS_HIGH} sein, war {s['earliness_pts']}")
    _expect(s["earliness_breakdown"]["pm_vol_match"] is True,
            "pm_vol_match muss True sein bei ratio ≥ HIGH")
    print("PASS  test_ratio_at_high_threshold")


def test_negative_overnight_blocks_pm_pts():
    # PM-Vol hoch (HIGH-Band) ABER change_overnight < 0 → kein Trigger
    s = _base_stock(premarket_volume=80_000, cur_open=9.5)  # -5 %
    compute_earliness_pts([s])
    _expect(s["earliness_pts"] == 0,
            f"pts muss 0 sein bei change_overnight<0, war {s['earliness_pts']}")
    _expect(s["earliness_breakdown"]["pm_vol_match"] is False,
            "pm_vol_match darf bei PM-Selloff nicht aktiv sein")
    print("PASS  test_negative_overnight_blocks_pm_pts")


def test_change_5d_too_high_blocks_pm_pts():
    # PM-Vol hoch ABER change_5d >= 5 → Earliness-Charakter verletzt
    s = _base_stock(premarket_volume=80_000, change_5d=7.0)
    compute_earliness_pts([s])
    _expect(s["earliness_pts"] == 0,
            f"pts muss 0 sein bei change_5d≥5, war {s['earliness_pts']}")
    _expect(s["earliness_breakdown"]["pm_vol_match"] is False,
            "pm_vol_match darf nicht aktiv sein wenn change_5d-Filter fehlschlägt")
    print("PASS  test_change_5d_too_high_blocks_pm_pts")


def test_missing_avg_vol_blocks_pm_pts():
    # avg_vol_20d=0 → Ratio undefiniert → 0 Punkte
    s = _base_stock(premarket_volume=80_000, avg_vol_20d=0)
    compute_earliness_pts([s])
    _expect(s["earliness_pts"] == 0, "avg_vol=0 muss PM-Pts blockieren")
    _expect(s["earliness_breakdown"]["pm_vol_match"] is False,
            "pm_vol_match darf bei avg_vol=0 nicht True sein")
    print("PASS  test_missing_avg_vol_blocks_pm_pts")


def test_breakdown_always_written():
    s = _base_stock(premarket_volume=0.0)
    compute_earliness_pts([s])
    _expect("earliness_pts" in s, "earliness_pts immer schreiben")
    _expect("earliness_breakdown" in s, "earliness_breakdown immer schreiben")
    bd = s["earliness_breakdown"]
    for k in ("accel_match", "velocity_match", "pm_vol_match"):
        _expect(k in bd, f"breakdown-key {k} fehlt")
    print("PASS  test_breakdown_always_written")


def test_cap_at_max():
    # Alle drei Komponenten max → 3 + 2 + 2 = 7 == EARLINESS_PTS_MAX
    s = _base_stock(
        si_accel=True,
        si_velocity=200,           # ≥ 100
        rsi14=50,                  # < 60
        change_5d=2.0,             # < 5
        premarket_volume=100_000,  # 10 % vom avg → HIGH
    )
    compute_earliness_pts([s])
    _expect(s["earliness_pts"] == EARLINESS_PTS_MAX,
            f"pts muss EARLINESS_PTS_MAX={EARLINESS_PTS_MAX} sein, war {s['earliness_pts']}")
    bd = s["earliness_breakdown"]
    _expect(bd["accel_match"] and bd["velocity_match"] and bd["pm_vol_match"],
            "alle drei breakdown-flags müssen True sein")
    print("PASS  test_cap_at_max")


def main():
    try:
        test_no_pm_data_returns_zero()
        test_ratio_below_low_threshold()
        test_ratio_in_low_band()
        test_ratio_at_high_threshold()
        test_negative_overnight_blocks_pm_pts()
        test_change_5d_too_high_blocks_pm_pts()
        test_missing_avg_vol_blocks_pm_pts()
        test_breakdown_always_written()
        test_cap_at_max()
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"\nOK: Alle Mock-Tests grün (9/9, EARLINESS_PTS_MAX={EARLINESS_PTS_MAX}).")


if __name__ == "__main__":
    main()
