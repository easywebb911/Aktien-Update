"""Mock-Tests — LLM-Fallback-Flag ``ki_sentiment_source`` (16.07.2026).

ANLASS (ki_signal-Re-Test 15.07.): der Confound-Anker „LLM-Fallback-Mix" war
NICHT bestimmbar — ``backtest_history.json`` trug kein Per-Record-Flag, ob der
News-Anteil des ki_signal-Scores vom Claude-Haiku-Call oder vom Keyword-Fallback
stammt. Dieses Feld macht die Sample-Heterogenität beim nächsten Re-Test messbar.

Feld ``ki_sentiment_source`` ∈ {"llm", "keyword", "none"} (None auf Alt-Records,
forward-only). Kette:
  ki_agent.compute_signal (Klassifikation @ claude_sentiment_score-Call)
    → meta["ki_sentiment_source"]
    → signal-Dict (agent_signals.json)
    → generate_report.apply_agent_boost setzt s["ki_sentiment_source"]
    → backtest_history._build_backtest_extension liest s.get(...)
    → entry.update(ext)  ← DER #411-Merge (Durchreichung MUSS asserted sein)

Verifiziert (fixture-/source-only, CI-minimal-safe via yfinance-Stub, §8u):
- (A) S10: in OBSERVED, NICHT MUSS/LAG; Schema bleibt v4.
- (B) Source: Feld im _build_backtest_extension-Return; ki_agent-Klassifikator +
      meta- + signal-Dict-Wiring; apply_agent_boost setzt s[...] aus sig.
- (C) Drei-Zustands-Klassifikation (Wahrheitstabelle, Mirror + Anti-Drift-Grep).
- (D) MERGE-ASSERTION (#411): stock[ki_sentiment_source]=X → ext trägt X, alle 3.
- (E) Alt-Record ohne Feld → ext-Wert None, kein Crash.
- (F) Additiv: kein Score-/Filter-Read des Flags (Look-Ahead-Konvention).

Ausführung: ``python3 scripts/mock_test_ki_sentiment_source.py``.
"""
from __future__ import annotations

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Drittlib-Stubs (im GH-Actions-Env via requirements.txt vorhanden).
# backtest_history importiert yfinance top-level (§8u).
for _mod_name in ("yfinance", "bs4", "deep_translator", "lxml", "pandas"):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)
sys.modules["yfinance"].download = lambda *a, **kw: None
sys.modules["yfinance"].Ticker = lambda *a, **kw: None
sys.modules["bs4"].BeautifulSoup = lambda *a, **kw: None
sys.modules["deep_translator"].GoogleTranslator = lambda *a, **kw: type(
    "T", (), {"translate": staticmethod(lambda s: s)}
)()

import backtest_history as bh   # noqa: E402

_fails: list[str] = []


def _check(name, cond, detail=""):
    print(("  OK  " if cond else "  FAIL ") + name + (
        "" if cond or not detail else f" — {detail}"))
    if not cond:
        _fails.append(name)


_KI = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
_GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
_BH = (ROOT / "backtest_history.py").read_text(encoding="utf-8")


# ── (A) S10 + Schema ──────────────────────────────────────────────────────
def test_a_s10_and_schema():
    print("── (A) S10-Klassifikation + Schema v4 ────────────────────────")
    import config
    _check("A1 in S10_OBSERVED_FIELDS",
           "ki_sentiment_source" in config.S10_OBSERVED_FIELDS)
    _check("A2 NICHT in S10_MUSS_FIELDS (legitim None auf Alt-Records)",
           "ki_sentiment_source" not in config.S10_MUSS_FIELDS)
    _check("A3 NICHT in S10_LAG_FIELDS (kein LAG-Outcome)",
           "ki_sentiment_source" not in config.S10_LAG_FIELDS)
    _check("A4 Schema bleibt v4 (kein Bump)",
           '"backtest_schema_version": 4,' in _BH
           and '"backtest_schema_version": 5' not in _BH)


# ── (B) Source-Wiring der gesamten Kette ──────────────────────────────────
def test_b_source_wiring():
    print("── (B) Source-Wiring (Kette vollständig) ─────────────────────")
    _check("B1 _build_backtest_extension schreibt das Feld",
           '"ki_sentiment_source":     s.get("ki_sentiment_source")' in _BH,
           "Feld fehlt im Extension-Return → käme nie im Record an")
    _check("B2 ki_agent: Klassifikator vorhanden",
           "_ki_sentiment_source = (" in _KI)
    _check("B3 ki_agent: meta trägt das Feld",
           '"ki_sentiment_source": _ki_sentiment_source' in _KI)
    _check("B4 ki_agent: signal-Dict schreibt es (agent_signals.json)",
           '"ki_sentiment_source": _meta.get("ki_sentiment_source")' in _KI)
    _check("B5 apply_agent_boost setzt s[...] aus sig",
           's["ki_sentiment_source"] = _kss' in _GR
           and '_kss = sig.get("ki_sentiment_source")' in _GR)


# ── (C) Drei-Zustands-Klassifikation (Wahrheitstabelle + Anti-Drift) ──────
def _classify(ai_score, news):
    """Exakter Mirror der ki_agent.compute_signal-Logik (Doku der Absicht)."""
    return ("llm" if ai_score is not None
            else "keyword" if any(h for h in (news or []))
            else "none")


