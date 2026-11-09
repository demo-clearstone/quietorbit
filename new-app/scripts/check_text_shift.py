"""Show lines whose left edge moved between the uploaded source PDFs and the app output.

Usage:
    python scripts/check_text_shift.py OUTPUT.pdf SOURCE1.pdf [SOURCE2.pdf ...] > shift.txt

A line is listed when its text exists in a source PDF but only at a different x
(within 12 pt). Nothing listed means the app did not move the text sideways.
"""
from __future__ import annotations

import collections
import sys

import fitz


def _lines(page: fitz.Page):
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"]).strip()
            if text:
                yield text, round(line["bbox"][0])


def main(output: str, sources: list[str]) -> None:
    known: dict[str, set[int]] = collections.defaultdict(set)
    for path in sources:
        for page in fitz.open(path):
            for text, x in _lines(page):
                known[text].add(x)
    moved = 0
    for page in fitz.open(output):
        for text, x in _lines(page):
            xs = known.get(text)
            if xs and x not in xs and min(abs(x - y) for y in xs) <= 12:
                moved += 1
                print(f"page {page.number + 1}: {text[:60]!r} output x={x} source x={sorted(xs)}")
    print(f"lines moved sideways: {moved}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
