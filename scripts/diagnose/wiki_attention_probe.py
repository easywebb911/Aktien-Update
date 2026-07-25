#!/usr/bin/env python3
"""Read-only Machbarkeits-Probe: Attention-Feed via Wikipedia-Pageviews.

Läuft AUSSCHLIESSLICH auf dem GitHub-Actions-Runner (unrestricted egress) —
die interaktive Sandbox ist egress-deny-all (403 auf alle externen Hosts).
Keyless. Wikimedia-User-Agent-Policy respektiert. KEINE Repo-Writes, KEINE
Secrets. Misst die fünf Fragen; Output komplett ins Run-Log.

Bewusst konservativ: max ~1 SPARQL + 1 Titel-Check + (Teilmenge) 1 Pageviews-
Call pro Ticker; kleine Pausen (Wikimedia-Policy ~<=100 req/s ist reichlich,
wir bleiben weit darunter).
"""
import json, sys, time, urllib.parse, urllib.request, datetime as dt

UA = ("SqueezeReportAttentionProbe/1.0 "
      "(https://github.com/easywebb911/Aktien-Update; easywebb@yahoo.de)")
SPARQL = "https://query.wikidata.org/sparql"
WD_API = "https://www.wikidata.org/w/api.php"
WP_API = "https://en.wikipedia.org/w/api.php"
PV = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
      "en.wikipedia/all-access/all-agents/{art}/daily/{start}/{end}")

# Bekannte Firmennamen für die Disambiguierungs-Härtefälle (Ground Truth).
GROUND_TRUTH = {
    "AI": "C3.ai", "WOLF": "Wolfspeed", "AMC": "AMC Theatres",
    "GO": "Grocery Outlet", "REAL": "The RealReal", "PLAY": "Dave & Buster's",
    "WEN": "Wendy's", "ROOT": "Root, Inc.", "HTZ": "Hertz",
    "OM": "Outset Medical", "SG": "Sweetgreen", "SEAT": "Vivid Seats",
}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return r.status, body, time.time() - t0


def wikidata_by_ticker(ticker):
    """Deterministischer Pfad: P249 (ticker symbol) als Qualifier auf P414
    (stock exchange), gefiltert auf US-Börsen (NASDAQ Q82059 / NYSE Q13677 /
    NYSE American Q11705394). Liefert (qid, label, enwiki_title) oder None."""
    q = f'''SELECT ?item ?itemLabel ?art ?artde WHERE {{
  ?item p:P414 ?st. ?st ps:P414 ?exch; pq:P249 "{ticker}".
  VALUES ?exch {{ wd:Q82059 wd:Q13677 wd:Q11705394 }}
  OPTIONAL {{ ?art schema:about ?item; schema:isPartOf <https://en.wikipedia.org/>. }}
  OPTIONAL {{ ?artde schema:about ?item; schema:isPartOf <https://de.wikipedia.org/>. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} LIMIT 5'''
    url = SPARQL + "?" + urllib.parse.urlencode({"query": q, "format": "json"})
    try:
        st, body, took = _get(url)
        rows = json.loads(body)["results"]["bindings"]
        if not rows:
            return None, took
        r = rows[0]
        qid = r["item"]["value"].rsplit("/", 1)[-1]
        label = r.get("itemLabel", {}).get("value", "")
        art = (r.get("art", {}).get("value", "") or "").rsplit("/wiki/", 1)[-1]
        artde = (r.get("artde", {}).get("value", "") or "").rsplit("/wiki/", 1)[-1]
        return {"qid": qid, "label": label,
                "enwiki": urllib.parse.unquote(art) if art else None,
                "dewiki": urllib.parse.unquote(artde) if artde else None,
                "n_rows": len(rows)}, took
    except Exception as e:
        return {"error": repr(e)[:120]}, 0.0


def enwiki_exists(title):
    url = WP_API + "?" + urllib.parse.urlencode({
        "action": "query", "titles": title, "redirects": 1, "format": "json"})
    try:
        st, body, took = _get(url)
        pages = json.loads(body)["query"]["pages"]
        pid = next(iter(pages))
        return (int(pid) > 0), pages[pid].get("title"), took
    except Exception as e:
        return False, repr(e)[:120], 0.0


def pageviews(article, start, end):
    art = urllib.parse.quote(article.replace(" ", "_"), safe="")
    url = PV.format(art=art, start=start, end=end)
    try:
        st, body, took = _get(url)
        items = json.loads(body).get("items", [])
        return [(it["timestamp"][:8], it["views"]) for it in items], took, st
    except Exception as e:
        return [], 0.0, repr(e)[:120]


