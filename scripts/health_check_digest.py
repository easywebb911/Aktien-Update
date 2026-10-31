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
# scripts/ selbst zusätzlich voranstellen (22.10.2026) — ``freeze_eval``
# (scripts/freeze_eval.py) wird lazy innerhalb von main() importiert; beim
# Laden dieses Moduls über ``importlib.util.spec_from_file_location``
# (Test-Harness-Muster, siehe scripts/mock_test_digest.py) fügt Python NICHT
# automatisch das eigene Skript-Verzeichnis zu sys.path hinzu (anders als
# beim direkten ``python scripts/health_check_digest.py``-Aufruf) — ohne
# diese Zeile würde der Test-Import scheitern.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import health_check as hc           # noqa: E402
from config import (                # noqa: E402
    HEALTH_CHECK_PROVIDER_TIER,
    NTFY_ENABLED,
    NTFY_TOPIC,
    EVAL_AUTORUN_ENABLED,
    SETUP_EDGE_FREEZE_N_TARGET,
    KI_SCORE_FREEZE_N_TARGET,
    EVAL_RESULTS_FILE,
)

try:
    import requests
except ImportError:
    requests = None   # type: ignore  # lokale Mock-Tests benötigen requests nicht

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("health_check_digest")

DIGEST_STATE_FILE = ROOT / "health_check_digest_state.json"
DIGEST_WINDOW_HOURS = 24


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
    """Sendet Push via ntfy.sh URL-Pattern (POST /{topic}). Fail-soft:
    Netzwerk-Fehler werden geloggt, kein Re-Raise.

    ``NTFY_TOPIC`` leer oder ``NTFY_ENABLED=False`` → no-op
    (graceful skip), Body wird geloggt für Diagnose.

    URL-Pattern-Adoption (17.05.2026): die JSON-API-Variante
    (``POST https://ntfy.sh/`` + ``json={"topic": ...}``) hat auf
    ntfy.sh nicht zuverlaessig gepusht — ``last_digest_sent`` blieb
    seit 15.05. trotz Workflow-Runs auf ``null``. Andere ntfy-Sender
    im Tool (``ki_agent._send_anomaly_ntfy``, ``_send_exit_p2_push``)
    nutzen das URL-Pattern und funktionieren zuverlaessig — analog
    adoptiert. Title MUSS ASCII-only sein (HTTP-Header-Limit per
    RFC 7230 latin-1); Emoji-Reste aus ``format_digest_body`` werden
    via ``.encode("ascii", "ignore")`` herausgefiltert. Body bleibt
    UTF-8 (laeuft als ``data=``-Body, kein Header).
    """
    if not NTFY_ENABLED or not NTFY_TOPIC:
        log.info("ntfy disabled — Body würde sein:\n%s", body)
        return False
    if requests is None:
        log.warning("requests-Modul fehlt — ntfy-Push übersprungen")
        return False
    # ASCII-clean title: HTTP-Header-Konstraints umgehen. Body bleibt UTF-8.
    title_ascii = title.encode("ascii", "ignore").decode("ascii").strip()
    if not title_ascii:
        title_ascii = "Health-Check"
    headers = {
        "Title":    title_ascii,
        "Priority": priority,
    }
    if tags:
        headers["Tags"] = tags
    try:
        resp = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        # Diagnose-Erweiterung (15.05.2026): HTTP-Status auch bei Success
        # loggen — beim ersten ausbleibenden Push konnten wir nicht
        # zwischen "Push gesendet, ntfy hat es geschluckt" und "Push
        # gefailed, return False" unterscheiden. INFO-Level damit in
        # Workflow-Logs sichtbar.
        if resp.status_code >= 400:
            log.warning("ntfy-Push HTTP %d (FAIL): %s",
                        resp.status_code, resp.text[:200])
            return False
        log.info("ntfy-Push HTTP %d (OK) — title=%r priority=%s",
                 resp.status_code, title_ascii, priority)
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
    """Returnt Exit-Code:
      0 = OK (Push gesendet / ntfy disabled / dry-run / skip)
      1 = ntfy-Send-Fail bei aktivem NTFY_TOPIC (16.05.2026 — macht
          GitHub-Actions-Run rot, Email-Notification an Easy).

    ``force=True`` umgeht den Mehrfach-Trigger-Schutz (für Debug).
    ``dry_run=True`` schreibt State nicht zurück und sendet keinen
    Push — nur Stdout-Print für lokale Tests.

    State-Datei wird IMMER vor dem Exit-Code-Return geschrieben
    (außer dry_run), damit Cooldown-Logik auch bei ntfy-Fail wirkt
    und der Workflow-Commit-Step (``if: always()``) den Stand
    persistieren kann.
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

    # §4-Re-Test-Zähler (fail-soft, backend-only): eine Zeile im Push-Body.
    # retest_counter_line ist bereits raise-frei; der try/except ist reine
    # Absicherung, damit der Digest durch diese Zeile unter KEINEN Umständen
    # scheitert (fällt sonst auf „keine Zeile" zurück).
    try:
        retest_line = hc.retest_counter_line(ROOT / hc.MATURED_EXPORT_FILE)
    except Exception as _rc_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("retest_counter_line unerwartet: %r", _rc_exc)
        retest_line = None

    # Setup-Edge/Conviction-Freeze-Zähler (fail-soft, backend-only, 11.10.2026):
    # eine Zeile "🧪 Freeze-Zähler" im Push-Body, analog zum §4-Zähler oben —
    # freeze_counter_line ist bereits raise-frei (eigener Außen-Guard); der
    # try/except ist reine Absicherung, damit der Digest durch diese Zeile
    # unter KEINEN Umständen scheitert.
    try:
        freeze_line = hc.freeze_counter_line(
            ROOT / hc.MATURED_EXPORT_FILE, ROOT / hc.BACKTEST_FILE)
    except Exception as _fz_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("freeze_counter_line unerwartet: %r", _fz_exc)
        freeze_line = None

    # inst_ownership_history-Liveness (fail-soft, backend-only): eine Zeile im
    # Body. Zeigt LIVENESS (läuft/noch-nie/kaputt), nicht Änderungen — 13F ist
    # quartalsweise. WICHTIG: der Sammler läuft NUR im Daily-Run, NICHT im
    # stündlichen ki_agent-Tick — deshalb die Frische gegen
    # latest_daily_run_ts (premarket/postclose) messen, NICHT gegen das
    # generische last_run_iso (das der stündliche ki_agent frisch hält und damit
    # einen toten Daily-Run maskieren würde). inst_ownership_liveness_line ist
    # raise-frei; try/except ist reine Absicherung, damit der Digest durch diese
    # Zeile NIE scheitert.
    try:
        # DEDIZIERTES weiteres Fenster: der 24h-``state_entries``-Cutoff könnte
        # den letzten Daily-Run (Wochenende/Montag-Morgen ≈ 82 h) NICHT sehen →
        # latest_daily_run_ts wäre dann None → Fehlalarm jeden Sonntag/Montag.
        # Deshalb den Daily-Run-Liveness-Anker gegen ein 96h-Fenster laden (>
        # der 90h-Schwelle, damit der Freitag-postclose am Montag noch sichtbar).
        _liveness_entries = _load_jsonl_window(
            ROOT / hc.LOG_FILE,
            now_ts - timedelta(hours=hc._INST_OWN_LOOKBACK_HOURS))
        _daily_run_iso = hc.latest_daily_run_ts(_liveness_entries)
        inst_own_line = hc.inst_ownership_liveness_line(
            ROOT / hc.INST_OWNERSHIP_HISTORY_FILE,
            last_run_iso=_daily_run_iso, now_ts=now_ts)
    except Exception as _io_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("inst_ownership_liveness_line unerwartet: %r", _io_exc)
        inst_own_line = None

    # options_oi-Liveness: KEIN Daily-Run-Fenster nötig — der Sammler läuft nur
    # postclose und die Frische kommt aus dem neuesten ``date`` in der Datei selbst
    # (postclose-aware). raise-frei; try/except ist reine Absicherung.
    try:
        options_oi_line = hc.options_oi_liveness_line(
            ROOT / hc.OPTIONS_OI_HISTORY_FILE, now_ts=now_ts)
    except Exception as _oi_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("options_oi_liveness_line unerwartet: %r", _oi_exc)
        options_oi_line = None

    # options_chain_raw-Liveness (17.10.2026): analog options_oi, eigene Datei
    # (JSONL). raise-frei; try/except ist reine Absicherung.
    try:
        chain_raw_line = hc.options_chain_raw_liveness_line(
            ROOT / hc.OPTIONS_CHAIN_RAW_FILE, now_ts=now_ts)
    except Exception as _ocr_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("options_chain_raw_liveness_line unerwartet: %r", _ocr_exc)
        chain_raw_line = None

    # News-Coverage-Watchdog (21.10.2026): analog options_chain_raw, eigene
    # Datei (JSONL). raise-frei; try/except ist reine Absicherung.
    try:
        news_coverage_line = hc.news_coverage_liveness_line(
            ROOT / hc.NEWS_COVERAGE_LOG_FILE, now_ts=now_ts)
    except Exception as _ncov_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("news_coverage_liveness_line unerwartet: %r", _ncov_exc)
        news_coverage_line = None
    try:
        news_coverage_warn = hc.news_coverage_warn_line(
            ROOT / hc.NEWS_COVERAGE_LOG_FILE, now_ts=now_ts)
    except Exception as _ncovw_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("news_coverage_warn_line unerwartet: %r", _ncovw_exc)
        news_coverage_warn = None

    # Reddit-Aufmerksamkeits-Schattensammlung (ApeWisdom, 23.10.2026): eigene
    # Digest-Zeile analog news_coverage_line — rein deskriptiv, KEIN Score-/
    # Push-/Top-10-Bezug. raise-frei; try/except ist reine Absicherung.
    try:
        apewisdom_line = hc.apewisdom_attention_digest_line(
            ROOT / hc.APEWISDOM_ATTENTION_LOG_FILE, now_ts=now_ts)
    except Exception as _apew_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("apewisdom_attention_digest_line unerwartet: %r", _apew_exc)
        apewisdom_line = None

    # Generischer Daten-Abdeckungs-Wächter (21.10.2026): je Quelle eine
    # Liveness-Zeile + optionale Warnzeile, plus EINE Übersichtszeile.
    # raise-frei; try/except ist reine Absicherung.
    coverage_lines: list[str] = []
    coverage_warns: list[str] = []
    coverage_silent_empty_warns: list[str] = []
    # Bekannt tote Quellen (Wächter, Easy-Entscheid 23.10.2026): ℹ️-Zeile
    # statt Liveness + ⚠️, solange das open_item offen/beobachtet ist und
    # die Quelle keine Daten liefert. raise-frei (fail-soft → {}).
    try:
        _known_dead = hc.known_dead_coverage_quellen(
            ROOT / hc.OPEN_ITEMS_FILE, ROOT / hc.COVERAGE_LOG_FILE, now_ts=now_ts)
    except Exception as _kd_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("known_dead_coverage_quellen unerwartet: %r", _kd_exc)
        _known_dead = {}
    for _q in hc.COVERAGE_QUELLEN:
        if _q in _known_dead:
            coverage_lines.append(hc.coverage_known_dead_line(_q, _known_dead[_q]))
            continue
        try:
            _recovered = hc.coverage_recovered_line(
                _q, ROOT / hc.OPEN_ITEMS_FILE, ROOT / hc.COVERAGE_LOG_FILE,
                now_ts=now_ts)
            if _recovered:
                coverage_warns.append(_recovered)
        except Exception as _rec_exc:  # pragma: no cover — Helper ist raise-frei
            log.warning("coverage_recovered_line(%s) unerwartet: %r", _q, _rec_exc)
        try:
            coverage_lines.append(hc.coverage_liveness_line(
                _q, ROOT / hc.COVERAGE_LOG_FILE, now_ts=now_ts))
        except Exception as _cov_exc:  # pragma: no cover — Helper ist raise-frei
            log.warning("coverage_liveness_line(%s) unerwartet: %r", _q, _cov_exc)
        try:
            _warn = hc.coverage_warn_line(_q, ROOT / hc.COVERAGE_LOG_FILE, now_ts=now_ts)
            if _warn:
                coverage_warns.append(_warn)
        except Exception as _covw_exc:  # pragma: no cover — Helper ist raise-frei
            log.warning("coverage_warn_line(%s) unerwartet: %r", _q, _covw_exc)
        # Stiller-Leer-Ausfall (22.10.2026): misst n_mit_daten statt
        # n_erhalten — fängt Fälle, in denen der Call antwortet, aber
        # inhaltlich immer leer bleibt (das Karten-News-Muster, #593).
        try:
            _silent_warn = hc.coverage_silent_empty_warn_line(
                _q, ROOT / hc.COVERAGE_LOG_FILE, now_ts=now_ts)
            if _silent_warn:
                coverage_silent_empty_warns.append(_silent_warn)
        except Exception as _covs_exc:  # pragma: no cover — Helper ist raise-frei
            log.warning("coverage_silent_empty_warn_line(%s) unerwartet: %r", _q, _covs_exc)
    try:
        coverage_overview = hc.coverage_overview_line(
            ROOT / hc.COVERAGE_LOG_FILE, now_ts=now_ts,
            exclude=set(_known_dead))
    except Exception as _covo_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("coverage_overview_line unerwartet: %r", _covo_exc)
        coverage_overview = None

    # FTD-Liveness: Heartbeat-basiert (Sidecar-State), kein Daily-Run-Fenster nötig.
    try:
        ftd_line = hc.ftd_liveness_line(
            ROOT / hc.FTD_HISTORY_FILE, ROOT / hc.FTD_HISTORY_STATE_FILE, now_ts=now_ts)
    except Exception as _ftd_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("ftd_liveness_line unerwartet: %r", _ftd_exc)
        ftd_line = None

    # Reg-SHO-Liveness: heartbeat-basiert (Sidecar-State), analog FTD.
    try:
        reg_sho_line = hc.reg_sho_liveness_line(
            ROOT / hc.REG_SHO_HISTORY_FILE, ROOT / hc.REG_SHO_HISTORY_STATE_FILE,
            now_ts=now_ts)
    except Exception as _rs_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("reg_sho_liveness_line unerwartet: %r", _rs_exc)
        reg_sho_line = None

    # Fällige Wiedervorlagen (22.10.2026, TÄGLICH — kein Montag-Gate wie der
    # Wochenblock unten): liest ``faellig_am`` aus open_items.json. raise-frei;
    # try/except ist reine Absicherung.
    try:
        due_items_lines_ = hc.due_items_lines(now_ts, path=ROOT / hc.OPEN_ITEMS_FILE)
    except Exception as _due_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("due_items_lines unerwartet: %r", _due_exc)
        due_items_lines_ = []

    # Freeze-Auswertungs-Autorun (Erratum 22.10.2026, scripts/freeze_eval.py):
    # EINMALIGER automatischer Auslöser für die Setup-Edge/Conviction- und
    # KI-Score-Edge-Test-Freezes, sobald n>=250 erreicht ist. Master-Switch
    # ``EVAL_AUTORUN_ENABLED`` (Default False) — bei False bleiben nur die
    # Vor-Auslöser-Zähler-Zeilen aktiv (reine Zählung, kein Auswertungs-
    # Versuch, kein eval_results.jsonl-Write). try/except ist DOPPELTE
    # Absicherung zusätzlich zu den fail-soft-Bausteinen in freeze_eval.py
    # selbst (BAU-Vorgabe: Fehler im Skript -> Digest-Warnung, kein
    # Ergebnis-Eintrag, Report unberührt).
    eval_lines: list[str] = []
    try:
        setup_pop = hc._count_setup_edge_freeze_population(ROOT / hc.MATURED_EXPORT_FILE)
        setup_rate = hc._freeze_rate_last_14d(ROOT / hc.MATURED_EXPORT_FILE, now=now_ts)
        ki_pop = hc._count_ki_score_freeze_population(ROOT / hc.MATURED_EXPORT_FILE)
        ki_rate = hc._ki_score_freeze_rate_last_14d(ROOT / hc.MATURED_EXPORT_FILE, now=now_ts)

        setup_verdict_text = None
        ki_verdict_text = None

        if EVAL_AUTORUN_ENABLED:
            import freeze_eval  # noqa: E402  (lazy — nur wenn Autorun aktiv)
            eval_out = freeze_eval.run_due_evaluations(
                export_path=ROOT / hc.MATURED_EXPORT_FILE,
                results_path=ROOT / EVAL_RESULTS_FILE,
                now=now_ts,
            )
            for trig in eval_out["just_triggered"]:
                summary = "; ".join(
                    f"{tid}: {verdict}" for tid, (verdict, _reason) in trig["verdicts"].items())
                push_body = (
                    f"Auslöser n>=250 erreicht ({trig['label']}). Verdikt je Test: "
                    f"{summary}. Details in {EVAL_RESULTS_FILE}.")
                try:
                    _ntfy_send(f"Freeze-Auswertung: {trig['label']}", push_body,
                              "high", "science")
                except Exception as _push_exc:  # pragma: no cover
                    log.warning("Eval-Autorun-Push fehlgeschlagen (%s): %r",
                               trig["family"], _push_exc)
                if trig["family"] == "setup_edge_conviction":
                    setup_verdict_text = summary
                elif trig["family"] == "ki_score":
                    ki_verdict_text = summary
            # Status nach einem evtl. gerade erfolgten Trigger neu lesen
            # (verdict_text gewinnt gegen die Vor-Auslöser-Zahlen).
            if eval_out["setup_edge_locked"] and setup_verdict_text is None:
                # Bereits in einem früheren Lauf ausgewertet — Verdikt aus
                # eval_results.jsonl für die Zeile nachladen.
                setup_verdict_text = freeze_eval.summarize_existing_verdict(
                    ROOT / EVAL_RESULTS_FILE,
                    {"setup_edge_a", "setup_edge_b", "setup_edge_conviction_c"})
            if eval_out["ki_score_locked"] and ki_verdict_text is None:
                ki_verdict_text = freeze_eval.summarize_existing_verdict(
                    ROOT / EVAL_RESULTS_FILE, {"ki_score_a", "ki_score_b"})

        eval_lines.append(hc.eval_status_line(
            "Setup-Edge/Conviction", setup_pop, SETUP_EDGE_FREEZE_N_TARGET,
            setup_rate, verdict_text=setup_verdict_text))
        eval_lines.append(hc.eval_status_line(
            "KI-Score", ki_pop, KI_SCORE_FREEZE_N_TARGET, ki_rate,
            verdict_text=ki_verdict_text))
    except Exception as _eval_exc:  # pragma: no cover — äußerster Fail-Soft-Guard
        log.warning("Freeze-Eval-Autorun unerwartet: %r", _eval_exc)
        eval_lines = []

    # Wöchentlicher Zusammenfassungs-Block (25.09.2026, nur Montag): reine
    # Funktion, ``state`` wird NICHT direkt mutiert — die Updates werden erst
    # unten (kurz vor _save_digest_state) gemerged, damit sie im selben
    # atomaren Write landen wie alles andere (kein zweiter State-Write, keine
    # eigene Retry-/Commit-Logik). weekly_state_updates ist {} an jedem
    # Nicht-Montag (State bleibt unangetastet).
    try:
        weekly_lines, weekly_state_updates = hc.weekly_summary_lines(
            now_ts, state,
            open_items_path=ROOT / hc.OPEN_ITEMS_FILE,
            matured_export_path=ROOT / hc.MATURED_EXPORT_FILE,
        )
    except Exception as _wk_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("weekly_summary_lines unerwartet: %r", _wk_exc)
        weekly_lines, weekly_state_updates = [], {}

    # Position-ohne-Watchlist-Wächter (31.10.2026, backend-only, fail-soft):
    # gleicht app_data.json["positions"] gegen watchlist_personal.json ab,
    # meldet Positionen seit > 1 Handelstag ohne Watchlist-Eintrag.
    # position_watchlist_watchdog_lines ist bereits raise-frei (eigener
    # Außen-Guard); der try/except ist reine Absicherung.
    try:
        watchdog_lines = hc.position_watchlist_watchdog_lines(
            now_ts,
            app_data_path=str(ROOT / "app_data.json"),
            watchlist_path=str(ROOT / hc.WATCHLIST_PERSONAL_FILE_FOR_WATCHDOG),
            state_path=str(ROOT / hc.POSITION_WATCHLIST_STATE_FILE),
            write_state=not dry_run,
        )
    except Exception as _wd_exc:  # pragma: no cover — Helper ist raise-frei
        log.warning("position_watchlist_watchdog_lines unerwartet: %r", _wd_exc)
        watchdog_lines = []

    body, title, priority, tags = hc.format_digest_body(
        state_fails, prov_fails,
        n_runs=n_runs,
        last_run_iso=last_run_iso,
        digest_date=today_iso,
        retest_line=retest_line,
        freeze_line=freeze_line,
        inst_own_line=inst_own_line,
        options_oi_line=options_oi_line,
        chain_raw_line=chain_raw_line,
        ftd_line=ftd_line,
        reg_sho_line=reg_sho_line,
        news_coverage_line=news_coverage_line,
        news_coverage_warn=news_coverage_warn,
        apewisdom_line=apewisdom_line,
        coverage_lines=coverage_lines,
        coverage_warns=coverage_warns,
        coverage_silent_empty_warns=coverage_silent_empty_warns,
        coverage_overview=coverage_overview,
        due_items_lines_=due_items_lines_,
        eval_lines=eval_lines,
        weekly_lines=weekly_lines,
        watchdog_lines=watchdog_lines,
    )

    log.info("Digest %s — %d state-fails, %d provider-fails, %d runs",
             today_iso, len(state_fails), len(prov_fails), n_runs)
    if dry_run:
        print(f"[DRY-RUN] {title} (priority={priority})")
        print(body)
        return 0

    # ntfy-Send mit Exception-Auffang: hartes Versagen (Netzwerk-Bug,
    # Exception in requests.post) wird wie sent=False behandelt und
    # zum Workflow-Fail eskaliert. _ntfy_send selbst ist fail-soft,
    # aber wir wollen kein Silent-Fail wenn NTFY_TOPIC erwartet wird.
    ntfy_active = bool(NTFY_TOPIC and NTFY_ENABLED)
    try:
        sent = _ntfy_send(title, body, priority, tags)
    except Exception as exc:
        log.warning("ntfy-Send Exception: %s: %s", type(exc).__name__, exc)
        sent = False

    if sent or not ntfy_active:
        # ntfy aktiv UND gesendet → mark today as sent.
        # ntfy disabled / Test-Mode → trotzdem state-update, damit auch ohne
        # ntfy nicht mehrfach pro Tag gerechnet wird (lokale Test-Runs).
        state["last_digest_sent"] = today_iso
    # ``last_successful_run`` ist ein Liveness-Marker: „wann lief der
    # Digest zuletzt überhaupt durch?". Vor 22.05.2026 wurde das Feld
    # nur bei 0 Fails gesetzt — da seit 14.05. jeder Digest mindestens
    # 1 Fail hatte, blieb es dauerhaft ``null`` und damit informations-
    # los. Lockerung auf ``n_runs > 0``: Feld wird gesetzt sobald der
    # Digest Daten im Fenster sieht und durchläuft, unabhängig vom
    # Fail-Count. Nicht ``last_digest_sent`` ersetzen (das ist der
    # ntfy-Push-Marker für S8); das hier ist der Workflow-Lauf-Marker.
    if n_runs > 0:
        state["last_successful_run"] = (
            last_run_iso or now_ts.strftime("%Y-%m-%dT%H:%M:%SZ"))

    # Wöchentlicher Block: State-Update unabhängig vom ntfy-Send-Erfolg
    # gemerged (analog last_successful_run oben) — der Snapshot muss auch
    # bei einem Push-Fail weiterrücken, sonst würde ein bereits gemeldetes
    # Item beim nächsten Montag fälschlich erneut als "neu" auftauchen.
    # {} an einem Nicht-Montag — kein Effekt auf state.update.
    state.update(weekly_state_updates)

    _save_digest_state(state)

    # Fail-Visibility-Fix (16.05.2026): Wenn ntfy aktiv erwartet wird
    # aber der Send fehlgeschlagen ist → exit 1. State ist bereits
    # persistiert; der `if: always()`-Commit-Step im Workflow läuft
    # trotzdem; aber der Run wird rot und Easy bekommt eine
    # GitHub-Notification. Vermeidet Silent-Fails wie am 15.05.2026.
    if ntfy_active and not sent:
        log.error("Digest-Push fehlgeschlagen — Workflow wird rot markiert.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
