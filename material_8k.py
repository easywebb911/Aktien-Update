"""Materielle-8-K-Sammelfeld (§6c) — forward-only S10_OBSERVED-Persistenz.

Sammelt pro postclose-Top-10-Record die **materiellen 8-K** eines Emittenten
aus SEC-EDGAR (keyless) — anchor über **CIK**, nie den heutigen Ticker.
Speichert roh: ``acceptance_datetime``, ``accession``, ``cik``,
``item_codes[]`` und ``matched_terms[]`` (FDA-CORE-Annotation). Reine
Analyse-/Outcome-Persistenz.

DISZIPLIN (eingefroren):
  • KEIN Score-/Filter-/Push-/Anzeige-Effekt. Nur ``backtest_history.json``.
    Das Feld darf NIEMALS als Score-Feature gelesen werden (Look-Ahead-
    Konvention analog ``entry_past_return_5d`` #402).
  • Point-in-time: NUR 8-K mit ``acceptance_datetime <= Report-Zeitpunkt``
    (und ``>= Report - MATERIAL_8K_LOOKBACK_DAYS``). ``period_ending``/
    ``reportDate`` NIE als Zeitfilter (A2: bis 7 Tage Δ).
  • CIK-Anchoring gegen Ticker-Recycling/Reverse-Merger. Ticker→CIK nur über
    ``company_tickers.json``; keine eindeutige CIK → fail-soft, leer, geloggt.
  • Fail-soft überall: EDGAR unerreichbar / Rate-Limit / leer / Format-Wechsel
    → ``collected=False`` + Grund-Code, GELOGGT, kein Crash, kein Retry-Sturm.
  • Deterministisch: der einzige Zeit-Input ist das übergebene ``now_utc``
    (= Report-Zeitpunkt) und echte ``acceptance_datetime``-Strings aus EDGAR.
    Kein ``datetime.now()`` im Wertepfad. ``time.monotonic()`` steuert nur
    das Fail-soft-Zeitbudget (Skip-mit-Log), nicht den Normal-Pfad-Wert.

I/O ist injizierbar (``get_json`` / ``get_text`` / ``company_tickers``) →
stdlib-only-Tests ohne Netzwerk. Die Default-I/O importiert ``requests``
LAZY (erst im Call), damit ``import material_8k`` stdlib-only bleibt.

ISOLIERTER RÜCKWEG (B0-1): das Feld ist EIN benannter Top-Level-Key
``material_8k_events`` pro Record, geschrieben AUSSCHLIESSLICH hier.
``scripts/purge_material_8k_events.py`` poppt exakt diesen Key aus jedem
Record — kein Manifest nötig (benannter Key ist eindeutig, keine Recompute-
Kollision wie beim ``entry_past_return_5d``-Wert), alle anderen Felder bleiben
byte-identisch.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Fallback-Defaults NUR falls config nicht importierbar ist (Tests importieren
# config normal). config.py bleibt Single-Source-of-Truth — der Aufrufer in
# backtest_history reicht die config-Werte explizit durch.
_FALLBACK_QUALIFYING_ITEMS = ("1.01", "2.02", "5.02", "7.01", "8.01")
_FALLBACK_CORE_TERMS = ("Complete Response Letter", "PDUFA",
                        "received FDA approval")
_FALLBACK = {
    "lookback_days": 5,
    "cap_n": 8,
    "run_budget_s": 45.0,
    "http_timeout": 10,
    "max_docs": 3,
    "sleep_s": 0.3,
}


def _cfg(name, default):
    """Liest eine config-Konstante lazy; Fallback wenn config fehlt."""
    try:
        import config
        return getattr(config, name, default)
    except Exception:
        return default


def _default_ua() -> str:
    import os
    return os.environ.get("EDGAR_USER_AGENT",
                          "Squeeze Report contact@example.com")


# ── Default-I/O (lazy requests) ──────────────────────────────────────────────
def _http_get_json(url: str, ua: str, timeout: int):
    import requests
    r = requests.get(url, headers={"User-Agent": ua,
                                   "Accept": "application/json"},
                     timeout=timeout)
    if r.status_code != 200:
        log.warning("material_8k GET %s → HTTP %s", url, r.status_code)
        return None
    return r.json()


def _http_get_text(url: str, ua: str, timeout: int):
    import requests
    r = requests.get(url, headers={"User-Agent": ua}, timeout=timeout)
    if r.status_code != 200:
        log.debug("material_8k GET(text) %s → HTTP %s", url, r.status_code)
        return None
    return r.text


# ── Pure Helfer ──────────────────────────────────────────────────────────────
def build_cik_index(company_tickers_json) -> dict:
    """``company_tickers.json`` → ``{TICKER: {cik10, ...}}``. Pure.

    Mehrere CIKs pro Ticker (selten) → Set mit >1 Element → ``resolve_cik``
    liefert dann None (keine eindeutige CIK).
    """
    idx: dict[str, set] = {}
    if not isinstance(company_tickers_json, dict):
        return idx
    for v in company_tickers_json.values():
        if not isinstance(v, dict):
            continue
        try:
            t = str(v.get("ticker", "")).strip().upper()
            c = int(v.get("cik_str"))
        except (TypeError, ValueError):
            continue
        if not t:
            continue
        idx.setdefault(t, set()).add(f"{c:010d}")
    return idx


def resolve_cik(ticker: str, cik_index: dict):
    """Eindeutige zero-padded CIK10 oder None. Pure."""
    ciks = cik_index.get((ticker or "").strip().upper())
    if not ciks or len(ciks) != 1:
        return None
    return next(iter(ciks))


def _parse_acc_dt(s):
    """ISO-8601 (mit optionalem ``Z``/Fraktion) → aware datetime, sonst None."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def select_windowed_8k(submissions_json, *, now_utc, lookback_days,
                       qualifying_items, cik) -> list:
    """Pure: qualifizierende 8-K im Point-in-time-Fenster, aufsteigend sortiert.

    Filter: ``form`` beginnt mit ``8-K`` UND ≥1 qualifizierender item_code
    UND ``now-lookback <= acceptance_datetime <= now``. Sortierung nach
    acceptance (deterministisch). Jedes Event enthält intern zusätzlich
    ``_primary_document`` (für den matched_terms-Doc-Scan; wird vor der
    Persistenz entfernt).
    """
    rec = (((submissions_json or {}).get("filings") or {}).get("recent")
           or {})
    forms = rec.get("form") or []
    items = rec.get("items") or []
    accs = rec.get("acceptanceDateTime") or []
    adsh = rec.get("accessionNumber") or []
    prim = rec.get("primaryDocument") or []
    n = len(forms)
    lo = now_utc - timedelta(days=lookback_days)
    qset = set(qualifying_items)
    out = []
    for i in range(n):
        if not str(forms[i]).startswith("8-K"):
            continue
        acc_dt = _parse_acc_dt(accs[i] if i < len(accs) else None)
        if acc_dt is None or acc_dt > now_utc or acc_dt < lo:
            continue
        raw_items = str(items[i]) if i < len(items) else ""
        codes = [c.strip() for c in raw_items.split(",") if c.strip()]
        if not (qset & set(codes)):
            continue
        out.append({
            "acceptance_datetime": str(accs[i]),
            "accession": str(adsh[i]) if i < len(adsh) else "",
            "cik": cik,
            "item_codes": codes,
            "matched_terms": [],
            "_primary_document": str(prim[i]) if i < len(prim) else "",
            "_sort_dt": acc_dt,
        })
    out.sort(key=lambda e: e["_sort_dt"])
    for e in out:
        e.pop("_sort_dt", None)
    return out


