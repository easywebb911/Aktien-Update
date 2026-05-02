#!/usr/bin/env python3
"""Holt ``squeeze_data.json`` aus dem privaten User-Gist und
materialisiert daraus ``positions.json`` und ``watchlist_personal.json``
für den Daily-Run / KI-Agent-Tick.

Datenquelle:
    GIST_ID    — Gist-ID (Repo-Secret)
    GIST_TOKEN — PAT mit ``gist``-Scope (Repo-Secret)

Schema in Gist::

    {
      "watchlist": ["TICKER", ...],
      "positions": {
        "TICKER": {"entry_date": "YYYY-MM-DD",
                   "entry_price": 12.34,
                   "shares": 35}
      }
    }

Migration-Fallback: ist ``positions`` im Gist leer **und** das Repo-
Secret ``POSITIONS_JSON`` belegt, wird letzteres als ``positions.json``
geschrieben (legacy-Pfad). Watchlist hat keinen Legacy-Pfad — sie
wurde bislang per ``watchlist_personal.json`` direkt im Repo gepflegt;
fehlt der Gist-Eintrag, lassen wir die Datei unverändert (das
in-repo-File greift weiter).

Fail-soft: jede Stufe (kein Gist konfiguriert / API-Fehler / Parse-
Fehler) führt nicht zu Workflow-Abbruch — der Daily-Run läuft mit
der jeweils nächstbesten Quelle weiter.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


GIST_API = "https://api.github.com/gists/{}"
DATA_FILENAME = "squeeze_data.json"

POS_FILE = Path("positions.json")
WL_FILE  = Path("watchlist_personal.json")


def _http_get_gist(gist_id: str, token: str) -> dict | None:
    """GET https://api.github.com/gists/{id} → JSON-Dict oder None."""
    req = urllib.request.Request(
        GIST_API.format(gist_id),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept":        "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent":    "Aktien-Update-Workflow",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        print(f"[pull_gist_data] Gist-GET fehlgeschlagen: {exc}", file=sys.stderr)
    except json.JSONDecodeError as exc:
        print(f"[pull_gist_data] Gist-Body kein JSON: {exc}", file=sys.stderr)
    return None


def _extract_data(gist: dict) -> dict:
    """Liest ``squeeze_data.json`` aus den Gist-Files.

    Bei fehlender Datei oder Parse-Fehler → ``{"watchlist": [], "positions": {}}``.
    """
    files = (gist or {}).get("files") or {}
    entry = files.get(DATA_FILENAME) or {}
    raw = entry.get("content") or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[pull_gist_data] {DATA_FILENAME} kein JSON: {exc}", file=sys.stderr)
        return {"watchlist": [], "positions": {}}
    if not isinstance(data, dict):
        return {"watchlist": [], "positions": {}}
    data.setdefault("watchlist", [])
    data.setdefault("positions", {})
    return data


def _write_positions(positions: dict) -> None:
    POS_FILE.write_text(json.dumps(positions, ensure_ascii=False, indent=2),
                        encoding="utf-8")


def _write_watchlist(watchlist: list) -> None:
    WL_FILE.write_text(json.dumps(watchlist, ensure_ascii=False, indent=2),
                       encoding="utf-8")


def _legacy_positions_from_env() -> dict:
    raw = os.environ.get("POSITIONS_JSON", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        print("[pull_gist_data] POSITIONS_JSON-Env nicht parsebar — ignoriert",
              file=sys.stderr)
        return {}


def main() -> int:
    gist_id = os.environ.get("GIST_ID", "").strip()
    token   = os.environ.get("GIST_TOKEN", "").strip()
    legacy  = _legacy_positions_from_env()

    if not (gist_id and token):
        # Kein Gist konfiguriert — Legacy-POSITIONS_JSON gewinnt.
        _write_positions(legacy)
        # Watchlist bleibt unverändert (in-Repo watchlist_personal.json
        # ist die Quelle, Datei wird hier nicht überschrieben).
        print(f"[pull_gist_data] Kein Gist konfiguriert — "
              f"positions.json aus POSITIONS_JSON ({len(legacy)} Einträge)")
        return 0

    gist = _http_get_gist(gist_id, token)
    if gist is None:
        # API-Fehler: degradiere auf Legacy-Pfad, bricht aber nicht ab.
        _write_positions(legacy)
        print(f"[pull_gist_data] Gist-API-Fehler — Legacy-Fallback "
              f"({len(legacy)} Positions-Einträge)")
        return 0

    data = _extract_data(gist)
    positions = data.get("positions") or {}
    watchlist = data.get("watchlist") or []

    # Migration: Gist leer, aber POSITIONS_JSON gesetzt → Legacy-Daten
    # weiterverwenden bis User die Daten in den Gist umzieht.
    if not positions and legacy:
        print(f"[pull_gist_data] Gist-Positions leer, Migration aus "
              f"POSITIONS_JSON ({len(legacy)} Einträge); "
              f"bitte Gist manuell aktualisieren und POSITIONS_JSON danach löschen")
        positions = legacy

    _write_positions(positions)
    if isinstance(watchlist, list) and watchlist:
        _write_watchlist(watchlist)
    print(f"[pull_gist_data] Gist gelesen: "
          f"{len(positions)} Positions, {len(watchlist)} Watchlist-Ticker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
