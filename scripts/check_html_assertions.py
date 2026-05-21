"""HTML-Sanity-Check (Health-Check S9, Phase 1a + 1b).

Fängt stille DOM-Degradation durch Selektor-Mismatch (Bug-Klasse aus
PR #199/#226/#235) — der heutige Health-Check liest den generierten
``index.html`` nicht und merkt nichts wenn z.B. CSS-Selektor-Renames
ganze Render-Pfade auf v1-Fallback zurückfallen lassen.

Phase 1a (PR #237) misst vier deterministische Top-Counts auf dem
gerenderten HTML — Gesamt-Counts ohne Pro-Card-Auflösung. Das fängt
Layout-Mix-Defekte und harte Klassen-Renames, aber NICHT „eine Karte
mit 0 cockpit-price und eine mit 2 — Summe 10, durchgerutscht".

Phase 1b erweitert das um sieben **Pro-Card-Checks** mit echtem
Article-Split, plus zwei **Setup-Pillar-Wert-Checks** (numerisch und
> 0). Wichtigster neuer Schutz: ein einzelnes Card mit Setup-Pillar
``"—"`` statt Score ist beschädigte Trading-Information und blockt
in Phase 1b sofort als CRIT.

Beide Phasen laufen in **derselben Fail-Liste** mit identischem
Dict-Schema; Phase 1a ist unverändert und unabhängig von Phase 1b.

Pure function: nimmt einen HTML-String, gibt eine Liste von Fail-Dicts
zurück (leer wenn alles OK). Kein I/O. Wird vom ``health_check.S9``-
Block via ``html_path``-Kwarg eingebunden.
"""

from __future__ import annotations

import re


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

    # ── Phase 1b: Pro-Card-Checks ─────────────────────────────────────────
    # Läuft NACH der Phase-1a-Loop. Wenn Phase 1a bereits CRIT-Fails
    # hat, läuft 1b trotzdem durch — Easy soll alle Defekte in einer
    # Fehler-Meldung sehen, statt cascading.
    fails.extend(_evaluate_per_card(html, article_count))

    return fails


# ── Phase 1b — Pro-Card-Checks ─────────────────────────────────────────────
#
# Gold-Liste der deterministischen Per-Card-Checks (alle mit per-Card-
# Count == 1 oder 3 als Soll-Wert):
_PER_CARD_ASSERTION_SPECS = (
    {
        "id":       "html_per_card_cockpit_price",
        "label":    "cockpit-price",
        "literal":  'class="cockpit-price"',
        "is_prefix": False,
        "per_card": 1,
    },
    {
        "id":       "html_per_card_cockpit_ticker_block",
        "label":    "cockpit-ticker-block",
        "literal":  'class="cockpit-ticker-block"',
        "is_prefix": False,
        "per_card": 1,
    },
    {
        "id":       "html_per_card_cockpit_pillar",
        "label":    "cockpit-pillar",
        "literal":  'class="cockpit-pillar"',
        "is_prefix": False,
        "per_card": 3,
    },
    {
        # Prefix-Falle: im echten HTML steht hier IMMER ein Konfidenz-
        # Tier-Suffix (sb-conf-robust / -mittel / -prov / -heur). Daher
        # ohne Closing-Quote matchen.
        "id":       "html_per_card_cockpit_pillar_value",
        "label":    "cockpit-pillar-value",
        "literal":  'class="cockpit-pillar-value',
        "is_prefix": True,
        "per_card": 3,
    },
    {
        # Selbe Prefix-Falle wie pillar-value.
        "id":       "html_per_card_cockpit_donut_number",
        "label":    "cockpit-donut-number",
        "literal":  'class="cockpit-donut-number',
        "is_prefix": True,
        "per_card": 1,
    },
)


# Regex zur robusten Setup-Pillar-Wert-Extraktion:
#   data-sb="setup" markiert eindeutig den Setup-Pillar (reihenfolge-
#   unabhängig). Greedy-Skip bis zum ersten cockpit-pillar-value-Tag
#   innerhalb desselben pillar-Containers; Inner-Text bis zum nächsten
#   ``<``-Char (das schließende </div>). DOTALL für Mehrzeiler-Resilienz.
_SETUP_VAL_RE = re.compile(
    r'data-sb="setup"[^>]*>.*?class="cockpit-pillar-value[^"]*"[^>]*>([^<]*)<',
    re.DOTALL,
)


