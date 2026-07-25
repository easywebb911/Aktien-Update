"""Mock-Tests für das ``source_pools``-Sammelfeld (Kandidaten-Herkunft, 25.07.2026).

FIXTURE-ONLY / netzwerkfrei — kein echter Screener-Call, keine
``backtest_history.json``.

Beweist die Kern-Invarianten:
- (A) Yahoo-Collector taggt GRANULAR (yahoo_<screener_id>, nicht kollabiert)
      und MERGT bei Multi-Membership (ein Ticker in 2 Screenern → beide Pools),
      während der grobe ``source``-String (ranking-relevant) first-win bleibt.
- (B) Finviz-v111-Collector taggt ["finviz_v111"].
- (C) Finviz-v141-Fallback taggt ["finviz_v141"] UND feuert nur bei Yahoo=0
      (Source-Inspektion des ``if not candidates:``-Gates).
- (D) Record-Builder schreibt sorted(set(...)) → deterministisch + dedupliziert;
      fehlender Key → [] (Alt-Record-tolerant); Multi-Membership erhalten.
- (E) main()-Dedupe MERGT statt first-win (v111- + Manual-Merge, Source-Inspektion).
- (F) Look-Ahead-Isolation: KEIN Read von source_pools in Score-/Filter-/Push-
      Funktionen (generate_report Score-Funcs) noch in ki_agent.py/health_check.py.
- (G) Vokabular-Geschlossenheit: alle vergebenen Tags stehen im config-Enum.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

GR_TEXT = (ROOT / "generate_report.py").read_text(encoding="utf-8")
BH_TEXT = (ROOT / "backtest_history.py").read_text(encoding="utf-8")


def _try_backtest_history():
    """Lazy-Import: backtest_history importiert yfinance top-level → im
    Minimal-CI-Slot (stdlib+jinja2+pyyaml, kein yfinance) NICHT verfügbar.
    Dann laufen die funktionalen D-Tests nicht, die Source-Inspektion (D0)
    verankert das Record-Wiring trotzdem deterministisch (analog
    mock_test_max_gain_pct)."""
    try:
        import backtest_history as B  # noqa
        return B
    except Exception:
        return None

_fails: list[str] = []


def _check(name, cond, msg=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {msg}")
        _fails.append(name)


def _extract(src: str, name: str) -> str:
    pat = re.compile(rf"^def {re.escape(name)}\(.*?(?=^def |^class |\Z)",
                     re.MULTILINE | re.DOTALL)
    m = pat.search(src)
    assert m, f"{name} nicht im Source gefunden"
    return m.group(0)


# ── (A) Yahoo-Collector: granular + Multi-Membership-Merge ───────────────────

def _load_yahoo_collector():
    """Extrahiere get_yahoo_screener_candidates und exec mit gestubbten Deps.

    Der Stub ``_fetch_yf_screener`` liefert Fixture-Quotes pro Screener:
      - most_shorted_stocks → DUAL, SOLO_MS
      - small_cap_gainers   → DUAL, SOLO_SCG
    DUAL steckt in BEIDEN → Merge-Beweis.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    quotes_by_sid = {
        "most_shorted_stocks": [
            {"symbol": "DUAL", "regularMarketPrice": 5.0, "marketCap": 1e8,
             "shortPercentOfFloat": 0.4, "shortRatio": 6.0, "shortName": "Dual Co"},
            {"symbol": "SOLOMS", "regularMarketPrice": 8.0, "marketCap": 2e8,
             "shortPercentOfFloat": 0.3, "shortRatio": 5.0, "shortName": "Solo MS"},
        ],
        "small_cap_gainers": [
            {"symbol": "DUAL", "regularMarketPrice": 5.0, "marketCap": 1e8,
             "shortPercentOfFloat": 0.4, "shortRatio": 6.0, "shortName": "Dual Co"},
            {"symbol": "SOLOSCG", "regularMarketPrice": 9.0, "marketCap": 3e8,
             "shortPercentOfFloat": 0.2, "shortRatio": 4.0, "shortName": "Solo SCG"},
        ],
    }

    class _Log:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def debug(self, *a, **k): pass

    ns = {
        "re": re, "time": __import__("time"), "float": float, "len": len,
        "set": set, "log": _Log(),
        "ThreadPoolExecutor": ThreadPoolExecutor, "as_completed": as_completed,
        "print": lambda *a, **k: None,
        "MIN_PRICE": 1.0, "MAX_MARKET_CAP": 1e12,
        "INTL_SCREENING_ENABLED": False,
        "_YF_SCREENERS": {"US": ["most_shorted_stocks", "small_cap_gainers"]},
        "SOURCE_POOL_YAHOO_PREFIX": config.SOURCE_POOL_YAHOO_PREFIX,
        "fmt_cap": lambda x: "",
        "strip_surrogates": lambda x: x,
        "_fetch_yf_screener": lambda sid, region="US", count=100: quotes_by_sid.get(sid, []),
    }
    exec(_extract(GR_TEXT, "get_yahoo_screener_candidates"), ns)
    return ns["get_yahoo_screener_candidates"]


