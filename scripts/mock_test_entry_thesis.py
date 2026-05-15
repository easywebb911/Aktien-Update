"""Mock-Tests für Trade-Journal-Eröffnungs-Begründung (15.05.2026).

Auftrag: User-Notiz beim Eröffnen erfassen, beim Schließen automatisch
in die thesis-Textarea pre-fillen — Easy verliert die Trade-Details
zwischen Eröffnen und Schließen nicht mehr.

Plus 5 neue Auto-Snapshot-Felder beim Position-Open:
  entry_monster_score, entry_ki_score, entry_rvol, entry_si_trend,
  entry_conviction_components.

Tests:
  1. Open-Form rendert pos-thesis-Textarea mit maxlength=500
  2. _cacheOpenFormFields-Helper existiert + persistiert entry_thesis
  3. Open-Form-Render konsumiert _formState.entry_thesis (Bug-A)
  4. wlSubmitPosition liest pos-thesis und schreibt entry_thesis
     (mit slice(0, 500))
  5. wlSubmitPosition Validation-Fail ruft _cacheOpenFormFields auf
  6. wlSubmitPosition Success ruft _setPanelFormState(null) auf
     (Cache verwerfen)
  7. 5 neue Score-Snapshot-Felder mit Null-Checks
  8. Close-Form pos-th-Initial-Value: Cache > entry_thesis > ''
  9. XSS-Schutz: _escAttr auf entry_thesis Pre-Fill
 10. Pythonische Replikation: 4 Pre-Fill-Szenarien

  + Vorsichts-Prinzip:
    - closed_trades-Schema unverändert
    - Open-Form-Felder Datum/Preis/Stueck unverändert
    - existing 7+ Snapshot-Felder unangetastet
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _wl_iife_block() -> str:
    """Extrahiere den Watchlist-IIFE-Block (enthaelt buildPositionPanel
    + wlSubmitPosition + wlSubmitClose + _cache-Helper)."""
    start = SRC.find("function buildPositionPanel(")
    assert start > 0
    # IIFE-Ende: nächstes ``}})();`` nach 11000 Zeilen
    end_anchor = "// ── Claude / Anthropic API"
    end = SRC.find(end_anchor, start)
    assert end > start
    return SRC[start:end]


def _open_form_block() -> str:
    block = _wl_iife_block()
    open_idx = block.find("if (mode === 'open-form')")
    assert open_idx > 0, "open-form-Block nicht gefunden"
    close_idx = block.find("if (mode === 'close-form')", open_idx)
    if close_idx < 0:
        close_idx = open_idx + 3500
    return block[open_idx:close_idx]


def _submit_position_block() -> str:
    block = _wl_iife_block()
    s = block.find("window.wlSubmitPosition")
    e = block.find("// Trade-Journal: max Setup-Score", s)
    assert s > 0 and e > s
    return block[s:e]


def _close_form_block() -> str:
    block = _wl_iife_block()
    open_close = block.find("if (mode === 'close-form')")
    if open_close < 0:
        # alternative: where _thInit appears
        open_close = block.find("_thInit")
        assert open_close > 0
        open_close = block.rfind("\n", 0, open_close - 200)
    open_form = block.find("if (mode === 'open-form')", open_close)
    return block[open_close:open_form]


# === 1 — Open-Form rendert pos-thesis-Textarea ============================


def test_open_form_renders_pos_thesis_textarea():
    block = _open_form_block()
    assert 'id="pos-thesis-${{ticker}}"' in block, (
        "pos-thesis-Textarea fehlt im open-form-Render")


def test_open_form_textarea_has_maxlength_500():
    block = _open_form_block()
    pat = re.compile(
        r'<textarea[^>]*id="pos-thesis-\$\{\{ticker\}\}"[^>]*maxlength="500"',
        re.DOTALL,
    )
    assert pat.search(block), (
        "pos-thesis-Textarea hat kein maxlength=500 (Soft-Limit)")


def test_open_form_textarea_has_helpful_placeholder():
    block = _open_form_block()
    # Pruefe Placeholder-Schluesselwoerter (Trigger, Verlauf, Pre-Fill-Hinweis)
    assert "Trigger" in block
    assert "Setup" in block
    assert "vorbef" in block, (   # vorbefüllt mit u-umlaut
        "Placeholder erwaehnt nicht die Pre-Fill-Mechanik")


def test_open_form_textarea_position_before_buttons():
    """Textarea steht vor den Submit-Buttons (UX: Felder → Begruendung → Buttons)."""
    block = _open_form_block()
    idx_textarea = block.find('id="pos-thesis-')
    idx_buttons  = block.find('pos-form-btns')
    assert 0 < idx_textarea < idx_buttons, (
        "Textarea muss vor pos-form-btns stehen")


def test_open_form_textarea_after_stueckzahl():
    """UX-Ordnung: Datum → Preis → Stueckzahl → Total → Textarea."""
    block = _open_form_block()
    idx_stueck   = block.find('id="pos-s-')
    idx_textarea = block.find('id="pos-thesis-')
    assert 0 < idx_stueck < idx_textarea, (
        "Textarea muss nach Stueckzahl stehen")


# === 2 — _cacheOpenFormFields-Helper =====================================


def test_cache_open_form_fields_exists():
    block = _wl_iife_block()
    assert "function _cacheOpenFormFields(ticker)" in block, (
        "_cacheOpenFormFields-Helper fehlt")


def test_cache_open_form_persists_entry_thesis():
    block = _wl_iife_block()
    pat = re.compile(
        r"function _cacheOpenFormFields\(ticker\)\s*\{\{.*?"
        r"_setPanelFormState\(ticker,\s*\{\{[^}]*entry_thesis",
        re.DOTALL,
    )
    assert pat.search(block), (
        "_cacheOpenFormFields persistiert entry_thesis nicht")


def test_open_form_consumes_cached_entry_thesis():
    """Open-Form-Render liest _formState.entry_thesis fuer Bug-A-Recovery."""
    block = _open_form_block()
    assert "_openState.entry_thesis" in block, (
        "Open-Form konsumiert _formState.entry_thesis nicht — "
        "Validation-Fail wuerde User-Tippen verlieren")


def test_open_form_pre_fill_escaped():
    """_escAttr verhindert </textarea>-Injection auf User-Eingabe."""
    block = _open_form_block()
    pat = re.compile(r"_escAttr\(_openState\.entry_thesis")
    assert pat.search(block), "Pre-Fill wird nicht via _escAttr escaped"


# === 3 — wlSubmitPosition: thesis lesen + persistieren ===================


def test_submit_reads_pos_thesis_value():
    block = _submit_position_block()
    pat = re.compile(
        r"document\.getElementById\(\s*['\"]pos-thesis-['\"]\s*\+\s*ticker\s*\)",
    )
    assert pat.search(block), (
        "wlSubmitPosition liest pos-thesis-Element nicht")


def test_submit_writes_entry_thesis_field():
    block = _submit_position_block()
    assert "_newPos.entry_thesis" in block, (
        "wlSubmitPosition schreibt entry_thesis nicht")


def test_submit_trims_and_slices_entry_thesis():
    """User-Input wird getrimmt und auf 500 Zeichen geschnitten."""
    block = _submit_position_block()
    assert ".trim()" in block
    assert ".slice(0, 500)" in block, (
        "Server-side-Schutz: thesis ueber maxlength=500 hinaus schneiden")


def test_submit_validation_fail_caches_entry_thesis():
    """Bei Validation-Fail wird der bisherige Tipper-Stand persistiert."""
    block = _submit_position_block()
    # Validation-Fail-Block enthaelt _cacheOpenFormFields
    pat = re.compile(
        r"if \(!date \|\| !isFinite\(price\).*?_cacheOpenFormFields\(ticker\)",
        re.DOTALL,
    )
    assert pat.search(block), (
        "Validation-Fail-Pfad ruft _cacheOpenFormFields nicht — "
        "User verliert thesis-Tippen bei Re-Render")


def test_submit_success_clears_cache():
    """Bei erfolgreichem Save wird der Cache verworfen (kein Verschmutzen
    der naechsten Position)."""
    block = _submit_position_block()
    # Success-Block enthaelt _setPanelFormState(ticker, null)
    pat = re.compile(
        r"_setPanelMode\(ticker, 'view'\).*?"
        r"_setPanelFormState\(ticker, null\)",
        re.DOTALL,
    )
    assert pat.search(block), (
        "Success-Block verwirft Open-Form-Cache nicht — Folge-Position "
        "wuerde alten thesis-Wert sehen")


# === 4 — 5 neue Score-Snapshot-Felder mit Null-Checks ====================


def test_snapshot_entry_monster_score():
    block = _submit_position_block()
    assert "_newPos.entry_monster_score" in block
    # Quelle = monster_scores[ticker]
    assert "monster_scores[ticker]" in block, (
        "entry_monster_score liest nicht aus _APP_DATA.monster_scores")
    # Null-Check
    pat = re.compile(
        r"typeof _entryMonster === 'number'.*?_newPos\.entry_monster_score",
        re.DOTALL,
    )
    assert pat.search(block), "entry_monster_score Null-Check fehlt"


def test_snapshot_entry_ki_score():
    block = _submit_position_block()
    assert "_newPos.entry_ki_score" in block
    assert "ki_signal_score" in block, "Quelle .ki_signal_score nicht referenziert"


def test_snapshot_entry_rvol():
    block = _submit_position_block()
    assert "_newPos.entry_rvol" in block
    # Quelle = watchlist_cards.rel_volume
    pat = re.compile(r"_wlCard\.rel_volume")
    assert pat.search(block), "rel_volume-Quelle nicht referenziert"


def test_snapshot_entry_si_trend():
    block = _submit_position_block()
    assert "_newPos.entry_si_trend" in block
    pat = re.compile(r"_wlCard\.si_trend")
    assert pat.search(block)


def test_snapshot_entry_conviction_components():
    block = _submit_position_block()
    assert "_newPos.entry_conviction_components" in block
    # Sub-Objekt enthaelt die 4 Komponenten
    for k in ("setup", "earliness", "anomaly", "regime"):
        assert f"_c.{k}" in block, (
            f"Conviction-Komponente {k} nicht im Snapshot")


def test_snapshot_components_only_if_complete():
    """Sub-Objekt wird nur geschrieben, wenn mind. 1 Komponente vorhanden
    (kein leeres Dict im Gist)."""
    block = _submit_position_block()
    assert "Object.keys(_comp).length > 0" in block


# === 5 — Close-Form Pre-Fill aus pos.entry_thesis ========================


def test_close_form_th_init_falls_back_to_entry_thesis():
    block = _close_form_block()
    assert "_formState.thesis" in block
    # Cache (Vorrang) || entry_thesis (Pre-Fill) || ''
    pat = re.compile(
        r"_formState\.thesis\s*\n?\s*\|\|\s*\(pos && pos\.entry_thesis\)",
        re.DOTALL,
    )
    assert pat.search(block), (
        "Close-Form _thInit fallt nicht auf pos.entry_thesis zurueck — "
        "Pre-Fill funktioniert nicht")


def test_close_form_pre_fill_escaped():
    """_escAttr wickelt den gesamten Fallback-Ausdruck (XSS-Schutz fuer
    pos.entry_thesis aus dem Gist)."""
    block = _close_form_block()
    pat = re.compile(
        r"_thInit\s*=\s*_escAttr\(\s*\n?\s*_formState\.thesis",
        re.DOTALL,
    )
    assert pat.search(block), (
        "_thInit wird nicht durch _escAttr gewickelt — XSS-Risiko")


# === 6 — Pythonische Replikation: 4 Pre-Fill-Szenarien ===================


def _resolve_thesis_init(form_state: dict, pos: dict | None) -> str:
    """Replikat der Close-Form-_thInit-Logik."""
    cache = form_state.get("thesis") if form_state else None
    entry_thesis = pos.get("entry_thesis") if pos else None
    return cache or entry_thesis or ""


def test_replicate_pre_fill_from_entry_thesis():
    pos = {"entry_thesis": "13D-Filing + DTC 12"}
    assert _resolve_thesis_init({}, pos) == "13D-Filing + DTC 12"


def test_replicate_pre_fill_cache_overrides():
    """Cache hat Vorrang vor entry_thesis (Bug-A: User hat schon getippt)."""
    pos = {"entry_thesis": "Original-Notiz"}
    cache = {"thesis": "User-Edit beim Schliessen"}
    assert _resolve_thesis_init(cache, pos) == "User-Edit beim Schliessen"


def test_replicate_pre_fill_empty_for_legacy_positions():
    """Bestandspositionen ohne entry_thesis → leerer Pre-Fill."""
    pos = {"entry_date": "2026-05-10"}   # kein entry_thesis-Feld
    assert _resolve_thesis_init({}, pos) == ""


def test_replicate_pre_fill_empty_when_pos_missing():
    """Defensiv: pos kann None sein (theoretisch, sollte nicht vorkommen)."""
    assert _resolve_thesis_init({}, None) == ""


# === 7 — Vorsichts-Prinzip ===============================================


def test_closed_trades_schema_unchanged():
    """wlSubmitClose schreibt closed_trades — Schema unangetastet.
    Heuristik: kein 'closed_trades.push' enthaelt entry_thesis (das
    bleibt in positions, nicht in closed_trades)."""
    block = _wl_iife_block()
    close_block_start = block.find("data.closed_trades.push(")
    assert close_block_start > 0
    # Suche bis zum Ende des push-Calls (matching brace)
    depth = 0
    i = close_block_start
    end = i
    while i < len(block):
        c = block[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    push_call = block[close_block_start:end]
    assert "entry_thesis" not in push_call, (
        "closed_trades.push enthaelt entry_thesis — Schema unbeabsichtigt "
        "erweitert (Vorsichts-Prinzip verletzt)")


def test_open_form_keeps_existing_3_fields():
    """Datum/Einstiegskurs/Stueckzahl-Felder bleiben unangetastet."""
    block = _open_form_block()
    assert 'id="pos-d-${{ticker}}"' in block
    assert 'id="pos-p-${{ticker}}"' in block
    assert 'id="pos-s-${{ticker}}"' in block


def test_existing_snapshot_fields_intact():
    """Die 7+ existierenden Snapshot-Felder bleiben unangetastet."""
    block = _submit_position_block()
    for field in ("_newPos.entry_score", "_newPos.entry_conviction_score",
                  "_newPos.entry_dtc", "_newPos.entry_short_float",
                  "_newPos.entry_cost_to_borrow", "_newPos.entry_snapshot_ts",
                  "_newPos.entry_fx"):
        assert field in block, f"existing Snapshot-Feld {field} ist verschwunden"


def test_entry_snapshot_ts_covers_new_fields():
    """entry_snapshot_ts wird auch gesetzt, wenn nur die NEUEN Felder
    (ki/rvol/trend) erfolgreich gesnapshottet wurden."""
    block = _submit_position_block()
    # Prüfe dass _ki/_rv/_trend in der entry_snapshot_ts-Bedingung stehen
    pat = re.compile(
        r"if \(_dtc != null.*?_ki != null.*?_rv != null.*?_trend != null\)\s*\{\{[^}]*entry_snapshot_ts",
        re.DOTALL,
    )
    assert pat.search(block), (
        "entry_snapshot_ts beruecksichtigt die neuen Snapshot-Felder nicht")


# === 8 — JS-Template-Pflichtcheck ========================================


def test_no_unescaped_js_template_vars():
    hits = re.findall(r"\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}", SRC)
    assert not hits, f"Unescapte JS-Template-Vars: {hits[:5]}"


# === Runner ==============================================================


def main() -> None:
    tests = [
        # Open-Form
        ("Open-Form rendert pos-thesis-Textarea",          test_open_form_renders_pos_thesis_textarea),
        ("Textarea hat maxlength=500",                       test_open_form_textarea_has_maxlength_500),
        ("Placeholder erwaehnt Pre-Fill",                    test_open_form_textarea_has_helpful_placeholder),
        ("Textarea vor Submit-Buttons",                       test_open_form_textarea_position_before_buttons),
        ("Textarea nach Stueckzahl",                         test_open_form_textarea_after_stueckzahl),
        # _cacheOpenFormFields
        ("_cacheOpenFormFields-Helper exists",                test_cache_open_form_fields_exists),
        ("_cacheOpenFormFields persistiert entry_thesis",    test_cache_open_form_persists_entry_thesis),
        ("Open-Form konsumiert _formState.entry_thesis",     test_open_form_consumes_cached_entry_thesis),
        ("Open-Form Pre-Fill escaped via _escAttr",           test_open_form_pre_fill_escaped),
        # wlSubmitPosition
        ("Submit liest pos-thesis-Element",                   test_submit_reads_pos_thesis_value),
        ("Submit schreibt entry_thesis",                      test_submit_writes_entry_thesis_field),
        ("Submit trim + slice(0,500)",                         test_submit_trims_and_slices_entry_thesis),
        ("Validation-Fail ruft _cacheOpenFormFields",         test_submit_validation_fail_caches_entry_thesis),
        ("Success verwirft Open-Form-Cache",                  test_submit_success_clears_cache),
        # 5 Snapshot-Felder
        ("entry_monster_score + Null-Check",                  test_snapshot_entry_monster_score),
        ("entry_ki_score + Quelle",                          test_snapshot_entry_ki_score),
        ("entry_rvol + Quelle",                              test_snapshot_entry_rvol),
        ("entry_si_trend + Quelle",                          test_snapshot_entry_si_trend),
        ("entry_conviction_components Sub-Objekt",            test_snapshot_entry_conviction_components),
        ("Components nur bei n > 0 geschrieben",              test_snapshot_components_only_if_complete),
        # Close-Form Pre-Fill
        ("Close-Form _thInit faellt auf entry_thesis",        test_close_form_th_init_falls_back_to_entry_thesis),
        ("Close-Form Pre-Fill escaped",                       test_close_form_pre_fill_escaped),
        # Pythonische Replikation
        ("Pre-Fill aus entry_thesis",                         test_replicate_pre_fill_from_entry_thesis),
        ("Cache ueberschreibt Pre-Fill",                      test_replicate_pre_fill_cache_overrides),
        ("Bestandsposition ohne entry_thesis → leer",         test_replicate_pre_fill_empty_for_legacy_positions),
        ("Defensiv: pos=None → leer",                         test_replicate_pre_fill_empty_when_pos_missing),
        # Vorsichts-Prinzip
        ("closed_trades-Schema unveraendert",                  test_closed_trades_schema_unchanged),
        ("Open-Form 3 Felder unangetastet",                    test_open_form_keeps_existing_3_fields),
        ("Existing 7 Snapshot-Felder intakt",                  test_existing_snapshot_fields_intact),
        ("entry_snapshot_ts deckt neue Felder ab",             test_entry_snapshot_ts_covers_new_fields),
        # Pflichtcheck
        ("Keine unescapten ${...} im f-String",              test_no_unescaped_js_template_vars),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {name}\n      {exc}")
        except Exception as exc:
            failed += 1
            print(f"  ✗ {name}\n      Unexpected: {type(exc).__name__}: {exc}")
    print()
    if failed:
        print(f"{failed} Test(s) fehlgeschlagen.")
        sys.exit(1)
    print(f"{len(tests)} Tests bestanden.")
    sys.exit(0)


if __name__ == "__main__":
    main()
