"""Smoke tests for the MCP server tool functions."""
import pytest

from mcp_markdown.server import markdown_structure, markdown_read, markdown_update, markdown_move

SAMPLE = """\
Preamble.

# Alpha

Alpha body.

## Alpha Sub

Sub body.

# Beta

Beta body.
"""


@pytest.fixture
def doc(tmp_path):
    p = tmp_path / "test.md"
    p.write_text(SAMPLE)
    return str(p)


async def test_structure_shows_preamble(doc):
    result = await markdown_structure(doc)
    assert 'preamble' in result


async def test_structure_shows_sections(doc):
    result = await markdown_structure(doc)
    assert 'Alpha' in result
    assert 'Beta' in result
    assert 'Alpha Sub' in result


async def test_structure_shows_word_counts(doc):
    result = await markdown_structure(doc)
    assert 'words' in result


async def test_structure_shows_checksums(doc):
    result = await markdown_structure(doc)
    # Each section line contains an 8-char checksum in brackets
    import re
    assert re.search(r'\[[A-Za-z0-9_-]{8}\]', result)


# ---------------------------------------------------------------------------
# markdown_read
# ---------------------------------------------------------------------------

async def test_read_returns_dict(doc):
    result = await markdown_read(doc)
    assert isinstance(result, dict)
    assert 'content' in result
    assert 'checksum' in result


async def test_read_full_document(doc):
    result = await markdown_read(doc)
    assert 'Alpha body.' in result['content']
    assert 'Beta body.' in result['content']


async def test_read_section_recursive(doc):
    result = await markdown_read(doc, section=["Alpha"])
    assert 'Alpha body.' in result['content']
    assert 'Sub body.' in result['content']
    assert '## Alpha Sub' in result['content']


async def test_read_section_recursive_includes_sections(doc):
    result = await markdown_read(doc, section=["Alpha"])
    assert 'sections' in result
    assert 'Alpha Sub' in result['sections']
    assert 'checksum' in result['sections']['Alpha Sub']


async def test_read_section_non_recursive_no_sections_key(doc):
    result = await markdown_read(doc, section=["Alpha"], recursive=False)
    assert 'sections' not in result


async def test_read_section_non_recursive(doc):
    result = await markdown_read(doc, section=["Alpha"], recursive=False)
    assert result['content'] == 'Alpha body.'


async def test_read_checksum_is_eight_chars(doc):
    result = await markdown_read(doc, section=["Alpha"])
    assert len(result['checksum']) == 8


async def test_read_missing_section_raises(doc):
    with pytest.raises(ValueError):
        await markdown_read(doc, section=["Nonexistent"])


# ---------------------------------------------------------------------------
# markdown_update — checksum behaviour
# ---------------------------------------------------------------------------

async def test_update_creates_file_if_missing(tmp_path):
    p = str(tmp_path / "new.md")
    cs = await markdown_update(p, section=["Hello"], content="World.")
    result = await markdown_read(p, section=["Hello"], recursive=False)
    assert result['content'] == "World."
    assert cs is not None and len(cs) == 8


async def test_update_creates_section_no_checksum_required(doc):
    cs = await markdown_update(doc, section=["Gamma"], content="Gamma body.")
    result = await markdown_read(doc, section=["Gamma"], recursive=False)
    assert result['content'] == "Gamma body."
    assert cs == result['checksum']


async def test_update_returns_new_checksum(doc):
    read = await markdown_read(doc, section=["Beta"], recursive=False)
    cs = await markdown_update(doc, section=["Beta"], content="New beta.", checksum=read['checksum'])
    assert cs is not None and len(cs) == 8


async def test_update_requires_checksum_for_existing_section(doc):
    with pytest.raises(ValueError, match='checksum'):
        await markdown_update(doc, section=["Beta"], content="New beta.")


async def test_update_modifies_section_with_correct_checksum(doc):
    read = await markdown_read(doc, section=["Beta"], recursive=False)
    await markdown_update(doc, section=["Beta"], content="New beta.", checksum=read['checksum'])
    result = await markdown_read(doc, section=["Beta"], recursive=False)
    assert result['content'] == "New beta."


async def test_update_rejects_wrong_checksum(doc):
    with pytest.raises(ValueError):
        await markdown_update(doc, section=["Beta"], content="New beta.", checksum="ZZZZZZZZ")


async def test_update_non_recursive_delete_clears_content(doc):
    read = await markdown_read(doc, section=["Alpha"], recursive=False)
    cs = await markdown_update(doc, section=["Alpha"], content="", checksum=read['checksum'])
    result = await markdown_read(doc, section=["Alpha"], recursive=False)
    assert result['content'] == ""
    # Children must still exist
    struct = await markdown_structure(doc)
    assert 'Alpha Sub' in struct
    # New checksum returned
    assert cs is not None


async def test_update_recursive_delete_uses_recursive_checksum(doc):
    read = await markdown_read(doc, section=["Alpha"])
    cs = await markdown_update(doc, section=["Alpha"], checksum=read['checksum'])
    assert cs is None
    struct = await markdown_structure(doc)
    assert 'Alpha' not in struct


async def test_update_recursive_delete_wrong_checksum_raises(doc):
    with pytest.raises(ValueError):
        await markdown_update(doc, section=["Alpha"], checksum="ZZZZZZZZ")


# ---------------------------------------------------------------------------
# markdown_move (no checksum)
# ---------------------------------------------------------------------------

async def test_move_to_first(doc):
    await markdown_move(doc, section=["Beta"], after=None)
    result = await markdown_structure(doc)
    lines = [l for l in result.splitlines() if 'Alpha' in l or 'Beta' in l]
    assert lines[0].strip().startswith('- Beta')


async def test_move_after_sibling(doc):
    # Add a second child to Alpha so we have two siblings to reorder
    await markdown_update(doc, section=["Alpha", "Alpha Sub2"], content="Sub2.")
    # Now move Alpha Sub after Alpha Sub2 (reversing their order)
    await markdown_move(doc, section=["Alpha", "Alpha Sub"], after="Alpha Sub2")
    result = await markdown_structure(doc)
    lines = result.splitlines()
    sub_lines = [l for l in lines if 'Alpha Sub' in l]
    idx_sub = next(i for i, l in enumerate(sub_lines) if 'Alpha Sub2' not in l)
    idx_sub2 = next(i for i, l in enumerate(sub_lines) if 'Alpha Sub2' in l)
    assert idx_sub > idx_sub2
