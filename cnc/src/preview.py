"""Preview images, rendered from the emitted DXF/STL files - not from memory."""
import glob
import os

import ezdxf
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

import config

STYLE = {
    "CUT_OUTER": ("#d21e1e", 1.1), "CUT_INNER": ("#d21e1e", 1.1),
    "ENGRAVE_NEXT": ("#1f9e4a", 0.5), "ENGRAVE_BLDG_BOX": ("#1f5fd2", 0.45),
    "ENGRAVE_BLDG_FOOTPRINT": ("#9a9a9a", 0.35),
    "ENGRAVE_SITE_BOUNDARY": ("#c000c0", 0.6),
    "ENGRAVE_TEXT": ("#e08a00", 0.7), "ENGRAVE_NORTH": ("#e08a00", 0.7),
    "SHEET_EDGE": ("#202020", 1.4),
}


def _read(path):
    doc = ezdxf.readfile(path)
    out = {}
    for e in doc.modelspace():
        if e.dxftype() != "LWPOLYLINE":
            continue
        pts = np.array([(p[0], p[1]) for p in e.get_points("xy")])
        if e.closed and len(pts) > 2:
            pts = np.vstack([pts, pts[:1]])
        out.setdefault(e.dxf.layer, []).append(pts)
    return out


def sheet_contact(sheet_dir, out_png, cols=5):
    files = sorted(glob.glob(os.path.join(sheet_dir, "*.dxf")))
    rows = (len(files) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.5, rows * 3.7), dpi=115)
    axes = np.atleast_2d(axes)
    S = config.SHEET_MM
    for k in range(rows * cols):
        ax = axes[k // cols][k % cols]
        ax.axis("off")
        if k >= len(files):
            continue
        lay = _read(files[k])
        for name, polys in lay.items():
            col, lw = STYLE.get(name, ("#888888", 0.4))
            ax.add_collection(LineCollection(polys, colors=col, linewidths=lw))
        ax.set_xlim(-25, S + 25); ax.set_ylim(-25, S + 25); ax.set_aspect("equal")
        n = sum(len(v) for kk, v in lay.items() if kk.startswith("CUT_"))
        ax.set_title(f"sheet {k+1}  -  {n} cut profiles", fontsize=9)
    fig.suptitle("SHREYAS 1:500 terrain - nested 4 ft x 4 ft cutting sheets  "
                 "(red = cut, green = next-layer glue guide, blue = roof out-to-out box)",
                 fontsize=12, y=0.998)
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    fig.savefig(out_png, facecolor="white")
    plt.close(fig)
    return out_png


def single_sheet(path, out_png):
    lay = _read(path)
    S = config.SHEET_MM
    fig, ax = plt.subplots(figsize=(11, 11), dpi=140)
    for name, polys in lay.items():
        col, lw = STYLE.get(name, ("#888888", 0.5))
        ax.add_collection(LineCollection(polys, colors=col, linewidths=lw * 1.7))
    ax.set_xlim(-20, S + 20); ax.set_ylim(-20, S + 20); ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(os.path.basename(path), fontsize=11)
    fig.tight_layout(); fig.savefig(out_png, facecolor="white"); plt.close(fig)
    return out_png


def model_preview(Z, boxes, out_png):
    W, H = config.MODEL_W_M * 1000.0, config.MODEL_H_M * 1000.0
    ls = matplotlib.colors.LightSource(azdeg=315, altdeg=45)
    fig, ax = plt.subplots(figsize=(13, 12), dpi=130)
    rgb = ls.shade(Z, cmap=plt.cm.terrain, blend_mode="soft",
                   vert_exag=6.0, dx=0.25, dy=0.25)
    ax.imshow(rgb, origin="lower", extent=[0, W, 0, H], aspect="equal")
    cs = ax.contour(np.linspace(0, W, Z.shape[1]), np.linspace(0, H, Z.shape[0]), Z,
                    levels=range(config.LEVEL_MIN, config.LEVEL_MAX + 1),
                    colors="k", linewidths=0.35, alpha=0.55)
    ax.clabel(cs, levels=range(config.LEVEL_MIN, config.LEVEL_MAX + 1, 2),
              fmt="%d", fontsize=6)
    for kind, col in (("raster", "#8b0000"), ("campus", "#101010"), ("platform", "#404060")):
        for e in boxes.get(kind, ()):
            b = e.get("box_clip")
            if b is not None:
                ax.plot(b[:, 0], b[:, 1], color=col, lw=0.55)
    for e in boxes.get("water", ()):
        f = e.get("footprint_clip")
        if f is not None:
            ax.fill(f[:, 0], f[:, 1], color="#00b4c8")
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    ax.set_title("SHREYAS - 600 x 540 m model window, 1 m contours 44-67 m, "
                 "roof out-to-out boxes", fontsize=12)
    fig.tight_layout(); fig.savefig(out_png, facecolor="white"); plt.close(fig)
    return out_png


def iso_preview(Z, out_png, step_m=4.0):
    from mpl_toolkits.mplot3d import Axes3D  # noqa
    s = int(step_m / config.DEM_CELL_M)
    S = Z[::s, ::s]
    W, H = config.MODEL_W_M, config.MODEL_H_M
    x = np.linspace(0, W, S.shape[1]); y = np.linspace(0, H, S.shape[0])
    X, Y = np.meshgrid(x, y)
    Q = np.floor(S)                       # the stepped, board-by-board surface
    fig = plt.figure(figsize=(15, 9), dpi=130)
    for i, (data, title) in enumerate(((S, "interpolated terrain surface"),
                                       (Q, "as-built 2 mm board stack"))):
        ax = fig.add_subplot(1, 2, i + 1, projection="3d")
        ax.plot_surface(X, Y, data, cmap="terrain", linewidth=0, antialiased=False,
                        rstride=1, cstride=1, vmin=43, vmax=68)
        ax.set_box_aspect((W, H, (68 - 43) * 6))
        ax.view_init(elev=42, azim=-58)
        ax.set_axis_off(); ax.set_title(title, fontsize=11)
    fig.tight_layout(); fig.savefig(out_png, facecolor="white"); plt.close(fig)
    return out_png