def _split_articles(html: str) -> list[str]:
    """Teilt das gerenderte HTML in Article-Slices an
    ``<article class="card``-Boundary. Letztes Slice endet bei
    ``</body>``-Tag (oder Doku-Ende, falls fehlt) und kann nachfolgenden
    Section-Content (Watchlist etc.) enthalten — die per-Card-Counts
    pro Slice bleiben trotzdem gut definiert, weil die gesuchten
    Cockpit-Klassen außerhalb der Top-10-Cards nicht vorkommen.

    Returnt 0 Slices bei leerem HTML oder fehlendem Article-Tag.
    """
    if not isinstance(html, str) or not html:
        return []
    positions: list[int] = []
    start = 0
    while True:
        idx = html.find(_ARTICLE_LITERAL, start)
        if idx < 0:
            break
        positions.append(idx)
        start = idx + len(_ARTICLE_LITERAL)
    if not positions:
        return []
    end_marker = html.find('</body>')
    if end_marker < 0:
        end_marker = len(html)
    slices: list[str] = []
    for i, p in enumerate(positions):
        slice_end = positions[i + 1] if i + 1 < len(positions) else end_marker
        slices.append(html[p:slice_end])
    return slices


def _per_card_severity(n_broken: int, n_articles: int) -> str:
    """Severity-Mapping für Pro-Card-Sub-Counts:
    1-5 Cards kaputt → warn; ≥6 (≥ Hälfte einer Top-10) → crit.
    Schwelle ist hartkodiert auf 6, weil Top-10 die normale Größe ist;
    bei kleineren Pools (n_articles < 10) wird trotzdem >= ceil(n/2)
    als crit klassifiziert.
    """
    if n_broken <= 0:
        return "ok"
    threshold = (n_articles + 1) // 2  # ceil(n/2)
    return "crit" if n_broken >= threshold else "warn"


