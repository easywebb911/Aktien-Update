"""Mock-Tests fuer den Wegwerf-Workflow v2
(.github/workflows/oneoff-remove-ghost-positions-v2.yml).

Folge-PR nach PR #614/#615/#616: entfernt GRPN/IONQ/PDYN aus dem
Positions-Gist, NACH dem Lost-Update-Fix (PR #616) in gistLoad/gistSave.
Identisches Sicherheits-Muster zu PR #614 (mock_test_oneoff_remove_
ghost_positions.py, inzwischen mit jenem Workflow zusammen entfernt),
erweitert um einen ZWEITEN Verifikations-Anker (WOLF) -- in v1 war nur
AMC unberuehrt zu pruefen, in v2 sind AMC UND WOLF echte, verbleibende
Positionen, die beide unberuehrt bleiben muessen.

Tests: analog v1 (siehe Git-Historie von mock_test_oneoff_remove_ghost_
positions.py), mit folgenden Aenderungen:
  - Allowlist ist jetzt {GRPN, IONQ, PDYN} statt {IONQ, PDYN}.
  - AMC und WOLF sind BEIDE Verifikations-Anker (nicht nur AMC).
  - Mock-Positionsdaten umfassen 5 Ticker (AMC, GRPN, IONQ, PDYN, WOLF),
    identisch zum tatsaechlichen Gist-Zustand nach PR #616.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "oneoff-remove-ghost-positions-v2.yml"


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

_MOCK_POSITIONS = {
    "AMC":  {"entry_date": "2026-09-28", "entry_price": 4.21, "shares": 50},
    "GRPN": {"entry_date": "2026-10-01", "entry_price": 25.0, "shares": 5},
    "IONQ": {"entry_date": "2026-05-01", "entry_price": 37.5, "shares": 10},
    "PDYN": {"entry_date": "2026-04-15", "entry_price": 12.1, "shares": 20},
    "WOLF": {"entry_date": "2026-08-01", "entry_price": 2.9, "shares": 100},
}


def _mock_gist_body(positions: dict, *, watchlist=None, truncated=False, content=None) -> dict:
    data = {"watchlist": watchlist if watchlist is not None else ["VEEA", "AMC", "WOLF"],
            "positions": positions}
    entry = {
        "truncated": truncated,
        "content": content if content is not None else json.dumps(data),
    }
    return {"files": {DATA_FILENAME: entry}}


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


def _run_workflow(env: dict, *, gist_sequence=None, patch_impl=None,
                   get_error: Exception | None = None,
                   patch_error: Exception | None = None):
    """Fuehrt den extrahierten Python-Block in einer Sandbox aus.

    ``gist_sequence`` ist eine Liste von Gist-JSON-Dicts, die bei
    aufeinanderfolgenden GET-Aufrufen zurueckgegeben werden (erster GET =
    gist_sequence[0], zweiter GET/Verifikation = gist_sequence[1], ...).
    Gibt (exit_code, stdout, stderr, patch_requests) zurueck.
    """
    import io
    import os
    import contextlib
    import unittest.mock as mock
    import urllib.request as real_urllib_request

    gist_sequence = list(gist_sequence or [])
    get_calls: list = []
    patch_calls: list = []

    def fake_urlopen(req, timeout=None):
        method = getattr(req, "method", None) or "GET"
        if method == "PATCH":
            patch_calls.append(req)
            if patch_error is not None:
                raise patch_error
            if patch_impl is not None:
                return patch_impl(req)
            return _FakeResponse(200)
        if get_error is not None:
            raise get_error
        idx = len(get_calls)
        get_calls.append(req)
        gist = gist_sequence[idx] if idx < len(gist_sequence) else gist_sequence[-1]
        return _FakeResponse(200, json.dumps(gist).encode("utf-8"))

    ns: dict = {"__name__": "__main__"}

    stdout_buf, stderr_buf = io.StringIO(), io.StringIO()
    exit_code = None
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf), \
         mock.patch.object(real_urllib_request, "urlopen", fake_urlopen), \
         mock.patch.dict(os.environ, env, clear=True):
        try:
            exec(compile(_PY_BLOCK, "<oneoff_remove_ghost_positions_v2>", "exec"), ns)
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 0
    assert exit_code is not None, "Block hat sys.exit() nicht aufgerufen"
    return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue(), patch_calls


def _base_env(**overrides) -> dict:
    env = {
        "GIST_ID": "testgist123",
        "GIST_TOKEN": "ghp_test_token_xyz",
        "TARGET_TICKER": "IONQ",
        "DRY_RUN": "true",
    }
    env.update(overrides)
    return env


# === 1 — YAML-Struktur ======================================================

def test_yaml_valid_and_dispatch_only():
    data = _load_yaml()
    assert data.get("name") == "One-off Remove Ghost Positions v2"
    trigger_key = True if True in data else "on"
    triggers = data[trigger_key]
    assert set(triggers.keys()) == {"workflow_dispatch"}, (
        "Trigger MUSS ausschliesslich workflow_dispatch sein")


def test_yaml_ticker_choice_only_grpn_ionq_pdyn():
    data = _load_yaml()
    trigger_key = True if True in data else "on"
    ticker_input = data[trigger_key]["workflow_dispatch"]["inputs"]["ticker"]
    assert ticker_input["type"] == "choice"
    assert set(ticker_input["options"]) == {"GRPN", "IONQ", "PDYN"}, (
        "Choice-Optionen MUESSEN exakt {GRPN, IONQ, PDYN} sein -- kein "
        "AMC/WOLF, kein Freitext")
    assert ticker_input["required"] is True


def test_yaml_dry_run_default_true():
    data = _load_yaml()
    trigger_key = True if True in data else "on"
    dry_run_input = data[trigger_key]["workflow_dispatch"]["inputs"]["dry_run"]
    assert dry_run_input["type"] == "boolean"
    assert dry_run_input["default"] is True


def test_yaml_permissions_empty():
    data = _load_yaml()
    assert data["permissions"] == {}, "permissions muss leer sein"


def test_yaml_concurrency_no_cancel():
    data = _load_yaml()
    conc = data["concurrency"]
    assert conc["group"] == "oneoff-remove-ghost-positions-v2"
    assert conc["cancel-in-progress"] is False, (
        "Ein laufender Schreib-Versuch darf nicht abgeschossen werden")


def test_yaml_no_checkout():
    src = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "actions/checkout" not in src, "Workflow soll ohne Checkout laufen"


def test_yaml_secrets_only_via_env():
    data = _load_yaml()
    step = data["jobs"]["remove-ghost-position"]["steps"][-1]
    assert step["env"]["GIST_ID"] == "${{ secrets.GIST_ID }}"
    assert step["env"]["GIST_TOKEN"] == "${{ secrets.GIST_TOKEN }}"
    assert "${{ secrets.GIST_TOKEN }}" not in step["run"]
    assert "${{ secrets.GIST_ID }}" not in step["run"]


# === 2 — Eingebetteter Python-Block ========================================

def test_embedded_python_syntax_ok():
    compile(_PY_BLOCK, "<oneoff_remove_ghost_positions_v2>", "exec")


# === 3 — Allowlist (AMC/WOLF-Schutz) =======================================

def test_amc_ticker_aborts_without_any_http_call():
    env = _base_env(TARGET_TICKER="AMC", DRY_RUN="false")
    code, out, err, patch_calls = _run_workflow(env, gist_sequence=[
        _mock_gist_body(_MOCK_POSITIONS)])
    assert code == 1
    assert "AMC" in err
    assert not patch_calls, "Bei AMC darf NIEMALS ein PATCH gesendet werden"


def test_wolf_ticker_aborts_without_any_http_call():
    env = _base_env(TARGET_TICKER="WOLF", DRY_RUN="false")
    code, out, err, patch_calls = _run_workflow(env, gist_sequence=[
        _mock_gist_body(_MOCK_POSITIONS)])
    assert code == 1
    assert "WOLF" in err
    assert not patch_calls, "Bei WOLF darf NIEMALS ein PATCH gesendet werden"


def test_arbitrary_other_ticker_aborts():
    for bad in ("GME", "TSLA", "", "GRPNX", "../etc"):
        env = _base_env(TARGET_TICKER=bad, DRY_RUN="false")
        code, out, err, patch_calls = _run_workflow(env, gist_sequence=[
            _mock_gist_body(_MOCK_POSITIONS)])
        assert code == 1, f"ticker={bad!r} sollte abbrechen"
        assert not patch_calls, f"ticker={bad!r} darf keinen PATCH ausloesen"


def test_allowlist_check_runs_before_any_gist_access():
    env = _base_env(TARGET_TICKER="AMC", DRY_RUN="false")
    code, out, err, patch_calls = _run_workflow(
        env, get_error=ConnectionError("sollte nie aufgerufen werden"))
    assert code == 1
    assert "ConnectionError" not in err
    assert "Allowlist" in err or "FEHLER" in err


# === 4 — Ticker nicht im Gist vorhanden ====================================

def test_ticker_not_present_no_write():
    positions_without_ionq = {k: v for k, v in _MOCK_POSITIONS.items() if k != "IONQ"}
    env = _base_env(TARGET_TICKER="IONQ", DRY_RUN="false")
    code, out, err, patch_calls = _run_workflow(env, gist_sequence=[
        _mock_gist_body(positions_without_ionq)])
    assert code == 0, err
    assert not patch_calls
    assert "NICHT vorhanden" in out
    assert "erledigt" in out


# === 5 — dry_run=true ======================================================

def test_dry_run_true_only_reads():
    env = _base_env(TARGET_TICKER="PDYN", DRY_RUN="true")
    code, out, err, patch_calls = _run_workflow(env, gist_sequence=[
        _mock_gist_body(_MOCK_POSITIONS)])
    assert code == 0, err
    assert not patch_calls
    assert "PROBELAUF" in out
    assert str(len(_MOCK_POSITIONS)) in out


def test_dry_run_default_env_missing_is_safe_true():
    env = _base_env(TARGET_TICKER="GRPN")
    del env["DRY_RUN"]
    code, out, err, patch_calls = _run_workflow(env, gist_sequence=[
        _mock_gist_body(_MOCK_POSITIONS)])
    assert code == 0, err
    assert not patch_calls
    assert "PROBELAUF" in out


# === 6 — Echter Lauf, Happy-Path ============================================

def test_real_run_happy_path_removes_only_target_ticker():
    positions_after = {k: v for k, v in _MOCK_POSITIONS.items() if k != "IONQ"}
    gist_before = _mock_gist_body(_MOCK_POSITIONS, watchlist=["VEEA", "AMC", "WOLF"])
    gist_after = _mock_gist_body(positions_after, watchlist=["VEEA", "AMC", "WOLF"])

    env = _base_env(TARGET_TICKER="IONQ", DRY_RUN="false")
    code, out, err, patch_calls = _run_workflow(
        env, gist_sequence=[gist_before, gist_after])
    assert code == 0, err
    assert len(patch_calls) == 1
    patch_req = patch_calls[0]

    sent_body = json.loads(patch_req.data.decode("utf-8"))
    sent_content = json.loads(sent_body["files"][DATA_FILENAME]["content"])
    assert "IONQ" not in sent_content["positions"]
    assert sent_content["positions"]["AMC"] == _MOCK_POSITIONS["AMC"]
    assert sent_content["positions"]["WOLF"] == _MOCK_POSITIONS["WOLF"]
    assert sent_content["positions"]["GRPN"] == _MOCK_POSITIONS["GRPN"]
    assert sent_content["positions"]["PDYN"] == _MOCK_POSITIONS["PDYN"]
    assert sent_content["watchlist"] == ["VEEA", "AMC", "WOLF"], (
        "watchlist muss unveraendert mitgeschrieben werden (volles "
        "Datei-Overwrite bei Gist-PATCH)")

    assert "ERFOLG" in out
    assert f"{len(_MOCK_POSITIONS)} -> {len(_MOCK_POSITIONS) - 1}" in out


def test_real_run_amc_and_wolf_subtree_byte_identical_before_after():
    positions_after = {k: v for k, v in _MOCK_POSITIONS.items() if k != "PDYN"}
    gist_before = _mock_gist_body(_MOCK_POSITIONS)
    gist_after = _mock_gist_body(positions_after)

    env = _base_env(TARGET_TICKER="PDYN", DRY_RUN="false")
    code, out, err, patch_calls = _run_workflow(
        env, gist_sequence=[gist_before, gist_after])
    assert code == 0, err
    assert "AMC unveraendert: True" in out
    assert "WOLF unveraendert: True" in out


def test_real_run_removes_grpn_specifically():
    positions_after = {k: v for k, v in _MOCK_POSITIONS.items() if k != "GRPN"}
    gist_before = _mock_gist_body(_MOCK_POSITIONS)
    gist_after = _mock_gist_body(positions_after)

    env = _base_env(TARGET_TICKER="GRPN", DRY_RUN="false")
    code, out, err, patch_calls = _run_workflow(
        env, gist_sequence=[gist_before, gist_after])
    assert code == 0, err
    assert "ERFOLG" in out
    sent_body = json.loads(patch_calls[0].data.decode("utf-8"))
    sent_content = json.loads(sent_body["files"][DATA_FILENAME]["content"])
    assert "GRPN" not in sent_content["positions"]


# === 7 — PATCH schlaegt fehl ================================================

def test_patch_failure_aborts_cleanly():
    import urllib.error
    env = _base_env(TARGET_TICKER="IONQ", DRY_RUN="false")
    patch_exc = urllib.error.HTTPError("https://api.github.com/gists/x", 403,
                                        "Forbidden", {}, None)
    code, out, err, patch_calls = _run_workflow(
        env, gist_sequence=[_mock_gist_body(_MOCK_POSITIONS)],
        patch_error=patch_exc)
    assert code == 1
    assert "ERFOLG" not in out
    assert "HTTPError" in err or "FEHLER" in err


# === 8 — Verifikation nach PATCH zeigt unerwartetes Ergebnis ===============

def test_verification_mismatch_ticker_still_present_is_critical():
    gist_before = _mock_gist_body(_MOCK_POSITIONS)
    gist_after_unexpected = _mock_gist_body(_MOCK_POSITIONS)  # IONQ noch da!

    env = _base_env(TARGET_TICKER="IONQ", DRY_RUN="false")
    code, out, err, patch_calls = _run_workflow(
        env, gist_sequence=[gist_before, gist_after_unexpected])
    assert code == 1
    assert "KRITISCH" in err
    assert "ERFOLG" not in out


def test_verification_wolf_changed_is_critical():
    positions_after_but_wolf_changed = {
        **{k: v for k, v in _MOCK_POSITIONS.items() if k != "IONQ"},
        "WOLF": {**_MOCK_POSITIONS["WOLF"], "entry_price": 999.0},
    }
    gist_before = _mock_gist_body(_MOCK_POSITIONS)
    gist_after = _mock_gist_body(positions_after_but_wolf_changed)

    env = _base_env(TARGET_TICKER="IONQ", DRY_RUN="false")
    code, out, err, patch_calls = _run_workflow(
        env, gist_sequence=[gist_before, gist_after])
    assert code == 1
    assert "KRITISCH" in err


def test_verification_amc_changed_is_critical():
    positions_after_but_amc_changed = {
        **{k: v for k, v in _MOCK_POSITIONS.items() if k != "IONQ"},
        "AMC": {**_MOCK_POSITIONS["AMC"], "entry_price": 999.0},
    }
    gist_before = _mock_gist_body(_MOCK_POSITIONS)
    gist_after = _mock_gist_body(positions_after_but_amc_changed)

    env = _base_env(TARGET_TICKER="IONQ", DRY_RUN="false")
    code, out, err, patch_calls = _run_workflow(
        env, gist_sequence=[gist_before, gist_after])
    assert code == 1
    assert "KRITISCH" in err


# === 9 — Log-Hygiene (keine Gist-Inhalte in Logs) ==========================

_SENSITIVE_VALUES = ["37.5", "12.1", "4.21", "2.9", "25.0",
                     "2026-05-01", "2026-04-15", "2026-10-01"]


def test_no_sensitive_values_in_logs_dry_run():
    env = _base_env(TARGET_TICKER="IONQ", DRY_RUN="true")
    code, out, err, _ = _run_workflow(env, gist_sequence=[
        _mock_gist_body(_MOCK_POSITIONS)])
    combined = out + err
    for val in _SENSITIVE_VALUES:
        assert val not in combined, f"sensibler Wert {val!r} ist im Log aufgetaucht"


def test_no_sensitive_values_in_logs_real_run():
    positions_after = {k: v for k, v in _MOCK_POSITIONS.items() if k != "IONQ"}
    env = _base_env(TARGET_TICKER="IONQ", DRY_RUN="false")
    code, out, err, _ = _run_workflow(env, gist_sequence=[
        _mock_gist_body(_MOCK_POSITIONS), _mock_gist_body(positions_after)])
    combined = out + err
    for val in _SENSITIVE_VALUES:
        assert val not in combined, f"sensibler Wert {val!r} ist im Log aufgetaucht"


def test_no_sensitive_values_in_logs_error_paths():
    env = _base_env(TARGET_TICKER="AMC", DRY_RUN="false")
    code, out, err, _ = _run_workflow(env, gist_sequence=[
        _mock_gist_body(_MOCK_POSITIONS)])
    combined = out + err
    for val in _SENSITIVE_VALUES:
        assert val not in combined


# === 10 — truncated / kaputtes JSON =========================================

def test_truncated_gist_aborts_without_write():
    env = _base_env(TARGET_TICKER="IONQ", DRY_RUN="false")
    gist = _mock_gist_body(_MOCK_POSITIONS, truncated=True)
    code, out, err, patch_calls = _run_workflow(env, gist_sequence=[gist])
    assert code == 1
    assert not patch_calls
    assert "truncated" in err


def test_corrupt_json_aborts_without_write():
    env = _base_env(TARGET_TICKER="IONQ", DRY_RUN="false")
    gist = _mock_gist_body(_MOCK_POSITIONS, content="{not valid json")
    code, out, err, patch_calls = _run_workflow(env, gist_sequence=[gist])
    assert code == 1
    assert not patch_calls


def test_missing_positions_key_aborts_without_write():
    env = _base_env(TARGET_TICKER="IONQ", DRY_RUN="false")
    gist = _mock_gist_body(_MOCK_POSITIONS, content=json.dumps({"watchlist": []}))
    code, out, err, patch_calls = _run_workflow(env, gist_sequence=[gist])
    assert code == 1
    assert not patch_calls


def test_missing_secrets_aborts():
    env = _base_env(GIST_ID="", DRY_RUN="false")
    code, out, err, patch_calls = _run_workflow(env, gist_sequence=[
        _mock_gist_body(_MOCK_POSITIONS)])
    assert code == 1
    assert not patch_calls


def main() -> None:
    tests = [
        ("YAML: nur workflow_dispatch",                      test_yaml_valid_and_dispatch_only),
        ("YAML: Ticker-Choice exakt GRPN/IONQ/PDYN",          test_yaml_ticker_choice_only_grpn_ionq_pdyn),
        ("YAML: dry_run Default true",                        test_yaml_dry_run_default_true),
        ("YAML: permissions leer",                            test_yaml_permissions_empty),
        ("YAML: concurrency-Gruppe, kein cancel",             test_yaml_concurrency_no_cancel),
        ("YAML: kein Checkout",                               test_yaml_no_checkout),
        ("YAML: Secrets nur via env:",                        test_yaml_secrets_only_via_env),
        ("Python-Block: Syntax OK",                           test_embedded_python_syntax_ok),
        ("Allowlist: AMC -> Abbruch ohne HTTP-Call",          test_amc_ticker_aborts_without_any_http_call),
        ("Allowlist: WOLF -> Abbruch ohne HTTP-Call",         test_wolf_ticker_aborts_without_any_http_call),
        ("Allowlist: beliebiger anderer Ticker -> Abbruch",   test_arbitrary_other_ticker_aborts),
        ("Allowlist-Check laeuft vor jedem Gist-Zugriff",     test_allowlist_check_runs_before_any_gist_access),
        ("Ticker nicht vorhanden -> kein Write",              test_ticker_not_present_no_write),
        ("dry_run=true liest nur",                            test_dry_run_true_only_reads),
        ("Fehlendes DRY_RUN -> sicher True",                  test_dry_run_default_env_missing_is_safe_true),
        ("Echter Lauf: nur Ziel-Ticker entfernt, Rest intakt", test_real_run_happy_path_removes_only_target_ticker),
        ("Echter Lauf: AMC+WOLF-Teilbaum byte-identisch",     test_real_run_amc_and_wolf_subtree_byte_identical_before_after),
        ("Echter Lauf: GRPN gezielt entfernt",                test_real_run_removes_grpn_specifically),
        ("PATCH-Fehler -> Abbruch, keine Erfolgsmeldung",     test_patch_failure_aborts_cleanly),
        ("Verifikations-Mismatch (Ticker noch da) -> KRITISCH", test_verification_mismatch_ticker_still_present_is_critical),
        ("Verifikations-Mismatch (WOLF veraendert) -> KRITISCH", test_verification_wolf_changed_is_critical),
        ("Verifikations-Mismatch (AMC veraendert) -> KRITISCH", test_verification_amc_changed_is_critical),
        ("Log-Hygiene: dry_run ohne sensible Werte",          test_no_sensitive_values_in_logs_dry_run),
        ("Log-Hygiene: echter Lauf ohne sensible Werte",      test_no_sensitive_values_in_logs_real_run),
        ("Log-Hygiene: Fehlerpfade ohne sensible Werte",      test_no_sensitive_values_in_logs_error_paths),
        ("Truncated Gist-Body -> Abbruch ohne Write",         test_truncated_gist_aborts_without_write),
        ("Kaputtes JSON -> Abbruch ohne Write",               test_corrupt_json_aborts_without_write),
        ("Fehlender positions-Key -> Abbruch ohne Write",     test_missing_positions_key_aborts_without_write),
        ("Fehlende Secrets -> Abbruch",                       test_missing_secrets_aborts),
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
