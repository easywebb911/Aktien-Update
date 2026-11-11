"""Regressionstest: None-Guard in short_situation / risk_assessment / _card
(Bug-Fix 16.06.2026 — #795/#796 crashten beim HTML-Render mit
``TypeError: '>' not supported between instances of 'NoneType' and 'int'``).

Ursache: yfinance kann ein Feld als present-but-None liefern → ``.get(k, 0)``
schützt NICHT (Default greift nur bei fehlendem Key). ``short_situation``
(``chg > 5``), ``risk_assessment`` (``sf > 40`` / ``rv > 5``) und ``_card``
(``chg >= 0`` / ``_metric_color``) verglichen den None-Wert ungeschützt.

Fix-Konvention (fachlich):
  - sf/sr/rv (Pflicht-Werte/Farben, kein „unbekannt"-Display): ``or 0``.
  - chg in short_situation (OPTIONALE Bewegungs-Aussage): None = UNBEKANNT
    ≠ 0 % flach → ``is not None``-Guard, KEINE Bewegungs-Note (statt „+0 %").
  - chg in _card/_build_card_ctx (Pflicht-Tile): None→0 (flach), wie Cockpit/v2.

Schwellen (5 / -3 / 40 / 25 / 5) UNVERÄNDERT — None rutscht in KEINEN Zweig.

Kategorie A: stdlib + Heavy-Dep-Stubs (analog mock_test_outer_page_golden),
deterministisch, env-frei, CI-gate-bar.
"""
from __future__ import annotations

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_fails: list[str] = []


def _check(name, cond):
    if cond:
        print(f"  OK  {name}")
    else:
        _fails.append(name)
        print(f"  FAIL {name}")


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


