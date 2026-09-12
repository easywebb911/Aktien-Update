"""Mock-Tests für den Ausführungskosten-Haircut (Netto-Renditefelder, 12.09.2026).

Ergänzt ``return_3d/5d/10d`` und ``max_gain_pct`` in ``backtest_history.json``
um parallele ``_net``-Geschwisterfelder, reduziert um ``HAIRCUT_ROUND_TRIP_PCT``
(``config.py`` — konservative Literaturschätzung, KEIN belegter Fakt, siehe
SESSION_HANDOVER für die Herleitung). Bestehende Brutto-Felder bleiben
UNVERÄNDERT — reine additive Ergänzung.

FIXTURE-ONLY — kein Kontakt mit ``backtest_history.json`` oder anderen Live-
Dateien (Tier B nutzt temporäre Dateien in einem eigenen ``tempfile``-
Verzeichnis, nie das echte Repo-File).

Zweistufiger Test (Muster analog ``mock_test_max_gain_pct.py``):
  (A) S10-Whitelist + Schema-v4 + Source-Inspektions-Regression + Wiring —
      nur ``config``-Import + Text-Read von ``backtest_history.py``/
      ``ki_agent.py`` (KEIN Modul-Import — beide importieren yfinance top-
      level). Läuft im stdlib-only CI-Slot (Allowlist).
  (B) Formel-Tests (``apply_round_trip_haircut``) + ECHTE Berechnungsfunktion
      — braucht pandas + yfinance (weil ``backtest_history``/``ki_agent``
      yfinance top-level importieren). Wird übersprungen wenn nicht
      verfügbar (CI-Slot); läuft lokal / im Daily-Run-Environment
      vollständig.

Verifiziert:
- (A) alle 4 neuen Felder in S10_OBSERVED_FIELDS (sonst WARN, Lehre #388);
      NICHT in MUSS/LAG (dieselbe 0.0/None-Reifegrad-Problematik wie ihre
      Brutto-Geschwister). Schema bleibt v4 (kein Bump).
- (A) Regression: bestehende Brutto-Init-Placeholder + Brutto-Berechnungs-
      Zeilen sind UNVERÄNDERT im Source vorhanden.
- (A) Wiring: neue Init-Placeholder + apply_round_trip_haircut-Aufrufe sind
      an den erwarteten Stellen im Source vorhanden; ki_agent.py importiert
      die Funktion aus backtest_history (Single-Source-of-Truth, keine
      Dopplung).
- (A) Scope-Grenze: return_Xd_t1 bekommt BEWUSST kein _net-Pendant (kein
      Oversight, sondern Scope-Entscheidung).
- (B) apply_round_trip_haircut: None-Guard, bekannte Formel-Werte (0/±10/
      +1000 Brutto-Prozent) gegen von Hand vorgerechnete Erwartungswerte.
- (B) ECHTE Berechnungsfunktion, nicht nur isolierte Hilfsfunktion:
      * max_gain_pct_net — Kette aus den REALEN Funktionen
        ``_compute_max_gain_pct`` + ``apply_round_trip_haircut`` auf einer
        synthetischen Bar-Fixture (identisch zur F1-Fixture in
        ``mock_test_max_gain_pct.py``).
      * return_10d_net — VOLLSTÄNDIGER Integrationstest der ECHTEN
        ``ki_agent.update_backtest_returns()`` gegen eine monkeypatchte
        ``yf.download``-Fixture + temporäre backtest_history.json-Datei.
        Prüft: (1) return_10d (Brutto) hat den erwarteten Wert, (2)
        return_10d_net ist EXAKT ``apply_round_trip_haircut(return_10d)``,
        (3) bestehende Felder (score, max_gain_pct) bleiben unverändert
        (Regressionstest gegen versehentliche Fremd-Mutation).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def _test_s10_schema_and_wiring():
    """(A) — läuft ohne pandas/yfinance, stdlib-only. CI-Slot-Kompatibel."""
    print("── (A) S10-Klassifikation + Schema-v4 + Source-Wiring (stdlib-only) ──")

    new_fields = ("return_3d_net", "return_5d_net", "return_10d_net",
                  "max_gain_pct_net")

    for f in new_fields:
        _check(f"A1 {f} in S10_OBSERVED_FIELDS",
               f in config.S10_OBSERVED_FIELDS,
               "sonst feuert _s10_check_unknown_fields WARN am 1. Record (Lehre #388)")
        _check(f"A2 {f} NICHT in S10_MUSS_FIELDS",
               f not in config.S10_MUSS_FIELDS,
               "0.0/None-Semantik-Overload analog Brutto-Geschwister — kein sinnvoller MUSS-Check")
        _check(f"A3 {f} NICHT in S10_LAG_FIELDS",
               f not in config.S10_LAG_FIELDS,
               "reine Transformation des Brutto-Felds, kein eigener Lag-Zeitpunkt")

    _check("A4 HAIRCUT_ROUND_TRIP_PCT existiert und ist negativ",
           hasattr(config, "HAIRCUT_ROUND_TRIP_PCT")
           and isinstance(config.HAIRCUT_ROUND_TRIP_PCT, float)
           and config.HAIRCUT_ROUND_TRIP_PCT < 0,
           f"got {getattr(config, 'HAIRCUT_ROUND_TRIP_PCT', '<missing>')}")

    cfg_src = (ROOT / "config.py").read_text(encoding="utf-8")
    _check("A5 HAIRCUT_ROUND_TRIP_PCT-Kommentar markiert Schätzungs-Charakter",
           "KONSERVATIVE LITERATURSCHÄTZUNG" in cfg_src
           and "KEIN BELEGTER FAKT" in cfg_src
           and "SESSION_HANDOVER" in cfg_src,
           "Herkunfts-/Schätzungs-Hinweis muss direkt am Konstantenblock stehen")

    bh_src = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    ka_src = (ROOT / "ki_agent.py").read_text(encoding="utf-8")

    # Schema-Version — additiv, KEIN v4-Bump (Source-Inspektion, analog
    # mock_test_max_gain_pct.py A5).
    _check("A6 Schema-Version bleibt 4 (Source-Inspektion, KEIN Bump)",
           '"backtest_schema_version": 4' in bh_src
           and '"backtest_schema_version": 5' not in bh_src,
           "additive Erweiterung darf keinen Bump erzeugen")

    # Regression: bestehende Brutto-Init-Placeholder unverändert vorhanden.
    for gross_line in ('"return_3d":     None,', '"return_5d":     None,',
                        '"return_10d":    None,', '"max_gain_pct": 0.0,'):
        _check(f"A7 Regression — Brutto-Init unverändert: {gross_line.strip()}",
               gross_line in bh_src)

    # Neue Init-Placeholder vorhanden.
    for net_line in ('"return_3d_net":  None,', '"return_5d_net":  None,',
                      '"return_10d_net": None,', '"max_gain_pct_net": None,'):
        _check(f"A8 Neuer Init-Placeholder vorhanden: {net_line.strip()}",
               net_line in bh_src)

    _check("A9 apply_round_trip_haircut in backtest_history.py definiert",
           "def apply_round_trip_haircut(" in bh_src)

    # Wiring: max_gain_pct_net wird NUR innerhalb desselben "in e"-Guards wie
    # max_gain_pct selbst gesetzt (kein Backfill auf Alt-Records ohne Feld).
    guard_idx = bh_src.find('if "max_gain_pct" in e:')
    _check("A10 max_gain_pct-Rolling-Update-Guard gefunden", guard_idx != -1)
    guard_block = bh_src[guard_idx:guard_idx + 600] if guard_idx != -1 else ""
    _check("A11 max_gain_pct_net wird im selben Guard-Block gesetzt",
           'e["max_gain_pct_net"] = apply_round_trip_haircut(mg)' in guard_block,
           "muss INNERHALB des 'in e'-Guards stehen, sonst Backfill-Risiko auf Alt-Records")
    # Regression: die Brutto-Zuweisung selbst muss VOR der Netto-Zuweisung
    # stehen (net wird AUS dem frisch berechneten mg abgeleitet).
    _check("A12 Regression — Brutto-Zuweisung e[\"max_gain_pct\"] = mg unverändert vorhanden",
           'e["max_gain_pct"] = mg' in guard_block)
    _check("A13 Reihenfolge: Brutto-Zuweisung VOR Netto-Zuweisung",
           guard_block.find('e["max_gain_pct"] = mg')
           < guard_block.find('e["max_gain_pct_net"] = apply_round_trip_haircut(mg)'))

    # ki_agent.py: Import + return_Xd_net-Wiring.
    _check("A14 ki_agent.py importiert apply_round_trip_haircut aus backtest_history",
           "from backtest_history import apply_round_trip_haircut" in ka_src)

    ret_idx = ka_src.find('e[k0] = round((c / entry_basis - 1) * 100, 2)')
    _check("A15 return_Xd-Brutto-Zuweisung (ki_agent) unverändert vorhanden", ret_idx != -1)
    ret_block = ka_src[ret_idx:ret_idx + 400] if ret_idx != -1 else ""
    _check("A16 return_Xd_net wird direkt danach aus dem Brutto-Wert abgeleitet",
           'e[f"{k0}_net"] = apply_round_trip_haircut(e[k0])' in ret_block)
    _check("A17 Reihenfolge: Brutto-Zuweisung VOR Netto-Zuweisung (ki_agent)",
           ret_block.find('e[k0] = round((c / entry_basis - 1) * 100, 2)')
           < ret_block.find('e[f"{k0}_net"] = apply_round_trip_haircut(e[k0])'))

    # Scope-Grenze: return_Xd_t1 bekommt BEWUSST kein _net-Pendant.
    _check("A18 Scope: kein return_Xd_t1_net irgendwo im Source (bewusste Grenze, kein Oversight)",
           "_t1_net" not in bh_src and "_t1_net" not in ka_src
           and "return_3d_t1_net" not in config.S10_OBSERVED_FIELDS
           and "return_5d_t1_net" not in config.S10_OBSERVED_FIELDS
           and "return_10d_t1_net" not in config.S10_OBSERVED_FIELDS)


def _test_real_functions():
    """(B) — braucht pandas + yfinance (backtest_history/ki_agent importieren
    yfinance top-level). Testet die ECHTEN Produktions-Funktionen, keine
    isolierten Neu-Implementierungen."""
    try:
        import pandas as pd  # noqa: F401
        import yfinance  # noqa: F401
        import backtest_history as bh
    except ImportError as exc:
        print(f"── (B) Formel-/Integrations-Tests: ÜBERSPRUNGEN — {exc} nicht "
              "verfügbar (CI-Slot stdlib+jinja2+pyyaml). Läuft im Daily-Run-"
              "Environment mit pandas+yfinance vollständig.")
        return

    print("── (B) apply_round_trip_haircut — Formel gegen Handrechnung ──")

    _check("B-F1 None-Guard", bh.apply_round_trip_haircut(None) is None)

    # Handrechnung: h=4%, half=2%. net = (1+g/100)*(1-half)/(1+half) - 1, ×100.
    def _expected(gross, haircut=4.0):
        h = abs(haircut) / 100.0
        half = h / 2.0
        gf = 1.0 + gross / 100.0
        return round((gf * (1.0 - half) / (1.0 + half) - 1.0) * 100.0, 2)

    for gross in (0.0, 10.0, -10.0, 1000.0, -50.0):
        got = bh.apply_round_trip_haircut(gross)
        exp = _expected(gross)
        _check(f"B-F2 gross={gross} → net={exp}", got == exp, f"got {got}")

    _check("B-F3 großer Gewinn: multiplikativ konservativer als flache Subtraktion",
           bh.apply_round_trip_haircut(1000.0) < 1000.0 - 4.0,
           "956.86 muss < 996.00 sein (Kern-Begründung für multiplikativ statt subtraktiv)")

    _check("B-F4 custom haircut_pct-Parameter wird respektiert",
           bh.apply_round_trip_haircut(10.0, haircut_pct=-8.0) == _expected(10.0, 8.0))

    print("── (B) ECHTE Berechnungsfunktion — max_gain_pct_net (verkettete Produktions-Funktionen) ──")

    # Identische Fixture-Form wie mock_test_max_gain_pct.py F1 (+50%).
    df1 = pd.DataFrame({"High": [11.0, 12.0, 15.0], "Low": [10.0, 11.0, 13.0]})
    mg = bh._compute_max_gain_pct(df1)
    _check("B-G1 _compute_max_gain_pct(F1) = 50.0 (Referenzwert)", mg == 50.0, f"got {mg}")
    net = bh.apply_round_trip_haircut(mg)
    _check("B-G2 max_gain_pct_net = apply_round_trip_haircut(50.0) = 44.12",
           net == _expected(50.0), f"got {net}")

    print("── (B) ECHTE Berechnungsfunktion — ki_agent.update_backtest_returns() (Vollintegration) ──")
    _test_ki_agent_integration()


def _test_ki_agent_integration():
    """Ruft die ECHTE ``ki_agent.update_backtest_returns()`` gegen eine
    monkeypatchte yfinance-Fixture + temporäre Datei auf. Kein Netzwerk-
    Zugriff, keine Berührung der echten backtest_history.json."""
    import pandas as pd
    import ki_agent

    dates = pd.bdate_range("2026-01-05", periods=30)
    closes = pd.Series([100.0 + i for i in range(30)], index=dates)
    df = pd.DataFrame({
        "Open": closes, "High": closes + 0.5, "Low": closes - 0.5,
        "Close": closes, "Volume": 1000,
    })
    entry_date = dates[5]
    entry_date_str = entry_date.strftime("%d.%m.%Y")

    tmp_dir = tempfile.mkdtemp(prefix="mock_test_haircut_")
    bt_path = os.path.join(tmp_dir, "backtest_history.json")

    entry = {
        "date": entry_date_str, "ticker": "TESTX", "score": 80.0,
        "entry_price": None, "entry_price_t1": None,
        "return_3d": None, "return_5d": None, "return_10d": None,
        "return_3d_t1": None, "return_5d_t1": None, "return_10d_t1": None,
        "return_3d_net": None, "return_5d_net": None, "return_10d_net": None,
        "max_gain_pct": 0.0, "max_gain_pct_net": None,
        "max_drawdown_pct": 0.0,
    }
    with open(bt_path, "w", encoding="utf-8") as fh:
        json.dump([entry], fh)

    # Isolierte Monkeypatches — NUR auf dem Modul-Objekt, keine globalen
    # Seiteneffekte über diesen Testlauf hinaus (Python-Prozess endet danach).
    orig_backtest_file = ki_agent.BACKTEST_FILE
    orig_download = ki_agent.yf.download
    orig_datetime = ki_agent.datetime

    class _FakeDateTime(orig_datetime):
        @classmethod
        def now(cls, tz=None):
            return orig_datetime(2026, 1, 20, tzinfo=tz)

    try:
        ki_agent.BACKTEST_FILE = bt_path
        ki_agent.yf.download = lambda tickers, **kw: df
        ki_agent.datetime = _FakeDateTime

        ki_agent.update_backtest_returns()

        with open(bt_path, encoding="utf-8") as fh:
            result = json.load(fh)
    finally:
        ki_agent.BACKTEST_FILE = orig_backtest_file
        ki_agent.yf.download = orig_download
        ki_agent.datetime = orig_datetime

    e = result[0]
    entry_basis = float(closes.iloc[5])
    c10 = float(closes.iloc[5 + 10])
    expected_gross_10 = round((c10 / entry_basis - 1) * 100, 2)

    _check("B-I1 return_10d (Brutto) korrekt aus echtem Preisverlauf",
           e["return_10d"] == expected_gross_10,
           f"expected {expected_gross_10}, got {e['return_10d']}")

    import backtest_history as bh
    expected_net_10 = bh.apply_round_trip_haircut(e["return_10d"])
    _check("B-I2 return_10d_net = apply_round_trip_haircut(return_10d) EXAKT",
           e["return_10d_net"] == expected_net_10,
           f"expected {expected_net_10}, got {e['return_10d_net']}")

    _check("B-I3 return_10d_net != return_10d (Haircut hat tatsächlich gewirkt)",
           e["return_10d_net"] != e["return_10d"])

    # Regressionstest: unbeteiligte Bestandsfelder unverändert.
    _check("B-I4 Regression — score unverändert (80.0)", e["score"] == 80.0)
    _check("B-I5 Regression — max_gain_pct unverändert (0.0, andere Rolling-"
           "Update-Funktion in backtest_history.py, nicht hier)",
           e["max_gain_pct"] == 0.0)
    _check("B-I6 max_gain_pct_net bleibt None (kein Backfill aus 0.0-Platzhalter)",
           e["max_gain_pct_net"] is None,
           "kritischer Guard — sonst würde ein synthetischer Haircut-Wert auf "
           "einem 'noch nicht berechnet'-Platzhalter wie echte Daten aussehen")

    # Scope-Grenze bestätigt: return_Xd_t1 bekam kein _net-Pendant.
    _check("B-I7 Scope — return_10d_t1_net existiert nicht im Ergebnis-Record",
           "return_10d_t1_net" not in e)


def main():
    _test_s10_schema_and_wiring()
    _test_real_functions()

    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (Haircut-Netto-Renditefelder: S10 + Schema + "
          "Wiring + Formel + echte Berechnungsfunktionen + Vollintegration).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
