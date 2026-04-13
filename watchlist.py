# Manuell gepflegt: echte lokale Aktien je Börse
"""
Static watchlist of liquid local-exchange tickers per market.
Maintained manually — do not overwrite with US screener results.

Each region contains genuine stocks listed on the respective exchange.
update_watchlist.py uses these as seed tickers and may add screener results.
"""

WATCHLIST: dict[str, list[str]] = {
    "DE": [  # XETRA / Frankfurt
        "SAP.DE",
        "SIE.DE",
        "BAS.DE",
        "MBG.DE",
        "VOW3.DE",
        "RHM.DE",
        "P911.DE",
        "TUI1.DE",
        "LEG.DE",
        "TAG.DE",
        "AIXA.DE",
        "EVTG.DE",
        "NFON.DE",
        "PVA.DE",
        "SGL.DE",
    ],
    "GB": [  # London Stock Exchange
        "SHEL.L",
        "BP.L",
        "LLOY.L",
        "BARC.L",
        "VOD.L",
        "IAG.L",
        "NXT.L",
        "OCDO.L",
        "THG.L",
        "BOOH.L",
        "AO.L",
    ],
    "FR": [  # Euronext Paris
        "AIR.PA",
        "TTE.PA",
        "SAN.PA",
        "BNP.PA",
        "MC.PA",
        "ORA.PA",
        "VIE.PA",
        "HO.PA",
        "GENFIT.PA",
        "VALNEVA.PA",
    ],
    "NL": [  # Euronext Amsterdam
        "ASML.AS",
        "PHIA.AS",
        "ING.AS",
        "BAMNB.AS",
        "HEIJM.AS",
    ],
    "CA": [  # Toronto / TSX
        "BB.TO",
        "TLRY.TO",
        "HIVE.TO",
        "BITF.TO",
        "WEED.TO",
        "ACB.TO",
        "CRON.TO",
        "HUT.TO",
    ],
    "JP": [  # Tokyo Stock Exchange
        "7203.T",
        "9984.T",
        "6758.T",
        "7267.T",
        "9433.T",
        "6861.T",
        "4063.T",
        "8306.T",
    ],
    "HK": [  # Hong Kong Stock Exchange
        "0700.HK",
        "0941.HK",
        "0005.HK",
        "1299.HK",
        "0388.HK",
        "2318.HK",
        "0992.HK",
        "2382.HK",
        "0175.HK",
    ],
    "KR": [  # Korea Exchange
        "005930.KS",
        "000660.KS",
        "035420.KS",
        "051910.KS",
        "006400.KS",
        "207940.KS",
    ],
}
