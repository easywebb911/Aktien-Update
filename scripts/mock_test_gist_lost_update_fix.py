"""Mock-Tests für den Lost-Update-Fix in gistLoad/gistSave (31.10.2026).

Hintergrund (Diagnose 31.10.2026): Nach erfolgreicher Entfernung von
IONQ/PDYN aus dem Positions-Gist (Workflow-Runs 41212535664/41212644169,
14:57/14:59 UTC) standen beide um 17:43 UTC wieder im Gist -- ein
frischer, erfolgreicher Gist-Pull (``gist_pull_state.json``) hat das
bestätigt, kein stiller Recovery-Fallback.

Root Cause (Code-Beweis, keine Spekulation): ``gistLoad()``
(generate_report.py) cacht den Gist-Inhalt im Modul-Level-Var
``_GIST_DATA`` für die GESAMTE Lebensdauer der Seite/des Tabs --
populiert einmalig beim ``DOMContentLoaded``-Eager-Preload, NIE
invalidiert. Vier Schreib-Pfade (``_wlGistSyncWatchlist``,
``wlSubmitPosition``, ``wlSubmitClose``, ``wlRemoveFromExpanded``) lesen
diesen Cache, mutieren NUR ihr eigenes Feld (z.B. nur ``watchlist``),
und schreiben das GESAMTE ``data``-Objekt per PATCH zurück
(``gistSave``) -- ein klassisches Lost-Update-Muster. Ist der Cache
älter als eine externe Änderung (anderes Gerät, anderer Tab, oder --
wie demonstriert -- ein serverseitiger Wegwerf-Workflow), wird die
externe Änderung beim nächsten lokalen Schreibvorgang stillschweigend
überschrieben. iOS-Safari hält Tabs beim "Schließen" oft im Hintergrund
lebend statt sie neu zu laden (CLAUDE.md: Easy ist iPhone-Trader) --
genau das erklärt die 3-Stunden-Lücke zwischen Entfernung und
Rückkehr.

Repo-weiter Grep bestätigt: ``gistSave``/PATCH ist der EINZIGE
Schreibpfad für den Positions-Gist im gesamten Repo (kein Python-
Schreiber -- ``scripts/pull_gist_data.py`` liest nur per GET). Die
Ursache liegt also eindeutig in diesem einen Cache-Mechanismus, nicht
in einem der (bereits entfernten) Workflow-Läufe selbst.

Fix: ``gistLoad(force)`` -- ``force=true`` erzwingt einen echten
Netz-Fetch statt den Cache zu liefern. Alle VIER Schreib-Pfade rufen
jetzt ``gistLoad(true)`` statt ``gistLoad()`` -- lesen also
unmittelbar vor jedem Schreiben frisch, statt dem (ggf. stunden-/
tagealten) Cache zu vertrauen. Reine Lese-Pfade (Trade-Journal-Render,
Watchlist-Drawer-Refresh, DOMContentLoaded-Eager-Preload) bleiben
unverändert bei ``force=false`` (Default) -- kein zusätzlicher
Netz-Verkehr bei jedem Karten-Expand.

Tests:
  1. ``gistLoad`` hat ``force``-Parameter mit ``!force &&``-Cache-Guard
     (Source-Inspektion).
  2. Alle vier bekannten Schreib-Call-Sites nutzen ``gistLoad(true)``.
  3. Alle drei bekannten Lese-Call-Sites nutzen weiterhin ``gistLoad()``
     ohne Force (kein ungewollter Verhaltens-Drift / Netz-Mehrverkehr).
  4. Zählkonsistenz: genau 4× ``gistLoad(true)``, genau 3× ``gistLoad()``
     im gesamten File.
  5. ``gistSave`` aktualisiert den Cache nach Erfolg weiterhin
     (Regression-Guard -- Fix darf diesen Pfad nicht brechen).
  6. Python-Replikation der Cache-Semantik: ALTES Muster
     (``gistLoad(force=False)`` vor jedem Schreiben) lässt eine
     server-seitig gelöschte Position stillschweigend wieder aufleben
     -- Bug reproduziert, deterministisch, kein Netz.
  7. Python-Replikation: NEUES Muster (``gistLoad(force=True)`` vor
     jedem Schreiben) lässt die Löschung bestehen -- Fix verifiziert.
  8. In beiden Szenarien bleibt eine dritte, unberührte Position (AMC)
     byte-identisch -- der Fix ändert nichts an unbeteiligten Feldern.
  9. CLAUDE.md-Pflichtcheck: keine unescapten ``${...}``-Vars durch den
     Fix eingeführt.
"""
from __future__ import annotations

