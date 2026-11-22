"""Stilles Kennzeichen „Verwässerung“ (Aktienausgabe laut SEC) — SAMMLUNG.

Easy-Entscheid 22.11.2026 (Lit-Check 18.11.: Billett/Floros/Garfinkel JFQA
2019; Schultz JFQA 2023). Nur sammeln und zählen: KEIN Score-, Filter-,
Auswahl-, Anzeige- oder Push-Effekt, keine Auswertung gegen Kurse/Treffer
ohne Easys ausdrücklichen Entscheid und vorab festgeschriebene Regel.
Top-10-Einträge sind Blindfenster-Daten (nur speichern und zählen). Das Feld
ist KEIN Score-Input (Look-ahead-Konvention wie ``material_8k_events``).

Quelle: dasselbe ``data.sec.gov/submissions``-JSON, das ``material_8k`` im
Postclose je Top-10-Ticker ohnehin holt (``extras_out[t]["verw_quelle"]``) —
kein zusätzlicher Abruf.

Regel-ENTWURF (nichts eingefroren, beide Fassungen werden gezählt):
  VERW(D) = mindestens eine Meldung mit Form-Präfix (eng ``424B5`` / breit
  ``424B``), deren Annahme-Datum in US-Ostküstenzeit zwischen D−179 und D
  liegt (180 Kalendertage einschließlich D) UND deren Annahmezeit nicht nach
  dem Report-Zeitpunkt liegt (Point-in-time, nur ``acceptanceDateTime``).

Unbekannt ≠ 0: Abruf gescheitert, keine CIK, unvollständige Liste → die
Kennzeichen sind ``None`` mit lesbarem ``grund``, nie ``False``.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

FIELD = "verwaesserung"
SCHEMA_V = 1
WINDOW_DAYS = 180          # D−179 … D (ET-Datum)
RAW_DAYS = 365             # Rohliste D−364 … D (ET-Datum)
QUELLE = "data.sec.gov submissions (filings.recent)"
_ET = ZoneInfo("America/New_York")

# Lesbare Gründe für ``geprueft=False``.
_GRUND_TEXT = {
    "no_cik": "keine eindeutige CIK",
    "fetch_failed": "Abruf fehlgeschlagen",
    "budget_skip": "Zeitbudget erschöpft",
    "recent_fehlt": "filings.recent fehlt",
}


def _report_day(report_date) -> date | None:
    """``"DD.MM.YYYY"`` / ``"YYYY-MM-DD"`` / ``date`` → date."""
    if isinstance(report_date, date) and not isinstance(report_date, datetime):
        return report_date
    s = str(report_date or "")
    try:
        if "." in s:
            d, m, y = s.split(".")
            return date(int(y), int(m), int(d))
        return date.fromisoformat(s[:10])
    except (TypeError, ValueError):
        return None


def _et_date(acc_utc: str) -> date | None:
    try:
        dt = datetime.fromisoformat(str(acc_utc).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_ET).date()


def _empty(grund: str, cik=None, geprueft: bool = False) -> dict:
    return {
        "schema_v": SCHEMA_V, "geprueft": geprueft, "cik": cik,
        "grund": grund, "quelle": QUELLE, "fenster_tage": WINDOW_DAYS,
        "verw_424b5_180d": None, "anzahl_424b5_180d": None,
        "juengste_424b5_annahme_utc": None,
        "verw_424b_180d": None, "anzahl_424b_180d": None,
        "juengste_424b_annahme_utc": None,
        "recent_aelteste_utc": None, "recent_files_vorhanden": None,
        "rohliste_vollstaendig": None, "rohliste": None,
    }


def build(m8k_extras, report_date, *, material_8k_enabled: bool = True) -> dict:
    """Pure: Block ``verwaesserung`` für einen Backtest-Eintrag.

    ``m8k_extras`` ist ``material_8k.collect_material_8k_events(extras_out=…)
    [ticker]`` (None, wenn der Ticker in diesem Lauf nicht gesammelt wurde).
    Die Rohzeilen tragen bereits nur Annahmen ``<= Report-Zeitpunkt``.
    Deterministisch, keine Uhr."""
    if not material_8k_enabled:
        return _empty("edgar_aus")
    if not isinstance(m8k_extras, dict):
        return _empty("edgar_nicht_gesammelt")
    src = m8k_extras.get("verw_quelle")
    if not isinstance(src, dict):
        return _empty(str(m8k_extras.get("reason") or "keine_rohdaten"))
    cik = src.get("cik")
    if not src.get("ok"):
        g = str(src.get("grund") or "unbekannt")
        return _empty(_GRUND_TEXT.get(g, g), cik)
    d = _report_day(report_date)
    if d is None:
        return _empty("berichtstag_unlesbar", cik)
    w_lo = d - timedelta(days=WINDOW_DAYS - 1)
    r_lo = d - timedelta(days=RAW_DAYS - 1)
    out = _empty(None, cik, geprueft=True)
    out["recent_aelteste_utc"] = src.get("recent_aelteste_utc")
    out["recent_files_vorhanden"] = bool(src.get("recent_files_vorhanden"))
    oldest = _et_date(src.get("recent_aelteste_utc")) if src.get("recent_aelteste_utc") else None
    # Vollständig, wenn recent bis vor das Fenster reicht ODER es keine
    # Zusatzdateien gibt (dann ist recent die ganze Historie).
    def _covers(lo):
        return (not out["recent_files_vorhanden"]) or (oldest is not None and oldest <= lo)
    raw = []
    for r in src.get("rows") or []:
        ed = _et_date(r.get("acceptance_utc"))
        if ed is None or ed < r_lo or ed > d:
            continue
        raw.append({"form": r.get("form"), "acceptance_utc": r.get("acceptance_utc"),
                    "accession": r.get("accession")})
    raw.sort(key=lambda r: (str(r["acceptance_utc"]), str(r["accession"])))
    out["rohliste"] = raw
    out["rohliste_vollstaendig"] = _covers(r_lo)
    if not _covers(w_lo):
        out["geprueft"] = False
        out["grund"] = "recent unvollständig"
        return out
    for key, pref in (("424b5", "424B5"), ("424b", "424B")):
        hits = [r for r in raw if str(r["form"] or "").startswith(pref)
                and w_lo <= _et_date(r["acceptance_utc"]) <= d]
        out[f"anzahl_{key}_180d"] = len(hits)
        out[f"verw_{key}_180d"] = bool(hits)
        out[f"juengste_{key}_annahme_utc"] = (max(h["acceptance_utc"] for h in hits)
                                              if hits else None)
    return out


def log_line(entries: list[dict]) -> str:
    """Zählungen über die in DIESEM Lauf angehängten Einträge (keine Werte)."""
    blocks = [e.get(FIELD) for e in entries if isinstance(e.get(FIELD), dict)]
    n = len(entries)
    p = [b for b in blocks if b.get("geprueft")]
    n5 = sum(1 for b in p if b.get("verw_424b5_180d"))
    nb = sum(1 for b in p if b.get("verw_424b_180d"))
    gr: dict[str, int] = {}
    for b in blocks:
        if not b.get("geprueft"):
            g = str(b.get("grund") or "?")
            gr[g] = gr.get(g, 0) + 1
    why = ", ".join(f"{k} {v}" for k, v in sorted(gr.items(), key=lambda x: (-x[1], x[0])))
    return (f"[verwaesserung] {n} neue Einträge: geprüft {len(p)} · 424B5 {n5} · "
            f"424B {nb} · unbekannt {n - len(p)}" + (f" ({why})" if why else ""))


def _last_day_blocks(bh_path):
    with open(bh_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    rows = [e for e in (data if isinstance(data, list) else [])
            if isinstance(e, dict) and isinstance(e.get(FIELD), dict)
            and not e.get("bootstrap")]
    if not rows:
        return None, []

    def _k(e):
        d = _report_day(e.get("date"))
        return d or date.min
    last = max(_k(e) for e in rows)
    return last, [e[FIELD] for e in rows if _k(e) == last]


def _why(blocks) -> str:
    gr: dict[str, int] = {}
    for b in blocks:
        if not b.get("geprueft"):
            g = str(b.get("grund") or "?")
            gr[g] = gr.get(g, 0) + 1
    return ", ".join(f"{k} {v}" for k, v in sorted(gr.items(), key=lambda x: (-x[1], x[0])))


def digest_line(bh_path) -> str:
    """„🧾 Verwässerung (TT.MM.): X von N mit Meldung · Y unbekannt (Gründe)“
    aus dem jüngsten Tag mit dem Feld. Raise nie."""
    try:
        last, blocks = _last_day_blocks(bh_path)
    except FileNotFoundError:
        return "🧾 Verwässerung: Datei fehlt"
    except Exception:
        return "🧾 Verwässerung: Status nicht ermittelbar"
    if not blocks:
        return "🧾 Verwässerung: sammelt ab dem nächsten Postclose (noch kein Eintrag)"
    n = len(blocks)
    p = [b for b in blocks if b.get("geprueft")]
    n5 = sum(1 for b in p if b.get("verw_424b5_180d"))
    nb = sum(1 for b in p if b.get("verw_424b_180d"))
    txt = (f"🧾 Verwässerung ({last.day:02d}.{last.month:02d}.): {n5} von {n} mit 424B5 · "
           f"{nb} mit 424B · {n - len(p)} unbekannt")
    why = _why(blocks)
    return txt + (f" ({why})" if why else "")


def warn_line(bh_path) -> str | None:
    """Warnzeile, wenn am jüngsten Tag ALLE Einträge unbekannt sind; ein
    Lesefehler ergibt eine Warnung statt Stille. Sonst None."""
    try:
        last, blocks = _last_day_blocks(bh_path)
    except FileNotFoundError:
        return None
    except Exception as exc:
        return f"🟡 Verwässerung: Warnprüfung fehlgeschlagen ({type(exc).__name__})"
    if not blocks or any(b.get("geprueft") for b in blocks):
        return None
    return (f"🟡 Verwässerung ({last.day:02d}.{last.month:02d}.): alle {len(blocks)} "
            f"unbekannt ({_why(blocks)})")
