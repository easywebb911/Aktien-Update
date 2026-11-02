"""Lint: ``X.get("feld") or 0``/``0.0`` bei bekannten NaN-fähigen Markt-Feldern.

Hintergrund: das Bug-Muster ``.get(...) or 0`` wurde bereits mehrfach
unabhängig gefunden und gefixt (u. a. PR #533/#534, #557, #558) — ``or 0``
lässt ein numerisches NaN unbemerkt durch (NaN ist in Python truthy),
während ``None``/ein fehlender Key korrekt auf ``0`` fällt. Eine Diagnose
(21.–22.09.2026) hat das Muster systematisch kartiert und in Gruppe A
(riskant) / Gruppe B (legitim, z. B. Zähler/Flags) eingeteilt — dieser
Linter automatisiert genau die Gruppe-A-Erkennung, KEIN blindes
Pattern-Grep (das FP-Risiko über die gesamte Codebasis wäre zu hoch,
siehe Gruppe B in der Diagnose).

ZWEISTUFIGER AUFBAU (kalibriert, nicht neu erfunden):

1. FELDNAMEN-ALLOWLIST (``_ALLOWLIST_FIELDS`` unten) — nur ``.get("...")``-
   Aufrufe mit einem Schlüssel aus dieser kuratierten Liste werden
   überhaupt betrachtet. Alles andere (Zähler, Flags, IDs, ...) ist von
   vornherein außerhalb des Scans.

2. SICHERHEITS-GEGENPROBE — auch ein Allowlist-Treffer wird NICHT
   geflaggt, wenn:
   (a) der ``.get(...)``-Aufruf NICHT der unmittelbare linke Operand des
       ``or`` ist, sondern durch einen Funktionsaufruf gewrappt ist
       (``irgendeine_funktion(x.get("feld")) or 0``) — jede Wrapper-
       Funktion zwischen ``.get()`` und ``or`` gilt als Schutz-Versuch.
       VEREINFACHUNG ggü. der ursprünglichen Diagnose-Vorgabe („nur wenn
       es NACHWEISLICH die echte generate_report._safe_float ist"):
       eine statische, importpfad-genaue Unterscheidung zwischen der
       echten und einer lokalen Reimplementierung wäre nur mit vollem
       Cross-Modul-Import-Auflösen möglich — genau der Aufwand, den die
       Aufgabenstellung als Mini-Stopp-Fall vorgesehen hat (Punkt 6:
       „ggf. diese Sicherheitsregel vorerst weglassen"). Diese gröbere
       Variante deckt den mechanisch relevanten Teil ab (rohes ``.get()``
       direkt vor ``or 0``) und lässt der Diagnose/dem Review die
       inhaltliche Prüfung, OB ein Wrapper tatsächlich sicher ist (siehe
       PR #558, wo genau so ein Wrapper selbst unsicher war und separat
       gefixt wurde — dieser Lint hätte diesen Fall NICHT gefangen, weil
       ``_safe_float(...)`` ihn bereits als „gewrappt" einordnet; das ist
       eine bewusst akzeptierte Lücke, siehe PR-Text).
   (b) direkt ein ``int(...)``-Cast um den gesamten ``X.get(...) or 0``-
       Ausdruck liegt — ``int(nan)`` wirft zuverlässig ``ValueError``,
       das umgebende try/except fängt es.
   (c) der Fundort in der manuell gepflegten ``_EXCEPTIONS``-Liste steht
       (analog ``EXCLUDED`` in ``scripts/run_ci_mock_tests.py``) — für
       Fälle, in denen der KONSUMENT der Zeile bereits nachweislich
       NaN-gehärtet ist (z. B. ``_compute_rvol_buildup_5d`` prüft
       ``avg_vol_20d`` selbst via ``_finite()``), was sich NICHT generisch
       per AST erkennen lässt und deshalb manuell einzutragen ist.

SCOPE: der Lint prüft nur NEUE Treffer gegen die kuratierte Feldliste in
den unten gelisteten ``_SCAN_FILES`` — er ist kein rückwirkender Voll-Scan
des Repos (das wäre ein zu großer Erstlauf-Aufwand, siehe Diagnose).

BASELINE (Easy-Entscheid 22.09.2026, nach dem ersten echten Lint-Lauf):
der erste Lauf gegen die reale Codebasis fand 70 Treffer statt der in der
Diagnose erwarteten ~4 — die meisten davon sind GENUINE, noch offene
Gruppe-A-Bugs (z. B. ``risk_assessment()``, ``short_situation()``,
``_build_card_ctx()``, ``compute_exit_score()``-Eingang), nicht
„Konsument-bereits-sicher"-Fälle. Ein Lint, der ab Einführung dauerhaft
rot ist, widerspricht dem Repo-Grundsatz „Signal statt Rauschen"
(Alarm-Müdigkeit) — deshalb wurden alle 70 als Momentaufnahme in
``_BASELINE_KNOWN_OPEN`` eingetragen (seit 02.11.2026 inhaltsbasiert:
Datei+Funktion+Feld+Zeilentext statt Zeilennummer, bewusst
GETRENNT von ``_EXCEPTIONS`` — Baseline heißt NICHT „geprüft und sicher",
sondern „bekannt offen, noch nicht gefixt"). Der Lint ist dadurch bei
Einführung grün, fängt aber jede NEUE Instanz (andere Datei/Zeile/Feld)
sofort (Multiset: ein Eintrag deckt genau ein Vorkommen). Jede Baseline-Zeile ist ein offener Fix-Kandidat für einen
eigenen Folge-PR — beim Fixen den Eintrag entfernen, nicht stehen lassen.
Seit #636 erzwungen: ein Baseline-Eintrag ohne passenden Fund
(stale) macht den Lint ebenfalls rot — die Baseline darf nur schrumpfen.

Exit-Code 0 = OK, 1 = Fail. Bei Fail werden Datei, Funktion, Zeile und
Feldname geloggt.

Workflow-Integration: NUR ``.github/workflows/pr-checks.yml`` (advisory,
PR-Checks) — bewusst ABWEICHEND vom Muster der 4 bestehenden Linter
(die von Anfang an in BEIDEN Workflows liefen). Dieser Lint ist neu
gebaut und erst gegen einen Snapshot des Codes gelaufen; ein Fehlalarm
soll nicht den produktiven Daily-Run stoppen (dort bricht ein Lint-Fail
den Workflow ab, siehe ``.github/workflows/daily-squeeze-report.yml``).
TODO (Folge-Entscheidung): nach ein paar echten PR-Zyklen ohne False
Positives auch dort ergänzen (Guardian-Review 22.09.2026, Finding 1 —
dieser Docstring behauptete vorher fälschlich bereits die Dual-
Verdrahtung; korrigiert).
"""
from __future__ import annotations

