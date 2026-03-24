"""
Markdown document model.

Parses a markdown document into a tree of Section nodes keyed by heading title.
The tree can be queried, mutated, and rendered back to markdown.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from mistune import BlockParser, Markdown

_ATX_CLOSER_RE = re.compile(r'\s+#+\s*$')


class _PositionBlockParser(BlockParser):
    """
    BlockParser subclass that annotates heading tokens with their byte-offset
    positions in the source string so content between headings can be sliced out.

    Added fields on heading tokens:
      pos_start: int  — offset of the first character of the heading line (the '#'
                        for ATX, or the first char of the title line for setext)
      pos_end:   int  — offset one past the last character of the heading construct
                        (not including the trailing newline)
    """

    def parse_atx_heading(self, m, state) -> int:
        result = super().parse_atx_heading(m, state)
        state.tokens[-1]['pos_start'] = m.start()
        state.tokens[-1]['pos_end'] = m.end()
        return result

    def parse_setex_heading(self, m, state) -> int | None:
        result = super().parse_setex_heading(m, state)
        if result is None:
            return None
        tok = state.tokens[-1]
        if tok.get('style') != 'setext':
            return result
        src = state.src
        # The underline line begins at m.start(). The title line is the line
        # immediately before it. Find the \n that ends the title line, then the
        # \n that starts it (or BOF).
        nl_before_underline = src.rfind('\n', 0, m.start())
        nl_before_title = src.rfind('\n', 0, nl_before_underline) if nl_before_underline > 0 else -1
        tok['pos_start'] = nl_before_title + 1
        tok['pos_end'] = m.end()
        return result


def _heading_title(src: str, token: dict) -> str:
    """
    Extracts the plain-text title from a heading token.

    For ATX headings the title is sliced from the source and trailing closer
    hashes are stripped.  For setext headings the title occupies the line
    immediately before the underline tracked in pos_start/pos_end.
    """
    level = token['attrs']['level']
    ps, pe = token['pos_start'], token['pos_end']
    if token.get('style') == 'setext':
        nl_before_underline = src.rfind('\n', 0, ps + (pe - ps))
        title_end = src.rfind('\n', ps, pe)
        return src[ps:title_end].strip()
    # ATX
    heading_line = src[ps:pe]
    title = heading_line[level:].strip()
    return _ATX_CLOSER_RE.sub('', title).strip()


@dataclass
class Section:
    """
    A node in the markdown document tree.

    Represents one section of a markdown document.  ``content`` is the raw
    markdown body text that appears directly under this section's heading
    (between this heading and the next heading at the same or higher level).
    ``children`` is an ordered mapping of heading title → child Section,
    preserving the order in which the sections appear in the document.

    The root Section returned by :func:`parse` has no heading of its own;
    its ``content`` is the document preamble (text before the first heading)
    and its ``children`` are the top-level sections.
    """

    content: str = ""
    children: dict[str, Section] = field(default_factory=dict)
    # Original heading level from the parsed source (1–6). None for sections
    # created programmatically. Used by render() to preserve the exact heading
    # depth rather than normalising skipped levels.
    _level: int | None = field(default=None, repr=False)

    def empty(self) -> bool:
        """Returns True if this section has no content and no children."""
        return not self.content and not self.children

    def structure(self, depth: int = 0) -> str:
        """
        Returns an indented outline of all headings in this subtree.

        Each entry is annotated with the section's direct content size:
        ``(N lines, N words)``.  Only direct content is counted; nested
        subsections are not included in the count but are listed recursively.

        The root section's own content (preamble) is not included; callers
        that want a preamble line should prepend it themselves.

        Example output (depth=0)::

            - Introduction (3 lines, 45 words)
              - Background (5 lines, 82 words)
              - Motivation (2 lines, 30 words)
            - Design (0 lines, 0 words)
        """
        indent = '  ' * depth
        lines = []
        for title, child in self.children.items():
            line_count = len(child.content.splitlines()) if child.content else 0
            word_count = len(child.content.split()) if child.content else 0
            lines.append(f'{indent}- {title} ({line_count} lines, {word_count} words)')
            if child.children:
                lines.append(child.structure(depth + 1))
        return '\n'.join(lines)

    def render(self, depth: int = 0) -> str:
        """
        Renders this section and all its descendants as markdown.

        ``depth`` is the heading level of *this* section (the caller has
        already emitted this section's heading at that level).  Children are
        rendered at ``depth + 1`` unless they carry a stored ``_level`` from
        parsing, in which case that level is used verbatim.  This preserves
        skipped heading levels on roundtrip and produces natural "takeover"
        behaviour: inserting an intermediate level before a deeper one causes
        the deeper section to appear nested under it in the output.

        All headings are rendered in ATX style regardless of the original style.
        """
        output = ''
        if self.content:
            output = self.content.strip() + '\n'
        for title, child in self.children.items():
            child_level = child._level if child._level is not None else depth + 1
            output += f'\n{"#" * child_level} {title}\n\n'
            child_rendered = child.render(child_level).strip()
            if child_rendered:
                output += child_rendered + '\n'
        return output

    def get(self, path: list[str]) -> Section | None:
        """
        Returns the section at the given path, or ``None`` if not found.

        An empty path returns ``self``.
        """
        if not path:
            return self
        if path[0] not in self.children:
            return None
        return self.children[path[0]].get(path[1:])

    def update(self, path: list[str], content: str | None) -> None:
        """
        Creates, updates, or deletes the section at ``path``.

        If ``content`` is not ``None``, creates the section (and any missing
        intermediate sections) or updates its direct body text.  Existing
        children of the target section are not affected.

        If ``content`` is ``None``, deletes the section and all its descendants.
        Raises ``KeyError`` if the path does not exist.

        An empty path updates the root's content or clears it (delete on root
        only clears ``content``; it does not remove children).
        """
        if not path:
            self.content = content if content is not None else ''
            return
        name = path[0]
        if content is None:
            if name not in self.children:
                raise KeyError(name)
            if len(path) == 1:
                del self.children[name]
            else:
                self.children[name].update(path[1:], None)
            return
        if name not in self.children:
            self.children[name] = Section()
        self.children[name].update(path[1:], content)

    def move(self, path: list[str], after: str | None) -> None:
        """
        Moves the section at ``path`` to a new position within its parent.

        ``after`` is the title of the sibling that the moved section should
        follow.  ``None`` moves the section to the first position.

        Raises ``KeyError`` if ``path`` or ``after`` does not exist.
        Raises ``ValueError`` if ``path`` is empty (cannot move root).
        """
        if not path:
            raise ValueError('cannot move root section')
        if len(path) > 1:
            parent = self.get(path[:-1])
            if parent is None:
                raise KeyError(path[:-1])
            parent.move([path[-1]], after)
            return
        name = path[0]
        if name not in self.children:
            raise KeyError(name)
        if after is not None and after not in self.children:
            raise KeyError(after)
        section = self.children.pop(name)
        new_children: dict[str, Section] = {}
        if after is None:
            new_children[name] = section
        for key, val in self.children.items():
            new_children[key] = val
            if key == after:
                new_children[name] = section
        self.children = new_children


def parse(text: str) -> Section:
    """
    Parses markdown text into a Section tree.

    Uses mistune for block-level parsing so that constructs such as fenced
    code blocks and HTML blocks are handled correctly — headings inside those
    constructs are not mistaken for document structure.

    Returns the root :class:`Section`.  The root's ``content`` is the
    preamble (text before the first heading); its ``children`` are the
    top-level sections in document order.
    """
    md = Markdown(renderer=None, block=_PositionBlockParser())
    tokens, state = md.parse(text)
    src = state.src

    headings = [t for t in tokens if t['type'] == 'heading']

    root = Section()
    # stack entries are (level, section); level 0 is the synthetic root level
    section_stack: list[tuple[int, Section]] = [(0, root)]
    prev_end = 0

    for token in headings:
        level = token['attrs']['level']
        title = _heading_title(src, token)

        section_stack[-1][1].content = src[prev_end:token['pos_start']].strip()

        while len(section_stack) > 1 and section_stack[-1][0] >= level:
            section_stack.pop()

        new_section = Section(_level=level)
        section_stack[-1][1].children[title] = new_section
        section_stack.append((level, new_section))

        prev_end = token['pos_end'] + 1

    section_stack[-1][1].content = src[prev_end:].strip()

    return root


def load(path: str) -> Section:
    """Reads ``path`` from disk and returns the parsed :class:`Section` tree."""
    with open(path, encoding='utf-8') as f:
        return parse(f.read())


def save(path: str, root: Section) -> None:
    """Renders ``root`` and writes it to ``path``."""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(root.render())
