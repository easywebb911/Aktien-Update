"""Mock-Tests für ``scripts/business_days.finra_publication_date``.

FIXTURE-ONLY — kein Kontakt mit Live-Dateien, kein FINRA-Fetch. Verifiziert
die Business-Day-Vorwärts-Arithmetik gegen manuell nachvollziehbare Fälle
inkl. Good-Friday-Übersprung (der Kern-Nutzen von PR #407).

HINTERGRUND:
- FINRA Rule 4560: SI-Reports sind ~7 Handelstage nach Settlement öffentlich.
- Basis für ``si_velocity_pub``-Look-Ahead-Filter (PR-3): Report darf einem
  Backtest-Record nur zugeordnet werden wenn ``pub_date <= entry_date``.
- Karfreitag muss im ``US_MARKET_HOLIDAYS``-Set sein — sonst rechnet der
  Zähler an Karfreitags-Nähe 1 Business-Day zu früh (Look-Ahead in die
  falsche Richtung). PR #407 hat das mit Meeus-Osterformel gefixt; dieser
  Test verriegelt den Nutzen.

Verifiziert:
- (A) Formel gegen 4 manuell nachvollziehbare Fälle inkl. Good Friday +
      Memorial Day + Independence Day (observed).
- (B) Kern-Nutzen von PR #407: Settlement 26.03.2026 mit Karfreitag im
      Fenster liefert 07.04. (mit Fix); ohne Fix wäre 06.04. — die
      1-Business-Day-Look-Ahead-Falle.
- (C) ``next_trading_day``-Kernfunktion: Wochenend-/Feiertags-Übersprung.
- (D) Offset-Konstante zentral gekapselt (ein Ort ändern → überall wirksam).
- (E) Offset-Override akzeptiert (Test-Injection ohne Konstanten-Touch).
- (F) Randfälle: ``offset=0`` → Settlement selbst (kein-Handelstag-Guard!);
      negative offsets → ValueError.
- (G) Determinismus: mehrfacher Aufruf → identischer Wert.
- (H) Look-Ahead-Konvention im Docstring einfroren (Grep-Beleg).
- (I) Score-/Push-Konsumenten-Isolation: der Helper wird NIRGENDS in
      Score/Filter/Push-Pfaden gelesen (rein Analyse-/Persistenz-Vorbau).
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
from business_days import (  # noqa: E402
    finra_publication_date,
    next_trading_day,
)


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def _test_publication_date_manual_cases():
    """(A) Vier manuell nachvollziehbare Rechnungen gegen echten NYSE-Kalender.

    Rechnungen SIND transparent im Test-Body dokumentiert, damit jeder
    Reviewer sie ohne Kalender-App validieren kann.
    """
    print("── (A) Publikations-Datum manuell verifiziert ────────────────")

    # A1: Settlement Do 26.03.2026 mit Karfreitag im Fenster.
    #   Do 26.03. (Start, zählt nicht) → +1 Fr 27.03 → +2 Mo 30.03
    #   → +3 Di 31.03 → +4 Mi 01.04 → +5 Do 02.04
    #   → SKIP Fr 03.04 = Good Friday (im Set dank #407!)
    #   → +6 Mo 06.04 → +7 Di 07.04 → pub_date
    _check(
        "A1 Settlement 26.03.2026 (Good Friday im +7-Fenster) → 07.04.2026",
        finra_publication_date(date(2026, 3, 26)) == date(2026, 4, 7),
        f"got {finra_publication_date(date(2026, 3, 26)).isoformat()}",
    )

    # A2: Settlement Fr 15.05.2026 mit Memorial Day im Fenster.
    #   Fr 15.05. → +1 Mo 18.05 → +2 Di 19.05 → +3 Mi 20.05 → +4 Do 21.05
    #   → +5 Fr 22.05 → SKIP Mo 25.05 = Memorial Day → +6 Di 26.05
    #   → +7 Mi 27.05 → pub_date
    _check(
        "A2 Settlement 15.05.2026 (Memorial Day im +7-Fenster) → 27.05.2026",
        finra_publication_date(date(2026, 5, 15)) == date(2026, 5, 27),
        f"got {finra_publication_date(date(2026, 5, 15)).isoformat()}",
    )

    # A3: Settlement Di 30.06.2026 mit Independence Day (observed) im Fenster.
    #   Di 30.06. → +1 Mi 01.07 → +2 Do 02.07
    #   → SKIP Fr 03.07 = Independence Day (observed, im Set)
    #   → +3 Mo 06.07 → +4 Di 07.07 → +5 Mi 08.07 → +6 Do 09.07
    #   → +7 Fr 10.07 → pub_date
    _check(
        "A3 Settlement 30.06.2026 (Independence Day 03.07. im +7-Fenster) "
        "→ 10.07.2026",
        finra_publication_date(date(2026, 6, 30)) == date(2026, 7, 10),
        f"got {finra_publication_date(date(2026, 6, 30)).isoformat()}",
    )

    # A4: Kontrolle — sauberes Fenster ohne Feiertag.
    #   Di 15.09.2026 → +1 Mi 16.09 → +2 Do 17.09 → +3 Fr 18.09
    #   → +4 Mo 21.09 → +5 Di 22.09 → +6 Mi 23.09 → +7 Do 24.09 → pub_date
    _check(
        "A4 Settlement 15.09.2026 (kein Feiertag, Kontrolle) → 24.09.2026",
        finra_publication_date(date(2026, 9, 15)) == date(2026, 9, 24),
        f"got {finra_publication_date(date(2026, 9, 15)).isoformat()}",
    )


def _test_good_friday_kern_nutzen():
    """(B) Kern-Nutzen von PR #407: verriegelt, dass Karfreitag im
    ``US_MARKET_HOLIDAYS``-Set die pub_date-Berechnung korrekt macht.

    Wenn Karfreitag 03.04.2026 NICHT im Set wäre, würde der Zähler an
    Fr 03.04 als Business-Day mitzählen und pub_date fälschlich am
    Mo 06.04. landen (1 Business-Day zu früh) → Look-Ahead in die
    falsche Richtung. Dieser Test schützt den #407-Fix.
    """
    print("── (B) PR #407 Kern-Nutzen: Karfreitag korrekt übersprungen ──")

    _check(
        "B1 Karfreitag 2026-04-03 im US_MARKET_HOLIDAYS-Set (Vorbedingung)",
        "2026-04-03" in config.US_MARKET_HOLIDAYS,
        "PR #407 rückgängig? Kern-Nutzen wäre gebrochen",
    )
    # Wenn A1 grün ist, ist der Fix auch grün — aber ein expliziter
    # Landmark-Test macht den Zusammenhang lesbar:
    _check(
        "B2 Settlement 26.03.2026 pub_date=07.04.2026 (statt fälschlich "
        "06.04. ohne #407)",
        finra_publication_date(date(2026, 3, 26)) == date(2026, 4, 7),
    )


def _test_next_trading_day_core():
    """(C) ``next_trading_day``-Kernfunktion: Wochenend-/Feiertag-Übersprung."""
    print("── (C) next_trading_day Basis-Fälle ──────────────────────────")

    # Do → Fr (kein Wochenende)
    _check("C1 next_trading_day(Do 21.05.2026) → Fr 22.05.2026",
           next_trading_day(date(2026, 5, 21)) == date(2026, 5, 22))
    # Fr → Mo (Wochenende übersprungen)
    _check("C2 next_trading_day(Fr 22.05.2026) → Di 26.05.2026 "
           "(WE + Memorial Day 25.05.)",
           next_trading_day(date(2026, 5, 22)) == date(2026, 5, 26))
    # Do vor Karfreitag → Mo (Karfreitag + Wochenende übersprungen)
    _check("C3 next_trading_day(Do 02.04.2026) → Mo 06.04.2026 "
           "(Karfreitag + WE)",
           next_trading_day(date(2026, 4, 2)) == date(2026, 4, 6))
    # Wochenende als Input erlaubt
    _check("C4 next_trading_day(Sa 04.04.2026) → Mo 06.04.2026 "
           "(Input ist WE, Karfreitag übersprungen)",
           next_trading_day(date(2026, 4, 4)) == date(2026, 4, 6))
    # Feiertag als Input erlaubt
    _check("C5 next_trading_day(Karfreitag 03.04.2026) → Mo 06.04.2026 "
           "(Input selbst ist Feiertag)",
           next_trading_day(date(2026, 4, 3)) == date(2026, 4, 6))


def _test_offset_constant():
    """(D) Offset-Konstante zentral gekapselt in config."""
    print("── (D) FINRA_PUB_OFFSET_BUSINESS_DAYS zentral gekapselt ──────")

    _check("D1 Konstante FINRA_PUB_OFFSET_BUSINESS_DAYS existiert",
           hasattr(config, "FINRA_PUB_OFFSET_BUSINESS_DAYS"))
    _check("D2 Default-Wert = 7 (FINRA Rule 4560)",
           config.FINRA_PUB_OFFSET_BUSINESS_DAYS == 7)
    _check("D3 Ist Integer",
           isinstance(config.FINRA_PUB_OFFSET_BUSINESS_DAYS, int))


def _test_offset_override():
    """(E) Offset-Injection für Tests (ohne Konstanten-Touch)."""
    print("── (E) Offset-Override akzeptiert ────────────────────────────")

    # Settlement Di 15.09.2026, offset=1 → +1 Mi 16.09
    _check("E1 offset=1 (Settlement + 1 Handelstag)",
           finra_publication_date(date(2026, 9, 15), offset=1)
           == date(2026, 9, 16))
    # offset=3 → +3 Fr 18.09
    _check("E2 offset=3 (Settlement + 3 Handelstage)",
           finra_publication_date(date(2026, 9, 15), offset=3)
           == date(2026, 9, 18))


def _test_edge_cases():
    """(F) Randfälle."""
    print("── (F) Randfälle ─────────────────────────────────────────────")

    # offset=0 → next_trading_day-Aufruf wird gar nicht gemacht → Settlement selbst
    # ACHTUNG: Settlement kann selbst ein Nicht-Handelstag sein — diese Konvention
    # gibt das Settlement zurück, ohne Handelstag-Guard. Für die reale Anwendung
    # (SI-Report-Settlements sind IMMER Handelstage per FINRA-Konvention) egal.
    _check("F1 offset=0 → Settlement selbst zurückgegeben",
           finra_publication_date(date(2026, 9, 15), offset=0)
           == date(2026, 9, 15))
    # Negativer Offset → ValueError
    try:
        finra_publication_date(date(2026, 9, 15), offset=-1)
        _check("F2 offset=-1 → ValueError", False, "kein Fehler geworfen")
    except ValueError:
        _check("F2 offset=-1 → ValueError", True)


def _test_determinism():
    """(G) Determinismus."""
    print("── (G) Determinismus ─────────────────────────────────────────")

    a = finra_publication_date(date(2026, 3, 26))
    b = finra_publication_date(date(2026, 3, 26))
    c = finra_publication_date(date(2026, 3, 26))
    _check("G1 finra_publication_date 3× → identisch", a == b == c)


def _test_look_ahead_convention_frozen():
    """(H) Look-Ahead-Konvention im Docstring einfroren."""
    print("── (H) Look-Ahead-Konvention einfroren ───────────────────────")

    src = (ROOT / "scripts" / "business_days.py").read_text(encoding="utf-8")
    _check(
        "H1 Look-Ahead-Konvention im Modul-Docstring",
        "LOOK-AHEAD-KONVENTION" in src,
    )
    _check(
        "H2 Erklärung 'pub_date <= entry_date' im Docstring",
        "pub_date" in src and "entry_date" in src,
    )
    # Test-Text ist im Docstring über 2 Zeilen umbrochen ("lieber zu\n
    # spät zuordnen als zu früh") — normalize whitespace vor dem Grep.
    src_normalized = " ".join(src.split())
    _check(
        "H3 Konservativ-Regel 'lieber zu spät zuordnen als zu früh' explizit",
        "lieber zu spät zuordnen als zu früh" in src_normalized,
    )


def _test_consumer_isolation():
    """(I) Der Helper wird NIRGENDS im Score/Filter/Push-Pfad gelesen.

    Reine Analyse-/Persistenz-Vorbau. Score-Read würde Look-Ahead-Konvention
    verletzen (rückwirkbar backgefüllte Records würden ins Score-Compute
    fließen).
    """
    print("── (I) Konsumenten-Isolation Score/Filter/Push ───────────────")

    forbidden_read_patterns = [
        "finra_publication_date(",
        "from scripts.business_days import",
        "from business_days import",
    ]

    for path_rel, tag in (
        ("ki_agent.py",     "KI-Agent-/Push-Pfad"),
        ("health_check.py", "Health-Check-Pfad"),
        ("backtest_history.py", "Backtest-Persistenz-Pfad"),
    ):
        src = (ROOT / path_rel).read_text(encoding="utf-8")
        for pat in forbidden_read_patterns:
            _check(
                f"I-{path_rel}: kein Import/Read von '{pat}'",
                pat not in src,
                f"{tag} — Look-Ahead-Bruch: pub_date wird in Score-Pfad gelesen",
            )

    # generate_report.py DARF finra_publication_date aufrufen — aber NUR in
    # Persistenz-/Live-Enrichment-Pfaden, NIEMALS in Score-/Filter-/Push-Logik.
    # Zwei erlaubte Call-Sites (beide Look-Ahead-safe, reine Datierung):
    #   1. get_finra_short_interest (Live-Enrichment der FINRA-history-Entries)
    #   2. _si_pub_date (SI-Positions-Zeitreihe si_position_history.json,
    #      forward-only Persistenz — kein Score-Read; separat verriegelt durch
    #      mock_test_si_position_history.py Look-Ahead-Grep).
    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    n_uses = gr_src.count("finra_publication_date(")
    _check(
        "I-gr n_uses == 2 (get_finra_short_interest + _si_pub_date, beide Persistenz)",
        n_uses == 2,
        f"got {n_uses} — neue Call-Site? Prüfen ob Persistenz (ok) oder Score-Read (Bruch)",
    )
    # Positiv-Absicherung: beide erlaubten Call-Sites müssen im Score-freien
    # Kontext liegen — kein Aufruf innerhalb score()/_compute_sub_scores/score_bonus.
    for score_fn in ("def score(", "def _compute_sub_scores(", "def score_bonus("):
        idx = gr_src.find(score_fn)
        if idx < 0:
            continue
        body = gr_src[idx: idx + 8000]
        _check(
            f"I-gr: {score_fn.strip()} ruft finra_publication_date NICHT auf",
            "finra_publication_date(" not in body,
            "Look-Ahead-Bruch: Score-Funktion datiert SI/pub_date selbst",
        )


def main():
    _test_publication_date_manual_cases()
    _test_good_friday_kern_nutzen()
    _test_next_trading_day_core()
    _test_offset_constant()
    _test_offset_override()
    _test_edge_cases()
    _test_determinism()
    _test_look_ahead_convention_frozen()
    _test_consumer_isolation()

    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (Formel-Verifikation + PR#407-Kern-Nutzen + "
          "next_trading_day + Offset-Kapselung + Override + Randfälle + "
          "Determinismus + Look-Ahead-Konvention + Konsumenten-Isolation).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
