"""The pieces that only matter once the app leaves a laptop.

Each of these is a way a deploy can look healthy and be quietly broken:
sentiment that silently reports NEUTRAL, a translation service that refuses
datacentre IPs, a rate limit mistaken for an outage, an email that is never
sent, a static file server that hands out files it should not.

Written without fixtures on purpose — plain functions with try/finally —
so the file has no dependency beyond pytest itself.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

import i18n
import llm
import safety
import sentiment
from config import settings
from wordpiece import WordPieceTokenizer

BACKEND = Path(__file__).resolve().parent.parent
VOCAB = BACKEND / "models" / "vocab.txt"


@contextmanager
def patched(obj, **values):
    """Set attributes for the duration of a block, then put them back."""
    missing = object()
    before = {name: getattr(obj, name, missing) for name in values}
    for name, value in values.items():
        setattr(obj, name, value)
    try:
        yield
    finally:
        for name, value in before.items():
            if value is missing:
                delattr(obj, name)
            else:
                setattr(obj, name, value)


# ------------------------------------------------------------- tokenizer
def test_tokenizer_matches_bert_reference_ids():
    """The ids BERT's own documentation gives for bert-base-uncased."""
    tok = WordPieceTokenizer(VOCAB)
    assert tok.encode("Hello, my dog is cute") == [
        101, 7592, 1010, 2026, 3899, 2003, 10140, 102,
    ]
    assert tok.encode("hello world") == [101, 7592, 2088, 102]


def test_tokenizer_wordpiece_and_normalisation():
    tok = WordPieceTokenizer(VOCAB)
    assert tok.tokenize("unaffable") == ["una", "##ffa", "##ble"]
    assert tok.tokenize("Café NAÏVE") == ["cafe", "naive"]
    assert tok.tokenize("can't!") == ["can", "'", "t", "!"]


def test_tokenizer_truncates_and_keeps_special_tokens():
    tok = WordPieceTokenizer(VOCAB)
    ids = tok.encode("word " * 2000, max_length=64)
    assert len(ids) == 64
    assert ids[0] == tok.cls_id and ids[-1] == tok.sep_id


def test_tokenizer_survives_hostile_input():
    tok = WordPieceTokenizer(VOCAB)
    assert tok.encode("") == [tok.cls_id, tok.sep_id]
    assert tok.encode("\x00�​") == [tok.cls_id, tok.sep_id]
    assert tok.tokenize("a" * 500) == ["[UNK]"]


# ------------------------------------------------------------- sentiment
def test_softmax_picks_the_larger_logit():
    labels = {0: "NEGATIVE", 1: "POSITIVE"}
    label, score = sentiment._softmax_top([-3.2, 4.1], labels)
    assert label == "POSITIVE" and score > 0.99
    label, score = sentiment._softmax_top([2.0, -2.0], labels)
    assert label == "NEGATIVE" and 0.97 < score < 0.99


def test_low_confidence_becomes_neutral():
    with patched(sentiment, _predict=lambda text: ("POSITIVE", 0.62)):
        assert sentiment.classify("it was fine I guess") == ("NEUTRAL", 0.62)
    with patched(sentiment, _predict=lambda text: ("NEGATIVE", 0.97)):
        assert sentiment.classify("I hated it") == ("NEGATIVE", 0.97)


def test_sentiment_never_raises_into_the_chat_path():
    def explode(text):
        raise RuntimeError("model fell over")

    with patched(sentiment, _predict=explode):
        assert sentiment.classify("anything") == ("NEUTRAL", 0.0)
    assert sentiment.classify("   ") == ("NEUTRAL", 0.0)


def test_sentiment_reports_when_it_is_degraded():
    with patched(sentiment, _predict=None, _backend="unavailable", _load_error="no model"):
        assert sentiment.classify("I love this") == ("NEUTRAL", 0.0)
        state = sentiment.status()
        assert state["ready"] is False and state["error"] == "no model"


# ----------------------------------------------------------- translation
def test_translation_falls_through_google_to_the_llm():
    calls = []

    def google(text, source, target):
        calls.append("google")
        return None  # what a blocked datacentre IP looks like

    def model(text, source, target):
        calls.append("llm")
        return "I am sad"

    with patched(i18n, _google=google, _llm=model), patched(settings, TRANSLATION_PROVIDER="auto"):
        assert i18n.translate("मैं उदास हूँ", "hi", "en") == "I am sad"
    assert calls == ["google", "llm"]


def test_translation_never_fails_the_request():
    nothing = lambda text, source, target: None  # noqa: E731
    with patched(i18n, _google=nothing, _llm=nothing), patched(settings, TRANSLATION_PROVIDER="auto"):
        assert i18n.translate("मैं उदास हूँ", "hi", "en") == "मैं उदास हूँ"


def test_translation_is_skipped_when_not_needed():
    def boom(text, source, target):
        raise AssertionError("should not be called")

    with patched(i18n, _google=boom, _llm=boom):
        assert i18n.translate("hello", "en", "en") == "hello"
        assert i18n.translate("", "hi", "en") == ""
        with patched(settings, TRANSLATION_PROVIDER="off"):
            assert i18n.translate("नमस्ते", "hi", "en") == "नमस्ते"


def test_language_codes():
    assert i18n.language_of("hi-IN") == "hi"
    assert i18n.language_of("mr-IN") == "mr"
    assert i18n.language_of("en-US") == "en"
    assert i18n.language_of(None) == "en"


# --------------------------------------------------- localized crisis text
@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_crisis_response_exists_in_every_supported_language(lang):
    reply = safety.crisis_response("IN", lang)
    assert "14416" in reply and "1800-599-0019" in reply and "112" in reply
    assert "{resources}" not in reply


