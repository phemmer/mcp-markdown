"""
MCP server exposing markdown document viewing and editing tools.
"""
from typing import Annotated, Any, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from mcp_markdown.document import Section, load, parse, save, validate_checksum

mcp = FastMCP("markdown")

_SECTION_FIELD = Field(
    description=(
        "Path to the target section as a list of heading names, e.g. "
        '["Introduction", "Background"]. Empty list or omitted means the '
        "document root."
    ),
)

_FILE_FIELD = Field(description="Absolute or relative path to the markdown file.")


def _section_checksums(section: Section) -> dict[str, Any]:
    """
    Builds a nested dict of ``{title: {checksum, sections?}}`` for all
    descendants of ``section``.  Used by ``markdown_read`` when recursive.
    """
    result: dict[str, Any] = {}
    for title, child in section.children.items():
        entry: dict[str, Any] = {'checksum': child.checksum()}
        if child.children:
            entry['sections'] = _section_checksums(child)
        result[title] = entry
    return result


@mcp.tool()
async def markdown_structure(
    file_path: Annotated[str, _FILE_FIELD],
) -> str:
    """
    Returns the heading hierarchy of a markdown document as an indented outline.

    Each entry shows the section's checksum, direct content size ``(N lines,
    N words)``.  A ``(preamble)`` line is shown when the document has content
    before the first heading.

    Use this tool first to map the document before reading or editing sections.
    """
    root = load(file_path)
    parts = []
    if root.content:
        line_count = len(root.content.splitlines())
        word_count = len(root.content.split())
        parts.append(f'(preamble: {line_count} lines, {word_count} words)')
    outline = root.structure()
    if outline:
        parts.append(outline)
    return '\n'.join(parts) if parts else '(empty document)'


@mcp.tool()
async def markdown_read(
    file_path: Annotated[str, _FILE_FIELD],
    section: Annotated[Optional[list[str]], _SECTION_FIELD] = None,
    recursive: Annotated[
        bool,
        Field(
            description=(
                "When True (default), return the section rendered as full markdown "
                "including all nested subsections. When False, return only the "
                "immediate body text of the section, with no nested headings."
            )
        ),
    ] = True,
) -> dict[str, Any]:
    """
    Returns the content and checksum of a section in a markdown document.

    Response always includes ``content`` (the section text) and ``checksum``
    (an opaque token for the section's current state).  When ``recursive=true``
    the response also includes a ``sections`` dict that maps each child section
    title to its own ``{checksum, sections?}`` entry, so you can obtain
    checksums for subsections without additional reads.

    When no section path is provided, reads the entire document.
    """
    root = load(file_path)
    path = section or []
    target = root.get(path)
    if target is None:
        raise ValueError(f'Section not found: {path!r}')
    if recursive:
        depth = target._level if target._level is not None else len(path)
        result: dict[str, Any] = {
            'content': target.render(depth=depth),
            'checksum': target.checksum(),
        }
        if target.children:
            result['sections'] = _section_checksums(target)
        return result
    return {'content': target.content, 'checksum': target.checksum()}


@mcp.tool()
async def markdown_update(
    file_path: Annotated[str, _FILE_FIELD],
    section: Annotated[list[str], _SECTION_FIELD],
    content: Annotated[
        Optional[str],
        Field(
            description=(
                "Body text to set for this section. "
                "Pass an empty string to clear the body while keeping child sections. "
                "Omit or pass null to delete the section and all its children."
            )
        ),
    ] = None,
    checksum: Annotated[
        Optional[str],
        Field(
            description=(
                "Checksum of the section as returned by a previous read or structure "
                "call. Required when the section already exists. "
                "For content updates and non-recursive deletes (empty string content) "
                "the local component is validated. "
                "For recursive deletes (null content) the recursive component is validated."
            )
        ),
    ] = None,
) -> Optional[str]:
    """
    Creates, updates, or deletes a section in a markdown document.

    Returns the new checksum when the section still exists after the operation
    (i.e. for creates and content updates), or ``null`` for recursive deletes.

    New sections are appended after any existing siblings. Use
    ``markdown_move`` afterwards to place the section in a specific position.
    """
    try:
        root = load(file_path)
    except FileNotFoundError:
        root = Section()

    existing = root.get(section)
    if existing is not None:
        if checksum is None:
            raise ValueError(
                'checksum is required when updating or deleting an existing section'
            )
        validate_checksum(existing, checksum, recursive=(content is None))

    root.update(section, content)
    save(file_path, root)

    if content is None:
        return None
    updated = root.get(section)
    assert updated is not None
    return updated.checksum()


@mcp.tool()
async def markdown_move(
    file_path: Annotated[str, _FILE_FIELD],
    section: Annotated[list[str], _SECTION_FIELD],
    after: Annotated[
        Optional[str],
        Field(
            description=(
                "Title of the sibling section this section should follow. "
                "Pass null to move the section to the first position."
            )
        ),
    ] = None,
) -> None:
    """
    Moves a section to a different position within its parent.

    Does not affect the section's content or its children.
    """
    root = load(file_path)
    root.move(section, after)
    save(file_path, root)


def main() -> None:
    """Entry point — starts the MCP server."""
    mcp.run()
