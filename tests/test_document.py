"""Tests for the document module."""
import pytest

from mcp_markdown.document import Section, parse, load, save, validate_checksum


# ---------------------------------------------------------------------------
# parse()
# ---------------------------------------------------------------------------

SIMPLE_DOC = """\
Preamble text.

# H1

H1 body.

## H1.1

H1.1 body.

## H1.2

H1.2 body.

# H2

H2 body.
"""

CODE_BLOCK_DOC = """\
# Real heading

```markdown
# Not a heading
## Also not a heading
```

After code block.
"""

SETEXT_DOC = """\
Preamble.

Top level
=========

Top content.

Sub section
-----------

Sub content.
"""

ATX_TRAILING_HASHES_DOC = """\
# Title with trailing hashes ##

Body text.
"""


def test_parse_preamble():
    root = parse(SIMPLE_DOC)
    assert root.content == "Preamble text."


def test_parse_top_level_sections():
    root = parse(SIMPLE_DOC)
    assert list(root.children.keys()) == ["H1", "H2"]


def test_parse_nested_sections():
    root = parse(SIMPLE_DOC)
    assert list(root.children["H1"].children.keys()) == ["H1.1", "H1.2"]


def test_parse_section_content():
    root = parse(SIMPLE_DOC)
    assert root.children["H1"].content == "H1 body."
    assert root.children["H1"].children["H1.1"].content == "H1.1 body."
    assert root.children["H2"].content == "H2 body."


def test_parse_ignores_headings_in_code_blocks():
    root = parse(CODE_BLOCK_DOC)
    # Only the real heading should be parsed; code block contents must be ignored
    assert list(root.children.keys()) == ["Real heading"]
    assert "Not a heading" not in root.children
    assert "Also not a heading" not in root.children


def test_parse_code_block_preserved_in_content():
    root = parse(CODE_BLOCK_DOC)
    section = root.children["Real heading"]
    assert "```" in section.content
    assert "# Not a heading" in section.content


def test_parse_setext_headings():
    root = parse(SETEXT_DOC)
    assert root.content == "Preamble."
    assert "Top level" in root.children
    assert "Sub section" in root.children["Top level"].children


def test_parse_atx_trailing_hashes_stripped():
    root = parse(ATX_TRAILING_HASHES_DOC)
    assert "Title with trailing hashes" in root.children
    assert "Title with trailing hashes ##" not in root.children


def test_parse_no_preamble():
    doc = "# Only heading\n\nContent.\n"
    root = parse(doc)
    assert root.content == ""
    assert "Only heading" in root.children


def test_parse_empty_document():
    root = parse("")
    assert root.content == ""
    assert root.children == {}


def test_parse_no_headings():
    root = parse("Just some text.\n\nMore text.")
    assert root.content == "Just some text.\n\nMore text."
    assert root.children == {}


SKIPPED_LEVEL_DOC = """\
# Top

Top content.

### Skipped

Deep content.
"""


def test_parse_skipped_level_section_is_child_of_nearest_ancestor():
    root = parse(SKIPPED_LEVEL_DOC)
    assert "Skipped" in root.children["Top"].children


def test_parse_skipped_level_content_preserved():
    root = parse(SKIPPED_LEVEL_DOC)
    assert root.children["Top"].children["Skipped"].content == "Deep content."


def test_render_skipped_level_roundtrip():
    """H3 under H1 must stay H3 on output, not collapse to H2."""
    root = parse(SKIPPED_LEVEL_DOC)
    rendered = root.render()
    # Must be exactly H3, not normalised to H2
    assert "\n### Skipped" in rendered
    assert "\n## Skipped\n" not in rendered


def test_render_skipped_level_full_roundtrip():
    """Parse → render → re-parse must preserve tree structure."""
    root = parse(SKIPPED_LEVEL_DOC)
    root2 = parse(root.render())
    assert "Skipped" in root2.children["Top"].children
    assert root2.children["Top"].children["Skipped"].content == "Deep content."


def test_insert_intermediate_level_causes_takeover():
    """
    Inserting an H2 between an H1 and its H3 child, then re-rendering and
    re-parsing, must cause the H3 to be re-parented under the new H2.
    """
    root = parse(SKIPPED_LEVEL_DOC)
    root.update(["Top", "Middle"], "Middle content.")
    root.move(["Top", "Middle"], None)  # move before Skipped
    rendered = root.render()
    # H2 must appear before H3 in the output
    assert rendered.index("## Middle") < rendered.index("### Skipped")
    # After re-parsing, Skipped should be a child of Middle, not of Top
    root2 = parse(rendered)
    assert "Skipped" not in root2.children["Top"].children
    assert "Skipped" in root2.children["Top"].children["Middle"].children


# ---------------------------------------------------------------------------
# Section.empty()
# ---------------------------------------------------------------------------