def test_crisis_response_is_actually_translated():
    assert "कृपया" in safety.crisis_response("IN", "hi")
    assert "कृपया" in safety.crisis_response("IN", "mr")
    assert safety.crisis_response("IN", "hi") != safety.crisis_response("IN", "mr")


def test_unknown_language_falls_back_to_english():
    assert safety.crisis_response("IN", "xx") == safety.crisis_response("IN", "en")
    assert "14416" in safety.append_resources("reply", "IN", "xx")


DEVANAGARI = [
    ("मैं आज अपनी जान दे दूँगा", "IMMINENT"),
    ("आज मैं आत्महत्या करूँगा", "IMMINENT"),
    ("मैं खुद को खत्म कर दूँगा", "IMMINENT"),
    ("मी स्वतःला संपवणार आहे", "IMMINENT"),
    ("मी आज जीव देणार", "IMMINENT"),
    ("मैं मरना चाहता हूँ", "IDEATION"),
    ("आत्महत्या के विचार आते हैं", "IDEATION"),
    ("मला जगायचं नाही", "IDEATION"),
]


@pytest.mark.parametrize("text,tier", DEVANAGARI)
def test_devanagari_risk_is_caught_without_translation(text, tier):
    """If the translation service is down, the original script is all the
    classifier gets. It still has to work."""
    assert safety.assess_risk(text).tier.name == tier


ORDINARY_HINDI_MARATHI = [
    "काम खत्म करना है आज",
    "आज मैंने सारा काम खत्म कर दिया",
    "kaam khatam karna hai aaj",
    "project khatam kar dunga kal tak",
    "मुझे जानकारी दे दो",
    "मी आज काम संपवणार आहे",
    "आज का दिन अच्छा था",
]


@pytest.mark.parametrize("text", ORDINARY_HINDI_MARATHI)
def test_finishing_work_is_not_a_crisis(text):
    """'khatam karna' means 'to finish'. The pattern used to fire on someone
    saying they had work to finish — and sent them the crisis response."""
    assert safety.assess_risk(text).tier is safety.RiskTier.NONE


# ------------------------------------------------------------ llm client
class _Response:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _ok(text):
    return _Response(200, {"choices": [{"message": {"content": text}}]})


def _run_llm(responses, **config):
    seen = []
    queue = iter(responses)

    def post(url, json=None, headers=None, timeout=None):
        seen.append(json["model"])
        return next(queue)

    fresh = llm.CircuitBreaker()
    with patched(llm.requests, post=post), patched(llm, breaker=fresh), patched(
        settings, LLM_MODEL="big", LLM_FALLBACK_MODEL=config.get("fallback", "small")
    ):
        try:
            return llm.chat([{"role": "user", "content": "hi"}]), seen, fresh
        except llm.LLMUnavailable as exc:
            return exc, seen, fresh


def test_rate_limit_falls_back_to_the_second_model():
    result, seen, breaker = _run_llm([_Response(429, headers={"retry-after": "30"}), _ok("hello")])
    assert result == "hello" and seen == ["big", "small"]
    assert breaker._failures == 0


def test_rate_limit_does_not_trip_the_breaker():
    """Being told to slow down is not the provider being down."""
    result, seen, breaker = _run_llm(
        [_Response(429), _Response(429, headers={"retry-after": "0"}), _Response(429)]
    )
    assert isinstance(result, llm.LLMUnavailable)
    assert breaker._failures == 0 and not breaker.is_open


def test_real_failures_do_trip_the_breaker():
    result, seen, breaker = _run_llm([_Response(500)])
    assert isinstance(result, llm.LLMUnavailable) and breaker._failures == 1


def test_hosted_endpoints_are_not_warmed_up():
    with patched(settings, LLM_BASE_URL="https://api.groq.com/openai/v1"):
        assert llm.is_local() is False
    with patched(settings, LLM_BASE_URL="http://127.0.0.1:11434/v1"):
        assert llm.is_local() is True


# ------------------------------------------------------- static serving
def _site():
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    os.environ["MINDWELL_SKIP_APP_BUILD"] = "1"
    import server

    root = Path(tempfile.mkdtemp())
    build = root / "build"
    (build / "static" / "js").mkdir(parents=True)
    (build / "index.html").write_text("<html>app</html>")
    (build / "static" / "js" / "main.abc.js").write_text("console.log(1);" * 300)
    (root / "secret.txt").write_text("SECRET")

    async def echo(request):
        return JSONResponse({"path": request.url.path})

    api = Starlette(routes=[Route("/login", echo, methods=["POST"])])
    app = server.create_app(api, health=lambda: {"status": "ok"}, static_dir=build, hsts=True)
    return TestClient(app)


def test_api_is_mounted_under_api_and_the_app_at_the_root():
    client = _site()
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/api/login").json() == {"path": "/api/login"}
    assert client.get("/").text == "<html>app</html>"
    assert client.get("/any/client/route").text == "<html>app</html>"


def test_hashed_assets_are_cached_and_index_is_not():
    client = _site()
    asset = client.get("/static/js/main.abc.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
    assert client.get("/").headers["cache-control"] == "no-cache"


def test_missing_asset_is_a_404_not_the_app_shell():
    """Answering index.html for a missing .js makes the browser run HTML."""
    assert _site().get("/static/js/gone.js").status_code == 404


@pytest.mark.parametrize("path", ["/../secret.txt", "/..%2fsecret.txt", "/%2e%2e/secret.txt"])
def test_static_server_cannot_be_walked_out_of(path):
    response = _site().get(path)
    assert "SECRET" not in response.text


def test_security_headers_are_set():
    headers = _site().get("/").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "max-age" in headers["strict-transport-security"]
