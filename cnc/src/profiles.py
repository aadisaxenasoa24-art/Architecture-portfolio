"""
Step 4 - turn the DEM into one closed cut profile per 1 m layer.

Layer L is the plan of everything at or above L metres, clipped to the model
window.  Stacked on 2 mm board (1 m / 500) the pile reproduces the terrain.
Profiles come out of a marching-squares pass over the DEM, so every ring is
closed, correctly nested and free of self-intersections by construction.
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path

import config


def _rdp(pts, eps):
    """Douglas-Peucker, iterative."""
    n = len(pts)
    if n < 3:
        return pts
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        ab = b - a
        L = np.hypot(*ab)
        seg = pts[i + 1:j]
        if L < 1e-12:
            d = np.hypot(seg[:, 0] - a[0], seg[:, 1] - a[1])
        else:
            d = np.abs((seg[:, 0] - a[0]) * ab[1] - (seg[:, 1] - a[1]) * ab[0]) / L
        k = int(np.argmax(d))
        if d[k] > eps:
            k += i + 1
            keep[k] = True
            stack.append((i, k))
            stack.append((k, j))
    return pts[keep]


def _signed_area(a):
    x, y = a[:, 0], a[:, 1]
    return 0.5 * (np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]))


def rings_at(Z, level, simplify_mm=25.0, min_area_mm2=0.0, eps=1e-3):
    """
    All closed rings bounding {Z >= level}, in ground millimetres.

    The DEM is pinned to exactly `level` along the traced contour, and marching
    squares is degenerate on cells that sit exactly on the threshold - it emits
    a speck of a loop around each one.  Slicing a hair below the level puts the
    whole pinned band strictly inside the region and removes the degeneracy;
    at a typical 1:20 slope the 1 mm offset moves the line 20 mm on the ground,
    i.e. 0.04 mm at 1:500.

    Returns [{'outer': ring, 'holes': [ring, ...]}, ...] - one entry per island.
    """
    level = level - eps
    cell = config.DEM_CELL_M * 1000.0
    ny, nx = Z.shape
    x = np.arange(nx) * cell + cell / 2.0
    y = np.arange(ny) * cell + cell / 2.0

    # Pad with a ring of very low ground so islands touching the window edge
    # close along the edge instead of being left open.
    Zp = np.full((ny + 2, nx + 2), level - 1000.0, dtype=np.float64)
    Zp[1:-1, 1:-1] = Z
    xp = np.concatenate([[0.0], x, [config.MODEL_W_M * 1000.0]])
    yp = np.concatenate([[0.0], y, [config.MODEL_H_M * 1000.0]])
    X, Y = np.meshgrid(xp, yp)

    fig = plt.figure()
    ax = fig.add_subplot(111)
    cs = ax.contour(X, Y, Zp, levels=[level])
    loops = []
    for p in cs.get_paths():
        v = p.vertices
        codes = p.codes
        if codes is None:
            parts = [v]
        else:
            starts = np.flatnonzero(codes == Path.MOVETO).tolist() + [len(v)]
            parts = [v[starts[i]:starts[i + 1]] for i in range(len(starts) - 1)]
        for a in parts:
            if len(a) < 4:
                continue
            if np.hypot(*(a[-1] - a[0])) > 1e-6:
                a = np.vstack([a, a[:1]])
            if simplify_mm > 0:
                a = _rdp(a, simplify_mm)
                if np.hypot(*(a[-1] - a[0])) > 1e-6:
                    a = np.vstack([a, a[:1]])
            if len(a) >= 4 and abs(_signed_area(a)) >= min_area_mm2:
                loops.append(a)
    plt.close(fig)

    # classify: a loop nested inside an odd number of others is a hole
    depth = []
    paths = [Path(a) for a in loops]
    for i, a in enumerate(loops):
        d = sum(1 for j, pj in enumerate(paths)
                if j != i and pj.contains_point(a[0]))
        depth.append(d)

    islands = []
    for i, a in enumerate(loops):
        if depth[i] % 2 != 0:
            continue
        outer = a if _signed_area(a) > 0 else a[::-1]
        holes = []
        pi = Path(a)
        for j, b in enumerate(loops):
            if j == i or depth[j] != depth[i] + 1:
                continue
            if pi.contains_point(b[0]):
                holes.append(b if _signed_area(b) < 0 else b[::-1])
        islands.append({"outer": outer, "holes": holes})
    return islands


def polygon_area_mm2(island):
    a = abs(_signed_area(island["outer"]))
    for h in island["holes"]:
        a -= abs(_signed_area(h))
    return a


def min_width_mm(ring, samples=None):
    """
    Crude narrowness probe: smallest distance from a vertex to a
    non-adjacent part of the same ring.  Flags slivers a router bit cannot cut.
    """
    a = ring[:-1]
    n = len(a)
    if n < 8:
        return None
    step = max(1, n // (samples or 400))
    best = np.inf
    for i in range(0, n, step):
        d = np.hypot(a[:, 0] - a[i, 0], a[:, 1] - a[i, 1])
        skip = max(3, n // 40)
        idx = np.arange(n)
        mask = (np.abs(idx - i) > skip) & (np.abs(idx - i) < n - skip)
        if mask.any():
            best = min(best, float(d[mask].min()))
    return best


def build_all(Z, simplify_mm=25.0, min_area_mm2=1.0e6, verbose=True):
    out = {}
    for L in range(config.LEVEL_MIN, config.LEVEL_MAX + 1):
        isl = rings_at(Z, float(L), simplify_mm, min_area_mm2)
        out[L] = isl
        if verbose:
            nv = sum(len(i["outer"]) + sum(len(h) for h in i["holes"]) for i in isl)
            area = sum(polygon_area_mm2(i) for i in isl) / 1e6
            print(f"  level {L}: {len(isl):3d} island(s), "
                  f"{sum(len(i['holes']) for i in isl):2d} hole(s), "
                  f"{nv:6d} vertices, area {area:9.1f} m2")
    return out


def filter_manufacturable(profiles, tool_mm=2.0, scale=None, verbose=True):
    """
    Drop islands and holes that the cutter physically cannot make.

    A profile is cuttable if it survives an erosion by half the tool diameter
    at model scale.  Anything dropped is reported - nothing disappears quietly.
    """
    from shapely.geometry import Polygon
    scale = scale or config.SCALE
    r = tool_mm / 2.0 * scale          # erosion radius in ground millimetres
    dropped = []
    out = {}
    for L, isls in profiles.items():
        keep = []
        for isl in isls:
            poly = Polygon(isl["outer"][:, :2])
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty or poly.buffer(-r).is_empty:
                dropped.append(("island", L, poly.area))
                continue
            holes = []
            for h in isl["holes"]:
                hp = Polygon(h[:, :2])
                if not hp.is_valid:
                    hp = hp.buffer(0)
                if hp.is_empty or hp.buffer(-r).is_empty:
                    dropped.append(("hole", L, hp.area))
                    continue
                holes.append(h)
            keep.append({"outer": isl["outer"], "holes": holes})
        out[L] = keep
    if verbose:
        if dropped:
            print(f"  manufacturability filter ({tool_mm:.1f} mm tool at 1:{scale}):")
            for kind, L, area in dropped:
                print(f"    dropped {kind:7s} at {L} m - {area/1e6:8.2f} m2 ground "
                      f"= {area/scale**2:7.1f} mm2 on the model")
        else:
            print(f"  manufacturability filter ({tool_mm:.1f} mm tool): nothing dropped")
    return out, dropped
