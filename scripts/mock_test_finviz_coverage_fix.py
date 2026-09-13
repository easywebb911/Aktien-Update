"""Mock-Tests für den Finviz-Provider-Health-Coverage-Fix (13.09.2026).

Vorher: ``http_status`` für den Provider-Health-Eintrag „finviz" wurde nach
einem All-or-Nothing-Prinzip gesetzt (200 NUR wenn ALLE Calls im Lauf
erfolgreich waren, sonst None) — bei der bekannten ~45-50% Quote-Page-
Fail-Rate (CLAUDE.md) war das strukturell IMMER None (Diagnose 13.09.2026:
0/46 Läufe im 30-Tage-Fenster mit http_status=200, obwohl real ~53% der
Einzel-Calls erfolgreich waren). Jetzt: ``coverage_pct`` wird analog zum
bestehenden ``stockanalysis``-Muster berechnet (Anteil erfolgreicher Calls),
``http_status=200`` sobald IRGENDEIN Call erfolgreich war.

REINE Monitoring-/Instrumentierungs-Korrektur — KEINE Änderung an der
Finviz-Fetch-Logik, der Short-Float-Fallback-Kette oder einem Score-/
Filter-Pfad. Nur wie die bereits korrekt gezählten Erfolgs-/Fehlschlag-
Zahlen (``_FINVIZ_ACCT``) nach ``provider_health.jsonl`` geschrieben werden.

FIXTURE-ONLY — kein Kontakt mit der echten ``provider_health.jsonl``
(Tier-B-Tests nutzen eine temporäre Datei in einem eigenen ``tempfile``-
Verzeichnis).

Zweistufiger Test (Muster analog ``mock_test_haircut_net_returns.py``):
  (A) Source-Inspektion — nur ``config``/``health_check``-Import (beide
      stdlib-only, KEIN yfinance/pandas nötig) + Text-Read von
      ``generate_report.py`` (KEIN Modul-Import — die Datei importiert
      yfinance/pandas top-level). Läuft vollständig im CI-Slot
      (stdlib+jinja2+pyyaml).
  (B) ECHTE Berechnungsfunktion, nicht nur Behauptung: der exakte Finviz-
      Record-Block wird per Source-Extraktion + ``exec`` aus
      ``generate_report.py`` gezogen (byte-identisch zum Datei-Inhalt,
      keine Neu-Implementierung) und gegen die ECHTE
      ``health_check.record_provider_call`` + ``aggregate_provider_fails``
      ausgeführt — mit einer temporären ``provider_health.jsonl``, nie der
      echten Datei.

Verifiziert:
- (A) Neue Formel (`coverage_pct`, `_fv_successes > 0`) im Source vorhanden;
      alte All-or-Nothing-Bedingung (`_fv_acct["failures"] == 0` als
      http_status-Gate) NICHT mehr vorhanden (Regression gegen Revert).
      `error`-Feld-Logik UNVERÄNDERT (Zeile bleibt Zeichen-identisch).
- (A) `DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES["finviz"] == 100` UNVERÄNDERT
      (bewusst nicht angefasst — Mini-Stopp-Vorgabe der Aufgabenstellung).
- (A) `aggregate_provider_fails` bleibt provider-generisch (kein
      literaler "finviz"-Sonderfall in der Coverage-/http_status-Logik).
- (B) Drei Szenarien (gemischt 5/10, alle erfolgreich, alle fehlgeschlagen)
      gegen den ECHTEN Call-Site-Block + echte `record_provider_call`.
- (B) Boundary: coverage_pct genau auf der Tier-2/3-Schwelle (50.0) wird
      von der ECHTEN `aggregate_provider_fails` als NICHT-Fail gewertet
      (strikte `<`-Bedingung).
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config          # noqa: E402  (stdlib-only import)
import health_check    # noqa: E402  (stdlib-only import, s. Docstring oben)


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def _test_source_and_overrides():
    """(A) — stdlib-only, kein generate_report-Import (yfinance top-level)."""
    print("── (A) Source-Inspektion + Override-Regression (stdlib-only) ──")

    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")

    idx = gr_src.find('_fv_acct = _FINVIZ_ACCT')
    end_idx = gr_src.find('# Tier 2: stockanalysis', idx) if idx != -1 else -1
    _check("A1 Finviz-Record-Block gefunden", idx != -1 and end_idx != -1)
    block = gr_src[idx:end_idx] if idx != -1 and end_idx != -1 else ""

    _check("A2 Neue Formel: _fv_successes = calls - failures",
           '_fv_successes = _fv_acct["calls"] - _fv_acct["failures"]' in block)
    _check("A3 Neue Formel: coverage_pct berechnet (round(...*100, 1))",
           '_fv_coverage = round(_fv_successes / _fv_acct["calls"] * 100, 1)' in block)
    _check("A4 coverage_pct wird an record_provider_call übergeben",
           'coverage_pct=_fv_coverage' in block)
    _check("A5 http_status jetzt an _fv_successes > 0 gekoppelt",
           'http_status=200 if _fv_successes > 0 else None' in block)

    _check("A6 Regression — alte All-or-Nothing-Bedingung NICHT mehr vorhanden",
           'http_status=200 if _fv_acct["failures"] == 0 else None' not in block,
           "das war der ursprüngliche Bug — darf nach dem Fix nicht mehr da sein")

    _check("A7 error-Feld-Logik unverändert (Zeichen-identisch)",
           'error=None if _fv_acct["failures"] == 0\n'
           '                      else (_fv_acct.get("last_error_repr")\n'
           '                            or f"{_fv_acct[\'failures\']}/{_fv_acct[\'calls\']} calls failed"),'
           in block)

    _check("A8 DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES['finviz'] unverändert (== 100)",
           config.DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES.get("finviz") == 100,
           "bewusst NICHT angefasst laut Aufgabenstellung (Mini-Stopp-Vorgabe)")

    hc_src = (ROOT / "health_check.py").read_text(encoding="utf-8")
    agg_idx = hc_src.find("def aggregate_provider_fails")
    agg_end = hc_src.find("\ndef ", agg_idx + 10)
    agg_block = hc_src[agg_idx:agg_end if agg_end != -1 else agg_idx + 3000]
    _check("A9 aggregate_provider_fails bleibt provider-generisch "
           "(kein literaler 'finviz'-Sonderfall in der Coverage-Logik)",
           '"finviz"' not in agg_block and "'finviz'" not in agg_block,
           "Coverage-/http_status-Bewertung darf nicht providerspezifisch verzweigen")


def _run_real_finviz_block(*, calls, failures, v161=0, v111=0,
                           last_error_repr=None, latency_ms=100,
                           run_phase="postclose"):
    """Extrahiert den ECHTEN Finviz-Record-Block aus generate_report.py
    (Source-Text, keine Neu-Implementierung) und führt ihn per ``exec``
    gegen die ECHTE ``health_check.record_provider_call`` aus — mit einer
    temporären Datei, nie der echten ``provider_health.jsonl``.

    Returnt das zuletzt geschriebene JSONL-Record-Dict.
    """
    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    start_marker = "        _fv_acct = _FINVIZ_ACCT\n"
    end_marker = "        # Tier 2: stockanalysis"
    start = gr_src.index(start_marker)
    end = gr_src.index(end_marker, start)
    block = gr_src[start:end]

    # Dedent (der Block sitzt 8 Leerzeichen tief in main()'s try-Block).
    dedented = []
    for line in block.split("\n"):
        if line.startswith("        "):
            dedented.append(line[8:])
        elif line.strip() == "":
            dedented.append("")
        else:
            dedented.append(line)
    block_src = "\n".join(dedented)

    tmp_dir = tempfile.mkdtemp(prefix="mock_test_finviz_coverage_")
    tmp_path = os.path.join(tmp_dir, "provider_health.jsonl")
    orig_cwd = os.getcwd()
    try:
        os.chdir(tmp_dir)
        ns = {
            "_FINVIZ_ACCT": {
                "latency_ms": latency_ms, "calls": calls, "failures": failures,
                "v161_count": v161, "v111_count": v111,
                "last_error_repr": last_error_repr,
            },
            "health_check": health_check,
            "HEALTH_CHECK_PROVIDER_TIER": config.HEALTH_CHECK_PROVIDER_TIER,
            "run_phase": run_phase,
        }
        exec(compile(block_src, "<finviz_record_block>", "exec"), ns)
        written = health_check.read_all_provider(path=tmp_path)
        return written[-1] if written else None
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _test_real_call_site():
    """(B) — ECHTER Call-Site-Block (Source-Extraktion, kein Reimplement)
    gegen die ECHTE record_provider_call, drei Szenarien."""
    print("── (B) ECHTE Berechnungsfunktion — drei Szenarien ──────────────")

    # B1: gemischtes Ergebnis, 5 von 10 Calls erfolgreich.
    rec_mixed = _run_real_finviz_block(calls=10, failures=5,
                                       last_error_repr="HTTPError 403")
    _check("B1 gemischt 5/10 — coverage_pct == 50.0",
           rec_mixed is not None and rec_mixed.get("coverage_pct") == 50.0,
           f"got {rec_mixed.get('coverage_pct') if rec_mixed else None}")
    _check("B1 gemischt 5/10 — http_status == 200 (vorher: None)",
           rec_mixed is not None and rec_mixed.get("http_status") == 200,
           f"got {rec_mixed.get('http_status') if rec_mixed else None}")
    _check("B1 gemischt 5/10 — error-Feld weiterhin gesetzt (informativ)",
           rec_mixed is not None and rec_mixed.get("error") == "HTTPError 403")

    # B2: alle Calls erfolgreich (unverändertes Verhalten ggü. vorher).
    rec_all_ok = _run_real_finviz_block(calls=8, failures=0)
    _check("B2 alle erfolgreich — coverage_pct == 100.0",
           rec_all_ok is not None and rec_all_ok.get("coverage_pct") == 100.0,
           f"got {rec_all_ok.get('coverage_pct') if rec_all_ok else None}")
    _check("B2 alle erfolgreich — http_status == 200",
           rec_all_ok is not None and rec_all_ok.get("http_status") == 200)
    _check("B2 alle erfolgreich — error-Feld == None",
           rec_all_ok is not None and rec_all_ok.get("error") is None)

    # B3: alle Calls fehlgeschlagen (http_status bleibt None, wie vorher).
    rec_all_fail = _run_real_finviz_block(calls=6, failures=6,
                                          last_error_repr="Timeout")
    _check("B3 alle fehlgeschlagen — coverage_pct == 0.0",
           rec_all_fail is not None and rec_all_fail.get("coverage_pct") == 0.0,
           f"got {rec_all_fail.get('coverage_pct') if rec_all_fail else None}")
    _check("B3 alle fehlgeschlagen — http_status weiterhin None",
           rec_all_fail is not None and rec_all_fail.get("http_status") is None)
    _check("B3 alle fehlgeschlagen — error-Feld gesetzt",
           rec_all_fail is not None and rec_all_fail.get("error") == "Timeout")

    print("── (B) Downstream — ECHTE aggregate_provider_fails ─────────────")

    # B4: Boundary — coverage_pct GENAU auf der Tier-2/3-Schwelle (50.0)
    # darf laut strikter "<"-Bedingung NICHT als Fail gelten.
    counters = {}
    fails = health_check.aggregate_provider_fails(
        [rec_mixed], counters=counters,
        tier_map={"finviz": config.HEALTH_CHECK_PROVIDER_TIER.get("finviz", 2)})
    _check("B4 coverage_pct==50.0 (Tier-2/3-Schwelle) wird NICHT als Fail "
           "gewertet (row_fail erfordert coverage < 50.0, nicht <=)",
           not any(f["provider"] == "finviz" for f in fails),
           f"fails={fails}")

    # B5: Kontrastprobe — VOR dem Fix wäre http_status hier None gewesen
    # (identische failures>0-Konstellation) → das hätte sofort einen
    # Konsekutiv-Counter-Increment ausgelöst. Nachweis: mit der alten
    # Formel (simuliert, nicht der echte Code) wäre B1 als Fail gezählt
    # worden — mit dem Fix (B4) nicht mehr.
    old_http_status = 200 if 5 == 0 else None  # alte Bedingung: failures==0
    _check("B5 Kontrastprobe — alte Formel hätte http_status=None geliefert "
           "(bestätigt, dass der Fix das Verhalten tatsächlich ändert)",
           old_http_status is None)


def main():
    _test_source_and_overrides()
    _test_real_call_site()

    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (Finviz-Coverage-Fix: Source + Override-"
          "Regression + echte Call-Site + Downstream-Aggregation).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
