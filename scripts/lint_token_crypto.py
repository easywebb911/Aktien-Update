#!/usr/bin/env python3
"""Lint: Token-Krypto-Invarianten in generate_report.py (CI-Gate, blockierend).

Prüft NUR harte, eindeutige Sicherheitsregeln aus der Master-Passwort-Token-
Encryption (CLAUDE.md „Master-Passwort-Token-Encryption (Phase 3)" + das dort
Z.~1665 dokumentierte grep-Pattern). KEINE Heuristik — jede Regel ist ein
deterministischer Pattern-Check gegen den realen Token-Code.

Hintergrund: Der Klartext-GitHub-PAT darf NUR in sessionStorage leben, der
verschlüsselte Blob in localStorage. Ein versehentliches Schreiben des
Klartext-Tokens nach localStorage, ein zweiter localStorage-Lesepfad außerhalb
des Legacy-Migrations-Helpers, ein Token-console.log oder ein versehentliches
Entfernen der AES-GCM/PBKDF2-Krypto wäre ein echter Sicherheitsfehler — kein
Geschmacks-Thema. Darum blockierend (Lint-Fail bricht den Workflow ab, analog
lint_jsformat_escape / lint_score_confidence_isolation).

Regeln (aus CLAUDE.md + Token-Code abgeleitet, NICHT erfunden):
  R1  localStorage.getItem(TOK_KEY) / (TOK_LEGACY_KEY) NUR im
      _getLegacyPlaintextToken-Helper bzw. der _tokSnapshot-Diagnose.
      (CLAUDE.md: "grep -n 'localStorage.getItem(TOK_KEY)' sollte außerhalb
      des _getLegacyPlaintextToken-Helper leer bleiben.")
  R2  Klartext-Token NIE nach localStorage SCHREIBEN:
      localStorage.setItem(TOK_KEY, ...) / (TOK_LEGACY_KEY, ...) verboten.
      (Klartext gehört in sessionStorage; localStorage nur für TOK_ENC_KEY-Blob.)
  R3  Kein console.*-Logging des Klartext-Tokens (token/pat als Variable).
  R4  Krypto-Primitive vorhanden (nicht versehentlich entfernt): AES-GCM,
      PBKDF2, _TOK_PBKDF2_ITER, _TOK_KEY_BITS müssen im Code existieren.

Exit-Code 0 = OK, 1 = Verstoß. Bei Verstoß werden Datei:Zeile + Regel geloggt.

Aufruf: ``python scripts/lint_token_crypto.py``
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_PATH = ROOT / "generate_report.py"

# Helper-Namen, in denen ein localStorage-Klartext-Lesepfad LEGITIM ist
# (Legacy-Migration + Diagnose-Snapshot). Außerhalb davon = Verstoß.
_ALLOWED_LS_READ_FUNCS = ("_getLegacyPlaintextToken", "_tokSnapshot")


def _strip_string_literals(line: str) -> str:
    """Entfernt einfache/doppelte/Backtick-String-Literale aus einer JS-Zeile,
    damit Wort-Treffer INNERHALB von Strings (Log-Labels wie 'Token-Setup …')
    nicht als Identifier-Match zählen. Bewusst simpel (keine vollständige
    JS-Lexer-Semantik) — reicht für die Single-Line-Log-Pattern hier."""
    out = re.sub(r"'[^']*'", "''", line)
    out = re.sub(r'"[^"]*"', '""', out)
    out = re.sub(r"`[^`]*`", "``", out)
    return out


def _enclosing_func(lines: list[str], idx: int) -> str:
    """Name der nächstgelegenen JS-Funktion oberhalb von Zeile idx (0-based).
    Sucht ``function NAME(`` oder ``const NAME = (...) =>`` / ``NAME = function``.
    """
    pat = re.compile(r'(?:function\s+([A-Za-z_$][\w$]*)\s*\(|'
                     r'(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*'
                     r'(?:async\s*)?(?:function|\())')
    for i in range(idx, -1, -1):
        m = pat.search(lines[i])
        if m:
            return m.group(1) or m.group(2) or "?"
    return "?"


def check(src: str) -> list[tuple[int, str, str]]:
    """Returnt Liste von (zeilennr_1based, regel, code_zeile)."""
    lines = src.splitlines()
    fails: list[tuple[int, str, str]] = []

    # R4 zuerst: Krypto-Primitive müssen existieren (global, nicht zeilenweise).
    for needle in ("AES-GCM", "PBKDF2", "_TOK_PBKDF2_ITER", "_TOK_KEY_BITS"):
        if needle not in src:
            fails.append((0, "R4", f"Krypto-Primitive fehlt im Code: {needle!r}"))

    for n, line in enumerate(lines, start=1):
        # R1 — localStorage.getItem(TOK_KEY|TOK_LEGACY_KEY) außerhalb erlaubter Funcs
        if re.search(r'localStorage\.getItem\(\s*(TOK_KEY|TOK_LEGACY_KEY)\s*\)', line):
            func = _enclosing_func(lines, n - 1)
            if func not in _ALLOWED_LS_READ_FUNCS:
                fails.append((n, "R1",
                              f"localStorage-Klartext-Token-Read in {func!r} "
                              f"(erlaubt nur in {_ALLOWED_LS_READ_FUNCS}): {line.strip()}"))

        # R2 — Klartext-Token nach localStorage SCHREIBEN (verboten)
        if re.search(r'localStorage\.setItem\(\s*(TOK_KEY|TOK_LEGACY_KEY)\b', line):
            fails.append((n, "R2",
                          f"Klartext-Token nach localStorage geschrieben "
                          f"(nur sessionStorage erlaubt): {line.strip()}"))

        # R3 — console.*-Logging einer token/pat-VARIABLE (blanker Identifier).
        #      Das Wort "Token" in einem String-Label ('Token-Setup …') ist
        #      KEIN Verstoß — nur ein geloggter Identifier `token`/`tok`/`pat`
        #      wäre Klartext-Leak. Vorgehen: String-Literale aus der Zeile
        #      strippen, DANN auf den blanken Identifier prüfen (Wort-Grenze,
        #      nicht gefolgt von \w/Punkt → schließt token.length / tokenLen aus).
        if "console." in line:
            stripped = _strip_string_literals(line)
            if re.search(r'console\.(log|warn|error|info|debug)\([^)]*'
                         r'\b(?:token|tok|pat)\b(?![\w.])', stripped, re.IGNORECASE):
                fails.append((n, "R3",
                              f"Mögliches Klartext-Token-Logging (Variable): "
                              f"{line.strip()}"))

    return fails


def main() -> None:
    if not SRC_PATH.exists():
        print(f"FEHLER: {SRC_PATH} nicht gefunden.")
        sys.exit(1)
    src = SRC_PATH.read_text(encoding="utf-8")
    fails = check(src)
    if not fails:
        print("OK: Token-Krypto-Invarianten erfüllt "
              "(R1 localStorage-Read-Scope, R2 kein Klartext-Write, "
              "R3 kein Token-Log, R4 Krypto-Primitive vorhanden).")
        sys.exit(0)
    print(f"FEHLER: {len(fails)} Token-Krypto-Verstoß/Verstöße:")
    for ln, rule, detail in fails:
        loc = f"generate_report.py:{ln}" if ln else "generate_report.py"
        print(f"  [{rule}] {loc} — {detail}")
    sys.exit(1)


if __name__ == "__main__":
    main()
