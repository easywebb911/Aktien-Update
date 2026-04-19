#!/usr/bin/env python3
"""
update_watchlist.py — Regenerate watchlist.py from curated seed tickers.

Runs weekly (Sunday 08:00 MEZ) via GitHub Actions and can be triggered manually.
Does NOT touch generate_report.py or any other files.

The screener-based ticker discovery was disabled because Yahoo Finance's
international predefined screeners (day_gainers, most_actives, …) return mostly
low-quality or already-delisted symbols. Only the curated ``_INTL_SEED_TICKERS``
are written, filtered against ``watchlist_inactive.json`` so delisted tickers
never reappear in the watchlist.
"""

import json
import logging
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WATCHLIST_FILE    = "watchlist.py"
INACTIVE_FILE     = "watchlist_inactive.json"
MIN_TOTAL_TICKERS = 50   # safety guard: abort if seeds minus inactive drop below this

# Seed tickers per region — curated list of liquid local-exchange stocks.
# MAX_PER_REGION is effectively ``len(seeds)`` — no screener fill-up any more.
_INTL_SEED_TICKERS: dict[str, list[str]] = {
    "DE": ["SAP.DE","SIE.DE","BAS.DE","MBG.DE","VOW3.DE","RHM.DE","P911.DE",
           "TUI1.DE","LEG.DE","TAG.DE","AIXA.DE","EVTG.DE","NFON.DE","PVA.DE","SGL.DE"],
    "GB": ["SHEL.L","BP.L","LLOY.L","BARC.L","VOD.L","IAG.L","NXT.L",
           "MKS.L","OCDO.L","THG.L","BOOH.L","AO.L"],
    "FR": ["AIR.PA","TTE.PA","SAN.PA","BNP.PA","MC.PA","ORA.PA",
           "VIE.PA","HO.PA","CGG.PA","GENFIT.PA","VALNEVA.PA"],
    "NL": ["ASML.AS","PHIA.AS","ING.AS","BAMNB.AS","HEIJM.AS","TKWY.AS","HYDRA.AS"],
    "CA": ["BB.TO","TLRY.TO","HIVE.TO","BITF.TO","WEED.TO","ACB.TO",
           "CRON.TO","SNDL.TO","HUT.TO"],
    "JP": ["7203.T","9984.T","6758.T","7267.T","9433.T","6861.T","4063.T","8306.T"],
    "HK": ["0700.HK","0941.HK","0005.HK","1299.HK","0388.HK",
           "2318.HK","0992.HK","2382.HK","0175.HK"],
    "KR": ["005930.KS","000660.KS","035420.KS","051910.KS",
           "006400.KS","207940.KS"],
}

# Region comments shown in the generated watchlist.py
_REGION_LABELS: dict[str, str] = {
    "DE": "XETRA / Frankfurt",
    "GB": "London Stock Exchange",
    "FR": "Euronext Paris",
    "NL": "Euronext Amsterdam",
    "CA": "Toronto / TSX",
    "JP": "Tokyo Stock Exchange",
    "HK": "Hong Kong Stock Exchange",
    "KR": "Korea Exchange",
}


# ---------------------------------------------------------------------------
# Inactive-ticker blacklist
# ---------------------------------------------------------------------------

def _load_inactive() -> set[str]:
    """Load tickers marked inactive by generate_report.py's watchlist scan."""
    try:
        with open(INACTIVE_FILE) as f:
            data = json.load(f)
    except Exception:
        return set()
    # Accept either {"tickers": [...]} or bare list
    if isinstance(data, dict):
        return set(data.get("tickers", []))
    if isinstance(data, list):
        return set(data)
    return set()


# ---------------------------------------------------------------------------
# watchlist.py writer
# ---------------------------------------------------------------------------

def _format_watchlist_py(watchlist: dict[str, list[str]], timestamp: str) -> str:
    """Render the watchlist as valid Python source."""
    lines: list[str] = [
        f'# Automatisch aktualisiert: {timestamp}',
        '"""',
        'Auto-generated watchlist of curated local-exchange tickers per market.',
        'Updated weekly by update_watchlist.py — do not edit manually.',
        '',
        'Only curated seed tickers are written; the screener-based enrichment',
        'was disabled to keep the watchlist limited to liquid local stocks.',
        'Delisted tickers from watchlist_inactive.json are excluded.',
        '"""',
        '',
        'WATCHLIST: dict[str, list[str]] = {',
    ]
    for region, tickers in watchlist.items():
        label = _REGION_LABELS.get(region, region)
        lines.append(f'    "{region}": [  # {label}')
        for t in tickers:
            lines.append(f'        "{t}",')
        lines.append('    ],')
    lines.append('}')
    lines.append('')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    log.info("=== update_watchlist.py started at %s ===", timestamp)

    inactive = _load_inactive()
    if inactive:
        log.info("Blacklist: %d delisted tickers from %s", len(inactive), INACTIVE_FILE)

    new_watchlist: dict[str, list[str]] = {}
    for region, seeds in _INTL_SEED_TICKERS.items():
        active = [t for t in seeds if t not in inactive]
        skipped = len(seeds) - len(active)
        new_watchlist[region] = active
        log.info("Region %s: %d seeds → %d active (%d blacklisted)",
                 region, len(seeds), len(active), skipped)

    total = sum(len(v) for v in new_watchlist.values())
    if total < MIN_TOTAL_TICKERS:
        print(
            f"Watchlist-Update abgebrochen: nur {total} Ticker übrig, "
            f"Mindest {MIN_TOTAL_TICKERS} nicht erreicht",
            flush=True,
        )
        log.error(
            "Aborting: %d tickers is below safety threshold %d. watchlist.py unchanged.",
            total, MIN_TOTAL_TICKERS,
        )
        sys.exit(1)

    content = _format_watchlist_py(new_watchlist, timestamp)
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as fh:
        fh.write(content)

    per_region = {r: len(v) for r, v in new_watchlist.items()}
    print(
        f"Watchlist aktualisiert: {per_region}, Gesamt: {total}",
        flush=True,
    )
    for region, n in per_region.items():
        log.info("  %s: %d Ticker", region, n)
    log.info("watchlist.py written (%d total tickers)", total)


if __name__ == "__main__":
    main()