def test_empty_true_when_no_content_no_children():
    s = Section()
    assert s.empty()


def test_empty_false_when_has_content():
    s = Section(content="some text")
    assert not s.empty()


def test_empty_false_when_has_children():
    s = Section(children={"Child": Section()})
    assert not s.empty()


# ---------------------------------------------------------------------------
# Section.get()
# ---------------------------------------------------------------------------


def test_get_empty_path_returns_self():
    root = parse(SIMPLE_DOC)
    assert root.get([]) is root


def test_get_top_level():
    root = parse(SIMPLE_DOC)
    assert root.get(["H1"]) is root.children["H1"]


def test_get_nested():
    root = parse(SIMPLE_DOC)
    assert root.get(["H1", "H1.1"]) is root.children["H1"].children["H1.1"]


def test_get_missing_returns_none():
    root = parse(SIMPLE_DOC)
    assert root.get(["Nonexistent"]) is None
    assert root.get(["H1", "Nonexistent"]) is None


# ---------------------------------------------------------------------------
# Section.update()
# ---------------------------------------------------------------------------


def test_update_existing_content():
    root = parse(SIMPLE_DOC)
    root.update(["H1"], "New H1 body.")
    assert root.children["H1"].content == "New H1 body."


def test_update_preserves_children():
    root = parse(SIMPLE_DOC)
    root.update(["H1"], "New H1 body.")
    assert "H1.1" in root.children["H1"].children


def test_update_creates_new_section():
    root = parse(SIMPLE_DOC)
    root.update(["H3"], "H3 body.")
    assert "H3" in root.children
    assert root.children["H3"].content == "H3 body."


def test_update_creates_intermediate_sections():
    root = parse(SIMPLE_DOC)
    root.update(["New", "Deep"], "Deep body.")
    assert "New" in root.children
    assert "Deep" in root.children["New"].children


def test_update_new_section_appended_last():
    root = parse(SIMPLE_DOC)
    root.update(["H3"], "H3 body.")
    assert list(root.children.keys())[-1] == "H3"


def test_update_delete_section():
    root = parse(SIMPLE_DOC)
    root.update(["H1", "H1.1"], None)
    assert "H1.1" not in root.children["H1"].children


def test_update_delete_also_removes_children():
    root = parse(SIMPLE_DOC)
    root.update(["H1"], None)
    assert "H1" not in root.children


def test_update_delete_missing_raises():
    root = parse(SIMPLE_DOC)
    with pytest.raises(KeyError):
        root.update(["Nonexistent"], None)


def test_update_empty_path_sets_root_content():
    root = parse(SIMPLE_DOC)
    root.update([], "New preamble.")
    assert root.content == "New preamble."


# ---------------------------------------------------------------------------
# Section.move()
# ---------------------------------------------------------------------------


def test_move_to_first():
    root = parse(SIMPLE_DOC)
    root.move(["H2"], None)
    assert list(root.children.keys())[0] == "H2"


def test_move_after_sibling():
    root = parse(SIMPLE_DOC)
    # H1.2 is already after H1.1; move H1.1 after H1.2
    root.move(["H1", "H1.1"], "H1.2")
    keys = list(root.children["H1"].children.keys())
    assert keys.index("H1.1") > keys.index("H1.2")


def test_move_preserves_other_sections():
    root = parse(SIMPLE_DOC)
    root.move(["H2"], None)
    assert "H1" in root.children


def test_move_missing_section_raises():
    root = parse(SIMPLE_DOC)
    with pytest.raises(KeyError):
        root.move(["Nonexistent"], None)


def test_move_missing_after_raises():
    root = parse(SIMPLE_DOC)
    with pytest.raises(KeyError):
        root.move(["H1"], "Nonexistent")


def test_move_empty_path_raises():
    root = parse(SIMPLE_DOC)
    with pytest.raises(ValueError):
        root.move([], None)


# ---------------------------------------------------------------------------
# Section.structure()
# ---------------------------------------------------------------------------


def test_structure_contains_headings():
    root = parse(SIMPLE_DOC)
    out = root.structure()
    assert "H1" in out
    assert "H1.1" in out
    assert "H2" in out


def test_structure_shows_word_counts():
    root = parse(SIMPLE_DOC)
    out = root.structure()
    # "H1 body." is 2 words
    assert "2 words" in out


def test_structure_shows_line_counts():
    root = parse(SIMPLE_DOC)
    out = root.structure()
    assert "lines" in out


def test_structure_indents_children():
    root = parse(SIMPLE_DOC)
    lines = root.structure().splitlines()
    h1_line = next(l for l in lines if "H1" in l and "H1.1" not in l and "H1.2" not in l)
    h1_1_line = next(l for l in lines if "H1.1" in l)
    # H1.1 should be indented more than H1
    assert len(h1_1_line) - len(h1_1_line.lstrip()) > len(h1_line) - len(h1_line.lstrip())


