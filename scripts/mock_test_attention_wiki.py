"""Mock-Tests für attention_wiki (Wikipedia-Pageviews Attention-Feed, 24.07.2026).

Spec: docs/attention_wiki_spec.md. Fixtures aus den ECHTEN Probe-Responses
(PR #474, Run 30173587095) — reale QIDs/Titel, keine erfundenen Werte. Kein
Netzwerk (I/O injiziert).

Abgedeckt (Task 3):
  (a) VIA-Fixture → issuer_mismatch → substrate=none
  (b) Defunct-Fixture (P576) → REJECT → substrate=none
  (c) none ⇒ ALLE views/baseline/delta null, NIRGENDS 0 (harte Assertion)
  (d) en + Fetch-Fail ⇒ substrate bleibt en, views null, kein Crash
  (e) Baseline-Fenster endet T-2 (T-1 nicht in Baseline)
  (f) Nachtrag-Idempotenz (zweiter T+1-Lauf überschreibt views_t NICHT)
  (g) Look-Ahead-Konvention: attention_wiki wird von keinem Score-/Filter-/
      Push-Pfad gelesen (Grep-Test wie entry_past_return_5d)
  + positiver Pfad (AI→C3.ai en), S10-Disziplin (OBSERVED, nicht MUSS/LAG),
    Token-Fuzzy (VIA/Viacom-Prefix-Kollision), 0-ist-gültig.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import wiki_attention as wa  # noqa: E402

_spec = importlib.util.spec_from_file_location("config", ROOT / "config.py")
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)

_fails: list[str] = []


def _check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


# ── SPARQL-Fixtures (echte Probe-Werte, reale wikibase-JSON-Form) ────────────
def _sparql(qid=None, label="", art=None, dissolved=None):
    if qid is None:
        return {"results": {"bindings": []}}
    b = {"item": {"value": f"http://www.wikidata.org/entity/{qid}"},
         "itemLabel": {"value": label}}
    if art:
        b["art"] = {"value": f"https://en.wikipedia.org/wiki/{art}"}
    if dissolved:
        b["dissolved"] = {"value": dissolved}
    return {"results": {"bindings": [b]}}


_FIX_AI   = _sparql("Q104081972", "C3.ai", "C3.ai")                 # valid en
_FIX_WOLF = _sparql("Q5183828", "Wolfspeed", "Wolfspeed")          # valid en
# VIA real: Q214346 / Viacom_(2005–2019). Ticker heute = Via Renewables.
_FIX_VIA_MISMATCH = _sparql("Q214346", "Viacom", "Viacom_(2005–2019)")   # (a) kein dissolved
_FIX_VIA_DEFUNCT  = _sparql("Q214346", "Viacom", "Viacom_(2005–2019)",
                            dissolved="2019-12-04T00:00:00Z")             # (b) dissolved
_FIX_NO_P249 = _sparql()                                            # WRLD: leer
_FIX_NO_ART  = _sparql("Q92546757", "Biohaven", art=None)          # BHVN: QID ohne Artikel


def _pv(items):
    """items: list of (YYYYMMDD, views) → Pageviews-JSON in realer Form."""
    return {"items": [{"timestamp": d + "00", "views": v} for d, v in items]}


# ── Resolve-Tests ─────────────────────────────────────────────────────────────
def test_a_via_issuer_mismatch():
    r = wa.resolve_ticker("VIA", "Via Renewables, Inc.",
                          sparql_fetch=lambda t: _FIX_VIA_MISMATCH)
    _check("(a) VIA (nicht dissolved) → issuer_mismatch → substrate=none",
           r["substrate"] == "none" and r["reason"] == "issuer_mismatch"
           and r["issuer_verified"] is False,
           f"got {r}")


def test_b_defunct_reject():
    r = wa.resolve_ticker("VIA", "Via Renewables, Inc.",
                          sparql_fetch=lambda t: _FIX_VIA_DEFUNCT)
    _check("(b) Defunct (P576) → REJECT → substrate=none reason=defunct",
           r["substrate"] == "none" and r["reason"] == "defunct",
           f"got {r}")


def test_positive_en():
    r = wa.resolve_ticker("AI", "C3.ai, Inc.", sparql_fetch=lambda t: _FIX_AI)
    _check("positiv: AI → C3.ai → substrate=en, verified",
           r["substrate"] == "en" and r["title"] == "C3.ai"
           and r["qid"] == "Q104081972" and r["issuer_verified"] is True,
           f"got {r}")
    r2 = wa.resolve_ticker("WOLF", "Wolfspeed, Inc.", sparql_fetch=lambda t: _FIX_WOLF)
    _check("positiv: WOLF → Wolfspeed → substrate=en",
           r2["substrate"] == "en" and r2["title"] == "Wolfspeed", f"got {r2}")


def test_token_fuzzy_prefix_collision():
    # „Via Renewables" darf NICHT auf „Viacom" matchen (Token, nicht Substring).
    _check("Token-Fuzzy: 'Via Renewables' matcht NICHT 'Viacom' (Prefix-Kollision)",
           wa._issuer_matches("Via Renewables", "Viacom") is False)
    _check("Token-Fuzzy: 'C3.ai, Inc.' matcht 'C3.ai'",
           wa._issuer_matches("C3.ai, Inc.", "C3.ai") is True)
    _check("Token-Fuzzy: Rechtsform-Suffixe ignoriert (Hertz Global Holdings)",
           wa._issuer_matches("Hertz Global Holdings", "Hertz Global Holdings") is True)


def test_no_p249_and_no_article():
    r = wa.resolve_ticker("WRLD", "World Acceptance", sparql_fetch=lambda t: _FIX_NO_P249)
    _check("kein P249 → substrate=none reason=no_p249",
           r["substrate"] == "none" and r["reason"] == "no_p249", f"got {r}")
    r2 = wa.resolve_ticker("BHVN", "Biohaven Ltd.", sparql_fetch=lambda t: _FIX_NO_ART)
    _check("QID ohne Artikel → substrate=none reason=no_article (nicht nutzbar)",
           r2["substrate"] == "none" and r2["reason"] == "no_article", f"got {r2}")


def test_sparql_fetch_fail():
    r = wa.resolve_ticker("AI", "C3.ai", sparql_fetch=lambda t: None)
    _check("SPARQL-Fetch-Fail → substrate=none reason=sparql_fetch_failed (kein Crash)",
           r["substrate"] == "none" and r["reason"] == "sparql_fetch_failed", f"got {r}")


# ── Record-Bau-Tests ──────────────────────────────────────────────────────────
def test_c_none_all_null_never_zero():
    entry = {"substrate": "none", "qid": None, "title": None}
    rec = wa.build_attention_record(entry, date(2026, 7, 25))
    null_fields = ["views_t_minus_1", "views_t", "views_t_backfilled_at",
                   "baseline_30d_median", "baseline_30d_n", "delta_ratio"]
    all_null = all(rec[f] is None for f in null_fields)
    never_zero = all(rec[f] != 0 for f in null_fields)  # None != 0 → True; harte Trennung
    _check("(c) none ⇒ ALLE views/baseline/delta null",
           rec["substrate"] == "none" and all_null, f"got {rec}")
    _check("(c) none ⇒ NIRGENDS 0 (null ≠ 0, hart)",
           never_zero and all(rec[f] is None for f in null_fields), f"got {rec}")


def test_d_en_fetch_fail_stays_en():
    entry = {"substrate": "en", "qid": "Q104081972", "title": "C3.ai"}
    rec = wa.build_attention_record(entry, date(2026, 7, 25),
                                    pageviews_fetch=lambda t, s, e: None)
    _check("(d) en + Fetch-Fail ⇒ substrate bleibt en, views_t_minus_1 null, kein Crash",
           rec["substrate"] == "en" and rec["views_t_minus_1"] is None
           and rec["article_title"] == "C3.ai", f"got {rec}")


def test_e_baseline_ends_t_minus_2():
    # today=25. → T-1=24. Baseline muss T-2 (23.) und älter nutzen, NICHT T-1.
    today = date(2026, 7, 25)
    # 24. = T-1 (value 1000), 23..14 = 10 Baseline-Tage (value 100 je), plus 24. NICHT in Baseline
    items = [("20260724", 1000)] + [(f"202607{d:02d}", 100) for d in range(14, 24)]
    rec = wa.build_attention_record({"substrate": "en", "title": "C3.ai",
                                     "qid": "Q1"}, today,
                                    pageviews_fetch=lambda t, s, e: _pv(items))
    _check("(e) views_t_minus_1 = T-1-Wert (24. = 1000)",
           rec["views_t_minus_1"] == 1000, f"got {rec['views_t_minus_1']}")
    _check("(e) Baseline endet T-2: Median=100 (T-1=1000 NICHT in Baseline)",
           rec["baseline_30d_median"] == 100.0 and rec["baseline_30d_n"] == 10,
           f"got median={rec['baseline_30d_median']} n={rec['baseline_30d_n']}")
    _check("(e) delta_ratio = 1000/100 = 10.0 (abgeleitet)",
           rec["delta_ratio"] == 10.0, f"got {rec['delta_ratio']}")


def test_zero_is_valid_measured():
    # T-1 mit 0 Views ist ein GEMESSENER Wert (0), NICHT null.
    today = date(2026, 7, 25)
    items = [("20260724", 0)] + [(f"202607{d:02d}", 50) for d in range(14, 24)]
    rec = wa.build_attention_record({"substrate": "en", "title": "X", "qid": "Q1"},
                                    today, pageviews_fetch=lambda t, s, e: _pv(items))
    _check("0-Views-Tag ⇒ views_t_minus_1 == 0 (gemessen), NICHT null",
           rec["views_t_minus_1"] == 0 and rec["views_t_minus_1"] is not None,
           f"got {rec['views_t_minus_1']!r}")


def test_f_backfill_idempotent():
    rec = {"substrate": "en", "article_title": "C3.ai", "views_t": None,
           "views_t_backfilled_at": None}
    ed = date(2026, 7, 24)
    wrote1 = wa.backfill_views_t(rec, ed, pageviews_fetch=lambda t, s, e: _pv([("20260724", 777)]))
    _check("(f) erster Nachtrag setzt views_t=777",
           wrote1 is True and rec["views_t"] == 777, f"got {rec}")
    # zweiter Lauf mit ANDEREM Wert → darf NICHT überschreiben (idempotent).
    wrote2 = wa.backfill_views_t(rec, ed, pageviews_fetch=lambda t, s, e: _pv([("20260724", 999)]))
    _check("(f) zweiter Nachtrag überschreibt NICHT (idempotent, bleibt 777)",
           wrote2 is False and rec["views_t"] == 777, f"got {rec}")


def test_backfill_none_noop():
    rec = {"substrate": "none", "article_title": None, "views_t": None}
    wrote = wa.backfill_views_t(rec, date(2026, 7, 24),
                               pageviews_fetch=lambda t, s, e: _pv([("20260724", 5)]))
    _check("Nachtrag no-op bei substrate=none (views_t bleibt null)",
           wrote is False and rec["views_t"] is None, f"got {rec}")


# ── S10-Disziplin + Look-Ahead ────────────────────────────────────────────────
def test_s10_classification():
    _check("attention_wiki in S10_OBSERVED_FIELDS",
           "attention_wiki" in config.S10_OBSERVED_FIELDS)
    _check("attention_wiki NICHT in S10_MUSS_FIELDS",
           "attention_wiki" not in getattr(config, "S10_MUSS_FIELDS", {}))
    _check("attention_wiki NICHT in S10_LAG_FIELDS",
           "attention_wiki" not in getattr(config, "S10_LAG_FIELDS", {}))


def test_g_look_ahead_isolation():
    forbidden = ['get("attention_wiki")', '["attention_wiki"]', "['attention_wiki']"]
    for path_rel, tag in (("generate_report.py", "Live-Report-/Score-Pfad"),
                          ("ki_agent.py", "KI-Agent-/Push-Pfad"),
                          ("health_check.py", "Health-Check-Pfad")):
        src = (ROOT / path_rel).read_text(encoding="utf-8")
        _check(f"(g) {path_rel}: kein Read von attention_wiki aus dict",
               not any(p in src for p in forbidden),
               f"{tag} — Look-Ahead-Bruch: Score/Push liest Sammel-Feld")


def main():
    print("── attention_wiki ──────────────────────────────────────────────")
    for fn in (test_a_via_issuer_mismatch, test_b_defunct_reject, test_positive_en,
               test_token_fuzzy_prefix_collision, test_no_p249_and_no_article,
               test_sparql_fetch_fail, test_c_none_all_null_never_zero,
               test_d_en_fetch_fail_stays_en, test_e_baseline_ends_t_minus_2,
               test_zero_is_valid_measured, test_f_backfill_idempotent,
               test_backfill_none_noop, test_s10_classification,
               test_g_look_ahead_isolation):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            _fails.append(fn.__name__)
            print(f"  FAIL {fn.__name__}: {exc!r}")
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        sys.exit(1)
    print("✓ Alle Tests bestanden (Guard a/b, none-null-nie-0, Fetch-Fail, "
          "Baseline T-2, Nachtrag-Idempotenz, S10, Look-Ahead).")


if __name__ == "__main__":
    main()
