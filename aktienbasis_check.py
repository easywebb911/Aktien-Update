"""Datenprüfung Aktienbasis / Short Float (Easy-Entscheid 17.11.2026, PR C).

ZWECK: Fälle wie FGL 16.11.2026 sichtbar machen — Yahoo lieferte eine
Marktkapitalisierung auf veralteter Aktienbasis (77.069 $ < Float × Kurs) und
einen Short Float von 38,9 %, während der FINRA-Bestand (consolidatedShortInterest,
Stichtag 30.10.2026: 28.526 Aktien) gegen den Float 609.806 nur 4,7 % ergibt.

REINE KENNZEICHEN + ROHWERTE. Dieses Modul ändert NICHTS an score(),
Conviction, Filter, Auswahl oder Reihenfolge. Konsumenten: Karte (Warnhinweis),
Risiko-Text (keine Marktkap als Tatsache bei Kennzeichen a), Backtest-Feld
``aktienbasis_pruefung`` (forward-only, S10_OBSERVED), Digest-Zeile.

Zwei Kennzeichen je Kandidat:
  (a) Aktienbasis widersprüchlich: Marktkapitalisierung <
      AKTIENBASIS_MCAP_FLOAT_FACTOR (0,9) × Float × Kurs.
  (b) Short Float weicht vom FINRA-Bestand ab: FINRA-Bestand des letzten
      veröffentlichten Stichtags / Float weicht um mehr als
      SHORT_FLOAT_FINRA_ABWEICHUNG_FAKTOR (2) vom verwendeten Short Float ab.

ZEITLICH SAUBER: verwendet wird nur der jüngste Stichtag, dessen
Veröffentlichung nach der Repo-Regel (``scripts/business_days.
finra_publication_date``, 7 US-Handelstage nach Stichtag) am Berichtstag D
oder davor liegt. Yahoo-Werte sind die des Laufs (Stand zum Laufzeitpunkt).

FINRA-Abruf: POST api.finra.org consolidatedShortInterest, Filter symbolCode,
ohne Zugangsdaten. Zeitlimit je Abruf + Gesamtbudget, Zwischenspeicher
``finra_si_cache.json`` (TTL 20 h, im Daily-Workflow committet). Ausfall,
Rate-Limit (kein Retry) oder unbekannter Ticker → Kennzeichen
„nicht_pruefbar“ mit Grund, nie Abbruch des Laufs.

Determinismus: ``evaluate`` ist pure (gleiche Eingaben → gleiches Dict).
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import date, datetime, timedelta, timezone

from config import (
    AKTIENBASIS_MCAP_FLOAT_FACTOR,
    FINRA_CSI_BUDGET_S,
    FINRA_CSI_CACHE_FILE,
    FINRA_CSI_CACHE_PRUNE_DAYS,
    FINRA_CSI_CACHE_TTL_H,
    FINRA_CSI_ENABLED,
    FINRA_CSI_TIMEOUT_S,
    FINRA_CSI_URL,
    SHORT_FLOAT_FINRA_ABWEICHUNG_FAKTOR,
    SHORT_FLOAT_FINRA_MIN_PCT,
)

FIELD = "aktienbasis_pruefung"   # Backtest-Feldname (eine Stelle)
_N_RECORDS = 6                   # jüngste Stichtage je Ticker im Cache

# Feldnamen-Kandidaten (aus der Probe Rückrechnung, Lauf 43606294489).
_F_SYMBOL = ("symbolCode", "issueSymbolIdentifier", "symbol")
_F_DATE = ("settlementDate",)
_F_QTY = ("currentShortPositionQuantity", "currentShortShareNumber")
_F_SPLIT = ("stockSplitFlag",)
_F_REV = ("revisionFlag",)


def _pick(rec: dict, keys):
    for k in keys:
        if k in rec:
            return rec[k]
    return None


def _num(x):
    """Endliche, positive Zahl oder None (None/NaN/Inf/bool/≤0 → None)."""
    if isinstance(x, bool) or x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or v <= 0:
        return None
    return v


def _num0(x):
    """Wie _num, aber 0 ist erlaubt (FINRA-Bestand 0 ist ein gültiger Wert)."""
    if isinstance(x, bool) or x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or v < 0:
        return None
    return v


def normalize_records(raw) -> list[dict] | None:
    """FINRA-Antwort → ``[{settlement_date, bestand, split, revision}]``,
    jüngster Stichtag zuerst. None bei unlesbarer Antwort."""
    if not isinstance(raw, list):
        return None
    out: dict[str, dict] = {}
    for r in raw:
        if not isinstance(r, dict):
            continue
        sd = str(_pick(r, _F_DATE) or "")[:10]
        try:
            date.fromisoformat(sd)
        except ValueError:
            continue
        qty = _num0(_pick(r, _F_QTY))
        split = _pick(r, _F_SPLIT)
        rev = _pick(r, _F_REV)
        out[sd] = {"settlement_date": sd,
                   "bestand": int(qty) if qty is not None else None,
                   "split": (str(split).strip() or None) if split not in (None, "") else None,
                   "revision": (str(rev).strip() or None) if rev not in (None, "") else None}
    return sorted(out.values(), key=lambda x: x["settlement_date"], reverse=True)[:_N_RECORDS]


def fetch_finra(symbol: str, *, post_fn=None, timeout: float = FINRA_CSI_TIMEOUT_S):
    """Ein Abruf. Rückgabe ``(status, records)``: ``("ok", [...])``,
    ``("rate_limit", None)``, ``("fehler", None)``. Raise nie. Kein Retry."""
    if post_fn is None:
        import requests
        post_fn = requests.post
    payload = {
        "limit": _N_RECORDS,
        "compareFilters": [{"fieldName": "symbolCode", "compareType": "EQUAL",
                            "fieldValue": symbol.strip().upper()}],
        "sortFields": ["-settlementDate"],
    }
    try:
        r = post_fn(FINRA_CSI_URL, json=payload, timeout=timeout,
                    headers={"Content-Type": "application/json",
                             "Accept": "application/json"})
    except Exception:
        return "fehler", None
    code = getattr(r, "status_code", None)
    if code == 429:
        return "rate_limit", None
    if code == 204:
        return "ok", []
    if code != 200:
        return "fehler", None
    try:
        raw = r.json() if (getattr(r, "text", "") or "").strip() else []
    except Exception:
        return "fehler", None
    recs = normalize_records(raw)
    if recs is None:
        return "fehler", None
    return "ok", recs


def load_cache(path=FINRA_CSI_CACHE_FILE) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        if isinstance(d, dict) and isinstance(d.get("tickers"), dict):
            return d
    except Exception:
        pass
    return {"schema_v": 1, "tickers": {}}


def save_cache(cache: dict, path=FINRA_CSI_CACHE_FILE, *, now_utc: datetime) -> None:
    """Atomar schreiben; Einträge ohne Abruf seit FINRA_CSI_CACHE_PRUNE_DAYS fallen raus."""
    cutoff = now_utc - timedelta(days=FINRA_CSI_CACHE_PRUNE_DAYS)
    keep = {}
    for sym, e in sorted((cache.get("tickers") or {}).items()):
        try:
            ts = datetime.fromisoformat(e["abgerufen_utc"])
        except Exception:
            continue
        if ts >= cutoff:
            keep[sym] = e
    out = {"schema_v": 1, "tickers": keep}
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def get_records(symbols, *, now_utc: datetime, cache: dict, post_fn=None,
                budget_s: float = FINRA_CSI_BUDGET_S, clock=time.monotonic) -> dict:
    """``{SYM: {"status", "records", "quelle", "abgerufen_utc"}}`` für alle
    Symbole. Cache-Treffer (jünger als TTL) ohne Abruf; sonst ein Abruf je
    Symbol, bis Budget oder Rate-Limit erreicht ist (Rest: ``nicht_abgerufen``
    bzw. ``rate_limit``). Mutiert ``cache`` bei erfolgreichen Abrufen."""
    out: dict[str, dict] = {}
    tickers = cache.setdefault("tickers", {})
    t0 = clock()
    stop = None
    for sym in sorted({s.strip().upper() for s in symbols if s}):
        ent = tickers.get(sym)
        if isinstance(ent, dict):
            try:
                age_h = (now_utc - datetime.fromisoformat(ent["abgerufen_utc"])).total_seconds() / 3600
            except Exception:
                age_h = None
            if age_h is not None and 0 <= age_h < FINRA_CSI_CACHE_TTL_H:
                out[sym] = {"status": "ok", "records": ent.get("records") or [],
                            "quelle": "cache", "abgerufen_utc": ent["abgerufen_utc"]}
                continue
        if not FINRA_CSI_ENABLED:
            out[sym] = {"status": "aus", "records": None, "quelle": None, "abgerufen_utc": None}
            continue
        if stop is None and clock() - t0 > budget_s:
            stop = "zeitlimit"
        if stop:
            out[sym] = {"status": stop, "records": None, "quelle": None, "abgerufen_utc": None}
            continue
        status, recs = fetch_finra(sym, post_fn=post_fn)
        if status == "ok":
            iso = now_utc.isoformat(timespec="seconds")
            tickers[sym] = {"abgerufen_utc": iso, "records": recs}
            out[sym] = {"status": "ok", "records": recs, "quelle": "api", "abgerufen_utc": iso}
        else:
            if status == "rate_limit":
                stop = "rate_limit"
            out[sym] = {"status": status, "records": None, "quelle": None, "abgerufen_utc": None}
    return out


def select_known(records, report_day: date):
    """Jüngster Stichtag mit Veröffentlichung ≤ D (Repo-Regel). (record, pub) oder (None, None)."""
    from scripts.business_days import finra_publication_date
    for rec in records or []:
        try:
            sd = date.fromisoformat(rec["settlement_date"])
        except Exception:
            continue
        pub = finra_publication_date(sd)
        if pub <= report_day:
            return rec, pub
    return None, None


def evaluate(s: dict, finra: dict | None, report_day: date) -> dict:
    """Pure. Kennzeichen + Rohwerte für einen Kandidaten."""
    cap = _num(s.get("yf_market_cap")) or _num(s.get("market_cap"))
    flt = _num(s.get("float_shares"))
    shares = _num(s.get("shares_outstanding"))
    price = _num(s.get("price"))
    # Short Float 0 / ohne Quelle („none“) gilt als fehlend, nicht als echter
    # Wert — sonst Fehlalarm bei Watchlist-Tickern ohne Short-Daten (Guardian #735).
    sf_used = (None if s.get("short_float_source") == "none"
               else _num(s.get("short_float")))
    res = {
        "marktkap": cap, "float_aktien": int(flt) if flt else None,
        "aktienzahl": int(shares) if shares else None, "kurs": price,
        "short_float_verwendet": round(sf_used, 2) if sf_used is not None else None,
        "short_float_quelle": s.get("short_float_source"),
        "finra_bestand": None, "finra_stichtag": None, "finra_veroeffentlicht": None,
        "finra_split": None, "finra_split_kuerzlich": None, "finra_short_float": None,
        "finra_quelle": None, "finra_abgerufen_utc": None,
        "aktienbasis": "nicht_pruefbar", "aktienbasis_grund": None,
        "short_float_pruefung": "nicht_pruefbar", "short_float_grund": None,
    }
    # (a) Aktienbasis
    if cap is None:
        res["aktienbasis_grund"] = "marktkap_fehlt"
    elif flt is None:
        res["aktienbasis_grund"] = "float_fehlt"
    elif price is None:
        res["aktienbasis_grund"] = "kurs_fehlt"
    else:
        res["aktienbasis"] = ("widerspruechlich"
                              if cap < AKTIENBASIS_MCAP_FLOAT_FACTOR * flt * price else "ok")
    # (b) Short Float gegen FINRA-Bestand
    f = finra or {}
    res["finra_quelle"] = f.get("quelle")
    res["finra_abgerufen_utc"] = f.get("abgerufen_utc")
    status = f.get("status")
    if status != "ok":
        res["short_float_grund"] = f"finra_{status or 'nicht_abgerufen'}"
        return res
    recs = f.get("records") or []
    if not recs:
        res["short_float_grund"] = "finra_kennt_ticker_nicht"
        return res
    rec, pub = select_known(recs, report_day)
    if rec is None:
        res["short_float_grund"] = "kein_veroeffentlichter_stichtag"
        return res
    res["finra_stichtag"] = rec["settlement_date"]
    res["finra_veroeffentlicht"] = pub.isoformat()
    res["finra_split"] = rec.get("split")
    known = [r for r in recs if r["settlement_date"] <= rec["settlement_date"]][:3]
    res["finra_split_kuerzlich"] = any(r.get("split") for r in known)
    qty = rec.get("bestand")
    res["finra_bestand"] = qty
    if qty is None:
        res["short_float_grund"] = "finra_bestand_fehlt"
        return res
    if flt is None:
        res["short_float_grund"] = "float_fehlt"
        return res
    fsf = qty / flt * 100.0
    res["finra_short_float"] = round(fsf, 2)
    if sf_used is None:
        res["short_float_grund"] = "short_float_fehlt"
        return res
    hi, lo = max(sf_used, fsf), min(sf_used, fsf)
    if hi < SHORT_FLOAT_FINRA_MIN_PCT:
        res["short_float_pruefung"] = "ok"
    elif lo <= 0 or hi / lo > SHORT_FLOAT_FINRA_ABWEICHUNG_FAKTOR:
        res["short_float_pruefung"] = "abweichend"
    else:
        res["short_float_pruefung"] = "ok"
    return res


def is_auffaellig(res: dict | None) -> bool:
    return isinstance(res, dict) and (
        res.get("aktienbasis") == "widerspruechlich"
        or res.get("short_float_pruefung") == "abweichend")


def _de_pct(v: float) -> str:
    """Anzeige-Rundung (festgelegt): eine Nachkommastelle, Komma, geschütztes Leerzeichen."""
    return f"{v:.1f}".replace(".", ",") + " %"


def _de_int(v) -> str:
    return f"{int(round(v)):,}".replace(",", ".")


def _de_date(iso: str | None) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except Exception:
        return "?"


def warning_text(res: dict | None) -> str:
    """Ein Satz für Karte/Tooltip, leer wenn nicht auffällig. Deterministisch."""
    if not is_auffaellig(res):
        return ""
    parts = []
    if res.get("short_float_pruefung") == "abweichend" and res.get("finra_short_float") is not None:
        t = (f"Short Float zweifelhaft — FINRA-Bestand ergibt {_de_pct(res['finra_short_float'])}"
             f" ({_de_int(res['finra_bestand'])} Aktien, Stichtag {_de_date(res['finra_stichtag'])})")
        if res.get("finra_split_kuerzlich"):
            t += ", FINRA meldet eine Zusammenlegung oder Teilung der Aktien"
        parts.append(t)
    if res.get("aktienbasis") == "widerspruechlich":
        parts.append("Aktienbasis widersprüchlich — Marktkapitalisierung kleiner als Float × Kurs")
    return "; ".join(parts) + "."


def log_line(results: dict) -> str:
    n = len(results)
    auff = sorted(t for t, r in results.items() if is_auffaellig(r))
    np_a = sum(1 for r in results.values() if r.get("aktienbasis") == "nicht_pruefbar")
    np_b = sum(1 for r in results.values() if r.get("short_float_pruefung") == "nicht_pruefbar")
    return (f"[aktienbasis] {n} geprüft: auffällig {len(auff)} ({', '.join(auff) or '—'}) · "
            f"nicht prüfbar Aktienbasis {np_a}, Short Float {np_b}")


def digest_line(bh_path) -> str:
    """Digest-Hinweis (warn-Charakter, kein crit) aus dem jüngsten Postclose-Tag,
    dessen Einträge das Feld tragen. Raise nie."""
    try:
        try:
            with open(bh_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return "🔎 Datenprüfung Short Float: Datei fehlt"
        rows = [e for e in (data if isinstance(data, list) else [])
                if isinstance(e, dict) and isinstance(e.get(FIELD), dict)
                and not e.get("bootstrap")]
        if not rows:
            return "🔎 Datenprüfung Short Float: sammelt ab dem nächsten Postclose (noch kein Eintrag)"

        def _k(e):
            try:
                d, m, y = str(e.get("date", "")).split(".")
                return (int(y), int(m), int(d))
            except Exception:
                return (0, 0, 0)
        last = max(_k(e) for e in rows)
        day = [e for e in rows if _k(e) == last]
        auff = sorted(str(e.get("ticker")) for e in day if is_auffaellig(e[FIELD]))
        n_np = sum(1 for e in day if e[FIELD].get("short_float_pruefung") == "nicht_pruefbar")
        icon = "🟡" if auff else "🔎"
        txt = (f"{icon} Datenprüfung Short Float ({last[2]:02d}.{last[1]:02d}.): "
               f"{len(auff)} von {len(day)} auffällig")
        if auff:
            txt += f" ({', '.join(auff)})"
        if n_np:
            txt += f" · FINRA nicht prüfbar {n_np}"
        return txt
    except Exception:
        return "🔎 Datenprüfung Short Float: Status nicht ermittelbar"


def run(stocks, *, report_day: date, now_utc: datetime | None = None, post_fn=None,
        cache_path=FINRA_CSI_CACHE_FILE, write_cache: bool = True) -> dict:
    """Prüft alle übergebenen Stock-Dicts, setzt ``s[FIELD]``. Raise nie."""
    now_utc = now_utc or datetime.now(timezone.utc)
    results: dict[str, dict] = {}
    try:
        syms = [s.get("ticker") for s in stocks if s.get("ticker")]
        cache = load_cache(cache_path)
        finra = get_records(syms, now_utc=now_utc, cache=cache, post_fn=post_fn)
        for s in stocks:
            t = s.get("ticker")
            if not t:
                continue
            res = evaluate(s, finra.get(t.strip().upper()), report_day)
            s[FIELD] = res
            results[t] = res
        if write_cache:
            try:
                save_cache(cache, cache_path, now_utc=now_utc)
            except Exception as exc:  # Cache-Schreibfehler: nur Log, kein Abbruch
                print(f"[aktienbasis] Cache nicht geschrieben: {exc!r}", flush=True)
    except Exception as exc:
        print(f"[aktienbasis] Prüfung übersprungen: {exc!r}", flush=True)
    return results
