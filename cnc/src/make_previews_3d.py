#!/usr/bin/env python3
"""
Render the delivered 3-D files, and pack them for the web viewer.

    python3 make_previews_3d.py [--out DIR] [--docs DIR]

Everything is read back out of output/MASTER_*.stl and output/MASTER_*.dxf, so
the images and the viewer show the files that ship, not the in-memory model.
"""
import argparse
import base64
import json
import os
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config
import render3d as R

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _fit(tris, size, azim, elev, vex, pad, base, top, W, H):
    Rm = R.camera(azim, elev)
    centre = np.array([W / 2, H / 2, (base + top) / 2 * vex])
    P = tris.reshape(-1, 3).copy()
    P[:, 2] *= vex
    Q = (P - centre) @ Rm.T
    span = max(np.ptp(Q[:, 0]), np.ptp(Q[:, 1]) * size[0] / size[1])
    s = size[0] / (span * pad)

    def proj(A):
        A = np.asarray(A, dtype=float).reshape(-1, 3).copy()
        A[:, 2] *= vex
        B = (A - centre) @ Rm.T
        return np.stack([B[:, 0] * s + size[0] / 2, size[1] / 2 - B[:, 1] * s, B[:, 2]], axis=1)
    return proj


def render(tris, size, azim, elev, vex, base, top, W, H,
           lines=None, boxes=None, water=None, lw=1.0, pad=1.05, ss=2, bias=2.5):
    proj = _fit(tris, size, azim, elev, vex, pad, base, top, W, H)
    img, z = R.rasterise(proj(tris).reshape(-1, 3, 3), R.shade(tris, base, top), size, ss=ss)
    img[np.isinf(z)] = np.array([1.0, 1.0, 1.0], dtype=np.float32)
    if water:
        R.draw_lines(img, z, [proj(a) for a in water], (0.0, 0.62, 0.72), lw=2.0, bias=bias)
    if lines:
        R.draw_lines(img, z, [proj(l) for l in lines], (0.13, 0.13, 0.16), lw=lw, bias=bias)
    if boxes:
        R.draw_lines(img, z, [proj(b) for b in boxes], (0.09, 0.20, 0.50), lw=1.0, bias=bias)
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def label(arr, title, sub):
    im = Image.fromarray(arr)
    d = ImageDraw.Draw(im)
    try:
        f1 = ImageFont.truetype(FONT_B, 30)
        f2 = ImageFont.truetype(FONT_R, 22)
    except Exception:
        f1 = f2 = ImageFont.load_default()
    d.text((34, 26), title, fill=(20, 20, 24), font=f1)
    d.text((34, 64), sub, fill=(95, 95, 105), font=f2)
    return np.array(im)