import ast
import collections
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Dateien, die auf das Muster gescannt werden. Bewusst eine explizite
# Liste (kein glob über das ganze Repo) — Skripte/Tools/Tests sind nicht
# der produktionsrelevante Lese-Pfad für Live-Marktdaten.
_SCAN_FILES = (
    "generate_report.py",
    "ki_agent.py",
    "backtest_history.py",
    "backtest_bootstrap.py",
    "alert.py",
    "score_inflation_log.py",
    "health_check.py",
)

# Gruppe-A-Feldnamen (Diagnose 21.–22.09.2026): numerische Marktwerte, die
# NaN werden können (yfinance-Datenlücke, kaputte Zelle) UND in Score-/
# Filter-/Preis-/Renditeberechnung oder Kartenanzeige einfließen.
_ALLOWLIST_FIELDS = frozenset({
    # Display-/Pipeline-Felder (snake_case)
    "short_float", "short_ratio", "rel_volume", "rsi14",
    "change", "change_2d", "change_3d", "change_5d",
    "price", "market_cap", "yf_market_cap", "float_shares",
    "avg_vol_20d", "52w_high", "52w_low", "score", "setup_today",
    "entry_price", "rvol_4d", "short_interest", "premarket_volume",
    # Ergänzt ggü. der Diagnose-Startliste (Cross-Check 22.09.2026 gegen
    # echte Dict-Keys in generate_report.py/ki_agent.py) — gleiche
    # Risikoklasse, in der Startliste schlicht nicht genannt:
    "atm_iv", "cost_to_borrow", "entry_dtc", "vix_current",
    # Rohe yfinance .info/.fast_info-Felder (camelCase) — Cross-Check fand
    # dieselbe "or 0"-Gefahr unter anderer Namenskonvention in alert.py /
    # backtest_bootstrap.py / generate_report.py. Namensbasierte Erkennung
    # statt Attribut-Ketten-Tracking (".info.get(...)"), weil das Objekt
    # meist über eine lokale Zwischenvariable läuft (``info = stk.info``)
    # — ein struktureller Attribut-Check würde das nicht zuverlässig sehen,
    # der Feldname selbst ist aber eindeutig yfinance-Rohformat.
    "regularMarketPrice", "regularMarketChangePercent",
    "shortPercentOfFloat", "shortRatio", "floatShares", "marketCap",
    "lastPrice", "last_price",
})

