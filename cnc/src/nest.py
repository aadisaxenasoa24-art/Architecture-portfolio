"""
Step 6 - lay every cut profile out on 4 ft x 4 ft sheets at 1:500.

One part = one island of one contour layer.  Parts keep their true orientation
(never rotated) so a piece can only go on the model one way, and each piece
carries an engraved copy of the outline of the layer that sits on top of it, so
the stack self-registers with no measuring.
"""
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely.ops import unary_union

import config
import stickfont

SCALE = config.SCALE
SHEET = config.SHEET_MM
MARGIN = 6.0            # clear of the sheet edge
GAP = 5.0               # between parts
LABEL_H = 5.0


def _poly(island):
    p = Polygon(island["outer"][:, :2], [h[:, :2] for h in island["holes"]])
    if not p.is_valid:
        p = p.buffer(0)
    return p


def to_model_mm(geom_ground):
    """Ground millimetres -> model millimetres at 1:500."""
    from shapely import affinity
    return affinity.scale(geom_ground, 1.0 / SCALE, 1.0 / SCALE, origin=(0, 0))


def make_parts(profiles, boxes, extra_lines=None):
    """One part per island, with everything that gets engraved on it."""
    level_union = {}
    for L, isls in profiles.items():
        polys = [_poly(i) for i in isls]
        level_union[L] = unary_union(polys) if polys else Polygon()

    parts = []
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for L in sorted(profiles):
        isls = sorted(profiles[L], key=lambda i: -Polygon(i["outer"][:, :2]).area)
        for n, isl in enumerate(isls):
            p = to_model_mm(_poly(isl))
            above = level_union.get(L + 1, Polygon())
            above_m = to_model_mm(above) if not above.is_empty else Polygon()
            terrace = p.difference(above_m) if not above_m.is_empty else p

            engrave_next = []
            if not above_m.is_empty:
                clipped = above_m.intersection(p)
                engrave_next = _rings(clipped)

            engrave_box, engrave_foot = [], []
            for kind in ("raster", "campus", "platform"):
                for e in boxes.get(kind, ()):
                    for src, sink in ((e.get("box_clip"), engrave_box),
                                      (e.get("footprint_clip"), engrave_foot)):
                        if src is None:
                            continue
                        g = to_model_mm(Polygon(src[:, :2]))
                        if not g.is_valid:
                            g = g.buffer(0)
                        if g.is_empty or not g.intersects(terrace):
                            continue
                        sink.extend(_rings(g.intersection(terrace)))

            engrave_extra = []
            for kind, lines in (extra_lines or {}).items():
                for ln in lines:
                    g = to_model_mm(LineString(ln[:, :2]))
                    cut = g.intersection(terrace)
                    engrave_extra.extend((kind, np.asarray(c.coords))
                                         for c in _lines(cut))

            parts.append({
                "id": f"L{L}-{letters[n] if n < 26 else str(n)}",
                "level": L,
                "poly": p,
                "engrave_next": engrave_next,
                "engrave_box": engrave_box,
                "engrave_foot": engrave_foot,
                "engrave_extra": engrave_extra,
            })
    return parts


def _rings(g):
    out = []
    if g.is_empty:
        return out
    geoms = g.geoms if hasattr(g, "geoms") else [g]
    for q in geoms:
        if not isinstance(q, Polygon) or q.is_empty:
            continue
        out.append(np.asarray(q.exterior.coords))
        out.extend(np.asarray(r.coords) for r in q.interiors)
    return out


def _lines(g):
    if g.is_empty:
        return []
    geoms = g.geoms if hasattr(g, "geoms") else [g]
    return [q for q in geoms if isinstance(q, LineString) and not q.is_empty]


def base_part(profiles, boxes, extra_lines=None):
    """The base board: the whole model rectangle at the base datum."""
    W = config.MODEL_W_M * 1000.0 / SCALE
    H = config.MODEL_H_M * 1000.0 / SCALE
    p = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
    above = unary_union([_poly(i) for i in profiles[config.LEVEL_MIN]])
    above_m = to_model_mm(above)
    terrace = p.difference(above_m)
    return {
        "id": f"L{config.BASE_LEVEL}-BASE",
        "level": config.BASE_LEVEL,
        "poly": p,
        "engrave_next": _rings(above_m),
        "engrave_box": [], "engrave_foot": [], "engrave_extra": [],
    }


# --------------------------------------------------------------------------
# nesting - shape aware, on a raster occupancy mask

RES = 1.5                      # mm per pixel for the nesting mask


