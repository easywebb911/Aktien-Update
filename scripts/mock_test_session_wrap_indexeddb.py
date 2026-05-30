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


def test_14_pending_callback_queue_push():
    """PR #282: _tokPending wurde durch Callback-Queue (FIFO) ersetzt.
    _ensureToken pusht jeden Aufrufer in die Queue — kein Slot-Verlust
    bei parallelen Aufrufen waehrend des PR-#281-Async-Windows."""
    body_start = SRC.index("function _ensureToken(callback)")
    body_end   = SRC.index("\nfunction _showModalErr", body_start)
    body = SRC[body_start:body_end]
    assert "_tokPendingQueue.push(callback)" in body, \
        "_tokPendingQueue.push fehlt — Queue-Refactor PR #282 nicht angekommen"
    # Kein Single-Slot-Rest mehr
    assert "_tokPending = callback" not in body, \
        "Single-Slot-Restcode in _ensureToken (sollte Queue sein)"
    assert "if (!_tokPending)" not in body, \
        "Single-Slot-Guard-Rest in _ensureToken (sollte Queue sein)"


def test_14a_no_single_slot_residue_anywhere():
    """Kein _tokPending-Single-Slot-Rest in der GANZEN Datei.
    Nur _tokPendingQueue + _drainTokPendingQueue duerfen vorkommen."""
    # \b matched word-boundary, also '_tokPendingX' wird nicht gefangen
    pattern = re.compile(r"\b_tokPending\b")
    hits = pattern.findall(SRC)
    assert not hits, \
        f"Single-Slot-Rest gefunden ({len(hits)} Hits) — sollten alle " \
        "auf _tokPendingQueue migriert sein"


def test_14b_drain_helper_present_and_fail_soft():
    """_drainTokPendingQueue Helper: capture-then-clear-then-invoke,
    jeder Callback in try/catch (werfender CB blockiert Rest nicht)."""
    assert "function _drainTokPendingQueue(tok)" in SRC, \
        "_drainTokPendingQueue-Helper fehlt"
    body_start = SRC.index("function _drainTokPendingQueue(tok)")
    body_end   = SRC.index("\n}}", body_start) + 3
    body = SRC[body_start:body_end]
    # capture-then-clear-Reihenfolge (race-sicher)
    capture_pos = body.index("const callbacks = _tokPendingQueue")
    clear_pos   = body.index("_tokPendingQueue = []")
    assert capture_pos < clear_pos, \
        "_drainTokPendingQueue muss zuerst capturen, dann clearen"
    # try/catch pro Callback
    assert "try {{" in body and "catch(e)" in body, \
        "_drainTokPendingQueue muss try/catch pro Callback haben"


def test_14c_trampoline_uses_drain_helper():
    """_ensureToken-Trampoline-Success-Branch drained die Queue
    statt nur einen Callback aufzurufen."""
    body_start = SRC.index("function _ensureToken(callback)")
    body_end   = SRC.index("\nfunction _showModalErr", body_start)
    body = SRC[body_start:body_end]
    # Erfolgreicher Unwrap drained die Queue
    assert "_drainTokPendingQueue(unwrapped)" in body, \
        "Trampoline-Success-Branch muss _drainTokPendingQueue aufrufen"
    # Kein einzelner Slot-Capture-Rest mehr
    assert "const pending = _tokPending" not in body, \
        "Single-Slot-Capture-Rest in Trampoline (sollte Drain sein)"


def test_14d_submit_handlers_drain_queue():
    """Alle 4 Submit-Handler (Setup/Unlock/Migrate/Skip) capturen die
    Queue VOR _closeTokenModals und invoken alle gequeueten Callbacks.
    Single-Slot-Pattern `const cb = _tokPending` darf nicht mehr
    vorkommen."""
    for fn_name in ("_submitTokenSetup", "_submitTokenUnlock",
                    "_submitTokenMigrate", "_skipTokenMigrate"):
        # Begin
        fn_start = SRC.index(f"function {fn_name}(")
        # End ist naechste top-level function-decl oder Esc-Handler
        rest = SRC[fn_start + 1:]
        # naechste 'function ' oder '// Esc'-Marker als Body-Ende
        next_fn = rest.find("\nfunction ")
        next_esc = rest.find("\n// Esc ")
        candidates = [c for c in (next_fn, next_esc) if c > 0]
        fn_end = fn_start + 1 + min(candidates)
        body = SRC[fn_start:fn_end]
        # Capture-Pattern
        assert "const _queuedCallbacks = _tokPendingQueue" in body, \
            f"{fn_name}: Queue-Capture-Pattern fehlt"
        assert "_tokPendingQueue = []" in body, \
            f"{fn_name}: Queue-Clear nach Capture fehlt"
        # Kein Single-Slot-Rest
        assert "const cb = _tokPending" not in body, \
            f"{fn_name}: Single-Slot-Capture-Rest"
        # Drain-Loop mit try/catch (jeder Callback isoliert)
        assert "for (const cb of _queuedCallbacks)" in body, \
            f"{fn_name}: Drain-for-of-Loop fehlt"
        assert "try {{ if (cb) cb(" in body, \
            f"{fn_name}: try-around-cb fehlt"


def test_14e_close_modals_drops_queue():
    """_closeTokenModals droppt die Queue defensiv (identisch zum
    alten Single-Slot-null-Verhalten — Esc-Taste etc. droppt wartende
    Callbacks; Submit-Handler capturen VOR Close)."""
    fn_start = SRC.index("function _closeTokenModals()")
    fn_end   = SRC.index("\nfunction _ensureToken", fn_start)
    body = SRC[fn_start:fn_end]
    assert "_tokPendingQueue = []" in body, \
        "_closeTokenModals muss Queue droppen (defensiv)"
    assert "_tokPending = null" not in body, \
        "Single-Slot-null-Rest in _closeTokenModals"


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
        test_14_pending_callback_queue_push,
        test_14a_no_single_slot_residue_anywhere,
        test_14b_drain_helper_present_and_fail_soft,
        test_14c_trampoline_uses_drain_helper,
        test_14d_submit_handlers_drain_queue,
        test_14e_close_modals_drops_queue,
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