def _accession_nodash(accession: str) -> str:
    return (accession or "").replace("-", "")


def _filing_index_url(cik: str, accession: str) -> str:
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{_accession_nodash(accession)}/index.json")


def _doc_url(cik: str, accession: str, name: str) -> str:
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{_accession_nodash(accession)}/{name}")


def select_scan_docs(index_json, primary_document, *, max_docs) -> list:
    """Pure: aus filing ``index.json`` das primaryDocument + EX-99*-Exhibits.

    EXZELLENZ-1b: der FDA-Text steht im EXHIBIT (EX-99.1), nicht im 8-K-Mantel
    — deshalb werden Exhibits explizit mitgescannt, nicht nur die Primärdatei.
    """
    items = (((index_json or {}).get("directory") or {}).get("item")) or []
    names: list[str] = []
    if primary_document:
        names.append(str(primary_document))
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name", ""))
        typ = str(it.get("type", ""))
        if not name or name in names:
            continue
        low = name.lower()
        if typ.upper().startswith("EX-99") or "ex99" in low or "ex-99" in low:
            names.append(name)
    names = [n for n in names
             if n.lower().endswith((".htm", ".html", ".txt"))]
    return names[:max_docs]


def scan_terms_in_text(text, core_terms) -> list:
    """Pure: Teilmenge der CORE-Terme (case-insensitive Substring), stabile
    Reihenfolge = ``core_terms``-Reihenfolge."""
    if not text:
        return []
    low = str(text).lower()
    return [t for t in core_terms if t.lower() in low]