def _evaluate_per_card(html: str, article_count: int) -> list[dict]:
    """Phase-1b-Loop. Splittet das HTML in Article-Slices und prüft
    die 5 Sub-Counts pro Karte + 2 Setup-Pillar-Wert-Checks.

    Returnt Liste von Fail-Dicts (leer wenn alles OK). Jeder Eintrag
    trägt zusätzlich zum Phase-1a-Schema noch ``card_idx`` (1-basiert)
    oder ``card_indices`` (aggregierte Liste), damit Easy im Push
    direkt weiß welche Karte kaputt ist.
    """
    slices = _split_articles(html)
    if not slices or len(slices) != article_count:
        # Inkonsistenz zwischen Phase-1a-Count und Slice-Count: das ist
        # ein Slicer-Bug, kein Render-Bug. Defensive: nur dann melden,
        # wenn auch wirklich Slices da sind aber nicht passend. Phase 1a
        # hat bereits eigene Asserts für article_count.
        if slices and len(slices) != article_count:
            return [{
                "id":       "html_per_card_slice_mismatch",
                "severity": "warn",
                "detail":   (f"Article-Slice-Count ({len(slices)}) "
                             f"weicht von article_count "
                             f"({article_count}) ab — Phase-1b-Pfad "
                             f"übersprungen"),
                "expected": article_count,
                "actual":   len(slices),
            }]
        return []

    fails: list[dict] = []

    # === Checks 1-5: Per-Card-Sub-Counts =================================
    for spec in _PER_CARD_ASSERTION_SPECS:
        broken: list[tuple[int, int]] = []  # (card_idx, actual)
        for idx, article in enumerate(slices, start=1):
            actual = article.count(spec["literal"])
            if actual != spec["per_card"]:
                broken.append((idx, actual))
        if not broken:
            continue
        sev = _per_card_severity(len(broken), article_count)
        match_kind = " (prefix-match)" if spec["is_prefix"] else ""
        if len(broken) == 1:
            idx, act = broken[0]
            detail = (f"Card #{idx}: {spec['label']}{match_kind} "
                      f"= {act}, erwartet {spec['per_card']}")
        else:
            sample = ", ".join(
                f"#{idx}({act})" for idx, act in broken[:5]
            )
            more = f" und {len(broken) - 5} weitere" if len(broken) > 5 else ""
            detail = (f"{len(broken)}/{article_count} Cards mit "
                      f"{spec['label']}{match_kind}-Defekt: {sample}{more} "
                      f"(erwartet {spec['per_card']} pro Card)")
        fails.append({
            "id":            spec["id"],
            "severity":      sev,
            "detail":        detail,
            "expected":      spec["per_card"],
            "card_indices":  [idx for idx, _ in broken],
        })

    # === Check 6: Setup-Pillar-Wert numerisch ============================
    # Setup-Pillar-Wert kommt aus _card_cockpit_html als f"{setup_val:.1f}"
    # — IMMER numerisch, kein None-Fallback. Ein "—" oder leerer Wert
    # ist beschädigte Trading-Info → IMMER crit (unabhängig von n_broken).
    non_numeric: list[tuple[int, str]] = []
    non_positive: list[tuple[int, float]] = []
    missing_pillar: list[int] = []
    for idx, article in enumerate(slices, start=1):
        m = _SETUP_VAL_RE.search(article)
        if not m:
            missing_pillar.append(idx)
            continue
        raw = (m.group(1) or "").strip()
        try:
            num = float(raw)
        except (ValueError, TypeError):
            non_numeric.append((idx, raw))
            continue
        if num <= 0:
            non_positive.append((idx, num))

    if missing_pillar:
        # Setup-Pillar gar nicht extrahierbar via data-sb="setup" —
        # das ist ein Render-Strukturbruch, IMMER crit.
        sample = ", ".join(f"#{i}" for i in missing_pillar[:5])
        more = f" und {len(missing_pillar) - 5} weitere" if len(missing_pillar) > 5 else ""
        fails.append({
            "id":           "html_setup_pillar_missing",
            "severity":     "crit",
            "detail":       (f"{len(missing_pillar)} Card(s) ohne "
                             f"extrahierbaren Setup-Pillar (data-sb=\"setup\" "
                             f"→ cockpit-pillar-value): {sample}{more}"),
            "card_indices": list(missing_pillar),
        })

    if non_numeric:
        # IMMER crit — Setup-Pillar-Wert nicht-numerisch heißt der
        # Renderer hat None statt Score bekommen, das ist eine
        # beschädigte Trading-Information. Auch eine einzelne Card
        # reicht für einen Push-Block.
        sample = ", ".join(f"#{i}({v!r})" for i, v in non_numeric[:5])
        more = f" und {len(non_numeric) - 5} weitere" if len(non_numeric) > 5 else ""
        fails.append({
            "id":           "html_setup_pillar_non_numeric",
            "severity":     "crit",
            "detail":       (f"{len(non_numeric)} Card(s) mit "
                             f"nicht-numerischem Setup-Pillar-Wert "
                             f"(beschädigte Trading-Info): {sample}{more}"),
            "card_indices": [i for i, _ in non_numeric],
        })

    if non_positive:
        # Setup-Pillar = 0 oder negativ: theoretisch Score-Inflation-
        # Bug ODER ein Top-10-Eintrag mit Score=0 (sollte nicht
        # vorkommen, aber Setup gehört in Top-10 → muss > 0 sein).
        # 1 Card = warn, >=2 = crit.
        sev = "crit" if len(non_positive) >= 2 else "warn"
        sample = ", ".join(f"#{i}({v:.1f})" for i, v in non_positive[:5])
        more = f" und {len(non_positive) - 5} weitere" if len(non_positive) > 5 else ""
        fails.append({
            "id":           "html_setup_pillar_non_positive",
            "severity":     sev,
            "detail":       (f"{len(non_positive)} Card(s) mit "
                             f"Setup-Pillar ≤ 0: {sample}{more}"),
            "card_indices": [i for i, _ in non_positive],
        })

    return fails


__all__ = ["evaluate_html_assertions"]
