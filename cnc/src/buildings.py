"""
Step 3 - building footprints and their roof out-to-out boxes.

"Out to out" = the overall rectangle that encloses the roof in plan.  For a
building drawn as a rotated rectangle that is the rectangle itself; for the
L- and T-shaped campus blocks it is the minimum-area oriented bounding
rectangle, which is what a model maker cuts.
"""
import numpy as np
from scipy.spatial import ConvexHull

import config

GREY = 0.5961           # campus building mass fill
GREY2 = 0.7294          # paved platform fill
CYAN = (0.0, 0.8667, 0.8667)
RED = (255, 0, 0)


def _area(a):
    x, y = a[:, 0], a[:, 1]
    return 0.5 * abs(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]))


def _closed(a):
    if np.hypot(*(a[-1] - a[0])) > 1e-9:
        a = np.vstack([a, a[:1]])
    return a


def min_area_rect(pts):
    """Minimum-area oriented bounding rectangle (rotating calipers)."""
    pts = np.asarray(pts, dtype=float)
    if len(pts) < 3:
        return None
    try:
        hull = pts[ConvexHull(pts).vertices]
    except Exception:
        return None
    best = None
    n = len(hull)
    for i in range(n):
        e = hull[(i + 1) % n] - hull[i]
        L = np.hypot(*e)
        if L < 1e-9:
            continue
        u = e / L
        v = np.array([-u[1], u[0]])
        pu = hull @ u
        pv = hull @ v
        w, h = float(np.ptp(pu)), float(np.ptp(pv))
        if best is None or w * h < best[0]:
            u0, u1 = pu.min(), pu.max()
            v0, v1 = pv.min(), pv.max()
            corners = np.array([u0 * u + v0 * v, u1 * u + v0 * v,
                                u1 * u + v1 * v, u0 * u + v1 * v])
            best = (w * h, corners, w, h, float(np.degrees(np.arctan2(u[1], u[0]))))
    if best is None:
        return None
    _a, corners, w, h, ang = best
    return {"corners": np.vstack([corners, corners[:1]]),
            "w": w, "h": h, "angle": ang}


def collect(paths):
    """Footprint polygons in ground millimetres, grouped by kind."""
    out = {"raster": [], "campus": [], "platform": [], "water": []}
    for p in paths:
        subs = [s for s in p["subs"] if len(s) >= 4]
        if not subs:
            continue
        if p["layer"] in ("ref", "building blocks") and p["rgb"] == RED:
            for s in subs:
                if len(s) == 5 and _area(s) > 1e-6:
                    out["raster"].append(config.pt_to_ground(_closed(s)))
        elif p["layer"] == "i_hatch space" and p["fill"]:
            f = p["fill"]
            if abs(f[0] - GREY) < 0.01 and abs(f[1] - GREY) < 0.01:
                for s in subs:
                    out["campus"].append(config.pt_to_ground(_closed(s)))
            elif abs(f[0] - GREY2) < 0.01:
                for s in subs:
                    out["platform"].append(config.pt_to_ground(_closed(s)))
            elif abs(f[0] - CYAN[0]) < 0.02 and abs(f[1] - CYAN[1]) < 0.02:
                for s in subs:
                    out["water"].append(config.pt_to_ground(_closed(s)))
    return out


def in_window(poly, pad=0.0):
    W, H = config.MODEL_W_M * 1000.0, config.MODEL_H_M * 1000.0
    return (poly[:, 0].max() >= -pad and poly[:, 0].min() <= W + pad
            and poly[:, 1].max() >= -pad and poly[:, 1].min() <= H + pad)


def clip_to_window(poly):
    """Sutherland-Hodgman clip of a closed polygon to the model rectangle."""
    W, H = config.MODEL_W_M * 1000.0, config.MODEL_H_M * 1000.0
    edges = [(0, 0.0), (1, W), (2, 0.0), (3, H)]     # xmin, xmax, ymin, ymax

    def inside(p, which, val):
        return (p[0] >= val if which == 0 else
                p[0] <= val if which == 1 else
                p[1] >= val if which == 2 else p[1] <= val)

    def cut(a, b, which, val):
        if which in (0, 1):
            t = (val - a[0]) / (b[0] - a[0])
            return np.array([val, a[1] + t * (b[1] - a[1])])
        t = (val - a[1]) / (b[1] - a[1])
        return np.array([a[0] + t * (b[0] - a[0]), val])

    poly = list(np.asarray(poly)[:-1])
    for which, val in edges:
        if not poly:
            return None
        res = []
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            ia, ib = inside(a, which, val), inside(b, which, val)
            if ia:
                res.append(a)
                if not ib:
                    res.append(cut(a, b, which, val))
            elif ib:
                res.append(cut(a, b, which, val))
        poly = res
    if len(poly) < 3:
        return None
    return np.vstack([np.array(poly), np.array(poly[:1])])


def build_boxes(paths):
    """Footprints + out-to-out boxes, clipped to the model window."""
    groups = collect(paths)
    result = {}
    for kind, polys in groups.items():
        keep = []
        for poly in polys:
            if not in_window(poly):
                continue
            box = min_area_rect(poly[:-1])
            entry = {"footprint": poly, "box": box}
            entry["footprint_clip"] = clip_to_window(poly)
            entry["box_clip"] = clip_to_window(box["corners"]) if box else None
            keep.append(entry)
        result[kind] = keep
    return result
