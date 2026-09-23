"""Coordinate-based line reader for primary financial statement pages.

Groups PyMuPDF words into visual lines by vertical position; money-formatted tokens in the
right part of the page are values, recorded with their right edge (numbers are right-aligned).
"""
import re, sys
import pymupdf

NUM = re.compile(r"^\(?-?[\d,]+\.\d{2}\)?$|^[-–—]$")

def page_lines(doc, page_no):
    """Return [(label_text, [(right_edge_x, value_text), ...]), ...] in top-to-bottom order."""
    page = doc[page_no - 1]
    W = page.rect.width
    words = sorted(page.get_text("words"), key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines, cur, cy = [], [], None
    for w in words:
        yc = (w[1] + w[3]) / 2
        if cy is not None and abs(yc - cy) > 3:
            lines.append(cur); cur, cy = [], None
        cur.append(w)
        if cy is None: cy = yc
    if cur: lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda w: w[0])
        vals = [w for w in ln if w[0] > W * 0.55 and NUM.match(w[4])]
        out.append((" ".join(w[4] for w in ln if w not in vals), [(w[2], w[4]) for w in vals]))
    return out

if __name__ == "__main__":
    doc = pymupdf.open(sys.argv[1])
    for text, vals in page_lines(doc, int(sys.argv[2])):
        print(f"{text[:70]:70} | {[(round(x), v) for x, v in vals]}")
