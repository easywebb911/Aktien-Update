"""Mock-Tests für Option C — Session-Wrap via IndexedDB (Token Re-Encrypt
mit 7-Tage-Rolling-Window).

Pattern: Source-Inspection (JS lebt im Jinja-f-String von generate_report.py,
keine JS-Test-Runtime im Projekt). Tests verifizieren Struktur, Andock-
Punkte, Fail-soft-Pattern und Schema-Disziplin.

Verifiziert:
- IndexedDB-Layer (_idbOpen / _idbGetRecord / _idbPutRecord / _idbDeleteRecord)
  vorhanden, alle 4 fail-soft (Promise-Wrapper mit catch).
- _persistSessionWrap + _tryUnwrapSessionToken vorhanden, fire-and-forget,
  fail-soft.
- _ensureToken ruft _tryUnwrapSessionToken VOR _showModal — async-Trampolin.
- _setSessionToken ruft _persistSessionWrap fire-and-forget.
- _clearAllTokens loescht IndexedDB-Record (kein Geist-Session).
- 7-Tage-Konstante hartkodiert.
- Fail-soft-Pattern: Promise-Catch + null-Fallback.
- Master-PW-Anker unveraendert (_hasEncryptedToken-Pfad bleibt).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")


# ── 1) Konstanten ──────────────────────────────────────────────────────────


def test_01_constants_present():
    """Alle 4 Session-Wrap-Konstanten + Window = 7*24*60*60*1000 ms."""
    assert "const _SESSION_WRAP_DB_NAME" in SRC, "_SESSION_WRAP_DB_NAME fehlt"
    assert "const _SESSION_WRAP_STORE" in SRC, "_SESSION_WRAP_STORE fehlt"
    assert "const _SESSION_WRAP_KEY" in SRC, "_SESSION_WRAP_KEY fehlt"
    assert "const _SESSION_WRAP_WINDOW_MS" in SRC, "_SESSION_WRAP_WINDOW_MS fehlt"
    # 7-Tage-Fenster (NICHT 30 — ITP-Realismus, dokumentiert)
    assert "7 * 24 * 60 * 60 * 1000" in SRC, \
        "7-Tage-Window-Konstante fehlt (Diagnose 30.05.: kein 30-Tage-Versprechen)"


# ── 2) IndexedDB-Layer ─────────────────────────────────────────────────────


def test_02_idb_layer_four_helpers_present():
    """4 fail-soft Promise-Wrapper-Helper vorhanden."""
    for fn in ("_idbOpen", "_idbGetRecord", "_idbPutRecord", "_idbDeleteRecord"):
        assert f"function {fn}(" in SRC, f"{fn} fehlt"


def test_03_idb_open_fail_soft():
    """_idbOpen returnt null bei Fehler/blocked statt zu throwen."""
    body_start = SRC.index("function _idbOpen()")
    body_end   = SRC.index("function _idbGetRecord()", body_start)
    body = SRC[body_start:body_end]
    assert "resolve(null)" in body, "_idbOpen muss null-Fallback haben"
    assert "req.onerror" in body and "req.onblocked" in body, \
        "_idbOpen muss onerror UND onblocked-Pfade haben"
    assert "typeof indexedDB === 'undefined'" in body, \
        "_idbOpen muss IndexedDB-Verfuegbarkeit pruefen"


# ── 3) Wrap/Unwrap-Mechanik ────────────────────────────────────────────────


def test_04_persist_and_unwrap_present():
    """_persistSessionWrap + _tryUnwrapSessionToken vorhanden, async."""
    assert "async function _persistSessionWrap(tok)" in SRC
    assert "async function _tryUnwrapSessionToken()" in SRC


def test_05_persist_uses_random_key_not_pbkdf2():
    """Session-Key ist random (crypto.getRandomValues), KEIN PBKDF2
    (kein User-Passwort)."""
    body_start = SRC.index("async function _persistSessionWrap(tok)")
    body_end   = SRC.index("async function _tryUnwrapSessionToken()")
    body = SRC[body_start:body_end]
    assert "crypto.getRandomValues" in body, \
        "_persistSessionWrap muss random Key generieren"
    assert "PBKDF2" not in body, \
        "_persistSessionWrap darf KEIN PBKDF2 nutzen (kein User-PW)"
    assert "AES-GCM" in body, "AES-GCM-Krypto muss da sein"


def test_06_unwrap_checks_expires_at():
    """_tryUnwrapSessionToken prueft expires_at_ms vor decrypt."""
    body_start = SRC.index("async function _tryUnwrapSessionToken()")
    # bis zum naechsten Top-Level-Funktions-Start
    body_end   = SRC.index("\n// ──", body_start)
    body = SRC[body_start:body_end]
    assert "expires_at_ms" in body, "Ablauf-Check fehlt"
    assert "Date.now() >=" in body, "now-Vergleich gegen expires_at_ms fehlt"


def test_07_unwrap_rolling_refresh():
    """Bei erfolgreichem Unwrap wird _persistSessionWrap fuer Rolling-
    Refresh aufgerufen (frischer Wrap, neue expires_at_ms)."""
    body_start = SRC.index("async function _tryUnwrapSessionToken()")
    body_end   = SRC.index("\n// ──", body_start)
    body = SRC[body_start:body_end]
    assert "_persistSessionWrap(tok)" in body, \
        "Rolling-Refresh via _persistSessionWrap fehlt"


def test_08_unwrap_deletes_record_on_expire_or_fail():
    """Bei Ablauf oder Decrypt-Fehler wird Record entsorgt."""
    body_start = SRC.index("async function _tryUnwrapSessionToken()")
    body_end   = SRC.index("\n// ──", body_start)
    body = SRC[body_start:body_end]
    assert body.count("_idbDeleteRecord()") >= 2, \
        "_tryUnwrapSessionToken muss Record bei Ablauf UND Fail entsorgen"


# ── 4) Andock-Punkte (vier kritische Stellen) ──────────────────────────────


def test_09_ensure_token_async_trampoline_before_modal():
    """_ensureToken ruft _tryUnwrapSessionToken VOR _showModal-Pfaden."""
    body_start = SRC.index("function _ensureToken(callback)")
    body_end   = SRC.index("\nfunction _showModalErr", body_start)
    body = SRC[body_start:body_end]
    # Trampolin vor allen Modal-Pfaden
    pos_trampolin = body.find("_tryUnwrapSessionToken")
    pos_unlock    = body.find("'tok-modal-unlock'")
    assert pos_trampolin > 0, "Trampolin fehlt in _ensureToken"
    assert pos_trampolin < pos_unlock, \
        "_tryUnwrapSessionToken muss VOR unlock-Modal stehen"


def test_10_ensure_token_signature_unchanged():
    """_ensureToken bleibt synchron (kein async), Aufrufer-Signatur intakt."""
    assert "function _ensureToken(callback)" in SRC
    assert "async function _ensureToken" not in SRC, \
        "_ensureToken darf NICHT async werden — Aufrufer-Signatur unveraendert"


def test_11_ensure_token_fail_soft_catch():
    """Async-Trampolin hat .catch fuer Fail-soft auf Modal-Pfad."""
    body_start = SRC.index("function _ensureToken(callback)")
    body_end   = SRC.index("\nfunction _showModalErr", body_start)
    body = SRC[body_start:body_end]
    assert ".catch(e =>" in body, "Trampolin-Catch fehlt (Fail-soft)"
    # Im Catch-Branch muessen alle 3 Modal-Pfade da sein (unlock/migrate/setup)
    catch_idx = body.index(".catch(e =>")
    catch_body = body[catch_idx:]
    assert "tok-modal-unlock" in catch_body
    assert "tok-modal-migrate" in catch_body
    assert "tok-modal-setup" in catch_body


def test_12_set_session_token_fires_persist():
    """_setSessionToken ruft _persistSessionWrap fire-and-forget."""
    body_start = SRC.index("function _setSessionToken(tok)")
    body_end   = SRC.index("function _clearSessionToken()")
    body = SRC[body_start:body_end]
    assert "_persistSessionWrap(tok)" in body, \
        "_setSessionToken muss _persistSessionWrap aufrufen"
    assert ".catch(() => null)" in body, \
        "_setSessionToken-Call muss fire-and-forget catch haben"


def test_13_clear_all_tokens_deletes_idb():
    """_clearAllTokens loescht IndexedDB-Record (kein Geist-Session)."""
    body_start = SRC.index("function _clearAllTokens()")
    body_end   = SRC.index("\n// ── Soft-Reset", body_start)
    body = SRC[body_start:body_end]
    assert "_idbDeleteRecord()" in body, \
        "_clearAllTokens muss IndexedDB-Record loeschen (Geist-Session-Schutz)"


# ── 5) Defensive / Race / Master-PW-Anker ─────────────────────────────────


def test_14_pending_callback_guard_present():
    """Defensive _tokPending-Guard verhindert Slot-Ueberschreiben."""
    body_start = SRC.index("function _ensureToken(callback)")
    body_end   = SRC.index("\nfunction _showModalErr", body_start)
    body = SRC[body_start:body_end]
    assert "if (!_tokPending) _tokPending = callback" in body, \
        "_tokPending-Single-Slot-Guard fehlt"


def test_15_master_pw_anchor_unchanged():
    """_hasEncryptedToken (Master-PW-Anker) bleibt unveraendert in Form."""
    assert "function _hasEncryptedToken()" in SRC
    # PBKDF2-600k bleibt fuer Master-PW
    assert "const _TOK_PBKDF2_ITER = 600000" in SRC, \
        "Master-PW-PBKDF2 muss unveraendert bleiben"


def test_16_no_30_day_promise_in_code():
    """Kein 30-Tage-Versprechen im Code-Kommentar (Diagnose 30.05.:
    iOS-ITP-Realismus = max 7 Tage)."""
    # Sucht nach 30-Tage-Versprechen IM SESSION-WRAP-BEREICH (anderswo
    # ist 30 ok, z.B. 30 Tage Score-Inflation-Bereinigung)
    block_start = SRC.index("// ── Session-Wrap (IndexedDB")
    block_end   = SRC.index("\n// ── Diagnose-Build", block_start)
    block = SRC[block_start:block_end]
    assert "30 * 24" not in block, "Kein 30-Tage-Window im Session-Wrap"
    assert "30 Tage" not in block, "Keine 30-Tage-Versprechen im Kommentar"
    assert "7-Tage" in block or "7 Tage" in block, \
        "7-Tage-Window muss als ehrliche Spec im Kommentar stehen"


# ── 6) Schema / Diagnose-Verweis ───────────────────────────────────────────


def test_17_diagnosis_reference_in_comment():
    """Code-Kommentar verweist auf Diagnose 30.05. und ITP-Konsequenz."""
    block_start = SRC.index("// ── Session-Wrap (IndexedDB")
    block_end   = SRC.index("\n// ── Diagnose-Build", block_start)
    block = SRC[block_start:block_end]
    assert "30.05.2026" in block, "Diagnose-Datum fehlt"
    assert "ITP" in block or "7d Inaktivit" in block, \
        "ITP-Hintergrund muss erklaert sein"
    assert "_tok_keepalive" in block, \
        "Verweis auf bestehenden Workaround fehlt"


# ── 7) Runner ─────────────────────────────────────────────────────────────


if __name__ == "__main__":
    tests = [
        test_01_constants_present,
        test_02_idb_layer_four_helpers_present,
        test_03_idb_open_fail_soft,
        test_04_persist_and_unwrap_present,
        test_05_persist_uses_random_key_not_pbkdf2,
        test_06_unwrap_checks_expires_at,
        test_07_unwrap_rolling_refresh,
        test_08_unwrap_deletes_record_on_expire_or_fail,
        test_09_ensure_token_async_trampoline_before_modal,
        test_10_ensure_token_signature_unchanged,
        test_11_ensure_token_fail_soft_catch,
        test_12_set_session_token_fires_persist,
        test_13_clear_all_tokens_deletes_idb,
        test_14_pending_callback_guard_present,
        test_15_master_pw_anchor_unchanged,
        test_16_no_30_day_promise_in_code,
        test_17_diagnosis_reference_in_comment,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"OK  {t.__name__}")
        except AssertionError as exc:
            print(f"FAIL {t.__name__}: {exc}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} Tests bestanden.")
    sys.exit(1 if failed else 0)
