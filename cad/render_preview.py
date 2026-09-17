#!/usr/bin/env python3
"""Render PNG previews of each drawing so the geometry can be eyeballed."""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import Configuration, ColorPolicy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ama_params as P

OUT = os.path.join(HERE, "preview")
os.makedirs(OUT, exist_ok=True)

VIEWS = {
    "01_site":      ("SITE",   -36000, -58000, 162000, 122000),
    "02_ground":    ("GF",     -34000, -30000, 165000, 68000),
    "03_first":     ("FF",     -34000, -30000, 165000, 68000),
    "04_roof":      ("ROOF",   -34000, -30000, 165000, 68000),
    "05_sec_aa":    ("SEC_AA", -18000, -12000, 135000, 34000),
    "06_sec_bb":    ("SEC_BB", -18000, -12000,  62000, 34000),
    "07_sec_cc":    ("SEC_CC", -18000, -12000,  62000, 34000),
    "08_elev_n":    ("ELEV_N", -18000, -14000, 135000, 34000),
    "09_elev_s":    ("ELEV_S", -18000, -14000, 135000, 34000),
    "10_elev_e":    ("ELEV_E", -18000, -16000,  62000, 34000),
    "11_notes":     ("NOTES",   -4000, -52000,  52000, 58000),
}


def render(doc, name, key, dx, dy, w, h):
    ox, oy = P.ORIGINS[key]
    x0, y0 = ox + dx, oy + dy
    fig = plt.figure(figsize=(w / 4500.0, h / 4500.0), dpi=190)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("white")
    cfg = Configuration(color_policy=ColorPolicy.BLACK, lineweight_scaling=0.5)
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(
        doc.modelspace(), finalize=False)
    ax.set_xlim(x0, x0 + w)
    ax.set_ylim(y0, y0 + h)
    ax.set_aspect("equal")
    ax.axis("off")
    path = os.path.join(OUT, name + ".png")
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def main():
    doc = ezdxf.readfile(os.path.join(HERE, "AMA_Ahmedabad_HCP.dxf"))
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    for name, (key, dx, dy, w, h) in VIEWS.items():
        if only and not any(o in name for o in only):
            continue
        print(render(doc, name, key, dx, dy, w, h))


if __name__ == "__main__":
    main()
