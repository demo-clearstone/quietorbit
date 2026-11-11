"""Compare an app output PDF against an expected PDF and print a pasteable
report.

Usage:
    python scripts/compare_pdfs.py EXPECTED.pdf ACTUAL.pdf > compare.txt

Reports, per page: missing/extra lines, bold/italic span differences, and
header/column x-positions for lines that differ. Cover-letter dates are ignored.
"""
from __future__ import annotations

import difflib
import re
import sys

import fitz

DATE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
)


def _lines(page: fitz.Page) -> list[dict]:
    """Return text lines with x/y, size and bold/italic flags for each line."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in line["spans"]).rstrip()
            style = "".join(
                ("B" if (s["flags"] & 16 or "bold" in s["font"].lower()) else "-")
                + ("I" if (s["flags"] & 2 or "italic" in s["font"].lower() or "oblique" in s["font"].lower()) else "-")
                for s in spans
            )
            out.append(
                {
                    "text": text,
                    "x": round(line["bbox"][0]),
                    "y": round(line["bbox"][1]),
                    "size": round(spans[0]["size"], 1),
                    "style": style,
                    "cols": [(round(s["bbox"][0]), s["text"].strip()) for s in spans],
                }
            )
    out.sort(key=lambda l: (l["y"], l["x"]))
    return out


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", DATE.sub("<DATE>", text)).strip()


def _borders(page: fitz.Page) -> list[tuple[int, int, int]]:
    """Horizontal rules as (y, x0, x1), sorted for stable compare.

    Includes both stroked lines and thin filled/stroked rectangles (client
    packages often draw dividers as ``re`` rects rather than ``l`` lines).
    """
    out: list[tuple[int, int, int]] = []
    for drawing in page.get_drawings():
        for item in drawing.get("items") or []:
            if not item:
                continue
            if item[0] == "l" and len(item) >= 3:
                start, end = fitz.Point(item[1]), fitz.Point(item[2])
                if abs(start.y - end.y) > 1.5 or abs(start.x - end.x) < 30:
                    continue
                left, right = sorted((start.x, end.x))
                out.append((round((start.y + end.y) / 2), round(left), round(right)))
            elif item[0] == "re" and len(item) >= 2:
                rect = fitz.Rect(item[1])
                if rect.width < 30 or rect.height > 2.5:
                    continue
                out.append((round((rect.y0 + rect.y1) / 2), round(rect.x0), round(rect.x1)))
    return sorted(set(out))


def main(expected_path: str, actual_path: str) -> None:
    exp, act = fitz.open(expected_path), fitz.open(actual_path)
    print(f"Pages: expected={exp.page_count} actual={act.page_count}")
    for i in range(max(exp.page_count, act.page_count)):
        if i >= exp.page_count or i >= act.page_count:
            print(f"\n=== PAGE {i + 1}: only in {'actual' if i >= exp.page_count else 'expected'} ===")
            continue
        e, a = _lines(exp[i]), _lines(act[i])
        et, at = [_norm(l["text"]) for l in e], [_norm(l["text"]) for l in a]
        eb, ab = _borders(exp[i]), _borders(act[i])
        text_same = et == at and all(x["style"] == y["style"] and abs(x["x"] - y["x"]) <= 1 for x, y in zip(e, a))
        borders_same = eb == ab
        if text_same and borders_same:
            continue
        print(f"\n=== PAGE {i + 1}: {(e[0]['text'] if e else '')[:60]!r} ===")
        for pair in difflib.SequenceMatcher(None, eb, ab, autojunk=False).get_opcodes():
            tag, i1, i2, j1, j2 = pair
            if tag == "equal":
                continue
            for y, x0, x1 in eb[i1:i2]:
                print(f"  BORDER EXP y={y} x=({x0},{x1})")
            for y, x0, x1 in ab[j1:j2]:
                print(f"  BORDER ACT y={y} x=({x0},{x1})")
        if text_same:
            continue
        sm = difflib.SequenceMatcher(None, et, at, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for x, y in zip(e[i1:i2], a[j1:j2]):
                    notes = []
                    if x["style"] != y["style"]:
                        notes.append(f"style exp={x['style']} act={y['style']}")
                    if abs(x["x"] - y["x"]) > 1:
                        notes.append(f"x exp={x['x']} act={y['x']}")
                    if x["size"] != y["size"]:
                        notes.append(f"size exp={x['size']} act={y['size']}")
                    if len(x["cols"]) != len(y["cols"]) or any(abs(p[0] - q[0]) > 2 for p, q in zip(x["cols"], y["cols"])):
                        notes.append(f"cols exp={x['cols']} act={y['cols']}")
                    if notes:
                        print(f"  FMT  {x['text'][:80]!r}: " + "; ".join(notes))
                continue
            for l in e[i1:i2]:
                print(f"  EXP  x={l['x']:<4} {l['style'][:2]} {l['text']}")
            for l in a[j1:j2]:
                print(f"  ACT  x={l['x']:<4} {l['style'][:2]} {l['text']}")
            print("  ---")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
