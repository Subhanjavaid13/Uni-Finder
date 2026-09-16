import pytest

from scholar_radar.llm import (
    DAILY_QUOTA,
    GEMINI_DEFAULT_MODEL,
    GEMINI_FALLBACK_MODELS,
    GeminiLLM,
    LLMError,
    OpenAICompatibleLLM,
    get_llm,
    parse_json_text,
)


def gemini(**kw):
    return GeminiLLM(api_key="k", model=kw.pop("model", GEMINI_DEFAULT_MODEL), min_interval=0)


def fake_response(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def test_gemini_falls_back_when_model_retired_or_overloaded(monkeypatch):
    llm = gemini()
    tried = []

    def fake_generate(model, system, prompt):
        tried.append(model)
        if model == GEMINI_DEFAULT_MODEL:
            raise LLMError("gemini HTTP 404: no longer available")
        if model == GEMINI_FALLBACK_MODELS[0]:
            raise LLMError("gemini HTTP 503: high demand")
        return fake_response('{"ok": true}')

    monkeypatch.setattr(llm, "_generate", fake_generate)
    assert llm.complete_json("s", "p") == {"ok": True}
    assert tried == [GEMINI_DEFAULT_MODEL, GEMINI_FALLBACK_MODELS[0], GEMINI_FALLBACK_MODELS[1]]
    assert llm.model == GEMINI_FALLBACK_MODELS[1]  # remembered for the rest of the run


def test_gemini_switches_model_when_the_daily_free_quota_is_gone(monkeypatch):
    """Free quotas are per model per day, so waiting is useless - move to the next model."""
    llm = gemini()
    tried = []

    def fake_generate(model, system, prompt):
        tried.append(model)
        if model == GEMINI_DEFAULT_MODEL:
            raise LLMError(f"gemini HTTP 429 {DAILY_QUOTA}: quota exceeded")
        return fake_response('{"ok": true}')

    monkeypatch.setattr(llm, "_generate", fake_generate)
    assert llm.complete_json("s", "p") == {"ok": True}
    assert GEMINI_DEFAULT_MODEL in llm.exhausted
    # The exhausted model is not tried again for the rest of the run
    llm.complete_json("s", "p")
    assert tried.count(GEMINI_DEFAULT_MODEL) == 1


def test_daily_quota_detected_from_response_body():
    class Resp:
        status_code = 429
        text = "{}"

        @staticmethod
        def json():
            return {"error": {"details": [
                {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                 "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                                 "quotaValue": "20"}]},
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "32s"}]}}

    assert GeminiLLM._quota_info(Resp) == (True, 32)

    class PerMinute(Resp):
        @staticmethod
        def json():
            return {"error": {"details": [
                {"violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel"}]},
                {"retryDelay": "9s"}]}}

    assert GeminiLLM._quota_info(PerMinute) == (False, 9)


def test_gemini_does_not_retry_other_errors(monkeypatch):
    llm = gemini()
    calls = []

    def fake_generate(model, system, prompt):
        calls.append(model)
        raise LLMError("gemini HTTP 400: bad request")

    monkeypatch.setattr(llm, "_generate", fake_generate)
    with pytest.raises(LLMError, match="400"):
        llm.complete_json("s", "p")
    assert calls == [GEMINI_DEFAULT_MODEL]


def test_gemini_raises_when_every_model_fails(monkeypatch):
    llm = gemini()
    monkeypatch.setattr(llm, "_generate",
                        lambda *a: (_ for _ in ()).throw(LLMError("gemini HTTP 503: busy")))
    with pytest.raises(LLMError, match="503"):
        llm.complete_json("s", "p")


def test_provider_selection(monkeypatch):
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
                 "LLM_PROVIDER", "LLM_MIN_INTERVAL_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    assert get_llm() is None

    monkeypatch.setenv("GEMINI_API_KEY", "x")
    llm = get_llm()
    assert isinstance(llm, GeminiLLM) and llm.model == GEMINI_DEFAULT_MODEL

    monkeypatch.setenv("LLM_PROVIDER", "none")
    assert get_llm() is None

    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "g")
    assert isinstance(get_llm(), OpenAICompatibleLLM)

    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    with pytest.raises(LLMError, match="OPENROUTER_MODEL"):
        get_llm()


def test_parse_json_text_rejects_non_objects():
    with pytest.raises(LLMError):
        parse_json_text("not json at all")