def main():
    uni = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else ["GRPN", "AI"]
    today = dt.date.today()
    print(f"# Probe-Start {dt.datetime.utcnow().isoformat()}Z  Universe n={len(uni)}")
    print(f"# Runner-IP:")
    try:
        _, ip, _ = _get("https://api.ipify.org?format=json"); print("  ", ip.decode()[:80])
    except Exception as e:
        print("  (ip probe failed)", e)

    # ── Q4/Q6: UA-Policy — mit vs. ohne User-Agent ───────────────────────────
    print("\n## Q6 User-Agent-Policy (Wikimedia)")
    test_url = PV.format(art="GameStop",
                         start=(today - dt.timedelta(days=10)).strftime("%Y%m%d"),
                         end=(today - dt.timedelta(days=3)).strftime("%Y%m%d"))
    for tag, hdr in (("MIT UA", {"User-Agent": UA}), ("OHNE UA", {})):
        try:
            req = urllib.request.Request(test_url, headers=hdr)
            with urllib.request.urlopen(req, timeout=20) as r:
                print(f"  {tag}: HTTP {r.status}")
        except Exception as e:
            print(f"  {tag}: FAIL {repr(e)[:100]}")

    # ── Q3 + Fork 1: Finalität PRÄZISE. Wann ist der Pageview-Tageswert final?
    # Miss über MEHRERE stark frequentierte Artikel (robuster als ein Sample),
    # zum aktuellen UTC-Zeitpunkt. Konsequenz für Fork-1-Design (T-1 sofort +
    # Tag-T-Nachtrag am T+1-postclose) hängt genau hieran.
    now_utc = dt.datetime.utcnow()
    print(f"\n## Q3 Finalität (Dispatch-Zeit UTC={now_utc.isoformat()}Z)")
    print("   Fork-1-Frage: ist T-1 JETZT final? ist T-2 final? → ist Tag-T am T+1-postclose final?")
    for art in ("GameStop", "AMC_Theatres", "Tesla,_Inc."):
        rows, took, st = pageviews(art,
                                   (today - dt.timedelta(days=6)).strftime("%Y%m%d"),
                                   today.strftime("%Y%m%d"))
        avail = {d for d, _ in rows}
        newest = rows[-1][0] if rows else None
        lag = (today - dt.datetime.strptime(newest, "%Y%m%d").date()).days if newest else None
        tm1 = (today - dt.timedelta(days=1)).strftime("%Y%m%d")
        tm2 = (today - dt.timedelta(days=2)).strftime("%Y%m%d")
        print(f"  {art:<16} newest={newest} (T-{lag})  "
              f"T-1_final={tm1 in avail}  T-2_final={tm2 in avail}  ({took:.2f}s, {len(rows)}d)")
    print("  ⇒ Interpretation: newest==T-1 ⇒ Tag-T wird morgen (T+1) final ⇒ Fork-1-Nachtrag machbar.")
    print("    newest==T-2 ⇒ Tag-T erst T+2 final ⇒ T+1-Nachtrag NOCH nicht stabil (Design-Warnung).")
    print("    (Dispatch möglichst nahe 21:17 UTC = postclose, damit die Aussage zeitlich gilt.)")

    # ── Q1/Q2: Mapping + Disambiguierung über das echte Universum ────────────
    print("\n## Q1/Q2 Mapping-Abdeckung (Wikidata P249 → en/de-wiki)")
    print(f"  {'TICK':<6}{'WD?':<5}{'QID':<10}{'enwiki-Titel':<30}{'de?':<5}{'GT-ok?':<7}{'s':<6}")
    cov = {"wd_ticker": 0, "enwiki": 0, "dewiki": 0, "none": 0, "gt_checked": 0, "gt_ok": 0}
    t_start = time.time()
    for tk in uni:
        res, took = wikidata_by_ticker(tk)
        if not res or res.get("error"):
            cov["none"] += 1
            print(f"  {tk:<6}{'no':<5}{'-':<10}{'—':<30}{'-':<5}{'-':<7}{took:<6.2f}"
                  + (f"ERR {res.get('error')}" if res and res.get('error') else ""))
        else:
            cov["wd_ticker"] += 1
            enw, dew = res.get("enwiki"), res.get("dewiki")
            if enw:
                cov["enwiki"] += 1
            if dew:
                cov["dewiki"] += 1
            gt = ""
            if tk in GROUND_TRUTH:
                cov["gt_checked"] += 1
                ok = GROUND_TRUTH[tk].lower().split(",")[0][:6] in (res.get("label", "").lower() + (enw or "").lower())
                cov["gt_ok"] += 1 if ok else 0
                gt = "OK" if ok else "MISS"
            print(f"  {tk:<6}{'yes':<5}{res.get('qid','-'):<10}{(enw or '—')[:29]:<30}"
                  f"{('y' if dew else '-'):<5}{gt:<7}{took:<6.2f}"
                  + (f"  →{res.get('label')}" if gt == "MISS" else ""))
        time.sleep(0.3)
    dt_total = time.time() - t_start
    n = len(uni)
    print(f"\n## ABDECKUNG (n={n}, Mapping-Zeit {dt_total:.1f}s = {dt_total/n:.2f}s/Ticker)")
    print(f"  (a) Wikidata-Eintrag mit US-Ticker (P249): {cov['wd_ticker']}/{n} = {100*cov['wd_ticker']//n}%")
    print(f"  (b) davon mit en-Wikipedia-Artikel:        {cov['enwiki']}/{n} = {100*cov['enwiki']//n}%")
    print(f"      davon mit de-Wikipedia-Artikel (Fork2):{cov['dewiki']}/{n} = {100*cov['dewiki']//n}%")
    print(f"  kein Mapping (substrate=none-Kandidat):    {cov['none']}/{n} = {100*cov['none']//n}%")
    print(f"  Disambiguierung Härtefälle: {cov['gt_ok']}/{cov['gt_checked']} korrekt zur FIRMA")


if __name__ == "__main__":
    main()