import copy
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")


# === 1 — gistLoad hat force-Parameter + Cache-Guard ========================

def test_gistLoad_has_force_param_and_guard():
    m = re.search(r"async function gistLoad\(force\)\s*\{\{", SRC)
    assert m, "gistLoad(force) Signatur nicht gefunden"
    tail = SRC[m.end():m.end() + 200]
    assert "if (!force && _GIST_DATA)" in tail, (
        "Cache-Guard muss !force prüfen, sonst bleibt der Fix wirkungslos")


# === 2 — Vier Schreib-Call-Sites nutzen gistLoad(true) =====================

_WRITE_CONTEXT_MARKERS = [
    "_wlGistSyncWatchlist",   # Watchlist-Sync (toggle/add/remove)
    "_entryThesis",           # wlSubmitPosition (Position eröffnen)
    "closed_trades: []",      # wlSubmitClose (Position schließen)
    "wlRemoveFromExpanded",   # Aus Watchlist entfernen
]


def _code_lines_with(pattern: str) -> list[str]:
    """Zeilen, die ``pattern`` enthalten UND keine reine Kommentarzeile
    sind (Zeile beginnt nach Trim nicht mit ``//``) -- filtert Doku-
    Erwähnungen des Patterns (z.B. in Kommentaren) aus echten Aufrufen."""
    return [l for l in SRC.splitlines()
            if pattern in l and not l.strip().startswith("//")]


def test_four_write_sites_use_forced_fresh_load():
    occurrences = _code_lines_with("gistLoad(true)")
    assert len(occurrences) == 4, (
        f"Erwartet genau 4 echte gistLoad(true)-Aufrufe (ein Treffer pro "
        f"Schreib-Pfad, Kommentarzeilen ausgeschlossen), gefunden: "
        f"{len(occurrences)}")
    # Jeder Marker muss NAH an einem gistLoad(true)-Aufruf stehen (gleiche
    # Funktion) -- grobe Nähe-Prüfung statt exakter AST-Zuordnung reicht,
    # da die Marker-Strings je Funktion eindeutig sind.
    for marker in _WRITE_CONTEXT_MARKERS:
        idx = SRC.index(marker)
        window = SRC[max(0, idx - 400):idx + 400]
        assert "gistLoad(true)" in window, (
            f"Marker {marker!r} hat keinen gistLoad(true)-Aufruf in "
            f"unmittelbarer Nähe -- Schreib-Pfad evtl. nicht gefixt")


# === 3 — Drei Lese-Call-Sites bleiben ungeforct =============================

def test_read_only_sites_remain_unforced():
    # Trade-Journal-Render: "const data = await gistLoad();"
    assert "const data = await gistLoad();" in SRC, (
        "Trade-Journal-Render-Pfad darf NICHT auf gistLoad(true) "
        "umgestellt sein (unnötiger Netz-Call bei jedem Render)")
    # wlExpand-Refresh nach ki_agent-Tick
    assert "gistLoad().then(() => _refreshPositionPanel(ticker)).catch(() => {{}});" in SRC
    # DOMContentLoaded Eager-Preload
    assert "gistLoad().catch(() => {{}});" in SRC


# === 4 — Zählkonsistenz =====================================================