# ── Orchestrierung ───────────────────────────────────────────────────────────
def _empty_wrapper(reason=None, cik=None) -> dict:
    return {"collected": False, "reason": reason, "cik": cik,
            "truncated": False, "events": []}


def collect_for_ticker(ticker, *, now_utc, cik_index, ua, timeout,
                       lookback_days, qualifying_items, core_terms, cap_n,
                       max_docs, get_json, get_text,
                       deadline=None, sleep_s=0.0) -> dict:
    """Fail-soft: liefert das ``material_8k_events``-Wrapper-Dict für EINEN
    Ticker. Raise nie."""
    cik = resolve_cik(ticker, cik_index)
    if cik is None:
        log.info("material_8k %s: keine eindeutige CIK — leer (no_cik)", ticker)
        return _empty_wrapper(reason="no_cik")

    try:
        sub = get_json(f"https://data.sec.gov/submissions/CIK{cik}.json",
                       ua, timeout)
    except Exception as exc:
        log.warning("material_8k %s: submissions-Fetch fehlgeschlagen: %s",
                    ticker, exc)
        sub = None
    if sub is None:
        return _empty_wrapper(reason="fetch_failed", cik=cik)

    events = select_windowed_8k(
        sub, now_utc=now_utc, lookback_days=lookback_days,
        qualifying_items=qualifying_items, cik=cik)

    wrapper = {"collected": True, "reason": None, "cik": cik,
               "truncated": False, "events": []}
    if len(events) > cap_n:
        wrapper["truncated"] = True
        log.warning("material_8k %s: %d qualifizierende 8-K > Cap %d — "
                    "truncated (erste %d nach acceptance)", ticker,
                    len(events), cap_n, cap_n)
        events = events[:cap_n]

    # matched_terms-Annotation (best-effort, Zeitbudget-begrenzt). Rohdaten
    # bleiben IMMER erhalten; nur der Term-Scan wird bei Budget-Ablauf
    # übersprungen (reason=budget_skip).
    for ev in events:
        if deadline is not None and time.monotonic() > deadline:
            wrapper["reason"] = "budget_skip"
            log.warning("material_8k %s: Zeitbudget erschöpft — matched_terms-"
                        "Scan übersprungen (Rohdaten bleiben)", ticker)
            break
        try:
            idx = get_json(_filing_index_url(cik, ev["accession"]), ua, timeout)
        except Exception as exc:
            log.debug("material_8k %s: index.json-Fetch fehlgeschlagen: %s",
                      ticker, exc)
            idx = None
        found = set()
        for name in select_scan_docs(idx, ev.get("_primary_document", ""),
                                     max_docs=max_docs):
            if deadline is not None and time.monotonic() > deadline:
                wrapper["reason"] = "budget_skip"
                break
            if sleep_s:
                time.sleep(sleep_s)
            try:
                txt = get_text(_doc_url(cik, ev["accession"], name), ua, timeout)
            except Exception as exc:
                log.debug("material_8k %s: Doc-Fetch %s fehlgeschlagen: %s",
                          ticker, name, exc)
                txt = None
            for t in scan_terms_in_text(txt, core_terms):
                found.add(t)
        ev["matched_terms"] = [t for t in core_terms if t in found]
        if sleep_s:
            time.sleep(sleep_s)

    for ev in events:
        ev.pop("_primary_document", None)
    wrapper["events"] = events
    return wrapper


