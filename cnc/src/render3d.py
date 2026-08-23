"""
Render the delivered 3-D files.

Reads MASTER_TERRAIN_*.stl and MASTER_3D_*.dxf back off disk and rasterises
them with a small z-buffer renderer, so what you see is the file that ships,
not the model that was in memory when it was written.
"""
import struct

import ezdxf
import numpy as np


# --------------------------------------------------------------------------
# readers

def read_stl(path):
    with open(path, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        raw = np.frombuffer(f.read(n * 50), dtype=np.uint8).reshape(n, 50)
    return raw[:, 12:48].copy().view("<f4").reshape(n, 3, 3).astype(np.float64)


def read_master_dxf(path):
    """{'contours': {level: [ring, ...]}, 'boxes': [...], 'water': [...]}"""
    doc = ezdxf.readfile(path)
    out = {"contours": {}, "boxes": [], "footprints": [], "water": [], "boundary": []}
    for e in doc.modelspace():
        if e.dxftype() != "POLYLINE":
            continue
        a = np.array([(p[0], p[1], p[2]) for p in e.points()])
        if len(a) < 3:
            continue
        a = np.vstack([a, a[:1]])
        lay = e.dxf.layer
        if lay.startswith("CONTOUR_"):
            out["contours"].setdefault(int(lay.split("_")[1]), []).append(a)
        elif lay.startswith("BLDG_BOX_"):
            out["boxes"].append(a)
        elif lay.startswith("BLDG_FOOTPRINT_"):
            out["footprints"].append(a)
        elif lay == "WATER":
            out["water"].append(a)
        elif lay == "MODEL_BOUNDARY":
            out["boundary"].append(a)
    return out


def stepped_heightfield(contours, w_mm, h_mm, base_level, scale, px=1400):
    """
    Rebuild the as-built board stack from the delivered contour polygons.

    Rasterises each level's polygon (holes punched out) and keeps the highest
    level covering each cell - exactly what the glued stack of 2 mm boards is.
    """
    from PIL import Image, ImageDraw
    ny = int(round(px * h_mm / w_mm))
    grid = np.full((ny, px), float(base_level))
    for L in sorted(contours):
        img = Image.new("1", (px, ny), 0)
        d = ImageDraw.Draw(img)
        rings = contours[L]
        areas = []
        for r in rings:
            x, y = r[:, 0], r[:, 1]
            areas.append(0.5 * np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))
        order = np.argsort(-np.abs(np.array(areas)))
        for i in order:
            r = rings[i]
            pts = [(x / w_mm * px, y / h_mm * ny) for x, y, _z in r]
            d.polygon(pts, fill=1 if areas[i] > 0 else 0)
        m = np.array(img, dtype=bool)
        grid[m] = L
    return grid


def grid_to_tris(grid, w_mm, h_mm, scale):
    """Regular grid heightfield -> triangles, in model millimetres."""
    ny, nx = grid.shape
    x = np.linspace(0, w_mm, nx)
    y = np.linspace(0, h_mm, ny)
    X, Y = np.meshgrid(x, y)
    Z = grid * 1000.0 / scale
    V = np.stack([X, Y, Z], axis=-1)
    a, b = V[:-1, :-1], V[:-1, 1:]
    c, d = V[1:, 1:], V[1:, :-1]
    return np.vstack([np.stack([a, b, c], -2).reshape(-1, 3, 3),
                      np.stack([a, c, d], -2).reshape(-1, 3, 3)])


# --------------------------------------------------------------------------
# renderer

def camera(azim=-55.0, elev=32.0):
    a, e = np.radians(azim), np.radians(elev)
    fwd = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    up0 = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, up0)
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    # depth axis points away from the camera, so a smaller value is nearer
    return np.stack([right, up, -fwd])         # rows: x_cam, y_cam, depth


def project(P, R, centre, spanpx, size, vert_exag=1.0):
    P = np.asarray(P, dtype=np.float64).reshape(-1, 3).copy()
    P[:, 2] *= vert_exag
    Q = (P - centre) @ R.T
    w, h = size
    s = spanpx
    return np.stack([Q[:, 0] * s + w / 2.0, h / 2.0 - Q[:, 1] * s, Q[:, 2]], axis=1)


