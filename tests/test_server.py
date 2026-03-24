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


async def test_read_full_document(doc):
    result = await markdown_read(doc)
    assert 'Alpha body.' in result
    assert 'Beta body.' in result


async def test_read_section_recursive(doc):
    result = await markdown_read(doc, section=["Alpha"])
    assert 'Alpha body.' in result
    assert 'Sub body.' in result
    assert '## Alpha Sub' in result


async def test_read_section_non_recursive(doc):
    result = await markdown_read(doc, section=["Alpha"], recursive=False)
    assert result == 'Alpha body.'


async def test_read_missing_section_raises(doc):
    with pytest.raises(ValueError):
        await markdown_read(doc, section=["Nonexistent"])


async def test_update_creates_file_if_missing(tmp_path):
    p = str(tmp_path / "new.md")
    await markdown_update(p, section=["Hello"], content="World.")
    result = await markdown_read(p, section=["Hello"], recursive=False)
    assert result == "World."


async def test_update_creates_section(doc):
    await markdown_update(doc, section=["Gamma"], content="Gamma body.")
    result = await markdown_read(doc, section=["Gamma"], recursive=False)
    assert result == "Gamma body."


async def test_update_modifies_section(doc):
    await markdown_update(doc, section=["Beta"], content="New beta.")
    result = await markdown_read(doc, section=["Beta"], recursive=False)
    assert result == "New beta."


async def test_update_delete_section(doc):
    await markdown_update(doc, section=["Beta"])
    result = await markdown_structure(doc)
    assert 'Beta' not in result


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
