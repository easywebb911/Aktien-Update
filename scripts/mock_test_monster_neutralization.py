"""Mock-Tests — Monster-Score neutralisiert (Anzeige + Push + Signal-Zähler).

GRUND (13.07.2026): monster_score ist unvalidiert (30.06. AUC 0.76→0.51
kollabiert, kein belegter Prädiktor). Er wurde als validierter Prädiktor
dargestellt (grüne robuste Zahl), pushte (monster_backup) und zählte als
Signal (n_signals). Berechnung/Persistenz/Sortierung BLEIBEN — nur die
Signal-Suggestion wird entfernt.

TEIL A — Anzeige (funktional):
  A1 compute_score_confidence: monster-tier = "heuristisch" (NICHT setup_tier),
     auch wenn genug Backtest-Daten für setup=robust vorliegen (Differenzierung).
  A2 setup bleibt "robust" (unberührt).
  A3 _conf_class("monster") liefert sb-conf-heur (Wasserzeichen) bei
     befülltem _SCORE_CONFIDENCE; _conf_class("setup") bleibt robust (leer).

TEIL B1 — Push raus (funktional):
  B1a detect_anomalies mit monster_score=95 (≥90) → KEIN monster_backup-Trigger.
  B1b ki_agent-Source enthält keinen monster_backup-Trigger + kein
      `monster >= ANOMALY_MONSTER_BACKUP`-Push mehr.

TEIL B2 — Signal-Zähler monster-frei (source):
  B2a monster speist n_signals NICHT mehr (kein `monster ... >= 70 ... n_signals`).
  B2b n_signals wird über ki_signal_score ≥ 70 gespeist.

BLEIBT unangetastet (Belege):
  C1 apply_monster_score unverändert vorhanden (Berechnung bleibt).
  C2 Sortier-Option data-sort="monster" bleibt.

generate_report + ki_agent importieren schwere Module — vor dem Import gestubbt
(Union der beiden Stub-Sätze). Funktionale Tests nutzen Fixtures, kein Netz.

Ausführung: ``python scripts/mock_test_monster_neutralization.py``.
Exit 0 bei Erfolg, 1 bei Fail.
"""
from __future__ import annotations

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _install_stubs() -> None:
    # Union der Stub-Sätze von generate_report (yfinance/bs4/deep_translator/
    # requests/watchlist) und ki_agent (pandas/requests/yfinance).
    for m in ("pandas", "yfinance", "bs4", "deep_translator", "lxml"):
        if m not in sys.modules:
            sys.modules[m] = types.ModuleType(m)
    if not hasattr(sys.modules["yfinance"], "Ticker"):
        sys.modules["yfinance"].Ticker = lambda *a, **k: None
        sys.modules["yfinance"].download = lambda *a, **k: None
    if not hasattr(sys.modules["bs4"], "BeautifulSoup"):
        sys.modules["bs4"].BeautifulSoup = lambda *a, **k: None
    if not hasattr(sys.modules["deep_translator"], "GoogleTranslator"):
        sys.modules["deep_translator"].GoogleTranslator = lambda *a, **k: \
            types.SimpleNamespace(translate=lambda s: s)
    if "requests" not in sys.modules:
        rq = types.ModuleType("requests")
        rq.Session = lambda *a, **k: types.SimpleNamespace(
            headers=types.SimpleNamespace(update=lambda *a, **k: None))
        rq.get = lambda *a, **k: None
        rq.post = lambda *a, **k: None
        rq.exceptions = types.SimpleNamespace(RequestException=Exception)
        sys.modules["requests"] = rq
    if "watchlist" not in sys.modules:
        wl = types.ModuleType("watchlist")
        wl.WATCHLIST = []
        sys.modules["watchlist"] = wl


_install_stubs()

import generate_report as gr  # noqa: E402
import ki_agent as ka  # noqa: E402
import config  # noqa: E402


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail and not cond:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


