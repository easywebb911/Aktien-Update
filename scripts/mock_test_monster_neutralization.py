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
    print("── TEIL A — Konfidenz-Wasserzeichen ──────────────────────────")
    # Backtest-Fixture mit genug return_10d-Einträgen → setup=robust.
    bh = [{"return_10d": 5.0} for _ in range(config.SCORE_CONFIDENCE_N_ROBUST + 10)]
    conf = gr.compute_score_confidence(bh)

    _check("A1 monster-tier == 'heuristisch' (nicht setup-vererbt)",
           conf["monster"]["tier"] == "heuristisch",
           f"got {conf['monster']['tier']}")
    _check("A2 setup-tier == 'robust' (unberührt, Differenzierung belegt)",
           conf["setup"]["tier"] == "robust",
           f"got {conf['setup']['tier']}")
    _check("A2b monster-note nennt die Kollaps-Empirik (ehrlich)",
           "0.76" in conf["monster"]["note"] and "kollabiert" in conf["monster"]["note"])

    # _conf_class liest den Modul-State → setzen und prüfen.
    gr._SCORE_CONFIDENCE = conf
    m_css, m_title, m_aria = gr._conf_class("monster")
    s_css, s_title, s_aria = gr._conf_class("setup")
    _check("A3 _conf_class('monster') → sb-conf-heur (Wasserzeichen)",
           m_css == "sb-conf-heur" and "heuristisch" in m_title,
           f"got css={m_css!r} title={m_title!r}")
    _check("A3b _conf_class('setup') bleibt robust (kein Wasserzeichen)",
           s_css == "sb-conf-robust" and s_title == "",
           f"got css={s_css!r} title={s_title!r}")


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


def main() -> int:
    _test_display()
    _test_push_removed()
    _test_signal_counter()
    _test_untouched()
    print()
    if _fails:
        print(f"✗ {len(_fails)} FAIL: {_fails}")
        return 1
    print("✓ alle Monster-Neutralisierungs-Tests grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