def test_yahoo_multi_membership_merge():
    collector = _load_yahoo_collector()
    cands = {c["ticker"]: c for c in collector()}
    _check("A1 DUAL in beiden Screenern erfasst", "DUAL" in cands)
    dual_pools = sorted(cands["DUAL"]["source_pools"])
    _check("A2 DUAL trägt BEIDE granularen Pools (Merge, nicht first-win)",
           dual_pools == ["yahoo_most_shorted_stocks", "yahoo_small_cap_gainers"],
           dual_pools)
    _check("A3 SOLOMS single-membership → nur most_shorted",
           cands.get("SOLOMS", {}).get("source_pools") == ["yahoo_most_shorted_stocks"],
           cands.get("SOLOMS", {}).get("source_pools"))
    _check("A4 SOLOSCG single-membership → nur small_cap_gainers",
           cands.get("SOLOSCG", {}).get("source_pools") == ["yahoo_small_cap_gainers"],
           cands.get("SOLOSCG", {}).get("source_pools"))
    # grober `source` bleibt kollabiert + ranking-relevant (UNBERÜHRT):
    _check("A5 grober source=DUAL kollabiert (first-win), NICHT granular",
           cands["DUAL"]["source"] in ("yahoo_most_shorted", "yahoo_screener"),
           cands["DUAL"].get("source"))
    _check("A6 SOLOMS grober source==yahoo_most_shorted (Tier-2-Ranking intakt)",
           cands["SOLOMS"]["source"] == "yahoo_most_shorted",
           cands["SOLOMS"].get("source"))


# ── (B) Finviz-v111-Collector ────────────────────────────────────────────────

def _load_v111_collector():
    html = ('x quote?t=DUAL" y quote?t=FVONLY" z quote?t=DUAL"')

    class _Resp:
        status_code = 200
        text = html

    class _Requests:
        @staticmethod
        def get(*a, **k):
            return _Resp()

    ns = {
        "re": re, "print": lambda *a, **k: None, "len": len,
        "FINVIZ_SCREENER_ENABLED": True, "FINVIZ_MAX_TICKERS": 50,
        "SOURCE_POOL_FINVIZ_V111": config.SOURCE_POOL_FINVIZ_V111,
        "requests": _Requests(), "HTTP_HEADERS": {},
    }
    exec(_extract(GR_TEXT, "get_finviz_screener_v111"), ns)
    return ns["get_finviz_screener_v111"]


def test_v111_tag():
    collector = _load_v111_collector()
    out = collector()
    tickers = {c["ticker"]: c for c in out}
    _check("B1 v111 liefert deduplizierte Ticker", set(tickers) == {"DUAL", "FVONLY"})
    _check("B2 v111-Candidate trägt source_pools=['finviz_v111']",
           all(c["source_pools"] == ["finviz_v111"] for c in out),
           [c["source_pools"] for c in out])
    _check("B3 v111 grober source unverändert 'finviz_screener_v111'",
           all(c["source"] == "finviz_screener_v111" for c in out))


