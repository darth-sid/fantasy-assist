from assembler import assemble
from contracts import ContextBlock


def test_assemble_joins_ok_blocks_content():
    blocks = [
        ContextBlock(source="a", status="ok", content="BLOCK A", as_of="Week 1"),
        ContextBlock(source="b", status="ok", content="BLOCK B", as_of="Week 1"),
    ]
    assert assemble(blocks) == "BLOCK A\n\nBLOCK B"


def test_assemble_renders_empty_status_explicitly():
    blocks = [ContextBlock(source="recent_stats", status="empty", content="", as_of="Week 1")]
    assert assemble(blocks) == "RECENT STATS: no data found"


def test_assemble_renders_error_status_explicitly():
    blocks = [ContextBlock(source="recent_stats", status="error", content="", as_of="Week 1")]
    assert assemble(blocks) == "RECENT STATS: fetch error"


def test_assemble_mixes_statuses_without_dropping_any():
    blocks = [
        ContextBlock(source="ok_source", status="ok", content="OK CONTENT", as_of="Week 1"),
        ContextBlock(source="empty_source", status="empty", content="", as_of="Week 1"),
        ContextBlock(source="error_source", status="error", content="", as_of="Week 1"),
    ]
    result = assemble(blocks)
    assert "OK CONTENT" in result
    assert "EMPTY SOURCE: no data found" in result
    assert "ERROR SOURCE: fetch error" in result