# ── (2c) Manuelle Ausnahmeliste ─────────────────────────────────────────
# (Datei, umschließende Funktion, Feldname) — NUR Fälle, bei denen der
# KONSUMENT der Zeile nachweislich bereits NaN-gehärtet ist (nicht die
# Zeile selbst). Jeder Eintrag braucht einen Kommentar mit Beleg.
_EXCEPTIONS: frozenset[tuple[str, str, str]] = frozenset({
    # avg_vol_20d fließt hier NUR in _compute_rvol_buildup_5d(volumes_5d,
    # avg_vol_20d) — dessen eigener Guard ist bereits `not _finite(avg_vol_20d)`
    # (15.08.2026-Härtung, siehe backtest_history.py-Docstring dort).
    # Ein NaN würde also im Konsumenten sauber zu None, nicht durchrutschen.
    ("backtest_history.py", "_build_backtest_extension", "avg_vol_20d"),
})

# ── Baseline: bekannt offene Alt-Funde (inhaltsbasiert seit 02.11.2026) ─
# NICHT zu verwechseln mit _EXCEPTIONS oben (dort: nachweislich sicher).
# Diese Liste sind GENUINE, noch OFFENE Fundstellen -- seit 02.11.2026 genau
# die geparkte "Gruppe 1" (Score-/Freeze-/Push-/Exit-Pfad, open_items
# nan-bypass-baseline-70, Wiedervorlage 03.12.2026). Sie decken einen Fund
# nur, solange er unverändert an seiner Stelle steht -- NICHT "geprüft und
# sicher".
#
# SCHLÜSSEL (Easy-Entscheid 02.11.2026, open_items
# nan-lint-baseline-zeilennummern-fragil): (Datei, umgebende Funktion, Feld,
# normalisierter Zeilentext) statt (Datei, Zeile, Feld). Grund: der alte
# Zeilen-Schlüssel riss bei JEDER Einfügung oberhalb einer Fundstelle
# (#565, hist_5d-Folge-PR, #623, #630, #633, #635) und musste von Hand per
# Diff-Abbildung nachgezogen werden. Normalisierung = Whitespace auf ein
# Leerzeichen zusammengezogen, Ränder abgeschnitten (_norm_snippet).
#   - Verschiebt sich der Code (Leerzeilen, neue Funktionen darüber):
#     Lint bleibt grün.
#   - Wird die Fund-ZEILE selbst geändert (Refactor, anderer Ausdruck) oder
#     wandert sie in eine andere Funktion: Fund wird wieder SICHTBAR (gewollt).
#   - MULTISET: ein Eintrag deckt genau EIN Vorkommen. Steht dieselbe Zeile
#     (gleiche Funktion/Feld/Text) zweimal in der Baseline, sind genau zwei
#     Vorkommen gedeckt; eine dritte, neu kopierte identische Zeile wird
#     trotzdem gemeldet.
# ABBAU-PFAD: beim Fix den Eintrag HIER entfernen -- die Liste darf nur
# schrumpfen.
_BASELINE_KNOWN_OPEN: tuple[tuple[str, str, str, str], ...] = (
    ("alert.py", "fetch_live", "regularMarketChangePercent",
     "chg_pct = float(info.get(\"regularMarketChangePercent\") or 0.0)"),
    ("alert.py", "fetch_live", "shortPercentOfFloat",
     "sf = float(info.get(\"shortPercentOfFloat\") or 0.0) * 100"),
    ("alert.py", "fetch_live", "shortRatio",
     "sr = float(info.get(\"shortRatio\") or 0.0)"),
    ("alert.py", "fetch_screener_candidates", "regularMarketChangePercent",
     "\"change_pct\": float(q.get(\"regularMarketChangePercent\") or 0.0),"),
    ("alert.py", "fetch_screener_candidates", "regularMarketPrice",
     "\"price\": float(q.get(\"regularMarketPrice\") or 0.0),"),
    ("alert.py", "fetch_screener_candidates", "shortPercentOfFloat",
     "sf = float(q.get(\"shortPercentOfFloat\") or 0.0)"),
    ("alert.py", "fetch_screener_candidates", "shortRatio",
     "\"short_ratio\": float(q.get(\"shortRatio\") or 0.0),"),
    ("backtest_bootstrap.py", "_process_ticker", "shortRatio",
     "dtc_est = float(info.get(\"shortRatio\") or 0.0)"),
    ("generate_report.py", "_add_quotes", "regularMarketChangePercent",
     "\"change\": float(q.get(\"regularMarketChangePercent\") or 0),"),
    ("generate_report.py", "_add_quotes", "shortPercentOfFloat",
     "sf_raw = float(q.get(\"shortPercentOfFloat\") or 0)"),
    ("generate_report.py", "_add_quotes", "shortRatio",
     "\"short_ratio\": float(q.get(\"shortRatio\") or 0),"),
    ("generate_report.py", "_compute_exit_state", "score",
     "weighted += float(t.get(\"score\") or 0) * weights[k]"),
    ("generate_report.py", "_compute_sub_scores", "float_shares",
     "fl = s.get(\"float_shares\") or 0"),
    ("generate_report.py", "_float_turnover_pts", "float_shares",
     "fl = stock.get(\"float_shares\") or 0"),
    ("generate_report.py", "apply_late_runner_penalty", "rsi14",
     "rsi14 = _safe_float(s.get(\"rsi14\") or 0)"),
    ("generate_report.py", "apply_late_runner_penalty", "score",
     "before = _safe_float(s.get(\"score\") or 0)"),
    ("generate_report.py", "compute_exit_score", "entry_price",
     "entry_price = float(position.get(\"entry_price\") or 0.0)"),
    ("generate_report.py", "compute_exit_score", "price",
     "cur_price = float(current_data.get(\"price\") or 0.0)"),
    ("generate_report.py", "compute_exit_score", "setup_today",
     "setup_today = float(current_data.get(\"setup_today\") or 0.0)"),
    ("generate_report.py", "get_yfinance_batch", "floatShares",
     "\"float_shares\": info.get(\"floatShares\") or 0,"),
    ("generate_report.py", "get_yfinance_batch", "shortPercentOfFloat",
     "\"short_float_yf\": (info.get(\"shortPercentOfFloat\") or 0.0) * 100,"),
    ("generate_report.py", "get_yfinance_batch", "shortRatio",
     "\"short_ratio\": info.get(\"shortRatio\") or 0.0,"),
    ("generate_report.py", "get_yfinance_data", "floatShares",
     "\"float_shares\": info.get(\"floatShares\") or 0,"),
    ("generate_report.py", "get_yfinance_data", "shortPercentOfFloat",
     "\"short_float_yf\": (info.get(\"shortPercentOfFloat\") or 0.0) * 100,"),
    ("generate_report.py", "get_yfinance_data", "shortRatio",
     "\"short_ratio\": info.get(\"shortRatio\") or 0.0,"),
    ("generate_report.py", "main", "score",
     "candidates.sort(key=lambda x: x.get(\"score\") or 0, reverse=True)"),
    ("generate_report.py", "main", "score",
     "enriched.sort(key=lambda x: x.get(\"score\") or 0, reverse=True)"),
    ("generate_report.py", "main", "score",
     "top10.sort(key=lambda x: x.get(\"score\") or 0, reverse=True)"),
    ("generate_report.py", "main", "score",
     "top10.sort(key=lambda x: x.get(\"score\") or 0, reverse=True)"),
    ("generate_report.py", "score", "float_shares",
     "_float = stock.get(\"float_shares\") or 0"),
    ("health_check.py", "evaluate_data_maturity_gate", "score",
     "ge70 = [e for e in v4 if (e.get(\"score\") or 0) >= 70]"),
    ("ki_agent.py", "_process_ticker", "rvol_4d",
     "prev_rvol_4d=float(old_sigs.get(ticker, {}).get(\"rvol_4d\", 0) or 0),"),
    ("ki_agent.py", "detect_anomalies", "rvol_4d",
     "rvol_prev_4d = float((prev_signal or {}).get(\"rvol_4d\") or 0.0)"),
    ("ki_agent.py", "detect_anomalies", "rvol_4d",
     "rvol_today_4d = float(signal.get(\"rvol_4d\") or 0.0)"),
    ("ki_agent.py", "detect_anomalies", "score",
     "ki_score = signal.get(\"score\") or 0"),
    ("ki_agent.py", "fetch_uoa_signal", "last_price",
     "spot = float(getattr(tk, \"fast_info\", {}).get(\"last_price\") or 0.0)"),
)


