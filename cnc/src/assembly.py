"""
Step 9 - resolve the model into real parts: registration dowels and building
locating sockets, cut into every board that needs them.

Dowels.  A contour stack is nested - the region at or above level L sits inside
the region at or above L-1 - so a point that is safely inside a board is safely
inside every board beneath it, with at least as much edge clearance.  That makes
the placement problem easy to solve exactly: work down from the summit, and a
dowel placed for a high board is reused free by everything below it.  Each dowel
therefore serves one contiguous run, base board up to the highest board that
still holds it with full clearance.

Sockets.  A building block that lands wholly inside one terrace gets its
out-to-out box cut through that board, so the block drops in on a 2 mm spigot
and cannot shift.  Blocks that straddle a terrace edge are left engraved only -
a socket there would be ambiguous.
"""
import numpy as np
from shapely.geometry import Polygon, Point, box as shp_box
from shapely.ops import unary_union

import config

# --- dowel spec, in model millimetres at 1:500 -----------------------------
ROD_DIA = 3.0             # brass or beech rod
HOLE_DIA = 3.2            # 0.1 mm clearance per side
EDGE_CLEAR = 4.0          # material left between hole edge and any cut edge
MIN_SPACING = 28.0        # between dowel centres
HOLE_SEGMENTS = 48

# how many dowels a piece wants, by its area in square millimetres
DOWEL_TARGET = ((10000.0, 3), (1000.0, 2), (150.0, 1), (0.0, 0))

# --- socket spec -----------------------------------------------------------
SOCKET_CLEAR = 3.0        # material left around a building socket
SOCKET_MIN_MM = 6.0       # a socket smaller than this is not worth cutting


def _target(area_mm2):
    for lim, n in DOWEL_TARGET:
        if area_mm2 >= lim:
            return n
    return 0


def part_polygons(profiles, scale=None):
    """{level: [shapely Polygon, ...]} in model millimetres."""
    scale = scale or config.SCALE
    out = {}
    for L, isls in profiles.items():
        polys = []
        for isl in isls:
            p = Polygon(isl["outer"][:, :2] / scale,
                        [h[:, :2] / scale for h in isl["holes"]])
            if not p.is_valid:
                p = p.buffer(0)
            if not p.is_empty:
                polys.append(p)
        out[L] = polys
    return out


def _candidates(safe, step=3.0):
    """Grid of points inside `safe`, with their distance to its boundary."""
    x0, y0, x1, y1 = safe.bounds
    xs = np.arange(x0 + step / 2, x1, step)
    ys = np.arange(y0 + step / 2, y1, step)
    pts = []
    for y in ys:
        for x in xs:
            p = Point(x, y)
            if safe.contains(p):
                pts.append((x, y, safe.exterior.distance(p) if safe.geom_type == "Polygon"
                            else safe.boundary.distance(p)))
    return pts


def plan_dowels(profiles, verbose=True):
    """
    Dowel positions and the run of boards each one passes through.

    Returns [{'x','y','top_level','levels':[...]}, ...] with levels running from
    the base board up to and including the highest board that holds the dowel.
    """
    parts = part_polygons(profiles)
    r = HOLE_DIA / 2.0 + EDGE_CLEAR
    dowels = []

    for L in sorted(parts, reverse=True):
        for poly in sorted(parts[L], key=lambda p: -p.area):
            safe = poly.buffer(-r)
            if safe.is_empty:
                continue
            want = _target(poly.area)
            have = [d for d in dowels if safe.contains(Point(d["x"], d["y"]))]
            need = want - len(have)
            if need <= 0:
                continue
            geoms = safe.geoms if hasattr(safe, "geoms") else [safe]
            cands = []
            for g in geoms:
                if isinstance(g, Polygon) and not g.is_empty:
                    cands += _candidates(g)
            if not cands:
                continue
            placed = [(d["x"], d["y"]) for d in dowels]
            best_clr = max(c[2] for c in cands)
            # keep dowels off the edge: only the deeper half of the piece is
            # eligible, so a pin never ends up in a 5 mm sliver of board
            floor_clr = max(2.0, min(0.45 * best_clr, 12.0))
            for k in range(need):
                pool = [c for c in cands if c[2] >= floor_clr] or cands
                # a piece with no pin at all must get one, spacing or not
                must = (k == 0 and not any(
                    np.hypot(x - px, y - py) < 1e-9 for (px, py) in placed
                    for x, y, _c in [] ) and len(
                        [1 for px, py in placed if safe.contains(Point(px, py))]) == 0)
                best, bs = None, -1e18
                for (x, y, clr) in pool:
                    if placed:
                        dmin = min(np.hypot(x - px, y - py) for px, py in placed)
                        if dmin < MIN_SPACING and not must:
                            continue
                    else:
                        dmin = 1e6
                    s = 0.5 * min(dmin, 140.0) + min(clr, 45.0)
                    if s > bs:
                        bs, best = s, (x, y)
                if best is None:
                    break
                placed.append(best)
                dowels.append({"x": best[0], "y": best[1]})

    # the run each dowel serves: base board up to the highest board holding it
    for d in dowels:
        p = Point(d["x"], d["y"])
        top = config.BASE_LEVEL
        for L in sorted(parts):
            if any(poly.buffer(-r).contains(p) for poly in parts[L]):
                top = L
        d["top_level"] = top
        d["levels"] = list(range(config.BASE_LEVEL, top + 1))

    dowels.sort(key=lambda d: (-d["top_level"], d["x"], d["y"]))
    for i, d in enumerate(dowels, 1):
        d["id"] = "D%02d" % i

    if verbose:
        print(f"  {len(dowels)} dowels, {ROD_DIA:.1f} mm rod in {HOLE_DIA:.1f} mm holes")
        per = {}
        for d in dowels:
            for L in d["levels"]:
                per[L] = per.get(L, 0) + 1
        thin = [L for L in sorted(parts) for _ in [0] if per.get(L, 0) < 2]
        print(f"  holes per board: {min(per.values())} to {max(per.values())}")
        if thin:
            print(f"  boards with fewer than 2 dowels: {thin}")
    return dowels


