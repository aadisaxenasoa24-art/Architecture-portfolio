"""
The roof out-to-out boxes on their own, as 2-D DXF plus a schedule.

Every building the drawing carries is included - the raster-traced context
blocks, the campus masses and the platforms - with its overall (out-to-out)
plan rectangle, the rectangle's true bearing, and whether it falls inside the
600 x 540 m model window.
"""
import csv

import ezdxf
import numpy as np

import config
import buildings as bld

KIND_LAYER = {
    "raster": ("BLDG_BOX_RASTER", "BLDG_FOOTPRINT_RASTER", 1, 12),
    "campus": ("BLDG_BOX_CAMPUS", "BLDG_FOOTPRINT_CAMPUS", 5, 8),
    "platform": ("BLDG_BOX_PLATFORM", "BLDG_FOOTPRINT_PLATFORM", 3, 94),
    "water": (None, "WATER", None, 4),
}


def all_boxes(paths):
    groups = bld.collect(paths)
    rows = []
    for kind, polys in groups.items():
        for i, poly in enumerate(polys):
            box = bld.min_area_rect(poly[:-1])
            if box is None:
                continue
            w, h = sorted((box["w"], box["h"]))
            ang = box["angle"] % 180.0
            rows.append({
                "kind": kind,
                "id": f"{kind[:3].upper()}-{i+1:03d}",
                "footprint": poly,
                "box": box["corners"],
                "short_mm": w, "long_mm": h,
                "bearing_deg": ang,
                "box_area_m2": w * h / 1e6,
                "foot_area_m2": _area(poly) / 1e6,
                "in_window": bld.in_window(poly),
            })
    return rows


def _area(a):
    x, y = a[:, 0], a[:, 1]
    return 0.5 * abs(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]))


def write_dxf(path, rows, scale=1):
    k = 1.0 / scale
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    for kind, (boxlay, footlay, boxcol, footcol) in KIND_LAYER.items():
        if boxlay and boxlay not in doc.layers:
            doc.layers.add(boxlay, color=boxcol)
        if footlay not in doc.layers:
            doc.layers.add(footlay, color=footcol)
    doc.layers.add("MODEL_WINDOW", color=7)
    W = config.MODEL_W_M * 1000.0 * k
    H = config.MODEL_H_M * 1000.0 * k
    msp.add_lwpolyline([(0, 0), (W, 0), (W, H), (0, H)],
                       dxfattribs={"layer": "MODEL_WINDOW", "closed": True})
    for r in rows:
        boxlay, footlay, _bc, _fc = KIND_LAYER[r["kind"]]
        if boxlay:
            msp.add_lwpolyline([(x * k, y * k) for x, y in r["box"]],
                               dxfattribs={"layer": boxlay, "closed": True})
        msp.add_lwpolyline([(x * k, y * k) for x, y in r["footprint"]],
                           dxfattribs={"layer": footlay, "closed": True})
    doc.saveas(path)
    return path


def write_schedule(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "kind", "out_to_out_long_m", "out_to_out_short_m",
                    "box_bearing_deg", "box_area_m2", "footprint_area_m2",
                    "centre_x_m", "centre_y_m", "inside_model_window"])
        for r in sorted(rows, key=lambda d: (d["kind"], -d["box_area_m2"])):
            c = r["box"][:4].mean(axis=0)
            w.writerow([r["id"], r["kind"],
                        round(r["long_mm"] / 1000.0, 2), round(r["short_mm"] / 1000.0, 2),
                        round(r["bearing_deg"], 1), round(r["box_area_m2"], 1),
                        round(r["foot_area_m2"], 1),
                        round(c[0] / 1000.0, 2), round(c[1] / 1000.0, 2),
                        "yes" if r["in_window"] else "no"])
    return path
