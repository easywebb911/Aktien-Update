"""Mock-Test: Selektor-Konsistenz JS-DOM-Patcher <-> Karten-Render (20.05.2026).

Haette die Cockpit-Migrations-Bug-Welle (PR #199 -> #229/#231) sofort gefangen:
".price-tag" im Polling-Patcher fand auf Cockpit-Karten kein Element, weil
das Cockpit-Render auf ".cockpit-price" umgestellt hat. Selber Klasse-Drift
existiert(e) fuer ".ticker-block" (renderAgentSignals push-silenced-Badge)
und ".price-tag" (_refreshPositionPanel im Watchlist-Drawer).

Architektur (Variante Hybrid A + C):

  * Variante C: Whitelist-Map ``PATCHER_SELECTORS`` listet pro DOM-Patcher
    die erwarteten Karten-relevanten Selektoren.
  * Variante A: statischer grep parsed die Patcher-Funktions-Bodies und
    vergleicht gefundene literale Selektoren mit der Whitelist.
  * Render-Coverage: pro Whitelist-Eintrag muss mindestens ein literaler
    Class-Tref in einem der Render-Pfade existieren (oder Patcher ist
    als ``DYNAMIC_ONLY`` markiert, weil das Element zur Laufzeit erzeugt
    wird).

Tests:
  1. Patcher-Funktions-Body laesst sich extrahieren
  2. Drift-Schutz: jeder literale ``querySelector(All)?``-Selektor im
     Patcher steht in der Whitelist UND umgekehrt
  3. Render-Coverage: jede Whitelist-Klasse (ausser DYNAMIC_ONLY) ist
     in mindestens einem Render-Pfad als ``class="..."`` zu finden
  4. Bekannte historische Mismatches sind behoben (Regressions-Schutz
     gegen Re-Introduktion):
       - ``.ticker-block, .cockpit-ticker-block`` in renderAgentSignals
       - ``.price-tag, .cockpit-price`` in _refreshPositionPanel
       - ``.price-tag, .cockpit-price`` in _quotePatchScope
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR_SRC   = (ROOT / "generate_report.py").read_text(encoding="utf-8")
CARD_JNJ = (ROOT / "templates" / "card.jinja").read_text(encoding="utf-8")


# == Whitelist: pro Patcher die erwarteten Selektoren ========================
# Compound-Selektoren ".a, .b" werden bei der Coverage als OR behandelt
# (mind. eine Komponente muss in einem Render-Pfad existieren).

PATCHER_SELECTORS: dict[str, list[str]] = {
    "_quoteSetIndicator": [
        ".quote-live-dot",
    ],
    "_quotePatchScope": [
        ".price-tag, .cockpit-price",
        ".cockpit-change",
        ".metric-box",
        ".m-lbl",
        ".m-val",
        ".pos-pnl-live",
    ],
    "_quoteEnsureLiveDot": [
        ".quote-live-dot",
        ".cockpit-header-right",
        ".card-cockpit",
        ".score-block",
        ".card-top",
    ],
    "_patchWlMomentumLive": [
        ".metric-box",
        ".m-lbl",
        ".m-val",
    ],
    "renderAgentSignals": [
        ".card[data-ticker]",
        ".ticker",
        ".ticker-block, .cockpit-ticker-block",
        ".push-silenced-badge",
        ".detail-table",
        ".detail-st-row",
        ".detail-rvol-row",
        ".ki-signal-block",
        ".ki-signal-body",
        ".spark-wrap",
    ],
    "_refreshPositionPanel": [
        ".position-panel",
        ".price-tag, .cockpit-price",
    ],
}

# Selektoren, deren Element vom Patcher selbst zur Laufzeit erzeugt /
# entfernt wird (kein statisches Render-Pendant noetig). Skip im
# Coverage-Test, aber im Drift-Test sichtbar.
DYNAMIC_ONLY: set[str] = {
    ".push-silenced-badge",
    ".detail-st-row",
    ".detail-rvol-row",
}

# == Render-Pfade (Suche nach class="..." in diesen Quellen) =================

RENDER_PATHS: list[tuple[str, str]] = [
    ("_card_cockpit_html",
     "def _card_cockpit_html("),
    ("_build_card_ctx (v2 incl. v1-Fallback)",
     "def _build_card_ctx("),
    ("_card (v1)",
     "def _card("),
    ("templates/card.jinja",
     None),                   # eigene Datei, separat geladen
    ("buildWlDetails (Outsider-Build)",
     "function buildWlDetails("),
    ("buildPositionPanel (WL-Drawer-Position)",
     "function buildPositionPanel("),
]


def _func_block(src: str, def_marker: str) -> str:
    """Extrahiert Funktions-Body von ``def_marker`` bis zum naechsten Top-
    Level-``def`` bzw. EOF. Auch fuer JS-Funktionen (``function name(``).
    """
    idx = src.find(def_marker)
    assert idx > 0, f"Marker {def_marker!r} nicht gefunden"
    rest = src[idx + len(def_marker):]
    # Python ``def`` am Zeilenanfang oder JS ``function``/``async function``
    # (auch innerhalb IIFE-Blocks indented). ``\s*`` matched 0..n
    # Leerzeichen am Zeilenstart.
    # Erkennt auch Assignment-Form (``window.X = function``,
    # ``window.X = async function``).
    end_m = re.search(
        r"\n\s*(?:"
        r"def "
        r"|function "
        r"|async function "
        r"|window\.\w+\s*=\s*(?:async\s+)?function"
        r")",
        rest,
    )
    end = (idx + len(def_marker) + end_m.start()) if end_m else len(src)
    return src[idx:end]


# == Test 1 — Patcher-Bodies extrahierbar ====================================

def test_01_patcher_bodies_extractable() -> None:
    for fn in PATCHER_SELECTORS:
        # Sowohl ``function fn(`` (top-level) als auch ``function fn(``
        # innerhalb eines IIFE-Blocks treffen denselben Marker.
        marker = f"function {fn}("
        assert marker in GR_SRC, (
            f"Patcher-Funktion ``{fn}`` nicht im Source gefunden")


# == Helpers fuer Test 2 + 3 =================================================

_QS_RE = re.compile(r"querySelector(?:All)?\(\s*['\"]([^'\"]+)['\"]\s*\)")


def _selectors_in_func(fn_name: str) -> set[str]:
    """Liefert Class-/Attribut-Selektoren aus dem Patcher-Body.

    Reine Tag-Selektoren (``span``, ``div``) sind nicht Drift-relevant —
    HTML-Element-Namen sind stabil. Wir interessieren uns nur fuer
    Class-Selektoren (``.foo``) und Attribut-Selektoren (``[data-xxx]``),
    die der Cockpit-Migrations-Bug-Klasse unterliegen koennen.
    """
    body = _func_block(GR_SRC, f"function {fn_name}(")
    raw = set(_QS_RE.findall(body))
    return {s for s in raw if "." in s or "[" in s}


def _classes_from_selector(sel: str) -> list[str]:
    """Extrahiert Klassen-Namen aus einem Selektor (ohne fuehrenden ``.``,
    ohne Attribut-Predicates). Compound-Selektoren werden zerlegt."""
    parts = [p.strip() for p in sel.split(",")]
    out: list[str] = []
    for p in parts:
        # Attribute strippen: ``.card[data-ticker]`` -> ``card``
        p_noattr = re.sub(r"\[[^\]]+\]", "", p)
        # Erster ``.foo`` extrahieren
        m = re.match(r"\.([A-Za-z][A-Za-z0-9_\-]*)", p_noattr)
        if m:
            out.append(m.group(1))
    return out


# Korpus aller Render-Pfade vorab bauen (einmalig).

def _build_render_corpus() -> dict[str, str]:
    corpus: dict[str, str] = {}
    for label, marker in RENDER_PATHS:
        if marker is None:
            corpus[label] = CARD_JNJ
        else:
            corpus[label] = _func_block(GR_SRC, marker)
    return corpus


_RENDER_CORPUS = _build_render_corpus()


def _class_found_in_render(cls_name: str) -> list[str]:
    """Sucht ``class="cls_name"`` oder ``class="... cls_name ..."`` in
    allen Render-Pfaden. Akzeptiert auch Praefix-Form (``cls_name-...``)
    fuer dynamisch suffixierte Klassen (z. B. ``cockpit-change-up`` matcht
    Whitelist-Eintrag ``cockpit-change``)."""
    hits: list[str] = []
    # 1) Exakter Match: class="X" oder " X " oder Anfang/Ende eines class-Attribut-Werts.
    exact_re = re.compile(
        r'class\s*=\s*["\']([^"\']*\b' + re.escape(cls_name) + r'\b[^"\']*)["\']'
    )
    # 2) Praefix-Match: class="X-foo" oder " X-foo "
    prefix_re = re.compile(
        r'class\s*=\s*["\']([^"\']*\b' + re.escape(cls_name) + r'-[A-Za-z0-9_\-]+\b[^"\']*)["\']'
    )
    for label, corpus in _RENDER_CORPUS.items():
        if exact_re.search(corpus) or prefix_re.search(corpus):
            hits.append(label)
    return hits


# == Test 2 — Drift-Schutz (Patcher-Source <-> Whitelist) ====================

def test_02_drift_no_unknown_selectors_in_source() -> None:
    """Jeder literale ``querySelector(All)``-Selektor im Patcher-Body
    muss in der Whitelist stehen. Faengt: neuer Selektor wurde
    hinzugefuegt, Whitelist nicht mit-gepflegt."""
    for fn, expected in PATCHER_SELECTORS.items():
        found = _selectors_in_func(fn)
        whitelist = set(expected)
        unknown = found - whitelist
        # Hinweis: scope.querySelector(...) und card.querySelector(...) sind
        # gleichwertig — Selektor-String ist das, was zaehlt.
        assert not unknown, (
            f"{fn}: Unbekannte(r) Selektor(en) im Source: {sorted(unknown)}.\n"
            f"   Whitelist erweitern in PATCHER_SELECTORS oder im Code\n"
            f"   den ``querySelector``-Aufruf bewusst entfernt halten.")


def test_03_drift_no_orphan_whitelist_entries() -> None:
    """Jeder Whitelist-Eintrag muss tatsaechlich im Patcher-Source als
    ``querySelector(...)``-Argument auftauchen. Faengt: Selektor wurde
    aus dem Code entfernt, Whitelist veraltet."""
    for fn, expected in PATCHER_SELECTORS.items():
        found = _selectors_in_func(fn)
        whitelist = set(expected)
        orphans = whitelist - found
        assert not orphans, (
            f"{fn}: Whitelist-Eintrag/-Eintraege nicht im Source verwendet: "
            f"{sorted(orphans)}.\n"
            f"   PATCHER_SELECTORS bereinigen.")


# == Test 4 — Render-Coverage (Whitelist <-> Render-Pfade) ==================

def test_04_render_coverage() -> None:
    """Jede Whitelist-Klasse (ausser DYNAMIC_ONLY) muss in mindestens
    einem Render-Pfad als statisches ``class="..."`` zu finden sein."""
    failures: list[str] = []
    for fn, selectors in PATCHER_SELECTORS.items():
        for sel in selectors:
            if sel in DYNAMIC_ONLY:
                continue
            # Compound-Selektor ".a, .b" -> akzeptiert wenn EINE Komponente
            # gefunden wird (Patcher matcht zur Laufzeit ohnehin nur eine).
            components = _classes_from_selector(sel)
            if not components:
                continue   # z. B. reines [attr] ohne Klasse
            any_hit = False
            checked_dynamic = sel in DYNAMIC_ONLY
            for cls in components:
                # Compound-Komponenten gegen DYNAMIC_ONLY pruefen (
                # ``.detail-st-row`` ist Teil keiner Compound, aber
                # robust bleiben).
                if "." + cls in DYNAMIC_ONLY:
                    checked_dynamic = True
                if _class_found_in_render(cls):
                    any_hit = True
                    break
            if not any_hit and not checked_dynamic:
                failures.append(
                    f"   {fn}: Selektor ``{sel}`` -> Klasse(n) "
                    f"{components} nirgends in Render-Pfaden gefunden")
    assert not failures, (
        "Render-Coverage-Luecken:\n" + "\n".join(failures))


# == Test 5 — Bekannte historische Mismatches regression-getestet ===========

def test_05_known_mismatches_fixed() -> None:
    """Faengt Re-Introduktion der Cockpit-Migrations-Bugs (PR #199 Folge)."""
    # Bug-A: renderAgentSignals push-silenced-Badge muss auch
    # Cockpit-Ticker-Block treffen.
    body = _func_block(GR_SRC, "function renderAgentSignals(")
    assert ".ticker-block, .cockpit-ticker-block" in body, (
        "Bug-A re-introduced: renderAgentSignals sucht nur ``.ticker-block``,"
        " Push-Silenced-Badge bleibt unsichtbar auf Cockpit-Top-10")

    # Bug-B: _refreshPositionPanel muss Cockpit-Price als Spot-Quelle
    # akzeptieren.
    body = _func_block(GR_SRC, "function _refreshPositionPanel(")
    assert ".price-tag, .cockpit-price" in body, (
        "Bug-B re-introduced: _refreshPositionPanel parst nur ``.price-tag``,"
        " Position-Panel-PnL fehlt fuer Top-10-Watchlist-Ticker")

    # Bug-Original (PR #229): _quotePatchScope muss Cockpit-Price
    # mit-patchen.
    body = _func_block(GR_SRC, "function _quotePatchScope(")
    assert ".price-tag, .cockpit-price" in body, (
        "Bug-Original re-introduced: _quotePatchScope updated nur "
        "``.price-tag``, Live-Polling-Kurs bleibt eingebrannt auf Cockpit")


# == Runner ==================================================================

def main() -> int:
    tests = [
        ("01 Patcher-Bodies extrahierbar",
         test_01_patcher_bodies_extractable),
        ("02 Drift: keine unbekannten Source-Selektoren",
         test_02_drift_no_unknown_selectors_in_source),
        ("03 Drift: keine verwaisten Whitelist-Eintraege",
         test_03_drift_no_orphan_whitelist_entries),
        ("04 Render-Coverage pro Whitelist-Klasse",
         test_04_render_coverage),
        ("05 Historische Mismatches behoben (Regression)",
         test_05_known_mismatches_fixed),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {name}:\n{exc}")
        except Exception as exc:
            failed += 1
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
    print()
    print(f"Total: {len(tests)} | Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
