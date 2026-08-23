"""
Step 8 - independent check of the emitted DXF sheets.

Everything here is read back OUT of the written files, not from the in-memory
model, so it catches emitter bugs as well as geometry bugs.
"""
import glob
import os

import ezdxf
import numpy as np
from shapely.geometry import Polygon, LinearRing
from shapely.strtree import STRtree

import config


def read_sheet(path):
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    out = {}
    for e in msp:
        if e.dxftype() != "LWPOLYLINE":
            continue
        pts = np.array([(p[0], p[1]) for p in e.get_points("xy")])
        out.setdefault(e.dxf.layer, []).append((pts, bool(e.closed)))
    return out


def _polys(rings):
    ps = []
    for pts, closed in rings:
        if len(pts) < 3:
            continue
        p = Polygon(pts)
        if not p.is_valid:
            p = p.buffer(0)
        if not p.is_empty:
            ps.append(p)
    return ps


def check(paths, gap=5.0, margin=6.0, tools=(2.0, 3.0), verbose=True):
    report = {"sheets": [], "errors": [], "warnings": []}
    S = config.SHEET_MM
    for path in sorted(paths):
        name = os.path.basename(path)
        lay = read_sheet(path)
        outer = lay.get("CUT_OUTER", [])
        inner = lay.get("CUT_INNER", [])
        row = {"sheet": name, "outer": len(outer), "inner": len(inner)}

        for pts, closed in outer + inner:
            if not closed:
                report["errors"].append(f"{name}: open cut polyline ({len(pts)} pts)")
            if len(pts) < 3:
                report["errors"].append(f"{name}: degenerate cut polyline")
            else:
                r = LinearRing(np.vstack([pts, pts[:1]]))
                if not r.is_simple:
                    report["errors"].append(f"{name}: self-intersecting cut polyline")

        allpts = np.vstack([p for p, _ in outer + inner]) if outer or inner else None
        if allpts is not None:
            if allpts.min() < margin - 1e-6 or allpts.max() > S - margin + 1e-6:
                report["errors"].append(
                    f"{name}: geometry outside the {margin} mm sheet margin "
                    f"(min {allpts.min():.2f}, max {allpts.max():.2f})")

        polys = _polys(outer)
        tree = STRtree(polys)
        worst_gap = np.inf
        for i, a in enumerate(polys):
            for j in tree.query(a.buffer(gap)):
                if int(j) <= i:
                    continue
                b = polys[int(j)]
                if a.intersects(b):
                    report["errors"].append(f"{name}: parts overlap")
                else:
                    worst_gap = min(worst_gap, a.distance(b))
        if worst_gap < np.inf:
            row["min_part_gap_mm"] = round(float(worst_gap), 2)
            if worst_gap < gap - 0.51:
                report["warnings"].append(
                    f"{name}: parts only {worst_gap:.2f} mm apart (target {gap})")

        # holes must sit inside exactly one outer profile
        for pts, _ in inner:
            h = Polygon(pts)
            if not h.is_valid:
                h = h.buffer(0)
            owners = [k for k, p in enumerate(polys) if p.contains(h.representative_point())]
            if len(owners) != 1:
                report["errors"].append(f"{name}: hole with {len(owners)} owning profiles")

        # narrowest cuttable feature
        for tool in tools:
            bad = 0
            for p in polys:
                if p.buffer(-tool / 2.0).is_empty:
                    bad += 1
            row[f"parts_below_{tool}mm_tool"] = bad
        report["sheets"].append(row)

    if verbose:
        print(f"{'sheet':38s}{'outer':>7}{'inner':>7}{'min gap':>9}"
              f"{'<2mm':>7}{'<3mm':>7}")
        for r in report["sheets"]:
            print(f"{r['sheet']:38s}{r['outer']:7d}{r['inner']:7d}"
                  f"{r.get('min_part_gap_mm', float('nan')):9.2f}"
                  f"{r.get('parts_below_2.0mm_tool', 0):7d}{r.get('parts_below_3.0mm_tool', 0):7d}")
        print(f"\nERRORS  : {len(report['errors'])}")
        for e in report["errors"][:25]:
            print("   ", e)
        print(f"WARNINGS: {len(report['warnings'])}")
        for w in report["warnings"][:25]:
            print("   ", w)
    return report


if __name__ == "__main__":
    import sys
    check(glob.glob(sys.argv[1]))