def _norm_snippet(text: str) -> str:
    """Zeilentext für den Baseline-Schlüssel: Whitespace zusammengezogen,
    Ränder abgeschnitten (Einrückungs-/Leerzeichen-Änderungen sollen den
    Schlüssel nicht brechen, jede inhaltliche Änderung schon)."""
    return " ".join((text or "").split())


class _RiskyOrVisitor(ast.NodeVisitor):
    """Sammelt (lineno, func_name, field, code_snippet) für jeden riskanten
    ``X.get("feld_in_allowlist") or 0``-Fund, der NICHT durch (a)/(b)
    ausgeschlossen ist."""

    def __init__(self, src_lines: list[str]) -> None:
        self.src_lines = src_lines
        self.func_stack: list[str] = ["<module>"]
        self.parent_stack: list[ast.AST] = []
        self.findings: list[tuple[int, str, str, str]] = []

    def _current_func(self) -> str:
        return self.func_stack[-1]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.func_stack.append(node.name)
        self.generic_visit(node)
        self.func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def _is_bare_get_call(self, node: ast.AST) -> str | None:
        """Wenn ``node`` ein unmittelbarer ``X.get("feld")``-Aufruf ist
        (keine Wrapper-Funktion drumherum), liefert den Feld-String,
        sonst None."""
        if not isinstance(node, ast.Call):
            return None
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "get"):
            return None
        if not node.args:
            return None
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        return None

    @staticmethod
    def _is_zero_constant(node: ast.AST) -> bool:
        return (isinstance(node, ast.Constant)
                and isinstance(node.value, (int, float))
                and not isinstance(node.value, bool)
                and node.value == 0)

    def _parent_is_int_cast(self) -> bool:
        """(2b) — ist der unmittelbare Elternknoten des aktuell besuchten
        BoolOp ein ``int(...)``-Call?"""
        if not self.parent_stack:
            return False
        parent = self.parent_stack[-1]
        return (isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Name)
                and parent.func.id == "int")

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if isinstance(node.op, ast.Or):
            for i in range(len(node.values) - 1):
                left, right = node.values[i], node.values[i + 1]
                field = self._is_bare_get_call(left)
                if (field is not None
                        and field in _ALLOWLIST_FIELDS
                        and self._is_zero_constant(right)
                        and not self._parent_is_int_cast()):
                    lineno = getattr(left, "lineno", node.lineno)
                    snippet = (self.src_lines[lineno - 1].strip()
                              if 0 < lineno <= len(self.src_lines) else "")
                    self.findings.append(
                        (lineno, self._current_func(), field, snippet))
        # KEIN eigener Push/Pop hier — generic_visit() (unten überschrieben)
        # pusht `node` selbst, bevor es in dessen Kinder absteigt. Würde
        # visit_BoolOp zusätzlich pushen, stünde `node` doppelt auf dem
        # Stack. self.parent_stack[-1] muss beim EINTRITT in diese Methode
        # (oben, vor diesem Aufruf) der ECHTE Elternknoten von `node` sein
        # — das gilt nur, wenn hier NICHT vorher gepusht wird.
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        # Eltern-Tracking auch für Nicht-BoolOp-Knoten, damit (2b) den
        # UNMITTELBAREN Elternknoten sieht (z. B. Call(int, [BoolOp])).
        self.parent_stack.append(node)
        super().generic_visit(node)
        self.parent_stack.pop()