# ── (C) Finviz-v141-Fallback (Source-Inspektion: Tag + Yahoo=0-Gate) ─────────

def test_v141_fallback():
    v141_body = _extract(GR_TEXT, "get_finviz_candidates")
    _check("C1 v141-Fallback taggt source_pools=[SOURCE_POOL_FINVIZ_V141]",
           '"source_pools": [SOURCE_POOL_FINVIZ_V141]' in v141_body)
    # Fragil-Punkt (EXZELLENZ 6): v141 feuert NUR wenn Yahoo=0 — Gate belegen.
    _check("C2 v141-Aufruf durch 'if not candidates:'-Gate geschützt",
           re.search(r"if not candidates:\s*\n(?:.*\n)*?\s*candidates = get_finviz_candidates\(",
                     GR_TEXT) is not None)


# ── (D) Record-Builder: sorted+dedup, Alt-Record-tolerant ────────────────────

def test_record_builder():
    # D0 — Source-Inspektion (stdlib-only, läuft AUCH im Minimal-CI-Slot):
    # das Record-Wiring schreibt sorted(set(...)) → deterministisch + dedup.
    _check("D0 _build_backtest_extension wired sorted(set(s.get('source_pools')...))",
           'sorted(set(s.get("source_pools") or []))' in BH_TEXT)

    B = _try_backtest_history()
    if B is None:
        _check("D-SKIP funktionale Record-Tests (kein yfinance im CI-Slot)", True)
        return

    def _rec(s):
        return B._build_backtest_extension(
            s, 0, 30, {}, compute_sub_scores_fn=lambda x: None,
            safe_float_fn=lambda x: float(x or 0))

    r = _rec({"ticker": "AI", "short_float": None,
              "source_pools": ["yahoo_day_gainers", "manual", "yahoo_day_gainers"]})
    _check("D1 Record schreibt sorted(set(...)) (dedup + deterministisch)",
           r["source_pools"] == ["manual", "yahoo_day_gainers"], r["source_pools"])
    r2 = _rec({"ticker": "ZZ", "short_float": None})   # KEIN Feld
    _check("D2 Alt-Record ohne Feld → [] (kein Crash)", r2["source_pools"] == [])
    r3 = _rec({"ticker": "MM", "short_float": None,
               "source_pools": ["yahoo_most_shorted_stocks", "finviz_v111"]})
    _check("D3 Multi-Membership erhalten (sortiert)",
           r3["source_pools"] == ["finviz_v111", "yahoo_most_shorted_stocks"],
           r3["source_pools"])
    _check("D4 Schema bleibt v4 (additiv, kein Bump)",
           r["backtest_schema_version"] == 4)
    # Determinismus: gleiche Eingabe in anderer Reihenfolge → gleiche Ausgabe
    ra = _rec({"ticker": "A", "short_float": None,
               "source_pools": ["manual", "finviz_v141", "yahoo_day_gainers"]})
    rb = _rec({"ticker": "B", "short_float": None,
               "source_pools": ["yahoo_day_gainers", "manual", "finviz_v141"]})
    _check("D5 permutierte Eingabe → identische sortierte Ausgabe",
           ra["source_pools"] == rb["source_pools"], (ra["source_pools"], rb["source_pools"]))


# ── (E) main()-Dedupe MERGT (v111 + Manual), nicht first-win ─────────────────

def test_main_dedupe_merges():
    # v111-Merge: else-Zweig mit Pool-Merge statt reinem first-win-Drop.
    _check("E1 v111-Merge: _by_tkr-Map angelegt",
           '_by_tkr  = {c["ticker"]: c for c in candidates}' in GR_TEXT
           or '_by_tkr = {c["ticker"]: c for c in candidates}' in GR_TEXT)
    _check("E2 v111-Merge: else-Zweig hängt fremde Pools an",
           re.search(r"for _p in fv\.get\(\"source_pools\", \[\]\):\s*\n\s*if _p not in _ex\[\"source_pools\"\]",
                     GR_TEXT) is not None)
    # Manual-Merge: existierender Kandidat bekommt 'manual' ADDITIV (nicht überschrieben).
    _check("E3 Manual-Merge: existierender Kandidat → SOURCE_POOL_MANUAL additiv",
           re.search(r'c\.setdefault\("source_pools", \[\]\)\s*\n\s*if SOURCE_POOL_MANUAL not in c\["source_pools"\]',
                     GR_TEXT) is not None)
    _check("E4 Manual-Neu-Kandidat taggt ['manual']",
           '"source_pools":   [SOURCE_POOL_MANUAL]' in GR_TEXT)


