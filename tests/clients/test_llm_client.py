import pytest

import ffassistant.clients.llm_client as llm_client_module
from ffassistant.clients.anthropic_client import AnthropicClient, _system_block
from ffassistant.clients.llm_client import SystemBlock, get_llm_client


def test_factory_returns_anthropic_client():
    assert isinstance(get_llm_client(), AnthropicClient)


def test_factory_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(llm_client_module, "LLM_PROVIDER", "nope")

    with pytest.raises(ValueError, match="nope"):
        get_llm_client()


def test_cached_block_gets_cache_control():
    assert _system_block(SystemBlock(text="roster", cache=True)) == {
        "type": "text",
        "text": "roster",
        "cache_control": {"type": "ephemeral"},
    }


def test_uncached_block_has_no_cache_control():
    assert _system_block(SystemBlock(text="instructions")) == {"type": "text", "text": "instructions"}
