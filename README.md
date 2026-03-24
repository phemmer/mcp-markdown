# mcp-markdown

An MCP server that gives LLM agents structured read and write access to markdown documents.

Rather than treating a markdown file as a flat blob of text, the server understands the heading hierarchy and exposes tools that let an agent navigate to specific sections, read only what it needs, and make targeted edits without touching the rest of the document.

## Tools

### `markdown_structure`

Returns the heading outline of a document with direct content size (lines and words) for each section. Use this first to map a document before deciding what to read or edit.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | yes | Path to the markdown file |

**Example output:**
```
(preamble: 2 lines, 8 words)
- Introduction (3 lines, 45 words)
  - Background (5 lines, 82 words)
  - Motivation (2 lines, 30 words)
- Design (0 lines, 0 words)
  - Architecture (8 lines, 120 words)
- Implementation (10 lines, 150 words)
```

### `markdown_read`

Reads a section by path. With `recursive=true` (default) returns the section and all nested subsections as rendered markdown. With `recursive=false` returns only the section's immediate body text.

Omitting the section path reads the entire document.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | yes | Path to the markdown file |
| `section` | list of strings | no | Path to the section. Omit to read the entire document. |
| `recursive` | boolean | no | Include nested subsections (default: `true`) |

### `markdown_update`

Creates, updates, or deletes a section by path. Only the section's direct body text is affected — nested subsections are preserved. Omitting `content` deletes the section and all its children. New sections are appended after existing siblings.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | yes | Path to the markdown file |
| `section` | list of strings | yes | Path to the section to create, update, or delete |
| `content` | string | no | Body text to set. Omit to delete the section and all its children. |

### `markdown_move`

Moves a section to a different position within its parent. Pass a sibling name in `after` to place the section after it, or `null` to move it to the first position. This is a separate tool from `markdown_update` so each tool has single-purpose semantics.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | yes | Path to the markdown file |
| `section` | list of strings | yes | Path to the section to move |
| `after` | string | no | Title of the sibling to place this section after. Omit or pass `null` to move to the first position. |

## Section paths

All tools that target a section accept a `section` parameter that is a list of heading names forming the path through the document hierarchy:

```json
["Introduction", "Background"]
```

An empty list (or omitting the parameter) refers to the document root.

## Usage

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "markdown": {
      "command": "uvx --from git+https://github.com/phemmer/mcp-markdown mcp-markdown"
    }
  }
}
```

## Notes

- Parsing is done with [mistune](https://github.com/lepture/mistune), so fenced code blocks, HTML blocks, and other constructs are handled correctly — headings inside code blocks are not mistaken for document structure.
- Setext-style headings (`Title\n=====`) are supported for reading but all output uses ATX style (`# Title`).
- Section children maintain document order. New sections created with `markdown_update` are appended last; use `markdown_move` to reorder.
