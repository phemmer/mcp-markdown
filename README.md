# mcp-markdown

An MCP server that gives LLM agents structured read and write access to markdown documents.

Rather than treating a markdown file as a flat blob of text, the server understands the heading hierarchy and exposes tools that let an agent navigate to specific sections, read only what it needs, and make targeted edits without touching the rest of the document.

## Tools

### `markdown_structure`

Returns the heading outline of a document. Each entry shows the section's checksum and direct content size so you can quickly decide which sections to read in detail. Use this first to map a document before reading or editing.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | yes | Path to the markdown file |

**Example output:**
```
(preamble: 2 lines, 8 words)
- Introduction [aBcDeFgH] (3 lines, 45 words)
  - Background [1234abcd] (5 lines, 82 words)
  - Motivation [XyZ98765] (2 lines, 30 words)
- Design [qRsT4321] (0 lines, 0 words)
  - Architecture [uVwX1234] (8 lines, 120 words)
- Implementation [yZaB5678] (10 lines, 150 words)
```

### `markdown_read`

Reads a section by path. Returns a structured response containing the content and a checksum. With `recursive=true` (default) the response also includes a `sections` map with checksums for all nested subsections, so you can obtain checksums for subsections without additional reads. With `recursive=false` returns only the section's immediate body text.

Omitting the section path reads the entire document.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | yes | Path to the markdown file |
| `section` | list of strings | no | Path to the section. Omit to read the entire document. |
| `recursive` | boolean | no | Include nested subsections (default: `true`) |

**Example response (`recursive=true`):**
```json
{
  "content": "# Introduction\n\nBody text.\n\n## Background\n\nBackground text.",
  "checksum": "aBcDeFgH",
  "sections": {
    "Background": {
      "checksum": "1234abcd"
    }
  }
}
```

**Example response (`recursive=false`):**
```json
{
  "content": "Body text.",
  "checksum": "aBcDeFgH"
}
```

### `markdown_update`

Creates, updates, or deletes a section by path. Returns the new checksum when the section still exists after the operation, or `null` for recursive deletes.

When the section already exists, `checksum` is required to prevent unintentional overwrites. Pass the checksum obtained from a previous `markdown_read` or `markdown_structure` call.

The value of `content` determines the operation:

| `content` value | Operation | Checksum validated |
|-----------------|-----------|-------------------|
| `"some text"` | Set body text (create or update) | local |
| `""` (empty string) | Clear body text, keep child sections | local |
| `null` / omitted | Delete section and all children | recursive |

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | yes | Path to the markdown file |
| `section` | list of strings | yes | Path to the section to create, update, or delete |
| `content` | string | no | Body text to set. Empty string clears body while keeping children. Omit or pass `null` to delete the section and all its children. |
| `checksum` | string | when section exists | Checksum from a previous read. Required when modifying an existing section. |

### `markdown_move`

Moves a section to a different position within its parent. Pass a sibling name in `after` to place the section after it, or `null` to move it to the first position. This is a separate tool from `markdown_update` so each tool has single-purpose semantics. Does not require a checksum.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | yes | Path to the markdown file |
| `section` | list of strings | yes | Path to the section to move |
| `after` | string | no | Title of the sibling to place this section after. Omit or pass `null` to move to the first position. |

## Checksums

Every section has an opaque 8-character checksum. The checksum is returned by `markdown_structure` (inline in each entry) and `markdown_read` (in the response object).

When updating or deleting an existing section, pass the checksum back in the `checksum` parameter. This ensures you are editing the version of the section you read — if the document has changed in the meantime, the update is rejected with an error.

The checksum has two internal components (local and recursive) that are validated differently depending on the operation. This is an implementation detail; treat the checksum as a single opaque token.

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
- Skipped heading levels (e.g. `# H1` followed by `### H3`) are preserved on roundtrip. Inserting an intermediate level and re-reading will cause the deeper section to be re-parented under it.
- Section children maintain document order. New sections created with `markdown_update` are appended last; use `markdown_move` to reorder.
