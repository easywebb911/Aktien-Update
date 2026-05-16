"""Mock-Tests fuer ntfy Unicode-Encoding-Fix (16.05.2026, PR #168 Punkt D).

Hintergrund:
Manueller Workflow-Trigger 16.05.2026 10:31 zeigte echte Ursache des
fehlenden Pushes:
    WARNING ntfy-Push Netzwerk-Fehler UnicodeEncodeError:
    'latin-1' codec can't encode characters in position 0-1:
    ordinal not in range(256)

Title-Strings wie "⚠️ Health-Check-Digest" / "✅ Health-Check OK" /
"📭 Health-Check ohne Daten" enthalten Emojis. Header-Encoding ist
laut RFC 7230 latin-1 — requests-Stack scheitert beim Serialisieren.

Fix: Wechsel auf ntfy JSON-API. Topic, Title, Body, Priority, Tags
alles im JSON-Body — keine HTTP-Header mit Emojis mehr.

Tests:
  1. Body mit Emojis -> kein UnicodeEncodeError (JSON umgeht latin-1)
  2. Title mit Emojis -> kein UnicodeEncodeError
  3. Body + Title beide nur ASCII -> funktioniert weiter
  4. Edge: leerer Body
  5. Edge: nur Emojis im Body
  6. Tags-String wird zu Array gesplittet ("warning" -> ["warning"])
  7. Tags=None -> kein tags-Feld im Payload
  8. Tags mit Komma -> Multi-Element-Array
  9. Source-Inspektion: POST geht zu NTFY_URL (kein /{topic} Suffix)
 10. Source-Inspektion: json=payload statt headers={Title:...}
 11. Source-Inspektion: topic im JSON-Body
 12. NTFY disabled -> kein POST, return False
 13. requests fehlt -> kein POST, return False
 14. HTTP 4xx -> return False
 15. HTTP 2xx -> return True
"""
from __future__ import annotations

import pathlib
import sys
from unittest.mock import patch, MagicMock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCRIPT_SRC = (ROOT / "scripts" / "health_check_digest.py").read_text(encoding="utf-8")

import health_check_digest as hcd  # type: ignore


# Sammelt POST-Args fuer Inspektion
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
    """Kontextmanager-Stil-Replacement: patch NTFY_TOPIC/ENABLED auf aktiv."""
    return [
        patch.object(hcd, "NTFY_TOPIC", "test-topic-xyz"),
        patch.object(hcd, "NTFY_ENABLED", True),
    ]


def _enter(patches):
    return [p.__enter__() for p in patches]

def _exit(patches):
    for p in patches:
        p.__exit__(None, None, None)


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_09_post_uses_ntfy_url_no_topic_suffix() -> None:
    # Suche nach requests.post-Aufruf in _ntfy_send
    block_start = SCRIPT_SRC.find("def _ntfy_send(")
    block_end = SCRIPT_SRC.find("\ndef ", block_start + 10)
    block = SCRIPT_SRC[block_start:block_end]
    # POST geht zu NTFY_URL ohne /{NTFY_TOPIC}-Suffix
    assert "requests.post(\n            NTFY_URL," in block or \
           "requests.post(NTFY_URL," in block or \
           "url=NTFY_URL" in block, \
        "POST geht nicht zu NTFY_URL als Root"
    # Alter URL-Pattern darf nicht mehr da sein
    assert "{NTFY_URL}/{NTFY_TOPIC}" not in block, \
        "Alter URL-Pattern {NTFY_URL}/{NTFY_TOPIC} noch vorhanden"


def test_10_uses_json_payload_not_headers() -> None:
    block_start = SCRIPT_SRC.find("def _ntfy_send(")
    block_end = SCRIPT_SRC.find("\ndef ", block_start + 10)
    block = SCRIPT_SRC[block_start:block_end]
    assert "json=payload" in block, "POST nutzt nicht json=payload"
    # Alter Title-in-Header darf nicht mehr da sein
    assert '"Title": title' not in block, \
        "Alter Title-Header noch vorhanden"


def test_11_topic_in_json_body() -> None:
    block_start = SCRIPT_SRC.find("def _ntfy_send(")
    block_end = SCRIPT_SRC.find("\ndef ", block_start + 10)
    block = SCRIPT_SRC[block_start:block_end]
    assert '"topic":' in block and "NTFY_TOPIC" in block, \
        "topic nicht im JSON-Payload"


# ── Funktional: kein UnicodeEncodeError mehr ─────────────────────────────────

def test_01_body_with_emojis_no_unicode_error() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            rc = hcd._ntfy_send(
                title="ASCII-only Title",
                body="⚠️ 7 provider-fails, 2 state-fails 🔴🟡✅📭",
                priority="high",
                tags="warning",
            )
        assert rc is True
        assert len(recorder.calls) == 1
        # JSON payload muss UTF-8-Emojis enthalten
        payload = recorder.calls[0]["json"]
        assert "⚠️" in payload["message"]
    finally:
        _exit(patches)


