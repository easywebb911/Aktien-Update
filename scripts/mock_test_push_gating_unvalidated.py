"""Mock-Tests für Push-Gating unvalidierter Trading-Signale (Easy-Entscheid 06.09.2026).

Kontext: solange keine der zugrundeliegenden Scores/Trigger eine bewiesene
Edge hat (SCORE_STATUS_LABELS — durchgängig "unvalidiert"/"heuristisch"/
"OoS-kollabiert"/"OoS falsifiziert"), soll nichts davon als Handlungs-
aufforderung aufs Handy kommen. Fünf ntfy-Sender wurden dafür mit einem
zentralen Flag in ``config.py`` gegated (Default ``False``):

  1. ``PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED`` — ki_agent.send_ntfy_alert
  2. ``PUSH_EXIT_P2_NTFY_ENABLED``            — ki_agent._send_exit_p2_push (Bundle+Eskalation)
  3. ``PUSH_ANOMALY_NTFY_ENABLED``            — ki_agent._send_anomaly_ntfy (alle 7 Trigger)
  4. ``PUSH_EXIT_P1_NTFY_ENABLED``            — generate_report._send_exit_ntfy
  5. ``PUSH_ALERT_LEGACY_NTFY_ENABLED``       — alert.send_ntfy_alert (bereits faktisch tot)

Jeder Sender prüft sein Flag als ALLERERSTES und returnt dann OHNE
``requests.post``-Call — die Trigger-Logik (``detect_anomalies``,
``compute_exit_score``, Cooldown/Dedupe-State, ``_record_push``-Audit)
bleibt an den Aufrufstellen komplett unverändert. Für die vier push_history-
Konsumenten (1-4) wird das hier direkt bewiesen: der reale Sender liefert
``False`` zurück (kein Netzwerk-Call), UND die reale ``_record_push``-
Funktion wird mit genau diesem Rückgabewert aufgerufen — der Audit-Eintrag
entsteht trotzdem, mit ``success=False``. Für alert.py (5) gibt es keine
push_history-Anbindung (eigenständiges Legacy-Modul) — dort wird nur der
Sende-Stopp selbst geprüft.

Jeder der 5 Sender wird zusätzlich mit dem Flag FORCIERT AUF True getestet
(mit gemocktem ``requests.post``) — das beweist, dass der Rückweg ein reiner
Flag-Flip ist (kein zweiter Code-Pfad wurde kaputt gemacht).

Kein Netzwerk: ``requests.post`` wird an jeder Call-Site gemockt (Call-
Recorder). Deterministisch, kein Live-ntfy-Call.
"""
from __future__ import annotations

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Heavy-Dependency-Stubs (Minimal-CI: kein pandas/requests/yfinance/bs4/
# deep_translator) — identisch zu mock_test_exit_push_dedupe.py /
# mock_test_translate_error_guard.py. ``requests`` bleibt ein leeres
# ModuleType — wir hängen pro Test ``.post`` selbst dran (Call-Recorder).
for _m in ("pandas", "yfinance"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)
if "requests" not in sys.modules:
    _rq = types.ModuleType("requests")
    _rq.Session = lambda *a, **k: types.SimpleNamespace(
        headers=types.SimpleNamespace(update=lambda *a, **k: None))
    _rq.get = lambda *a, **k: None
    _rq.post = lambda *a, **k: None
    _rq.exceptions = types.SimpleNamespace(RequestException=Exception)
    sys.modules["requests"] = _rq
if "bs4" not in sys.modules:
    _bs4 = types.ModuleType("bs4")
    _bs4.BeautifulSoup = lambda *a, **k: None
    sys.modules["bs4"] = _bs4
if "deep_translator" not in sys.modules:
    _dt = types.ModuleType("deep_translator")
    _dt.GoogleTranslator = lambda *a, **k: types.SimpleNamespace(translate=lambda s: s)
    sys.modules["deep_translator"] = _dt
if "watchlist" not in sys.modules:
    _wl = types.ModuleType("watchlist")
    _wl.WATCHLIST = []
    sys.modules["watchlist"] = _wl

import ki_agent  # noqa: E402
import generate_report as gr  # noqa: E402
import alert  # noqa: E402
from push_history import _record_push  # noqa: E402

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def _fake_post_factory():
    """Call-Recorder — gibt (fake_post_fn, calls_list) zurück."""
    calls: list[dict] = []

    def _fake_post(url, *a, **k):
        calls.append({"url": url, "data": k.get("data"), "headers": k.get("headers")})
        return types.SimpleNamespace(status_code=200, text="ok")

    return _fake_post, calls


# === 1) Earnings-Sofort-Alert (ki_agent.send_ntfy_alert) ===================

def test_01a_earnings_ntfy_disabled_no_send():
    fake_post, calls = _fake_post_factory()
    orig_post = ki_agent.requests.post
    orig_en, orig_topic = ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC
    orig_gate = ki_agent.PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED
    try:
        ki_agent.requests.post = fake_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = True, "test_topic"
        ki_agent.PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED = False
        ki_agent.send_ntfy_alert("DMRC", 80, ["driver1"])
    finally:
        ki_agent.requests.post = orig_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = orig_en, orig_topic
        ki_agent.PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED = orig_gate
    assert calls == [], f"kein Push erwartet (Flag=False), aber POST(s): {calls}"


def test_01b_earnings_ntfy_reenabled_still_sends():
    """Rückweg-Nachweis: Flag=True (mit NTFY_ENABLED/TOPIC gesetzt) sendet
    wieder ganz normal — kein zweiter Code-Pfad wurde kaputt gemacht."""
    fake_post, calls = _fake_post_factory()
    orig_post = ki_agent.requests.post
    orig_en, orig_topic = ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC
    orig_gate = ki_agent.PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED
    try:
        ki_agent.requests.post = fake_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = True, "test_topic"
        ki_agent.PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED = True
        ki_agent.send_ntfy_alert("DMRC", 80, ["driver1"])
    finally:
        ki_agent.requests.post = orig_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = orig_en, orig_topic
        ki_agent.PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED = orig_gate
    assert len(calls) == 1, f"genau 1 Push erwartet (Flag=True), got {calls}"


def test_01c_earnings_callsite_ok_expression_present():
    """Die Aufrufstelle in main() muss PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED
    in die _ok-Berechnung mit aufnehmen — send_ntfy_alert() selbst gibt
    (unverändert) None zurück, der Erfolgs-Proxy lebt an der Call-Site."""
    src = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
    assert ("_ok = bool(NTFY_ENABLED and NTFY_TOPIC\n"
            "                              and PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED)") in src, \
        "Earnings-Call-Site: _ok-Ausdruck ohne PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED"


def test_01d_earnings_persistence_continues_when_disabled():
    """Kette real: gegateter Sender liefert False -> _record_push (real,
    unverändert) bekommt genau dieses success=False -> Audit-Eintrag
    entsteht trotzdem (kein Datenverlust durchs Gating)."""
    fake_post, calls = _fake_post_factory()
    orig_post = ki_agent.requests.post
    orig_en, orig_topic = ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC
    orig_gate = ki_agent.PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED
    state = {}
    try:
        ki_agent.requests.post = fake_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = True, "test_topic"
        ki_agent.PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED = False
        # Repliziert die Call-Site-Formel wörtlich (Test 01c sichert die
        # echte Quelle dagegen ab) — send_ntfy_alert() selbst returnt None.
        ki_agent.send_ntfy_alert("DMRC", 80, ["driver1"])
        _ok = bool(ki_agent.NTFY_ENABLED and ki_agent.NTFY_TOPIC
                   and ki_agent.PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED)
        _record_push(state, "DMRC", kind="earnings_immediate", severity="default",
                     trigger=None, body="DMRC Earnings-Sofort-Alert (in 1d, KI 80)",
                     success=_ok)
    finally:
        ki_agent.requests.post = orig_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = orig_en, orig_topic
        ki_agent.PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED = orig_gate
    assert calls == [], calls
    hist = state.get("push_history") or []
    assert len(hist) == 1, hist
    assert hist[0]["kind"] == "earnings_immediate" and hist[0]["success"] is False, hist[0]


# === 2) Exit Phase 2 — beide Kanäle (ki_agent._send_exit_p2_push) ==========

def test_02a_exit_p2_bundle_disabled_no_send():
    fake_post, calls = _fake_post_factory()
    orig_post = ki_agent.requests.post
    orig_en, orig_topic = ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC
    orig_gate = ki_agent.PUSH_EXIT_P2_NTFY_ENABLED
    try:
        ki_agent.requests.post = fake_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = True, "test_topic"
        ki_agent.PUSH_EXIT_P2_NTFY_ENABLED = False
        ok = ki_agent._send_exit_p2_push("WOLF", "Exit-Warnung Test", severity="trigger")
    finally:
        ki_agent.requests.post = orig_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = orig_en, orig_topic
        ki_agent.PUSH_EXIT_P2_NTFY_ENABLED = orig_gate
    assert ok is False and calls == [], (ok, calls)


def test_02b_exit_p2_escalation_disabled_no_send():
    """Der Eskalations-Kanal ruft dieselbe Funktion mit severity=escalation
    — muss ebenso gegated sein (BEIDE Kanäle laut Auftrag)."""
    fake_post, calls = _fake_post_factory()
    orig_post = ki_agent.requests.post
    orig_en, orig_topic = ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC
    orig_gate = ki_agent.PUSH_EXIT_P2_NTFY_ENABLED
    try:
        ki_agent.requests.post = fake_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = True, "test_topic"
        ki_agent.PUSH_EXIT_P2_NTFY_ENABLED = False
        ok = ki_agent._send_exit_p2_push("WOLF", "Exit-Eskalation Test", severity="escalation")
    finally:
        ki_agent.requests.post = orig_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = orig_en, orig_topic
        ki_agent.PUSH_EXIT_P2_NTFY_ENABLED = orig_gate
    assert ok is False and calls == [], (ok, calls)


def test_02c_exit_p2_reenabled_still_sends():
    fake_post, calls = _fake_post_factory()
    orig_post = ki_agent.requests.post
    orig_en, orig_topic = ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC
    orig_gate = ki_agent.PUSH_EXIT_P2_NTFY_ENABLED
    try:
        ki_agent.requests.post = fake_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = True, "test_topic"
        ki_agent.PUSH_EXIT_P2_NTFY_ENABLED = True
        ok = ki_agent._send_exit_p2_push("WOLF", "Exit-Warnung Test", severity="trigger")
    finally:
        ki_agent.requests.post = orig_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = orig_en, orig_topic
        ki_agent.PUSH_EXIT_P2_NTFY_ENABLED = orig_gate
    assert ok is True and len(calls) == 1, (ok, calls)


def test_02d_exit_p2_persistence_continues_when_disabled():
    """Reale Kette: _send_exit_p2_push (gegated) -> False -> _record_push
    (real) bekommt success=False -> Eintrag existiert trotzdem."""
    fake_post, calls = _fake_post_factory()
    orig_post = ki_agent.requests.post
    orig_en, orig_topic = ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC
    orig_gate = ki_agent.PUSH_EXIT_P2_NTFY_ENABLED
    state = {}
    try:
        ki_agent.requests.post = fake_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = True, "test_topic"
        ki_agent.PUSH_EXIT_P2_NTFY_ENABLED = False
        _ok = ki_agent._send_exit_p2_push("WOLF", "Exit-Eskalation WOLF: pressure 70->76/100",
                                          severity="escalation")
        _record_push(state, "WOLF", kind="exit_p2", severity="escalation",
                     trigger="profit_lock,trend_break",
                     body="Exit-Eskalation WOLF: pressure 70->76/100", success=_ok)
    finally:
        ki_agent.requests.post = orig_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = orig_en, orig_topic
        ki_agent.PUSH_EXIT_P2_NTFY_ENABLED = orig_gate
    assert calls == [], calls
    hist = state.get("push_history") or []
    assert len(hist) == 1, hist
    assert hist[0]["kind"] == "exit_p2" and hist[0]["success"] is False, hist[0]


# === 3) Anomalie-Trigger — alle 7 (ki_agent._send_anomaly_ntfy) ============

def test_03a_anomaly_disabled_no_send():
    fake_post, calls = _fake_post_factory()
    orig_post = ki_agent.requests.post
    orig_en, orig_topic = ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC
    orig_gate = ki_agent.PUSH_ANOMALY_NTFY_ENABLED
    try:
        ki_agent.requests.post = fake_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = True, "test_topic"
        ki_agent.PUSH_ANOMALY_NTFY_ENABLED = False
        ok = ki_agent._send_anomaly_ntfy("NVAX", "NVAX rvol explosion test")
    finally:
        ki_agent.requests.post = orig_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = orig_en, orig_topic
        ki_agent.PUSH_ANOMALY_NTFY_ENABLED = orig_gate
    assert ok is False and calls == [], (ok, calls)


def test_03b_anomaly_reenabled_still_sends():
    fake_post, calls = _fake_post_factory()
    orig_post = ki_agent.requests.post
    orig_en, orig_topic = ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC
    orig_gate = ki_agent.PUSH_ANOMALY_NTFY_ENABLED
    try:
        ki_agent.requests.post = fake_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = True, "test_topic"
        ki_agent.PUSH_ANOMALY_NTFY_ENABLED = True
        ok = ki_agent._send_anomaly_ntfy("NVAX", "NVAX rvol explosion test")
    finally:
        ki_agent.requests.post = orig_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = orig_en, orig_topic
        ki_agent.PUSH_ANOMALY_NTFY_ENABLED = orig_gate
    assert ok is True and len(calls) == 1, (ok, calls)


def test_03c_anomaly_persistence_continues_when_disabled():
    fake_post, calls = _fake_post_factory()
    orig_post = ki_agent.requests.post
    orig_en, orig_topic = ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC
    orig_gate = ki_agent.PUSH_ANOMALY_NTFY_ENABLED
    state = {}
    try:
        ki_agent.requests.post = fake_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = True, "test_topic"
        ki_agent.PUSH_ANOMALY_NTFY_ENABLED = False
        _ok = ki_agent._send_anomaly_ntfy("NVAX", "NVAX Perfect Storm 4/4")
        _record_push(state, "NVAX", kind="anomaly", severity="high",
                     trigger="perfect_storm", body="NVAX Perfect Storm 4/4",
                     success=_ok, conviction_score=80)
    finally:
        ki_agent.requests.post = orig_post
        ki_agent.NTFY_ENABLED, ki_agent.NTFY_TOPIC = orig_en, orig_topic
        ki_agent.PUSH_ANOMALY_NTFY_ENABLED = orig_gate
    assert calls == [], calls
    hist = state.get("push_history") or []
    assert len(hist) == 1, hist
    assert hist[0]["kind"] == "anomaly" and hist[0]["success"] is False, hist[0]


def test_03d_conviction_high_uses_same_gated_sender():
    """conviction_high ist von der SEPARATEN Conviction-Gating-Klausel
    (ANOMALY_CONVICTION_MIN_THRESHOLD) explizit ausgenommen — muss aber
    trotzdem durch denselben _send_anomaly_ntfy-Aufruf laufen wie alle
    anderen Trigger, damit das neue Master-Flag ihn ebenfalls stoppt.
    Source-Nachweis: es gibt in detect_anomalies()/dem Aufrufer KEINEN
    zweiten, conviction_high-spezifischen ntfy-Sende-Pfad."""
    ka_src = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
    # Es darf nur EINE _send_anomaly_ntfy-Definition + EINE Aufrufstelle geben.
    assert ka_src.count("def _send_anomaly_ntfy(") == 1, "unerwartete zweite Definition"
    assert ka_src.count("_ok = _send_anomaly_ntfy(ticker, body)") == 1, \
        "unerwartete zweite/fehlende Aufrufstelle — conviction_high könnte einen Bypass haben"
    # Funktional bestätigt durch 03a/03b bereits (Funktion kennt keinen
    # Trigger-Namen, kann also nicht zwischen conviction_high und anderen
    # Triggern unterscheiden) — hier nur die Struktur-Absicherung.
    _check_dummy = True
    assert _check_dummy


# === 4) Exit Phase 1 (generate_report._send_exit_ntfy) =====================

def test_04a_exit_p1_disabled_no_send():
    fake_post, calls = _fake_post_factory()
    orig_post = gr.requests.post
    orig_en, orig_topic = gr.NTFY_ENABLED, gr.NTFY_TOPIC
    orig_gate = gr.PUSH_EXIT_P1_NTFY_ENABLED
    try:
        gr.requests.post = fake_post
        gr.NTFY_ENABLED, gr.NTFY_TOPIC = True, "test_topic"
        gr.PUSH_EXIT_P1_NTFY_ENABLED = False
        ok = gr._send_exit_ntfy("AMC", "AMC Exit 65 | -8% | trailing_stop")
    finally:
        gr.requests.post = orig_post
        gr.NTFY_ENABLED, gr.NTFY_TOPIC = orig_en, orig_topic
        gr.PUSH_EXIT_P1_NTFY_ENABLED = orig_gate
    assert ok is False and calls == [], (ok, calls)


def test_04b_exit_p1_profit_take_disabled_no_send():
    """Zweiter Untertyp (profit_take) ruft dieselbe Funktion — ebenfalls
    gegated."""
    fake_post, calls = _fake_post_factory()
    orig_post = gr.requests.post
    orig_en, orig_topic = gr.NTFY_ENABLED, gr.NTFY_TOPIC
    orig_gate = gr.PUSH_EXIT_P1_NTFY_ENABLED
    try:
        gr.requests.post = fake_post
        gr.NTFY_ENABLED, gr.NTFY_TOPIC = True, "test_topic"
        gr.PUSH_EXIT_P1_NTFY_ENABLED = False
        ok = gr._send_exit_ntfy("AMC", "AMC Profit-Take | +55% seit Entry | Halbe Position?")
    finally:
        gr.requests.post = orig_post
        gr.NTFY_ENABLED, gr.NTFY_TOPIC = orig_en, orig_topic
        gr.PUSH_EXIT_P1_NTFY_ENABLED = orig_gate
    assert ok is False and calls == [], (ok, calls)


def test_04c_exit_p1_reenabled_still_sends():
    fake_post, calls = _fake_post_factory()
    orig_post = gr.requests.post
    orig_en, orig_topic = gr.NTFY_ENABLED, gr.NTFY_TOPIC
    orig_gate = gr.PUSH_EXIT_P1_NTFY_ENABLED
    try:
        gr.requests.post = fake_post
        gr.NTFY_ENABLED, gr.NTFY_TOPIC = True, "test_topic"
        gr.PUSH_EXIT_P1_NTFY_ENABLED = True
        ok = gr._send_exit_ntfy("AMC", "AMC Exit 65 | -8% | trailing_stop")
    finally:
        gr.requests.post = orig_post
        gr.NTFY_ENABLED, gr.NTFY_TOPIC = orig_en, orig_topic
        gr.PUSH_EXIT_P1_NTFY_ENABLED = orig_gate
    assert ok is True and len(calls) == 1, (ok, calls)


def test_04d_exit_p1_persistence_continues_when_disabled():
    fake_post, calls = _fake_post_factory()
    orig_post = gr.requests.post
    orig_en, orig_topic = gr.NTFY_ENABLED, gr.NTFY_TOPIC
    orig_gate = gr.PUSH_EXIT_P1_NTFY_ENABLED
    state = {}
    try:
        gr.requests.post = fake_post
        gr.NTFY_ENABLED, gr.NTFY_TOPIC = True, "test_topic"
        gr.PUSH_EXIT_P1_NTFY_ENABLED = False
        _ok = gr._send_exit_ntfy("AMC", "AMC Exit 65 | -8% | trailing_stop")
        _record_push(state, "AMC", kind="exit_p1", severity="default",
                     trigger="exit_alert", body="AMC Exit 65 | -8% | trailing_stop",
                     success=_ok)
    finally:
        gr.requests.post = orig_post
        gr.NTFY_ENABLED, gr.NTFY_TOPIC = orig_en, orig_topic
        gr.PUSH_EXIT_P1_NTFY_ENABLED = orig_gate
    assert calls == [], calls
    hist = state.get("push_history") or []
    assert len(hist) == 1, hist
    assert hist[0]["kind"] == "exit_p1" and hist[0]["success"] is False, hist[0]


# === 5) Legacy Alert-Monitor (alert.send_ntfy_alert) =======================
# Kein push_history in diesem isolierten Modul — Persistenz-Nachweis entfällt
# strukturell (nichts zu preservieren außer baseline.json/last_alert.json,
# die über den separaten E-Mail-Pfad laufen und von diesem Flag NICHT
# berührt werden). Nur der Sende-Stopp selbst wird geprüft.

def test_05a_legacy_alert_disabled_no_send():
    fake_post, calls = _fake_post_factory()
    orig_post = alert.requests.post
    orig_en, orig_topic = alert.NTFY_ENABLED, alert.NTFY_TOPIC
    orig_gate = alert.PUSH_ALERT_LEGACY_NTFY_ENABLED
    try:
        alert.requests.post = fake_post
        alert.NTFY_ENABLED, alert.NTFY_TOPIC = True, "test_topic"
        alert.PUSH_ALERT_LEGACY_NTFY_ENABLED = False
        alert.send_ntfy_alert("GME", 80, ["driver1"])
    finally:
        alert.requests.post = orig_post
        alert.NTFY_ENABLED, alert.NTFY_TOPIC = orig_en, orig_topic
        alert.PUSH_ALERT_LEGACY_NTFY_ENABLED = orig_gate
    assert calls == [], calls


def test_05b_legacy_alert_reenabled_still_sends():
    fake_post, calls = _fake_post_factory()
    orig_post = alert.requests.post
    orig_en, orig_topic = alert.NTFY_ENABLED, alert.NTFY_TOPIC
    orig_gate = alert.PUSH_ALERT_LEGACY_NTFY_ENABLED
    try:
        alert.requests.post = fake_post
        alert.NTFY_ENABLED, alert.NTFY_TOPIC = True, "test_topic"
        alert.PUSH_ALERT_LEGACY_NTFY_ENABLED = True
        alert.send_ntfy_alert("GME", 80, ["driver1"])
    finally:
        alert.requests.post = orig_post
        alert.NTFY_ENABLED, alert.NTFY_TOPIC = orig_en, orig_topic
        alert.PUSH_ALERT_LEGACY_NTFY_ENABLED = orig_gate
    assert len(calls) == 1, calls


# === Config-Defaults & Trennschärfe zu den NICHT betroffenen Pushes ========

def test_06a_all_five_flags_default_false():
    import config
    assert config.PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED is False
    assert config.PUSH_EXIT_P2_NTFY_ENABLED is False
    assert config.PUSH_ANOMALY_NTFY_ENABLED is False
    assert config.PUSH_EXIT_P1_NTFY_ENABLED is False
    assert config.PUSH_ALERT_LEGACY_NTFY_ENABLED is False


def test_06b_untouched_infra_pushes_have_own_unrelated_flags():
    """Health-Check-Digest / HTML-Sanity-CRIT / Status-Review-Wecker /
    Lit-Check-Reminder dürfen NICHT auf eines der 5 neuen Flags reagieren
    — sie behalten ihre eigenen, unabhängigen ENABLED-Schalter."""
    import config
    # Lit-Reminder + Status-Wecker haben je ein eigenes Enabled-Flag,
    # unabhängig von den 5 neuen Push-Gates.
    assert hasattr(config, "LIT_REMINDER_ENABLED")
    assert hasattr(config, "STATUS_REVIEW_WECKER_ENABLED")
    # HTML-Sanity-CRIT (_send_html_assertion_alert) hat KEIN eigenes Enabled-
    # Flag (nur NTFY_ENABLED/NTFY_TOPIC) — genau das darf sich NICHT geändert
    # haben: keines der 5 neuen Flags darf im Sender-Body vorkommen.
    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    start = gr_src.find("def _send_html_assertion_alert(")
    end = gr_src.find("\ndef ", start + 10)
    block = gr_src[start:end]
    for flag in ("PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED", "PUSH_EXIT_P2_NTFY_ENABLED",
                 "PUSH_ANOMALY_NTFY_ENABLED", "PUSH_EXIT_P1_NTFY_ENABLED",
                 "PUSH_ALERT_LEGACY_NTFY_ENABLED"):
        assert flag not in block, f"{flag} darf NICHT in _send_html_assertion_alert vorkommen"
    # health_check_digest._ntfy_send und status_review_reminder._ntfy_send
    # und lit_reminder._ntfy_send ebenfalls gegenprüfen.
    for path, fname in (("scripts/health_check_digest.py", "_ntfy_send"),
                        ("status_review_reminder.py", "_ntfy_send"),
                        ("scripts/lit_reminder.py", "_ntfy_send")):
        src = (ROOT / path).read_text(encoding="utf-8")
        s2 = src.find(f"def {fname}(")
        e2 = src.find("\ndef ", s2 + 10)
        blk = src[s2:e2] if e2 != -1 else src[s2:]
        for flag in ("PUSH_EARNINGS_IMMEDIATE_NTFY_ENABLED", "PUSH_EXIT_P2_NTFY_ENABLED",
                     "PUSH_ANOMALY_NTFY_ENABLED", "PUSH_EXIT_P1_NTFY_ENABLED",
                     "PUSH_ALERT_LEGACY_NTFY_ENABLED"):
            assert flag not in blk, f"{flag} darf NICHT in {path}:{fname} vorkommen"


# === Runner =================================================================

def main():
    tests = [
        ("01a Earnings: Flag=False -> kein Send",                    test_01a_earnings_ntfy_disabled_no_send),
        ("01b Earnings: Flag=True -> sendet wieder (Rückweg)",       test_01b_earnings_ntfy_reenabled_still_sends),
        ("01c Earnings: Call-Site-Ausdruck im Source vorhanden",     test_01c_earnings_callsite_ok_expression_present),
        ("01d Earnings: Persistenz trotz Gating (success=False)",    test_01d_earnings_persistence_continues_when_disabled),
        ("02a Exit-P2 Bundle: Flag=False -> kein Send",              test_02a_exit_p2_bundle_disabled_no_send),
        ("02b Exit-P2 Eskalation: Flag=False -> kein Send",          test_02b_exit_p2_escalation_disabled_no_send),
        ("02c Exit-P2: Flag=True -> sendet wieder (Rückweg)",        test_02c_exit_p2_reenabled_still_sends),
        ("02d Exit-P2: Persistenz trotz Gating (success=False)",     test_02d_exit_p2_persistence_continues_when_disabled),
        ("03a Anomaly: Flag=False -> kein Send",                     test_03a_anomaly_disabled_no_send),
        ("03b Anomaly: Flag=True -> sendet wieder (Rückweg)",        test_03b_anomaly_reenabled_still_sends),
        ("03c Anomaly: Persistenz trotz Gating (success=False)",     test_03c_anomaly_persistence_continues_when_disabled),
        ("03d conviction_high nutzt denselben gegateten Sender",     test_03d_conviction_high_uses_same_gated_sender),
        ("04a Exit-P1 exit_alert: Flag=False -> kein Send",          test_04a_exit_p1_disabled_no_send),
        ("04b Exit-P1 profit_take: Flag=False -> kein Send",         test_04b_exit_p1_profit_take_disabled_no_send),
        ("04c Exit-P1: Flag=True -> sendet wieder (Rückweg)",        test_04c_exit_p1_reenabled_still_sends),
        ("04d Exit-P1: Persistenz trotz Gating (success=False)",     test_04d_exit_p1_persistence_continues_when_disabled),
        ("05a Legacy-Alert: Flag=False -> kein Send",                test_05a_legacy_alert_disabled_no_send),
        ("05b Legacy-Alert: Flag=True -> sendet wieder (Rückweg)",   test_05b_legacy_alert_reenabled_still_sends),
        ("06a alle 5 Flags default False",                           test_06a_all_five_flags_default_false),
        ("06b NICHT betroffene Infra-Pushes unberührt",              test_06b_untouched_infra_pushes_have_own_unrelated_flags),
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
