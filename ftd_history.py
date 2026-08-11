"""ftd_history.py — Forward-only SEC-Fail-to-Deliver-Sammlung (prune-immun, 11.08.2026).

Sammelt pro postclose die Fail-to-Deliver-Zeilen der Universums-Ticker aus dem
JEWEILS NEUESTEN SEC-Halbmonats-File in eine eigene, prune-immune Datei
(``ftd_history.json``) — analog options_oi_history / inst_ownership_history.
REINE Sammlung: KEIN Score/Filter/Push/Anzeige/Auswertung, kein Konsument,
löschbar ohne Nebenwirkung (Feature-Flag + Datei entfernen).

⚠ LOOK-AHEAD-FALLE (Punkt A, Easy 11.08.): SEC-FTD ist ~1 Monat RÜCKDATIERT.
Ein Fails-Wert für Settlement-Tag T war an Tag T NICHT bekannt — er wird erst
~1 Monat später veröffentlicht. Wer ihn später als Merkmal FÜR T nutzt, baut
Look-Ahead ein (genau die Klasse, die Reife-Gate #503 verhindert hat). Deshalb
trägt JEDER Punkt ZWEI Daten:
  ``settlement_date`` — wann der Ausfall war (SEC-Datenstand, rückdatiert)
  ``first_available`` — wann der Wert für UNS erstmals abrufbar war (Run-Tag der
                        Erst-Ingestion). Eine spätere Auswertung MUSS als
                        „as-of"-Datum ``first_available`` nutzen, NIE
                        ``settlement_date``.

Disziplin (wie #524): forward-only (kein Backfill in diesem PR), idempotent pro
``(ticker, settlement_date)``, KEIN Prune/Cap (Lehre #519), fail-soft je Quelle,
atomarer Write, hartes Zeitbudget. Fetch-Fail und Leerbefund werden GETRENNT
protokolliert.

KEIN Backfill: nur das jeweils neueste Halbmonats-File wird geprüft/ingested —
kein Voll-Download des Archivs (bis 2004). Das Archiv ist jederzeit später
beziehbar und gehört zur Auswertung, nicht zum Sammeln.

none-Semantik: eine tote Quelle → GAR KEIN Punkt (unbeobachtbar), NICHT „0 Fails".
Ein Ticker, der im geladenen File FEHLT, hatte schlicht keine meldepflichtigen
Fails (FTD-Daten sind von Natur aus dünn) → ebenfalls kein Punkt, kein „0".
"""
from __future__ import annotations

import io
import json
import logging
import math
import os
import re
import zipfile
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

try:  # zentrale Konstanten; Fallback macht das Modul standalone-testbar
    from config import (FTD_HISTORY_ENABLED, FTD_HISTORY_FILE,
                        FTD_HISTORY_STATE_FILE, FTD_HTTP_TIMEOUT, FTD_TIME_BUDGET_S)
except Exception:  # pragma: no cover
    FTD_HISTORY_ENABLED = True
    FTD_HISTORY_FILE = "ftd_history.json"
    FTD_HISTORY_STATE_FILE = "ftd_history_state.json"
    FTD_HTTP_TIMEOUT = 20
    FTD_TIME_BUDGET_S = 30.0

# Beschreibender Wegwerf-Kontakt (KEIN Secret) — SEC/EDGAR verlangt einen
# Kontakt-Header, blockt sonst produktive Aufrufe. .invalid ist per RFC 2606
# reserviert → erkennbar keine reale Adresse. Bei einer späteren Produktiv-
# Nutzung gehört hier ein Secret hin, nicht eine Klartext-Adresse.
_UA = ("SqueezeReportFTD/1.0 (read-only research; "
       "contact squeeze-report-ftd@example.invalid) Mozilla/5.0")

# Kandidaten-ÜBERSICHTSSEITEN (bestes Wissen aus Probe #522, beide lieferten dort
# HTTP 200 + 431 .zip-Links). Von HIER werden Datei-Links EXTRAHIERT, nicht
# konstruiert (Lehre #496). Reihenfolge = Fallback.
_FTD_OVERVIEWS = (
    "https://www.sec.gov/data/foiadocsfailsdatahtm",
    "https://www.sec.gov/foia/docs/failsdata.htm",
)
# Halbmonats-File: cnsfails<YYYYMM><a|b>.zip (a=erste, b=zweite Monatshälfte).
_FTD_FILE_RE = re.compile(r'cnsfails(\d{6})([ab])\.zip', re.I)