def test_c_classification():
    print("── (C) Drei-Zustands-Klassifikation ──────────────────────────")
    _check("C1 LLM-Erfolg (score gesetzt) → 'llm'",
           _classify(72, ["headline"]) == "llm")
    _check("C2 Fallback (score None, Headlines da) → 'keyword'",
           _classify(None, ["frische news"]) == "keyword")
    _check("C3 kein Call (score None, keine Headlines) → 'none'",
           _classify(None, []) == "none")
    _check("C4 leere Headline-Strings → 'none' (kein Keyword-Input)",
           _classify(None, ["", ""]) == "none")
    _check("C5 LLM-Score 0 ist gültig (not None) → 'llm'",
           _classify(0, ["x"]) == "llm")
    # Anti-Drift: der exakte Prädikat-Ausdruck steht im ki_agent-Source,
    # damit der Test-Mirror nicht still von der Implementierung abweicht.
    _check("C6 Anti-Drift: exaktes Prädikat im ki_agent-Source",
           'else "keyword" if any(h for h in (news or []))' in _KI
           and 'else "none"' in _KI)


# ── (D)/(E) Merge-Durchreichung (#411) + Alt-Record-Toleranz ──────────────
def _baseline_stock():
    return {
        "ticker": "TEST", "score": 70.0, "score_raw": 68.0, "price": 10.0,
        "short_float": 25.0, "short_ratio": 5.0, "rel_volume": 2.4,
        "rel_volume_yesterday": 1.5, "change": 2.5, "float_shares": 1e8,
        "avg_vol_20d": 1e6, "hist_5d": [],
        "score_trend_bonus_pts": 0.0, "agent_boost_factor": 1.0,
        "finra_bonus_pts": 0.0, "short_float_source": "yfinance",
        "finra_data": {"trend": "no_data", "history": [],
                       "si_trend_source": "finra"},
        "sparkline": None,
    }


def _build(stock):
    return bh._build_backtest_extension(
        stock, pool_position=1, pool_size=20, agent_signals={},
        compute_sub_scores_fn=lambda s: {"struct": 0, "catalyst": 0, "timing": 0},
        safe_float_fn=lambda v, d=0.0: float(v) if v not in (None, "") else d,
        latest_push_ts_by_ticker=None,
        now_dt=None,
    )


def test_d_merge_durchreichung():
    print("── (D) MERGE-Durchreichung #411 (alle 3 Zustände) ────────────")
    for src_val in ("llm", "keyword", "none"):
        st = _baseline_stock()
        st["ki_sentiment_source"] = src_val   # so wie apply_agent_boost es setzt
        ext = _build(st)
        _check(f"D:{src_val} kommt im Extension-Record an",
               ext.get("ki_sentiment_source") == src_val,
               f"got {ext.get('ki_sentiment_source')!r}")
    # entry.update(ext) ist ein trivialer Dict-Merge → wenn ext das Feld trägt,
    # landet es im Record. Das explizit demonstrieren:
    st = _baseline_stock(); st["ki_sentiment_source"] = "llm"
    entry = {"date": "16.07.2026", "ticker": "TEST"}
    entry.update(_build(st))
    _check("D:entry.update trägt das Feld in den finalen Record",
           entry.get("ki_sentiment_source") == "llm")


def test_e_alt_record_tolerance():
    print("── (E) Alt-Record ohne Feld → None, kein Crash ───────────────")
    st = _baseline_stock()          # KEIN ki_sentiment_source gesetzt
    ext = _build(st)
    _check("E1 fehlendes Feld → ext-Wert None (leer-tolerant)",
           ext.get("ki_sentiment_source") is None)
    # Auswertungs-Seite: Alt-Record-Dict ohne das Feld → .get() = None
    alt_record = {"ticker": "OLD", "return_10d": 12.3}
    _check("E2 Alt-Record .get() = None (Auswertung filtert sauber)",
           alt_record.get("ki_sentiment_source") is None)


# ── (F) Additiv: kein Score-/Filter-Read des Flags ────────────────────────
def test_f_no_score_read():
    print("── (F) Additiv — kein Score-/Filter-Read (Look-Ahead) ────────")
    # Das Flag darf NUR persistiert (geschrieben) werden, nie in einer Score-/
    # Filter-Entscheidung GELESEN werden. Heuristik: kein Gleichheits-/Branch-
    # Vergleich gegen die Werte in generate_report/ki_agent.
    for src, name in ((_GR, "generate_report"), (_KI, "ki_agent")):
        bad = ('ki_sentiment_source ==' in src
               or 'ki_sentiment_source"] ==' in src
               or "ki_sentiment_source') ==" in src)
        _check(f"F:{name} kein Gleichheits-Branch auf dem Flag (kein Score-Read)",
               not bad)


def main() -> int:
    for fn in (test_a_s10_and_schema, test_b_source_wiring, test_c_classification,
               test_d_merge_durchreichung, test_e_alt_record_tolerance,
               test_f_no_score_read):
        fn()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (ki_sentiment_source: S10 + Kette + 3 Zustände "
          "+ #411-Merge + Alt-Record-Toleranz + kein Score-Read).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
