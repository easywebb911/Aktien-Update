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
``_BASELINE_KNOWN_OPEN`` eingetragen (Schlüssel MIT Zeilennummer, bewusst
GETRENNT von ``_EXCEPTIONS`` — Baseline heißt NICHT „geprüft und sicher",
sondern „bekannt offen, noch nicht gefixt"). Der Lint ist dadurch bei
Einführung grün, fängt aber jede NEUE Instanz (andere Datei/Zeile/Feld)
sofort. Jede Baseline-Zeile ist ein offener Fix-Kandidat für einen
eigenen Folge-PR — beim Fixen den Eintrag entfernen, nicht stehen lassen.

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

# ── Baseline: Alt-Bestand zum Zeitpunkt der Lint-Einführung ─────────────
# NICHT zu verwechseln mit _EXCEPTIONS oben (dort: nachweislich sicher).
# Diese Liste sind GENUINE, noch OFFENE Gruppe-A-Fundstellen (Diagnose
# 21.-22.09.2026), die beim ersten echten Lint-Lauf (22.09.2026) auftraten
# -- absichtlich NICHT in diesem PR mitgefixt (Sequenz-Regel: nur melden,
# nicht mitfixen). Ohne diese Baseline wäre der Lint ab Einführung dauerhaft
# rot -- Alarm-Müdigkeit, widerspricht dem Repo-Grundsatz "Signal statt
# Rauschen". Schlüssel bewusst (Datei, Zeile, Feld) MIT Zeilennummer --
# anders als _EXCEPTIONS (dort: strukturelle Funktions-Eigenschaft, Zeile
# irrelevant) ist eine Baseline-Zeile ein MOMENTAUFNAHME-Fund: verschiebt
# sich der Code, soll ein Refactor das erneut sichtbar machen, statt
# stillschweigend weiter zu decken (bewusst fragiler als _EXCEPTIONS).
#
# ABBAU-PFAD: jede Zeile hier ist ein offener Fix-Kandidat für einen
# eigenen Folge-PR (Klassifikation dort selbst prüfen -- viele davon
# berühren risk_assessment()/short_situation()/_build_card_ctx()/
# compute_exit_score() u.ä., die laut Diagnose potenziell Manual-Merge-
# pflichtig sind). Bei einem Fix: den Eintrag HIER entfernen, nicht stehen
# lassen -- sonst verdeckt die Baseline den eigenen Fortschritt.
# 70 Einträge, generiert 22.09.2026 aus dem ersten echten Lint-Lauf
_BASELINE_KNOWN_OPEN: frozenset[tuple[str, int, str]] = frozenset({
    ("alert.py", 217, "regularMarketChangePercent"),
    ("alert.py", 218, "shortPercentOfFloat"),
    ("alert.py", 219, "shortRatio"),
    ("alert.py", 261, "shortPercentOfFloat"),
    ("alert.py", 267, "shortRatio"),
    ("alert.py", 268, "regularMarketPrice"),
    ("alert.py", 269, "regularMarketChangePercent"),
    ("backtest_bootstrap.py", 146, "shortRatio"),
    ("generate_report.py", 670, "shortPercentOfFloat"),
    ("generate_report.py", 677, "regularMarketChangePercent"),
    ("generate_report.py", 680, "shortRatio"),
    ("generate_report.py", 1018, "shortRatio"),
    ("generate_report.py", 1019, "shortPercentOfFloat"),
    ("generate_report.py", 1032, "floatShares"),
    ("generate_report.py", 1365, "shortRatio"),
    ("generate_report.py", 1366, "shortPercentOfFloat"),
    ("generate_report.py", 1384, "floatShares"),
    ("generate_report.py", 2738, "float_shares"),
    ("generate_report.py", 2752, "52w_high"),
    ("generate_report.py", 2753, "52w_low"),
    ("generate_report.py", 2758, "market_cap"),
    ("generate_report.py", 2951, "float_shares"),
    ("generate_report.py", 3103, "float_shares"),
    ("generate_report.py", 3128, "float_shares"),
    ("generate_report.py", 4012, "rsi14"),
    ("generate_report.py", 4044, "score"),
    ("generate_report.py", 4336, "short_float"),
    ("generate_report.py", 4358, "rel_volume"),
    ("generate_report.py", 4376, "short_float"),
    ("generate_report.py", 4377, "short_ratio"),
    ("generate_report.py", 4378, "rel_volume"),
    ("generate_report.py", 4510, "float_shares"),
    ("generate_report.py", 4511, "price"),
    ("generate_report.py", 4512, "market_cap"),
    ("generate_report.py", 4593, "float_shares"),
    ("generate_report.py", 4912, "float_shares"),
    ("generate_report.py", 4913, "float_shares"),
    ("generate_report.py", 4914, "float_shares"),
    ("generate_report.py", 4915, "float_shares"),
    ("generate_report.py", 5518, "score"),
    ("generate_report.py", 5975, "short_float"),
    ("generate_report.py", 5976, "short_ratio"),
    ("generate_report.py", 5977, "rel_volume"),
    ("generate_report.py", 5979, "change"),
    ("generate_report.py", 6245, "float_shares"),
    ("generate_report.py", 6350, "52w_high"),
    ("generate_report.py", 6350, "52w_low"),
    ("generate_report.py", 6447, "price"),
    ("generate_report.py", 6448, "short_float"),
    ("generate_report.py", 6449, "short_ratio"),
    ("generate_report.py", 6450, "rel_volume"),
    ("generate_report.py", 6451, "change"),
    ("generate_report.py", 6786, "float_shares"),
    ("generate_report.py", 6794, "52w_high"),
    ("generate_report.py", 6795, "52w_low"),
    ("generate_report.py", 7477, "float_shares"),
    ("generate_report.py", 16241, "entry_price"),
    ("generate_report.py", 16250, "price"),
    ("generate_report.py", 16274, "setup_today"),
    ("generate_report.py", 17031, "score"),
    ("generate_report.py", 17528, "score"),
    ("generate_report.py", 18082, "score"),
    ("generate_report.py", 18125, "score"),
    ("generate_report.py", 18274, "score"),
    ("health_check.py", 627, "score"),
    ("ki_agent.py", 1299, "last_price"),
    ("ki_agent.py", 2637, "score"),
    ("ki_agent.py", 2645, "rvol_4d"),
    ("ki_agent.py", 2649, "rvol_4d"),
    ("ki_agent.py", 3107, "rvol_4d"),
})


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


def _scan_file(rel_path: str) -> list[tuple[str, int, str, str, str]]:
    """Returnt Liste (rel_path, lineno, func_name, field, snippet) für
    NICHT-ausgeschlossene Funde in dieser Datei."""
    path = ROOT / rel_path
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=rel_path)
    visitor = _RiskyOrVisitor(src.splitlines())
    visitor.visit(tree)
    out = []
    for lineno, func_name, field, snippet in visitor.findings:
        if (rel_path, func_name, field) in _EXCEPTIONS:
            continue
        if (rel_path, lineno, field) in _BASELINE_KNOWN_OPEN:
            continue
        out.append((rel_path, lineno, func_name, field, snippet))
    return out


def main() -> int:
    all_findings: list[tuple[str, int, str, str, str]] = []
    for rel_path in _SCAN_FILES:
        if not (ROOT / rel_path).exists():
            continue
        all_findings.extend(_scan_file(rel_path))

    if not all_findings:
        print(f"OK: Keine unbewachten '.get(feld) or 0'-Muster bei "
              f"{len(_ALLOWLIST_FIELDS)} Allowlist-Feldern in "
              f"{len(_SCAN_FILES)} Dateien gefunden.")
        return 0

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
