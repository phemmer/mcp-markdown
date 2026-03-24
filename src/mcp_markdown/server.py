"""
MCP server exposing markdown document viewing and editing tools.
"""
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from mcp_markdown.document import Section, load, save

mcp = FastMCP("markdown")

_SECTION_FIELD = Field(
    description=(
        "Path to the target section as a list of heading names, e.g. "
        '["Introduction", "Background"]. Empty list or omitted means the '
        "document root."
    ),
)

_FILE_FIELD = Field(description="Absolute or relative path to the markdown file.")


@mcp.tool()
async def markdown_structure(
    file_path: Annotated[str, _FILE_FIELD],
) -> str:
    """
    Returns the heading hierarchy of a markdown document as an indented outline.

    Each entry shows the section's direct content size as ``(N lines, N words)``
    so you can quickly decide which sections to read in detail.  A ``(preamble)``
    line is shown when the document has content before the first heading.

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
) -> str:
    """
    Returns the content of a section in a markdown document.

    When no section path is provided, reads the entire document (equivalent to
    ``recursive=True`` on the root).
    """
    root = load(file_path)
    path = section or []
    target = root.get(path)
    if target is None:
        raise ValueError(f'Section not found: {path!r}')
    if recursive:
        # Use the stored heading level as the render depth so that skipped
        # levels and relative sub-heading gaps are preserved in the output.
        depth = target._level if target._level is not None else len(path)
        return target.render(depth=depth)
    return target.content


@mcp.tool()
async def markdown_update(
    file_path: Annotated[str, _FILE_FIELD],
    section: Annotated[list[str], _SECTION_FIELD],
    content: Annotated[
        Optional[str],
        Field(
            description=(
                "The body text to set for this section. Omit or pass null to delete "
                "the section and all its children. When provided, only the section's "
                "direct body is changed; existing nested subsections are preserved."
            )
        ),
    ] = None,
) -> None:
    """
    Creates, updates, or deletes a section in a markdown document.

    New sections are appended after any existing siblings. Use
    ``markdown_move`` afterwards to place the section in a specific position.
    """
    root = load(file_path)
    root.update(section, content)
    save(file_path, root)


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
