import pytest

from ffassistant.clients.anthropic_client import AnthropicClient, _system_block
from ffassistant.clients.llm_client import SystemBlock, get_llm_client
from tests.helpers import CFG


def test_factory_returns_anthropic_client():
    assert isinstance(get_llm_client(CFG.llm), AnthropicClient)


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="nope"):
        get_llm_client(CFG.llm.model_copy(update={"provider": "nope"}))


def test_cached_block_gets_cache_control():
    assert _system_block(SystemBlock(text="roster", cache=True)) == {
        "type": "text",
        "text": "roster",
        "cache_control": {"type": "ephemeral"},
    }


def test_uncached_block_has_no_cache_control():
    assert _system_block(SystemBlock(text="instructions")) == {"type": "text", "text": "instructions"}
