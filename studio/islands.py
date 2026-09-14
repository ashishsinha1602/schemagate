"""Read and write the page's JSON islands with an HTML parser.

The page carries its data in `<script type="application/json">` blocks. Those
were being found with a regular expression, which is the wrong tool: the
pattern has to guess at attribute order, whitespace and what may appear inside
the block, and it fails silently by matching the wrong thing rather than
loudly by not matching. HTMLParser knows where a tag starts and ends because
it parses the document, so this asks the parser instead of guessing.

One source of truth underneath it all:

    demo_schema.py  ->  studio/schemas.json  ->  the island in studio.html

so a question, a column or a restriction is written down once and everything
downstream is generated from it.
"""
from __future__ import annotations

import json
import pathlib
from html.parser import HTMLParser


class _Islands(HTMLParser):
    """Record the byte span of every application/json script's contents."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._id: str | None = None
        self._start: int | None = None
        self.spans: dict[str, tuple[int, int]] = {}
        self._lines: list[int] = []

    def feed_text(self, text: str) -> "_Islands":
        # offset of the start of each line, so getpos() converts to an index
        off = 0
        for line in text.splitlines(keepends=True):
            self._lines.append(off)
            off += len(line)
        self._text = text
        self.feed(text)
        return self

    def _index(self) -> int:
        line, col = self.getpos()
        return self._lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and a.get("type") == "application/json" and a.get("id"):
            self._id = a["id"]
            # contents begin after this start tag
            self._start = self._text.index(">", self._index()) + 1

    def handle_endtag(self, tag):
        if tag == "script" and self._id is not None and self._start is not None:
            self.spans[self._id] = (self._start, self._index())
            self._id, self._start = None, None


def read(page: str, island_id: str):
    """The parsed JSON held in one island."""
    spans = _Islands().feed_text(page).spans
    if island_id not in spans:
        raise KeyError("no island %r in this page" % island_id)
    a, b = spans[island_id]
    return json.loads(_unescape(page[a:b]))


def write(page: str, island_id: str, value) -> str:
    """The page with one island's contents replaced by `value` as JSON."""
    spans = _Islands().feed_text(page).spans
    if island_id not in spans:
        raise KeyError("no island %r in this page" % island_id)
    a, b = spans[island_id]
    return page[:a] + _escape(json.dumps(value, ensure_ascii=False)) + page[b:]


def ids(page: str) -> list[str]:
    return sorted(_Islands().feed_text(page).spans)


#: `</` inside a script block would end it early, so it is written `<\/`
#: -- valid JSON string content, and inert to the HTML parser.
def _escape(s: str) -> str:
    return s.replace("</", "<\\/")


def _unescape(s: str) -> str:
    return s.replace("<\\/", "</")


if __name__ == "__main__":
    P = (pathlib.Path(__file__).resolve().parent
         / "sg033" / "src" / "schemagate" / "studio.html")
    page = P.read_text("utf-8")
    for i in ids(page):
        v = read(page, i)
        print("  %-14s %s" % (i, ("%d keys: %s" % (len(v), ", ".join(list(v)[:5])))
                              if isinstance(v, dict) else type(v).__name__))
