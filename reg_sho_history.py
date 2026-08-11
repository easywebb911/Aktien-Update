"""reg_sho_history.py — Forward-only Reg-SHO-Threshold-Sammlung (prune-immun, 11.08.2026).

Sammelt pro postclose je Universums-Ticker, ob er auf der Reg-SHO-Threshold-Liste
SEINER BÖRSE steht — eigene, prune-immune Datei (``reg_sho_history.json``), analog
ftd_history. REINE Sammlung: KEIN Score/Filter/Push/Anzeige/Auswertung.

⚠ BÖRSEN-LÜCKE (Kernpunkt, Easy 11.08.): Die Threshold-Liste ist PRO BÖRSE
(Nasdaq / NYSE-Familie / …). Ein NYSE-Ticker gegen die Nasdaq-Liste geprüft wäre
ein stilles FALSCH-NEGATIV. Deshalb wird je Ticker die BÖRSE (yfinance
``.info["exchange"]``, kein Extra-Fetch) auf die zuständige Quelle gemappt und
NUR dann ``restricted=True/False`` gesetzt, wenn die RICHTIGE Liste erfolgreich
geladen wurde. In JEDEM anderen Fall bleibt ``restricted=None`` MIT Grund —
NIEMALS ``False``. ``False`` (geprüft, nicht drauf) und „nicht geprüft" sehen im
Datensatz NIE gleich aus. Das ist das härteste Abnahmekriterium — die EINZIGE
Stelle, die ``restricted`` auf einen Bool setzt, ist ``tk in syms`` im
``syms is not None``-Zweig (``_evaluate_ticker``).

TÄGLICH (Momentanstand): die Archiv-Verfügbarkeit ist NICHT bewiesen (die Probe
lud nur das heutige File; datums-parametrisierte URL macht Archiv plausibel, aber
ungeprüft) → jeder nicht gesammelte Tag könnte weg sein. Wie FTD zwei Daten:
``date`` (wann WIR lasen, = as-of) + ``source_date`` (Datum IN der Liste).

Disziplin (wie #525): forward-only (kein Backfill), idempotent pro
``(ticker, date)``, KEIN Prune/Cap (Lehre #519), fail-soft je Quelle (tote Quelle
→ kein ``False``, sondern ``None``+Grund), atomarer Write (Datei + State),
Zeitbudget vor JEDEM Netz-Schritt. Fetch-Fail und Leerbefund GETRENNT im State.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

try:
    from config import (REG_SHO_HISTORY_ENABLED, REG_SHO_HISTORY_FILE,
                        REG_SHO_HISTORY_STATE_FILE, REG_SHO_HTTP_TIMEOUT,
                        REG_SHO_TIME_BUDGET_S)
except Exception:  # pragma: no cover
    REG_SHO_HISTORY_ENABLED = True
    REG_SHO_HISTORY_FILE = "reg_sho_history.json"
    REG_SHO_HISTORY_STATE_FILE = "reg_sho_history_state.json"
    REG_SHO_HTTP_TIMEOUT = 15
    REG_SHO_TIME_BUDGET_S = 25.0

_UA = ("SqueezeReportRegSHO/1.0 (read-only research; "
       "contact squeeze-report-regsho@example.invalid) Mozilla/5.0")

# Börsen-Codes (yfinance .info["exchange"]) → Threshold-Quelle.
_NASDAQ_EX = frozenset({"NMS", "NGM", "NCM", "NAS", "NASDAQ", "NIM"})
_NYSE_EX = frozenset({"NYQ", "ASE", "PCX", "NYS", "NYSE", "AMEX", "ARCA", "NYSEAMERICAN"})

# Nasdaq-Übersicht (Probe #522: lieferte den datierten nasdaqth<YYYYMMDD>.txt-Link).
_NASDAQ_OVERVIEWS = (
    "https://www.nasdaqtrader.com/Trader.aspx?id=RegSHOThreshold",
    "http://www.nasdaqtrader.com/Trader.aspx?id=RegSHOThreshold",
)
_NASDAQ_FILE_RE = re.compile(r'(nasdaqth(\d{8})\.txt|regsho[^"\']*\.txt)', re.I)
_NASDAQ_DATE_RE = re.compile(r'nasdaqth(\d{8})\.txt', re.I)
# NYSE-Übersicht (Probe #522: HTTP 200, aber 0 extrahierbare Links — Versuch
# bleibt, Fallback ist none/nicht-abgedeckt).
_NYSE_OVERVIEWS = (
    "https://www.nyse.com/regulation/threshold-securities",
)
_NYSE_FILE_RE = re.compile(r'threshold[^"\']*\.(txt|csv)|regsho[^"\']*\.(txt|csv)', re.I)


# ── HTTP (urllib, stdlib — kein requests) ─────────────────────────────────────
def _http_get(url, *, timeout=None, ua=None):
    """``(status, text, error)``. FETCH-FAIL := ``error`` gesetzt."""
    to = REG_SHO_HTTP_TIMEOUT if timeout is None else timeout
    req = Request(url, headers={"User-Agent": ua or _UA, "Accept": "*/*"})
    try:
        with urlopen(req, timeout=to) as r:
            return getattr(r, "status", r.getcode()), r.read().decode("utf-8", "replace"), None
    except HTTPError as e:
        return e.code, None, f"HTTPError {e.code}"
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"


def _default_get_text(url):
    return _http_get(url)


# ── Börse → Quelle ────────────────────────────────────────────────────────────
def _source_for_exchange(ex):
    """``(source, reason)``: ``("nasdaq"|"nyse", None)`` bei abgedeckter Börse,
    sonst ``(None, "exchange_unknown")`` (kein Code) bzw.
    ``(None, "exchange_not_covered")`` (bekannter Code, aber nicht abgedeckt,
    z.B. Cboe/BATS)."""
    if not ex or not str(ex).strip():
        return None, "exchange_unknown"
    e = str(ex).strip().upper()
    if e in _NASDAQ_EX:
        return "nasdaq", None
    if e in _NYSE_EX:
        return "nyse", None
    return None, "exchange_not_covered"


# ── Nasdaq-Resolver ───────────────────────────────────────────────────────────
def parse_nasdaq_threshold(text):
    """``(symbols:set, source_date:str|None)``. Pipe-delimited, Header
    ``Symbol|Security Name|…``; Symbol = Spalte 0. Trailer-/Leerzeilen robust
    übersprungen. ``source_date`` aus dem 'File Creation Date'-Trailer, sonst None
    (der Discovery-Pfad ergänzt es sicherer aus dem Dateinamen)."""
    syms = set()
    src_date = None
    if not text:
        return syms, None
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.lower().startswith("symbol|"):
            continue
        m = re.search(r'(\d{4})(\d{2})(\d{2})', s)
        if "file creation" in s.lower() and m:
            src_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            continue
        first = s.split("|")[0].strip().upper()
        if first and first.isalpha():
            syms.add(first)
    return syms, src_date


def _resolve_nasdaq(get_text_fn, over_budget):
    """``(symbols:set|None, source_date:str|None, result:str)``.
    ``result`` ∈ ``ok:N`` / ``fetch_failed`` / ``empty`` / ``budget``.
    ``symbols=None`` heißt „Liste NICHT verwertbar" (→ Ticker bekommen None+Grund,
    nie False)."""
    last_err = None
    for ov in _NASDAQ_OVERVIEWS:
        if over_budget():
            return None, None, "budget"
        st, html, err = get_text_fn(ov)
        if err or st != 200 or not html:
            last_err = err or f"HTTP {st}"
            continue
        m = _NASDAQ_FILE_RE.search(html)
        if not m:
            continue                                   # Übersicht ok, aber kein Link
        href = m.group(0)
        url = href if href.startswith("http") else urljoin(ov, href)
        if over_budget():
            return None, None, "budget"
        st2, txt, err2 = get_text_fn(url)
        if err2 or st2 != 200 or not txt:
            last_err = err2 or f"HTTP {st2}"
            continue
        syms, src_date = parse_nasdaq_threshold(txt)
        dm = _NASDAQ_DATE_RE.search(url)               # Dateiname trägt das Datum
        if dm:
            src_date = f"{dm.group(1)[:4]}-{dm.group(1)[4:6]}-{dm.group(1)[6:8]}"
        if not syms:
            return None, src_date, "empty"             # geladen, 0 Symbole (Leerbefund)
        return syms, src_date, f"ok:{len(syms)}"
    return None, None, "fetch_failed"                  # keine Übersicht/Datei ladbar


# ── NYSE-Resolver (Versuch; Fallback = nicht auflösbar) ───────────────────────
def _resolve_nyse(get_text_fn, over_budget):
    """``(symbols:set|None, source_date:str|None, result:str)``.
    ``result`` ∈ ``ok:N`` / ``fetch_failed`` / ``empty`` / ``not_resolved`` /
    ``budget``. ``not_resolved`` = Übersicht(en) geladen, aber KEIN
    extrahierbarer Datei-Link (Probe #522: NYSE-Seite ist JS-gerendert). Der
    Versuch bleibt echt; der Fallback garantiert None statt False."""
    any_ok = False
    last_err = None
    for ov in _NYSE_OVERVIEWS:
        if over_budget():
            return None, None, "budget"
        st, html, err = get_text_fn(ov)
        if err or st != 200 or not html:
            last_err = err or f"HTTP {st}"
            continue
        any_ok = True
        m = _NYSE_FILE_RE.search(html)
        if not m:
            continue
        href = m.group(0)
        url = href if href.startswith("http") else urljoin(ov, href)
        if over_budget():
            return None, None, "budget"
        st2, txt, err2 = get_text_fn(url)
        if err2 or st2 != 200 or not txt:
            last_err = err2 or f"HTTP {st2}"
            continue
        syms = set()
        src_date = None
        for ln in txt.splitlines():
            s = ln.strip()
            if not s:
                continue
            first = re.split(r'[|,]', s)[0].strip().upper()
            if first and first.isalpha() and first != "SYMBOL":
                syms.add(first)
        if not syms:
            return None, src_date, "empty"
        return syms, src_date, f"ok:{len(syms)}"
    if any_ok:
        return None, None, "not_resolved"     # geladen, aber kein Datei-Link
    return None, None, "fetch_failed"          # Übersicht(en) tot


# ── Persistenz (eigene Datei + State, atomar, KEIN Prune) ─────────────────────
def _load_history(path=None):
    p = path or REG_SHO_HISTORY_FILE
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_history(hist, path=None):
    """Atomarer Write — BEWUSST OHNE JEDEN PRUNE (Lehre #519). Nur Nicht-Listen/
    Nicht-Dicts droppen + je Ticker nach ``date`` sortieren. KEIN ``[-N:]``-Slice,
    KEIN ``timedelta``/Cutoff, KEIN ``MAX_POINTS``. Kompakt. ``.tmp`` + ``os.replace``."""
    p = path or REG_SHO_HISTORY_FILE
    compact = {}
    for ticker, points in hist.items():
        if not isinstance(points, list):
            continue
        kept = [pt for pt in points if isinstance(pt, dict)]
        kept.sort(key=lambda pt: pt.get("date") or "")
        if kept:
            compact[ticker] = kept
    tmp = f"{p}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(compact, fh, separators=(",", ":"))
    os.replace(tmp, p)


def _load_state(path=None):
    p = path or REG_SHO_HISTORY_STATE_FILE
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_state(state, path=None):
    p = path or REG_SHO_HISTORY_STATE_FILE
    tmp = f"{p}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, separators=(",", ":"))
    os.replace(tmp, p)


# ── Per-Ticker-Bewertung (die none-vs-false-Grenze) ───────────────────────────
def _evaluate_ticker(ticker, exchange, sources, *, date_iso):
    """Baut den Punkt für EINEN Ticker. ``sources`` = ``{"nasdaq": (syms|None,
    src_date, result), "nyse": (...)}``.

    ``restricted`` wird auf einen Bool NUR gesetzt, wenn die zuständige Liste
    geladen ist (``syms is not None``) — ``tk in syms``. Sonst None + Grund."""
    src, reason0 = _source_for_exchange(exchange)
    point = {"date": date_iso, "restricted": None, "reason": None,
             "exchange": exchange if exchange else None, "source": src,
             "source_date": None}
    if src is None:
        point["reason"] = reason0                     # exchange_unknown / _not_covered
        return point
    syms, src_date, result = sources[src]
    if syms is None:
        # Quelle nicht verwertbar → None + spezifischer Grund (nie False).
        point["reason"] = {
            "empty": "source_empty",
            "not_resolved": "source_unresolved",
            "budget": "budget_skipped",
        }.get(result, "fetch_failed")
        return point
    # EINZIGE Stelle, die restricted auf einen Bool setzt:
    point["restricted"] = ticker in syms
    point["reason"] = None
    point["source_date"] = src_date
    return point


# ── Orchestrierung ────────────────────────────────────────────────────────────
def collect_and_persist(universe, *, report_date_iso=None, run_phase=None,
                        now_utc=None, get_nasdaq_text_fn=None, get_nyse_text_fn=None,
                        time_budget_s=None, hist_path=None, state_path=None):
    """Sammelt TÄGLICH (postclose) je Universums-Ticker den Reg-SHO-Threshold-
    Status. ``universe`` = Liste von Dicts mit ``ticker`` + ``exchange``.

    NUR postclose, idempotent pro ``(ticker, date)``, fail-soft, Zeitbudget vor
    jedem Netz-Schritt. Heartbeat + Quell-Health im Sidecar-State. Injizierbare
    Text-Fetcher (Tests ohne Netzwerk). Returns: Anzahl neu geschriebener Punkte."""
    if not REG_SHO_HISTORY_ENABLED:
        return 0
    if run_phase != "postclose":
        return 0
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    t_iso = report_date_iso or now.date().isoformat()
    budget = REG_SHO_TIME_BUDGET_S if time_budget_s is None else time_budget_s
    import time as _time
    t0 = _time.monotonic()

    def over_budget():
        return (_time.monotonic() - t0) > budget

    state = _load_state(state_path)
    state["last_run"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _finish(added):
        try:
            _save_state(state, state_path)
        except Exception as exc:   # pragma: no cover
            log.warning("[reg_sho] State-Write fehlgeschlagen (fail-soft): %s", exc)
        return added

    uni = [u for u in (universe or []) if isinstance(u, dict) and u.get("ticker")]

    # 1) Nasdaq-Liste (die meisten Universums-Ticker sind Nasdaq).
    nasdaq = _resolve_nasdaq(get_nasdaq_text_fn or _default_get_text, over_budget)
    state["nasdaq_result"] = nasdaq[2]

    # 2) NYSE-Liste NUR wenn ein Ticker sie braucht (spart einen Fetch).
    need_nyse = any(_source_for_exchange(u.get("exchange"))[0] == "nyse" for u in uni)
    if need_nyse and not over_budget():
        nyse = _resolve_nyse(get_nyse_text_fn or _default_get_text, over_budget)
    else:
        nyse = (None, None, "not_needed" if not need_nyse else "budget")
    state["nyse_result"] = nyse[2]

    sources = {"nasdaq": nasdaq, "nyse": nyse}

    # 3) Je Ticker bewerten + forward-only idempotent anhängen.
    hist = _load_history(hist_path)
    added = 0
    n_checked = n_restricted = n_none = 0
    for u in uni:
        try:
            tk = (u.get("ticker") or "").strip().upper()
            series = hist.setdefault(tk, [])
            if series and series[-1].get("date") == t_iso:   # idempotent
                continue
            point = _evaluate_ticker(tk, u.get("exchange"), sources, date_iso=t_iso)
            series.append(point)
            added += 1
            if point["restricted"] is None:
                n_none += 1
            else:
                n_checked += 1
                if point["restricted"]:
                    n_restricted += 1
        except Exception as exc:   # pragma: no cover — nie den Daily-Run brechen
            log.debug("[reg_sho] %s: %s", u.get("ticker"), exc)
            continue
    if added:
        _save_history(hist, hist_path)
    state["last_checked"] = n_checked
    state["last_none"] = n_none
    log.info("[reg_sho] %d Punkte · %d geprüft (%d restricted) · %d none · "
             "nasdaq=%s nyse=%s", added, n_checked, n_restricted, n_none,
             nasdaq[2], nyse[2])
    return _finish(added)
