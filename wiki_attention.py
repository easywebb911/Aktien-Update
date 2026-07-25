"""Wikipedia-Pageviews Attention-Feed — forward-only S10_OBSERVED-Persistenz.

Sammelt pro postclose-Top-10-Record die Wikipedia-Pageviews des Emittenten als
point-in-time Attention-Proxy (Svoboda „Fuel × Fuse": SI × Attention). Spec:
``docs/attention_wiki_spec.md`` (Single-Source). Machbarkeit belegt durch
Runner-Probe (PR #474).

DISZIPLIN (eingefroren, analog material_8k / entry_past_return_5d):
  • KEIN Score-/Filter-/Push-Effekt. Nur ``backtest_history.json`` +
    ``wiki_ticker_map.json``. Look-Ahead-Konvention: NIEMALS als Score-Feature
    lesen (Grep-Test verankert).
  • ``null`` ≠ ``0`` (hart): substrate=none → alle views/baseline/delta ``null``;
    ``0`` NUR für einen gemessenen Null-View-Tag auf einem gemappten Artikel.
  • Ticker-Recycling-Guard dreistufig bei Auflösung: (1) Wikidata P249+P414
    US-Börse, (2) company_name-Token-Fuzzy, (3) P576-Defunct-Guard. Mapping
    EINMALIG aufgelöst + eingefroren (wiki_ticker_map.json), nie täglich neu.
  • Fail-soft überall: SPARQL/Pageviews unerreichbar / HTTP≠200 / Parse-Fehler
    → betroffenes Feld ``null``, substrate unverändert, GELOGGT, kein Crash.
  • Point-in-time: views_t_minus_1 (T-1, zum postclose final), Baseline bis T-2;
    views_t (Entry-Tag) am T+1 nachgetragen. Kein Look-Ahead.

I/O ist injizierbar (``sparql_fetch`` / ``pageviews_fetch``) → stdlib-only-Tests
ohne Netzwerk (Fixtures aus echten Probe-Responses). Default-I/O importiert
``requests`` LAZY.
"""
from __future__ import annotations

import logging
import re
import statistics
import time
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger(__name__)

# US-Börsen-QIDs (Probe-belegt): NASDAQ, NYSE, NYSE American.
_US_EXCHANGE_QIDS = ("wd:Q82059", "wd:Q13677", "wd:Q11705394")
_SPARQL_URL = "https://query.wikidata.org/sparql"
_PAGEVIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia/all-access/all-agents/{art}/daily/{start}/{end}"
)

# Fallback-Defaults nur falls config fehlt; config.py bleibt Single-Source.
_FALLBACK = {
    "enabled": True,
    "http_timeout": 20,
    "sleep_s": 0.3,          # konservatives Delay (Actions-IP-Rate-Limit über Wochen)
    "run_budget_s": 60.0,
    "baseline_days": 30,
    "baseline_min_n": 10,
    "backfill_window_days": 3,   # T+1-Nachtrag mit kleinem Retry-Fenster
}

# Rechtsform-/Füllwort-Tokens, die beim Firmen-Namen-Fuzzy ignoriert werden.
_STOP_TOKENS = frozenset({
    "inc", "incorporated", "corp", "corporation", "co", "company", "companies",
    "ltd", "limited", "plc", "llc", "lp", "holdings", "holding", "group",
    "sa", "nv", "ag", "se", "the", "class", "common", "stock", "ordinary",
})


def _cfg(name, default):
    try:
        import config
        return getattr(config, name, default)
    except Exception:
        return default


def _default_ua() -> str:
    """Beschreibender User-Agent (Wikimedia-Policy: ohne UA HTTP 403, Probe-
    belegt). Env-Override ``WIKI_USER_AGENT``; Default ist Probe-erprobt (200)."""
    import os
    return os.environ.get(
        "WIKI_USER_AGENT",
        "SqueezeReportAttention/1.0 "
        "(https://github.com/easywebb911/Aktien-Update; easywebb@yahoo.de)",
    )


