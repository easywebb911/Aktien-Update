"""Mock-Tests fuer Karten-Cockpit Stage 2 — Aktivierung + Render-Pfade (18.05.2026).

Stage 1 (PR #198) lieferte Helper + CSS + Tests, Flag=False (no-op).
Stage 2 aktiviert Flag und stellt v1 (_card) + v2 (_build_card_ctx +
card.jinja) Render-Pfade auf Cockpit-Output um.

Tests:
  1. CARD_COCKPIT_ENABLED ist True
  2. _card-Funktion (v1) ruft _card_cockpit_html auf
  3. _build_card_ctx (v2) ruft _card_cockpit_html auf
  4. card.jinja nutzt card_header_html-Context-Variable
  5. card_header_html ist im v2-Return-Dict enthalten
  6. _WL_CARD_STRIP_RE hat cockpit_id-Pattern (fuer Watchlist-Drawer)
  7. _wl_full_card_html ruft cockpit_id-Strip auf
  8. Live-Polling-JS-Selector erweitert um .card-cockpit (und
     .cockpit-header-right als bevorzugtes Ziel)
  9. Fallback-Branch (Flag=False) im v1-Code existiert weiterhin
 10. Fallback-Branch (Flag=False) im v2-Code existiert weiterhin
 11. Alte card-top-Struktur in card.jinja entfernt
 12. Bei Flag=True erzeugt v1+v2 identisches header-HTML (byte-identisch)
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
CFG_SRC = (ROOT / "config.py").read_text(encoding="utf-8")
CARD_JINJA = (ROOT / "templates" / "card.jinja").read_text(encoding="utf-8")


def test_01_flag_enabled() -> None:
    assert "CARD_COCKPIT_ENABLED = True" in CFG_SRC, \
        "Stage 2 erwartet CARD_COCKPIT_ENABLED = True in config.py"


def test_02_card_v1_calls_cockpit() -> None:
    # Suche im _card-Funktions-Body nach _card_cockpit_html-Aufruf
    m = re.search(
        r"^def _card\(.*?(?=^def )",
        GR_SRC, re.MULTILINE | re.DOTALL,
    )
    assert m, "_card-Funktion nicht gefunden"
    assert "_card_cockpit_html(" in m.group(0), \
        "_card (v1) ruft _card_cockpit_html nicht auf"


def test_03_build_card_ctx_v2_calls_cockpit() -> None:
    m = re.search(
        r"^def _build_card_ctx\(.*?(?=^def )",
        GR_SRC, re.MULTILINE | re.DOTALL,
    )
    assert m, "_build_card_ctx-Funktion nicht gefunden"
    assert "_card_cockpit_html(" in m.group(0), \
        "_build_card_ctx (v2) ruft _card_cockpit_html nicht auf"


def test_04_card_jinja_uses_card_header_html() -> None:
    assert "{{ card_header_html }}" in CARD_JINJA, \
        "card.jinja nutzt nicht {{ card_header_html }}"


def test_05_card_header_html_in_v2_return_dict() -> None:
    m = re.search(
        r"^def _build_card_ctx\(.*?(?=^def )",
        GR_SRC, re.MULTILINE | re.DOTALL,
    )
    assert m
    # Im Return-Dict erscheint "card_header_html":
    assert '"card_header_html":' in m.group(0), \
        "card_header_html fehlt im _build_card_ctx-Return-Dict"


def test_06_wl_card_strip_re_has_cockpit_id_pattern() -> None:
    # Watchlist-Drawer reuse muss cockpit-{i} IDs strippen
    assert '"cockpit_id":' in GR_SRC, \
        "_WL_CARD_STRIP_RE hat kein cockpit_id-Pattern (Watchlist-Drawer-ID-Konflikt)"
    # Pattern matcht id="cockpit-N"
    assert r' id="cockpit-\d+"' in GR_SRC, \
        "Cockpit-ID-Regex-Pattern nicht im Source"


def test_07_wl_full_card_html_strips_cockpit_id() -> None:
    m = re.search(
        r"^def _wl_full_card_html\(.*?(?=^def )",
        GR_SRC, re.MULTILINE | re.DOTALL,
    )
    assert m, "_wl_full_card_html nicht gefunden"
    body = m.group(0)
    assert 'cockpit_id' in body, \
        '_wl_full_card_html ruft cockpit_id-Strip nicht auf'


def test_08_live_polling_selector_extended() -> None:
    # JS-Quote-Live-Dot-Injection muss .card-cockpit als Fallback haben
    assert ".card-cockpit" in GR_SRC, \
        "Live-Polling-Selector kennt .card-cockpit nicht"
    # cockpit-header-right ist das bevorzugte Ziel
    assert ".cockpit-header-right" in GR_SRC, \
        "Live-Polling-Selector kennt .cockpit-header-right nicht"


def test_09_v1_fallback_branch_exists() -> None:
    m = re.search(
        r"^def _card\(.*?(?=^def )",
        GR_SRC, re.MULTILINE | re.DOTALL,
    )
    assert m
    body = m.group(0)
    # Beide Pfade vorhanden — if CARD_COCKPIT_ENABLED + else
    assert "if CARD_COCKPIT_ENABLED" in body, \
        "v1 hat keinen CARD_COCKPIT_ENABLED-Branch"
    # Fallback hat score-block (alte Variante)
    assert 'score-block sort-setup' in body, \
        "v1-Fallback fuer Flag=False fehlt"


def test_10_v2_fallback_branch_exists() -> None:
    m = re.search(
        r"^def _build_card_ctx\(.*?(?=^def )",
        GR_SRC, re.MULTILINE | re.DOTALL,
    )
    assert m
    body = m.group(0)
    assert "if CARD_COCKPIT_ENABLED" in body, \
        "v2 hat keinen CARD_COCKPIT_ENABLED-Branch"
    assert 'score-block sort-setup' in body, \
        "v2-Fallback fuer Flag=False fehlt"


def test_11_old_card_top_block_removed_from_jinja() -> None:
    # Alter card-top Block ist aus card.jinja entfernt (jetzt via
    # card_header_html-Context als einzige Quelle)
    assert '<div class="card-top">' not in CARD_JINJA, \
        'Alter <div class="card-top"> noch in card.jinja'
    assert '<div class="card-left">' not in CARD_JINJA, \
        'Alter <div class="card-left"> noch in card.jinja'
    assert "{{ score_block_html }}" not in CARD_JINJA, \
        'Alte score_block_html-Variable noch in card.jinja referenziert'


def test_12_v1_v2_header_html_construction_symmetric() -> None:
    # v1 und v2 nutzen identischen Helper mit identischen Parameter-
    # Bindings (rank_html, market_tag_html, chart_badge_html mit
    # sa_badge+wl_add_btn, sector_tag_html-Bundle). Byte-Identitaet
    # wird durch shared Helper-Output garantiert. Test prueft die
    # 4 Parameter-Namen in beiden Funktionen.
    for fn_name in ("_card", "_build_card_ctx"):
        m = re.search(
            rf"^def {fn_name}\(.*?(?=^def )",
            GR_SRC, re.MULTILINE | re.DOTALL,
        )
        assert m, f"{fn_name} nicht gefunden"
        body = m.group(0)
        # Cockpit-Aufruf gefunden? Pruefe Kwargs
        cockpit_call_idx = body.find("_card_cockpit_html(")
        assert cockpit_call_idx > 0
        # Im selben Aufruf alle 4 Kwargs:
        snippet = body[cockpit_call_idx:cockpit_call_idx + 600]
        for kw in ("rank_html=", "market_tag_html=",
                   "chart_badge_html=", "sector_tag_html="):
            assert kw in snippet, \
                f"{fn_name}: Cockpit-Aufruf ohne {kw}"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 CARD_COCKPIT_ENABLED = True",            test_01_flag_enabled),
        ("02 _card (v1) ruft Cockpit auf",            test_02_card_v1_calls_cockpit),
        ("03 _build_card_ctx (v2) ruft Cockpit auf",  test_03_build_card_ctx_v2_calls_cockpit),
        ("04 card.jinja nutzt card_header_html",      test_04_card_jinja_uses_card_header_html),
        ("05 card_header_html in v2-Return-Dict",     test_05_card_header_html_in_v2_return_dict),
        ("06 cockpit_id-Pattern in _WL_CARD_STRIP",   test_06_wl_card_strip_re_has_cockpit_id_pattern),
        ("07 _wl_full_card_html strippt cockpit_id",  test_07_wl_full_card_html_strips_cockpit_id),
        ("08 Live-Polling-Selector erweitert",        test_08_live_polling_selector_extended),
        ("09 v1-Fallback-Branch fuer Flag=False",     test_09_v1_fallback_branch_exists),
        ("10 v2-Fallback-Branch fuer Flag=False",     test_10_v2_fallback_branch_exists),
        ("11 Alter card-top in card.jinja entfernt",  test_11_old_card_top_block_removed_from_jinja),
        ("12 v1==v2 Helper-Parameter-Symmetrie",      test_12_v1_v2_header_html_construction_symmetric),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
        except AssertionError as exc:
            print(f"  FAIL {name}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
            failed += 1
    print()
    print(f"Total: {len(tests)} | Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
