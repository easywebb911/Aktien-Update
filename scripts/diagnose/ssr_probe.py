#!/usr/bin/env python3
"""Read-only Machbarkeits-Probe: SSR-Flag (Reg-SHO Rule 201) — v2 Discovery-Follower.

Runde 1 (v1) hat gezeigt: das bequeme NasdaqTrader-`nasdaqth<date>.txt` ist die
Rule-203-THRESHOLD/FTD-Liste (Header „Reg SHO Threshold Flag", 0 Overlap mit
unserem Squeeze-Universum) — NICHT der Rule-201-SSR-CIRCUIT-BREAKER (−10%-Trigger).
ABER: die NasdaqTrader-RegSHO-Seite enthält einen Anchor-Text „short sale circuit
breakers" (ein .aspx-Nav-Link, den die v1-Regex — nur .csv/.txt/.json/.xls —
verpasst hat). v2 FOLGT diesem Lead.

Läuft AUSSCHLIESSLICH auf dem GitHub-Actions-Runner (unrestricted egress) — die
interaktive Sandbox ist egress-deny-all. Keyless, KEINE Secrets, KEINE Repo-Writes.

Kern-Härtung ggü. v1: NasdaqTrader liefert HTTP 200 + HTML-App-Shell für JEDE
nicht-existente URL/Datum → „200" ist KEIN Existenz-Beweis. `_is_flat_file`
verlangt echtes Delimiter-Textfile (kein <!DOCTYPE/<html>).
"""
import json
import re
import sys
import time
import datetime as dt
import urllib.parse
import urllib.request
import urllib.error

UA = ("SqueezeReportSSRProbe/2.0 "
      "(https://github.com/easywebb911/Aktien-Update; easywebb@yahoo.de)")

# Einstiegs-Seiten, deren Anchors nach „short sale circuit breaker" durchsucht
# und dann VERFOLGT werden (Discovery-Follow statt URL-Raten).
ENTRY_PAGES = [
    ("nasdaqtrader_regsho",      "https://www.nasdaqtrader.com/Trader.aspx?id=RegSHOThreshold"),
    ("nasdaqtrader_ssrcb_guess", "https://www.nasdaqtrader.com/Trader.aspx?id=ShortSaleCircuitBreaker"),
    ("nasdaqtrader_dp_index",    "https://www.nasdaqtrader.com/Trader.aspx?id=DataProducts"),
    ("cboe_mktstats",            "https://www.cboe.com/us/equities/market_statistics/"),
    ("cboe_reg",                 "https://www.cboe.com/us/equities/regulation/"),
    ("nyse_regulation",          "https://www.nyse.com/regulation"),
    ("nyse_trade_info",          "https://www.nyse.com/markets/nyse/trading-info"),
]

# Zusätzliche direkte SSR-Flat-File-Kandidaten (falls Discovery leer bleibt).
DIRECT_SSR = [
    ("nasdaq_ssrcb_txt",  "https://www.nasdaqtrader.com/dynamic/symdir/shortsalecircuitbreaker/ShortSaleCircuitBreaker{d}.txt"),
    ("nasdaq_ssrcb_txt2", "https://www.nasdaqtrader.com/dynamic/symdir/ShortSaleCircuitBreaker/ssrcb{d}.txt"),
    ("cboe_ssr_bzx",      "https://www.cboe.com/us/equities/market_statistics/circuit_breaker/BZX/csv/"),
    ("cboe_ssr_daily",    "https://www.cboe.com/us/equities/market_statistics/circuit_breaker/"),
]