def test_force_true_and_plain_call_counts_are_exact():
    forced = len(_code_lines_with("gistLoad(true)"))
    # "gistLoad()" ohne Argument, aber NICHT die Funktionsdefinition
    # selbst ("async function gistLoad(force)") und nicht Kommentar-Text.
    plain_calls = [l for l in _code_lines_with("gistLoad()")
                   if "function gistLoad" not in l]
    assert forced == 4, f"forced={forced}, erwartet 4"
    assert len(plain_calls) == 3, f"plain_calls={len(plain_calls)}, erwartet 3"


# === 5 — gistSave-Cache-Update-Regression-Guard =============================

def test_gistSave_still_updates_cache_on_success():
    m = re.search(r"async function gistSave\(data\)\s*\{\{", SRC)
    assert m, "gistSave nicht gefunden"
    rest = SRC[m.end():]
    next_fn = re.search(r"^\s*(?:async function|function)\s+\w+\(", rest, re.MULTILINE)
    body = rest[:next_fn.start()] if next_fn else rest
    assert "_GIST_DATA = _gistClone(data);" in body, (
        "gistSave muss den Cache nach erfolgreichem PATCH weiterhin "
        "aktualisieren -- der Fix ändert nur WANN frisch gelesen wird, "
        "nicht das Cache-Update nach dem Schreiben selbst")


# === 6/7/8 — Python-Replikation der Cache-Semantik =========================

class _MockGistBackend:
    """Simuliert den Server-seitigen Wahrheits-Zustand des Gist."""

    def __init__(self, data: dict):
        self.data = copy.deepcopy(data)


class _MockBrowserTab:
    """Repliziert exakt die gistLoad/gistSave-Cache-Semantik aus
    generate_report.py (Zeilen ~14960-15030): ``force=False`` liefert den
    Cache falls vorhanden, ``force=True`` erzwingt einen echten Fetch.
    ``gistSave`` überschreibt den GESAMTEN Backend-Zustand (PATCH-Semantik,
    kein Teil-Merge) und aktualisiert danach den Cache."""

    def __init__(self, backend: _MockGistBackend):
        self.backend = backend
        self._cache: dict | None = None

    def gist_load(self, force: bool = False) -> dict:
        if not force and self._cache is not None:
            return copy.deepcopy(self._cache)
        self._cache = copy.deepcopy(self.backend.data)
        return copy.deepcopy(self._cache)

    def gist_save(self, data: dict) -> bool:
        self.backend.data = copy.deepcopy(data)
        self._cache = copy.deepcopy(data)
        return True


def _initial_gist_state() -> dict:
    return {
        "watchlist": ["AMC", "WOLF"],
        "positions": {
            "AMC":  {"entry_date": "2026-09-28"},
            "IONQ": {"entry_date": "2026-05-01"},
            "PDYN": {"entry_date": "2026-04-15"},
        },
    }


def test_old_pattern_resurrects_server_side_deletion():
    """Bug-Reproduktion: Tab cacht VOR der serverseitigen Löschung,
    nutzt danach das ALTE Aufruf-Muster (force=False) für einen
    Watchlist-Schreibvorgang -> IONQ/PDYN leben wieder auf."""
    backend = _MockGistBackend(_initial_gist_state())
    tab = _MockBrowserTab(backend)

    # Seitenladen (DOMContentLoaded-Eager-Preload) -- Cache populiert MIT
    # IONQ/PDYN, bevor die serverseitige Bereinigung läuft.
    tab.gist_load(force=False)

    # Serverseitige Bereinigung (unser Wegwerf-Workflow) läuft NACH dem
    # Cache-Populieren dieses Tabs.
    del backend.data["positions"]["IONQ"]
    del backend.data["positions"]["PDYN"]
    assert "IONQ" not in backend.data["positions"]
    assert "PDYN" not in backend.data["positions"]

    # Easy tippt (auf dem WEITERHIN offenen Tab) irgendeine Watchlist-
    # Aktion an -- ALTES Muster: gistLoad() OHNE force.
    data = tab.gist_load(force=False)  # liefert STALE Cache mit IONQ/PDYN
    data["watchlist"] = data["watchlist"] + ["SOMETHING"]
    tab.gist_save(data)

    assert "IONQ" in backend.data["positions"], (
        "Bug nicht reproduziert -- IONQ sollte durch das Lost-Update "
        "wieder auftauchen")
    assert "PDYN" in backend.data["positions"], (
        "Bug nicht reproduziert -- PDYN sollte durch das Lost-Update "
        "wieder auftauchen")


