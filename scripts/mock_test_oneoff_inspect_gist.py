"""Mock-Tests fuer den rein lesenden Diagnose-Workflow
(.github/workflows/oneoff-inspect-gist.yml).

Folge-Auftrag nach PR #617: ein Probelauf fand nur 3 statt der
erwarteten 5 Positions-Eintraege (GRPN vorhanden, IONQ/PDYN NICHT
vorhanden). Easy will die 3 Namen bestaetigt sehen und die
Gist-Revisionshistorie pruefen, statt zu raten. Dieser Workflow macht
GENAU das -- rein lesend, KEIN PATCH-Call irgendwo im Skript.

Tests:
  1. YAML-Struktur: workflow_dispatch ohne Inputs, permissions leer,
     concurrency-Gruppe, kein Checkout.
  2. Python-Block Syntax OK.
  3. KEIN PATCH/method="PATCH" irgendwo im extrahierten Block (technisch
     unmoeglich, dass dieser Workflow schreibt).
  4. Happy-Path: listet Ticker-Namen aus positions + watchlist korrekt,
     sortiert, ohne Preise/Stueckzahlen/Daten im Output.
  5. Leere positions/watchlist -> "(leer)"-Hinweis, kein Crash.
  6. Ungueltiges positions/watchlist-Format -> Hinweis-Zeile, kein Crash.
  7. Revisionshistorie wird gelistet (Zeitstempel + Kurz-Hash + Aenderungs-
     Zaehler), KEINE Inhalte im Output.
  8. Revisionshistorie nicht lesbar -> WARNUNG, Ticker-Liste bleibt
     trotzdem im Output (exit 0, kein Abbruch der Haupt-Info).
  9. Fehlende Secrets / Gist-Lesefehler / truncated / kaputtes JSON ->
     jeweils klare Fehlermeldung, exit 1.
 10. Log-Hygiene: keine bekannten Preis-/Datums-Werte aus den Mock-Daten
     im Output (Ticker-NAMEN sind explizit erlaubt, siehe CLAUDE.md-
     Log-Hygiene-Konvention: nur Preise/Stueckzahlen/Einstiegskurse
     sind tabu, nicht Tickernamen).
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "oneoff-inspect-gist.yml"


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

DATA_FILENAME = "squeeze_data.json"


def _mock_gist_body(positions, *, watchlist=None, truncated=False, content=None) -> dict:
    data = {"watchlist": watchlist if watchlist is not None else [],
            "positions": positions}
    entry = {
        "truncated": truncated,
        "content": content if content is not None else json.dumps(data),
    }
    return {"files": {DATA_FILENAME: entry}}


_MOCK_COMMITS = [
    {"version": "abcdef1234567890", "committed_at": "2026-10-31T18:30:00Z",
     "change_status": {"additions": 0, "deletions": 2, "total": 2}},
    {"version": "1234567890abcdef", "committed_at": "2026-10-31T17:44:00Z",
     "change_status": {"additions": 1, "deletions": 1, "total": 2}},
]


class _FakeResponse:
    def __init__(self, status: int, body: bytes = b""):
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _run_workflow(env: dict, *, gist_body=None, commits_body=None,
                   get_error: Exception | None = None,
                   commits_error: Exception | None = None):
    import io
    import os
    import contextlib
    import unittest.mock as mock
    import urllib.request as real_urllib_request

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/commits" in url:
            if commits_error is not None:
                raise commits_error
            return _FakeResponse(200, json.dumps(commits_body or []).encode("utf-8"))
        if get_error is not None:
            raise get_error
        return _FakeResponse(200, json.dumps(gist_body or {}).encode("utf-8"))

    ns: dict = {"__name__": "__main__"}
    stdout_buf, stderr_buf = io.StringIO(), io.StringIO()
    exit_code = None
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf), \
         mock.patch.object(real_urllib_request, "urlopen", fake_urlopen), \
         mock.patch.dict(os.environ, env, clear=True):
        try:
            exec(compile(_PY_BLOCK, "<oneoff_inspect_gist>", "exec"), ns)
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 0
    assert exit_code is not None, "Block hat sys.exit() nicht aufgerufen"
    return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue()


def _base_env(**overrides) -> dict:
    env = {"GIST_ID": "testgist123", "GIST_TOKEN": "ghp_test_token_xyz"}
    env.update(overrides)
    return env


# === 1 — YAML-Struktur ======================================================

def test_yaml_valid_and_dispatch_only_no_inputs():
    data = _load_yaml()
    assert data.get("name") == "One-off Inspect Gist"
    trigger_key = True if True in data else "on"
    triggers = data[trigger_key]
    assert set(triggers.keys()) == {"workflow_dispatch"}
    assert triggers["workflow_dispatch"] in (None, {}), (
        "Dieser Diagnose-Workflow braucht keine Inputs")


def test_yaml_permissions_empty():
    data = _load_yaml()
    assert data["permissions"] == {}


def test_yaml_concurrency_group():
    data = _load_yaml()
    conc = data["concurrency"]
    assert conc["group"] == "oneoff-inspect-gist"


def test_yaml_no_checkout():
    src = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "actions/checkout" not in src


def test_yaml_secrets_only_via_env():
    data = _load_yaml()
    step = data["jobs"]["inspect"]["steps"][-1]
    assert step["env"]["GIST_ID"] == "${{ secrets.GIST_ID }}"
    assert step["env"]["GIST_TOKEN"] == "${{ secrets.GIST_TOKEN }}"
    assert "${{ secrets.GIST_TOKEN }}" not in step["run"]


# === 2 — Python-Block Syntax ================================================

def test_embedded_python_syntax_ok():
    compile(_PY_BLOCK, "<oneoff_inspect_gist>", "exec")


# === 3 — Technisch unmoeglich zu schreiben ==================================

def test_no_patch_call_anywhere_in_script():
    assert "PATCH" not in _PY_BLOCK, (
        "Dieser Diagnose-Workflow darf NIEMALS einen PATCH-Call enthalten")
    assert "method=" not in _PY_BLOCK.replace(" ", ""), (
        "Kein method=-Kwarg -- urllib.request.Request nutzt hier nur GET "
        "(Default-Methode)")


# === 4 — Happy-Path: Ticker-Namen gelistet =================================

def test_lists_ticker_names_sorted_no_sensitive_values():
    positions = {
        "GRPN": {"entry_date": "2026-10-01", "entry_price": 25.0, "shares": 5},
        "AMC":  {"entry_date": "2026-09-28", "entry_price": 4.21, "shares": 50},
        "WOLF": {"entry_date": "2026-08-01", "entry_price": 2.9, "shares": 100},
    }
    env = _base_env()
    code, out, err = _run_workflow(
        env, gist_body=_mock_gist_body(positions, watchlist=["VEEA", "AMC", "WOLF"]),
        commits_body=_MOCK_COMMITS)
    assert code == 0, err
    assert "AMC, GRPN, WOLF" in out, "Ticker muessen alphabetisch sortiert sein"
    assert "VEEA, WOLF" in out or "AMC, VEEA, WOLF" in out
    for sensitive in ("25.0", "4.21", "2.9", "2026-10-01", "2026-09-28"):
        assert sensitive not in out, f"sensibler Wert {sensitive!r} im Output"


# === 5 — Leere Listen =======================================================

def test_empty_positions_and_watchlist_show_leer_hint():
    env = _base_env()
    code, out, err = _run_workflow(
        env, gist_body=_mock_gist_body({}, watchlist=[]), commits_body=[])
    assert code == 0, err
    assert "(leer)" in out


# === 6 — Ungueltiges Format =================================================

def test_invalid_positions_format_shows_hint_no_crash():
    env = _base_env()
    gist = _mock_gist_body({}, content=json.dumps({"watchlist": [], "positions": "not-a-dict"}))
    code, out, err = _run_workflow(env, gist_body=gist, commits_body=[])
    assert code == 0, err
    assert "kein gueltiges Objekt" in out


# === 7 — Revisionshistorie gelistet, keine Inhalte =========================

def test_revision_history_listed_no_content():
    env = _base_env()
    code, out, err = _run_workflow(
        env, gist_body=_mock_gist_body({"AMC": {}}), commits_body=_MOCK_COMMITS)
    assert code == 0, err
    assert "Revisionshistorie (2 Eintraege" in out
    assert "2026-10-31T18:30:00Z" in out
    assert "abcdef1" in out
    assert "+0/-2" in out


# === 8 — Revisionshistorie nicht lesbar =====================================

def test_revision_history_unreadable_is_warning_not_abort():
    env = _base_env()
    code, out, err = _run_workflow(
        env, gist_body=_mock_gist_body({"AMC": {}}),
        commits_error=ConnectionError("boom"))
    assert code == 0, err
    assert "WARNUNG" in err
    assert "AMC" in out, "Ticker-Liste muss trotz Revisions-Fehler sichtbar bleiben"


# === 9 — Fehlerpfade =========================================================

def test_missing_secrets_aborts():
    env = _base_env(GIST_ID="")
    code, out, err = _run_workflow(env, gist_body=_mock_gist_body({}))
    assert code == 1
    assert "FEHLER" in err


def test_gist_get_error_aborts():
    env = _base_env()
    code, out, err = _run_workflow(env, get_error=ConnectionError("boom"))
    assert code == 1
    assert "FEHLER" in err


def test_truncated_aborts():
    env = _base_env()
    gist = _mock_gist_body({}, truncated=True)
    code, out, err = _run_workflow(env, gist_body=gist)
    assert code == 1
    assert "truncated" in err


def test_corrupt_json_aborts():
    env = _base_env()
    gist = _mock_gist_body({}, content="{not valid json")
    code, out, err = _run_workflow(env, gist_body=gist)
    assert code == 1


# === 10 — Log-Hygiene (Preise/Daten verboten, Tickernamen erlaubt) ========

def test_no_price_or_date_values_in_any_path():
    positions = {
        "GRPN": {"entry_date": "2026-10-01", "entry_price": 25.0, "shares": 5},
    }
    env = _base_env()
    code, out, err = _run_workflow(
        env, gist_body=_mock_gist_body(positions), commits_body=_MOCK_COMMITS)
    combined = out + err
    assert "25.0" not in combined
    assert "2026-10-01" not in combined
    # Tickername selbst ist explizit erlaubt:
    assert "GRPN" in combined


def main() -> None:
    tests = [
        ("YAML: workflow_dispatch ohne Inputs",          test_yaml_valid_and_dispatch_only_no_inputs),
        ("YAML: permissions leer",                        test_yaml_permissions_empty),
        ("YAML: concurrency-Gruppe",                      test_yaml_concurrency_group),
        ("YAML: kein Checkout",                           test_yaml_no_checkout),
        ("YAML: Secrets nur via env:",                    test_yaml_secrets_only_via_env),
        ("Python-Block: Syntax OK",                       test_embedded_python_syntax_ok),
        ("Kein PATCH-Call irgendwo im Skript",            test_no_patch_call_anywhere_in_script),
        ("Ticker-Namen sortiert, keine sensiblen Werte",  test_lists_ticker_names_sorted_no_sensitive_values),
        ("Leere Listen -> '(leer)'-Hinweis",              test_empty_positions_and_watchlist_show_leer_hint),
        ("Ungueltiges Format -> Hinweis, kein Crash",     test_invalid_positions_format_shows_hint_no_crash),
        ("Revisionshistorie gelistet, keine Inhalte",     test_revision_history_listed_no_content),
        ("Revisionshistorie-Fehler -> WARNUNG, kein Abbruch", test_revision_history_unreadable_is_warning_not_abort),
        ("Fehlende Secrets -> Abbruch",                   test_missing_secrets_aborts),
        ("Gist-GET-Fehler -> Abbruch",                    test_gist_get_error_aborts),
        ("Truncated -> Abbruch",                          test_truncated_aborts),
        ("Kaputtes JSON -> Abbruch",                       test_corrupt_json_aborts),
        ("Log-Hygiene: keine Preise/Daten, Ticker erlaubt", test_no_price_or_date_values_in_any_path),
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
