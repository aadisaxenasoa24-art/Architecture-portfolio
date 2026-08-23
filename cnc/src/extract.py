"""
Step 1 - pull every vector path out of the source PDF and assemble the
fragmented stroke segments back into continuous polylines.

The PDF was plotted from ZWCAD with its CAD layers preserved as optional-content
groups, so layer names survive.  Curves arrive as separate one-bezier paths, so
we re-join them end to end (they meet to well under 0.05 pt).
"""
import collections
import pickle

import numpy as np
import pymupdf

BEZ_STEPS = 12


def _bez(p0, p1, p2, p3, n=BEZ_STEPS):
    t = np.linspace(0.0, 1.0, n + 1)[1:]
    mt = 1.0 - t
    x = mt**3 * p0.x + 3 * mt * mt * t * p1.x + 3 * mt * t * t * p2.x + t**3 * p3.x
    y = mt**3 * p0.y + 3 * mt * mt * t * p1.y + 3 * mt * t * t * p2.y + t**3 * p3.y
    return list(zip(x, y))


def read_paths(pdf_path):
    """Every drawing path in the page, flattened to polylines in PDF points."""
    doc = pymupdf.open(pdf_path)
    page = doc[0]
    paths = []
    for it in page.get_drawings():
        subs, cur = [], []
        for seg in it["items"]:
            op = seg[0]
            if op in ("l", "c"):
                a = seg[1]
                if not cur:
                    cur = [(a.x, a.y)]
                elif abs(cur[-1][0] - a.x) > 1e-6 or abs(cur[-1][1] - a.y) > 1e-6:
                    if len(cur) > 1:
                        subs.append(cur)
                    cur = [(a.x, a.y)]
                if op == "l":
                    cur.append((seg[2].x, seg[2].y))
                else:
                    cur.extend(_bez(a, seg[2], seg[3], seg[4]))
            elif op == "re":
                if len(cur) > 1:
                    subs.append(cur)
                cur = []
                r = seg[1]
                subs.append([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1), (r.x0, r.y0)])
            elif op == "qu":
                if len(cur) > 1:
                    subs.append(cur)
                cur = []
                q = seg[1]
                subs.append([(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y),
                             (q.ll.x, q.ll.y), (q.ul.x, q.ul.y)])
        if len(cur) > 1:
            subs.append(cur)
        if not subs:
            continue
        col = it.get("color") or it.get("fill")
        paths.append({
            "layer": it.get("layer"),
            "type": it.get("type"),
            "stroke": it.get("color"),
            "fill": it.get("fill"),
            "width": round(it.get("width") or 0.0, 3),
            "rgb": tuple(round(c * 255) for c in col) if col else None,
            "subs": [np.asarray(s, dtype=float) for s in subs],
        })
    return paths


def join_chains(pieces, tol=0.05):
    """Greedy end-to-end merge of polyline fragments."""
    segs = [list(map(tuple, a)) for a in pieces]
    used = [False] * len(segs)
    index = collections.defaultdict(list)

    def key(p):
        return (round(p[0] / tol), round(p[1] / tol))

    for i, s in enumerate(segs):
        index[key(s[0])].append((i, 0))
        index[key(s[-1])].append((i, 1))

    chains = []
    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        chain = list(segs[i])
        for forward in (True, False):
            while True:
                end = chain[-1] if forward else chain[0]
                kx, ky = key(end)
                hit = None
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for j, which in index.get((kx + dx, ky + dy), ()):
                            if used[j]:
                                continue
                            pt = segs[j][0] if which == 0 else segs[j][-1]
                            if abs(pt[0] - end[0]) <= tol and abs(pt[1] - end[1]) <= tol:
                                hit = (j, which)
                                break
                        if hit:
                            break
                    if hit:
                        break
                if not hit:
                    break
                j, which = hit
                used[j] = True
                piece = segs[j] if which == 0 else segs[j][::-1]
                if forward:
                    chain.extend(piece[1:])
                else:
                    chain[:0] = piece[::-1][:-1]
        chains.append(np.asarray(chain, dtype=float))
    return chains


def contour_chains(paths):
    """{rgb: [polyline, ...]} for the contour layer, fragments re-joined."""
    groups = collections.defaultdict(list)
    for p in paths:
        if p["layer"] == "contours" and p["type"] == "s" and p["width"] > 0.5:
            groups[p["rgb"]].extend(s for s in p["subs"] if len(s) >= 2)
    return {rgb: join_chains(v) for rgb, v in groups.items()}


def main(pdf_path, out_path):
    paths = read_paths(pdf_path)
    chains = contour_chains(paths)
    pickle.dump({"paths": paths, "chains": chains}, open(out_path, "wb"))
    print(f"paths: {len(paths)}  contour colour groups: {len(chains)}")
    return paths, chains


if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2])