# ── Default-I/O (lazy requests) ──────────────────────────────────────────────
def _default_sparql_fetch(ticker: str, ua: str, timeout: int):
    """Wikidata SPARQL: P249 (ticker) als Qualifier auf P414 (stock exchange),
    gefiltert auf US-Börsen; +enwiki-Sitelink, +P576 (dissolution). Roh-JSON
    oder None bei HTTP≠200/Fehler."""
    import requests
    import urllib.parse
    q = (
        "SELECT ?item ?itemLabel ?art ?dissolved WHERE {"
        " ?item p:P414 ?st. ?st ps:P414 ?exch; pq:P249 \"%s\"."
        " VALUES ?exch { %s }"
        " OPTIONAL { ?art schema:about ?item; schema:isPartOf <https://en.wikipedia.org/>. }"
        " OPTIONAL { ?item wdt:P576 ?dissolved. }"
        " SERVICE wikibase:label { bd:serviceParam wikibase:language \"en\". }"
        "} LIMIT 5" % (ticker.replace('"', ""), " ".join(_US_EXCHANGE_QIDS))
    )
    url = _SPARQL_URL + "?" + urllib.parse.urlencode({"query": q, "format": "json"})
    try:
        r = requests.get(url, headers={"User-Agent": ua,
                                       "Accept": "application/json"},
                         timeout=timeout)
        if r.status_code != 200:
            log.warning("attention_wiki SPARQL %s → HTTP %s", ticker, r.status_code)
            return None
        return r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("attention_wiki SPARQL %s fail-soft: %s", ticker, exc)
        return None


def _default_pageviews_fetch(title: str, start: str, end: str, ua: str, timeout: int):
    """Wikimedia REST per-article daily, ein Call für die ganze Range. Roh-JSON
    oder None bei HTTP≠200/Fehler."""
    import requests
    import urllib.parse
    art = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = _PAGEVIEWS_URL.format(art=art, start=start, end=end)
    try:
        r = requests.get(url, headers={"User-Agent": ua,
                                       "Accept": "application/json"},
                         timeout=timeout)
        if r.status_code != 200:
            log.warning("attention_wiki pageviews %s → HTTP %s", title, r.status_code)
            return None
        return r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("attention_wiki pageviews %s fail-soft: %s", title, exc)
        return None


# ── Pure Helfer ──────────────────────────────────────────────────────────────
def _norm_tokens(s: str) -> set:
    """Firmenname → Menge signifikanter Tokens (lowercase, ohne Interpunktion,
    ohne Rechtsform-/Füllwörter, Länge ≥ 2). TOKEN-basiert, NICHT Substring —
    damit „Via Renewables" NICHT auf „Viacom" matcht (VIA-Recycling-Fall)."""
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return {t for t in s.split() if len(t) >= 2 and t not in _STOP_TOKENS}


def _issuer_matches(company_name: str, *labels: str) -> bool:
    """True, wenn company_name mind. ein signifikantes Token mit einem der
    Wikidata-Labels/Titel teilt. Token-Gleichheit (nicht Substring): „via" ≠
    „viacom". Konservativ: bei Nicht-Match → REJECT (lieber none als
    Falsch-Firma)."""
    cn = _norm_tokens(company_name)
    if not cn:
        return False
    for lab in labels:
        if cn & _norm_tokens(lab):
            return True
    return False


def _iso_now(now_utc: datetime | None = None) -> str:
    dt = now_utc or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_sparql(raw: dict) -> dict:
    """Roh-SPARQL-JSON → erste Bindung als {qid, label, enwiki_title,
    dissolved}. Leer/kein Treffer → {}."""
    try:
        rows = raw["results"]["bindings"]
    except (TypeError, KeyError):
        return {}
    if not rows:
        return {}
    r = rows[0]
    qid = r.get("item", {}).get("value", "").rsplit("/", 1)[-1] or None
    label = r.get("itemLabel", {}).get("value") or ""
    art_url = r.get("art", {}).get("value") or ""
    title = None
    if art_url:
        import urllib.parse
        title = urllib.parse.unquote(art_url.rsplit("/wiki/", 1)[-1]) or None
    dissolved = r.get("dissolved", {}).get("value") or None
    return {"qid": qid, "label": label, "title": title, "dissolved": dissolved}