def pack_viewer_data(out_dir, dowels=None, sockets=None):
    """Payload for docs/model-viewer.html - height grid, line sets, registration."""
    tris = R.read_stl(os.path.join(out_dir, "MASTER_TERRAIN_1to500.stl"))
    V = tris.reshape(-1, 3)
    base = config.BASE_LEVEL * 1000.0 / config.SCALE
    top = V[:, 2] > base + 1e-6
    xs = np.unique(np.round(V[top, 0], 4))
    ys = np.unique(np.round(V[top, 1], 4))
    G = np.full((len(ys), len(xs)), np.nan)
    G[np.searchsorted(ys, np.round(V[top, 1], 4)),
      np.searchsorted(xs, np.round(V[top, 0], 4))] = V[top, 2]
    assert not np.isnan(G).any(), "the STL is not a complete regular grid"

    M = R.read_master_dxf(os.path.join(out_dir, "MASTER_3D_1to500.dxf"))

    def b64(a):
        return base64.b64encode(a.tobytes()).decode()

    def lines(sets):
        X, Y, Z, off = [], [], [], [0]
        for a in sets:
            X.append(np.round(a[:, 0] * 10).astype(np.int16))
            Y.append(np.round(a[:, 1] * 10).astype(np.int16))
            Z.append(np.round(a[:, 2] * 100).astype(np.int16))
            off.append(off[-1] + len(a))
        if not X:
            X = [np.zeros(0, np.int16)]; Y = X; Z = X
        return (b64(np.concatenate(X)), b64(np.concatenate(Y)),
                b64(np.concatenate(Z)), b64(np.array(off, dtype=np.int32)))

    import assembly as _asm
    if dowels is None or sockets is None:
        import pickle as _p
        _c = os.path.join(os.path.dirname(out_dir), ".cache", "assembly.pkl")
        _d = _p.load(open(_c, "rb"))
        dowels, sockets = _d["dowels"], _d["sockets"]

    cont = [a for L in sorted(M["contours"]) for a in M["contours"][L]]
    cx, cy, cz, coff = lines(cont)
    bx, by, bz, boff = lines(M["boxes"])
    wx, wy, wz, woff = lines(M["water"])
    sock_rings = []
    for L, v in sorted(sockets.items()):
        for s_ in v:
            r = np.asarray(s_["poly"].exterior.coords)
            z = (L + 1) * 1000.0 / config.SCALE
            sock_rings.append(np.column_stack([r[:, 0], r[:, 1], np.full(len(r), z)]))
    sx, sy, sz, soff = lines(sock_rings)

    rod = np.array([[d["x"], d["y"], base,
                     (d["top_level"] + 1) * 1000.0 / config.SCALE] for d in dowels],
                   dtype=np.float64) if dowels else np.zeros((0, 4))
    return {
        "rodDia": _asm.ROD_DIA, "holeDia": _asm.HOLE_DIA,
        "rods": b64(np.round(rod * 100).astype(np.int32)),
        "nRods": len(rod),
        "sx": sx, "sy": sy, "sz": sz, "soff": soff,
        "w": config.MODEL_W_M * 1000 / config.SCALE,
        "h": config.MODEL_H_M * 1000 / config.SCALE,
        "base": base, "levelMin": config.LEVEL_MIN, "levelMax": config.LEVEL_MAX,
        "board": config.BOARD_MM, "scale": config.SCALE,
        "nx": len(xs), "ny": len(ys),
        "gx0": float(xs[0]), "gx1": float(xs[-1]),
        "gy0": float(ys[0]), "gy1": float(ys[-1]),
        "grid": b64(np.round(G * 100).astype(np.int16)),
        "cx": cx, "cy": cy, "cz": cz, "coff": coff,
        "bx": bx, "by": by, "bz": bz, "boff": boff,
        "wx": wx, "wy": wy, "wz": wz, "woff": woff,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "..", "output"))
    ap.add_argument("--docs", default=os.path.join(HERE, "..", "docs"))
    ap.add_argument("--size", type=int, nargs=2, default=(1600, 1120))
    a = ap.parse_args()

    W = config.MODEL_W_M * 1000 / config.SCALE
    H = config.MODEL_H_M * 1000 / config.SCALE
    base = config.BASE_LEVEL * 1000.0 / config.SCALE
    top = (config.LEVEL_MAX + 1) * 1000.0 / config.SCALE
    size = tuple(a.size)

    stl = R.read_stl(os.path.join(a.out, "MASTER_TERRAIN_1to500.stl"))
    M = R.read_master_dxf(os.path.join(a.out, "MASTER_3D_1to500.dxf"))
    cont = [x for L in sorted(M["contours"]) for x in M["contours"][L]]
    grid = R.stepped_heightfield(M["contours"], W, H, config.BASE_LEVEL, config.SCALE, px=1500)
    stack = R.grid_to_tris(grid[::2, ::2], W, H, config.SCALE)
    print(f"STL {len(stl):,} tris   stack {len(stack):,} tris")

    jobs = [
        ("p3d_terrain.png", stl, dict(azim=-58, elev=33, vex=1.0, lines=cont, water=M["water"]),
         "MASTER_TERRAIN_1to500.stl  +  MASTER_3D_1to500.dxf contours",
         "true vertical scale  -  1200 x 1080 x 48 mm  -  1 m contours, 44-67 m"),
        ("p3d_stack.png", stack, dict(azim=-58, elev=33, vex=1.0),
         "As-built stack  -  25 boards of 2.0 mm",
         "rebuilt from the delivered contour polygons  -  true vertical scale"),
        ("p3d_stack_boxes.png", stack, dict(azim=-58, elev=33, vex=1.0, boxes=M["boxes"]),
         "As-built stack  +  roof out-to-out boxes",
         "293 building boxes draped on the terraces"),
        ("p3d_exag.png", stl, dict(azim=-58, elev=26, vex=3.0, lines=cont, lw=1.2, water=M["water"]),
         "Same model, vertical x3  -  reading aid only",
         "the delivered file is true scale; this view exaggerates height so the landform reads"),
    ]
    tiles = []
    for name, tri, kw, title, sub in jobs:
        t = time.time()
        im = label(render(tri, size, base=base, top=top, W=W, H=H, **kw), title, sub)
        Image.fromarray(im).save(os.path.join(a.docs, name))
        tiles.append(im)
        print(f"  {name:24s} {time.time()-t:6.1f}s")

    sheet = Image.new("RGB", (size[0] * 2 + 30, size[1] * 2 + 30), "white")
    for i, t in enumerate(tiles):
        sheet.paste(Image.fromarray(t), ((i % 2) * (size[0] + 10) + 10, (i // 2) * (size[1] + 10) + 10))
    sheet.save(os.path.join(a.docs, "preview_3d.png"))
    print("  preview_3d.png", sheet.size)

    data = pack_viewer_data(a.out)
    p = os.path.join(a.docs, "model-viewer.data.json")
    json.dump(data, open(p, "w"))
    print(f"  viewer payload {os.path.getsize(p)/1024:.0f} KB -> {os.path.basename(p)}")
    print("  (docs/model-viewer.html embeds this payload inline)")


if __name__ == "__main__":
    main()
