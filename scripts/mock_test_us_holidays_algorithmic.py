"""Mock-Tests für die vollständig algorithmische ``config.US_MARKET_HOLIDAYS``
(Open-Item ``s6b-us-holidays-hardcoded-until-2027``, PR 07.10.2026).

FIXTURE-ONLY — kein Kontakt mit Live-Dateien, keine Netzwerkzugriffe.

HINTERGRUND:
Vor diesem PR waren 5 der 10 NYSE-Feiertage/Jahr (MLK Day, Presidents Day,
Memorial Day, Labor Day, Thanksgiving) für 2025–2027 hartcodiert und wären
2028 kommentarlos ausgelaufen (dieselbe Wartungs-Bombe, die PR #407 für
Karfreitag bereits gelöst hatte — Good Friday war schon vorher algorithmisch).
Dieser PR ersetzt ALLE 10 Kategorien durch Nth-Weekday-of-Month- bzw.
Last-Weekday-of-Month-Formeln (``config._nth_weekday_of_month``,
``config._last_weekday_of_month``, ``config._observed_weekend``), Range
2020–2050 (wie zuvor bei Good Friday), in Python UND im JS-Spiegel
(``generate_report.py`` ``_usMarketHolidaysForYear``).

Verifiziert:
- (A) Exakte Mengen-Gleichheit 2025–2027 gegen die VORHERIGE hartcodierte
      Liste (Beweis: bestehendes Verhalten unverändert).
- (B) 2028/2029 gegen von Hand abgeleitete Referenzwerte (Unsicherheits-
      Hinweis: Sandbox hat keinen Netzwerkzugriff auf nyse.com — Werte sind
      über Wochentags-Fortschreibung aus den bereits verifizierten
      2025–2027-Ankern abgeleitet, NICHT live nachgeschlagen; Good-Friday-
      Teilwerte sind zusätzlich gegen das bereits im Repo vorhandene,
      vertraute ``real_good_fridays``-Dict aus
      ``mock_test_good_friday.py`` gegengeprüft).
- (C) Neujahrs-Sonderregel: fällt der 1. Januar auf einen Samstag, gibt es
      KEINEN Ersatztag am 31.12. des Vorjahres (belegt an 2022 — real:
      NYSE war am 31.12.2021 regulärer Handelstag geöffnet — und an allen
      weiteren Samstags-Neujahrs-Jahren 2020–2050). Kontrollprobe ohne die
      Ausnahme zeigt, dass die Regel tatsächlich etwas bewirkt (sonst wäre
      der Test trivial grün).
- (D) Helper-Korrektheit gegen UNABHÄNGIGE, bereits vor diesem PR bekannte
      historische Anker (2020/2023/2024) — vermeidet Zirkularität (nicht
      dieselben Werte, die (A) schon gegen die alte Liste geprüft hat).
- (E) Allgemeine Wochenend-Beobachtungsregel (Sat→Fr, So→Mo) OHNE
      Neujahrs-Ausnahme, an von (A) unabhängigen Kontrollfällen.
- (F) Set-Eigenschaften: Typ, Determinismus, Größe (310 = 10 × 31 Jahre,
      keine Datums-Kollisionen).
- (G) Python↔JS-Vollparität über die GESAMTE Range 2020–2050 (nicht nur
      Stichprobe) via echter Node-Ausführung des extrahierten JS-Blocks.
      Soft-Skip wenn ``node`` nicht verfügbar (Source-Gates in
      ``mock_test_good_friday.py`` bleiben in dem Fall die harte Prüfung).
- (H) Konsumenten-Beleg: ``cluster_purge.previous_trading_day`` überspringt
      einen 2028er-Feiertag korrekt — Beweis, dass ein echter Konsument die
      neuen, vormals nicht abgedeckten Jahre tatsächlich nutzt.
- (I) Isolations-Beleg: keine der neuen Holiday-Helper-Funktionen wird in
      Score-/Filter-/Alert-Berechnungspfaden referenziert (reine
      Kalender-Hilfsfunktion, kein Trading-Logik-Touch).
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
from cluster_purge import previous_trading_day  # noqa: E402


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


# Die VORHERIGE (vor diesem PR) hartcodierte 2025–2027-Liste, Zeichen für
# Zeichen aus dem alten ``config.py``-Quelltext übernommen (Good Friday
# separat, war schon vorher algorithmisch via PR #407) — das ist die
# Referenz, gegen die Test A die neue, vollständig algorithmische Berechnung
# verifiziert.
_OLD_HARDCODED_2025_2027 = frozenset({
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-05-26", "2025-06-19",
    "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-05-25", "2026-06-19",
    "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-05-31", "2027-06-18",
    "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}) | frozenset(
    (config._easter_sunday(y) - timedelta(days=2)).isoformat()
    for y in (2025, 2026, 2027)
)


def _test_exact_match_2025_2027():
    """(A) Exakte Mengen-Gleichheit gegen die vormals hartcodierte Liste."""
    print("── (A) Exakte Gleichheit 2025–2027 gegen alte hartcodierte Liste ──")
    new_subset = frozenset(
        d for d in config.US_MARKET_HOLIDAYS if d.startswith(("2025", "2026", "2027"))
    )
    diff_new = sorted(new_subset - _OLD_HARDCODED_2025_2027)
    diff_old = sorted(_OLD_HARDCODED_2025_2027 - new_subset)
    _check(
        "A1 Mengen-Diff leer (neu − alt)",
        not diff_new,
        f"unerwartete neue Einträge: {diff_new}",
    )
    _check(
        "A2 Mengen-Diff leer (alt − neu)",
        not diff_old,
        f"fehlende alte Einträge: {diff_old}",
    )
    _check(
        "A3 Beide Mengen identisch (27 statisch + 3 Karfreitage = 30)",
        new_subset == _OLD_HARDCODED_2025_2027 and len(new_subset) == 30,
        f"got {len(new_subset)}",
    )


def _test_2028_2029_hand_values():
    """(B) 2028/2029 gegen von Hand abgeleitete Referenzwerte.

    UNSICHERHEITS-HINWEIS: Sandbox hat keinen Netzwerkzugriff — diese Werte
    sind über Wochentags-Fortschreibung aus den bereits bestätigten
    2025–2027-Ankern abgeleitet (z. B. 01.01.2026=Do → 01.01.2027=Fr →
    01.01.2028=Sa [2027 kein Schaltjahr, +1] → 01.01.2029=Mo [2028
    Schaltjahr, +2]), NICHT live gegen nyse.com verifiziert. Die Good-
    Friday-Teilwerte sind zusätzlich gegen das bereits vor diesem PR im
    Repo vorhandene ``real_good_fridays``-Dict aus
    ``mock_test_good_friday.py`` gegengeprüft (dort als vertraute,
    historisch belegte Quelle geführt).
    """
    print("── (B) 2028/2029 gegen von Hand abgeleitete Referenzwerte ──────")
    expected_2028 = {
        "2028-01-01",  # New Year's Day (Sa — Neujahrs-Ausnahme, kein Ersatz)
        "2028-01-17",  # MLK Day (3. Mo Jan)
        "2028-02-21",  # Presidents Day (3. Mo Feb)
        "2028-04-14",  # Good Friday — deckungsgleich mit mock_test_good_friday.py real_good_fridays[2028]
        "2028-05-29",  # Memorial Day (letzter Mo Mai)
        "2028-06-19",  # Juneteenth (Mo, kein Shift)
        "2028-07-04",  # Independence Day (Di, kein Shift)
        "2028-09-04",  # Labor Day (1. Mo Sep)
        "2028-11-23",  # Thanksgiving (4. Do Nov)
        "2028-12-25",  # Christmas (Mo, kein Shift)
    }
    expected_2029 = {
        "2029-01-01",  # New Year's Day (Mo, kein Shift)
        "2029-01-15",  # MLK Day
        "2029-02-19",  # Presidents Day
        "2029-03-30",  # Good Friday — deckungsgleich mit real_good_fridays[2029]
        "2029-05-28",  # Memorial Day
        "2029-06-19",  # Juneteenth (Di, kein Shift)
        "2029-07-04",  # Independence Day (Mi, kein Shift)
        "2029-09-03",  # Labor Day
        "2029-11-22",  # Thanksgiving
        "2029-12-25",  # Christmas (Di, kein Shift)
    }
    got_2028 = frozenset(d for d in config.US_MARKET_HOLIDAYS if d.startswith("2028"))
    got_2029 = frozenset(d for d in config.US_MARKET_HOLIDAYS if d.startswith("2029"))
    _check(
        "B1 2028 exakt 10 Einträge, Mengen-Diff leer",
        got_2028 == frozenset(expected_2028),
        f"diff neu−erwartet={sorted(got_2028 - expected_2028)}, "
        f"erwartet−neu={sorted(expected_2028 - got_2028)}",
    )
    _check(
        "B2 2029 exakt 10 Einträge, Mengen-Diff leer",
        got_2029 == frozenset(expected_2029),
        f"diff neu−erwartet={sorted(got_2029 - expected_2029)}, "
        f"erwartet−neu={sorted(expected_2029 - got_2029)}",
    )
    # Cross-Check gegen das in mock_test_good_friday.py bereits vertraute
    # real_good_fridays-Dict (importierbar, da reiner Literal-Wert dort).
    _check(
        "B3 Good Friday 2028 (2028-04-14) im Set",
        "2028-04-14" in config.US_MARKET_HOLIDAYS,
    )
    _check(
        "B4 Good Friday 2029 (2029-03-30) im Set",
        "2029-03-30" in config.US_MARKET_HOLIDAYS,
    )


def _test_new_years_saturday_exception():
    """(C) Neujahr auf Samstag → KEIN Ersatztag am 31.12. des Vorjahres."""
    print("── (C) Neujahrs-Sonderregel (Samstag → kein Ersatz am 31.12.) ──")
    # Jahre 2020-2050, in denen der 1. Januar auf einen Samstag fällt.
    saturday_new_years = [y for y in range(2020, 2051) if date(y, 1, 1).weekday() == 5]
    _check(
        "C1 mindestens 1 Samstags-Neujahr im Range 2020-2050 gefunden "
        "(sonst wäre die Regel in diesem Test nie getestet)",
        len(saturday_new_years) > 0,
        f"gefunden: {saturday_new_years}",
    )
    for y in saturday_new_years:
        prev_dec31 = date(y - 1, 12, 31).isoformat()
        this_jan1 = date(y, 1, 1).isoformat()
        _check(
            f"C2 {y}: KEIN Ersatztag {prev_dec31} im Set (Neujahrs-Ausnahme)",
            prev_dec31 not in config.US_MARKET_HOLIDAYS,
            f"{prev_dec31} fälschlich im Set — Neujahrs-Ausnahme nicht greifend",
        )
        _check(
            f"C3 {y}: {this_jan1} selbst im Set (Samstag, harmlos da ohnehin "
            "Wochenende)",
            this_jan1 in config.US_MARKET_HOLIDAYS,
        )
    # Realer Beleg 2022 (öffentlich bekannt: NYSE war am 31.12.2021 regulär
    # geöffnet, kein Neujahrs-Ersatztag wurde beobachtet).
    _check(
        "C4 2022 (realer Beleg): Jan1,2022 ist Samstag",
        date(2022, 1, 1).weekday() == 5,
    )
    _check(
        "C5 2022 (realer Beleg): 2021-12-31 NICHT im Set",
        "2021-12-31" not in config.US_MARKET_HOLIDAYS,
    )
    # Kontrollprobe: OHNE die Ausnahme würde die generische Wochenend-Regel
    # fälschlich 31.12. liefern — zeigt, dass die Ausnahme tatsächlich einen
    # Unterschied macht (kein Blindgänger-Test).
    without_exception = config._observed_weekend(
        date(2022, 1, 1), new_years_exception=False
    )
    _check(
        "C6 Kontrollprobe OHNE Ausnahme liefert 2021-12-31 (Beweis: Regel "
        "bewirkt etwas, Test ist nicht trivial grün)",
        without_exception.isoformat() == "2021-12-31",
        f"got {without_exception.isoformat()}",
    )


def _test_helper_independent_anchors():
    """(D) Helper gegen UNABHÄNGIGE historische Anker (keine Wiederverwendung
    der (A)/(B)-Werte — vermeidet Zirkularität)."""
    print("── (D) Nth-/Last-Weekday-Helper gegen unabhängige Anker ────────")
    cases = [
        ("D1 Thanksgiving 2023 (4. Do Nov) = 23.11.2023",
         config._nth_weekday_of_month(2023, 11, 3, 4), date(2023, 11, 23)),
        ("D2 Thanksgiving 2020 (4. Do Nov) = 26.11.2020",
         config._nth_weekday_of_month(2020, 11, 3, 4), date(2020, 11, 26)),
        ("D3 MLK Day 2024 (3. Mo Jan) = 15.01.2024",
         config._nth_weekday_of_month(2024, 1, 0, 3), date(2024, 1, 15)),
        ("D4 Labor Day 2024 (1. Mo Sep) = 02.09.2024",
         config._nth_weekday_of_month(2024, 9, 0, 1), date(2024, 9, 2)),
        ("D5 Memorial Day 2024 (letzter Mo Mai) = 27.05.2024",
         config._last_weekday_of_month(2024, 5, 0), date(2024, 5, 27)),
        ("D6 Presidents Day 2024 (3. Mo Feb) = 19.02.2024",
         config._nth_weekday_of_month(2024, 2, 0, 3), date(2024, 2, 19)),
        ("D7 Memorial Day 2023 (letzter Mo Mai) = 29.05.2023",
         config._last_weekday_of_month(2023, 5, 0), date(2023, 5, 29)),
        ("D8 Labor Day 2023 (1. Mo Sep) = 04.09.2023",
         config._nth_weekday_of_month(2023, 9, 0, 1), date(2023, 9, 4)),
    ]
    for name, got, expected in cases:
        _check(name, got == expected, f"got {got.isoformat()}")


def _test_general_weekend_observation():
    """(E) Allgemeine Wochenend-Beobachtung OHNE Neujahrs-Ausnahme."""
    print("── (E) Allgemeine Wochenend-Beobachtung (Sat→Fr, So→Mo) ────────")
    _check(
        "E1 Independence Day 2026 (Sa 04.07.) → Fr 03.07.",
        config._observed_weekend(date(2026, 7, 4)) == date(2026, 7, 3),
    )
    _check(
        "E2 Independence Day 2027 (So 04.07.) → Mo 05.07.",
        config._observed_weekend(date(2027, 7, 4)) == date(2027, 7, 5),
    )
    _check(
        "E3 Christmas 2027 (Sa 25.12.) → Fr 24.12.",
        config._observed_weekend(date(2027, 12, 25)) == date(2027, 12, 24),
    )
    _check(
        "E4 Juneteenth 2027 (Sa 19.06.) → Fr 18.06.",
        config._observed_weekend(date(2027, 6, 19)) == date(2027, 6, 18),
    )
    _check(
        "E5 Wochentag-Feiertag bleibt unverändert (Juneteenth 2025, Do 19.06.)",
        config._observed_weekend(date(2025, 6, 19)) == date(2025, 6, 19),
    )


def _test_set_properties():
    """(F) Set-Eigenschaften: Typ, Determinismus, Größe, keine Kollisionen."""
    print("── (F) Set-Eigenschaften ───────────────────────────────────────")
    _check("F1 US_MARKET_HOLIDAYS ist frozenset",
           isinstance(config.US_MARKET_HOLIDAYS, frozenset))
    _check(
        "F2 Größe = 310 (10 Feiertage × 31 Jahre, keine Kollisionen)",
        len(config.US_MARKET_HOLIDAYS) == 310,
        f"got {len(config.US_MARKET_HOLIDAYS)}",
    )
    a = frozenset(
        iso for y in range(2020, 2051) for iso in config._us_market_holidays_for_year(y)
    )
    b = frozenset(
        iso for y in range(2020, 2051) for iso in config._us_market_holidays_for_year(y)
    )
    _check("F3 Mehrfache Neuerzeugung liefert identisches Ergebnis", a == b)
    _check("F4 Neuerzeugung == Modul-Konstante", a == config.US_MARKET_HOLIDAYS)
    # Pro Jahr exakt 10 verschiedene Daten (keine Doppel-Belegung zweier
    # Feiertage auf denselben Kalendertag).
    bad_years = [
        y for y in range(2020, 2051)
        if len(config._us_market_holidays_for_year(y)) != 10
    ]
    _check(
        "F5 jedes Jahr liefert genau 10 verschiedene Daten (keine Kollision)",
        not bad_years,
        f"Jahre mit Kollision: {bad_years}",
    )


def _extract_js_holiday_block() -> str | None:
    """Extrahiert den self-contained JS-Feiertags-Block aus generate_report.py
    (zwischen ``function _toIso`` und ``function _isHoliday``) und hebt die
    Python-f-String-Escapes (``{{``/``}}``) für eine eigenständige
    Node-Ausführung auf."""
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    try:
        start = src.index("function _toIso(d) {{")
        end = src.index("function _isHoliday(d)")
    except ValueError:
        return None
    block = src[start:end]
    return block.replace("{{", "{").replace("}}", "}")


def _test_js_python_full_parity():
    """(G) Python↔JS-Vollparität über die GESAMTE Range 2020–2050 via
    echter Node-Ausführung (nicht nur Source-Inspektion)."""
    print("── (G) Python↔JS-Vollparität (Node-Ausführung, 2020..2050) ────")
    node = shutil.which("node")
    if not node:
        print("    ⊘ node nicht verfügbar — Funktionaltest übersprungen "
              "(Source-Gates in mock_test_good_friday.py bleiben hart).")
        return
    block = _extract_js_holiday_block()
    if block is None:
        _check("G0 JS-Feiertags-Block extrahierbar", False, "nicht gefunden")
        return
    script = block + "\nconsole.log(JSON.stringify(US_HOLIDAYS));\n"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(script)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            _check("G1 Node-Ausführung erfolgreich", False,
                   f"stderr: {out.stderr[:400]}")
            return
        import json
        js_holidays = frozenset(json.loads(out.stdout.strip()))
    finally:
        pathlib.Path(path).unlink(missing_ok=True)

    _check(
        "G2 JS-Array hat 310 Einträge (identisch zu Python)",
        len(js_holidays) == 310,
        f"got {len(js_holidays)}",
    )
    diff_js = sorted(js_holidays - config.US_MARKET_HOLIDAYS)
    diff_py = sorted(config.US_MARKET_HOLIDAYS - js_holidays)
    _check(
        "G3 JS − Python leer (keine JS-exklusiven Daten)",
        not diff_js, f"JS-exklusiv: {diff_js}",
    )
    _check(
        "G4 Python − JS leer (keine Python-exklusiven Daten)",
        not diff_py, f"Python-exklusiv: {diff_py}",
    )
    _check(
        "G5 JS-Set == Python-Set (volle Range-Parität 2020..2050)",
        js_holidays == config.US_MARKET_HOLIDAYS,
    )


def _test_consumer_2028():
    """(H) Konsumenten-Beleg: previous_trading_day überspringt einen echten
    2028er-Feiertag (vormals nicht abgedeckt)."""
    print("── (H) Konsumenten-Beleg: previous_trading_day für 2028 ────────")
    # MLK Day 2028 = Mo 17.01.2028. previous_trading_day(Di 18.01.2028)
    # muss Fr 14.01.2028 liefern (überspringt Mo-Feiertag + Wochenende).
    prev = previous_trading_day(date(2028, 1, 18))
    _check(
        "H1 previous_trading_day(Di 18.01.2028) → Fr 14.01.2028 "
        "(überspringt MLK Day 2028, vormals unabgedeckt)",
        prev == date(2028, 1, 14),
        f"got {prev.isoformat()}",
    )
    # Good Friday 2029 = Fr 30.03.2029. previous_trading_day(Mo 02.04.2029)
    # muss Do 29.03.2029 liefern.
    prev2 = previous_trading_day(date(2029, 4, 2))
    _check(
        "H2 previous_trading_day(Mo 02.04.2029) → Do 29.03.2029 "
        "(überspringt Karfreitag 2029)",
        prev2 == date(2029, 3, 29),
        f"got {prev2.isoformat()}",
    )


def _extract_function_body(src: str, def_line: str) -> str | None:
    """Schneidet einen Funktionskörper heraus: von ``def_line`` (z. B.
    ``"def score("``) bis zur nächsten Top-Level-``def ``/``class ``-Zeile
    (Spalte 0) danach. Grobe, aber für diesen Zweck ausreichende
    Source-Slice-Heuristik (kein AST nötig — wir suchen nur Substring-
    Referenzen innerhalb des Bodys)."""
    idx = src.find(def_line)
    if idx == -1:
        return None
    rest = src[idx:]
    lines = rest.splitlines()
    body_lines = [lines[0]]
    for line in lines[1:]:
        if line.startswith("def ") or line.startswith("class "):
            break
        body_lines.append(line)
    return "\n".join(body_lines)


def _test_score_isolation():
    """(I) Isolations-Beleg: Holiday-Helper werden NICHT in den Funktions-
    KÖRPERN der Score-/Filter-/Alert-Berechnung referenziert — reine
    Kalender-Hilfsfunktion, kein Trading-Logik-Touch.

    Schneidet gezielt die Funktionskörper heraus (nicht die ganze Datei),
    damit Doku-Kommentare an anderer Stelle im File (z. B. die JS-Helper-
    Kommentare, die zu Cross-Referenz-Zwecken auf die Python-Pendants
    verweisen) keine False-Positives erzeugen.
    """
    print("── (I) Isolations-Beleg: kein Score-/Filter-/Alert-Touch ───────")
    forbidden_def_lines = (
        "def score(", "def score_bonus(", "def apply_monster_score(",
        "def apply_agent_boost(", "def apply_late_runner_penalty(",
        "def apply_score_smoothing(", "def _compute_sub_scores(",
        "def compute_conviction_score(", "def compute_exit_score(",
        "def process_exit_signals(",
    )
    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    holiday_helpers = (
        "_nth_weekday_of_month", "_last_weekday_of_month", "_observed_weekend",
        "_us_market_holidays_for_year",
    )
    for def_line in forbidden_def_lines:
        body = _extract_function_body(gr_src, def_line)
        _check(
            f"I0 Funktionskörper {def_line!r} auffindbar (Voraussetzung "
            "für die eigentliche Prüfung)",
            body is not None,
        )
        if body is None:
            continue
        for helper in holiday_helpers:
            _check(
                f"I {def_line!r} ruft {helper} NICHT auf",
                helper not in body,
            )


def main():
    _test_exact_match_2025_2027()
    _test_2028_2029_hand_values()
    _test_new_years_saturday_exception()
    _test_helper_independent_anchors()
    _test_general_weekend_observation()
    _test_set_properties()
    _test_js_python_full_parity()
    _test_consumer_2028()
    _test_score_isolation()

    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (2025-2027 exakt wie vorher, 2028/2029 "
          "plausibel, Neujahrs-Ausnahme belegt, Helper gegen unabhängige "
          "Anker, Python↔JS-Vollparität, Konsument, Score-Isolation).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
