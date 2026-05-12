"""Mock-Tests für Token-Reentry-Fix Phase 1 (F1 + F2 + F5).

F1 — 401/403-Soft-Reset mit Counter (3 aufeinanderfolgende → hard reset)
F2 — autocomplete + <form>-Wrapper in den drei Token-Modalen (DOM-Markup-
     Check via Regex auf generate_report.py-Source)
F5 — getToken() schreibt _tok_keepalive-Timestamp in localStorage

Da der Token-Code rein clientseitig in JS lebt, replizieren wir die
Counter-Logik hier als Python-Mock + verifizieren das Source-Markup
für F2/F5.

Ausführung: ``python scripts/mock_test_token_reentry_fix.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# === F1 — Counter-Logik repliziert (Python-Spiegel der JS-Mechanik) ========

class _CounterMock:
    """Simuliert die JS-Logik aus generate_report.py:
    _tokAuthFailCount, _onTokenAuthFail, _resetTokenAuthFailCount,
    _clearAllTokens, _clearSessionToken."""

    HARD_THRESHOLD = 3

    def __init__(self):
        self.count = 0
        self.encrypted_blob_exists = True
        self.session_token = "decrypted-token"
        self.calls = []

    def on_auth_fail(self, status, reason):
        self.count += 1
        if self.count >= self.HARD_THRESHOLD:
            self._clear_all()
            self.count = 0
            self.calls.append(("hard", status, reason))
            return "hard"
        self._clear_session()
        self.calls.append(("soft", status, reason))
        return "soft"

    def reset_count(self):
        self.count = 0

    def _clear_all(self):
        self.encrypted_blob_exists = False
        self.session_token = ""

    def _clear_session(self):
        self.session_token = ""


# === F1 Tests ==============================================================

def test_one_transient_403_soft():
    c = _CounterMock()
    mode = c.on_auth_fail(403, "recalc")
    assert mode == "soft", c.calls
    assert c.encrypted_blob_exists is True, c.__dict__
    assert c.session_token == "", c.__dict__
    assert c.count == 1, c.count


def test_two_transient_403s_blob_remains():
    c = _CounterMock()
    c.on_auth_fail(403, "recalc")
    c.on_auth_fail(401, "ki")
    assert c.encrypted_blob_exists is True, c.__dict__
    assert c.count == 2, c.count


def test_three_consecutive_403s_hard():
    c = _CounterMock()
    c.on_auth_fail(403, "recalc")
    c.on_auth_fail(403, "recalc")
    mode = c.on_auth_fail(403, "recalc")
    assert mode == "hard", mode
    assert c.encrypted_blob_exists is False, c.__dict__
    # Counter ist nach hard reset zurückgesetzt
    assert c.count == 0, c.count


def test_success_in_between_resets_counter():
    c = _CounterMock()
    c.on_auth_fail(403, "recalc")
    c.on_auth_fail(403, "recalc")
    # Erfolgreicher Request resettet
    c.reset_count()
    # Nächste zwei 403 sollen NICHT hard sein
    mode1 = c.on_auth_fail(403, "recalc")
    mode2 = c.on_auth_fail(403, "recalc")
    assert mode1 == "soft", mode1
    assert mode2 == "soft", mode2
    assert c.encrypted_blob_exists is True, c.__dict__


def test_reset_no_op_when_count_zero():
    c = _CounterMock()
    c.reset_count()
    assert c.count == 0


# === F2 — DOM-Markup-Check ==================================================

def _gr_source() -> str:
    return (ROOT / "generate_report.py").read_text(encoding="utf-8")


def test_setup_modal_has_form_wrapper():
    src = _gr_source()
    # Setup-Modal hat <form onsubmit="return false">
    assert re.search(
        r'tok-modal-setup.*?<form onsubmit="return false"',
        src, re.DOTALL), "tok-modal-setup hat keinen <form>-Wrapper"


def test_unlock_modal_has_form_wrapper():
    src = _gr_source()
    assert re.search(
        r'tok-modal-unlock.*?<form onsubmit="return false"',
        src, re.DOTALL), "tok-modal-unlock hat keinen <form>-Wrapper"


def test_migrate_modal_has_form_wrapper():
    src = _gr_source()
    assert re.search(
        r'tok-modal-migrate.*?<form onsubmit="return false"',
        src, re.DOTALL), "tok-modal-migrate hat keinen <form>-Wrapper"


def test_unlock_modal_has_current_password_autocomplete():
    src = _gr_source()
    # Sucht innerhalb der Unlock-Modal-Section
    m = re.search(r'tok-modal-unlock.*?</form>', src, re.DOTALL)
    assert m, "Unlock-Modal nicht gefunden"
    section = m.group(0)
    assert 'autocomplete="current-password"' in section, (
        "Unlock-Input fehlt autocomplete=current-password")


def test_setup_modal_has_new_password_autocomplete():
    src = _gr_source()
    m = re.search(r'tok-modal-setup.*?</form>', src, re.DOTALL)
    assert m, "Setup-Modal nicht gefunden"
    section = m.group(0)
    # Mindestens zweimal new-password (Master + Bestätigung)
    n = section.count('autocomplete="new-password"')
    assert n >= 2, f"Setup-Modal: nur {n}× autocomplete=new-password, erwartet ≥ 2"


def test_modals_have_hidden_username_for_keychain():
    """Safari/iCloud-Schlüsselbund braucht autocomplete=username, sonst
    bietet er das Speichern nicht an. Hidden text-input mit
    stabilem Wert."""
    src = _gr_source()
    for modal_id in ("tok-modal-setup", "tok-modal-unlock", "tok-modal-migrate"):
        m = re.search(rf'{modal_id}.*?</form>', src, re.DOTALL)
        assert m, f"{modal_id} nicht gefunden"
        section = m.group(0)
        assert 'autocomplete="username"' in section, (
            f"{modal_id}: hidden autocomplete=username fehlt")


def test_submit_buttons_are_type_submit():
    """Innerhalb von <form> müssen die Hauptbuttons type=submit haben,
    damit Safari den Submit als Credential-Use erkennt. Cancel/Skip
    bleiben type=button."""
    src = _gr_source()
    for modal_id in ("tok-modal-setup", "tok-modal-unlock", "tok-modal-migrate"):
        m = re.search(rf'{modal_id}.*?</form>', src, re.DOTALL)
        section = m.group(0)
        # Mindestens ein type=submit pro Modal
        assert 'type="submit"' in section, (
            f"{modal_id}: kein type=submit-Button")
        # Cancel-Buttons sind type=button
        assert 'type="button"' in section, (
            f"{modal_id}: kein type=button-Button (Cancel)")


# === F5 — Keep-Alive-Touch =================================================

def _get_token_body() -> str:
    """Extrahiert den Body von ``function getToken()`` aus der Source.
    Brace-balancing über doppelte ``{{``/``}}`` (Python-f-String-Escapes
    werden zu single braces im Render-Output, aber wir sehen die Quelle)."""
    src = _gr_source()
    idx = src.find("function getToken()")
    assert idx >= 0, "function getToken() nicht im Source"
    # Body grob abgrenzen bis zum nächsten Top-Level-Functions-Marker
    end = src.find("// Schreibt sessionStorage", idx)
    if end < 0:
        end = idx + 1500
    return src[idx:end]


def test_get_token_writes_keepalive():
    """getToken() schreibt einen _tok_keepalive-Timestamp in
    localStorage (try/catch wrapped)."""
    body = _get_token_body()
    assert '_tok_keepalive' in body, (
        "getToken() schreibt keinen _tok_keepalive-Timestamp")
    assert "localStorage.setItem('_tok_keepalive'" in body, (
        "getToken() benutzt localStorage.setItem('_tok_keepalive', ...) nicht")


def test_keepalive_skipped_when_no_token():
    """Wenn kein Token da ist (frische Session), darf KEIN Keep-Alive
    geschrieben werden — sonst würde ein leerer Aufruf den ITP-Counter
    auch ohne User-Action resetten."""
    body = _get_token_body()
    # Pattern: Keep-Alive-Write ist innerhalb von "if (tok) {" — wir
    # validieren die Reihenfolge: zuerst `if (tok)`, dann `_tok_keepalive`.
    pos_if = body.find("if (tok)")
    pos_keepalive = body.find("_tok_keepalive")
    assert pos_if >= 0, "kein `if (tok)`-Gate in getToken()"
    assert pos_keepalive > pos_if, (
        f"_tok_keepalive (pos {pos_keepalive}) liegt nicht NACH "
        f"if (tok)-Gate (pos {pos_if}) → Write könnte ohne Token feuern")


# === Counter-Konstante ====================================================

def test_hard_threshold_in_source():
    """Die Konstante TOKEN_AUTH_FAIL_HARD_THRESHOLD muss im Source
    auf 3 stehen (Spec aus Diagnose-Bericht). Falls jemand das
    versehentlich senkt, fällt es hier auf."""
    src = _gr_source()
    m = re.search(r'TOKEN_AUTH_FAIL_HARD_THRESHOLD\s*=\s*(\d+)', src)
    assert m, "TOKEN_AUTH_FAIL_HARD_THRESHOLD nicht im Source"
    assert int(m.group(1)) == 3, f"Threshold = {m.group(1)}, erwartet 3"


# === Runner ================================================================

def main():
    tests = [
        ("F1: 1 transienter 403 → soft, Blob bleibt",     test_one_transient_403_soft),
        ("F1: 2 transiente 403 → Blob bleibt",            test_two_transient_403s_blob_remains),
        ("F1: 3 aufeinanderfolgende 403 → hard reset",    test_three_consecutive_403s_hard),
        ("F1: Erfolg zwischendrin → Counter zurück",      test_success_in_between_resets_counter),
        ("F1: reset() ist no-op bei count=0",             test_reset_no_op_when_count_zero),
        ("F1: TOKEN_AUTH_FAIL_HARD_THRESHOLD == 3",       test_hard_threshold_in_source),
        ("F2: Setup-Modal <form>-Wrapper",                test_setup_modal_has_form_wrapper),
        ("F2: Unlock-Modal <form>-Wrapper",               test_unlock_modal_has_form_wrapper),
        ("F2: Migrate-Modal <form>-Wrapper",              test_migrate_modal_has_form_wrapper),
        ("F2: Unlock autocomplete=current-password",      test_unlock_modal_has_current_password_autocomplete),
        ("F2: Setup autocomplete=new-password (≥2)",      test_setup_modal_has_new_password_autocomplete),
        ("F2: Hidden username für Keychain",              test_modals_have_hidden_username_for_keychain),
        ("F2: type=submit + type=button korrekt",         test_submit_buttons_are_type_submit),
        ("F5: getToken() schreibt _tok_keepalive",        test_get_token_writes_keepalive),
        ("F5: Keep-Alive nur wenn Token vorhanden",       test_keepalive_skipped_when_no_token),
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
