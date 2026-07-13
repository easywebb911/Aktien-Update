"""Mock-Tests für die SI-Positions-Zeitreihe (forward-only Sammlung).

Verifiziert den Bau aus dem Diagnose-Plan (Paper-Schritt A+B-Entblockung):
persistiert die ausstehende Short-POSITION (nicht Volumen) settlement-datiert
aus yfinance-.info-Feldern, die im selben Batch-.info-Dict wie short_float_yf
geholt werden (KEIN zusätzlicher .info-Call).

Sechs Test-Kategorien (Minimum aus dem Auftrag):
  1. MERGE-ASSERTION (#411-Absicherung): die 4 yf_*-Felder sind im
     c.update-Merge-Whitelist UND in beiden Read-Pfaden (Batch + Singleton)
     — Source-Inspektion, der eigentliche Fix gegen die gedroppte-Whitelist-
     Bug-Klasse.
  2. SEED-2-PUNKTE: Erststart pro Ticker → Vormonat + aktuell (Delta ab Tag 1).
  3. DEDUP: neuer Punkt nur bei geändertem settlement_date; None → kein Punkt.
  4. PUB_DATE: epoch→date→finra_publication_date (#408), fail-soft.
  5. LOOK-AHEAD-ISOLATION: die Serien-Felder werden NIEMALS in Score-/Filter-/
     Push-Pfaden gelesen (Grep-Guard analog entry_past_return_5d E1-E6).
  6. RETENTION: 400d-Cutoff + Cap 24/Ticker (KEIN 14d-Prune-Leak).

generate_report importiert schwere Module top-level (yfinance, bs4,
deep_translator) — die werden vor dem Import gestubbt (analog CI-Vertrag).
Funktionale Tests nutzen einen tempfile-Pfad statt der echten Datei.

Ausführung: ``python scripts/mock_test_si_position_history.py``.
Exit 0 bei Erfolg, 1 bei Fail.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# Drittlib-Stubs für die Test-Sandbox (CI-Install = NUR jinja2 + pyyaml;
# requests/yfinance/bs4/deep_translator/watchlist sind NICHT da → müssen VOR
# dem generate_report-Import gestubbt werden. Kanonisches Muster analog
# mock_test_short_situation_none_guard.py:_install_stubs — inkl. requests
# (Session/get/exceptions), das der ursprüngliche Stub-Satz vergaß und
# deshalb im CI-ALLOWLIST-Runner rot lief).
def _install_stubs() -> None:
    if "yfinance" not in sys.modules:
        yf = types.ModuleType("yfinance")
        yf.download = lambda *a, **k: None
        yf.Ticker = lambda *a, **k: None
        sys.modules["yfinance"] = yf
    if "requests" not in sys.modules:
        rq = types.ModuleType("requests")
        rq.Session = lambda *a, **k: types.SimpleNamespace(
            headers=types.SimpleNamespace(update=lambda *a, **k: None))
        rq.get = lambda *a, **k: None
        rq.exceptions = types.SimpleNamespace(RequestException=Exception)
        sys.modules["requests"] = rq
    if "bs4" not in sys.modules:
        bs4 = types.ModuleType("bs4")
        bs4.BeautifulSoup = lambda *a, **k: None
        sys.modules["bs4"] = bs4
    if "deep_translator" not in sys.modules:
        dt = types.ModuleType("deep_translator")
        dt.GoogleTranslator = lambda *a, **k: types.SimpleNamespace(
            translate=lambda s: s)
        sys.modules["deep_translator"] = dt
    if "watchlist" not in sys.modules:
        wl = types.ModuleType("watchlist")
        wl.WATCHLIST = []
        sys.modules["watchlist"] = wl


_install_stubs()
import generate_report as gr  # noqa: E402
import config  # noqa: E402


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail and not cond:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def _epoch(iso: str) -> int:
    """ISO-Datum → epoch-Sekunden (UTC-Mitternacht), wie yfinance liefert."""
    return int(_dt.datetime.strptime(iso, "%Y-%m-%d")
               .replace(tzinfo=_dt.timezone.utc).timestamp())


# ── (1) MERGE-ASSERTION — Source-Inspektion (#411-Absicherung) ───────────────
def _test_merge_and_read_wiring():
    print("── (1) Merge-Durchreichung + Read-Pfade (#411-Absicherung) ───")
    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")

    fields = [
        "yf_shares_short",
        "yf_shares_short_prior",
        "yf_si_settlement_ts",
        "yf_si_prev_settlement_ts",
    ]

    # PRIMÄR-FIX: c.update-Merge-Whitelist reicht alle 4 Felder durch.
    for f in fields:
        _check(
            f"1a c.update-Merge reicht {f} durch (PRIMÄR-FIX)",
            f'"{f}":          yfd.get("{f}"),' in gr_src
            or f'"{f}": yfd.get("{f}"),' in gr_src
            or f'yfd.get("{f}")' in gr_src,
            "ohne Merge-Eintrag bleibt das Feld None (gedroppte-Whitelist-Bug)",
        )

    # Read-Pfade: beide Records lesen aus dem info-Dict (kein neuer .info-Call).
    # Whitespace-agnostisch (Alignment-Spaces variieren) via Regex.
    import re
    for f, yk in (
        ("yf_shares_short", "sharesShort"),
        ("yf_shares_short_prior", "sharesShortPriorMonth"),
        ("yf_si_settlement_ts", "dateShortInterest"),
        ("yf_si_prev_settlement_ts", "sharesShortPreviousMonthDate"),
    ):
        n = len(re.findall(
            rf'"{f}":\s*info\.get\("{yk}"\)', gr_src))
        _check(
            f"1b {f} = info.get({yk}) in BEIDEN Read-Pfaden (Batch+Singleton)",
            n >= 2,
            f"nur {n}× gefunden — Batch _hist_stats + get_yfinance_data nötig",
        )

    # KEIN neuer .info-Call: keine zusätzliche yf.Ticker(...).info-Zeile für SI.
    # (Der bestehende _fetch_si_trend_from_yfinance-Call bleibt der einzige
    # separate .info-Zugriff — er ist NICHT Teil dieses Features.)
    _check(
        "1c Merge-Kommentar verweist auf #411-Bug-Klasse",
        "identische #411-Bug" in gr_src or "#411-Bug-Klasse" in gr_src,
        "Merge-Anker-Kommentar fehlt",
    )


# ── (2)+(3)+(4)+(6) Funktionale Tests über tempfile ──────────────────────────
def _with_temp_file(fn):
    tmp = tempfile.mkdtemp()
    orig = gr.SI_POSITION_HISTORY_FILE
    gr.SI_POSITION_HISTORY_FILE = os.path.join(tmp, "si_position_history.json")
    try:
        fn()
    finally:
        gr.SI_POSITION_HISTORY_FILE = orig


def _amc(**ov):
    base = {
        "ticker": "AMC", "market": "US",
        "yf_shares_short": 88_100_000,
        "yf_shares_short_prior": 92_500_000,
        "yf_si_settlement_ts": _epoch("2026-06-30"),
        "yf_si_prev_settlement_ts": _epoch("2026-05-29"),
        "short_float": 20.1,
    }
    base.update(ov)
    return base


def _test_seed_two_points():
    print("── (2) Seed-2-Punkte beim Erststart ──────────────────────────")

    def body():
        added = gr._persist_si_position_history([_amc()])
        data = json.load(open(gr.SI_POSITION_HISTORY_FILE))
        pts = data.get("AMC", [])
        _check("2a Erststart seedet 2 Punkte", added == 2, f"added={added}")
        _check("2b Serie hat 2 Punkte", len(pts) == 2, f"n={len(pts)}")
        _check("2c Punkt A = Vormonat 2026-05-29",
               pts[0]["settlement_date"] == "2026-05-29")
        _check("2d Vormonat seeded:true + short_pct_float=None (ehrlich)",
               pts[0].get("seeded") is True and pts[0]["short_pct_float"] is None)
        _check("2e Vormonat shares_short = prior-Wert",
               pts[0]["shares_short"] == 92_500_000)
        _check("2f Punkt B = aktuell 2026-06-30 mit short_pct_float=20.1",
               pts[1]["settlement_date"] == "2026-06-30"
               and pts[1]["short_pct_float"] == 20.1
               and "seeded" not in pts[1])
        # non-US wird übersprungen
        added_de = gr._persist_si_position_history(
            [{"ticker": "FOO", "market": "DE",
              "yf_si_settlement_ts": _epoch("2026-06-30")}])
        data2 = json.load(open(gr.SI_POSITION_HISTORY_FILE))
        _check("2g non-US-Ticker übersprungen (yfinance-SI ist US-FINRA)",
               "FOO" not in data2 and added_de == 0)

    _with_temp_file(body)


def _test_dedup():
    print("── (3) Dedup auf settlement_date ─────────────────────────────")

    def body():
        gr._persist_si_position_history([_amc()])          # seed 2
        added2 = gr._persist_si_position_history([_amc()])  # gleiche settlement
        _check("3a gleiches settlement_date → 0 neue Punkte (Dedup)",
               added2 == 0, f"added2={added2}")
        # neues settlement → genau +1
        added3 = gr._persist_si_position_history(
            [_amc(yf_si_settlement_ts=_epoch("2026-07-31"),
                  yf_shares_short=80_000_000)])
        data = json.load(open(gr.SI_POSITION_HISTORY_FILE))
        _check("3b neues settlement_date → +1 Punkt", added3 == 1)
        _check("3c Serie hat jetzt 3 Punkte", len(data["AMC"]) == 3)
        # yf_si_settlement_ts None → kein Punkt, kein Crash (fail-soft)
        added_none = gr._persist_si_position_history(
            [_amc(ticker="ZZZ", yf_si_settlement_ts=None)])
        _check("3d settlement_ts None → kein Punkt (fail-soft)",
               added_none == 0)

    _with_temp_file(body)


def _test_pub_date():
    print("── (4) pub_date epoch→date→finra_publication_date (#408) ─────")
    # epoch→ISO
    _check("4a epoch(2026-06-30) → 2026-06-30 (UTC, tz-sauber)",
           gr._si_settlement_from_ts(_epoch("2026-06-30")) == "2026-06-30")
    _check("4b settlement_from_ts(None) → None (fail-soft)",
           gr._si_settlement_from_ts(None) is None)
    _check("4c settlement_from_ts('garbage') → None (fail-soft)",
           gr._si_settlement_from_ts("garbage") is None)
    # pub_date: Settlement 30.06.2026 + 7 Handelstage = 10.07.2026 (#408-Testfall)
    _check("4d pub_date(2026-06-30) == 2026-07-10 (Rule 4560, +7 Handelstage)",
           gr._si_pub_date("2026-06-30") == "2026-07-10",
           f"got {gr._si_pub_date('2026-06-30')}")
    _check("4e pub_date(2026-05-15) == 2026-05-27 (Memorial-Day-Woche)",
           gr._si_pub_date("2026-05-15") == "2026-05-27",
           f"got {gr._si_pub_date('2026-05-15')}")
    _check("4f pub_date(None) → None (fail-soft)",
           gr._si_pub_date(None) is None)
    # _make_si_point leitet pub_date automatisch ab
    p = gr._make_si_point("2026-06-30", 88_100_000, 20.1)
    _check("4g _make_si_point leitet pub_date ab",
           p["pub_date"] == "2026-07-10" and p["settlement_date"] == "2026-06-30")


def _test_retention():
    print("── (6) Retention 400d-Cutoff + Cap 24 (KEIN 14d-Prune) ───────")

    def body():
        # Sanity: Konstanten sind gesetzt und != 14 (kein score_history-Prune).
        _check("6a SI_POSITION_HISTORY_DAYS == 400 (kein 14d-Prune)",
               config.SI_POSITION_HISTORY_DAYS == 400)
        _check("6b Cap 24 Punkte/Ticker gesetzt",
               config.SI_POSITION_HISTORY_MAX_POINTS == 24)
        # 30 künstliche Punkte über > 400 Tage → Cutoff + Cap greifen.
        today = _dt.date.today()
        pts = []
        for i in range(30):
            d = (today - _dt.timedelta(days=i * 20)).isoformat()  # 20d-Schritte
            pts.append({"settlement_date": d, "shares_short": 1000 + i,
                        "short_pct_float": 10.0, "pub_date": d})
        gr._save_si_position_history({"AMC": pts})
        data = json.load(open(gr.SI_POSITION_HISTORY_FILE))
        kept = data["AMC"]
        # Cap: höchstens 24
        _check("6c Punkt-Cap greift (≤ 24)", len(kept) <= 24, f"n={len(kept)}")
        # Cutoff: kein Punkt älter als 400 Tage
        cutoff = today - _dt.timedelta(days=config.SI_POSITION_HISTORY_DAYS)
        oldest = min(_dt.date.fromisoformat(p["settlement_date"]) for p in kept)
        _check("6d kein Punkt älter als 400 Tage (Cutoff greift)",
               oldest >= cutoff, f"oldest={oldest} cutoff={cutoff}")
        # jüngste bleiben (settlement-aufsteigend sortiert, Cap nimmt Tail)
        newest = max(_dt.date.fromisoformat(p["settlement_date"]) for p in kept)
        _check("6e jüngster Punkt bleibt erhalten (Tail-Cap)",
               newest == today)
        _check("6f Reihenfolge settlement-aufsteigend",
               [p["settlement_date"] for p in kept]
               == sorted(p["settlement_date"] for p in kept))

    _with_temp_file(body)


# ── (5) LOOK-AHEAD-ISOLATION — Grep-Guard (analog entry_past_return_5d) ───────
def _test_look_ahead_isolation():
    print("── (5) Look-Ahead-Isolation (Grep-Guard) ─────────────────────")

    # Die Serien-Felder + Helper dürfen NIEMALS in Score-/Filter-/Push-Pfaden
    # GELESEN werden. Persistenz-Definition in generate_report.py ist erlaubt
    # (dort LEBT der Helper) — verboten sind Reads in ki_agent/health_check
    # sowie ein Aufruf des Helpers außerhalb der Persistenz-Kette.
    serien_reads = [
        'get("settlement_date")',    # nur im Persist-Helper erlaubt
    ]
    # In ki_agent.py + health_check.py dürfen die neuen Feldnamen NICHT
    # als Score-/Push-Feature auftauchen.
    for path_rel, tag in (
        ("ki_agent.py", "KI-Agent-/Push-Pfad"),
        ("health_check.py", "Health-Check-Pfad"),
    ):
        src = (ROOT / path_rel).read_text(encoding="utf-8")
        for pat in (
            '_persist_si_position_history(',
            'si_position_history',
            '"yf_si_settlement_ts"', "'yf_si_settlement_ts'",
        ):
            _check(
                f"5-{path_rel}: kein Vorkommen von {pat}",
                pat not in src,
                f"{tag} — Look-Ahead-Bruch: Serien-Feld/Helper im falschen Pfad",
            )

    # In generate_report.py: der Helper wird NUR in der Persistenz-Kette
    # aufgerufen (main() nach apply_score_smoothing) — nicht in score()/
    # _compute_sub_scores/score_bonus/apply_*. Zähl-Assertion: genau 1 Aufruf.
    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    n_calls = gr_src.count("_persist_si_position_history(enriched)")
    _check(
        "5-generate_report: _persist_si_position_history genau 1× aufgerufen",
        n_calls == 1,
        f"got {n_calls} — genau ein Aufruf in der Persistenz-Kette erwartet",
    )
    # Die Score-/Push-Kern-Funktionen lesen KEINES der Serien-Felder.
    # (Heuristik: die 4 yf_*-Feld-Reads dürfen NUR im Merge + Persist-Helper
    # sein — score()/_compute_sub_scores greifen sie nicht ab.)
    for score_fn in ("def score(", "def _compute_sub_scores(", "def score_bonus("):
        idx = gr_src.find(score_fn)
        if idx < 0:
            continue
        # Body grob bis zur nächsten Top-Level-def abschneiden.
        body = gr_src[idx: idx + 8000]
        _check(
            f"5-score-isolation: {score_fn.strip()} liest kein yf_si_*-Feld",
            "yf_si_settlement_ts" not in body
            and "yf_shares_short" not in body,
            "Score-Funktion greift Serien-Feld ab — Look-Ahead-/Selbstbelohnungs-Bruch",
        )

    # Docstring-Anker: Look-Ahead-Konvention einfroren.
    _check(
        "5-docstring: Look-Ahead-Konvention im Helper-Umfeld verankert",
        "LOOK-AHEAD-KONVENTION" in gr_src
        and "NIEMALS als Score-Feature" in gr_src,
        "Look-Ahead-Warnung im Persist-Helper-Docstring fehlt",
    )


def main() -> int:
    _test_merge_and_read_wiring()
    _test_seed_two_points()
    _test_dedup()
    _test_pub_date()
    _test_retention()
    _test_look_ahead_isolation()
    print()
    if _fails:
        print(f"✗ {len(_fails)} FAIL: {_fails}")
        return 1
    print("✓ alle SI-Positions-Zeitreihe-Tests grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