def check_dowels(dowels, profiles, verbose=True):
    """Every piece that can take a dowel must actually get one; report the rest."""
    parts = part_polygons(profiles)
    r = HOLE_DIA / 2.0 + EDGE_CLEAR
    rows, unpinned = [], []
    for L in sorted(parts):
        for i, poly in enumerate(sorted(parts[L], key=lambda p: -p.area)):
            safe = poly.buffer(-r)
            n = sum(1 for d in dowels
                    if not safe.is_empty and safe.contains(Point(d["x"], d["y"])))
            fits = not safe.is_empty
            rows.append({"level": L, "island": i, "area_mm2": poly.area,
                         "dowels": n, "can_take_dowel": fits})
            if n == 0 and fits and _target(poly.area) > 0:
                unpinned.append((L, i, poly.area))
    if verbose:
        no_room = [r_ for r_ in rows if not r_["can_take_dowel"]]
        print(f"  pieces: {len(rows)}   pinned: {sum(1 for r_ in rows if r_['dowels'] > 0)}"
              f"   too small for a dowel: {len(no_room)}")
        if unpinned:
            print(f"  WARNING unpinned pieces that could take one: {unpinned}")
    return rows, unpinned


def dowel_circle(x, y, dia=HOLE_DIA, n=HOLE_SEGMENTS):
    t = np.linspace(0, 2 * np.pi, n + 1)
    return np.column_stack([x + dia / 2 * np.cos(t), y + dia / 2 * np.sin(t)])


def plan_sockets(profiles, boxes, dowels, verbose=True):
    """
    Building locating sockets.

    A socket is cut only where the whole out-to-out box sits inside one board's
    visible terrace with clearance, clear of every dowel.  Everything else stays
    engrave-only.
    """
    parts = part_polygons(profiles)
    levels = sorted(parts)
    union = {L: unary_union(parts[L]) for L in levels}
    dowel_pts = [Point(d["x"], d["y"]) for d in dowels]

    sockets = {L: [] for L in levels}
    taken = 0
    all_boxes = []
    for kind in ("raster", "campus", "platform"):
        for e in boxes.get(kind, ()):
            if e.get("box_clip") is None:
                continue
            all_boxes.append((kind, Polygon(e["box_clip"][:, :2] / config.SCALE)))

    for kind, g in all_boxes:
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty:
            continue
        w = min(g.bounds[2] - g.bounds[0], g.bounds[3] - g.bounds[1])
        if w < SOCKET_MIN_MM:
            continue
        placed = False
        for L in reversed(levels):
            terr = union[L]
            above = union.get(L + 1)
            if above is not None and not above.is_empty:
                terr = terr.difference(above)
            if terr.is_empty or not terr.contains(g):
                continue
            if not terr.buffer(-SOCKET_CLEAR).contains(g):
                break
            if any(g.buffer(SOCKET_CLEAR).contains(p) for p in dowel_pts):
                break
            sockets[L].append({"kind": kind, "poly": g})
            taken += 1
            placed = True
            break
        if placed:
            continue

    if verbose:
        print(f"  building sockets cut: {taken} of {len(all_boxes)} boxes "
              f"({100*taken/max(1,len(all_boxes)):.0f} %); the rest stay engrave-only")
        by = {L: len(v) for L, v in sockets.items() if v}
        print(f"  sockets per board: {by}")
    return sockets
