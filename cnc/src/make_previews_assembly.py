#!/usr/bin/env python3
"""
Views of the Rhino assembly, tessellated from MASTER_ASSEMBLY_1to500.3dm.

    python3 make_previews_assembly.py [--out DIR] [--docs DIR]

Nothing is drawn from the in-memory model - every board, hole, socket and rod
comes out of the .3dm, so a feature missing from the file is missing here too.
"""
import argparse
import os
import pickle
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import assembly
import config
import render3d as R
import render_3dm as R3

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
ASM = "MASTER_ASSEMBLY_1to500.3dm"


def view(tris, cols, size, azim, elev, pad=1.06, ss=2):
    Rm = R.camera(azim, elev)
    P = tris.reshape(-1, 3)
    centre = (P.min(0) + P.max(0)) / 2
    Q = (P - centre) @ Rm.T
    span = max(np.ptp(Q[:, 0]), np.ptp(Q[:, 1]) * size[0] / size[1])
    s = size[0] / (span * pad)
    ts = np.stack([Q[:, 0] * s + size[0] / 2,
                   size[1] / 2 - Q[:, 1] * s, Q[:, 2]], axis=1).reshape(-1, 3, 3)
    img, z = R.rasterise(ts, R3.shade(tris, cols), size, ss=ss)
    img[np.isinf(z)] = np.array([1, 1, 1], dtype=np.float32)
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def label(a, title, sub):
    im = Image.fromarray(a)
    d = ImageDraw.Draw(im)
    try:
        f1, f2 = ImageFont.truetype(FONT_B, 28), ImageFont.truetype(FONT_R, 20)
    except Exception:
        f1 = f2 = ImageFont.load_default()
    d.text((30, 24), title, fill=(20, 20, 24), font=f1)
    d.text((30, 58), sub, fill=(95, 95, 105), font=f2)
    return np.array(im)


def registration_plan(profiles, dowels, sockets, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    parts = assembly.part_polygons(profiles)
    W = config.MODEL_W_M * 1000 / config.SCALE
    H = config.MODEL_H_M * 1000 / config.SCALE
    fig, ax = plt.subplots(figsize=(15, 14), dpi=110)
    for L in sorted(parts):
        c = plt.cm.terrain((L - config.LEVEL_MIN) / 23)
        for p in parts[L]:
            ax.plot(*p.exterior.xy, color=c, lw=0.7)
            for r in p.interiors:
                ax.plot(*r.xy, color="red", lw=1.0)
    for L, v in sockets.items():
        for s in v:
            ax.fill(*s["poly"].exterior.xy, color="#1f5fd2", alpha=0.55,
                    ec="#0b2f66", lw=0.6)
    for d in dowels:
        ax.add_patch(plt.Circle((d["x"], d["y"]), assembly.HOLE_DIA / 2, color="k", zorder=9))
        ax.add_patch(plt.Circle((d["x"], d["y"]), 9, fill=False, color="k", lw=1.0, zorder=9))
        ax.annotate(f"{d['id']}\nL{d['top_level']}", (d["x"], d["y"]),
                    textcoords="offset points", xytext=(11, 6), fontsize=8, weight="bold",
                    bbox=dict(fc="white", ec="none", alpha=.8, pad=0.5), zorder=10)
    ax.add_patch(plt.Rectangle((0, 0), W, H, fill=False, ec="k", lw=2))
    ax.set_xlim(-30, W + 30)
    ax.set_ylim(-30, H + 30)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"Registration plan  -  {len(dowels)} dowels "
                 f"({assembly.ROD_DIA:.1f} mm rod / {assembly.HOLE_DIA:.1f} mm hole), "
                 f"{sum(len(v) for v in sockets.values())} building sockets (blue)",
                 fontsize=13)
    fig.tight_layout()
    fig.savefig(out_png, facecolor="white")
    plt.close(fig)
    return out_png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "..", "output"))
    ap.add_argument("--docs", default=os.path.join(HERE, "..", "docs"))
    ap.add_argument("--cache", default=os.path.join(HERE, "..", ".cache"))
    a = ap.parse_args()
    path = os.path.join(a.out, ASM)
    SIZE = (1600, 1120)
    SKIP = ("04_BUILDING", "05_ROOF")

    A = pickle.load(open(os.path.join(a.cache, "assembly.pkl"), "rb"))
    P = pickle.load(open(os.path.join(a.cache, "profiles.pkl"), "rb"))
    registration_plan(P, A["dowels"], A["sockets"],
                      os.path.join(a.docs, "preview_registration.png"))
    print("  preview_registration.png")

    jobs = [
        ("asm_assembled.png", dict(explode=0.0), (-58, 33), SIZE,
         "MASTER_ASSEMBLY_1to500.3dm  -  assembled",
         "25 boards of 2.0 mm, 28 dowel rods, 293 building blocks at a nominal "
         f"{config.BUILDING_H_NOMINAL_M:.0f} m"),
        ("asm_noblocks.png", dict(explode=0.0, skip_layers=SKIP), (-58, 33), SIZE,
         "Boards and rods only",
         "the terrain stack without the building blocks"),
        ("asm_exploded.png", dict(explode=30.0, skip_layers=SKIP), (-58, 22), SIZE,
         "Exploded  -  every board lifted 30 mm",
         "every board is a separate closed solid - the 3.2 mm dowel holes and the "
         "sockets are cut, not drawn on"),
        ("asm_detail.png",
         dict(explode=20.0, skip_layers=SKIP + ("01_BASE",), level_range=(62, 67),
              keep_over=(A["dowels"][0]["x"], A["dowels"][0]["y"]), over_r=70.0,
              rod_from_level=62),
         (-48, 30), (1500, 1050),
         "Detail  -  the stack over the south-west summit, exploded 20 mm",
         "boards L62 to L67 threaded on dowels D01, D02, D03 - the 3.2 mm holes are "
         "cut through each solid"),
    ]
    tiles = {}
    for name, kw, (az, el), size, t1, t2 in jobs:
        t = time.time()
        T, C, meta = R3.tessellate(path, **kw)
        im = label(view(T, C, size, az, el), t1, t2)
        Image.fromarray(im).save(os.path.join(a.docs, name))
        tiles[name] = im
        print(f"  {name:22s} {meta['triangles']:>8,} tris  {time.time()-t:6.1f}s")

    order = ["asm_assembled.png", "asm_exploded.png", "asm_detail.png"]
    ims = [Image.fromarray(tiles[n]) for n in order]
    w = max(i.width for i in ims)
    sheet = Image.new("RGB", (w, sum(i.height for i in ims) + 20), "white")
    y = 0
    for i in ims:
        sheet.paste(i, (0, y))
        y += i.height + 10
    sheet.save(os.path.join(a.docs, "preview_assembly.png"))
    print("  preview_assembly.png", sheet.size)


if __name__ == "__main__":
    main()
