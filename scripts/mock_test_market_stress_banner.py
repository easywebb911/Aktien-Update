"""Mock-Tests für den Markt-Stress-Banner (§6h, Anzeige-only, 08.08.2026).

Dezenter Header-Hinweis neben der Staleness-/Run-Phase-Pill, wenn der heutige
S&P-500-Tagesmove schwach oder panisch ist. Zwei Stufen (Schwellen in config):
  ≤ MARKET_STRESS_STRONG_PCT (−3 %) → rot,  „besonderer Vorsicht"
  ≤ MARKET_STRESS_MILD_PCT   (−2 %) → gelb, „vorsichtig"
  sonst / null / nicht-endlich      → versteckt (fail-soft, kein Falsch-Alarm)

ENTSCHEIDUNG (Easy, §6h-Diagnose 08.08.): reines ANZEIGE-Banner — KEIN Filter,
KEIN Push-Gate, KEINE Score-Änderung. Ein Panik-Tag ist der Moment zum Hinsehen,
NICHT zum Auto-Unterdrücken (harter Filter würde echte Panik-Squeezes töten).

Quelle ist der BEREITS gefetchte ^GSPC-Tagesmove (``spx_daily_perf``, aus der
20T-Relativstärke-Historie) — KEINE neue Datenquelle, kein neuer Fetch.

Zwei Test-Ebenen:
  1  ZIEL-MECHANIK durch den ECHTEN Render-Pfad (``generate_html_v1``): ein
     injizierter ``spx_daily_perf`` landet als JS-Const ``_SPX_DAILY_PERF``;
     −3 % erscheint wirklich, fehlend/NaN → ``null`` (fail-soft belegt).
  2  Klassifikations-Spiegel (Python-Mirror der JS-Schwellen, drift-resistent:
     liest die config-Konstanten zur Laufzeit) + Wiring/Isolation per Source.

Kategorie A: stdlib + jinja2, deterministisch, env-frei (Golden-Stub-Reuse).
"""
from __future__ import annotations

import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from config import MARKET_STRESS_MILD_PCT, MARKET_STRESS_STRONG_PCT  # noqa: E402
# Import zieht _install_stubs() + `import generate_report as gr` (Modul-Ebene).
from mock_test_outer_page_golden import _fixture_stock, gr  # noqa: E402

SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
HEAD = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def _render(spx, *, drop_key=False):
    """Rendert die Outer-Page über den Produktions-Renderer mit gesetztem
    (oder entferntem) ``spx_daily_perf`` auf allen Top-10-Dicts."""
    stocks = [_fixture_stock(f"T{i}", score=80.0 - i, price=5.0, change=2.0)
              for i in range(10)]
    for s in stocks:
        if drop_key:
            s.pop("spx_daily_perf", None)
        else:
            s["spx_daily_perf"] = spx
    return gr.generate_html_v1(stocks, "08.08.2026")


def _injected_const(html):
    m = re.search(r"const _SPX_DAILY_PERF\s*=\s*([^;]+);", html)
    return m.group(1).strip() if m else None


def classify(v, mild, strong):
    """Python-Spiegel der JS-Logik in _renderMarketStress (gleiche Grenzen):
    ``v null/nicht-endlich → hidden; v > MILD → hidden; v ≤ STRONG → strong;
    sonst → mild``. STRONG/MILD sind negativ (−3 / −2)."""
    if v is None or not isinstance(v, (int, float)) or not math.isfinite(v):
        return "hidden"
    if v > mild:
        return "hidden"
    if v <= strong:
        return "strong"
    return "mild"