# ── (F) Look-Ahead-Isolation ─────────────────────────────────────────────────

# Score-/Filter-/Push-Funktionen (dieselbe Liste wie lint_score_confidence_isolation)
_SCORE_FUNCS = (
    "compute_conviction_score", "apply_conviction_scores", "compute_earliness_pts",
    "_earliness_pts_v1", "_earliness_pts_v2", "score", "score_bonus",
    "apply_monster_score", "apply_agent_boost", "apply_late_runner_penalty",
    "apply_score_smoothing", "_compute_sub_scores", "_drivers_breakdown",
    "compute_exit_score", "process_exit_signals",
)


def test_look_ahead_isolation():
    for fn in _SCORE_FUNCS:
        try:
            body = _extract(GR_TEXT, fn)
        except AssertionError:
            _check(f"F-{fn}: Funktion gefunden", False, "nicht im Source")
            continue
        _check(f"F-{fn}: liest source_pools NICHT",
               "source_pools" not in body,
               "Look-Ahead-Bruch: Score-Funktion liest Herkunfts-Feld")
    # ki_agent.py + health_check.py: das Feld hat dort NICHTS verloren (Push/Health).
    for path_rel in ("ki_agent.py", "health_check.py"):
        src = (ROOT / path_rel).read_text(encoding="utf-8")
        forbidden = ['get("source_pools")', "['source_pools']", '["source_pools"]']
        _check(f"F-{path_rel}: kein source_pools-Read",
               not any(p in src for p in forbidden),
               "Look-Ahead-Bruch: Push/Health liest Herkunfts-Feld")


# ── (G) Vokabular-Geschlossenheit ────────────────────────────────────────────

def test_vocabulary_closed():
    vocab = config.SOURCE_POOL_VOCABULARY
    _check("G1 'manual' im Vokabular", config.SOURCE_POOL_MANUAL in vocab)
    _check("G2 finviz_v141/v111 im Vokabular",
           {config.SOURCE_POOL_FINVIZ_V141, config.SOURCE_POOL_FINVIZ_V111} <= vocab)
    # Jeder real vergebene Yahoo-Screener-Tag muss im Vokabular stehen.
    real_screeners = (["most_shorted_stocks", "small_cap_gainers",
                       "aggressive_small_caps"] + list(config.EXTRA_SCREENERS))
    for sid in real_screeners:
        tag = config.SOURCE_POOL_YAHOO_PREFIX + sid
        _check(f"G3 Vokabular deckt {tag}", tag in vocab)
    _check("G4 source_pools in S10_OBSERVED_FIELDS registriert",
           "source_pools" in config.S10_OBSERVED_FIELDS)


def main():
    print("── (A) Yahoo Multi-Membership-Merge ──────────────────────────")
    test_yahoo_multi_membership_merge()
    print("── (B) Finviz v111 Tag ───────────────────────────────────────")
    test_v111_tag()
    print("── (C) Finviz v141-Fallback (Gate + Tag) ─────────────────────")
    test_v141_fallback()
    print("── (D) Record-Builder (sorted/dedup/tolerant) ────────────────")
    test_record_builder()
    print("── (E) main()-Dedupe MERGT ───────────────────────────────────")
    test_main_dedupe_merges()
    print("── (F) Look-Ahead-Isolation ──────────────────────────────────")
    test_look_ahead_isolation()
    print("── (G) Vokabular-Geschlossenheit ─────────────────────────────")
    test_vocabulary_closed()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (source_pools: granular, Multi-Membership-"
          "Merge, sorted/dedup-Record, main-Merge, Look-Ahead-frei, Vokabular).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