# ── TEIL A — Anzeige (funktional) ─────────────────────────────────────────────
def _test_display():
    print("── TEIL A — Konfidenz-Wasserzeichen (Single-Source) ──────────")
    bh = [{"return_10d": 5.0} for _ in range(config.SCORE_CONFIDENCE_N_ROBUST + 10)]
    conf = gr.compute_score_confidence(bh)

    # A1: Monster-Validierungs-Status kommt aus SCORE_STATUS_LABELS (Single-
    # Source), eigenständig — NICHT von Setup vererbt.
    _check("A1 monster-Status == 'OoS-kollabiert' (eigenständig, nicht vererbt)",
           config.SCORE_STATUS_LABELS["monster"]["status"] == "OoS-kollabiert",
           f"got {config.SCORE_STATUS_LABELS['monster']['status']!r}")
    # A2: compute liefert für Monster NUR die Daten-Dimension (keine Validierung).
    _check("A2 compute[monster] nur {n, data_tier} (keine Validierungs-Stufe)",
           set(conf["monster"]) == {"n", "data_tier"} and conf["monster"]["n"] is None,
           f"got {conf['monster']}")
    # A2b: die Kollaps-Empirik ist ehrlich im config-Kommentar dokumentiert.
    cfg_src = (ROOT / "config.py").read_text(encoding="utf-8")
    _anchor = cfg_src.find("SCORE_STATUS_LABELS = {")
    _cmt = cfg_src[max(0, _anchor - 2200):_anchor]
    _check("A2b Kollaps-Empirik dokumentiert (0.76 + kollabiert)",
           "0.76" in _cmt and "kollabiert" in _cmt)

    # _conf_class liest jetzt SCORE_STATUS_LABELS (Modul-Global via config-*).
    m_css, m_title, _ = gr._conf_class("monster")
    s_css, s_title, _ = gr._conf_class("setup")
    _check("A3 _conf_class('monster') → sb-conf-heur + 'OoS-kollabiert'",
           m_css == "sb-conf-heur" and "OoS-kollabiert" in m_title,
           f"got css={m_css!r} title={m_title!r}")
    # A3b: Setup ist unter Single-Source EBENFALLS gedimmt (kein Schein-„robust"
    # mehr); Monster bleibt via Status-Text + Neutral-Farbe differenziert.
    _check("A3b _conf_class('setup') gedimmt (unvalidiert, kein Schein-robust)",
           s_css == "sb-conf-heur" and "unvalidiert" in s_title,
           f"got css={s_css!r} title={s_title!r}")
    _check("A3c Monster-Status ≠ Setup-Status (eigenständige Neutralisierung)",
           config.SCORE_STATUS_LABELS["monster"]["status"]
           != config.SCORE_STATUS_LABELS["setup"]["status"])


# ── TEIL B1 — Push raus (funktional + source) ─────────────────────────────────
def _test_push_removed():
    print("── TEIL B1 — monster_backup-Push entfernt ────────────────────")
    # Funktional: detect_anomalies mit monster≥90 darf keinen monster_backup
    # liefern. Signal bewusst „leer" (kein rvol/uoa/gap) → kein anderer Trigger.
    signal = {"score": 10, "drivers": "", "rvol_4d": 0.0, "rvol_20d": 0.0}
    app_data = {
        "setup_scores":      {"TEST": 80.0},
        "monster_scores":    {"TEST": 95.0},   # ≥ ANOMALY_MONSTER_BACKUP (90)
        "conviction_scores": {"TEST": {"score": 90}},
        "gap_states":        {},
        "score_history":     {},
    }
    out = ka.detect_anomalies("TEST", signal, None, app_data)
    triggers = [a.get("trigger") for a in out]
    _check("B1a detect_anomalies(monster=95) → KEIN monster_backup",
           "monster_backup" not in triggers,
           f"got triggers={triggers}")

    ki_src = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
    _check("B1b kein monster_backup-Trigger-String mehr im Source",
           '"monster_backup"' not in ki_src and "'monster_backup'" not in ki_src)
    _check("B1c kein `monster >= ANOMALY_MONSTER_BACKUP`-Push mehr",
           "monster >= ANOMALY_MONSTER_BACKUP" not in ki_src)


# ── TEIL B2 — Signal-Zähler monster-frei (source) ─────────────────────────────
def _test_signal_counter():
    print("── TEIL B2 — n_signals monster-frei (ki_signal_score) ────────")
    ki_src = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
    # Der alte monster-gespeiste Zähler ist weg.
    _check("B2a monster speist n_signals NICHT mehr",
           "monster = monster_scores.get(t)\n        if monster is not None and monster >= 70" not in ki_src)
    # Neuer Zähler über ki_signal_score ≥ 70.
    _check("B2b n_signals wird über ki_signal_score ≥ 70 gespeist",
           "_ki_sig" in ki_src and "_ki_sig >= 70" in ki_src
           and "n_signals += 1" in ki_src)