def collect_material_8k_events(tickers, *, now_utc=None, ua=None,
                               lookback_days=None, qualifying_items=None,
                               core_terms=None, cap_n=None, max_docs=None,
                               run_budget_s=None, http_timeout=None,
                               sleep_s=None, get_json=None, get_text=None,
                               company_tickers=None) -> dict:
    """Sammelt für ``tickers`` (Top-10) je das ``material_8k_events``-Wrapper-
    Dict. ``company_tickers.json`` wird EINMAL geholt (geteilt). Fail-soft
    über den gesamten Pfad — einzelne Ticker-Fehler nullen nur diesen Ticker.

    Rückgabe: ``{ticker: wrapper}``.
    """
    if now_utc is None:
        # NUR Fallback wenn der Aufrufer keinen Report-Zeitpunkt reicht. Der
        # Produktions-Aufrufer (backtest_history) übergibt IMMER now_utc.
        now_utc = datetime.now(timezone.utc)
    ua = ua or _default_ua()
    get_json = get_json or _http_get_json
    get_text = get_text or _http_get_text
    lookback_days = (lookback_days if lookback_days is not None
                     else _cfg("MATERIAL_8K_LOOKBACK_DAYS",
                               _FALLBACK["lookback_days"]))
    qualifying_items = (qualifying_items if qualifying_items is not None
                        else _cfg("MATERIAL_8K_QUALIFYING_ITEMS",
                                  _FALLBACK_QUALIFYING_ITEMS))
    core_terms = (core_terms if core_terms is not None
                  else _cfg("MATERIAL_8K_CORE_TERMS", _FALLBACK_CORE_TERMS))
    cap_n = cap_n if cap_n is not None else _cfg("MATERIAL_8K_CAP_N",
                                                 _FALLBACK["cap_n"])
    max_docs = (max_docs if max_docs is not None
                else _cfg("MATERIAL_8K_MAX_DOCS_PER_FILING",
                          _FALLBACK["max_docs"]))
    run_budget_s = (run_budget_s if run_budget_s is not None
                    else _cfg("MATERIAL_8K_RUN_BUDGET_S",
                              _FALLBACK["run_budget_s"]))
    http_timeout = (http_timeout if http_timeout is not None
                    else _cfg("MATERIAL_8K_HTTP_TIMEOUT",
                              _FALLBACK["http_timeout"]))
    sleep_s = (sleep_s if sleep_s is not None
               else _cfg("MATERIAL_8K_SLEEP_S", _FALLBACK["sleep_s"]))

    result: dict[str, dict] = {}
    if not tickers:
        return result

    ct = company_tickers
    if ct is None:
        try:
            ct = get_json(_COMPANY_TICKERS_URL, ua, http_timeout)
        except Exception as exc:
            log.warning("material_8k: company_tickers-Fetch fehlgeschlagen: %s",
                        exc)
            ct = None
    cik_index = build_cik_index(ct)
    if not cik_index:
        log.warning("material_8k: leerer CIK-Index → alle Ticker leer "
                    "(fetch_failed)")
        return {t: _empty_wrapper(reason="fetch_failed") for t in tickers}

    deadline = (time.monotonic() + run_budget_s) if run_budget_s else None
    for t in tickers:
        # HARTER Gesamt-Cap (Guardian-Fix): vor JEDEM neuen Ticker prüfen, ob
        # das Run-Budget schon erschöpft ist → restliche Ticker werden gar
        # nicht erst gestartet (budget_skip, leer). Damit ist der Gesamt-Wall-
        # Clock auf ~run_budget_s + EIN in-flight collect_for_ticker begrenzt
        # (statt N_tickers × HTTP_TIMEOUT bei EDGAR-Slowdown). Skip-mit-Log,
        # kein Stau.
        if deadline is not None and time.monotonic() > deadline:
            log.warning("material_8k: Gesamt-Zeitbudget erschöpft — Ticker %s "
                        "(und ggf. weitere) übersprungen (budget_skip)", t)
            result[t] = _empty_wrapper(reason="budget_skip")
            continue
        try:
            result[t] = collect_for_ticker(
                t, now_utc=now_utc, cik_index=cik_index, ua=ua,
                timeout=http_timeout, lookback_days=lookback_days,
                qualifying_items=qualifying_items, core_terms=core_terms,
                cap_n=cap_n, max_docs=max_docs, get_json=get_json,
                get_text=get_text, deadline=deadline, sleep_s=sleep_s)
        except Exception as exc:
            log.warning("material_8k %s: unerwarteter Fehler (fail-soft): %s",
                        t, exc)
            result[t] = _empty_wrapper(reason="error")
    return result


# ── Selbsttest (nur manuell / im temporären EDGAR-Testlauf) ──────────────────
def _selftest(argv) -> int:
    """``python -m material_8k --ticker LENZ --asof 2025-11-06`` — echter
    EDGAR-Call, druckt Roh-Wrapper + Timing. Kein Repo-Write."""
    import argparse
    import json as _json
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", action="append", required=True,
                   help="Ticker (mehrfach möglich)")
    p.add_argument("--asof", default=None,
                   help="Report-Zeitpunkt ISO (Default: jetzt UTC)")
    p.add_argument("--lookback", type=int, default=None,
                   help="Lookback-Kalendertage (Default: config-Wert)")
    a = p.parse_args(argv)
    now = (_parse_acc_dt(a.asof) if a.asof
           else datetime.now(timezone.utc))
    if a.asof and now is None:
        print(f"Ungültiges --asof: {a.asof}")
        return 2
    t0 = time.monotonic()
    res = collect_material_8k_events(a.ticker, now_utc=now,
                                     lookback_days=a.lookback)
    dt = time.monotonic() - t0
    print(_json.dumps(res, indent=2, ensure_ascii=False))
    print(f"\n[timing] {len(a.ticker)} Ticker in {dt:.2f}s "
          f"(now_utc={now.isoformat()})")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_selftest(sys.argv[1:]))
