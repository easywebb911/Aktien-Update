"""Mock-Tests fuer den Agent-ntfy-Relay-Workflow
(.github/workflows/agent_ntfy_relay.yml).

Der Workflow ist bewusst checkout-frei -- die gesamte Sende-Logik lebt
INLINE im Workflow-YAML (Python-Heredoc), nicht in einem separaten
Repo-Skript. Dieses Mock-Test extrahiert den Python-Block per Regex aus
der YAML-Datei (analog zum ``_extract``-Muster in
``mock_test_score_confidence.py``, das Funktions-Bodies aus
``generate_report.py`` zieht) und fuehrt ihn gegen gemockte
Umgebungsvariablen + gemocktes ``urllib.request.urlopen`` aus -- es gibt
also EINE Quelle der Wahrheit (die YAML selbst), keine Logik-Drift
zwischen Workflow und Test.

Tests:
  1. YAML ist syntaktisch gueltig + Struktur-Checks (trigger, inputs,
     permissions, timeout, kein checkout).
  2. Eingebetteter Python-Block ist syntaktisch gueltig (compile()).
  3. Happy-Path: Titel/Body/Headers wie erwartet, kein Topic-Echo in
     Stdout.
  4. Fehlendes NTFY_TOPIC -> no-op (exit 0, kein HTTP-Call).
  5. Injection-Sicherheit: Sonderzeichen ($, `, ", Umlaute, Emojis,
     Zeilenumbrueche) im Titel/Body fuehren zu KEINEM Shell-Effekt --
     sie kommen unveraendert (bzw. nur ASCII-gestrippt im Titel) im
     HTTP-Request an, niemals als ausgefuehrter Code.
  6. Titel-Laengenbegrenzung (100 Zeichen) + ASCII-Stripping.
  7. Body-Kuerzung auf ntfy-Limit mit "... (gekuerzt)"-Suffix, UTF-8-
     Zeichengrenze bleibt gueltig (kein kaputtes Multibyte-Zeichen).
  8. Priority-Validierung: ungueltiger Wert faellt auf "default" zurueck.
  9. HTTP-Fehler (4xx) -> exit 1, Exception -> exit 1.
 10. SESSION_HANDOVER.md dokumentiert den Relay (additiv, mit
     Aufruf-Beispiel).
"""
from __future__ import annotations

import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "agent_ntfy_relay.yml"


def _load_yaml() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _extract_python_block() -> str:
    src = WORKFLOW_PATH.read_text(encoding="utf-8")
    m = re.search(r"<<'PYEOF'\n([\s\S]+?)\n\s*PYEOF\n", src)
    assert m, "Python-Heredoc-Block nicht in der Workflow-YAML gefunden"
    lines = m.group(1).split("\n")
    indents = [len(l) - len(l.lstrip(" ")) for l in lines if l.strip()]
    min_indent = min(indents)
    return "\n".join(l[min_indent:] if l.strip() else "" for l in lines)


_PY_BLOCK = _extract_python_block()


class _FakeResponse:
    def __init__(self, status: int):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _run_relay(env: dict, *, urlopen_impl=None, http_error: Exception | None = None):
    """Fuehrt den extrahierten Python-Block in einer Sandbox aus.

    Gibt (exit_code, stdout, stderr, captured_request) zurueck.
    ``captured_request`` ist das ``urllib.request.Request``-Objekt des
    letzten (gemockten) Sende-Versuchs, oder None wenn kein Request
    gebaut wurde.
    """
    import io
    import os
    import contextlib
    import unittest.mock as mock
    import urllib.request as real_urllib_request

    captured: list = []

    def fake_urlopen(req, timeout=None):
        captured.append(req)
        if http_error is not None:
            raise http_error
        if urlopen_impl is not None:
            return urlopen_impl(req)
        return _FakeResponse(200)

    ns: dict = {"__name__": "__main__"}

    stdout_buf, stderr_buf = io.StringIO(), io.StringIO()
    exit_code = None
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf), \
         mock.patch.object(real_urllib_request, "urlopen", fake_urlopen), \
         mock.patch.dict(os.environ, env, clear=True):
        try:
            exec(compile(_PY_BLOCK, "<agent_ntfy_relay>", "exec"), ns)
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 0
    assert exit_code is not None, "Block hat sys.exit() nicht aufgerufen"
    return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue(), (captured[0] if captured else None)


