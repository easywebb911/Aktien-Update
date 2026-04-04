"""
Minimales Diagnose-Skript für FINRA- und Fintel-API.
Manuell per GitHub Actions triggern – zeigt vollständige API-Antworten.
"""
import os
import json
import requests

TICKER = "GME"

# ── FINRA ────────────────────────────────────────────────────────────────────
print("=" * 60)
print("FINRA SHORT INTEREST TEST")
print("=" * 60)

token = os.environ.get("FINRA_API_TOKEN", "")
print(f"FINRA_API_TOKEN gesetzt: {'JA (' + str(len(token)) + ' Zeichen)' if token else 'NEIN – Variable leer oder nicht gesetzt'}")

url = "https://api.finra.org/data/group/equity/name/shortInterest"
payload = {
    "compareFilters": [
        {"fieldName": "symbolCode", "compareType": "equal", "fieldValue": TICKER}
    ],
    "limit": 3,
    "sortFields": ["-settlementDate"],
}
headers = {"Content-Type": "application/json"}
if token:
    headers["Authorization"] = f"Bearer {token}"

print(f"\nEndpoint : POST {url}")
print(f"Ticker   : {TICKER}")
print(f"Auth     : {'Bearer ***' + token[-4:] if token else 'keiner'}")

try:
    r = requests.post(url, json=payload, headers=headers, timeout=15)
    print(f"\nHTTP Status : {r.status_code}")
    print(f"Response Body:\n{r.text[:2000]}")
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, list) and data:
            print(f"\nAnzahl Records: {len(data)}")
            print(f"Keys im ersten Record: {list(data[0].keys())}")
            print(f"Erster Record:\n{json.dumps(data[0], indent=2)}")
        else:
            print(f"\nAntwort ist kein befülltes Array: {type(data)}")
except Exception as e:
    print(f"\nVerbindungsfehler: {e}")

# ── Fintel FTD ───────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("FINTEL FTD TEST")
print("=" * 60)

ftd_url = f"https://fintel.io/api/filings/ftd/{TICKER}"
ftd_headers = {
    "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
    "Accept": "application/json",
}

print(f"\nEndpoint : GET {ftd_url}")
try:
    r2 = requests.get(ftd_url, headers=ftd_headers, timeout=15)
    print(f"HTTP Status : {r2.status_code}")
    print(f"Content-Type: {r2.headers.get('Content-Type', '?')}")
    print(f"Response Body (erste 1000 Zeichen):\n{r2.text[:1000]}")
    if r2.status_code == 200:
        try:
            d2 = r2.json()
            print(f"\nJSON-Typ: {type(d2)}")
            if isinstance(d2, list) and d2:
                print(f"Erstes Element: {json.dumps(d2[0], indent=2)}")
        except Exception:
            print("Body ist kein valides JSON")
except Exception as e:
    print(f"\nVerbindungsfehler: {e}")

print("\n" + "=" * 60)
print("TEST ABGESCHLOSSEN")
print("=" * 60)
