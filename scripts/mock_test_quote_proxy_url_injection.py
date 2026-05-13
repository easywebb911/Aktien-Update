"""Mock-Tests für den QUOTE_PROXY_URL-Context-Injection-Bug (Hotfix nach PR #135).

Hintergrund: PR #135 hat im JS-Block die Konstante
``const QUOTE_PROXY_URL = '{quote_proxy_url_js}';`` eingebaut, aber den
Context-Key + Unpacker in ``generate_html_v1`` vergessen. Daily-Run
crashte mit ``NameError: name 'quote_proxy_url_js' is not defined`` beim
f-String-Eval.

Fix: ``_build_context`` setzt den Key + ``generate_html_v1`` entpackt ihn
defensiv via ``ctx.get("quote_proxy_url_js", "")``. Bei leerer ENV-
Variable wird die Konstante zu ``''`` → JS-Polling-Modul ist no-op.

Tests:
  1. _build_context schreibt quote_proxy_url_js in den Context-Dict
  2. generate_html_v1 entpackt den Key mit defensivem .get-Fallback
  3. JS-Placeholder im f-String referenziert die Variable
  4. URL-Sanitize-Regex aus PR #135 wird angewendet (gegen XSS / Garbage)
  5. ENV gesetzt + sanitized URL → Variable nicht leer
  6. ENV leer → Variable leer (kein NameError)
  7. ENV mit Garbage (XSS, http://, javascript:) → Variable leer (defensiv)
  8. f-String-Simulation: lokale Variable definiert → kein NameError
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
import textwrap

ROOT = pathlib.Path(__file__).resolve().parent.parent

_SANITIZE_RE = re.compile(r"^https://[A-Za-z0-9.\-]+(/[A-Za-z0-9._\-/]*)?$")


def _resolve_qp_url(env_value: str) -> str:
    """Pythonische Nachbildung der Sanitize-Logik aus _build_context:

        _qp_raw = os.environ.get("QUOTE_PROXY_URL", "").strip().rstrip("/")
        quote_proxy_url_js = ""
        if re.match(URL_PATTERN, _qp_raw):
            quote_proxy_url_js = _qp_raw[:256]
    """
    raw = (env_value or "").strip().rstrip("/")
    if _SANITIZE_RE.match(raw or ""):
        return raw[:256]
    return ""


# === 1-3 — Source-Inspektion ===============================================

def test_build_context_sets_quote_proxy_url_js():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # Initialisierung im _build_context
    assert 'quote_proxy_url_js = ""' in src, (
        "Initial-Wert quote_proxy_url_js = \"\" fehlt in _build_context")
    # Eintrag im Context-Dict
    assert '"quote_proxy_url_js": quote_proxy_url_js' in src, (
        "Context-Dict-Key 'quote_proxy_url_js' fehlt — generate_html_v1 "
        "würde NameError werfen")


def test_generate_html_v1_unpacks_with_defensive_fallback():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # Unpacker mit .get-Fallback (alte Cached-Contexts ohne den Key)
    assert 'quote_proxy_url_js = ctx.get("quote_proxy_url_js"' in src, (
        "generate_html_v1 entpackt den Key nicht defensiv via ctx.get()")


def test_js_placeholder_references_local_var():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    assert "const QUOTE_PROXY_URL = '{quote_proxy_url_js}';" in src, (
        "JS-Placeholder '{quote_proxy_url_js}' fehlt im JS-Block")


# === 4-7 — Sanitize-Logik (Pythonisch repliziert) ==========================

def test_sanitize_accepts_valid_url():
    qp = _resolve_qp_url("https://quote-proxy.foo.workers.dev")
    assert qp == "https://quote-proxy.foo.workers.dev", qp


def test_sanitize_strips_trailing_slash():
    qp = _resolve_qp_url("https://quote-proxy.foo.workers.dev/")
    assert qp == "https://quote-proxy.foo.workers.dev", qp


def test_sanitize_empty_env_returns_empty():
    qp = _resolve_qp_url("")
    assert qp == "", f"Leere ENV muss leere String liefern, got {qp!r}"


def test_sanitize_rejects_garbage():
    for bad in (
        "http://insecure.com",
        "javascript:alert(1)",
        "https://foo bar.com",
        "https://foo.com?token=secret",
        "https://foo.com#anchor",
        "random-string",
    ):
        qp = _resolve_qp_url(bad)
        assert qp == "", f"Garbage {bad!r} fälschlich akzeptiert ({qp!r})"


# === 8 — f-String-Simulation: kein NameError ===============================

def test_format_template_with_var_set():
    """Simuliert den f-String-Eval in generate_html_v1 mit gesetzter Variable.
    Wenn die Variable im local scope existiert, läuft .format() ohne Error.
    """
    quote_proxy_url_js = "https://quote-proxy.example.workers.dev"
    template = "const QUOTE_PROXY_URL = '{quote_proxy_url_js}';"
    out = template.format(quote_proxy_url_js=quote_proxy_url_js)
    assert "https://quote-proxy.example.workers.dev" in out, out


def test_format_template_with_empty_var():
    """Wenn ENV leer → Variable leer → JS-Konstante wird zu '' → Polling
    no-op (das ist by design, kein UI-Bruch)."""
    quote_proxy_url_js = ""
    template = "const QUOTE_PROXY_URL = '{quote_proxy_url_js}';"
    out = template.format(quote_proxy_url_js=quote_proxy_url_js)
    assert out == "const QUOTE_PROXY_URL = '';", out


def test_format_template_missing_var_raises():
    """Negativ-Beweis für den Bug: ohne Variable im scope → KeyError beim
    .format()-Aufruf bzw. NameError beim f-String-Eval. Genau das was wir
    in PR #135 ohne Fix gesehen hätten."""
    template = "const QUOTE_PROXY_URL = '{quote_proxy_url_js}';"
    try:
        template.format()   # kein quote_proxy_url_js kwarg
    except KeyError as exc:
        assert "quote_proxy_url_js" in str(exc), exc
        return
    raise AssertionError(
        "format() ohne quote_proxy_url_js-Argument hätte KeyError werfen müssen — "
        "der ursprüngliche Bug-Pfad reproduziert sich nicht?")


# === Runner =================================================================

def main() -> None:
    tests = [
        ("_build_context setzt quote_proxy_url_js + Context-Key",
         test_build_context_sets_quote_proxy_url_js),
        ("generate_html_v1 entpackt defensiv via ctx.get()",
         test_generate_html_v1_unpacks_with_defensive_fallback),
        ("JS-Placeholder referenziert die Variable",
         test_js_placeholder_references_local_var),
        ("Sanitize akzeptiert gültige https-URL",
         test_sanitize_accepts_valid_url),
        ("Sanitize entfernt trailing slash",
         test_sanitize_strips_trailing_slash),
        ("Leere ENV → leerer String (kein NameError)",
         test_sanitize_empty_env_returns_empty),
        ("Garbage / XSS / http:// → leerer String",
         test_sanitize_rejects_garbage),
        ("f-String läuft mit gesetzter Variable",
         test_format_template_with_var_set),
        ("f-String läuft mit leerer Variable",
         test_format_template_with_empty_var),
        ("f-String OHNE Variable wirft KeyError (Bug-Reproduktion)",
         test_format_template_missing_var_raises),
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
