"""Mock-Tests fuer Health-Check-Digest ntfy URL-Pattern (17.05.2026).

Hintergrund: Health-Check-Digest hat seit Tagen keinen Push gesendet
trotz Workflow-Runs (last_digest_sent stets null). Diagnose: JSON-API-
Variante von PR #168 schlug auf ntfy.sh fehl. Alle anderen ntfy-Sender
im Tool (ki_agent._send_anomaly_ntfy, _send_exit_p2_push) nutzen das
URL-Pattern und funktionieren zuverlaessig.

Loesung: _ntfy_send adoptiert URL-Pattern analog ki_agent — POST an
https://ntfy.sh/{topic} mit Title-Header (ASCII-only durch automatic
encoding strip) + Body als UTF-8-data.

Tests:
  1. POST geht an URL-Pattern https://ntfy.sh/{topic}
  2. Body geht als data=UTF-8-encoded
  3. Title-Header ist ASCII-only (Emojis gestrippt)
  4. UTF-8-Body mit Emojis bleibt erhalten
  5. Priority-Header gesetzt
  6. Tags-Header gesetzt wenn vorhanden
  7. Tags=None -> kein Tags-Header
  8. NTFY disabled -> kein POST, return False
  9. requests=None -> return False
 10. HTTP 4xx -> return False
 11. HTTP 2xx -> return True
 12. Source-Inspektion: kein json=payload-Aufruf mehr (JSON-API weg)
 13. Source-Inspektion: kein NTFY_URL-Konstante mehr
 14. Source-Inspektion: Title-Header wird ASCII-stripped
"""
from __future__ import annotations

import pathlib
import sys
from unittest.mock import patch, MagicMock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCRIPT_SRC = (ROOT / "scripts" / "health_check_digest.py").read_text(encoding="utf-8")

import health_check_digest as hcd  # type: ignore


class _PostRecorder:
    def __init__(self, status_code: int = 200, text: str = "ok"):
        self.calls = []
        self.status_code = status_code
        self.text = text

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        resp = MagicMock()
        resp.status_code = self.status_code
        resp.text = self.text
        return resp


def _patch_ntfy_active():
    return [
        patch.object(hcd, "NTFY_TOPIC", "test-topic-xyz"),
        patch.object(hcd, "NTFY_ENABLED", True),
    ]


def _enter(patches):
    return [p.__enter__() for p in patches]


def _exit(patches):
    for p in patches:
        p.__exit__(None, None, None)


# ── Funktional ──────────────────────────────────────────────────────────────

def test_01_post_url_pattern() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            hcd._ntfy_send("title", "body", "high", "warning")
        assert recorder.calls[0]["url"] == "https://ntfy.sh/test-topic-xyz", \
            f"URL falsch: {recorder.calls[0]['url']!r}"
    finally:
        _exit(patches)


def test_02_body_utf8_encoded() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            hcd._ntfy_send("title", "Body mit ⚠️ und 🔴", "high", None)
        data = recorder.calls[0]["data"]
        assert data == "Body mit ⚠️ und 🔴".encode("utf-8"), \
            f"Body nicht als UTF-8-bytes: {data!r}"
    finally:
        _exit(patches)


def test_03_title_header_ascii_only() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            hcd._ntfy_send("⚠️ Health-Check-Digest", "body", "high", None)
        title = recorder.calls[0]["headers"]["Title"]
        # Title-Header muss als latin-1 encodebar sein (HTTP-Spec)
        title.encode("latin-1")  # Darf nicht raisen
        # Emoji-Reste sind raus, Text-Kern erhalten
        assert "Health-Check-Digest" in title, \
            f"Title-Kern verloren: {title!r}"
        assert "⚠" not in title and "️" not in title, \
            f"Emoji-Rest noch im Title: {title!r}"
    finally:
        _exit(patches)


def test_04_emoji_body_preserved() -> None:
    # Body bleibt UTF-8 — alle Emojis erhalten
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            hcd._ntfy_send("t", "🔴🟡✅📭⚠️🚀", "default", None)
        data = recorder.calls[0]["data"]
        assert data.decode("utf-8") == "🔴🟡✅📭⚠️🚀"
    finally:
        _exit(patches)


