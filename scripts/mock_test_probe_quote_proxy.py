"""Mock-Tests fuer scripts/probe_quote_proxy.py.

Drei Hauptpfade laut Auftrag:
1. OK              — HTTP 200 + numerischer ``price`` → item_count=1, error=None
2. yahoo_error     — HTTP 200 + ``error``-Feld → error gesetzt
3. worker_5xx      — HTTP 502/503/... → error="http_<N>"

Plus Edge-Cases: leere URL (Skip), Timeout, non-JSON, non-Dict, fehlender
Price, 0/negativer Price.

Pure-Test ohne Netzwerk — Stub-HTTP-Client wird via Kwarg injiziert.
Ausfuehrung: ``python3 scripts/mock_test_probe_quote_proxy.py``.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.probe_quote_proxy import probe_quote_proxy  # noqa: E402


URL = "https://quote-proxy.easywebb.workers.dev"


class _StubResp:
    """Minimaler requests.Response-Mock."""
    def __init__(self, status_code=200, json_data=None, raises=None):
        self.status_code = status_code
        self._json = json_data
        self._raises = raises

    def json(self):
        if self._raises is not None:
            raise self._raises
        return self._json


def _stub_http(*, status=200, body=None, json_exc=None,
               request_exc=None):
    """Baut http_get-Stub mit fest verdrahteter Antwort."""
    def fake_get(url, headers=None, timeout=None):
        assert "ticker=" in url, "URL muss ?ticker= enthalten"
        assert headers and headers.get("Origin"), "Origin-Header muss gesetzt sein"
        if request_exc is not None:
            raise request_exc
        return _StubResp(status_code=status, json_data=body, raises=json_exc)
    return fake_get


# === Pfad 1: OK ============================================================

def test_01_ok_with_numeric_price() -> None:
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(status=200, body={
            "ticker": "NVDA", "price": 123.45, "change": 0.5,
            "change_abs": 0.6, "volume": 1000000,
            "market_state": "REGULAR", "prev_close": 122.85,
            "ts": "2026-05-21T15:30:00Z",
        }),
    )
    assert res["skipped"] is False, res
    assert res["http_status"] == 200, res
    assert res["item_count"] == 1, res
    assert res["price"] == 123.45, res
    assert res["error"] is None, res
    assert res["latency_ms"] >= 0


# === Pfad 2: yahoo_error =================================================

def test_02_yahoo_error_field() -> None:
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(status=200, body={
            "ticker": None, "error": "yahoo_403",
        }),
    )
    assert res["http_status"] == 200
    assert res["item_count"] == 0
    assert res["error"] == "yahoo_403", res
    assert res["price"] is None


def test_03_yahoo_no_meta() -> None:
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(status=200, body={
            "ticker": None, "error": "yahoo_no_meta",
        }),
    )
    assert res["error"] == "yahoo_no_meta"


def test_04_proxy_fail() -> None:
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(status=200, body={
            "ticker": None, "error": "proxy_fail:fetch_aborted",
        }),
    )
    assert res["error"] == "proxy_fail:fetch_aborted"


# === Pfad 3: worker_5xx ==================================================

def test_05_worker_502() -> None:
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(status=502, body=None),
    )
    assert res["http_status"] == 502
    assert res["item_count"] == 0
    assert res["error"] == "http_502"


def test_06_worker_503() -> None:
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(status=503, body=None),
    )
    assert res["error"] == "http_503"


def test_07_worker_403_egress_block() -> None:
    """Beispiel: Cloudflare/Worker antwortet 403 (Allowlist-Drift / Account-Suspend)."""
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(status=403, body=None),
    )
    assert res["error"] == "http_403"


# === Edge-Cases ==========================================================

def test_08_empty_url_skips() -> None:
    """Leere URL → skipped=True, kein Aufruf, kein Eintrag."""
    res = probe_quote_proxy("")
    assert res["skipped"] is True
    assert res["error"] == "no_url"
    assert res["latency_ms"] == 0


def test_09_invalid_url_skips() -> None:
    """Nicht-https-Schema → Skip."""
    res = probe_quote_proxy("http://example.com")  # http statt https
    assert res["skipped"] is True


def test_10_url_with_query_skips() -> None:
    """URL mit Query-String → Skip (Sanitize verbietet)."""
    res = probe_quote_proxy("https://quote-proxy.example.workers.dev?foo=bar")
    assert res["skipped"] is True


def test_11_none_url_skips() -> None:
    """None statt String → Skip, kein Crash."""
    res = probe_quote_proxy(None)  # type: ignore[arg-type]
    assert res["skipped"] is True


def test_12_timeout() -> None:
    """requests.Timeout (oder beliebige Exception) → error gesetzt, kein Crash."""
    class _Timeout(Exception):
        pass
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(request_exc=_Timeout("Read timed out")),
    )
    assert res["http_status"] is None
    assert res["item_count"] == 0
    assert "Timeout" in res["error"] or "timed out" in res["error"]


def test_13_connection_error() -> None:
    class _ConnErr(Exception):
        pass
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(request_exc=_ConnErr("Cannot connect")),
    )
    assert res["http_status"] is None
    assert "ConnErr" in res["error"]


def test_14_non_json_response() -> None:
    """HTTP 200 aber Response ist kein JSON → error=non_json_response."""
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(status=200, json_exc=ValueError("not json")),
    )
    assert res["http_status"] == 200
    assert res["error"] == "non_json_response"


def test_15_non_dict_json() -> None:
    """HTTP 200 + JSON aber kein Dict → error=non_dict_response."""
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(status=200, body=["array", "not", "dict"]),
    )
    assert res["error"] == "non_dict_response"


def test_16_missing_price() -> None:
    """HTTP 200 + Dict ohne ``price`` und ohne ``error`` → no_price_in_response."""
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(status=200, body={"ticker": "NVDA"}),
    )
    assert res["error"] == "no_price_in_response"


def test_17_price_zero_treated_as_invalid() -> None:
    """Price = 0 ist kein gültiger Quote (Yahoo gibt manchmal 0 bei market-closed)."""
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(status=200, body={"ticker": "NVDA", "price": 0}),
    )
    assert res["item_count"] == 0
    assert res["error"] == "no_price_in_response"


def test_18_price_negative_treated_as_invalid() -> None:
    res = probe_quote_proxy(
        URL,
        http_get=_stub_http(status=200, body={"ticker": "NVDA", "price": -1.5}),
    )
    assert res["item_count"] == 0
    assert res["error"] == "no_price_in_response"


def test_19_origin_header_is_set() -> None:
    """Origin-Header muss bei jedem Probe-Call gesetzt sein (Client-Simulation)."""
    captured = {}
    def fake_get(url, headers=None, timeout=None):
        captured["headers"] = headers
        captured["url"] = url
        captured["timeout"] = timeout
        return _StubResp(200, {"ticker": "NVDA", "price": 100.0})
    res = probe_quote_proxy(URL, origin="https://test.example.org",
                             http_get=fake_get)
    assert captured["headers"]["Origin"] == "https://test.example.org"
    assert "ticker=NVDA" in captured["url"]
    assert captured["timeout"] == 5.0
    assert res["item_count"] == 1


def test_20_trailing_slash_normalized() -> None:
    """URL mit trailing / wird normalisiert (kein doppelter /)."""
    captured = {}
    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        return _StubResp(200, {"ticker": "NVDA", "price": 100.0})
    probe_quote_proxy(URL + "/", http_get=fake_get)
    assert "//?ticker=" not in captured["url"], captured["url"]
    assert "/?ticker=" in captured["url"]


def main() -> int:
    tests = [
        test_01_ok_with_numeric_price,
        test_02_yahoo_error_field,
        test_03_yahoo_no_meta,
        test_04_proxy_fail,
        test_05_worker_502,
        test_06_worker_503,
        test_07_worker_403_egress_block,
        test_08_empty_url_skips,
        test_09_invalid_url_skips,
        test_10_url_with_query_skips,
        test_11_none_url_skips,
        test_12_timeout,
        test_13_connection_error,
        test_14_non_json_response,
        test_15_non_dict_json,
        test_16_missing_price,
        test_17_price_zero_treated_as_invalid,
        test_18_price_negative_treated_as_invalid,
        test_19_origin_header_is_set,
        test_20_trailing_slash_normalized,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except AssertionError as exc:
            print(f"  ✗ {t.__name__}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ✗ {t.__name__}: unexpected {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} Tests OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