def test_new_pattern_preserves_server_side_deletion():
    """Fix-Verifikation: identisches Szenario, aber der Schreibvorgang
    nutzt das NEUE Muster (force=True) -> IONQ/PDYN bleiben gelöscht."""
    backend = _MockGistBackend(_initial_gist_state())
    tab = _MockBrowserTab(backend)

    tab.gist_load(force=False)  # Eager-Preload, identisch zum Bug-Test

    del backend.data["positions"]["IONQ"]
    del backend.data["positions"]["PDYN"]

    # NEUES Muster: gistLoad(force=True) unmittelbar vor dem Schreiben.
    data = tab.gist_load(force=True)  # liest FRISCH -> sieht die Löschung
    data["watchlist"] = data["watchlist"] + ["SOMETHING"]
    tab.gist_save(data)

    assert "IONQ" not in backend.data["positions"], (
        "Fix wirkungslos -- IONQ sollte NICHT wieder auftauchen")
    assert "PDYN" not in backend.data["positions"], (
        "Fix wirkungslos -- PDYN sollte NICHT wieder auftauchen")


def test_amc_untouched_in_both_scenarios():
    """AMC ist in keinem der beiden Szenarien beteiligt -- muss in
    beiden Fällen byte-identisch (als Dict-Vergleich) bleiben."""
    amc_ref = _initial_gist_state()["positions"]["AMC"]

    # Bug-Szenario
    backend = _MockGistBackend(_initial_gist_state())
    tab = _MockBrowserTab(backend)
    tab.gist_load(force=False)
    del backend.data["positions"]["IONQ"]
    del backend.data["positions"]["PDYN"]
    data = tab.gist_load(force=False)
    data["watchlist"] = data["watchlist"] + ["SOMETHING"]
    tab.gist_save(data)
    assert backend.data["positions"]["AMC"] == amc_ref

    # Fix-Szenario
    backend2 = _MockGistBackend(_initial_gist_state())
    tab2 = _MockBrowserTab(backend2)
    tab2.gist_load(force=False)
    del backend2.data["positions"]["IONQ"]
    del backend2.data["positions"]["PDYN"]
    data2 = tab2.gist_load(force=True)
    data2["watchlist"] = data2["watchlist"] + ["SOMETHING"]
    tab2.gist_save(data2)
    assert backend2.data["positions"]["AMC"] == amc_ref


# === 9 — CLAUDE.md-Pflichtcheck =============================================

def test_no_unescaped_dollar_vars_introduced():
    hits = [(i + 1, l.strip()) for i, l in enumerate(SRC.splitlines())
            if re.search(r"\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}", l)]
    assert not hits, f"Unescapte \\${{...}}-Vars gefunden: {hits[:5]}"


def main() -> None:
    tests = [
        ("gistLoad(force)-Signatur + Cache-Guard",       test_gistLoad_has_force_param_and_guard),
        ("4 Schreib-Sites nutzen gistLoad(true)",         test_four_write_sites_use_forced_fresh_load),
        ("3 Lese-Sites bleiben ungeforct",                test_read_only_sites_remain_unforced),
        ("Zählkonsistenz force/plain",                    test_force_true_and_plain_call_counts_are_exact),
        ("gistSave aktualisiert Cache weiterhin",         test_gistSave_still_updates_cache_on_success),
        ("Bug-Reproduktion: altes Muster weckt Geister",  test_old_pattern_resurrects_server_side_deletion),
        ("Fix-Verifikation: neues Muster hält Löschung",  test_new_pattern_preserves_server_side_deletion),
        ("AMC unberührt in beiden Szenarien",             test_amc_untouched_in_both_scenarios),
        ("Keine unescapten \\${...}-Vars",                test_no_unescaped_dollar_vars_introduced),
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