def test_05_priority_header_set() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            hcd._ntfy_send("t", "b", "urgent", None)
        assert recorder.calls[0]["headers"]["Priority"] == "urgent"
    finally:
        _exit(patches)


def test_06_tags_header_set_when_provided() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            hcd._ntfy_send("t", "b", "high", "warning,rotating_light")
        assert recorder.calls[0]["headers"]["Tags"] == "warning,rotating_light"
    finally:
        _exit(patches)


def test_07_no_tags_no_header() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            hcd._ntfy_send("t", "b", "default", None)
        assert "Tags" not in recorder.calls[0]["headers"]
    finally:
        _exit(patches)


def test_08_ntfy_disabled_no_post() -> None:
    with patch.object(hcd, "NTFY_TOPIC", ""), \
         patch.object(hcd, "NTFY_ENABLED", False):
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            rc = hcd._ntfy_send("t", "b", "default", None)
        assert rc is False
        assert len(recorder.calls) == 0


def test_09_requests_missing_no_post() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        with patch.object(hcd, "requests", None):
            rc = hcd._ntfy_send("t", "b", "default", None)
        assert rc is False
    finally:
        _exit(patches)


def test_10_http_4xx_returns_false() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder(status_code=429, text="rate limited")
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            rc = hcd._ntfy_send("t", "b", "high", None)
        assert rc is False
    finally:
        _exit(patches)


def test_11_http_2xx_returns_true() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder(status_code=200)
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            rc = hcd._ntfy_send("t", "b", "default", None)
        assert rc is True
    finally:
        _exit(patches)


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_12_no_json_payload_call() -> None:
    block_start = SCRIPT_SRC.find("def _ntfy_send(")
    block_end = SCRIPT_SRC.find("\ndef ", block_start + 10)
    block = SCRIPT_SRC[block_start:block_end]
    assert "json=payload" not in block, \
        "Alter JSON-API-Aufruf (json=payload) noch im Source"


def test_13_no_ntfy_url_constant() -> None:
    assert "NTFY_URL" not in SCRIPT_SRC, \
        "Obsolete NTFY_URL-Konstante noch im Source"


def test_14_title_ascii_strip_present() -> None:
    block_start = SCRIPT_SRC.find("def _ntfy_send(")
    block_end = SCRIPT_SRC.find("\ndef ", block_start + 10)
    block = SCRIPT_SRC[block_start:block_end]
    assert ".encode(\"ascii\", \"ignore\")" in block or \
           ".encode('ascii', 'ignore')" in block, \
        "Title-ASCII-Strip fehlt — Emoji-Header wuerde latin-1-Bug ausloesen"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 POST URL-Pattern",                test_01_post_url_pattern),
        ("02 Body UTF-8-encoded",              test_02_body_utf8_encoded),
        ("03 Title-Header ASCII-only",         test_03_title_header_ascii_only),
        ("04 UTF-8-Body bleibt erhalten",      test_04_emoji_body_preserved),
        ("05 Priority-Header",                  test_05_priority_header_set),
        ("06 Tags-Header bei Vorhandensein",    test_06_tags_header_set_when_provided),
        ("07 Tags=None -> kein Header",        test_07_no_tags_no_header),
        ("08 NTFY disabled -> kein POST",      test_08_ntfy_disabled_no_post),
        ("09 requests=None -> False",          test_09_requests_missing_no_post),
        ("10 HTTP 4xx -> False",                test_10_http_4xx_returns_false),
        ("11 HTTP 2xx -> True",                 test_11_http_2xx_returns_true),
        ("12 Kein json=payload mehr",           test_12_no_json_payload_call),
        ("13 Keine NTFY_URL-Konstante",         test_13_no_ntfy_url_constant),
        ("14 Title-ASCII-Strip vorhanden",      test_14_title_ascii_strip_present),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
        except AssertionError as exc:
            print(f"  FAIL {name}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
            failed += 1
    print()
    print(f"Total: {len(tests)} | Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
