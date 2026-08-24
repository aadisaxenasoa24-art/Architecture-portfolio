"""
Tessellate and render the Rhino assembly, reading the .3dm off disk.

The pictures are made from the file's own extrusions - outer profile, hole
profiles and path - so if a hole were missing from a board it would be missing
from the picture too.
"""
import numpy as np
import mapbox_earcut as earcut
import rhino3dm as r3

import config
import validate_3dm as V


def _cap_tris(rings):
    """Triangulate one cap: rings[0] outer, the rest holes."""
    verts, ends = [], []
    for r in rings:
        pts = r[:-1] if np.allclose(r[0], r[-1]) else r
        verts.append(pts)
        ends.append(sum(len(v) for v in verts))
    V2 = np.vstack(verts)
    idx = earcut.triangulate_float64(V2, np.array(ends, dtype=np.uint32))
    return V2, idx.reshape(-1, 3)


def _inside(ring, p):
    x, y = p
    n = len(ring) - 1
    c = False
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        if (y1 > y) != (y2 > y):
            xx = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xx:
                c = not c
    return c


def tessellate(path, explode=0.0, skip_layers=(), only_layers=None,
               level_range=None, keep_bbox=None, keep_over=None, over_r=60.0,
               rod_from_level=None):
    """
    (tris (n,3,3), colours (n,3), meta) for every extrusion in the file.

    `level_range` and `keep_bbox` filter whole solids - never individual
    triangles - so a detail view still shows complete boards.
    """
    m, objs = V.read(path)
    lay_rgb = {}
    for i in range(len(m.Layers)):
        c = m.Layers[i].Color
        lay_rgb[m.Layers[i].Name] = np.array([c[0], c[1], c[2]], float) / 255.0

    tris, cols = [], []
    for o in objs:
        if o["type"] != "Extrusion":
            continue
        name = o["layer"]
        leaf = name.rsplit("/", 1)[-1]
        if any(name.startswith(s) for s in skip_layers):
            continue
        if only_layers is not None and not any(name.startswith(s) for s in only_layers):
            continue
        if level_range is not None and leaf.startswith("L") and leaf[1:].isdigit():
            if not (level_range[0] <= int(leaf[1:]) <= level_range[1]):
                continue
        rings, (z0, z1) = V.profiles_of(o["geom"])
        za, zb = z0, z1
        if keep_bbox is not None:
            c = rings[0][:-1].mean(axis=0)
            if not (keep_bbox[0] <= c[0] <= keep_bbox[1]
                    and keep_bbox[2] <= c[1] <= keep_bbox[3]):
                continue
        if keep_over is not None:
            if name.startswith("03_DOWEL"):
                c = rings[0][:-1].mean(axis=0)
                if np.hypot(c[0] - keep_over[0], c[1] - keep_over[1]) > over_r:
                    continue
            elif not _inside(rings[0], keep_over):
                continue
        dz = 0.0
        if explode:
            if leaf.startswith("L") and leaf[1:].isdigit():
                dz = (int(leaf[1:]) - config.BASE_LEVEL) * explode
            elif name.startswith("01_BASE"):
                dz = 0.0
            elif name.startswith("03_DOWEL"):
                # a rod has to stretch to keep threading the boards it serves
                top = int(round(z1 * config.SCALE / 1000.0)) - 1
                zb = z1 + (top - config.BASE_LEVEL) * explode
                if rod_from_level is None:
                    za = z0
                else:
                    za = (rod_from_level * 1000.0 / config.SCALE
                          + (rod_from_level - config.BASE_LEVEL) * explode)
                dz = None
            else:
                dz = (z0 - config.BASE_LEVEL * 1000.0 / config.SCALE) \
                     / config.BOARD_MM * explode
        if dz is not None:
            za, zb = z0 + dz, z1 + dz
        rgb = lay_rgb.get(leaf, lay_rgb.get(name, np.array([0.6, 0.6, 0.6])))

        P2, faces = _cap_tris(rings)
        top = np.dstack([P2[:, 0], P2[:, 1], np.full(len(P2), zb)])[0]
        bot = np.dstack([P2[:, 0], P2[:, 1], np.full(len(P2), za)])[0]
        tris.append(top[faces])
        tris.append(bot[faces][:, ::-1])
        cols.append(np.repeat(rgb[None], len(faces) * 2, axis=0))

        for r in rings:
            pts = r[:-1] if np.allclose(r[0], r[-1]) else r
            n = len(pts)
            a = np.column_stack([pts, np.full(n, za)])
            b = np.column_stack([pts, np.full(n, zb)])
            i0 = np.arange(n)
            i1 = (i0 + 1) % n
            q = np.stack([np.stack([a[i0], a[i1], b[i1]], 1),
                          np.stack([a[i0], b[i1], b[i0]], 1)]).reshape(-1, 3, 3)
            tris.append(q)
            cols.append(np.repeat(rgb[None], len(q), axis=0))

    T = np.vstack(tris)
    C = np.vstack(cols)
    return T, C, {"objects": len(objs), "triangles": len(T)}


def shade(tris, base_cols, light=(-0.45, -0.62, 0.62), ambient=0.38):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.where(ln == 0, 1, ln)
    L = np.array(light, float)
    L /= np.linalg.norm(L)
    lam = np.clip(n @ L, 0, 1)
    return np.clip(base_cols * (ambient + (1 - ambient) * lam)[:, None], 0, 1)