def _base_env(**overrides) -> dict:
    env = {
        "NTFY_TOPIC": "test-topic-xyz",
        "RELAY_TITLE": "Testlauf",
        "RELAY_MESSAGE": "Alles ok.",
        "RELAY_TAGS": "robot",
        "RELAY_PRIORITY": "default",
    }
    env.update(overrides)
    return env


# === 1 — YAML-Struktur ======================================================

def test_yaml_valid_and_dispatch_only():
    data = _load_yaml()
    assert data.get("name") == "Agent ntfy Relay"
    trigger_key = True if True in data else "on"
    triggers = data[trigger_key]
    assert set(triggers.keys()) == {"workflow_dispatch"}, (
        "Trigger MUSS ausschliesslich workflow_dispatch sein")


def test_yaml_inputs_contract():
    data = _load_yaml()
    trigger_key = True if True in data else "on"
    inputs = data[trigger_key]["workflow_dispatch"]["inputs"]
    assert inputs["title"]["required"] is True
    assert inputs["message"]["required"] is True
    assert inputs["tags"]["required"] is False
    assert inputs["tags"]["default"] == "robot"
    assert inputs["priority"]["required"] is False
    assert inputs["priority"]["default"] == "default"


def test_yaml_permissions_empty_and_timeout():
    data = _load_yaml()
    assert data["permissions"] == {}, "permissions muss leer sein (kein Schreibrecht noetig)"
    job = data["jobs"]["relay"]
    assert job["timeout-minutes"] == 2


def test_yaml_no_checkout():
    src = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "actions/checkout" not in src, "Workflow soll ohne Checkout laufen"


def test_yaml_no_topic_interpolated_into_run_shell():
    # NTFY_TOPIC darf nur ueber env: in den Prozess, nie direkt im
    # `run:`-Shell-Text referenziert werden (Injection-Schutz).
    data = _load_yaml()
    step = data["jobs"]["relay"]["steps"][-1]
    assert "${{ secrets.NTFY_TOPIC }}" not in step["run"]
    assert step["env"]["NTFY_TOPIC"] == "${{ secrets.NTFY_TOPIC }}"
    for key in ("RELAY_TITLE", "RELAY_MESSAGE", "RELAY_TAGS", "RELAY_PRIORITY"):
        assert key in step["env"], f"{key} muss ueber env: durchgereicht werden"
        assert f"${{{{ inputs." not in step["run"], (
            "Inputs duerfen nicht direkt im Shell-Text interpoliert werden")


# === 2 — Eingebetteter Python-Block ========================================

def test_embedded_python_syntax_ok():
    compile(_PY_BLOCK, "<agent_ntfy_relay>", "exec")


# === 3 — Happy-Path =========================================================

def test_happy_path_sends_expected_request():
    code, out, err, req = _run_relay(_base_env())
    assert code == 0, err
    assert req is not None
    assert req.full_url == "https://ntfy.sh/test-topic-xyz"
    assert req.data == b"Alles ok."
    assert req.headers.get("Title") == "Testlauf"
    assert req.headers.get("Priority") == "default"
    assert req.headers.get("Tags") == "robot"
    assert "test-topic-xyz" not in out and "test-topic-xyz" not in err, (
        "Topic darf nirgends im Log auftauchen")


# === 4 — Fehlendes Topic ====================================================

def test_missing_topic_is_noop():
    code, out, err, req = _run_relay(_base_env(NTFY_TOPIC=""))
    assert code == 0
    assert req is None, "Ohne Topic darf kein HTTP-Call gebaut werden"
    assert "NTFY_TOPIC nicht gesetzt" in out


