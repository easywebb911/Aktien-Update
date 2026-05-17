"""Mock-Tests für _config.yml (Jekyll-Pages-Exclude).

Hintergrund: GitHub-Pages baut mit Jekyll und parsed jeden ``*.md`` durch
den Liquid-Template-Engine. PR #138 dokumentierte in CLAUDE.md wörtliche
``{{...}}``-Patterns (Python-f-String-Escape) → Liquid interpretiert sie
als Template-Variablen und der Pages-Build crashte mit „Variable
'{{ escapeden `{name}' was not properly terminated".

Fix: ``_config.yml`` mit ``exclude:``-Liste — interne Doku wird gar nicht
erst durch Jekyll geleitet.

Tests:
  1. _config.yml existiert und ist valides YAML
  2. exclude-Liste enthält die drei Liquid-unsicheren Doku-Files
  3. Code-/Daten-Stack auch ausgeschlossen (saubere Pages)
  4. *.json NICHT ausgeschlossen — Frontend fetched app_data.json
  5. README.md NICHT ausgeschlossen (Pages-Landing-Page)
  6. Realer Check: alle excludeden Files existieren auch tatsächlich

Ausführung: ``python scripts/mock_test_jekyll_exclude.py``.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_config():
    import yaml
    return yaml.safe_load((ROOT / "_config.yml").read_text(encoding="utf-8"))


# === 1 — Datei + YAML-Validität ============================================

def test_config_file_exists_and_parses():
    cfg_path = ROOT / "_config.yml"
    assert cfg_path.exists(), "_config.yml fehlt im Repo-Root"
    cfg = _load_config()
    assert isinstance(cfg, dict), f"_config.yml ist kein Dict: {type(cfg)}"
    assert "exclude" in cfg, "Key 'exclude' fehlt in _config.yml"
    assert isinstance(cfg["exclude"], list), "exclude muss eine Liste sein"


# === 2 — Liquid-unsichere Doku-Files explizit excluded =====================

def test_liquid_unsafe_docs_excluded():
    cfg = _load_config()
    excluded = set(cfg["exclude"])
    for required in ("CLAUDE.md", "SESSION_HANDOVER.md"):
        assert required in excluded, (
            f"{required} fehlt in exclude — Jekyll-Build wird wieder "
            f"crashen beim {{{{...}}}}-Pattern")
    # docs/ als Verzeichnis (statt einzelne Files)
    assert "docs/" in excluded or "docs" in excluded, (
        "docs/-Verzeichnis nicht excluded — Liquid-Risiko bei "
        "docs/health_check_spec.md o.ä.")


# === 3 — Code-/Build-Stack excluded ========================================

def test_code_and_build_stack_excluded():
    cfg = _load_config()
    excluded = set(cfg["exclude"])
    for required in ("*.py", "cloudflare/", "scripts/", "templates/",
                     "requirements.txt"):
        assert required in excluded, (
            f"{required} fehlt in exclude — gehört nicht in Pages-Output")


# === 4 — *.json NICHT excluded (Frontend braucht Daten-Files) ==============

def test_json_data_files_not_excluded():
    cfg = _load_config()
    excluded = set(cfg["exclude"])
    # *.json würde app_data.json, score_history.json, agent_signals.json,
    # backtest_history.json mit-killen → Frontend bekäme HTTP 404 beim
    # fetch('./app_data.json').
    assert "*.json" not in excluded, (
        "*.json darf NICHT exclude sein — sonst HTTP 404 beim Frontend-Fetch")
    # Auch keine individuellen Daten-JSONs
    for data_file in ("app_data.json", "score_history.json",
                      "agent_signals.json", "backtest_history.json"):
        assert data_file not in excluded, (
            f"{data_file} darf NICHT excluded sein — Frontend-Datenquelle")


# === 5 — README.md / index.html NICHT excluded =============================

def test_pages_landing_assets_not_excluded():
    cfg = _load_config()
    excluded = set(cfg["exclude"])
    # README.md ist optionale Landing-Page wenn kein index.html da wäre.
    # index.html ist die Haupt-App — auf gar keinen Fall excludieren.
    for keep in ("README.md", "index.html"):
        assert keep not in excluded, (
            f"{keep} darf NICHT excluded sein — Pages-Landing/App")


# === 6 — Existenz-Smoke: excludete Files existieren tatsächlich ============

def test_excluded_files_actually_exist():
    """Schützt vor Drift (Datei umbenannt, exclude vergessen zu aktualisieren).

    Wildcard-Patterns wie ``*.py`` werden übersprungen — wir prüfen nur
    konkrete Pfade.
    """
    cfg = _load_config()
    skipped = []
    for entry in cfg["exclude"]:
        if "*" in entry or entry in ("Gemfile", "Gemfile.lock"):
            # Wildcard oder optionale Ruby-Files — kein Existenz-Check
            skipped.append(entry)
            continue
        path = ROOT / entry.rstrip("/")
        assert path.exists(), (
            f"exclude-Eintrag {entry!r} verweist auf nicht existierende "
            f"Datei/Verzeichnis — Drift-Risiko")


# === Runner =================================================================

def main() -> None:
    tests = [
        ("_config.yml existiert + valides YAML",
         test_config_file_exists_and_parses),
        ("CLAUDE.md / SESSION_HANDOVER / docs/ in exclude",
         test_liquid_unsafe_docs_excluded),
        ("Code-/Build-Stack in exclude (*.py / cloudflare / scripts / templates)",
         test_code_and_build_stack_excluded),
        ("*.json NICHT excluded (Frontend-Daten)",
         test_json_data_files_not_excluded),
        ("README.md / index.html NICHT excluded",
         test_pages_landing_assets_not_excluded),
        ("Excludete Files existieren tatsächlich (Drift-Schutz)",
         test_excluded_files_actually_exist),
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
