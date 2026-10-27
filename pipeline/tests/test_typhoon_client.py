"""The real client against a fake HTTP layer: retries on 429/5xx, stops at once on a bad key."""
import pytest

from thai_ocr_pipeline import ocr as ocr_mod
from thai_ocr_pipeline.ocr import OcrError, TyphoonOCR


class FakeResp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code, self._payload, self.headers = status, payload or {}, headers or {}
        self.text = str(payload)

    def json(self):
        return self._payload


def client_with(responses, monkeypatch):
    c = TyphoonOCR("sk-test", max_retries=4)
    calls = []

    def post(url, json, timeout):
        calls.append(json)
        return responses.pop(0)

    monkeypatch.setattr(c.session, "post", post)
    monkeypatch.setattr(ocr_mod.time, "sleep", lambda s: None)
    return c, calls


def ok(text):
    return FakeResp(200, {"choices": [{"message": {"content": text}}]})


def test_sends_prompt_image_and_settings(monkeypatch):
    c, calls = client_with([ok("# หัวข้อ")], monkeypatch)
    assert c.ocr(b"\xff\xd8jpeg", "a.jpg", 1) == "# หัวข้อ"
    body = calls[0]
    assert body["model"] == "typhoon-ocr" and body["repetition_penalty"] == 1.1
    content = body["messages"][0]["content"]
    assert content[0]["text"].startswith("Extract all text from the image.")
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_retries_rate_limit_then_succeeds(monkeypatch):
    c, calls = client_with([FakeResp(429, headers={"Retry-After": "1"}), FakeResp(503), ok("done")], monkeypatch)
    assert c.ocr(b"x", "a.jpg", 1) == "done"
    assert len(calls) == 3


def test_bad_key_fails_without_retry(monkeypatch):
    c, calls = client_with([FakeResp(401)], monkeypatch)
    with pytest.raises(OcrError, match="API key"):
        c.ocr(b"x", "a.jpg", 1)
    assert len(calls) == 1


def test_gives_up_after_max_retries(monkeypatch):
    c, calls = client_with([FakeResp(500)] * 4, monkeypatch)
    with pytest.raises(OcrError, match="gave up"):
        c.ocr(b"x", "a.jpg", 1)
    assert len(calls) == 4


def test_missing_key_is_reported():
    with pytest.raises(OcrError):
        TyphoonOCR("")