def rasterise(tris_s, colours, size, ss=2):
    """Flat-shaded z-buffer fill.  tris_s: (n,3,3) already in screen space."""
    w, h = size[0] * ss, size[1] * ss
    zbuf = np.full((h, w), np.inf)
    img = np.zeros((h, w, 3), dtype=np.float32)
    T = tris_s.copy()
    T[:, :, 0] *= ss
    T[:, :, 1] *= ss

    for i in range(len(T)):
        t = T[i]
        x0 = int(np.floor(t[:, 0].min())); x1 = int(np.ceil(t[:, 0].max()))
        y0 = int(np.floor(t[:, 1].min())); y1 = int(np.ceil(t[:, 1].max()))
        if x1 < 0 or y1 < 0 or x0 >= w or y0 >= h:
            continue
        x0 = max(x0, 0); y0 = max(y0, 0); x1 = min(x1, w - 1); y1 = min(y1, h - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs = np.arange(x0, x1 + 1) + 0.5
        ys = np.arange(y0, y1 + 1) + 0.5
        PX, PY = np.meshgrid(xs, ys)
        ax, ay = t[0, 0], t[0, 1]
        bx, by = t[1, 0], t[1, 1]
        cx, cy = t[2, 0], t[2, 1]
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        l0 = ((by - cy) * (PX - cx) + (cx - bx) * (PY - cy)) / den
        l1 = ((cy - ay) * (PX - cx) + (ax - cx) * (PY - cy)) / den
        l2 = 1.0 - l0 - l1
        m = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        if not m.any():
            continue
        z = l0 * t[0, 2] + l1 * t[1, 2] + l2 * t[2, 2]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        hit = m & (z < sub)
        if not hit.any():
            continue
        sub[hit] = z[hit]
        img[y0:y1 + 1, x0:x1 + 1][hit] = colours[i]
    if ss > 1:
        img = img.reshape(size[1], ss, size[0], ss, 3).mean(axis=(1, 3))
        zbuf = zbuf.reshape(size[1], ss, size[0], ss).min(axis=(1, 3))
    return img, zbuf


TERRAIN_STOPS = [
    (0.00, (0.24, 0.45, 0.66)), (0.10, (0.36, 0.62, 0.55)),
    (0.28, (0.55, 0.72, 0.45)), (0.45, (0.79, 0.79, 0.50)),
    (0.62, (0.80, 0.68, 0.45)), (0.80, (0.70, 0.55, 0.44)),
    (1.00, (0.96, 0.95, 0.94)),
]


def hypsometric(t):
    t = np.clip(t, 0, 1)
    stops = np.array([s[0] for s in TERRAIN_STOPS])
    cols = np.array([s[1] for s in TERRAIN_STOPS])
    out = np.empty((len(t), 3))
    for k in range(3):
        out[:, k] = np.interp(t, stops, cols[:, k])
    return out


def shade(tris, zmin, zmax, light=(-0.45, -0.7, 0.75), ambient=0.34):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.where(ln == 0, 1, ln)
    L = np.array(light, dtype=float)
    L /= np.linalg.norm(L)
    lam = np.clip(n @ L, 0, 1)
    base = hypsometric((tris[:, :, 2].mean(axis=1) - zmin) / max(zmax - zmin, 1e-9))
    return np.clip(base * (ambient + (1 - ambient) * lam)[:, None], 0, 1)


def draw_lines(img, zbuf, segs_s, colour, lw=1.0, bias=0.6):
    """Depth-tested polyline overlay, drawn with a simple DDA."""
    h, w = zbuf.shape
    col = np.array(colour, dtype=np.float32)
    r = int(max(0, round(lw - 1)))
    for s in segs_s:
        for i in range(len(s) - 1):
            p, q = s[i], s[i + 1]
            n = int(max(abs(q[0] - p[0]), abs(q[1] - p[1]))) + 1
            if n > 6000:
                continue
            t = np.linspace(0, 1, n)
            xs = p[0] + (q[0] - p[0]) * t
            ys = p[1] + (q[1] - p[1]) * t
            zs = p[2] + (q[2] - p[2]) * t - bias
            xi = np.round(xs).astype(int)
            yi = np.round(ys).astype(int)
            ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
            if not ok.any():
                continue
            xi, yi, zs = xi[ok], yi[ok], zs[ok]
            vis = zs <= zbuf[yi, xi] + 1e-6
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    X = np.clip(xi + dx, 0, w - 1)
                    Y = np.clip(yi + dy, 0, h - 1)
                    img[Y[vis], X[vis]] = col
    return img
