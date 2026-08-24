"""
Step 7 - write the nested sheets as CNC-ready DXF.

Layer scheme (standard for router / laser CAM):
    CUT_OUTER               outer profile of every piece            - cut through
    CUT_INNER               terrain holes inside a piece            - cut first
    CUT_DOWEL_3.2           3.2 mm registration holes               - drill or mill
    CUT_SOCKET_BLDG         building locating sockets               - cut through
    ENGRAVE_NEXT            outline of the layer that stacks on top - glue guide
    ENGRAVE_BLDG_BOX        roof out-to-out boxes on the visible terrace
    ENGRAVE_BLDG_FOOTPRINT  true roof footprints
    ENGRAVE_SITE_BOUNDARY   campus boundary
    ENGRAVE_TEXT            part id / level, single-stroke so any CAM cuts it
    ENGRAVE_NORTH           north arrow
    SHEET_EDGE              the 4 ft x 4 ft blank - reference only, never cut
"""
import numpy as np
import ezdxf
from shapely.geometry import Polygon

import assembly
import config
import stickfont

LAYERS = [
    ("CUT_OUTER", 1), ("CUT_INNER", 1),
    ("CUT_DOWEL_%.1f" % assembly.HOLE_DIA, 2),
    ("CUT_SOCKET_BLDG", 4), ("ENGRAVE_NEXT", 3),
    ("ENGRAVE_BLDG_BOX", 5), ("ENGRAVE_BLDG_FOOTPRINT", 8),
    ("ENGRAVE_SITE_BOUNDARY", 6), ("ENGRAVE_TEXT", 2), ("ENGRAVE_NORTH", 2),
    ("SHEET_EDGE", 7), ("NOTES", 7),
]


def make_transform(part, rot, dx, dy):
    """Same transform the nester applied: rotate about the part centroid, then offset."""
    c = np.array(part["poly"].centroid.coords[0])
    if rot:
        t = np.radians(rot)
        R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    else:
        R = np.eye(2)
    off = np.array([dx, dy])

    def f(a):
        a = np.asarray(a, dtype=float)[:, :2]
        return (a - c) @ R.T + c + off
    return f


def _add(msp, layer, pts, closed=False):
    pts = np.asarray(pts, dtype=float)
    if len(pts) < 2:
        return
    msp.add_lwpolyline([(float(x), float(y)) for x, y in pts],
                       dxfattribs={"layer": layer, "closed": bool(closed)})


def _north_arrow(x, y, size, rot):
    """Arrow pointing to model north, rotated with the part."""
    body = np.array([(0, -size / 2), (0, size / 2)])
    head = np.array([(-size * 0.18, size * 0.22), (0, size / 2), (size * 0.18, size * 0.22)])
    out = [body, head]
    out += stickfont.text_polylines("N", 0, size * 0.60, size * 0.26, anchor="centre")
    t = np.radians(rot)
    R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    return [a @ R.T + np.array([x, y]) for a in out]


def _label_spot(part, tf):
    """A point guaranteed inside the piece, for the engraved id."""
    p = part["poly"]
    try:
        pt = p.representative_point()
    except Exception:
        pt = p.centroid
    return tf(np.array([[pt.x, pt.y]]))[0]


