#!/usr/bin/env python3
"""Mock-Tests für die Wegwerf-Probe Mehrjahres-Rückrechnung (stdlib-only, kein Netz).

Prüft die reinen Hilfsfunktionen (Kategorie-/Zuordnungsregel, Stichprobe,
Konfidenz, DTC-Hälften, Veröffentlichungs-Verzug, Verbleib eines Symbols,
Split-Flag-Klasse, Überschneidung, Proxy-Score-Teile, yfinance-Fehlergründe),
das vorab festgeschriebene Gültigkeitskriterium, die Blindheit (kein
Ergebnisfeld, aus Backtest-Dateien nur ticker/date), den Teilbefund bei Abbruch
und den Workflow (nur Hand-Start, contents: read, keine Secrets, kein Push).
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import probe_rueckrechnung as pr  # noqa: E402

SRC = (ROOT / "scripts" / "probe_rueckrechnung.py").read_text(encoding="utf-8")
WF = (ROOT / ".github" / "workflows" / "probe_rueckrechnung.yml").read_text(encoding="utf-8")
FAILS: list[str] = []


def check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


def main() -> int:
    check("01 Stichprobe n = 2401 (±2 pp, p = 0,5)", pr.SAMPLE_N == 2401)
    check("02 Gültigkeitskriterium Kontrolle vorab 0,97", pr.CONTROL_MIN == 0.97)
    w = pr.wilson(50, 100)
    check("03 Wilson 50/100 ≈ [0,40; 0,60]", w["ki95"][0] < 0.41 and w["ki95"][1] > 0.59)
    check("04 Wilson n=0 → None", pr.wilson(0, 0) is None)
    pop = [f"S{i}" for i in range(5000)]
    a = pr.draw_sample(pop, 2021)
    check("05 Stichprobe deterministisch, Reihenfolge egal",
          a == pr.draw_sample(list(reversed(pop)), 2021) and len(a) == 2401)
    check("06 kleine Grundgesamtheit → Vollerhebung", pr.draw_sample(["B", "A"], 2021) == ["A", "B"])
    # Zuordnungsregel
    cases = {
        ("AAPL", "Apple Inc. Common Stock"): "stamm",
        ("BRK.B", "Berkshire Hathaway Inc. Class B"): "klasse",
        ("BRK B", "Berkshire Hathaway Inc. Class B"): "klasse",
        ("SPY", "SPDR S&P 500 ETF Trust"): "etf_fonds",
        ("ABCDW", "Acme Corp Warrants"): "optionsschein",
        ("XYZ WS", "Xyz Holdings"): "optionsschein",
        ("ABCDU", "Acme Acquisition Corp Units"): "unit",
        ("ABCDR", "Acme Acquisition Corp Rights"): "right",
        ("BAC PRL", "Bank of America 7.25% Pfd"): "vorzug",
        ("ZVZZT", "NASDAQ TEST STOCK"): "test",
        ("XYZ", "Xyz 5.00% Senior Notes due 2030"): "vorzug",
        ("ABC1", "Weird"): "sonstiges",
        ("BDN", "Brandywine Realty Trust"): "stamm",
        ("TSM", "Taiwan Semiconductor American Depositary Shares"): "stamm",
        ("SOXL", "Direxion Daily Semiconductor Bull 3X Shares"): "etf_fonds",
    }
    bad = {k: pr.category(*k) for k, v in cases.items() if pr.category(*k) != v}
    check(f"07 Kategorie-Regel ({len(cases)} Fälle) {bad or ''}", not bad)
    check("08 Stammaktie = stamm + klasse", pr.is_stock("BRK.B", "Berkshire B") and not pr.is_stock("SPY", "SPDR ETF"))
    check("09 yfinance-Schreibweise", pr.yf_symbol("BRK.B") == "BRK-B" and pr.yf_symbol("brk b") == "BRK-B"
          and pr.yf_symbol("BF/A") == "BF-A")
    check("10 Symbol-Muster", pr.symbol_pattern("BRK.B") == "AAA.A")
    check("11 Name-Schlüssel ohne Rechtsform",
          pr.name_key("Apple Inc. Common Stock") == "APPLE" and pr.name_key("Acme Holdings Corp") == "ACME"
          and pr.name_key("Bank of America Corp") != pr.name_key("Bank of New York Mellon"))
    low, high, med = pr.split_halves({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": None})
    check("12 DTC-Hälften am Median", low == {"A", "B"} and high == {"C", "D"} and med == 2.5)
    check("13 DTC aus Feld / aus SI-ADV / None",
          pr.dtc_of(100, 50, 3.5) == 3.5 and pr.dtc_of(100, 50, None) == 2.0 and pr.dtc_of(100, None, None) is None)
    check("14 Werktage über Wochenende", pr.business_days_after(date(2026, 11, 13), 7) == date(2026, 11, 24))
    check("15 Werktage zwischen (31.12.2025 → 12.01.2026, Neujahr) = 7",
          pr.business_days_between(date(2025, 12, 31), date(2026, 1, 12), frozenset({"2026-01-01"})) == 7)
    s = [date(2026, 10, 15), date(2026, 10, 30)]
    check("16 Stichtag erst nach Veröffentlichung (8 Werktage)",
          pr.latest_usable_settlement(date(2026, 11, 10), s) == date(2026, 10, 15)
          and pr.latest_usable_settlement(date(2026, 11, 11), s) == date(2026, 10, 30)
          and pr.latest_usable_settlement(date(2026, 10, 20), s) is None)
    later = {"AAA": {"name": "Alpha Inc", "market": "NYSE"}, "BBB": {"name": "Beta Corp", "market": "OTC"},
             "CCC": {"name": "Completely Other Co", "market": "NNM"}, "DDX": {"name": "Delta Inc", "market": "NNM"}}
    names = {}
    for k, v in later.items():
        names.setdefault(pr.name_key(v["name"]), set()).add(k)
    f = {sym: pr.fate(sym, {"name": nm}, later, names) for sym, nm in
         (("AAA", "Alpha Inc."), ("BBB", "Beta Corp"), ("CCC", "Gamma Inc"), ("DDD", "Delta Inc"),
          ("EEE", "Epsilon Ltd"))}
    check("17 Verbleib: gelistet/otc/neu_vergeben/kuerzel_gewechselt/verschwunden",
          f == {"AAA": "gelistet", "BBB": "otc", "CCC": "neu_vergeben", "DDD": "kuerzel_gewechselt",
                "EEE": "verschwunden"})
    check("18 Split-Flag: Vorperiode roh / angepasst",
          pr.classify_split_flag(1000, 1000) == "vorperiode_roh"
          and pr.classify_split_flag(100, 1000) == "vorperiode_angepasst"
          and pr.classify_split_flag(None, 1000) == "unklar")
    o = pr.overlap_stats([({"A", "B"}, {"A", "C"}), ({"A"}, {"B"}), (set(), {"A"})])
    check("19 Überschneidung", o["tage"] == 2 and o["mittel"] == 0.5 and o["verteilung"]["1"] == 1)
    check("20 Gap/RS-Punkte", pr.gap_pts(110, 100, 120) == 5.0 and pr.gap_pts(110, 100, 99) == -3.0
          and pr.rs_pts(50) == 3.0 and pr.rs_pts(None) == 0.0)
    check("21 Proxy-Score Maximum ohne Gap/RS", pr.proxy_score(60, 12, 5, 20, 0, 0, True) == 32 + 23 + 23 + 14 + 5)
    check("22 yfinance-Fehlergründe",
          pr.yf_err_category("Too Many Requests") == "rate_limit"
          and pr.yf_err_category("$XYZ: possibly delisted; no timezone found") == "possibly_delisted"
          and pr.yf_err_category("read timed out") == "netz")
    # Blindheit
    code = re.sub(r'"""(.|\n)*?"""', "", SRC)
    check("23 kein Ergebnisfeld im Code",
          not re.search(r"return_\d|max_gain|max_drawdown|outcome_path|forward_\d", code))
    check("24 aus Backtest-Dateien nur ticker/date/bootstrap",
          set(re.findall(r'\be\.get\("(\w+)"\)', SRC)) <= {"ticker", "date", "bootstrap", "source"})
    check("25 SEC-User-Agent generisch .invalid", "@example.invalid" in pr.SEC_UA)
    # Workflow
    check("26 nur Hand-Start", "workflow_dispatch" in WF and "schedule" not in WF and "push:" not in WF)
    check("27 contents: read, keine Schreibrechte", "contents: read" in WF and "write" not in WF)
    check("28 keine Secrets, kein Push", "secrets." not in WF and "git push" not in WF)
    check("29 Abschnitt wählbar, Artifact auch bei Abbruch",
          "options: [alle, survivorship, proxy]" in WF and "if: always()" in WF)
    # Teilbefund bei Abbruch
    saved = (pr.probe_p1, pr.probe_p2f, pr.probe_p5, pr.probe_p7)

    def _p1(result):
        result["P1"] = {"ok": 1}
        return [date(2026, 1, 15)]

    def _p2f(result, sd):
        result["P2F"] = {"halb": 1}
        raise pr.RateLimited("simuliert")
    pr.probe_p1, pr.probe_p2f = _p1, _p2f
    pr.probe_p5 = lambda *a: (_ for _ in ()).throw(AssertionError("darf nicht laufen"))
    try:
        outp = pathlib.Path(tempfile.mkdtemp()) / "r.json"
        rc = pr.main(["--out", str(outp)])
        res = json.loads(outp.read_text(encoding="utf-8"))
        check("30 Abbruch: Exit 3, P1 bleibt, P2F verworfen",
              rc == 3 and res["abgebrochen_in"] == "P2F" and res["P1"] == {"ok": 1}
              and "P2F" not in res and res["abschnitte_vollstaendig"] == ["P1"])
        def _p2f_err(result, sd):
            raise ValueError("Netzfehler simuliert")
        pr.probe_p2f = _p2f_err
        rc = pr.main(["--out", str(outp)])
        res = json.loads(outp.read_text(encoding="utf-8"))
        check("30b anderer Fehler: Exit 4, Teilbefund P1 geschrieben",
              rc == 4 and res["abgebrochen_in"] == "P2F" and res["P1"] == {"ok": 1})
        calls = []
        pr.probe_p5 = lambda *a: calls.append("P5")
        pr.probe_p7 = lambda *a: calls.append("P7")
        rc = pr.main(["--out", str(outp), "--nur", "proxy"])
        check("31 --nur proxy: nur P5, keine P7", rc == 0 and calls == ["P5"])
    finally:
        pr.probe_p1, pr.probe_p2f, pr.probe_p5, pr.probe_p7 = saved
    old = pr.PROBE_END
    pr.PROBE_END = date(2000, 1, 1)
    try:
        check("32 nach PROBE_END no-op", pr.main(["--out", "/nonexistent/x.json"]) == 0)
    finally:
        pr.PROBE_END = old
    if FAILS:
        print(f"{len(FAILS)} FAIL: {FAILS}")
        return 1
    print("Alle probe_rueckrechnung-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
