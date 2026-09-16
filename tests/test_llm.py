import pytest

from scholar_radar.llm import (
    GEMINI_DEFAULT_MODEL,
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
        if model == "gemini-flash-latest":
            raise LLMError("gemini HTTP 503: high demand")
        return fake_response('{"ok": true}')

    monkeypatch.setattr(llm, "_generate", fake_generate)
    assert llm.complete_json("s", "p") == {"ok": True}
    assert tried == [GEMINI_DEFAULT_MODEL, "gemini-flash-latest", "gemini-3.5-flash-lite"]
    assert llm.model == "gemini-3.5-flash-lite"  # remembered for the rest of the run


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
