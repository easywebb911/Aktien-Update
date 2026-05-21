"""Mock-Tests für scripts/check_html_assertions.py (Health-Check S9 Phase 1a).

Synthetische HTML-Fixtures als Strings — KEINE echte Generierung über
generate_report.py. Testet evaluate_html_assertions direkt (String rein,
Fail-Liste raus) und deckt alle Severity-Pfade ab.

Ausführung: ``python scripts/mock_test_html_assertions.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.check_html_assertions import evaluate_html_assertions  # noqa: E402


def _build_html(n_articles: int = 10,
                n_cockpit: int | None = None,
                n_price: int | None = None,
                n_pillar: int | None = None) -> str:
    """Baut synthetisches HTML mit gewünschten Klassen-Counts.

    None → defaultet auf article-konformes Pendant
    (1× cockpit/article, 1× price/article, 3× pillar/article)."""
    if n_cockpit is None:
        n_cockpit = n_articles
    if n_price is None:
        n_price = n_articles
    if n_pillar is None:
        n_pillar = n_articles * 3

    parts = ["<html><body>"]
    for i in range(n_articles):
        parts.append(f'<article class="card" id="c{i}">')
    for _ in range(n_cockpit):
        parts.append('<div class="card-cockpit"></div>')
    for _ in range(n_price):
        parts.append('<div class="cockpit-price"></div>')
    for _ in range(n_pillar):
        parts.append('<div class="cockpit-pillar"></div>')
    parts.append("</body></html>")
    return "".join(parts)


def test_01_all_correct() -> None:
    """10 articles, alle Counts korrekt → 0 Fails."""
    html = _build_html(10)
    fails = evaluate_html_assertions(html)
    assert fails == [], f"erwartet 0 Fails, bekam: {fails}"


def test_02_cockpit_price_completely_missing() -> None:
    """cockpit-price komplett weg (0) → CRIT (actual == 0)."""
    html = _build_html(10, n_price=0)
    fails = evaluate_html_assertions(html)
    crit_price = [f for f in fails
                  if f["id"] == "html_cockpit_price_count"
                  and f["severity"] == "crit"]
    assert len(crit_price) == 1, f"erwartet 1 CRIT für price, bekam: {fails}"
    assert crit_price[0]["actual"] == 0
    assert crit_price[0]["expected"] == 10


def test_03_cockpit_price_partial_defect_warn() -> None:
    """3 von 10 cockpit-price (Teil-Defekt, > 50 % vorhanden? Nein, 3/10 = 30 %).

    Klassifikator: actual <= expected/2 → CRIT. 3 ≤ 5 → CRIT.
    Wir wollen WARN-Pfad zeigen mit 7/10 (70 % vorhanden, ≤ 50 % wäre crit).
    """
    html = _build_html(10, n_price=7)
    fails = evaluate_html_assertions(html)
    warn_price = [f for f in fails
                  if f["id"] == "html_cockpit_price_count"
                  and f["severity"] == "warn"]
    assert len(warn_price) == 1, f"erwartet 1 WARN für price, bekam: {fails}"
    assert warn_price[0]["actual"] == 7
    assert warn_price[0]["expected"] == 10


def test_04_cockpit_price_half_or_less_crit() -> None:
    """3/10 cockpit-price → CRIT (3 ≤ 10/2 = 5)."""
    html = _build_html(10, n_price=3)
    fails = evaluate_html_assertions(html)
    crit_price = [f for f in fails
                  if f["id"] == "html_cockpit_price_count"
                  and f["severity"] == "crit"]
    assert len(crit_price) == 1, f"erwartet 1 CRIT für 3/10 price, bekam: {fails}"


def test_05_card_cockpit_mismatch_is_always_crit() -> None:
    """card-cockpit != article-count → IMMER CRIT (Layout-Mix-Indikator),
    auch wenn 9/10 (90 % > 50 %) sonst WARN wäre."""
    html = _build_html(10, n_cockpit=9)
    fails = evaluate_html_assertions(html)
    cockpit_fail = [f for f in fails if f["id"] == "html_card_cockpit_count"]
    assert len(cockpit_fail) == 1, f"erwartet 1 Fail für card-cockpit, bekam: {fails}"
    assert cockpit_fail[0]["severity"] == "crit", \
        f"Layout-Mix muss CRIT sein, bekam: {cockpit_fail[0]['severity']}"


def test_06_zero_articles_is_crit() -> None:
    """article-count == 0 → ein einzelner CRIT-Eintrag, andere Asserts geskippt."""
    html = "<html><body>kein article hier</body></html>"
    fails = evaluate_html_assertions(html)
    assert len(fails) == 1, f"erwartet exakt 1 Fail bei 0 articles, bekam: {fails}"
    assert fails[0]["id"] == "html_card_count"
    assert fails[0]["severity"] == "crit"
    assert fails[0]["actual"] == 0


def test_07_pillar_count_multiplier_correct() -> None:
    """3 Pillars pro Karte: 10 Karten → 30 Pillars. 15 vorhanden → WARN (50 %)."""
    # 15/30 = 50 % → 15 <= 30/2 = 15 → CRIT (per `<=` Grenze)
    html = _build_html(10, n_pillar=15)
    fails = evaluate_html_assertions(html)
    pillar = [f for f in fails if f["id"] == "html_cockpit_pillar_count"]
    assert len(pillar) == 1, f"erwartet Fail für pillar, bekam: {fails}"
    assert pillar[0]["severity"] == "crit"  # 15 == 30/2 → crit
    assert pillar[0]["expected"] == 30
    assert pillar[0]["actual"] == 15


def test_08_pillar_warn_pfad() -> None:
    """20/30 Pillars = 66 % → WARN (zwischen 50 % und 100 %)."""
    html = _build_html(10, n_pillar=20)
    fails = evaluate_html_assertions(html)
    pillar = [f for f in fails if f["id"] == "html_cockpit_pillar_count"]
    assert len(pillar) == 1
    assert pillar[0]["severity"] == "warn"
    assert pillar[0]["actual"] == 20
    assert pillar[0]["expected"] == 30


def test_09_smaller_article_count_basis() -> None:
    """7 Articles statt 10 — Erwartungen sind relativ zur actual article-count."""
    html = _build_html(7)
    fails = evaluate_html_assertions(html)
    assert fails == [], f"erwartet 0 Fails bei 7 article-konformen, bekam: {fails}"


def test_10_invalid_input() -> None:
    """Nicht-String-Input → CRIT (defensive)."""
    fails = evaluate_html_assertions(None)  # type: ignore[arg-type]
    assert len(fails) == 1
    assert fails[0]["severity"] == "crit"


def test_11_all_three_per_card_with_mix() -> None:
    """Mix-Szenario: alles passt außer card-cockpit (9 statt 10) → CRIT-Mix.

    cockpit-price und pillar bleiben OK (10 / 30) — nur Mix-Eintrag."""
    html = _build_html(10, n_cockpit=9, n_price=10, n_pillar=30)
    fails = evaluate_html_assertions(html)
    assert len(fails) == 1, f"erwartet exakt 1 Fail (Mix only), bekam: {fails}"
    assert fails[0]["id"] == "html_card_cockpit_count"
    assert fails[0]["severity"] == "crit"


def main() -> int:
    tests = [
        test_01_all_correct,
        test_02_cockpit_price_completely_missing,
        test_03_cockpit_price_partial_defect_warn,
        test_04_cockpit_price_half_or_less_crit,
        test_05_card_cockpit_mismatch_is_always_crit,
        test_06_zero_articles_is_crit,
        test_07_pillar_count_multiplier_correct,
        test_08_pillar_warn_pfad,
        test_09_smaller_article_count_basis,
        test_10_invalid_input,
        test_11_all_three_per_card_with_mix,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except AssertionError as exc:
            print(f"  ✗ {t.__name__}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ✗ {t.__name__}: unexpected {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} Tests OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