# ── HTTP (urllib, stdlib — KEINE requests-Abhängigkeit für den CI-Import) ─────
def _http_get(url, *, binary=False, timeout=None, ua=None):
    """``(status, body, error)``. FETCH-FAIL := ``error`` gesetzt (Exception/
    HTTPError). Getrennt von Leerbefund (status 200, 0 verwertbare Zeilen — das
    prüft der Caller)."""
    to = FTD_HTTP_TIMEOUT if timeout is None else timeout
    req = Request(url, headers={"User-Agent": ua or _UA, "Accept": "*/*"})
    try:
        with urlopen(req, timeout=to) as r:
            raw = r.read()
            st = getattr(r, "status", r.getcode())
            return st, (raw if binary else raw.decode("utf-8", "replace")), None
    except HTTPError as e:
        return e.code, None, f"HTTPError {e.code}"
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"


def _default_get_overview(url):
    """Default-Übersichts-Fetcher → ``(status, html, error)`` (urllib)."""
    return _http_get(url, binary=False)


def _default_get_bytes(url):
    """Default-ZIP-Fetcher → ``(status, bytes, error)`` (urllib)."""
    return _http_get(url, binary=True)


# ── Discovery: neuestes Halbmonats-File aus der Übersicht (nicht geraten) ──────
def _file_sort_key(name):
    """``cnsfails202607a.zip`` → ``("202607","a")`` für max()-Vergleich."""
    m = _FTD_FILE_RE.search(name or "")
    return (m.group(1), m.group(2).lower()) if m else ("000000", "")


def discover_newest_ftd_file(get_overview_fn=None):
    """``(file_url, file_name, error)``. Liest die Kandidaten-Übersichten, extrahiert
    ``cnsfails…zip``-Links und wählt den NEUESTEN (max YYYYMM+Hälfte). ``error``
    gesetzt = ALLE Übersichten Fetch-Fail (unbeobachtbar). ``file_url=None,
    error=None`` = Übersicht(en) geladen, aber KEIN passender Link (Leerbefund)."""
    get_overview_fn = get_overview_fn or _default_get_overview
    any_ok = False
    seen = {}
    last_err = None
    for ov in _FTD_OVERVIEWS:
        st, html, err = get_overview_fn(ov)
        if err or st != 200 or not html:
            last_err = err or f"HTTP {st}"
            log.info("[ftd] Übersicht FETCH-FAIL %s → %s", ov, last_err)
            continue
        any_ok = True
        for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
            if _FTD_FILE_RE.search(href):
                url = href if href.startswith("http") else urljoin(ov, href)
                seen[_FTD_FILE_RE.search(href).group(0).lower()] = url
    if not any_ok:
        return None, None, last_err or "all_overviews_failed"   # FETCH-FAIL
    if not seen:
        return None, None, None                                  # LEER (geladen, 0 Links)
    newest_name = max(seen, key=_file_sort_key)
    return seen[newest_name], newest_name, None


