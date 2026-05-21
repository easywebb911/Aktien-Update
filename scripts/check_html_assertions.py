"""HTML-Sanity-Check (Health-Check S9, Phase 1a).

Fängt stille DOM-Degradation durch Selektor-Mismatch (Bug-Klasse aus
PR #199/#226/#235) — der heutige Health-Check liest den generierten
``index.html`` nicht und merkt nichts wenn z.B. CSS-Selektor-Renames
ganze Render-Pfade auf v1-Fallback zurückfallen lassen.

Phase 1a misst nur vier deterministische Top-Counts auf dem
gerenderten HTML — keine Pro-Card-Asserts, keine Pillar-Numerik (das
ist Phase 1b). Basis ist die tatsächliche article-count statt hart 10,
damit der Check robust ist falls die Top-10-Liste mal weniger Einträge
hat.

Pure function: nimmt einen HTML-String, gibt eine Liste von Fail-Dicts
zurück (leer wenn alles OK). Kein I/O. Wird vom ``health_check.S9``-
Block via ``html_path``-Kwarg eingebunden.
"""

from __future__ import annotations


# ── Assertion-Specs ────────────────────────────────────────────────────────
#
# Jeder Eintrag definiert ein Klassen-Literal, dessen Vorkommen relativ
# zur tatsächlichen article-count erwartet wird. Multiplikator gibt an,
# wie oft pro Karte das Literal vorkommen muss (3 = 3 Cockpit-Pillars
# pro Karte etc.).

_ARTICLE_LITERAL = '<article class="card'

_ASSERTION_SPECS = (
    {
        "id":          "html_card_cockpit_count",
        "literal":     'class="card-cockpit"',
        "per_article": 1,
        "label":       "card-cockpit",
    },
    {
        "id":          "html_cockpit_price_count",
        "literal":     'class="cockpit-price"',
        "per_article": 1,
        "label":       "cockpit-price",
    },
    {
        "id":          "html_cockpit_pillar_count",
        "literal":     'class="cockpit-pillar"',
        "per_article": 3,
        "label":       "cockpit-pillar",
    },
)


def _classify(actual: int, expected: int) -> str:
    """Severity-Mapping: crit wenn 0 oder ≤50%, warn wenn 1-49% kaputt,
    OK wenn exakt. Edge: expected == 0 → OK wenn actual == 0, sonst warn
    (defensive — sollte in Praxis nicht eintreten weil article==0 vorher
    schon als CRIT klassifiziert wird)."""
    if actual == expected:
        return "ok"
    if expected <= 0:
        return "warn" if actual > 0 else "ok"
    if actual == 0 or actual <= expected / 2:
        return "crit"
    return "warn"


def evaluate_html_assertions(html: str) -> list[dict]:
    """Bewertet die 4 Phase-1a-Counts auf dem gerenderten HTML.

    Returnt Liste von Fail-Dicts (leer wenn alles OK). Jeder Eintrag:
    ``{"id": <slug>, "severity": "crit"|"warn", "detail": <text>,
    "expected": <int>, "actual": <int>}``.

    Zusatz-CRIT-Regel: wenn ``card-cockpit``-Count nicht zur
    ``article``-Count passt, wird der Eintrag immer als ``crit``
    klassifiziert (Layout-Mix-Indikator: halbe Cockpit, halbe
    v1-Fallback-Karten).

    Edge-Case: ``article``-Count == 0 → ein einzelner CRIT-Eintrag
    (Render komplett kaputt); andere Assertions werden übersprungen.
    """
    if not isinstance(html, str):
        return [{
            "id":       "html_input_invalid",
            "severity": "crit",
            "detail":   f"HTML-Input kein String: {type(html).__name__}",
            "expected": None,
            "actual":   None,
        }]

    article_count = html.count(_ARTICLE_LITERAL)

    if article_count == 0:
        return [{
            "id":       "html_card_count",
            "severity": "crit",
            "detail":   "Keine <article class=\"card …\"> im HTML — "
                        "Render komplett kaputt",
            "expected": ">=1",
            "actual":   0,
        }]

    fails: list[dict] = []
    for spec in _ASSERTION_SPECS:
        expected = article_count * spec["per_article"]
        actual = html.count(spec["literal"])
        sev = _classify(actual, expected)

        # Zusatz-CRIT-Regel: card-cockpit != article-count ist immer
        # CRIT (Layout-Mix). Selbst wenn der Klassifizierer sonst nur
        # "warn" zurückgeben würde.
        if spec["id"] == "html_card_cockpit_count" and actual != expected:
            sev = "crit"

        if sev == "ok":
            continue

        fails.append({
            "id":       spec["id"],
            "severity": sev,
            "detail":   (f"{spec['label']}: {actual} gefunden, "
                         f"{expected} erwartet "
                         f"(article-count={article_count})"),
            "expected": expected,
            "actual":   actual,
        })

    return fails


__all__ = ["evaluate_html_assertions"]
