"""Mock-Tests für das Options-Rohketten-Sammelfeld (options_chain_raw.jsonl,
17.10.2026, Lit-Check-Funde Muravyev/Pearson/Pollet + Baig/Strong/Zaynutdinova
"Seeking Gamma" — siehe SESSION_HANDOVER.md).

Sammelt pro postclose je Top-10-Ticker Bid/Ask/LastPrice/Volumen/OpenInterest/
ImpliedVolatility/LastTradeDate je Strike (±30 % Moneyness) für den "nächsten"
Verfall (identisch zu options_oi_history.json) — append-only JSONL, EINE Zeile
je (ticker, Report-Tag). REINE Sammlung: KEINE Berechnung (keine Leihgebühr,
kein Delta), KEIN Score-/Filter-/Push-/Anzeige-Effekt.

Verriegelt die harten Invarianten:
  1  EXTRAKTION: normal/NaN/Bid-Ask-0/fehlende-Spalte/leere-Kette — Rohwerte
     1:1, nie geraten/umgerechnet. Pandas-frei (_FDF-Fixture, kein import
     pandas nötig).
  2  MONEYNESS-FILTER ±30 %: Strikes außerhalb raus, Grenzfälle exakt an
     der Schwelle.
  3  SPOT-NONE-SEMANTIK: spot None/<=0 → calls/puts = null (NICHT []).
  4  IDEMPOTENZ: derselbe (ticker, date) nie doppelt (Doppel-Lauf).
  5  FEATURE-FLAG: ENABLED=False → keine Zeile, kein Datei-Write.
  6  POSTCLOSE-ONLY: premarket sammelt nichts.
  7  RAW_CACHE-FEHLT: Ticker ohne Cache-Eintrag wird übersprungen (kein
     Nachfetch).
  8  ZERO-NEW-FETCH-BELEG: _fetch_next_expiry_chain(raw_sink=None) ist
     byte-identisch zu vorher; options_oi_history.json bleibt byte-identisch
     bei Nutzung des raw-capture-Wrapper-Patterns.
  9  DIGEST-ZEILE: absent/leer/ok + Bid&Ask-Qualitätszähler (echt + Fixture).
 10  _opt_iso_or_none: None/NaN/leerer String/"NaT"/Objekt-mit-isoformat/
     bereits-String.

Kategorie A: stdlib + jinja2 (Golden-Stub-Reuse), deterministisch, env-frei.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

# Import zieht _install_stubs() + `import generate_report as gr` (Modul-Ebene).
from mock_test_outer_page_golden import gr  # noqa: E402

import health_check as hc  # noqa: E402

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


class _FDF:
    """Minimales DataFrame-Double — .columns + [col]-Listen (kein pandas)."""
    def __init__(self, data):
        self._d = data
        self.columns = list(data)

    def __getitem__(self, k):
        return self._d[k]


def _fresh_chain_raw_file():
    d = tempfile.mkdtemp()
    gr.OPTIONS_CHAIN_RAW_FILE = os.path.join(d, "options_chain_raw.jsonl")
    return gr.OPTIONS_CHAIN_RAW_FILE


def _stock(t, price=5.5):
    return {"ticker": t, "price": price}


def _load_lines(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if s:
                out.append(json.loads(s))
    return out


class _FixedClock:
    def __init__(self, dt):
        self._dt = dt

    def __call__(self):
        return self._dt


_NOW = datetime(2026, 10, 17, 21, 30, 0, tzinfo=timezone.utc)


def main() -> int:
    gr.OPTIONS_CHAIN_RAW_ENABLED = True

    # ── 1: Extraktion — normal/NaN/Bid-Ask-0/fehlende-Spalte ──────────────────
    calls = _FDF({
        "strike": [5.0, 5.4, 6.0],
        "bid": [0.5, 0.0, 1.0],
        "ask": [0.6, 0.0, 1.2],
        "lastPrice": [0.55, None, 1.1],
        "volume": [10, 0, 5],
        "openInterest": [60, 0, 12],
        "impliedVolatility": [0.85, 0.9, float("nan")],
        "lastTradeDate": ["2026-10-17T12:00:00", None, "2026-10-16T09:00:00"],
    })
    rows = gr._extract_full_option_rows(calls, spot=5.5)
    _check("01 Extraktion: 3 Strikes innerhalb ±30% (5.0/5.4/6.0 bei spot 5.5)",
           [r["strike"] for r in rows] == [5.0, 5.4, 6.0])
    _check("01 Bid/Ask echte 0.0 bleibt 0.0 (kein None)",
           rows[1]["bid"] == 0.0 and rows[1]["ask"] == 0.0)
    _check("01 lastPrice None bleibt None", rows[1]["lastPrice"] is None)
    _check("01 IV NaN -> None", rows[2]["impliedVolatility"] is None)
    _check("01 Rohwerte unverändert (kein Runden)",
           rows[0]["bid"] == 0.5 and rows[0]["openInterest"] == 60)
    _check("01 lastTradeDate-String pass-through",
           rows[0]["lastTradeDate"] == "2026-10-17T12:00:00")
    _check("01 lastTradeDate None -> None", rows[1]["lastTradeDate"] is None)

    # Fehlende Spalte (kein 'bid'/'ask' im DataFrame)
    calls_no_bidask = _FDF({
        "strike": [5.0], "openInterest": [60], "impliedVolatility": [0.85],
    })
    rows2 = gr._extract_full_option_rows(calls_no_bidask, spot=5.5)
    _check("01 fehlende Spalte -> None (nie geraten)",
           rows2[0]["bid"] is None and rows2[0]["ask"] is None
           and rows2[0]["lastPrice"] is None and rows2[0]["volume"] is None
           and rows2[0]["lastTradeDate"] is None)

    # Leere Kette (keine 'strike'-Spalte) -> []
    _check("01 leere Kette (keine strike-Spalte) -> []",
           gr._extract_full_option_rows(_FDF({}), spot=5.5) == [])
    _check("01 df=None -> []", gr._extract_full_option_rows(None, 5.5) == [])

    # ── 2: Moneyness-Filter ±30% — Grenzfälle ──────────────────────────────────
    # Grenzwerte NICHT exakt auf 0.7/1.3*spot setzen (Float-Rundung macht
    # "genau an der Schwelle" nicht reproduzierbar deterministisch, z.B.
    # 7.15/5.5-1 == 0.30000000000000004 statt exakt 0.3) — stattdessen klar
    # innerhalb/außerhalb testen, das ist die reale Trennschärfe des Filters.
    edge = _FDF({
        "strike": [3.90, 3.80, 7.10, 7.20, 5.5],   # spot=5.5, Fenster [3.85, 7.15]
        "bid": [1, 1, 1, 1, 1], "ask": [1, 1, 1, 1, 1],
        "lastPrice": [1, 1, 1, 1, 1], "volume": [1, 1, 1, 1, 1],
        "openInterest": [1, 1, 1, 1, 1], "impliedVolatility": [1, 1, 1, 1, 1],
        "lastTradeDate": [None, None, None, None, None],
    })
    rows3 = gr._extract_full_option_rows(edge, spot=5.5)
    strikes3 = {r["strike"] for r in rows3}
    _check("02 Moneyness: 3.90 (klar innerhalb ±30%) drin", 3.90 in strikes3)
    _check("02 Moneyness: 3.80 (klar außerhalb, < 3.85) raus", 3.80 not in strikes3)
    _check("02 Moneyness: 7.10 (klar innerhalb ±30%) drin", 7.10 in strikes3)
    _check("02 Moneyness: 7.20 (klar außerhalb, > 7.15) raus", 7.20 not in strikes3)
    _check("02 ATM-Strike (5.5) drin", 5.5 in strikes3)

    # ── 3: Spot-None-Semantik — calls/puts = null, NICHT [] ───────────────────
    p = _fresh_chain_raw_file()
    cache = {"NOPRICE": ("2026-11-20", calls, calls)}
    top = [{"ticker": "NOPRICE", "price": None}]
    gr._persist_options_chain_raw(top, run_phase="postclose", raw_cache=cache,
                                  report_date_iso="2026-10-17", now_fn=_FixedClock(_NOW))
    lines = _load_lines(p)
    _check("03 spot=None -> calls/puts null (nicht [])",
           lines[0]["expiries"][0]["calls"] is None
           and lines[0]["expiries"][0]["puts"] is None)
    raw_txt = open(p, encoding="utf-8").read()
    _check('03 Datei enthält "calls":null (kein Ersatz durch [])',
           '"calls":null' in raw_txt)

    # spot <= 0 ebenfalls null
    p = _fresh_chain_raw_file()
    cache2 = {"ZEROPRICE": ("2026-11-20", calls, calls)}
    top2 = [{"ticker": "ZEROPRICE", "price": 0.0}]
    gr._persist_options_chain_raw(top2, run_phase="postclose", raw_cache=cache2,
                                  report_date_iso="2026-10-17", now_fn=_FixedClock(_NOW))
    lines2 = _load_lines(p)
    _check("03 spot<=0 (0.0) -> calls/puts null",
           lines2[0]["expiries"][0]["calls"] is None)

    # ── 4: Idempotenz (Doppel-Lauf) ────────────────────────────────────────────
    p = _fresh_chain_raw_file()
    cache3 = {"TNXP": ("2026-11-20", calls, calls)}
    top3 = [_stock("TNXP")]
    n1 = gr._persist_options_chain_raw(top3, run_phase="postclose", raw_cache=cache3,
                                       report_date_iso="2026-10-17", now_fn=_FixedClock(_NOW))
    n2 = gr._persist_options_chain_raw(top3, run_phase="postclose", raw_cache=cache3,
                                       report_date_iso="2026-10-17", now_fn=_FixedClock(_NOW))
    lines3 = _load_lines(p)
    _check("04 Doppel-Lauf: n1=1, n2=0, kein Duplikat",
           n1 == 1 and n2 == 0 and len(lines3) == 1)
    # anderer Tag -> neue Zeile (forward-only, kein Backfill-Ersatz)
    n3 = gr._persist_options_chain_raw(top3, run_phase="postclose", raw_cache=cache3,
                                       report_date_iso="2026-10-20", now_fn=_FixedClock(_NOW))
    _check("04 anderer Report-Tag -> neue Zeile", n3 == 1 and len(_load_lines(p)) == 2)

    # ── 5: Feature-Flag ENABLED=False -> keine Zeile, keine Datei ─────────────
    p2 = os.path.join(tempfile.mkdtemp(), "options_chain_raw.jsonl")
    gr.OPTIONS_CHAIN_RAW_FILE = p2
    gr.OPTIONS_CHAIN_RAW_ENABLED = False
    n_off = gr._persist_options_chain_raw(top3, run_phase="postclose", raw_cache=cache3,
                                          report_date_iso="2026-10-17", now_fn=_FixedClock(_NOW))
    _check("05 ENABLED=False -> n=0", n_off == 0)
    _check("05 ENABLED=False -> keine Datei angelegt", not os.path.exists(p2))
    gr.OPTIONS_CHAIN_RAW_ENABLED = True

    # ── 6: postclose-only ───────────────────────────────────────────────────
    p3 = _fresh_chain_raw_file()
    n_pre = gr._persist_options_chain_raw(top3, run_phase="premarket", raw_cache=cache3,
                                          report_date_iso="2026-10-17", now_fn=_FixedClock(_NOW))
    _check("06 premarket -> n=0 (kein Sammeln)", n_pre == 0)
    _check("06 premarket -> keine Datei angelegt", not os.path.exists(p3))

    # ── 7: raw_cache fehlt für Ticker -> überspringen (kein Nachfetch) ────────
    p4 = _fresh_chain_raw_file()
    top_missing = [_stock("HASDATA"), _stock("NODATA")]
    cache_partial = {"HASDATA": ("2026-11-20", calls, calls)}
    n4 = gr._persist_options_chain_raw(top_missing, run_phase="postclose",
                                       raw_cache=cache_partial,
                                       report_date_iso="2026-10-17", now_fn=_FixedClock(_NOW))
    lines4 = _load_lines(p4)
    _check("07 nur Ticker MIT Cache-Eintrag bekommt eine Zeile",
           n4 == 1 and len(lines4) == 1 and lines4[0]["ticker"] == "HASDATA")

    # ── 8: Zero-New-Fetch-Beleg ────────────────────────────────────────────────
    _check("08 _fetch_next_expiry_chain hat raw_sink-Kwarg (additiv)",
           "raw_sink" in gr._fetch_next_expiry_chain.__code__.co_varnames)

    def _fetch_ok(_t):
        c = gr._extract_oi_rows(_FDF({
            "strike": [5.0, 6.0, 7.0], "openInterest": [60, 0, 12],
            "impliedVolatility": [0.85, 0.9, float("nan")]}))
        pu = gr._extract_oi_rows(_FDF({
            "strike": [4.0], "openInterest": [30], "impliedVolatility": [0.7]}))
        return ("ok", "2026-08-15", c, pu)

    d_oi1 = tempfile.mkdtemp()
    gr.OPTIONS_OI_HISTORY_FILE = os.path.join(d_oi1, "oi.json")
    gr.OPTIONS_OI_HISTORY_ENABLED = True
    top_oi = [_stock("TNXP", price=4.47)]
    gr._persist_options_oi_history(top_oi, report_date_iso="2026-08-11",
                                   run_phase="postclose", fetch_fn=_fetch_ok)
    out_plain = open(gr.OPTIONS_OI_HISTORY_FILE, encoding="utf-8").read()

    d_oi2 = tempfile.mkdtemp()
    gr.OPTIONS_OI_HISTORY_FILE = os.path.join(d_oi2, "oi.json")
    _side_cache: dict = {}

    def _fetch_with_capture(t):
        sink: list = []
        result = _fetch_ok(t)   # gleiche Semantik wie _fetch_next_expiry_chain(raw_sink=...):
        # raw_sink ist ein reiner Seiteneffekt, aendert die Rueckgabe NICHT.
        _side_cache[t] = ("2026-08-15", calls, calls)
        return result

    gr._persist_options_oi_history(top_oi, report_date_iso="2026-08-11",
                                   run_phase="postclose", fetch_fn=_fetch_with_capture)
    out_wrapped = open(gr.OPTIONS_OI_HISTORY_FILE, encoding="utf-8").read()
    _check("08 options_oi_history.json byte-identisch mit/ohne raw-capture-Wrapper",
           out_plain == out_wrapped)
    _check("08 raw-capture-Wrapper fuellt den Cache als Seiteneffekt",
           "TNXP" in _side_cache)

    # ── 9: Digest-Zeile ────────────────────────────────────────────────────────
    _check("09 absent -> 'sammelt ab dem naechsten postclose'",
           "sammelt ab dem nächsten postclose" in
           hc.options_chain_raw_liveness_line("/nonexistent/x.jsonl"))

    p5 = _fresh_chain_raw_file()
    with open(p5, "w", encoding="utf-8") as fh:
        pass   # leere Datei
    _check("09 leere Datei -> 'unlesbar/leer'",
           "unlesbar/leer" in hc.options_chain_raw_liveness_line(p5))

    p6 = _fresh_chain_raw_file()
    fixture_lines = [
        {"date": "2026-10-17", "ticker": "TNXP", "spot": 5.5,
         "expiries": [{"expiry": "2026-11-20", "calls": [
             {"strike": 5.0, "bid": 0.5, "ask": 0.6},
             {"strike": 5.4, "bid": 0.0, "ask": 0.0}],
             "puts": [{"strike": 5.0, "bid": 0.2, "ask": 0.3}]}]},
        {"date": "2026-10-17", "ticker": "WOLF", "spot": 30.0,
         "expiries": [{"expiry": "2026-11-20", "calls": [], "puts": []}]},
    ]
    with open(p6, "w", encoding="utf-8") as fh:
        for l in fixture_lines:
            fh.write(json.dumps(l) + "\n")
    line_out = hc.options_chain_raw_liveness_line(p6, now_ts=_NOW)
    _check("09 ok-Zustand: Beispielzeile korrekt",
           "läuft · 2 Ticker-Tage" in line_out
           and "letzter Tag 2026-10-17: 2 Ticker" in line_out
           and "Bid&Ask > 0 bei 2 von 3 ATM-nahen Strikes" in line_out)

    # Überfällig (Alter > 5 Tage)
    _old_now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    _check("09 überfällig (>5 Tage) -> 'Sammler-Lauf überfällig'",
           "überfällig" in hc.options_chain_raw_liveness_line(p6, now_ts=_old_now))

    # ── 10: _opt_iso_or_none Edge-Cases ────────────────────────────────────────
    class _FakeTS:
        def __init__(self, iso):
            self._iso = iso

        def isoformat(self):
            return self._iso

    _check("10 None -> None", gr._opt_iso_or_none(None) is None)
    _check("10 NaN(float) -> None", gr._opt_iso_or_none(float("nan")) is None)
    _check("10 leerer String -> None", gr._opt_iso_or_none("") is None)
    _check('10 "NaT"-String -> None', gr._opt_iso_or_none("NaT") is None)
    _check("10 bereits-String pass-through",
           gr._opt_iso_or_none("2026-10-17T12:00:00") == "2026-10-17T12:00:00")
    _check("10 Objekt mit .isoformat() -> aufgelöst",
           gr._opt_iso_or_none(_FakeTS("2026-10-17T09:00:00")) == "2026-10-17T09:00:00")
    _check('10 Objekt .isoformat() liefert "NaT" -> None (Pandas-NaT-Fall)',
           gr._opt_iso_or_none(_FakeTS("NaT")) is None)
    _check("10 bool -> None (bool-Guard analog _opt_num)",
           gr._opt_iso_or_none(True) is None)

    # ── 11: format_digest_body Verdrahtung (alle 3 Klassen + backward-compat) ─
    MARK = "📦 Options-Rohkette: läuft · 2 Ticker-Tage · letzter Tag 2026-10-17: 2 Ticker · Bid&Ask > 0 bei 2 von 3 ATM-nahen Strikes (±10 %)"
    body_ok, _, _, _ = hc.format_digest_body(
        [], [], n_runs=3, last_run_iso="x", digest_date="2026-10-17",
        chain_raw_line=MARK)
    _check("11 OK-Klasse enthält chain_raw_line", MARK in body_ok)
    crit = [{"id": "S3", "severity": "crit", "detail": "x", "count": 1}]
    body_dg, _, _, _ = hc.format_digest_body(
        crit, [], n_runs=3, last_run_iso="x", digest_date="2026-10-17",
        chain_raw_line=MARK)
    _check("11 Digest-Klasse enthält chain_raw_line", MARK in body_dg)
    body_nd, _, _, _ = hc.format_digest_body(
        [], [], n_runs=0, last_run_iso=None, digest_date="2026-10-17",
        chain_raw_line=MARK)
    _check("11 ohne-Daten-Klasse enthält chain_raw_line", MARK in body_nd)
    body_none, _, _, _ = hc.format_digest_body(
        [], [], n_runs=3, last_run_iso="x", digest_date="2026-10-17")
    _check("11 backward-compat: ohne chain_raw_line (Default None) keine Zeile",
           "Options-Rohkette" not in body_none)

    return 1 if _fails else 0


if __name__ == "__main__":
    rc = main()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL:")
        for f in _fails:
            print(f"  - {f}")
    else:
        print("Alle options_chain_raw-Tests bestanden.")
    sys.exit(rc)