def resolve_ticker(ticker: str, company_name: str, *,
                   sparql_fetch=None, ua: str | None = None,
                   timeout: int | None = None,
                   now_utc: datetime | None = None) -> dict:
    """Dreistufiger Guard → eingefrorener Map-Eintrag. PURE gegeben
    ``sparql_fetch`` (injizierbar für Fixtures). Liefert IMMER einen Eintrag
    (nie raise); bei Ablehnung substrate=none + reason."""
    ua = ua or _default_ua()
    timeout = timeout if timeout is not None else _cfg("WIKI_ATTENTION_HTTP_TIMEOUT",
                                                       _FALLBACK["http_timeout"])
    fetch = sparql_fetch or (lambda tk: _default_sparql_fetch(tk, ua, timeout))
    base = {"qid": None, "title": None, "resolved_at": _iso_now(now_utc),
            "issuer_verified": False,
            "company_name_at_resolve": company_name or None,
            "substrate": "none", "reason": None}
    raw = fetch(ticker)
    if raw is None:
        base["reason"] = "sparql_fetch_failed"
        return base
    parsed = _parse_sparql(raw)
    if not parsed or not parsed.get("qid"):
        base["reason"] = "no_p249"
        return base
    # (3) Defunct-Guard: aufgelöste/dissolvierte Entität → REJECT.
    if parsed.get("dissolved"):
        base.update(qid=None, title=None, reason="defunct")
        return base
    # (2) Firmen-Namen-Plausibilisierung (Ticker-Recycling-Guard, VIA-Fall).
    if not _issuer_matches(company_name, parsed.get("label", ""),
                           parsed.get("title") or ""):
        base["reason"] = "issuer_mismatch"
        return base
    # enwiki-Artikel nötig, sonst nicht für Pageviews nutzbar.
    if not parsed.get("title"):
        base.update(qid=parsed["qid"], reason="no_article")
        return base
    return {"qid": parsed["qid"], "title": parsed["title"],
            "resolved_at": _iso_now(now_utc), "issuer_verified": True,
            "company_name_at_resolve": company_name or None,
            "substrate": "en", "reason": None}


def _empty_record(entry: dict) -> dict:
    """attention_wiki-Record bei substrate=none ODER Fetch-Fail: substrate +
    Anker gesetzt, ALLE views/baseline/delta ``null`` (NIE 0)."""
    return {
        "substrate": entry.get("substrate", "none"),
        "article_qid": entry.get("qid"),
        "article_title": entry.get("title"),
        "views_t_minus_1": None, "views_t": None, "views_t_backfilled_at": None,
        "baseline_30d_median": None, "baseline_30d_n": None, "delta_ratio": None,
    }


def _pv_rows(raw: dict) -> dict:
    """Roh-Pageviews-JSON → {YYYYMMDD: views}. Fehler → {}."""
    try:
        return {it["timestamp"][:8]: int(it["views"]) for it in raw.get("items", [])}
    except (TypeError, KeyError, ValueError):
        return {}


def build_attention_record(entry: dict, today: date, *,
                           pageviews_fetch=None, ua: str | None = None,
                           timeout: int | None = None) -> dict:
    """T-1-Views + 30d-Baseline (bis T-2) + abgeleitetes delta_ratio. ``entry``
    = eingefrorener Map-Eintrag. substrate=none → _empty_record (alle null).
    Fetch-Fail → substrate bleibt en, views null (retrybar)."""
    if entry.get("substrate") != "en" or not entry.get("title"):
        return _empty_record(entry)
    ua = ua or _default_ua()
    timeout = timeout if timeout is not None else _cfg("WIKI_ATTENTION_HTTP_TIMEOUT",
                                                       _FALLBACK["http_timeout"])
    baseline_days = _cfg("WIKI_ATTENTION_BASELINE_DAYS", _FALLBACK["baseline_days"])
    baseline_min_n = _cfg("WIKI_ATTENTION_BASELINE_MIN_N", _FALLBACK["baseline_min_n"])
    fetch = pageviews_fetch or (lambda t, s, e: _default_pageviews_fetch(t, s, e, ua, timeout))
    rec = _empty_record(entry)
    t1 = today - timedelta(days=1)
    start = (t1 - timedelta(days=baseline_days)).strftime("%Y%m%d")
    end = t1.strftime("%Y%m%d")
    raw = fetch(entry["title"], start, end)
    if raw is None:
        return rec  # Fetch-Fail: substrate=en bleibt, views null → nächster Tick retried
    by_day = _pv_rows(raw)
    t1_str = t1.strftime("%Y%m%d")
    # views_t_minus_1: gemessener Wert (0 ist gültig!), null NUR wenn Tag fehlt.
    rec["views_t_minus_1"] = by_day.get(t1_str)
    # Baseline: strikt VOR T-1 (bis T-2), damit T-1 die eigene Baseline nicht
    # kontaminiert.
    base_vals = [v for d, v in by_day.items() if d < t1_str]
    rec["baseline_30d_n"] = len(base_vals)
    if len(base_vals) >= baseline_min_n:
        rec["baseline_30d_median"] = round(float(statistics.median(base_vals)), 2)
    # delta_ratio (abgeleitet): null wenn Input null oder Baseline 0.
    v1, med = rec["views_t_minus_1"], rec["baseline_30d_median"]
    if v1 is not None and med:
        rec["delta_ratio"] = round(v1 / med, 4)
    return rec


