"""EDGAR Fix (b) (Easy-Entscheid 22.11.2026): 8-K / Form 4 aus
``data.sec.gov/submissions/CIK##########.json`` statt ``browse-edgar?CIK=<Ticker>``.

Reine Helfer (kein Netz, kein State) — der Abruf lebt in ``ki_agent``.

Score-Gleichheit (Freeze KI-Score, n = 180/250): ``compute_signal`` liest den
Titel nur für Stichwort-Boni (8-K: ``SEC_RELEVANT_KEYWORDS``; Form 4:
„purchase“/„acquisition“). Die alte Quelle lieferte FESTE Titel (Beleg 100
KI-Läufe 25.10.–16.11.2026: 130 8-K-Treffer nur „8-K  - Current report“ bzw.
„8-K/A [Amend]  - Current report“, 181 Form-4-Treffer nur „4  - Statement of
changes in beneficial ownership of securities“ bzw. „425  - Prospectuses and
communications, business combinations“). Diese Helfer bauen exakt denselben
Wortlaut nach; unbekannte Formen bekommen einen Titel ohne Stichwort. Auch die
Auswahl bleibt gleich: der alte Filter ``type=8-K`` / ``type=4`` war eine
PRÄFIX-Suche (deshalb zählte 425 als „Form 4“) → ``form.startswith(prefix)``;
das Fenster misst die Annahmezeit (``acceptanceDateTime``, UTC — Beleg: NTLA-
8-K ``22:05:40Z``, als Ostküstenzeit läge das nach Schluss des EDGAR-Fensters).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

QUELLE = "data.sec.gov submissions"
RAW_FILE = "sec_meldungen.jsonl"
SCHEMA_V = 1

# Exakter Atom-Wortlaut der alten Quelle (aus den Logs belegt).
_TITLES = {
    "8-K":   "8-K  - Current report",
    "8-K/A": "8-K/A [Amend]  - Current report",
    "4":     "4  - Statement of changes in beneficial ownership of securities",
    "4/A":   "4/A [Amend]  - Statement of changes in beneficial ownership of securities",
    "425":   "425  - Prospectuses and communications, business combinations",
}


def title_for(form: str) -> str:
    """Titel im alten Atom-Wortlaut; unbekannte Form → ``"<form>  - <form>"``
    (enthält kein Stichwort, Punkte bleiben gleich)."""
    form = str(form or "").strip()
    if form in _TITLES:
        return _TITLES[form]
    base = form[:-2] if form.endswith("/A") else form
    if form.endswith("/A"):
        return f"{form} [Amend]  - {base}"
    return f"{form}  - {form}"


def parse_acceptance(s):
    """``acceptanceDateTime`` (ISO, ``Z``) → aware UTC datetime, sonst None."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _recent(sub) -> dict:
    rec = (((sub or {}).get("filings") or {}).get("recent")) if isinstance(sub, dict) else None
    return rec if isinstance(rec, dict) else {}


def filings_in_window(sub, *, prefix: str, cutoff_utc: datetime) -> list[dict]:
    """Alle Meldungen mit ``form.startswith(prefix)`` und Annahmezeit > cutoff,
    neueste zuerst. Jede mit den Rohfeldern der Quelle (unbekannt = None)."""
    rec = _recent(sub)
    forms = rec.get("form") or []
    out = []
    for i, form in enumerate(forms):
        form = str(form or "")
        if not form.startswith(prefix):
            continue

        def _get(key, _i=i):
            arr = rec.get(key) or []
            v = arr[_i] if _i < len(arr) else None
            return v if v not in ("", None) else None
        acc_dt = parse_acceptance(_get("acceptanceDateTime"))
        if acc_dt is None or acc_dt <= cutoff_utc:
            continue
        items = _get("items")
        out.append({
            "form": form,
            "accession": _get("accessionNumber"),
            "filing_date": _get("filingDate"),
            "acceptance_utc": acc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "items": ([x.strip() for x in str(items).split(",") if x.strip()]
                      if (items and prefix == "8-K") else None),
            "beschreibung": _get("primaryDocDescription"),
            "primary_document": _get("primaryDocument"),
            "_dt": acc_dt,
        })
    out.sort(key=lambda r: r["_dt"], reverse=True)
    return out


def latest(sub, *, prefix: str, cutoff_utc: datetime):
    """Neueste Meldung im Fenster oder None (= alter „erster Eintrag im Fenster“)."""
    f = filings_in_window(sub, prefix=prefix, cutoff_utc=cutoff_utc)
    return f[0] if f else None


def raw_records(ticker: str, cik: str, filings: list[dict], *, now_utc: datetime) -> list[dict]:
    """Zeilen für ``sec_meldungen.jsonl`` — nur Felder der öffentlichen SEC-Quelle."""
    out = []
    for f in filings:
        out.append({
            "schema_v": SCHEMA_V,
            "ticker": ticker,
            "cik": cik,
            "accession": f.get("accession"),
            "form": f.get("form"),
            "filing_date": f.get("filing_date"),
            "acceptance_utc": f.get("acceptance_utc"),
            "items": f.get("items"),
            "beschreibung": f.get("beschreibung"),
            "primary_document": f.get("primary_document"),
            "erfasst_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "quelle": QUELLE,
        })
    return out


def append_raw(records: list[dict], path: str = RAW_FILE) -> int:
    """Hängt neue Meldungen an (Dublette = gleicher Ticker + accession).
    Atomar (tmp + replace). Gibt die Zahl neuer Zeilen zurück. Wirft bei
    I/O-Fehlern (Aufrufer fängt)."""
    if not records:
        return 0
    seen = set()
    old = b""
    if os.path.exists(path):
        with open(path, "rb") as fh:
            old = fh.read()
        for line in old.decode("utf-8", "replace").splitlines():
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if isinstance(o, dict):
                seen.add((o.get("ticker"), o.get("accession")))
        if old and not old.endswith(b"\n"):
            old += b"\n"
    new_lines = []
    for r in sorted(records, key=lambda x: (str(x.get("ticker")), str(x.get("acceptance_utc")),
                                            str(x.get("accession")))):
        k = (r.get("ticker"), r.get("accession"))
        if r.get("accession") is None or k in seen:
            continue
        seen.add(k)
        new_lines.append(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    if not new_lines:
        return 0
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(old + "".join(new_lines).encode("utf-8"))
    os.replace(tmp, path)
    return len(new_lines)