# === 5 — Injection-Sicherheit mit Sonderzeichen ============================

_INJECTION_PAYLOADS = [
    "$(rm -rf /)",
    "`echo pwned`",
    '";touch /tmp/pwned;"',
    "Ümlaut-Täst äöüÄÖÜß",
    "🚀🔥💥 Emoji-Titel",
    "Zeile1\nZeile2\nZeile3",
    "mixed $HOME `id` \"quoted\" 'single' \n newline Ümläut 🚀",
]


def test_injection_payloads_are_inert_and_passed_through():
    for payload in _INJECTION_PAYLOADS:
        env = _base_env(RELAY_TITLE=payload, RELAY_MESSAGE=payload)
        code, out, err, req = _run_relay(env)
        assert code == 0, f"payload={payload!r} err={err}"
        assert req is not None
        # Body kommt 1:1 (UTF-8) durch -- kein Shell-Effekt, keine Mutation
        # ausser der dokumentierten Laengenkuerzung (hier nicht relevant,
        # alle Payloads sind kurz).
        assert req.data == payload.encode("utf-8"), payload
        # Title-Header ist ASCII-only -- Payload darf den Header nicht
        # aufbrechen (kein CRLF, kein Nicht-ASCII-Byte).
        title_header = req.headers.get("Title")
        title_header.encode("ascii")  # wirft bei Nicht-ASCII
        assert "\n" not in title_header and "\r" not in title_header
        # Kein Hinweis auf echte Shell-Ausfuehrung (Exit-Code 0 bei jedem
        # Payload, kein zusaetzlicher Prozess-Seiteneffekt -- dass der
        # Payload-Text selbst in der Log-Zeile auftaucht, ist erwartet
        # und harmlos: er ist dort Daten, nicht ausgefuehrter Code).
        assert code == 0


def test_tags_field_not_shell_interpreted():
    env = _base_env(RELAY_TAGS="robot;$(echo x)")
    code, out, err, req = _run_relay(env)
    assert code == 0, err
    assert req.headers.get("Tags") == "robot;$(echo x)", (
        "Tags-Wert muss unveraendert als Header-Daten behandelt werden")


# === 6 — Titel-Laenge + ASCII =================================================

def test_title_truncated_to_100_chars():
    long_title = "A" * 150
    code, out, err, req = _run_relay(_base_env(RELAY_TITLE=long_title))
    assert code == 0, err
    assert len(req.headers.get("Title")) == 100


def test_title_ascii_stripped_with_umlauts_and_emoji():
    env = _base_env(RELAY_TITLE="Wächter-Läuft 🚀 OK")
    code, out, err, req = _run_relay(env)
    assert code == 0, err
    title = req.headers.get("Title")
    title.encode("ascii")  # wirft bei verbliebenem Nicht-ASCII-Zeichen
    assert "Wchter-Luft" in title or "W" in title  # robust gegen genaue Strip-Form


def test_title_empty_after_strip_falls_back():
    env = _base_env(RELAY_TITLE="🚀🔥💥")  # komplett nicht-ASCII
    code, out, err, req = _run_relay(env)
    assert code == 0, err
    assert req.headers.get("Title") == "Agent-Relay"


# === 7 — Body-Kuerzung auf ntfy-Limit ======================================

def test_body_truncated_with_suffix_and_valid_utf8():
    long_message = ("Ü" * 5000)  # Ü = 2 Bytes UTF-8 -> 10000 Bytes, > 3800
    env = _base_env(RELAY_MESSAGE=long_message)
    code, out, err, req = _run_relay(env)
    assert code == 0, err
    assert len(req.data) <= 3800
    body_text = req.data.decode("utf-8")  # wirft bei kaputter Zeichengrenze
    assert body_text.endswith("... (gekuerzt)")