def test_02_title_with_emojis_no_unicode_error() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            rc = hcd._ntfy_send(
                title="⚠️ Health-Check-Digest",
                body="ASCII body",
                priority="high",
                tags="warning",
            )
        assert rc is True
        payload = recorder.calls[0]["json"]
        assert payload["title"] == "⚠️ Health-Check-Digest"
    finally:
        _exit(patches)


def test_03_ascii_only_still_works() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            rc = hcd._ntfy_send(
                title="Health-Check OK",
                body="0 fails, 19 runs",
                priority="default",
                tags=None,
            )
        assert rc is True
        payload = recorder.calls[0]["json"]
        assert payload["title"] == "Health-Check OK"
        assert "tags" not in payload   # None → kein tags-Feld
    finally:
        _exit(patches)


def test_04_empty_body() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            rc = hcd._ntfy_send(title="t", body="", priority="default", tags=None)
        assert rc is True
        assert recorder.calls[0]["json"]["message"] == ""
    finally:
        _exit(patches)


def test_05_emoji_only_body() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            rc = hcd._ntfy_send(title="t", body="🔴🟡✅📭⚠️🚀",
                                  priority="high", tags=None)
        assert rc is True
        assert recorder.calls[0]["json"]["message"] == "🔴🟡✅📭⚠️🚀"
    finally:
        _exit(patches)


def test_06_single_tag_becomes_array() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            hcd._ntfy_send(title="t", body="b", priority="high", tags="warning")
        payload = recorder.calls[0]["json"]
        assert payload["tags"] == ["warning"]
    finally:
        _exit(patches)


def test_07_no_tags_no_field() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            hcd._ntfy_send(title="t", body="b", priority="default", tags=None)
        assert "tags" not in recorder.calls[0]["json"]
    finally:
        _exit(patches)


def test_08_multi_tag_splits_array() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            hcd._ntfy_send(title="t", body="b", priority="high",
                            tags="warning,rotating_light")
        payload = recorder.calls[0]["json"]
        assert payload["tags"] == ["warning", "rotating_light"]
    finally:
        _exit(patches)


def test_12_ntfy_disabled_no_post() -> None:
    with patch.object(hcd, "NTFY_TOPIC", ""), \
         patch.object(hcd, "NTFY_ENABLED", False):
        recorder = _PostRecorder()
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            rc = hcd._ntfy_send(title="t", body="b", priority="default", tags=None)
        assert rc is False
        assert len(recorder.calls) == 0


def test_13_requests_missing_no_post() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        with patch.object(hcd, "requests", None):
            rc = hcd._ntfy_send(title="t", body="b", priority="default", tags=None)
        assert rc is False
    finally:
        _exit(patches)


def test_14_http_4xx_returns_false() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder(status_code=429, text="rate limited")
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            rc = hcd._ntfy_send(title="t", body="b", priority="high", tags=None)
        assert rc is False
        assert len(recorder.calls) == 1   # POST wurde versucht
    finally:
        _exit(patches)


def test_15_http_2xx_returns_true() -> None:
    patches = _patch_ntfy_active()
    _enter(patches)
    try:
        recorder = _PostRecorder(status_code=200, text="ok")
        with patch.object(hcd, "requests", MagicMock(post=recorder)):
            rc = hcd._ntfy_send(title="t", body="b", priority="default", tags=None)
        assert rc is True
    finally:
        _exit(patches)


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 Body mit Emojis (UTF-8 OK)",              test_01_body_with_emojis_no_unicode_error),
        ("02 Title mit Emojis (UTF-8 OK)",             test_02_title_with_emojis_no_unicode_error),
        ("03 ASCII-only weiterhin OK",                 test_03_ascii_only_still_works),
        ("04 Edge: leerer Body",                       test_04_empty_body),
        ("05 Edge: nur Emojis im Body",                test_05_emoji_only_body),
        ("06 Single Tag → Array",                      test_06_single_tag_becomes_array),
        ("07 Tags=None → kein Feld",                   test_07_no_tags_no_field),
        ("08 Multi-Tag-Split",                         test_08_multi_tag_splits_array),
        ("09 POST URL ohne /{topic}",                  test_09_post_uses_ntfy_url_no_topic_suffix),
        ("10 json=payload statt Title-Header",         test_10_uses_json_payload_not_headers),
        ("11 topic im JSON-Body",                      test_11_topic_in_json_body),
        ("12 NTFY disabled → kein POST",               test_12_ntfy_disabled_no_post),
        ("13 requests=None → kein POST",               test_13_requests_missing_no_post),
        ("14 HTTP 4xx → False",                        test_14_http_4xx_returns_false),
        ("15 HTTP 2xx → True",                         test_15_http_2xx_returns_true),
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
