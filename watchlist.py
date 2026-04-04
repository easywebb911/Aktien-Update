"""
Static watchlist of curated liquid small/mid-cap tickers per market.
Used by generate_report.py to supplement the Yahoo Finance screener with
international candidates that are rarely surfaced by predefined screeners.

Selection criteria: liquid small/mid-cap stocks (market cap roughly $300M–$10B),
sufficient average daily volume for meaningful relative-volume signals.
"""

WATCHLIST: dict[str, list[str]] = {
    "DE": [
        "AIXA.DE",   # Aixtron SE – semiconductor equipment
        "WAF.DE",    # Siltronic – silicon wafers
        "S92.DE",    # SFC Energy – fuel cells
        "GFT.DE",    # GFT Technologies – IT services
        "DMP.DE",    # Dermapharm – pharmaceuticals
        "VBK.DE",    # Verbio – biofuels
        "SDF.DE",    # K+S AG – potash & salt
        "BC8.DE",    # Bechtle – IT solutions
        "FNTN.DE",   # freenet – telecom
        "EVT.DE",    # Evotec – drug research
        "MBB.DE",    # MBB SE – industrial holding
        "SMHN.DE",   # Südzucker – food/bio-ethanol
        "NWX.DE",    # Nagarro – software engineering
        "SIX2.DE",   # Sixt SE – car rental
        "HOB.DE",    # Hoberg & Driesch
        "UTDI.DE",   # United Internet
        "KSB.DE",    # KSB SE – pumps & valves
        "DHER.DE",   # Delivery Hero – food delivery
        "NCH2.DE",   # Nucera – hydrogen
        "HFG.DE",    # HelloFresh – meal kits
        "O2D.DE",    # Telefonica Deutschland
        "MOR.DE",    # MorphoSys – biotech
    ],
    "GB": [
        "SDRY.L",    # Superdry – clothing
        "CARD.L",    # Card Factory – greetings
        "TRN.L",     # Trainline – rail ticketing
        "ROO.L",     # Deliveroo – food delivery
        "MONY.L",    # Moneysupermarket – fintech
        "REC.L",     # Record – currency mgmt
        "HTG.L",     # Hunting – oil services
        "JD.L",      # JD Sports Fashion
        "FOUR.L",    # 4imprint – promotional products
        "WOSG.L",    # Watches of Switzerland
        "AUTO.L",    # Auto Trader Group
        "BBY.L",     # Balfour Beatty – infrastructure
        "OSB.L",     # OneSavings Bank
        "AFX.L",     # Alpha FX – FX services
        "FDM.L",     # FDM Group – IT staffing
        "ITV.L",     # ITV – media
        "PETS.L",    # Pets at Home
        "NWG.L",     # NatWest Group – banking
        "SGE.L",     # Sage Group – software
        "IGG.L",     # IG Group – trading
        "TUNE.L",    # Focusrite – audio equipment
        "KIE.L",     # Kier Group – construction
        "CMX.L",     # Chemring Group
    ],
    "FR": [
        "SESL.PA",   # SES-imagotag – digital labels
        "ECA.PA",    # Euroapi – APIs pharma
        "OSE.PA",    # OSE Immunotherapeutics
        "ABCA.PA",   # ABC arbitrage
        "FII.PA",    # Figeac Aero – aerospace
        "ALSPW.PA",  # Spie SA
        "ALCRB.PA",  # Carbios – biotech
        "ALMDG.PA",  # Median Technologies
        "MLCMG.PA",  # CM-CIC
        "ODET.PA",   # Bolloré (holding)
        "BI.PA",     # Bigben Interactive – gaming
        "IGTE.PA",   # iGTech
        "VLTSA.PA",  # Voltalia – renewable energy
        "NEOEN.PA",  # Neoen – renewable energy
        "ALTUR.PA",  # Turenne
        "MTRX.PA",   # Matryx
        "MLAGI.PA",  # Agile Content
        "ALSEI.PA",  # Séché Environnement
        "PROAC.PA",  # Proactel
        "PRESC.PA",  # Prescient Mining
        "ALSTG.PA",  # Stago
        "HCO.PA",    # Hexaôm – construction
        "LDLD.PA",   # Leyland SDM
    ],
    "NL": [
        "BESI.AS",   # BE Semiconductor – semiconductor
        "HEIJM.AS",  # Heijmans – construction
        "TKWY.AS",   # Takeaway.com – food delivery
        "BAMNB.AS",  # BAM Group – construction
        "AALB.AS",   # Aalberts – industrial
        "CTP.AS",    # CTP NV – real estate
        "IMCD.AS",   # IMCD Group – chemicals
        "SGNL.AS",   # Signify – lighting
        "AKZA.AS",   # Akzo Nobel – paints
        "NN.AS",     # NN Group – insurance
        "FFARM.AS",  # Forfarmers – animal nutrition
        "PHARM.AS",  # Pharming Group – biotech
        "ACOMO.AS",  # Acomo – commodities
        "TOM2.AS",   # TomTom – navigation
        "SBMO.AS",   # SBM Offshore – offshore energy
        "WKL.AS",    # Wolters Kluwer
        "CORA.AS",   # Corbion – biochemicals
        "VGP.AS",    # VGP NV – logistics real estate
        "HYDRA.AS",  # Hydratec Industries
        "RAND.AS",   # Randstad – staffing
        "CTPNV.AS",  # CTP NV
        "FLOW.AS",   # Flow Traders – market making
        "NSI.AS",    # NSI NV – real estate
        "CTAC.AS",   # Ctac NV – IT
        "OCI.AS",    # OCI NV – fertilisers
    ],
    "CA": [
        "WELL.TO",   # WELL Health – digital health
        "LSPD.TO",   # Lightspeed Commerce – POS
        "HUT.TO",    # HUT 8 – bitcoin mining
        "HIVE.TO",   # HIVE Digital – crypto mining
        "BB.TO",     # BlackBerry – cybersecurity
        "ACB.TO",    # Aurora Cannabis
        "CRON.TO",   # Cronos Group – cannabis
        "CLS.TO",    # Celestica – electronics
        "AR.TO",     # Argonaut Gold
        "BTO.TO",    # B2Gold – gold mining
        "NGT.TO",    # Nighthawk Gold
        "LUN.TO",    # Lundin Mining – copper
        "FM.TO",     # First Quantum Minerals
        "IMG.TO",    # IAMGOLD
        "OR.TO",     # Osisko Gold Royalties
        "GCM.TO",    # GCM Mining
        "TLRY.TO",   # Tilray – cannabis
        "WEED.TO",   # Canopy Growth – cannabis
        "PHO.TO",    # Phoebe Energy
        "DCBO.TO",   # Docebo – e-learning
        "KXS.TO",    # Kinaxis – supply chain
        "ENGH.TO",   # Enghouse Systems
        "GIB-A.TO",  # CGI Group – IT services
        "BIR.TO",    # Birchcliff Energy
    ],
    "JP": [
        "6920.T",    # Lasertec – EUV inspection
        "4385.T",    # Mercari – marketplace
        "2432.T",    # DeNA – mobile gaming
        "3659.T",    # Nexon – online gaming
        "6532.T",    # BayCurrent Consulting
        "4519.T",    # Chugai Pharmaceutical
        "4552.T",    # JCR Pharmaceuticals
        "7735.T",    # Screen Holdings – wafer processing
        "6146.T",    # Disco Corp – semiconductor tools
        "4689.T",    # Z Holdings – internet
        "3765.T",    # GungHo Online – gaming
        "2413.T",    # M3 – medical platform
        "6594.T",    # Nidec – motors
        "4563.T",    # AnGes – gene therapy
        "6758.T",    # Sony Group
        "7267.T",    # Honda Motor
        "9984.T",    # SoftBank Group
        "3861.T",    # Oji Holdings – paper
        "6702.T",    # Fujitsu
        "4021.T",    # Nissan Chemical
        "6366.T",    # Chiyoda – engineering
        "7912.T",    # Dai Nippon Printing
        "4503.T",    # Astellas Pharma
        "6770.T",    # Alps Alpine – electronics
    ],
    "HK": [
        "0241.HK",   # Ali Health – healthcare
        "0268.HK",   # Kingdee – enterprise software
        "1478.HK",   # Q Technology – camera modules
        "6060.HK",   # ZhongAn Online – insurtech
        "2382.HK",   # Sunny Optical – optical products
        "0285.HK",   # BYD Electronic – components
        "3888.HK",   # Kingsoft – software
        "0772.HK",   # China Literature – online reading
        "1024.HK",   # Kuaishou – short video
        "6690.HK",   # Haier Smart Home
        "0981.HK",   # SMIC – chip foundry
        "1347.HK",   # Hua Hong Semiconductor
        "0992.HK",   # Lenovo Group
        "1357.HK",   # Meitu – apps
        "2015.HK",   # Li Auto – EVs
        "9868.HK",   # Xpeng Motors – EVs
        "2238.HK",   # GAC Group – autos
        "0522.HK",   # ASM Pacific – assembly equipment
        "1211.HK",   # BYD Co – EVs & batteries
        "3690.HK",   # Meituan – super-app
        "0669.HK",   # Techtronic Industries
        "1810.HK",   # Xiaomi – electronics
        "0020.HK",   # SJM Holdings – gaming
        "0175.HK",   # Geely Automobile
        "0700.HK",   # Tencent Holdings
    ],
    "KR": [
        "035420.KS",  # NAVER – search & e-commerce
        "035720.KS",  # Kakao – messaging & fintech
        "011200.KS",  # HMM – shipping
        "086280.KS",  # Hyundai Glovis – logistics
        "271560.KS",  # Orion – snacks
        "003490.KS",  # Korean Air
        "326030.KS",  # SK Bioscience – vaccines
        "293490.KS",  # Kakao Pay – fintech
        "035900.KS",  # JYP Entertainment
        "352820.KS",  # HYBE – K-pop
        "251270.KS",  # Netmarble – gaming
        "036570.KS",  # NCsoft – gaming
        "263750.KS",  # Pearl Abyss – gaming
        "259960.KS",  # Krafton – gaming
        "010130.KS",  # Korea Zinc – metals
        "096770.KS",  # SK Innovation – energy
        "009150.KS",  # Samsung Electro-Mechanics
        "018260.KS",  # Samsung SDS – IT services
        "028260.KS",  # Samsung C&T – trading
        "012330.KS",  # Hyundai Mobis – auto parts
        "000270.KS",  # Kia – autos
        "051910.KS",  # LG Chem – battery materials
        "066570.KS",  # LG Electronics
        "034730.KS",  # SK Inc. – holding
        "017670.KS",  # SK Telecom
    ],
}
