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
                n_pillar: int | None = None,
                broken_setup_idx: list[int] | None = None,
                zero_setup_idx: list[int] | None = None,
                pillar_value_with_suffix: bool = True) -> str:
    """Baut synthetisches HTML mit Phase-1b-tauglicher Per-Card-Struktur.

    Jede Card wird als self-contained Article-Block gerendert (kein
    flacher Dump von Sub-Elementen nach allen Article-Open-Tags).

    Counter-Parameter ("erste N Cards mit dem Element"):
    - n_cockpit:  erste N Cards mit ``<div class="card-cockpit">``
    - n_price:    erste N Cards mit ``cockpit-price``
    - n_pillar:   TOTAL-Anzahl ``cockpit-pillar`` über alle Cards
                  (sequenziell ab Card #1 verteilt, max 3 pro Card).
                  Pillar-Value wird immer mit dem Pillar zusammen
                  gerendert.

    Phase-1b-spezifische Knöpfe:
    - broken_setup_idx: 1-basierte Card-Indizes, deren Setup-Pillar-
      Wert auf ``"—"`` gesetzt wird (statt der numerischen Default)
    - zero_setup_idx: 1-basierte Card-Indizes, deren Setup-Pillar-Wert
      auf ``0.0`` gesetzt wird (Check 7-Pfad)
    - pillar_value_with_suffix: ``False`` → Pillar-Value ohne
      Konfidenz-Tier-Suffix (Regression-Test gegen die Exact-Match-
      Falle aus Phase 1a)

    Defaults: alle Cards Phase-1b-konform.
    """
    if n_cockpit is None:
        n_cockpit = n_articles
    if n_price is None:
        n_price = n_articles
    if n_pillar is None:
        n_pillar = n_articles * 3
    broken_setup_idx = set(broken_setup_idx or [])
    zero_setup_idx = set(zero_setup_idx or [])

    pv_suffix = " sb-conf-robust" if pillar_value_with_suffix else ""
    dn_suffix = " sb-conf-heur"   if pillar_value_with_suffix else ""
    pillar_names = ["setup", "monster", "ki"]

    parts = ["<html><body>"]
    pillars_remaining = n_pillar
    for i in range(n_articles):
        card_idx = i + 1  # 1-basiert für broken_setup_idx
        parts.append(f'<article class="card" id="c{i}">')
        has_cockpit = i < n_cockpit
        if has_cockpit:
            parts.append('<div class="card-cockpit">')
        parts.append('<div class="cockpit-ticker-block"></div>')
        if i < n_price:
            parts.append('<div class="cockpit-price"></div>')
        card_pillars = min(3, max(0, pillars_remaining))
        for p_idx in range(card_pillars):
            name = pillar_names[p_idx]
            if name == "setup":
                if card_idx in broken_setup_idx:
                    val = "—"
                elif card_idx in zero_setup_idx:
                    val = "0.0"
                else:
                    val = "85.0"
            else:
                val = "70"
            parts.append(
                f'<div class="cockpit-pillar" data-sb="{name}">'
                f'<div class="cockpit-pillar-value{pv_suffix}">{val}</div>'
                f'</div>'
            )
        pillars_remaining -= card_pillars
        parts.append(f'<div class="cockpit-donut-number{dn_suffix}">75</div>')
        if has_cockpit:
            parts.append('</div>')
        parts.append('</article>')
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

    cockpit-price und pillar bleiben OK (10 / 30) — nur Mix-Eintrag.

    Card #10 hat in der Phase-1b-Fixture auch keinen ``card-cockpit``-
    Wrapper, aber alle 7 Gold-List-Per-Card-Checks (price/ticker-block/
    pillar/pillar-value/donut-number) sind via Helper-Default trotzdem
    in jeder Card vorhanden — daher KEIN zusätzlicher Phase-1b-Fail."""
    html = _build_html(10, n_cockpit=9, n_price=10, n_pillar=30)
    fails = evaluate_html_assertions(html)
    assert len(fails) == 1, f"erwartet exakt 1 Fail (Mix only), bekam: {fails}"
    assert fails[0]["id"] == "html_card_cockpit_count"
    assert fails[0]["severity"] == "crit"


# ── Phase 1b — Pro-Card-Checks ────────────────────────────────────────────


def test_12_per_card_all_healthy() -> None:
    """Default-Fixture (10 Cards voll Phase-1b-konform) → 0 Phase-1b-Fails."""
    html = _build_html(10)
    fails = evaluate_html_assertions(html)
    pc = [f for f in fails if f["id"].startswith("html_per_card_")
          or f["id"].startswith("html_setup_pillar_")]
    assert pc == [], f"erwartet 0 Phase-1b-Fails, bekam: {pc}"


def test_13_per_card_price_one_defect_warn() -> None:
    """1 von 10 Cards ohne cockpit-price → WARN (Phase 1b per-card)."""
    html = _build_html(10, n_price=9)
    fails = evaluate_html_assertions(html)
    pc = [f for f in fails if f["id"] == "html_per_card_cockpit_price"]
    assert len(pc) == 1, f"erwartet 1 Phase-1b-fail, bekam: {pc}"
    assert pc[0]["severity"] == "warn"
    assert pc[0]["card_indices"] == [10], \
        f"erwartet card #10 als defekt, bekam: {pc[0]['card_indices']}"


def test_14_per_card_price_six_defects_crit() -> None:
    """6 von 10 Cards ohne cockpit-price → CRIT (Phase 1b per-card, ≥ ceil(n/2))."""
    html = _build_html(10, n_price=4)
    fails = evaluate_html_assertions(html)
    pc = [f for f in fails if f["id"] == "html_per_card_cockpit_price"]
    assert len(pc) == 1
    assert pc[0]["severity"] == "crit", \
        f"6/10 broken sollte CRIT sein, bekam: {pc[0]['severity']}"
    assert len(pc[0]["card_indices"]) == 6


def test_15_setup_pillar_em_dash_always_crit() -> None:
    """Ein einzelnes Card mit Setup-Pillar="—" → IMMER CRIT (beschädigte
    Trading-Info, unabhängig von n_broken)."""
    html = _build_html(10, broken_setup_idx=[3])
    fails = evaluate_html_assertions(html)
    sp = [f for f in fails if f["id"] == "html_setup_pillar_non_numeric"]
    assert len(sp) == 1, f"erwartet 1 non-numeric-fail, bekam: {sp}"
    assert sp[0]["severity"] == "crit", \
        "Setup-Pillar non-numeric muss IMMER CRIT sein (auch bei n=1)"
    assert sp[0]["card_indices"] == [3]


def test_16_setup_pillar_zero_one_card_warn() -> None:
    """1 Card mit Setup-Pillar="0.0" → WARN (Check 7: <= 0, n=1)."""
    html = _build_html(10, zero_setup_idx=[5])
    fails = evaluate_html_assertions(html)
    sp = [f for f in fails if f["id"] == "html_setup_pillar_non_positive"]
    assert len(sp) == 1, f"erwartet 1 non-positive-fail, bekam: {sp}"
    assert sp[0]["severity"] == "warn", \
        f"1 Card mit Setup ≤ 0 sollte WARN sein, bekam: {sp[0]['severity']}"
    assert sp[0]["card_indices"] == [5]


def test_17_setup_pillar_zero_two_cards_crit() -> None:
    """2 Cards mit Setup-Pillar="0.0" → CRIT (Check 7: n >= 2)."""
    html = _build_html(10, zero_setup_idx=[2, 7])
    fails = evaluate_html_assertions(html)
    sp = [f for f in fails if f["id"] == "html_setup_pillar_non_positive"]
    assert len(sp) == 1
    assert sp[0]["severity"] == "crit", \
        f"2 Cards mit Setup ≤ 0 sollten CRIT sein, bekam: {sp[0]['severity']}"
    assert sorted(sp[0]["card_indices"]) == [2, 7]


def test_18_prefix_match_with_conf_suffix_counts() -> None:
    """Regression gegen die Exact-Match-Falle aus Phase 1a:
    cockpit-pillar-value MIT sb-conf-Suffix wird vom Phase-1b-Per-Card-
    Check korrekt als Treffer gezählt. Wenn Phase 1b versehentlich auf
    Exact-Match (mit closing-quote) umgestellt würde, wären alle Cards
    als defekt markiert.
    """
    html = _build_html(10, pillar_value_with_suffix=True)
    fails = evaluate_html_assertions(html)
    pc_val = [f for f in fails
              if f["id"] == "html_per_card_cockpit_pillar_value"]
    assert pc_val == [], \
        f"Prefix-Match muss sb-conf-Suffix-Variante erkennen, bekam Fails: {pc_val}"

    # Negative Kontrolle: ohne Suffix muss ebenfalls erkannt werden
    html_no_sfx = _build_html(10, pillar_value_with_suffix=False)
    fails_no_sfx = evaluate_html_assertions(html_no_sfx)
    pc_val_no_sfx = [f for f in fails_no_sfx
                     if f["id"] == "html_per_card_cockpit_pillar_value"]
    assert pc_val_no_sfx == [], \
        ("Prefix-Match muss AUCH ohne Suffix erkennen, bekam Fails: "
         f"{pc_val_no_sfx}")


def test_19_per_card_fail_detail_names_card_index() -> None:
    """Fail-Detail-Text muss den Card-Index nennen (1-basiert)."""
    html = _build_html(10, n_price=9)
    fails = evaluate_html_assertions(html)
    pc = [f for f in fails if f["id"] == "html_per_card_cockpit_price"]
    assert len(pc) == 1
    assert "#10" in pc[0]["detail"], \
        f"erwartet '#10' im Detail, bekam: {pc[0]['detail']!r}"


def test_20_per_card_donut_number_prefix_match() -> None:
    """Phase-1b-Per-Card-Check für cockpit-donut-number trifft mit
    Prefix-Match (Konfidenz-Tier-Suffix nicht obligat)."""
    html = _build_html(10)  # default with sb-conf-heur-Suffix
    fails = evaluate_html_assertions(html)
    dn = [f for f in fails if f["id"] == "html_per_card_cockpit_donut_number"]
    assert dn == [], f"erwartet 0 Donut-Fails, bekam: {dn}"


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
        # ── Phase 1b ────────────────────────────────────────────
        test_12_per_card_all_healthy,
        test_13_per_card_price_one_defect_warn,
        test_14_per_card_price_six_defects_crit,
        test_15_setup_pillar_em_dash_always_crit,
        test_16_setup_pillar_zero_one_card_warn,
        test_17_setup_pillar_zero_two_cards_crit,
        test_18_prefix_match_with_conf_suffix_counts,
        test_19_per_card_fail_detail_names_card_index,
        test_20_per_card_donut_number_prefix_match,
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