def write_sheet(path, sheet, index, total, variant="SOLID"):
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    msp = doc.modelspace()
    for name, col in LAYERS:
        if name not in doc.layers:
            doc.layers.add(name, color=col)

    S = config.SHEET_MM
    _add(msp, "SHEET_EDGE", [(0, 0), (S, 0), (S, S), (0, S)], closed=True)
    msp.add_text(
        f"SHREYAS 1:500 CNC TERRAIN  -  SHEET {index}/{total}  ({variant})   "
        f"BOARD {config.BOARD_MM:.1f} mm   4 ft x 4 ft ({S:.1f} x {S:.1f} mm)",
        height=8, dxfattribs={"layer": "NOTES"},
    ).set_placement((6, S + 12))

    for it in sheet["items"]:
        part = it["part"]
        tf = make_transform(part, it["rot"], it["x"], it["y"])
        geoms = part["poly"].geoms if hasattr(part["poly"], "geoms") else [part["poly"]]
        for g in geoms:
            _add(msp, "CUT_OUTER", tf(np.asarray(g.exterior.coords)), closed=True)
            for r in g.interiors:
                _add(msp, "CUT_INNER", tf(np.asarray(r.coords)), closed=True)
        dowel_layer = "CUT_DOWEL_%.1f" % assembly.HOLE_DIA
        for d in part.get("cut_dowels", ()):
            _add(msp, dowel_layer,
                 tf(assembly.dowel_circle(d["x"], d["y"])), closed=True)
            if min(part["poly"].bounds[2] - part["poly"].bounds[0],
                   part["poly"].bounds[3] - part["poly"].bounds[1]) >= 60:
                px, py = tf(np.array([[d["x"] + 3.4, d["y"] + 3.4]]))[0]
                for a in stickfont.text_polylines(d["id"], px, py, 3.0):
                    _add(msp, "ENGRAVE_TEXT", a)
        for ring in part.get("cut_sockets", ()):
            _add(msp, "CUT_SOCKET_BLDG", tf(ring), closed=True)
        for ring in part["engrave_next"]:
            _add(msp, "ENGRAVE_NEXT", tf(ring), closed=True)
        for ring in part["engrave_box"]:
            _add(msp, "ENGRAVE_BLDG_BOX", tf(ring), closed=True)
        for ring in part["engrave_foot"]:
            _add(msp, "ENGRAVE_BLDG_FOOTPRINT", tf(ring), closed=True)
        for kind, ln in part["engrave_extra"]:
            _add(msp, f"ENGRAVE_{kind}", tf(ln))

        x0, y0, x1, y1 = part["poly"].bounds
        span = min(x1 - x0, y1 - y0)
        h = min(5.0, span / 3.5)
        if h >= 1.6:
            px, py = _label_spot(part, tf)
            txt = f"{part['id']}  {part['level']}M"
            if h < 3.0:
                txt = part["id"]
            for a in stickfont.text_polylines(txt, px, py, h, anchor="centre"):
                _add(msp, "ENGRAVE_TEXT", a)
        if span >= 90:
            ax = x0 + (x1 - x0) * 0.06
            ay = y0 + (y1 - y0) * 0.06
            gx, gy = tf(np.array([[ax, ay]]))[0]
            for a in _north_arrow(gx, gy, 26.0, it["rot"]):
                _add(msp, "ENGRAVE_NORTH", a)

    doc.saveas(path)
    return path


def write_combined(path, sheets, variant="SOLID", cols=5, pitch=None):
    """All sheets side by side in one drawing, for checking."""
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    for name, col in LAYERS:
        if name not in doc.layers:
            doc.layers.add(name, color=col)
    S = config.SHEET_MM
    pitch = pitch or (S + 80)
    for i, sheet in enumerate(sheets):
        ox, oy = (i % cols) * pitch, -(i // cols) * pitch
        _add(msp, "SHEET_EDGE", [(ox, oy), (ox + S, oy), (ox + S, oy + S), (ox, oy + S)],
             closed=True)
        msp.add_text(f"SHEET {i+1}/{len(sheets)} ({variant})", height=22,
                     dxfattribs={"layer": "NOTES"}).set_placement((ox + 8, oy + S + 26))
        for it in sheet["items"]:
            part = it["part"]
            tf = make_transform(part, it["rot"], it["x"] + ox, it["y"] + oy)
            geoms = part["poly"].geoms if hasattr(part["poly"], "geoms") else [part["poly"]]
            for g in geoms:
                _add(msp, "CUT_OUTER", tf(np.asarray(g.exterior.coords)), closed=True)
                for r in g.interiors:
                    _add(msp, "CUT_INNER", tf(np.asarray(r.coords)), closed=True)
            for ring in part["engrave_next"]:
                _add(msp, "ENGRAVE_NEXT", tf(ring), closed=True)
    doc.saveas(path)
    return path


def cut_list(sheets, variant="SOLID"):
    rows = [("sheet", "part_id", "level_m", "rotation_deg",
             "bbox_w_mm", "bbox_h_mm", "cut_area_cm2", "outer_perimeter_mm",
             "terrain_holes", "dowel_holes", "dowel_ids", "building_sockets",
             "next_layer_rings", "bldg_boxes_engraved")]
    for i, sh in enumerate(sheets, 1):
        for it in sh["items"]:
            p = it["part"]
            x0, y0, x1, y1 = p["poly"].bounds
            geoms = p["poly"].geoms if hasattr(p["poly"], "geoms") else [p["poly"]]
            per = sum(g.exterior.length for g in geoms)
            holes = sum(len(g.interiors) for g in geoms)
            dow = p.get("cut_dowels", [])
            rows.append((i, p["id"], p["level"], it["rot"],
                         round(x1 - x0, 2), round(y1 - y0, 2),
                         round(p["poly"].area / 100.0, 2), round(per, 1),
                         holes, len(dow), " ".join(d["id"] for d in dow),
                         len(p.get("cut_sockets", [])),
                         len(p["engrave_next"]), len(p["engrave_box"])))
    return rows