def _scan_file_with_budget(rel_path: str):
    """Wie _scan_file, liefert zusätzlich das UNVERBRAUCHTE Baseline-Budget
    dieser Datei als Liste (rel_path, func, field, text) — ein Eintrag pro
    nicht gedecktem Vorkommen (Guardian-Finding #636: stale Einträge dürfen
    nicht liegen bleiben, sonst deckt eine später neu kopierte identische
    Zeile still einen echten NEUEN Fund)."""
    path = ROOT / rel_path
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=rel_path)
    visitor = _RiskyOrVisitor(src.splitlines())
    visitor.visit(tree)
    budget = collections.Counter(
        (fn, fld, txt) for (f, fn, fld, txt) in _BASELINE_KNOWN_OPEN
        if f == rel_path)
    out = []
    for lineno, func_name, field, snippet in visitor.findings:
        if (rel_path, func_name, field) in _EXCEPTIONS:
            continue
        key = (func_name, field, _norm_snippet(snippet))
        if budget[key] > 0:
            budget[key] -= 1
            continue
        out.append((rel_path, lineno, func_name, field, snippet))
    stale = [(rel_path, fn, fld, txt)
             for (fn, fld, txt), n in sorted(budget.items()) for _ in range(n)]
    return out, stale


def _scan_file(rel_path: str) -> list[tuple[str, int, str, str, str]]:
    """Returnt Liste (rel_path, lineno, func_name, field, snippet) für
    NICHT-ausgeschlossene Funde in dieser Datei."""
    return _scan_file_with_budget(rel_path)[0]