def main() -> int:
    print("=== 1 — short_situation: present-but-None crasht NICHT mehr ===")
    # Der #795/#796-Trigger: change=None, sf/sr vorhanden.
    out = gr.short_situation({"change": None, "short_float": 35.0,
                              "short_ratio": 6.0, "rel_volume": 2.5})
    _check("01 change=None rendert (kein Crash)", isinstance(out, str) and out)
    _check("02 change=None → KEINE Bewegungs-Note (None≠0%)", "% heute" not in out)
    _check("03 change=None → Short-Float-Note bleibt", "Short Float" in out)
    # Alle vier None.
    out2 = gr.short_situation({"change": None, "short_float": None,
                               "short_ratio": None, "rel_volume": None})
    _check("04 alle None rendert (Fallback)", isinstance(out2, str) and out2)

    print("\n=== 2 — Schwellen UNVERÄNDERT (None rutscht in keinen Zweig) ===")
    _check("05 chg=7 → Bewegungs-Note feuert", "% heute" in
           gr.short_situation({"change": 7.0}))
    _check("06 chg=0 → keine Note (flach, nicht >5/<-3)", "% heute" not in
           gr.short_situation({"change": 0.0}))
    _check("07 chg=-5 → Note feuert", "heute" in
           gr.short_situation({"change": -5.0}))
    _check("08 chg=5 (Grenze, nicht >5) → keine Note", "% heute" not in
           gr.short_situation({"change": 5.0}))

    print("\n=== 3 — risk_assessment: sf/rv present-but-None crasht NICHT ===")
    lvl, col, _txt = gr.risk_assessment({"short_float": None, "rel_volume": None,
                                         "market_cap": None})
    _check("09 risk_assessment(None,None) rendert", isinstance(lvl, str) and lvl)
    # sf vorhanden, rv None (gemischt) — der reale Latenz-Fall.
    lvl2, _c, _t = gr.risk_assessment({"short_float": 45.0, "rel_volume": None,
                                       "market_cap": 5e8})
    _check("10 risk_assessment(sf=45,rv=None) rendert", isinstance(lvl2, str) and lvl2)

    print("\n=== 4 — _card (v1) + _build_card_ctx (v2): change=None render ===")
    s = {"ticker": "TST", "company_name": "T", "change": None, "price": 5.0,
         "score": 60, "short_float": 35.0, "short_ratio": 6.0, "rel_volume": 2.5,
         "conviction": {"score": 50, "level": "medium", "action_text": "A"},
         "finra_data": {"trend": "up", "history": []}, "options": {},
         "sparkline_view": None, "news": [], "float_shares": 5e7}
    try:
        v1 = gr._card(1, s)
        _check("11 _card(v1, change=None) rendert (kein Crash)", bool(v1))
    except Exception as exc:
        _check(f"11 _card(v1, change=None) — CRASH: {type(exc).__name__}", False)
    try:
        ctx = gr._build_card_ctx(1, s)
        _check("12 _build_card_ctx(v2, change=None) rendert", bool(ctx))
    except Exception as exc:
        _check(f"12 _build_card_ctx(v2) — CRASH: {type(exc).__name__}", False)

    # ── NaN-Guards Anzeige-Gruppe (open_items nan-bypass-baseline-70,
    # Gruppe 2, 02.11.2026): NaN verhält sich jetzt wie None/0 ──────────
    nan = float("nan")
    base = {"ticker": "NAN", "change": 0.0}
    r_none = gr.risk_assessment(dict(base, short_float=None, rel_volume=None))
    r_nan  = gr.risk_assessment(dict(base, short_float=nan, rel_volume=nan))
    _check("13 risk_assessment: NaN wie None", r_nan == r_none)
    t_none = gr.short_situation(dict(base, short_float=None, short_ratio=None, rel_volume=None))
    t_nan  = gr.short_situation(dict(base, short_float=nan, short_ratio=nan, rel_volume=nan))
    _check("14 short_situation: NaN wie None", t_nan == t_none)
    f_none = gr._float_display({"float_shares": None, "price": None, "market_cap": None})
    f_nan  = gr._float_display({"float_shares": nan, "price": nan, "market_cap": nan})
    _check("15 _float_display: NaN wie None", f_nan == f_none)
    f_fb = gr._float_display({"float_shares": None, "price": 10.0,
                              "yf_market_cap": nan, "market_cap": 2.5e8})
    f_ok = gr._float_display({"float_shares": None, "price": 10.0,
                              "market_cap": 2.5e8})
    _check("16 _float_display: NaN-yf_market_cap fällt auf market_cap zurück", f_fb == f_ok)
    _check("17 _float_turnover_row_html: NaN-Float → leer wie None",
           gr._float_turnover_row_html({"float_shares": nan, "cur_vol": 1e6})
           == gr._float_turnover_row_html({"float_shares": None, "cur_vol": 1e6}))

    # ── Teil 2: Karten (v1/v2) + Watchlist-Payload ───────────────────────
    _check("18 _finite_or_zero: int bleibt int", gr._finite_or_zero(5) == 5 and isinstance(gr._finite_or_zero(5), int))
    _check("19 _finite_or_zero: NaN/Inf/None/bool → 0",
           [gr._finite_or_zero(x) for x in (nan, float("inf"), None, True)] == [0, 0, 0, 0])
    sc = dict(s, short_float=nan, short_ratio=nan, rel_volume=nan, change=nan,
              float_shares=nan, **{"52w_high": nan, "52w_low": nan})
    sn = dict(s, short_float=None, short_ratio=None, rel_volume=None, change=None,
              float_shares=None, **{"52w_high": None, "52w_low": None})
    try:
        v1_nan, v1_none = gr._card(1, sc), gr._card(1, sn)
        _check("20 _card(v1): NaN rendert wie None", v1_nan == v1_none)
    except Exception as exc:
        _check(f"20 _card(v1) NaN — CRASH: {type(exc).__name__}: {exc}", False)
    try:
        c_nan, c_none = gr._build_card_ctx(1, sc), gr._build_card_ctx(1, sn)
        _check("22 _build_card_ctx(v2): NaN wie None", c_nan == c_none)
    except Exception as exc:
        _check(f"22 _build_card_ctx(v2) NaN — CRASH: {type(exc).__name__}: {exc}", False)

    try:
        w_nan, w_none = gr._wl_card_payload(dict(sc, yf_market_cap=nan, market_cap=3e8)), \
                        gr._wl_card_payload(dict(sn, yf_market_cap=None, market_cap=3e8))
        _check("23 _wl_card_payload: NaN-Felder wie None, market_cap-Fallback greift",
               all(w_nan.get(k) == w_none.get(k) for k in ("float_shares", "52w_high", "52w_low", "market_cap"))
               and w_nan.get("market_cap") == 3e8)
    except Exception as exc:
        _check(f"23 _wl_card_payload NaN — CRASH: {type(exc).__name__}: {exc}", False)

    # ── Teil 3: DRIVER_CLASSIFICATIONS (Float-Treiber), verhaltensneutral ──
    d_nan  = gr._drivers_breakdown(dict(s, float_shares=nan))
    d_none = gr._drivers_breakdown(dict(s, float_shares=None))
    d_fin  = gr._drivers_breakdown(dict(s, float_shares=2e7))
    _check("24 _drivers_breakdown: NaN-Float wie None", d_nan == d_none)
    _check("25 _drivers_breakdown: endlicher kleiner Float erzeugt Float-Treiber",
           any("Float klein" in it["label"] for it in d_fin["strengths"]))

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle None-Guard-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
