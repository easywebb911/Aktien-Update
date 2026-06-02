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
from datetime import datetime, timezone
from pathlib import Path


GIST_API = "https://api.github.com/gists/{}"
DATA_FILENAME = "squeeze_data.json"

POS_FILE = Path("positions.json")
WL_FILE  = Path("watchlist_personal.json")
# Liveness-Marker (Schritt 1 von 2, 02.06.2026): wird AUSSCHLIESSLICH bei
# einem erfolgreichen HTTP-Gist-Read aktualisiert (siehe main()). Eigener
# State-File-Slot (NICHT app_data.json — dessen generated_at verjüngt sich
# bei jedem Daily-Run, „Self-refresh-Falle"). Ein späterer Health-Check
# (S14, separater PR) liest last_successful_gist_pull und alarmiert, wenn
# der Marker altert — d.h. wenn der Gist-Read über Zeit scheitert und der
# Recovery-Fallback geschlossene Positionen still als offen überbrückt
# (Vorfall 02.06.: toter GIST_TOKEN, mehrtägig unbemerkt). DIESER PR
# schreibt NUR den Marker — kein Check, kein Alarm, kein Verhaltens-Drift.
GIST_PULL_STATE_FILE = Path("gist_pull_state.json")


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


def _mark_successful_gist_pull(now_utc: datetime | None = None) -> None:
    """Schreibt ``last_successful_gist_pull`` (ISO-UTC) in den eigenen
    State-File. Atomic (tmp + os.replace, analog health_check_digest_state).
    Fail-soft: Schreibfehler werden geschluckt — der Marker ist Bonus-
    Telemetrie, der Pull selbst darf nie daran scheitern.

    Wird NUR im HTTP-Gist-Erfolgszweig aufgerufen (main()), nie im Recovery-
    oder gist-is-None-Zweig — so altert der Marker genau dann, wenn der
    Gist-Read über Zeit scheitert.
    """
    ts = (now_utc or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tmp = GIST_PULL_STATE_FILE.with_suffix(".json.tmp")
    try:
        tmp.write_text(
            json.dumps({"last_successful_gist_pull": ts},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        os.replace(tmp, GIST_PULL_STATE_FILE)
    except OSError as exc:
        print(f"[pull_gist_data] Marker-Write fehlgeschlagen (ignoriert): {exc}",
              file=sys.stderr)
        try:
            tmp.unlink()
        except OSError:
            pass


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


def _recover_positions_from_app_data(path: Path = Path("app_data.json")) -> dict:
    """Stammdaten-Recovery aus dem vorigen Daily-Run.

    ``app_data.json`` ist im Repo getrackt und enthält seit Phase 2
    Stufe 1 die Position-Stammdaten (``entry_date``, ``entry_price``,
    ``shares``) plus den derivierten ``exit_state`` mit Peak-Tracker.
    Bei einem Gist-API-Hiccup ist das die nächstbeste Quelle —
    Stammdaten sind quasi-immutable, Peaks (im Phase-2-Pfad via
    ``_read_existing_app_data`` beim nächsten Run gelesen) bleiben
    erhalten.

    Returnt ``{ticker: {entry_date, entry_price, shares}}`` (nur die
    Stammdaten, exit_state wird hier NICHT übernommen — der wird beim
    nächsten regulären Run aus den Stammdaten + History neu berechnet).
    Bei jedem Fehler / fehlender Datei → ``{}``.
    """
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[pull_gist_data] app_data.json-Recovery: Lesefehler ({exc})",
              file=sys.stderr)
        return {}
    positions = (data or {}).get("positions") or {}
    if not isinstance(positions, dict):
        return {}
    out: dict[str, dict] = {}
    for ticker, p in positions.items():
        if not isinstance(p, dict):
            continue
        if "entry_date" not in p or "entry_price" not in p:
            continue
        recovered = {
            "entry_date":  p.get("entry_date"),
            "entry_price": p.get("entry_price"),
        }
        if "shares" in p:
            recovered["shares"] = p.get("shares")
        # EUR-Stufe 1 (06.05.2026): entry_fx + fx_estimated mit recovern,
        # damit der eingefrorene Wechselkurs einen Gist-Hiccup überlebt.
        # Sonst würde die Bestandsposition beim nächsten Daily-Run als
        # „Erst-Sicht" behandelt und mit aktuellem FX als estimated neu
        # gestempelt — die Persistenz im app_data.json verlöre ihren Sinn.
        if "entry_fx" in p:
            recovered["entry_fx"] = p.get("entry_fx")
        if "fx_estimated" in p:
            recovered["fx_estimated"] = p.get("fx_estimated")
        # Trigger-4-Snapshot (Setup-Erosion): entry_dtc/entry_short_float/
        # entry_cost_to_borrow/entry_snapshot_ts müssen den Gist-Hiccup
        # überleben, sonst fällt der Trigger bei der nächsten Position
        # auf available=False zurück und die Empirik beginnt von vorn.
        for _snap_key in ("entry_dtc", "entry_short_float",
                          "entry_cost_to_borrow", "entry_snapshot_ts"):
            if _snap_key in p:
                recovered[_snap_key] = p.get(_snap_key)
        out[ticker] = recovered
    return out


def _fallback_positions(legacy: dict) -> tuple[dict, str]:
    """Wählt die nächstbeste Position-Quelle bei Gist-Fehler.

    Reihenfolge:
      1. Recovery aus voriger app_data.json (Stammdaten + Peak-Erhalt)
      2. POSITIONS_JSON-Secret-Legacy (deprecated, aber kompatibel)
      3. Leeres Dict (kein echter Recovery-Pfad verfügbar)

    Returnt ``(positions_dict, source_label)`` für strukturierte Logs.
    """
    recovered = _recover_positions_from_app_data()
    if recovered:
        return recovered, "app_data-recovery"
    if legacy:
        return legacy, "POSITIONS_JSON-legacy"
    return {}, "empty"


def main() -> int:
    gist_id = os.environ.get("GIST_ID", "").strip()
    token   = os.environ.get("GIST_TOKEN", "").strip()
    legacy  = _legacy_positions_from_env()

    if not (gist_id and token):
        # Kein Gist konfiguriert — Recovery-Kette: app_data → legacy → leer.
        positions, src = _fallback_positions(legacy)
        _write_positions(positions)
        # Watchlist bleibt unverändert (in-Repo watchlist_personal.json
        # ist die Quelle, Datei wird hier nicht überschrieben).
        print(f"[pull_gist_data] WARN: Kein Gist konfiguriert — "
              f"positions.json aus {src} ({len(positions)} Einträge)")
        return 0

    gist = _http_get_gist(gist_id, token)
    if gist is None:
        # API-Fehler: Recovery-Kette greift, Workflow bricht NICHT ab.
        # app_data-Recovery ist Peak-erhaltend — _read_existing_app_data
        # im Daily-Run findet weiterhin die alten peak-Werte für die
        # ratchet-up-Logik.
        positions, src = _fallback_positions(legacy)
        _write_positions(positions)
        print(f"[pull_gist_data] WARN: Gist-API-Fehler — Fallback aus "
              f"{src} ({len(positions)} Positions-Einträge)")
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
    # Liveness-Marker NUR hier (HTTP-Gist-Erfolg: _http_get_gist != None,
    # echte Gist-Daten geschrieben). Die beiden Recovery-Zweige (kein Gist
    # konfiguriert / Gist-API-Fehler) und der gist-is-None-Zweig schreiben
    # ihn bewusst NICHT → der Marker altert genau dann, wenn der Gist-Read
    # über Zeit scheitert (heutige Token-Tod-Klasse, Vorfall 02.06.).
    #
    # RESTKANTE (NICHT in diesem PR abgedeckt — separate Fehlerklasse,
    # eigener PR): Body-Korruption. Bei HTTP-200 + kaputtem squeeze_data.json
    # kollabiert _extract_data den Parse-Fehler still auf {"positions": {}}
    # (ununterscheidbar von „legitim alle geschlossen") — der Marker würde
    # dann fälschlich als Erfolg aktualisiert. Das ist NICHT der heutige
    # Token-Tod-Fall (dort ist _http_get_gist bereits None). Bewusst sichtbar
    # gelassen statt _extract_data anzufassen (Option B, kein Logik-Touch).
    _mark_successful_gist_pull()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