def main() -> int:
    all_findings: list[tuple[str, int, str, str, str]] = []
    stale: list[tuple[str, str, str, str]] = []
    scanned: set[str] = set()
    for rel_path in _SCAN_FILES:
        if not (ROOT / rel_path).exists():
            continue
        scanned.add(rel_path)
        found, left = _scan_file_with_budget(rel_path)
        all_findings.extend(found)
        stale.extend(left)
    # Baseline-Einträge für nicht (mehr) gescannte Dateien sind ebenfalls stale.
    stale.extend(e for e in _BASELINE_KNOWN_OPEN if e[0] not in scanned)

    if stale:
        print(f"FEHLER: {len(stale)} veraltete Baseline-Einträge in "
              f"_BASELINE_KNOWN_OPEN (kein passender Fund mehr im Code):",
              file=sys.stderr)
        for rel_path, func_name, field, text in stale:
            print(f"  {rel_path}  in {func_name}()  Feld={field!r}",
                  file=sys.stderr)
            print(f"    {text}", file=sys.stderr)
        print("\nFix: Fundstelle repariert oder Zeile geändert -> den Eintrag\n"
              "aus _BASELINE_KNOWN_OPEN entfernen (bzw. bei reinem Umbau den\n"
              "Zeilentext nachziehen). Die Baseline darf nur schrumpfen.",
              file=sys.stderr)

    if not all_findings and not stale:
        print(f"OK: Keine unbewachten '.get(feld) or 0'-Muster bei "
              f"{len(_ALLOWLIST_FIELDS)} Allowlist-Feldern in "
              f"{len(_SCAN_FILES)} Dateien gefunden.")
        return 0
    if not all_findings:
        return 1

    print(f"FEHLER: {len(all_findings)} unbewachte NaN-Bypass-Muster "
          f"(.get(feld) or 0 bei bekannten NaN-fähigen Feldern):",
          file=sys.stderr)
    for rel_path, lineno, func_name, field, snippet in all_findings:
        print(f"  {rel_path}:{lineno}  in {func_name}()  Feld={field!r}",
              file=sys.stderr)
        print(f"    {snippet}", file=sys.stderr)
    print(
        "\nFix: 'X.get(\"feld\")' vor dem 'or 0' durch einen echten NaN-\n"
        "Guard ersetzen (math.isfinite-Check, z. B. generate_report._safe_float\n"
        "oder _finite()), NICHT durch eine neue lokale Reimplementierung\n"
        "(siehe PR #558 — genau das war selbst ein Bug). Falls der\n"
        "KONSUMENT dieser Zeile bereits nachweislich NaN-gehärtet ist,\n"
        "die Stelle mit Beleg-Kommentar in _EXCEPTIONS in\n"
        "scripts/lint_nan_bypass_fields.py eintragen.",
        file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