def _rasterise(poly, res=RES):
    """Boolean mask of the material a part occupies (holes are not material)."""
    from PIL import Image, ImageDraw
    x0, y0, x1, y1 = poly.bounds
    w = int(np.ceil((x1 - x0) / res)) + 1
    h = int(np.ceil((y1 - y0) / res)) + 1
    img = Image.new("1", (w, h), 0)
    d = ImageDraw.Draw(img)

    def px(ring):
        return [((x - x0) / res, (y - y0) / res) for x, y in ring]

    geoms = poly.geoms if hasattr(poly, "geoms") else [poly]
    for g in geoms:
        d.polygon(px(g.exterior.coords), fill=1)
        for r in g.interiors:
            d.polygon(px(r.coords), fill=0)
    return np.array(img, dtype=bool), (x0, y0)


def nest(parts, sheet=SHEET, margin=MARGIN, gap=GAP, res=RES,
         rotations=(0, 90, 180, 270), verbose=True):
    """
    Shape-aware bottom-left nesting.

    Each part is rasterised and slid over the sheet with an FFT
    cross-correlation, which tests every candidate position at once.  The
    occupancy grid holds the material already placed, dilated by the clearance,
    so a new part only has to keep its own footprint out of it - that way a
    part that spans almost the whole sheet still places, and small parts can
    drop into the holes of larger ones (that material is scrap anyway).

    Parts may be rotated in 90 degree steps; every piece carries an engraved
    north arrow and part id, and the outline of the layer above, so a piece can
    only go on the model one way.
    """
    from scipy.signal import fftconvolve
    from shapely import affinity

    usable = sheet - 2 * margin
    npx = int(np.floor(usable / res))
    # dilate by the gap plus two pixels, to absorb rasterisation rounding
    grow = int(np.ceil((gap + 2 * res) / res))

    variants = []
    for p in parts:
        vs = []
        for rot in rotations:
            g = affinity.rotate(p["poly"], rot, origin="centroid") if rot else p["poly"]
            m, org = _rasterise(g, res)
            if m.shape[0] > npx or m.shape[1] > npx:
                continue
            vs.append({"rot": rot, "poly": g, "mask": m, "org": org})
        if not vs:
            raise ValueError(f"{p['id']} does not fit a {usable:.1f} mm usable sheet")
        variants.append({"part": p, "variants": vs, "area": p["poly"].area,
                         "span": max(max(v["mask"].shape) for v in vs)})
    variants.sort(key=lambda d: (-d["span"], -d["area"]))

    sheets = []
    for item in variants:
        placed = False
        for sh in sheets:
            if _place(sh, item, npx, res, margin, grow, fftconvolve):
                placed = True
                break
        if not placed:
            sh = {"raw": np.zeros((npx, npx), dtype=bool),
                  "occ": np.zeros((npx, npx), dtype=bool), "items": []}
            sheets.append(sh)
            if not _place(sh, item, npx, res, margin, grow, fftconvolve):
                raise ValueError(f"could not place {item['part']['id']} on an empty sheet")
        if verbose:
            print(f"   {item['part']['id']:10s} -> sheet {len(sheets)}")
    for sh in sheets:
        sh.pop("raw", None)
        sh.pop("occ", None)
    return sheets


def _place(sh, item, npx, res, margin, grow, fftconvolve):
    from scipy import ndimage
    occ = sh["occ"]
    best = None
    for v in item["variants"]:
        m = v["mask"]
        if m.shape[0] > npx or m.shape[1] > npx:
            continue
        corr = fftconvolve(occ.astype(np.float32), m[::-1, ::-1].astype(np.float32),
                           mode="valid")
        free = corr < 0.5
        if not free.any():
            continue
        rows, cols = np.nonzero(free)
        j = int(np.lexsort((cols, rows))[0])
        r, c = int(rows[j]), int(cols[j])
        if best is None or (r, c) < (best[0], best[1]):
            best = (r, c, v)
    if best is None:
        return False
    r, c, v = best
    mh, mw = v["mask"].shape
    sh["raw"][r:r + mh, c:c + mw] |= v["mask"]
    sh["occ"] = ndimage.binary_dilation(
        sh["raw"], np.ones((2 * grow + 1, 2 * grow + 1), bool))
    sh["items"].append({
        "part": item["part"], "rot": v["rot"], "poly": v["poly"],
        "x": c * res - v["org"][0] + margin,
        "y": r * res - v["org"][1] + margin,
    })
    return True