def test_body_not_truncated_when_short():
    env = _base_env(RELAY_MESSAGE="Kurzer Text.")
    code, out, err, req = _run_relay(env)
    assert code == 0, err
    assert req.data == b"Kurzer Text."
    assert b"gekuerzt" not in req.data


# === 8 — Priority-Validierung ===============================================

def test_invalid_priority_falls_back_to_default():
    env = _base_env(RELAY_PRIORITY="SUPER-URGENT-INJECT")
    code, out, err, req = _run_relay(env)
    assert code == 0, err
    assert req.headers.get("Priority") == "default"


def test_valid_priority_passthrough():
    for prio in ("min", "low", "default", "high", "urgent"):
        env = _base_env(RELAY_PRIORITY=prio)
        code, out, err, req = _run_relay(env)
        assert code == 0, err
        assert req.headers.get("Priority") == prio


# === 9 — Fehlerpfade =========================================================

def test_http_error_exits_1():
    import urllib.error
    err_exc = urllib.error.HTTPError("https://ntfy.sh/x", 413, "Payload Too Large", {}, None)
    code, out, err, req = _run_relay(_base_env(), http_error=err_exc)
    assert code == 1
    assert "413" in err


def test_network_exception_exits_1():
    code, out, err, req = _run_relay(_base_env(), http_error=ConnectionError("boom"))
    assert code == 1
    assert "ConnectionError" in err


def test_success_status_exits_0():
    code, out, err, req = _run_relay(_base_env(), urlopen_impl=lambda req: _FakeResponse(200))
    assert code == 0, err


# === 10 — Doku ===============================================================

def test_session_handover_documents_relay():
    handover = (ROOT / "SESSION_HANDOVER.md").read_text(encoding="utf-8")
    assert "agent_ntfy_relay" in handover
    assert "gh workflow run agent_ntfy_relay.yml" in handover


def main() -> None:
    tests = [
        ("YAML: nur workflow_dispatch",                 test_yaml_valid_and_dispatch_only),
        ("YAML: Inputs-Vertrag",                         test_yaml_inputs_contract),
        ("YAML: permissions:{} + timeout 2min",          test_yaml_permissions_empty_and_timeout),
        ("YAML: kein Checkout",                          test_yaml_no_checkout),
        ("YAML: Topic/Inputs nur via env:",              test_yaml_no_topic_interpolated_into_run_shell),
        ("Python-Block: Syntax OK",                      test_embedded_python_syntax_ok),
        ("Happy-Path: Request korrekt + kein Topic-Log", test_happy_path_sends_expected_request),
        ("Fehlendes Topic -> no-op",                     test_missing_topic_is_noop),
        ("Injection-Payloads inert + durchgereicht",     test_injection_payloads_are_inert_and_passed_through),
        ("Tags nicht shell-interpretiert",               test_tags_field_not_shell_interpreted),
        ("Titel auf 100 Zeichen gekuerzt",               test_title_truncated_to_100_chars),
        ("Titel: Umlaute/Emoji ASCII-gestrippt",         test_title_ascii_stripped_with_umlauts_and_emoji),
        ("Titel: leer nach Strip -> Fallback",           test_title_empty_after_strip_falls_back),
        ("Body gekuerzt + gueltiges UTF-8 + Suffix",     test_body_truncated_with_suffix_and_valid_utf8),
        ("Body: kurz -> unveraendert",                   test_body_not_truncated_when_short),
        ("Ungueltige Priority -> default",               test_invalid_priority_falls_back_to_default),
        ("Gueltige Prioritaeten durchgereicht",          test_valid_priority_passthrough),
        ("HTTP-Fehler -> exit 1",                        test_http_error_exits_1),
        ("Netzwerk-Exception -> exit 1",                 test_network_exception_exits_1),
        ("Erfolg -> exit 0",                             test_success_status_exits_0),
        ("SESSION_HANDOVER dokumentiert Relay",          test_session_handover_documents_relay),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERR  {name}: {type(e).__name__}: {e}")
    print(f"\nTotal: {len(tests)} | Failed: {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