# ── Parsing ───────────────────────────────────────────────────────────────────
def _ftd_num(raw):
    """Roh-Zahl ODER ``None`` (0-vs-null-Grenze, analog options_oi ``_opt_num``).
    ``bool``/``None``/``NaN``/``±Inf``/nicht-numerisch → ``None`` (unbeobachtbar,
    NIEMALS 0). Ein ECHTES 0 bleibt 0. String-Zahlen werden geparst."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if math.isfinite(raw) else None
    if isinstance(raw, str):
        s = raw.strip().replace(",", "")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _iso_settlement(raw):
    """SEC-``SETTLEMENT DATE`` (``YYYYMMDD``) → ISO ``YYYY-MM-DD``. ``None`` bei
    unparsebar (dann wird die Zeile übersprungen — ohne gültiges Settlement-Datum
    kein Idempotenz-Key)."""
    s = (raw or "").strip()
    if len(s) == 8 and s.isdigit():
        y, m, d = s[:4], s[4:6], s[6:8]
        try:
            datetime(int(y), int(m), int(d))
            return f"{y}-{m}-{d}"
        except ValueError:
            return None
    return None


def parse_ftd_zip(zip_bytes, universe):
    """Entpackt das SEC-ZIP und extrahiert NUR die Zeilen der ``universe``-Ticker.

    ``(rows, header, error)``. ``rows`` = Liste ``{symbol, settlement_date, fails,
    price}`` (nur universe-Ticker mit gültigem Settlement-Datum). ``error`` gesetzt
    = Entpack-/Lesefehler (FETCH-FAIL-Klasse). ``rows=[], error=None`` = geladen,
    aber 0 verwertbare Zeilen (Leerbefund). Pipe-delimited, Spalten per Header-
    Name (byte-positions-unabhängig)."""
    uni = {(t or "").strip().upper() for t in (universe or []) if t}
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        inner = zf.namelist()[0]
        txt = zf.read(inner).decode("latin-1", "replace")
    except Exception as e:
        return None, None, f"unzip_failed {type(e).__name__}: {e}"
    lines = [ln for ln in txt.splitlines() if ln.strip()]
    if not lines:
        return [], None, None                     # LEER
    header = lines[0]
    cols = [c.strip().upper() for c in header.split("|")]
    def _idx(name, default):
        return cols.index(name) if name in cols else default
    i_date = _idx("SETTLEMENT DATE", 0)
    i_sym = _idx("SYMBOL", 2)
    i_fails = _idx("QUANTITY (FAILS)", 3)
    i_price = _idx("PRICE", 5)
    rows = []
    for ln in lines[1:]:
        parts = ln.split("|")
        if len(parts) <= i_sym:
            continue
        sym = parts[i_sym].strip().upper()
        if sym not in uni:
            continue
        sett = _iso_settlement(parts[i_date] if len(parts) > i_date else "")
        if sett is None:
            continue                              # ohne Settlement-Datum kein Key
        fails = _ftd_num(parts[i_fails]) if len(parts) > i_fails else None
        price = _ftd_num(parts[i_price]) if len(parts) > i_price else None
        rows.append({"symbol": sym, "settlement_date": sett,
                     "fails": int(fails) if fails is not None else None,
                     "price": price})
    return rows, header, None


# ── Persistenz (eigene Datei, atomar, KEIN Prune) ─────────────────────────────
def _load_history(path=None):
    """Lädt ``ftd_history.json`` (fail-soft → leeres Dict)."""
    p = path or FTD_HISTORY_FILE
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_history(hist, path=None):
    """Atomarer Write — BEWUSST OHNE JEDEN PRUNE (Lehre #519). Nur Nicht-Listen/
    Nicht-Dicts droppen + je Ticker nach ``settlement_date`` sortieren. KEIN
    ``[-N:]``-Slice, KEIN ``timedelta``/Cutoff, KEIN ``MAX_POINTS``. Kompakt
    (byte-Optimierung, kein Cap). ``.tmp`` + ``os.replace`` → nie halb-geschrieben."""
    p = path or FTD_HISTORY_FILE
    compact = {}
    for ticker, points in hist.items():
        if not isinstance(points, list):
            continue
        kept = [pt for pt in points if isinstance(pt, dict)]
        kept.sort(key=lambda pt: pt.get("settlement_date") or "")
        if kept:
            compact[ticker] = kept
    tmp = f"{p}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(compact, fh, separators=(",", ":"))
    os.replace(tmp, p)


def _load_state(path=None):
    """Lädt den Heartbeat-Sidecar ``ftd_history_state.json`` (fail-soft → {})."""
    p = path or FTD_HISTORY_STATE_FILE
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_state(state, path=None):
    """Atomarer Heartbeat-Write (``.tmp`` + ``os.replace``)."""
    p = path or FTD_HISTORY_STATE_FILE
    tmp = f"{p}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, separators=(",", ":"))
    os.replace(tmp, p)


# ── Orchestrierung ────────────────────────────────────────────────────────────
def collect_and_persist(universe, *, report_date_iso=None, run_phase=None,
                        now_utc=None, get_overview_fn=None, get_bytes_fn=None,
                        time_budget_s=None, hist_path=None, state_path=None):
    """Prüft pro postclose, ob ein NEUES Halbmonats-File da ist, und zieht daraus
    die ``universe``-Ticker-Zeilen forward-only in ``ftd_history.json``.

    NUR postclose. Effizienz: die Übersicht (klein) wird immer geholt; das ZIP nur
    HERUNTERGELADEN, wenn das neueste File noch NICHT ingested ist (Heartbeat-State
    ``last_ingested_file``). Idempotent pro ``(ticker, settlement_date)``. Der
    Heartbeat (``last_run``/``last_result``) wird bei JEDEM postclose-Lauf
    geschrieben — so trennt der Digest „läuft, kein neues File" (normal) von
    „Sammler tot/überfällig".

    ``get_overview_fn``/``get_bytes_fn``/``now_utc``/``time_budget_s`` injizierbar
    (Tests ohne Netzwerk). Returns: Anzahl neu geschriebener Punkte."""
    if not FTD_HISTORY_ENABLED:
        return 0
    if run_phase != "postclose":            # NUR postclose (Task: „bei jedem Lauf")
        return 0
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    t_iso = report_date_iso or now.date().isoformat()
    budget = FTD_TIME_BUDGET_S if time_budget_s is None else time_budget_s
    import time as _time
    t0 = _time.monotonic()

    state = _load_state(state_path)
    state["last_run"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _finish(result, added=0):
        state["last_result"] = result
        try:
            _save_state(state, state_path)
        except Exception as exc:   # pragma: no cover
            log.warning("[ftd] State-Write fehlgeschlagen (fail-soft): %s", exc)
        return added

    # 1) Neuestes File aus der Übersicht (nicht geraten).
    file_url, file_name, err = discover_newest_ftd_file(get_overview_fn)
    if err is not None:
        log.info("[ftd] Discovery FETCH-FAIL: %s", err)
        return _finish("fetch_failed:overview")
    if file_url is None:
        log.info("[ftd] Übersicht geladen, aber kein cnsfails-Link (Leerbefund)")
        return _finish("empty:no_link")

    # 2) Schon ingested? (State-basiert → deckt auch „File gesehen, 0 universe-Zeilen".)
    if state.get("last_ingested_file") == file_name:
        return _finish("no_new_file")

    # 3) Zeitbudget vor dem (teuren) Download.
    if (_time.monotonic() - t0) > budget:
        log.warning("[ftd] Zeitbudget %.0fs vor Download überschritten — Abbruch "
                    "(Daily-Run läuft weiter).", budget)
        return _finish("budget_exceeded")

    get_bytes_fn = get_bytes_fn or _default_get_bytes
    st, body, berr = get_bytes_fn(file_url)
    if berr is not None or st != 200 or not body:
        log.info("[ftd] ZIP FETCH-FAIL %s → %s", file_url, berr or f"HTTP {st}")
        return _finish("fetch_failed:zip")

    rows, header, perr = parse_ftd_zip(body, universe)
    if perr is not None:
        log.info("[ftd] ZIP Parse-Fail: %s", perr)
        return _finish("parse_failed")

    # 4) Forward-only + idempotent (ticker, settlement_date) anhängen.
    hist = _load_history(hist_path)
    added = 0
    for r in (rows or []):
        sym = r["symbol"]
        series = hist.setdefault(sym, [])
        seen_dates = {pt.get("settlement_date") for pt in series if isinstance(pt, dict)}
        if r["settlement_date"] in seen_dates:      # idempotent
            continue
        series.append({
            "settlement_date": r["settlement_date"],   # SEC-Datenstand (rückdatiert)
            "first_available": t_iso,                  # wann WIR es sahen (anti-look-ahead)
            "fails": r["fails"],                       # int | null (null = magnitude unbeobachtbar)
            "price": r["price"],                       # float | null
            "source_file": file_name,
        })
        added += 1
    if added:
        _save_history(hist, hist_path)

    # 5) File als gesehen markieren (auch bei 0 universe-Zeilen → kein Re-Download).
    state["last_ingested_file"] = file_name
    log.info("[ftd] File %s ingested: %d neue Punkte (%d Ticker im Universum, "
             "%d Zeilen im File-Filter)", file_name, added, len(universe or []),
             len(rows or []))
    return _finish(f"ingested:{added}", added)