# ── BLEIBT unangetastet ───────────────────────────────────────────────────────
def _test_untouched():
    print("── C — Berechnung/Sortierung unberührt ───────────────────────")
    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # Berechnung: apply_monster_score existiert unverändert + setzt monster_score.
    _check("C1 apply_monster_score berechnet weiter (Persistenz bleibt)",
           "def apply_monster_score(" in gr_src
           and 's["monster_score"] = monster' in gr_src)
    # Funktional: apply_monster_score setzt tatsächlich einen Wert.
    stock = {"score": 80.0, "ki_signal_score": 65}
    gr.apply_monster_score([stock])
    _check("C1b apply_monster_score setzt monster_score (funktional)",
           isinstance(stock.get("monster_score"), (int, float)))
    # Sortier-Option bleibt.
    _check("C2 Sortier-Option data-sort=\"monster\" bleibt",
           'data-sort="monster"' in gr_src)


# ── TEIL A2 — Neutral-Grau statt Ampel (Feinschliff, beide Pfade) ─────────────
def _test_neutral_color():
    print("── TEIL A2 — Monster neutral-grau (kein Ampel-Grün) ──────────")
    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    _check("A4 Neutral-Konstante _MONSTER_NEUTRAL_COLOR definiert",
           '_MONSTER_NEUTRAL_COLOR = "#94a3b8"' in gr_src)
    _check("A5 Score-Row: Monster nutzt _MONSTER_NEUTRAL_COLOR (nicht Ampel)",
           "m_col = _MONSTER_NEUTRAL_COLOR" in gr_src
           and "m_col = _tri_score_color(ms)" not in gr_src)
    _check("A6 Cockpit-Pillar: monster-Zweig auf _MONSTER_NEUTRAL_COLOR",
           'elif conf_key == "monster":' in gr_src
           and gr_src.count("col = _MONSTER_NEUTRAL_COLOR") >= 1)
    # Funktional: der neutrale Farbwert ist NICHT das Ampel-Grün.
    _check("A7 Neutral-Farbe ist grau, nicht grün (#22c55e)",
           gr._MONSTER_NEUTRAL_COLOR == "#94a3b8"
           and gr._MONSTER_NEUTRAL_COLOR != "#22c55e")


# ── TEIL B (Earnings-Alert) — kein "🔥 Monster"-Aufmacher ─────────────────────
def _test_earnings_body_neutral():
    print("── TEIL B (Earnings) — Body ohne 🔥-Monster-Aufmacher ────────")
    captured = {}

    def _fake_post(url, *a, **k):
        captured["url"] = url
        captured["data"] = k.get("data")
        return types.SimpleNamespace(status_code=200, text="ok")

    # NTFY erzwingen + requests.post abfangen (kein Netz).
    _orig_post = ka.requests.post
    _orig_en, _orig_topic = ka.NTFY_ENABLED, ka.NTFY_TOPIC
    try:
        ka.requests.post = _fake_post
        ka.NTFY_ENABLED = True
        ka.NTFY_TOPIC = "test_topic"
        ka.send_ntfy_alert("TSLA", 80, ["driver1"],
                           production_score=72.0, monster_score=95.0)
    finally:
        ka.requests.post = _orig_post
        ka.NTFY_ENABLED, ka.NTFY_TOPIC = _orig_en, _orig_topic

    body = (captured.get("data") or b"").decode("utf-8") if isinstance(
        captured.get("data"), (bytes, bytearray)) else str(captured.get("data"))
    _check("B-earn body gebaut (Push abgefangen)", bool(body) and "TSLA" in body,
           f"got {body!r}")
    _check("B-earn KEIN '🔥 Monster'-Aufmacher mehr", "🔥 Monster" not in body,
           f"got {body!r}")
    _check("B-earn Setup steht VOR Monster (Setup zuerst)",
           "Setup" in body and body.find("Setup") < body.find("Monster"),
           f"got {body!r}")
    _check("B-earn Monster nachrangig in Klammer",
           "(Monster 95)" in body, f"got {body!r}")
    # Grep: '🔥 Monster' nirgends mehr als Push-Headline im Code.
    ki_src = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    _check("B-grep kein '🔥 Monster' als Body-Headline im Code",
           '🔥 Monster' not in ki_src and '🔥 Monster' not in gr_src)


def main() -> int:
    _test_display()
    _test_neutral_color()
    _test_push_removed()
    _test_signal_counter()
    _test_earnings_body_neutral()
    _test_untouched()
    print()
    if _fails:
        print(f"✗ {len(_fails)} FAIL: {_fails}")
        return 1
    print("✓ alle Monster-Neutralisierungs-Tests grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