# ── Orchestrierung (Prefetch, einmalige Auflösung + T-1-Sammlung) ────────────
def collect_attention_wiki(tickers: list[str], company_names: dict, *,
                           now_utc: datetime | None = None,
                           ticker_map: dict | None = None,
                           sparql_fetch=None, pageviews_fetch=None) -> tuple[dict, dict]:
    """Löst fehlende Ticker EINMALIG auf (eingefroren in ``ticker_map``), sammelt
    T-1-Views je gemapptem Ticker. Liefert ({ticker: attention_wiki_record},
    aktualisierte ticker_map). Fail-soft je Ticker + Run-Budget; ``ticker_map``
    wird in-place erweitert (Caller persistiert)."""
    tmap = ticker_map if ticker_map is not None else {}
    out: dict = {}
    _now = now_utc or datetime.now(timezone.utc)
    if _now.tzinfo is None:
        _now = _now.replace(tzinfo=timezone.utc)
    today = _now.astimezone(timezone.utc).date()
    sleep_s = _cfg("WIKI_ATTENTION_SLEEP_S", _FALLBACK["sleep_s"])
    budget_s = _cfg("WIKI_ATTENTION_RUN_BUDGET_S", _FALLBACK["run_budget_s"])
    deadline = time.monotonic() + budget_s
    for tk in tickers:
        if time.monotonic() > deadline:
            log.warning("attention_wiki: Run-Budget erschöpft, skip ab %s", tk)
            break
        try:
            if tk not in tmap:
                # Auflösung EINMALIG + eingefroren (auch none bleibt eingefroren,
                # Spec §7: Re-Resolution nur als explizite Populations-Entscheidung).
                tmap[tk] = resolve_ticker(tk, company_names.get(tk, tk),
                                          sparql_fetch=sparql_fetch, now_utc=_now)
                time.sleep(sleep_s)
            rec = build_attention_record(tmap[tk], today,
                                         pageviews_fetch=pageviews_fetch)
            if tmap[tk].get("substrate") == "en":
                time.sleep(sleep_s)
            out[tk] = rec
            _log_collect(tk, tmap[tk], rec)
        except Exception as exc:  # noqa: BLE001
            log.warning("attention_wiki %s unerwarteter Fehler (fail-soft): %s", tk, exc)
            out[tk] = _empty_record(tmap.get(tk, {"substrate": "none"}))
    return out, tmap


def backfill_views_t(record: dict, entry_day: date, *,
                     pageviews_fetch=None, ua: str | None = None,
                     timeout: int | None = None,
                     now_utc: datetime | None = None) -> bool:
    """T+1-Nachtrag: setzt ``views_t`` (Pageviews des Entry-Tags T) auf einem
    bestehenden Record. IDEMPOTENT: tut nichts, wenn ``views_t`` bereits gesetzt
    (nicht-None). substrate≠en → no-op. Liefert True, wenn geschrieben."""
    if not isinstance(record, dict) or record.get("substrate") != "en":
        return False
    if record.get("views_t") is not None:
        return False  # idempotent — bereits nachgetragen
    if not record.get("article_title"):
        return False
    ua = ua or _default_ua()
    timeout = timeout if timeout is not None else _cfg("WIKI_ATTENTION_HTTP_TIMEOUT",
                                                       _FALLBACK["http_timeout"])
    fetch = pageviews_fetch or (lambda t, s, e: _default_pageviews_fetch(t, s, e, ua, timeout))
    d = entry_day.strftime("%Y%m%d")
    raw = fetch(record["article_title"], d, d)
    if raw is None:
        return False  # Fetch-Fail → views_t bleibt null, nächster Lauf retried
    by_day = _pv_rows(raw)
    if d not in by_day:
        return False  # Tag noch nicht final → retry im Fenster
    record["views_t"] = by_day[d]  # gemessen (0 gültig)
    record["views_t_backfilled_at"] = _iso_now(now_utc)
    return True


def _log_collect(tk: str, entry: dict, rec: dict) -> None:
    sub = entry.get("substrate")
    if sub == "en":
        log.info("[attention_wiki] SENT %s: %s v_t-1=%s baseline=%s(n=%s) delta=%s",
                 tk, entry.get("title"), rec.get("views_t_minus_1"),
                 rec.get("baseline_30d_median"), rec.get("baseline_30d_n"),
                 rec.get("delta_ratio"))
    else:
        log.info("[attention_wiki] SKIP %s: substrate=none (%s)", tk, entry.get("reason"))