# ---------------------------------------------------------------------------
# Section.render()
# ---------------------------------------------------------------------------


def test_render_roundtrip():
    """Parsing and re-rendering should preserve all content."""
    root = parse(SIMPLE_DOC)
    rendered = root.render()
    re_parsed = parse(rendered)
    # Structure and content should be identical
    assert list(re_parsed.children.keys()) == list(root.children.keys())
    assert re_parsed.children["H1"].content == root.children["H1"].content
    assert re_parsed.children["H2"].content == root.children["H2"].content


def test_render_depth_controls_heading_level():
    root = parse(SIMPLE_DOC)
    h1 = root.children["H1"]
    # At depth=1 the children (H1.1, H1.2) should be rendered as ##
    rendered = h1.render(depth=1)
    assert "## H1.1" in rendered
    assert "## H1.2" in rendered


def test_render_includes_content():
    root = parse(SIMPLE_DOC)
    rendered = root.render()
    assert "H1 body." in rendered
    assert "H2 body." in rendered


# ---------------------------------------------------------------------------
# Section.checksum() / validate_checksum()
# ---------------------------------------------------------------------------


def test_checksum_is_eight_chars():
    root = parse(SIMPLE_DOC)
    cs = root.children["H1"].checksum()
    assert len(cs) == 8


def test_checksum_changes_when_content_changes():
    root = parse(SIMPLE_DOC)
    cs_before = root.children["H1"].checksum()
    root.update(["H1"], "Different body.")
    cs_after = root.children["H1"].checksum()
    assert cs_before != cs_after


def test_checksum_local_part_changes_when_content_changes():
    root = parse(SIMPLE_DOC)
    cs_before = root.children["H1"].checksum()
    root.update(["H1"], "Different body.")
    cs_after = root.children["H1"].checksum()
    # Local (chars 0-3) must differ
    assert cs_before[:4] != cs_after[:4]


def test_checksum_recursive_part_changes_when_child_changes():
    root = parse(SIMPLE_DOC)
    cs_before = root.children["H1"].checksum()
    root.update(["H1", "H1.1"], "Different child body.")
    cs_after = root.children["H1"].checksum()
    # Recursive (chars 4-7) must differ; local (chars 0-3) is unchanged
    assert cs_before[4:] != cs_after[4:]
    assert cs_before[:4] == cs_after[:4]


def test_checksum_stable_across_reads():
    root = parse(SIMPLE_DOC)
    cs1 = root.children["H1"].checksum()
    cs2 = root.children["H1"].checksum()
    assert cs1 == cs2


def test_validate_checksum_local_passes():
    root = parse(SIMPLE_DOC)
    section = root.children["H1"]
    validate_checksum(section, section.checksum(), recursive=False)  # must not raise


def test_validate_checksum_recursive_passes():
    root = parse(SIMPLE_DOC)
    section = root.children["H1"]
    validate_checksum(section, section.checksum(), recursive=True)  # must not raise


def test_validate_checksum_local_fails_on_wrong_local():
    root = parse(SIMPLE_DOC)
    section = root.children["H1"]
    bad = "ZZZZ" + section.checksum()[4:]
    with pytest.raises(ValueError):
        validate_checksum(section, bad, recursive=False)


def test_validate_checksum_recursive_fails_on_wrong_recursive():
    root = parse(SIMPLE_DOC)
    section = root.children["H1"]
    bad = section.checksum()[:4] + "ZZZZ"
    with pytest.raises(ValueError):
        validate_checksum(section, bad, recursive=True)


def test_validate_checksum_recursive_ignores_local_mismatch():
    """Recursive validation only checks chars 4-7, not 0-3."""
    root = parse(SIMPLE_DOC)
    section = root.children["H1"]
    # Correct recursive part, wrong local part — recursive validation must pass
    mixed = "ZZZZ" + section.checksum()[4:]
    validate_checksum(section, mixed, recursive=True)  # must not raise


def test_validate_checksum_local_ignores_recursive_mismatch():
    """Local validation only checks chars 0-3, not 4-7."""
    root = parse(SIMPLE_DOC)
    section = root.children["H1"]
    mixed = section.checksum()[:4] + "ZZZZ"
    validate_checksum(section, mixed, recursive=False)  # must not raise


# ---------------------------------------------------------------------------
# load() / save()
# ---------------------------------------------------------------------------


def test_load_save_roundtrip(tmp_path):
    p = tmp_path / "doc.md"
    p.write_text(SIMPLE_DOC)
    root = load(str(p))
    assert root.children["H1"].content == "H1 body."
    save(str(p), root)
    root2 = load(str(p))
    assert root2.children["H1"].content == "H1 body."
