"""Quote-Proxy-Health-Probe (Health-Check Provider-Tier 2).

Pingt den Cloudflare-Worker, der Live-Quotes für das Frontend liefert
(`quote-proxy.<account>.workers.dev`). Bewusst serverseitig, **nicht**
aus dem Browser — das fängt:

- Worker tot / Cloudflare-Account-Suspend / Worker-undeployed
- Yahoo v8 Endpoint gebrochen (Worker antwortet 200 mit `error`-Feld
  wie ``yahoo_403`` / ``yahoo_no_meta`` / ``proxy_fail:…``)
- HTTP-Timeout, 5xx, non-JSON-Response, Latency-Anomalien

Was die Probe **nicht** fängt (bewusst, akzeptiert):

- **CORS-Drift**: Browser-only-Klasse. Der GH-Actions-Runner setzt zwar
  den ``Origin``-Header, aber der Worker-Code fällt bei nicht-erlaubtem
  Origin auf den ersten Allowlist-Eintrag zurück (siehe
  ``cloudflare/quote-proxy/worker.js``) und liefert eine sinnvolle
  Antwort. Ein echter Browser würde die Response wegen CORS-Mismatch
  blocken — das sieht nur der Browser.
- JS-Bugs im ``_quoteFetchOnce``-Polling-Pfad — wir testen nur den
  Endpoint, nicht das Frontend.

Returnt ein Dict mit Feldern, die direkt an
``health_check.record_provider_call`` durchgereicht werden können.

Pure-Funktion mit injektierbarem HTTP-Client (Default ``requests.get``).
Tests können einen Stub-Client setzen ohne Netzwerk-Roundtrip.
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable


# URL-Sanitize identisch zur Frontend-Injection in generate_report.py:
# nur https://-Schema, Host als a-zA-Z0-9.-, optionaler Pfad ohne
# Query/Anker (die Probe hängt ?ticker=… selbst an).
_URL_RE = re.compile(r"^https://[A-Za-z0-9.\-]+(/[A-Za-z0-9._\-/]*)?$")


def _sanitize_url(raw: str) -> str:
    """Returnt die saubere URL ohne trailing ``/`` oder leeren String
    bei nicht-validem Input."""
    if not isinstance(raw, str):
        return ""
    u = raw.strip().rstrip("/")
    if not u:
        return ""
    if not _URL_RE.match(u):
        return ""
    return u[:256]


def probe_quote_proxy(
    url: str,
    *,
    ticker: str = "NVDA",
    timeout_s: float = 5.0,
    origin: str = "https://easywebb911.github.io",
    http_get: Callable[..., Any] | None = None,
) -> dict:
    """Pingt den Quote-Proxy einmal.

    Returnt ein Dict mit Feldern für ``record_provider_call``:
    - ``http_status``: int | None (None bei Timeout/Net-Exception)
    - ``latency_ms``: int (≥ 0)
    - ``item_count``: 0 oder 1 (1 = erfolgreicher Quote mit numerischem
       price-Feld)
    - ``error``: str | None (gesetzt bei jedem nicht-OK-Pfad)
    - ``price``: float | None (nur bei item_count=1)
    - ``skipped``: bool (True wenn URL leer/invalid → nichts gepingt)

    Skip-Fall (``skipped=True``): leere/invalide URL. Kein Netzwerk-
    Roundtrip, kein Eintrag in ``provider_health.jsonl`` — der Caller
    überspringt ``record_provider_call`` bei ``skipped=True``.
    """
    clean_url = _sanitize_url(url)
    if not clean_url:
        return {
            "http_status": None,
            "latency_ms":  0,
            "item_count":  0,
            "error":       "no_url",
            "price":       None,
            "skipped":     True,
        }

    if http_get is None:
        import requests
        http_get = requests.get

    request_url = f"{clean_url}/?ticker={ticker}"
    headers = {"Origin": origin}
    t0 = time.perf_counter()
    http_status: int | None = None
    error: str | None = None
    item_count = 0
    price: float | None = None

    try:
        resp = http_get(request_url, headers=headers, timeout=timeout_s)
        http_status = getattr(resp, "status_code", None)
        if http_status == 200:
            try:
                body = resp.json()
            except (ValueError, AttributeError):
                error = "non_json_response"
            else:
                if not isinstance(body, dict):
                    error = "non_dict_response"
                elif body.get("error"):
                    error = str(body.get("error"))[:80]
                else:
                    pr = body.get("price")
                    if isinstance(pr, (int, float)) and pr > 0:
                        price = float(pr)
                        item_count = 1
                    else:
                        error = "no_price_in_response"
        elif http_status is None:
            error = "no_status"
        else:
            error = f"http_{http_status}"
    except Exception as exc:
        # requests.Timeout, requests.ConnectionError, beliebige Stub-
        # Exceptions im Test. Wir loggen Klasse + Kurz-Repr.
        name = type(exc).__name__
        msg = str(exc)[:80].replace("\n", " ").strip()
        error = f"{name}: {msg}" if msg else name

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "http_status": http_status,
        "latency_ms":  latency_ms,
        "item_count":  item_count,
        "error":       error,
        "price":       price,
        "skipped":     False,
    }


__all__ = ["probe_quote_proxy"]
