"""Health-Check Daily Digest (Phase 3).

Liest die letzten 24 h aus ``health_check_log.jsonl`` und
``provider_health.jsonl``, aggregiert State-Fails + Provider-Fails
(mit Konsekutiv-Counter für Tier-2/3), sendet **einen** ntfy-Push
pro Tag und persistiert die Konsekutiv-Counter in
``health_check_digest_state.json``.

Drei Push-Klassen:
  - „✅ Health-Check OK"             (default-priority) bei 0 Fails
  - „⚠️ Health-Check-Digest"          (high) bei ≥ 1 crit oder ≥ 3 warn
  - „📭 Health-Check ohne Daten"     (high) bei leeren JSONL-Files

Trigger: GitHub-Actions Cron ``13 8 * * *`` (analog ki_agent xx:17,
gegen GitHub-Actions-Last-Peak abgesichert).

Spec: ``docs/health_check_spec.md`` Sektion „Daily-Digest-Format".
Architektur-Anker: CLAUDE.md „Health-Check (Phase 3)".
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import health_check as hc           # noqa: E402
from config import (                # noqa: E402
    HEALTH_CHECK_PROVIDER_TIER,
    NTFY_ENABLED,
    NTFY_TOPIC,
)

try:
    import requests
except ImportError:
    requests = None   # type: ignore  # lokale Mock-Tests benötigen requests nicht

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("health_check_digest")

DIGEST_STATE_FILE = ROOT / "health_check_digest_state.json"
DIGEST_WINDOW_HOURS = 24
NTFY_URL = "https://ntfy.sh"


# ── State-Datei (Konsekutiv-Counter + Mehrfach-Trigger-Schutz) ─────────────


def _load_digest_state() -> dict:
    """Lädt ``health_check_digest_state.json``. Fail-soft: bei Fehler
    oder fehlender Datei → leeres Default-Dict. Datei wird vom Digest-
    Workflow allein verwaltet (keine Schreibe-Conflicts mit ki_agent
    oder Daily-Run)."""
    if not DIGEST_STATE_FILE.exists():
        return {
            "consecutive_failures": {},
            "last_seen":             {},
            "last_digest_sent":      None,
            "last_successful_run":   None,
        }
    try:
        return json.loads(DIGEST_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("digest-state lese-fail (start mit leerem state): %s", exc)
        return {
            "consecutive_failures": {},
            "last_seen":             {},
            "last_digest_sent":      None,
            "last_successful_run":   None,
        }


def _save_digest_state(state: dict) -> bool:
    """Schreibt State atomar (tmp + os.replace). Fail-soft."""
    tmp = DIGEST_STATE_FILE.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        os.replace(tmp, DIGEST_STATE_FILE)
        return True
    except OSError as exc:
        log.warning("digest-state schreibe-fail: %s", exc)
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        return False


# ── JSONL-Reader mit Fenster-Filter ────────────────────────────────────────


def _parse_ts(ts_str: str) -> datetime | None:
    """ISO-8601-Parser tolerant gegen Z-Suffix. None bei Fehler."""
    if not ts_str or not isinstance(ts_str, str):
        return None
    s = ts_str[:-1] + "+00:00" if ts_str.endswith("Z") else ts_str
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _load_jsonl_window(path: pathlib.Path,
                      cutoff: datetime) -> list[dict]:
    """Liest JSONL-File und gibt Einträge mit ``run_ts >= cutoff`` zurück.

    Kaputte Zeilen werden geskippt (log.warning) — keine Pipeline-
    Crashes wegen einer korrupten Zeile.
    """
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    log.warning("%s: kaputte Zeile übersprungen", path.name)
                    continue
                ts = _parse_ts(obj.get("run_ts", ""))
                if ts is None:
                    continue
                if ts >= cutoff:
                    out.append(obj)
    except OSError as exc:
        log.warning("%s: lese-fehler (skipped): %s", path.name, exc)
    return out


def _latest_run_ts(entries: list[dict]) -> str | None:
    """Letzten run_ts-String aus den entries (oder None)."""
    timestamps = [e.get("run_ts") for e in entries if e.get("run_ts")]
    return max(timestamps) if timestamps else None


# ── ntfy-Send (Mock-fähig) ────────────────────────────────────────────────


def _ntfy_send(title: str, body: str, priority: str,
               tags: str | None) -> bool:
    """Sendet Push via ntfy.sh. Fail-soft: Netzwerk-Fehler werden
    geloggt, kein Re-Raise — der Workflow kommt durch.

    ``NTFY_TOPIC`` leer oder ``NTFY_ENABLED=False`` → no-op
    (graceful skip), Body wird geloggt für Diagnose."""
    if not NTFY_ENABLED or not NTFY_TOPIC:
        log.info("ntfy disabled — Body würde sein:\n%s", body)
        return False
    if requests is None:
        log.warning("requests-Modul fehlt — ntfy-Push übersprungen")
        return False
    headers = {"Title": title, "Priority": priority}
    if tags:
        headers["Tags"] = tags
    try:
        resp = requests.post(
            f"{NTFY_URL}/{NTFY_TOPIC}",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        # Diagnose-Erweiterung (15.05.2026): HTTP-Status auch bei Success
        # loggen — beim ersten ausbleibenden Push (heute Morgen) konnten
        # wir nicht zwischen "Push gesendet, ntfy hat es geschluckt" und
        # "Push gefailed, return False" unterscheiden. INFO-Level damit
        # in Workflow-Logs sichtbar.
        if resp.status_code >= 400:
            log.warning("ntfy-Push HTTP %d (FAIL): %s",
                        resp.status_code, resp.text[:200])
            return False
        log.info("ntfy-Push HTTP %d (OK) — title=%r priority=%s",
                 resp.status_code, title, priority)
        return True
    except Exception as exc:
        # Diagnose-Erweiterung (15.05.2026): Exception-Type mit-loggen,
        # damit zwischen Timeout / ConnectionError / SSL-Fehler /
        # DNS-Fail unterschieden werden kann.
        log.warning("ntfy-Push Netzwerk-Fehler %s: %s",
                    type(exc).__name__, exc)
        return False


# ── Mehrfach-Trigger-Schutz ─────────────────────────────────────────────


def _already_sent_today(state: dict, today_iso: str) -> bool:
    """True wenn der Digest heute bereits gesendet wurde. Verhindert
    doppelten Push bei ``workflow_dispatch`` am selben Tag."""
    return state.get("last_digest_sent") == today_iso


# ── Main ─────────────────────────────────────────────────────────────────


def main(*, now_ts: datetime | None = None,
         force: bool = False,
         dry_run: bool = False) -> int:
    """Returnt Exit-Code: 0 = OK (Push gesendet oder skip), 1 = Fehler.

    ``force=True`` umgeht den Mehrfach-Trigger-Schutz (für Debug).
    ``dry_run=True`` schreibt State nicht zurück und sendet keinen
    Push — nur Stdout-Print für lokale Tests.
    """
    now_ts = now_ts or datetime.now(timezone.utc)
    today_iso = now_ts.strftime("%Y-%m-%d")
    cutoff = now_ts - timedelta(hours=DIGEST_WINDOW_HOURS)

    state = _load_digest_state()
    if _already_sent_today(state, today_iso) and not force:
        log.info("Digest heute (%s) bereits gesendet — skip.", today_iso)
        return 0

    state_entries = _load_jsonl_window(
        ROOT / hc.LOG_FILE, cutoff)
    prov_entries = _load_jsonl_window(
        ROOT / hc.LOG_FILE_PROVIDER, cutoff)

    state_fails = hc.aggregate_state_fails(state_entries)
    prov_fails  = hc.aggregate_provider_fails(
        prov_entries, state,
        tier_map=HEALTH_CHECK_PROVIDER_TIER,
        now_ts=now_ts,
    )

    n_runs = len(state_entries)
    last_run_iso = _latest_run_ts(state_entries) or _latest_run_ts(prov_entries)

    body, title, priority, tags = hc.format_digest_body(
        state_fails, prov_fails,
        n_runs=n_runs,
        last_run_iso=last_run_iso,
        digest_date=today_iso,
    )

    log.info("Digest %s — %d state-fails, %d provider-fails, %d runs",
             today_iso, len(state_fails), len(prov_fails), n_runs)
    if dry_run:
        print(f"[DRY-RUN] {title} (priority={priority})")
        print(body)
        return 0

    sent = _ntfy_send(title, body, priority, tags)
    if sent or not NTFY_TOPIC:
        # Wenn ntfy aktiv UND gesendet → mark today as sent.
        # Wenn ntfy disabled → trotzdem state-update, damit auch ohne
        # ntfy nicht mehrfach pro Tag gerechnet wird (lokale Test-Runs).
        state["last_digest_sent"] = today_iso
    if n_runs > 0 and not state_fails and not prov_fails:
        state["last_successful_run"] = (
            last_run_iso or now_ts.strftime("%Y-%m-%dT%H:%M:%SZ"))

    _save_digest_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