def main() -> int:
    MILD, STRONG = MARKET_STRESS_MILD_PCT, MARKET_STRESS_STRONG_PCT

    print("=== Schwellen-Kalibrierung ===")
    _check("00 STRONG = −3.0 (Panik-Schwelle aus §6h-Diagnose)", STRONG == -3.0)
    _check("01 MILD = −2.0 (mildere Schwäche-Stufe)", MILD == -2.0)
    _check("02 STRONG < MILD < 0 (Stufen konsistent, beide negativ)",
           STRONG < MILD < 0)

    print("\n=== ZIEL-MECHANIK: Banner erscheint bei −3 % (echter Render-Pfad) ===")
    _check("03 spx=−3.5 → JS-Const _SPX_DAILY_PERF = -3.5",
           _injected_const(_render(-3.5)) == "-3.5")
    _check("04 spx=−2.4 → JS-Const = -2.4 (milde Stufe)",
           _injected_const(_render(-2.4)) == "-2.4")
    _check("05 spx=−1.0 → JS-Const = -1.0 (kein Banner, aber Wert da)",
           _injected_const(_render(-1.0)) == "-1.0")
    _check("06 spx=0.0 → JS-Const = 0.0 (Normalfall, Banner versteckt)",
           _injected_const(_render(0.0)) == "0.0")

    print("\n=== FAIL-SOFT: SPY fehlt / None / NaN / ±Inf → null → kein Banner ===")
    _check("07 spx-Key fehlt → _SPX_DAILY_PERF = null",
           _injected_const(_render(None, drop_key=True)) == "null")
    _check("08 spx=NaN → null (nicht 'nan', nicht Crash)",
           _injected_const(_render(float("nan"))) == "null")
    _check("09 spx=+Inf → null", _injected_const(_render(float("inf"))) == "null")
    _check("10 spx=−Inf → null", _injected_const(_render(float("-inf"))) == "null")
    # bool ist int-Subklasse — darf NICHT als Move durchrutschen
    _check("11 spx=True (bool) → null (kein versehentlicher 1.0-Move)",
           _injected_const(_render(True)) == "null")

    print("\n=== Klassifikation (Python-Spiegel der JS-Schwellen) ===")
    _check("12 −3.5 → strong (rot)",      classify(-3.5, MILD, STRONG) == "strong")
    _check("13 exakt −3.0 → strong",      classify(-3.0, MILD, STRONG) == "strong")
    _check("14 −2.5 → mild (gelb)",       classify(-2.5, MILD, STRONG) == "mild")
    _check("15 exakt −2.0 → mild",        classify(-2.0, MILD, STRONG) == "mild")
    _check("16 −1.99 → hidden",           classify(-1.99, MILD, STRONG) == "hidden")
    _check("17 0.0 → hidden",             classify(0.0, MILD, STRONG) == "hidden")
    _check("18 +1.0 (Markt grün) → hidden", classify(1.0, MILD, STRONG) == "hidden")
    _check("19 None → hidden",            classify(None, MILD, STRONG) == "hidden")
    _check("20 NaN → hidden",             classify(float("nan"), MILD, STRONG) == "hidden")

    print("\n=== Wiring / Struktur ===")
    _check("21 JS-Const _SPX_DAILY_PERF injiziert (server-Anker)",
           "const _SPX_DAILY_PERF" in SRC and "{market_stress_spx_js}" in SRC)
    _check("22 Schwellen aus config injiziert (kein Hardcode im JS)",
           "{market_stress_strong_pct}" in SRC and "{market_stress_mild_pct}" in SRC)
    _check("23 _renderMarketStress-Funktion existiert",
           "function _renderMarketStress(" in SRC)
    _check("24 Header-Span #hdr-market-stress vorhanden",
           'id="hdr-market-stress"' in SRC)
    _check("25 fetch-unabhängiger DOMContentLoaded-Listener",
           "DOMContentLoaded', function() {{ _renderMarketStress(_SPX_DAILY_PERF)" in SRC)
    _check("26 Anker aus spx_daily_perf im _build_context abgeleitet (kein neuer Fetch)",
           "market_stress_spx" in SRC
           and bool(re.search(r'_v\s*=\s*_s\.get\("spx_daily_perf"\)', SRC)))

    print("\n=== CSS (head.jinja) ===")
    _check("27 .hdr-market-stress-mild (gelb)", ".hdr-market-stress-mild" in HEAD)
    _check("28 .hdr-market-stress-strong (rot)", ".hdr-market-stress-strong" in HEAD)
    _check("29 .hdr-market-stress[hidden] (Normalfall versteckt)",
           ".hdr-market-stress[hidden]" in HEAD)

    print("\n=== Isolation: KEIN Score-/Push-/Filter-/Export-Eingriff ===")
    _func = SRC[SRC.find("function _renderMarketStress("):
                SRC.find("function _applyExitGlows(")]
    _check("30 _renderMarketStress berührt keine Score/Conviction/Push/Filter-Felder",
           not any(k in _func for k in ("score", "conviction", "backtest",
                                        "monster", "push", "filter", "exit_",
                                        "setup_score")))
    # Der Banner ist ANZEIGE: er darf den Move NUR anzeigen, nie in eine
    # Auswahl/Score-Berechnung zurückfließen. Guard gegen versehentliche
    # Filter-Nutzung — nur CODE-Zeilen zählen (Doc-Kommentare mit ``//`` raus).
    _code_uses = [ln for ln in SRC.splitlines()
                  if "_SPX_DAILY_PERF" in ln and not ln.lstrip().startswith("//")]
    # Erwartet exakt 2 Code-Stellen: const-Definition + der DOMContentLoaded-Call.
    _check("31 _SPX_DAILY_PERF nur const-Def + Render-Call (kein Gate/Filter)",
           len(_code_uses) == 2
           and any("const _SPX_DAILY_PERF" in ln for ln in _code_uses)
           and any("_renderMarketStress(_SPX_DAILY_PERF)" in ln for ln in _code_uses))

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle Markt-Stress-Banner-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