_SSR_KW = ("circuit breaker", "short sale", "shortsale", "short-sale", "ssr", "rule 201")
_A_RE = re.compile(r'<a\b[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
_LINK_DATA_RE = re.compile(r'''["']([^"']+?\.(?:csv|txt|json))(?:\?[^"']*)?["']''', re.I)
_TICKER_RE = re.compile(r'[A-Z][A-Z0-9.\-]{0,5}')


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read(800_000), time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, dict(getattr(e, "headers", {}) or {}), b"", time.time() - t0
    except Exception as e:
        return f"ERR:{type(e).__name__}:{str(e)[:80]}", {}, b"", time.time() - t0


def _txt(body):
    try:
        return body.decode("utf-8", "replace")
    except Exception:
        return ""


def _is_flat_file(headers, body):
    """Echtes Daten-Flat-File (kein HTML-App-Shell). v1-Falle: NasdaqTrader gibt
    200+HTML für jede tote URL."""
    if not body or len(body) < 15:
        return False
    head = body[:400].lstrip().lower()
    if head.startswith(b"<!doctype") or b"<html" in head or b"<head" in head:
        return False
    ct = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
    sample = _txt(body[:400])
    return ("text/plain" in ct or "csv" in ct or "json" in ct
            or "|" in sample or ("," in sample and "\n" in sample))


def _first_lines(body, n=8):
    return "\n".join(_txt(body).splitlines()[:n])


def _extract_tickers(body):
    txt = _txt(body)
    toks = set()
    for line in txt.splitlines()[1:]:
        parts = re.split(r'[|,;\t]', line.strip())
        if parts and parts[0]:
            c = parts[0].strip().upper()
            if _TICKER_RE.fullmatch(c):
                toks.add(c)
    return toks


def _ssr_anchors(html):
    out = []
    for href, text in _A_RE.findall(html):
        t = re.sub(r'<[^>]+>', '', text).strip()
        low = (t + " " + href).lower()
        if any(k in low for k in _SSR_KW):
            out.append((href, t))
    # dedup, Reihenfolge stabil
    seen, uniq = set(), []
    for h, t in out:
        if h not in seen:
            seen.add(h); uniq.append((h, t))
    return uniq


def _abs(base, href):
    return href if href.startswith("http") else urllib.parse.urljoin(base, href)


def _report_flatfile(tag, url, headers, body, universe):
    tks = _extract_tickers(body)
    ov = sorted(set(tks) & set(universe))
    ct = headers.get("Content-Type", "?")
    print(f"    ✔ FLAT-FILE {tag}: {url}")
    print(f"      ct={ct} bytes={len(body)} tickers~{len(tks)} "
          f"overlap={len(ov)}/{len(universe)} {ov[:12]}")
    print("      Kopf:\n        " + _first_lines(body, 8).replace("\n", "\n        "))
    # Q5: Spalten auf Trigger-/Effective-Datum prüfen
    header0 = (_txt(body).splitlines() or [""])[0].lower()
    has_date_col = any(k in header0 for k in ("date", "trigger", "effective", "day"))
    print(f"      Q5-Format: Header-Spalten enthalten Datum/Trigger-Marker? "
          f"{'JA' if has_date_col else 'NEIN'}  → '{header0[:120]}'")
    return len(ov), len(tks)


def follow_entry_pages(universe):
    print("\n═══ PHASE A2 — Anchor-Follow: 'short sale circuit breaker' verfolgen ═══")
    real_ssr_files = []
    for name, url in ENTRY_PAGES:
        st, hd, body, took = _get(url)
        ct = hd.get("Content-Type", "?")
        print(f"\n[{name}] {url}\n  → status={st} ct={ct} bytes={len(body)} {took:.2f}s")
        if not (isinstance(st, int) and st == 200 and body):
            continue
        html = _txt(body)
        anchors = _ssr_anchors(html)
        print(f"  → {len(anchors)} SSR-relevante Anchor(s):")
        for href, text in anchors[:12]:
            print(f"      '{text[:48]}' → {href}")
        # jeden Anchor verfolgen
        for href, text in anchors[:8]:
            follow_url = _abs(url, href)
            st2, hd2, body2, _ = _get(follow_url)
            print(f"    ↪ follow '{text[:32]}' → {follow_url}  [status={st2} "
                  f"ct={hd2.get('Content-Type','?')} bytes={len(body2)}]")
            if not (isinstance(st2, int) and st2 == 200 and body2):
                continue
            if _is_flat_file(hd2, body2):
                real_ssr_files.append(follow_url)
                _report_flatfile(name, follow_url, hd2, body2, universe)
            else:
                # Folge-Seite ist HTML → deren Daten-Links extrahieren + testen
                sub = sorted(set(_LINK_DATA_RE.findall(_txt(body2))))
                sub_ssr = [s for s in sub if any(k in s.lower() for k in
                           ("ssr", "circuit", "shortsale", "short_sale", "short-sale"))]
                cand = sub_ssr or sub[:6]
                if cand:
                    print(f"       → {len(sub)} Daten-Link(s), teste {len(cand)}:")
                for s in cand[:6]:
                    su = _abs(follow_url, s)
                    st3, hd3, body3, _ = _get(su)
                    flat = isinstance(st3, int) and st3 == 200 and _is_flat_file(hd3, body3)
                    print(f"         · {su} [status={st3} flat={flat}]")
                    if flat:
                        real_ssr_files.append(su)
                        _report_flatfile(name + "/sub", su, hd3, body3, universe)
                    time.sleep(0.3)
            time.sleep(0.3)
        time.sleep(0.4)
    return real_ssr_files


def try_direct(universe):
    print("\n═══ PHASE B2 — Direkte SSR-Flat-File-Kandidaten (Fallback) ═══")
    today = dt.datetime.now(dt.timezone.utc).date()
    dates = [(today - dt.timedelta(days=i)) for i in range(6)]
    hits = []
    for name, tmpl in DIRECT_SSR:
        print(f"\n[{name}] {tmpl}")
        for d in dates:
            url = tmpl.format(d=d.strftime("%Y%m%d"))
            st, hd, body, _ = _get(url, timeout=20)
            flat = isinstance(st, int) and st == 200 and _is_flat_file(hd, body)
            if flat:
                hits.append(url)
                _report_flatfile(name, url, hd, body, universe)
                break
            elif d == dates[0]:
                print(f"  · {d.isoformat()}: status={st} "
                      f"ct={hd.get('Content-Type','?')} bytes={len(body)} "
                      f"flat={isinstance(st,int) and st==200 and _is_flat_file(hd,body)}")
            time.sleep(0.25)
    return hits


def main(argv):
    uni_path = argv[1] if len(argv) > 1 else "scripts/diagnose/ssr_probe_universe.json"
    uni_doc = json.load(open(uni_path))
    universe = uni_doc.get("universe") or uni_doc
    now = dt.datetime.now(dt.timezone.utc)
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  SSR-Flag Machbarkeits-Probe v2 (Discovery-Follower, read-only)   ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"Runner-UTC now: {now.isoformat()}  (Wochentag {now.strftime('%a')})")
    print(f"Universum: n={len(universe)}")
    print(f"  {universe}")
    print("Ziel: die ECHTE Rule-201-SSR-Liste (Circuit-Breaker) via Anchor-Follow "
          "finden. Härtung: _is_flat_file verwirft HTML-App-Shells (v1-200-Falle).")

    ssr_files = follow_entry_pages(universe)
    if not ssr_files:
        ssr_files += try_direct(universe)

    print("\n═══ VERDIKT-ROHDATEN ═══")
    print(f"Echte SSR-Flat-Files gefunden: {len(ssr_files)}")
    for u in ssr_files:
        print(f"  • {u}")
    if not ssr_files:
        print("  (keine — Anchor-Follow + direkte Kandidaten lieferten kein "
              "echtes Rule-201-Flat-File. Konsequenz: keyless SSR nicht verfügbar "
              "über die getesteten Venue-Pfade.)")
    print("\nFERTIG.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
