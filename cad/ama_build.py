#!/usr/bin/env python3
"""
AMA — Ahmedabad Management Association, ATIRA Campus, Ahmedabad
HCP Design, Planning & Management (Bimal Patel), 1999-2001

Generates the complete drawing set as a layered DXF (AC1032 / AutoCAD 2018).

    python3 cad/ama_build.py

Output: cad/AMA_Ahmedabad_HCP.dxf

This is a dimensional RECONSTRUCTION, not a measured survey — see the
provenance header in ama_params.py.
"""

import json
import os
import sys

from ezdxf.enums import TextEntityAlignment as TA

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ama_params as P
from ama_draft import (
    Sheet, new_document, grid_bubble, level_tag, north_point,
    drawing_title, section_mark,
    H_ROOM, H_SMALL, H_LEVEL, TXT_NOTE, TXT_TITLE,
)

# =============================================================================
# ENVELOPE SCHEDULE  —  one character per bay (13 bays), 'G' glazed, 'W' solid
# =============================================================================
ENVELOPE = {
    ("GF", "S"): "WGGGGGGGGGGGW",
    ("GF", "N"): "WGGGGGGGGGGGW",
    ("FF", "S"): "WWWWGGGGGGGGW",
    ("FF", "N"): "WWWWGGGGGGGGW",
}

def _entity_points(e):
    """Every defining point of an entity, for bounding-box work."""
    t = e.dxftype()
    if t == "LINE":
        return [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    if t == "LWPOLYLINE":
        return list(e.get_points("xy"))
    if t in ("CIRCLE", "ARC"):
        c, r = e.dxf.center, e.dxf.radius
        return [(c.x - r, c.y - r), (c.x + r, c.y + r)]
    if t == "TEXT":
        pts = [(e.dxf.insert.x, e.dxf.insert.y)]
        ap = e.dxf.align_point
        if ap is not None:
            pts.append((ap.x, ap.y))
        return pts
    if t == "HATCH":
        pts = []
        for path in e.paths:
            pts.extend((v[0], v[1]) for v in getattr(path, "vertices", []))
        return pts
    return []


SECT_AA_Y = P.Y_B          # 9000   longitudinal cut, on gridline B
SECT_BB_X = 51600          # through the foyer and ramp flight 3
SECT_CC_X = 18000          # through the auditorium seating


# =============================================================================
# GENERIC FABRIC HELPERS
# =============================================================================

def wall_h(sh, layer, y, x0, x1, t, openings=()):
    """Wall running in x, centred on y, drawn as cut poche with openings."""
    cuts = sorted((c - w / 2.0, c + w / 2.0) for c, w in openings)
    segs, pos = [], x0
    for a, b in cuts:
        if a > pos:
            segs.append((pos, a))
        pos = max(pos, b)
    if pos < x1:
        segs.append((pos, x1))
    for a, b in segs:
        if b - a <= 0:
            continue
        sh.rect(layer, a, y - t / 2.0, b, y + t / 2.0)
        sh.solid_rect("A-WALL-PATT", a, y - t / 2.0, b, y + t / 2.0)
    return segs


def wall_v(sh, layer, x, y0, y1, t, openings=()):
    """Wall running in y, centred on x, drawn as cut poche with openings."""
    cuts = sorted((c - w / 2.0, c + w / 2.0) for c, w in openings)
    segs, pos = [], y0
    for a, b in cuts:
        if a > pos:
            segs.append((pos, a))
        pos = max(pos, b)
    if pos < y1:
        segs.append((pos, y1))
    for a, b in segs:
        if b - a <= 0:
            continue
        sh.rect(layer, x - t / 2.0, a, x + t / 2.0, b)
        sh.solid_rect("A-WALL-PATT", x - t / 2.0, a, x + t / 2.0, b)
    return segs


def door_v(sh, x, yc, w, side=1):
    """Door leaf + swing in a wall running in y (opening already cut)."""
    hy = yc - w / 2.0
    sh.line("A-DOOR", x, hy, x + side * w, hy)
    a0, a1 = (0, 90) if side > 0 else (90, 180)
    sh.arc("A-DOOR", x, hy, w, a0, a1)


def door_h(sh, xc, y, w, side=1):
    """Door leaf + swing in a wall running in x (opening already cut)."""
    hx = xc - w / 2.0
    sh.line("A-DOOR", hx, y, hx, y + side * w)
    a0, a1 = (270, 360) if side > 0 else (0, 90)
    sh.arc("A-DOOR", hx, y, w, a0, a1)


def glazing_h(sh, y, x0, x1, mullion=1200):
    """Glazing line running in x, with mullions at regular centres."""
    sh.rect("A-GLAZ", x0, y - P.GLAZ_T / 2.0, x1, y + P.GLAZ_T / 2.0)
    n = max(1, int(round((x1 - x0) / float(mullion))))
    for i in range(1, n):
        mx = x0 + round(i * (x1 - x0) / float(n))
        sh.line("A-GLAZ", mx, y - P.GLAZ_T / 2.0 - 40, mx, y + P.GLAZ_T / 2.0 + 40)


def glazing_v(sh, x, y0, y1, mullion=1200):
    sh.rect("A-GLAZ", x - P.GLAZ_T / 2.0, y0, x + P.GLAZ_T / 2.0, y1)
    n = max(1, int(round((y1 - y0) / float(mullion))))
    for i in range(1, n):
        my = y0 + round(i * (y1 - y0) / float(n))
        sh.line("A-GLAZ", x - P.GLAZ_T / 2.0 - 40, my, x + P.GLAZ_T / 2.0 + 40, my)


def columns(sh, layer="S-COLS"):
    """All 56 RCC columns at grid intersections, cut and poched."""
    for x in P.X_GRID:
        for y in P.Y_GRID:
            x0, x1 = x - P.COL_X / 2.0, x + P.COL_X / 2.0
            y0, y1 = y - P.COL_Y / 2.0, y + P.COL_Y / 2.0
            sh.rect(layer, x0, y0, x1, y1)
            sh.solid_rect("S-COLS-PATT", x0, y0, x1, y1)


def plan_grid(sh, ext=6500):
    """Grid lines with bubbles on all four sides."""
    y0, y1 = P.SLAB_Y0 - ext, P.SLAB_Y1 + ext
    x0, x1 = P.SLAB_X0 - ext, P.SLAB_X1 + ext
    for x, lab in zip(P.X_GRID, P.X_LABELS):
        sh.line("A-GRID", x, y0, x, y1)
        grid_bubble(sh, x, y1 + 700, lab)
        grid_bubble(sh, x, y0 - 700, lab)
    for y, lab in zip(P.Y_GRID, P.Y_LABELS):
        sh.line("A-GRID", x0, y, x1, y)
        grid_bubble(sh, x0 - 700, y, lab)
        grid_bubble(sh, x1 + 700, y, lab)


def plan_dims(sh, ext=6500):
    """Grid chain dimensions plus overall, on both axes."""
    yb = P.SLAB_Y0 - ext - 3600
    sh.dim_chain_h(P.X_GRID, P.SLAB_Y0, yb)
    sh.dim_h(P.X_GRID[0], P.X_GRID[-1], P.SLAB_Y0, yb - 3200)
    sh.dim_h(P.SLAB_X0, P.SLAB_X1, P.SLAB_Y0, yb - 6400)
    xb = P.SLAB_X0 - ext - 3600
    sh.dim_chain_v(P.Y_GRID, P.SLAB_X0, xb)
    sh.dim_v(P.Y_GRID[0], P.Y_GRID[-1], P.SLAB_X0, xb - 3200)
    sh.dim_v(P.SLAB_Y0, P.SLAB_Y1, P.SLAB_X0, xb - 6400)


def envelope(sh, floor):
    """External walls and glazing on gridlines A (south) and D (north)."""
    for side, yline in (("S", P.Y_A), ("N", P.Y_D)):
        code = ENVELOPE[(floor, side)]
        for bay in range(1, P.N_BAYS_X + 1):
            xa = P.gx(bay) + P.COL_X / 2.0
            xb = P.gx(bay + 1) - P.COL_X / 2.0
            if code[bay - 1] == "W":
                wall_h(sh, "A-WALL-EXTR", yline, xa, xb, P.WALL_EXT)
            else:
                glazing_h(sh, yline, xa, xb)
    # end walls
    for x in (P.X_GRID[0], P.X_GRID[-1]):
        wall_v(sh, "A-WALL-EXTR", x, P.Y_A + P.COL_Y / 2.0,
               P.Y_D - P.COL_Y / 2.0, P.WALL_EXT)


def slab_outline(sh):
    sh.rect("A-SLAB-EDGE", P.SLAB_X0, P.SLAB_Y0, P.SLAB_X1, P.SLAB_Y1)


def net_area(g0, g1, y0, y1):
    """Exact net internal area in m^2 for a room between two gridlines."""
    w = (P.gx(g1) - P.gx(g0)) - P.WALL_INT
    d = (y1 - y0) - P.WALL_INT
    return w * d / 1.0e6


def room_label(sh, g0, g1, y0, y1, text, show_area=True):
    cx = (P.gx(g0) + P.gx(g1)) / 2.0
    cy = (y0 + y1) / 2.0
    body = text
    if show_area:
        body = text + "\n%.1f m2" % net_area(g0, g1, y0, y1)
    sh.mtext("A-ANNO-TEXT", body, cx, cy, H_ROOM)


def stair(sh, x0, y0, x1, y1, n=12, up_dir=1):
    """Straight-flight stair with going lines and an UP arrow."""
    sh.rect("A-FLOR-STRS", x0, y0, x1, y1)
    step = (y1 - y0) / float(n)
    for i in range(1, n):
        sh.line("A-FLOR-STRS", x0, y0 + i * step, x1, y0 + i * step)
    cx = (x0 + x1) / 2.0
    sh.line("A-FLOR-STRS", cx, y0 + step * 0.6, cx, y1 - step * 0.6)
    tip = y1 - step * 0.6 if up_dir > 0 else y0 + step * 0.6
    d = -step * 0.7 if up_dir > 0 else step * 0.7
    sh.line("A-FLOR-STRS", cx, tip, cx - 180, tip + d)
    sh.line("A-FLOR-STRS", cx, tip, cx + 180, tip + d)
    sh.text("A-ANNO-TEXT", "UP" if up_dir > 0 else "DN",
            cx + 450, (y0 + y1) / 2.0, H_SMALL, TA.MIDDLE_LEFT)


# =============================================================================
# THE PROCESSIONAL RAMP
# =============================================================================

def ramp_geometry():
    """Return (flights, landings) as explicit, exact geometry.

    flight  = (x0, x1, y_start, y_end, lvl_start, lvl_end)
    landing = (x0, x1, y0, y1, lvl)
    """
    w, x0 = P.RAMP_WIDTH, P.RAMP_X0
    L = P.RAMP_LEVELS                       # [900, 2025, 3150, 4275, 5400]
    fx = [(x0 + k * w, x0 + (k + 1) * w) for k in range(4)]
    flights = [
        (fx[0][0], fx[0][1], P.RAMP_Y1, P.RAMP_Y2, L[0], L[1]),   # F1  +y
        (fx[1][0], fx[1][1], P.RAMP_Y2, P.RAMP_Y1, L[1], L[2]),   # F2  -y
        (fx[2][0], fx[2][1], P.RAMP_Y1, P.RAMP_Y2, L[2], L[3]),   # F3  +y
        (fx[3][0], fx[3][1], P.RAMP_Y2, P.RAMP_Y1, L[3], L[4]),   # F4  -y
    ]
    # Flight 1 rises straight off the foyer floor, so there is no separate
    # landing at the foot; the last landing is the first-floor arrival gallery,
    # run out to the inner face of the grid-8 wall.
    ff_edge = P.gx(P.FOYER_G1) - P.WALL_EXT / 2.0
    landings = [
        (fx[0][0], fx[1][1], P.RAMP_Y2, P.RAMP_Y3, L[1]),         # turn 1 (north)
        (fx[1][0], fx[2][1], P.RAMP_Y0, P.RAMP_Y1, L[2]),         # turn 2 (south)
        (fx[2][0], fx[3][1], P.RAMP_Y2, P.RAMP_Y3, L[3]),         # turn 3 (north)
        (fx[3][1], ff_edge, P.RAMP_Y0, P.RAMP_Y1, L[4]),          # arrival at FF
    ]
    return flights, landings


def ramp_level_at(flight, y):
    """Exact level of a flight at ordinate y (linear, 1:12)."""
    _, _, ys, ye, ls, le = flight
    t = (y - ys) / float(ye - ys)
    return ls + t * (le - ls)


def draw_ramp(sh, upto_level=None):
    flights, landings = ramp_geometry()
    for (x0, x1, ys, ye, ls, le) in flights:
        if upto_level is not None and min(ls, le) >= upto_level:
            continue
        ya, yb = min(ys, ye), max(ys, ye)
        sh.rect("A-FLOR-RAMP", x0, ya, x1, yb)
        # gradient tick at every 1000 mm of rise (= 12 000 mm of run)
        n = int((yb - ya) // 4500)
        for i in range(1, n + 1):
            yy = ya + i * 4500
            sh.line("A-FLOR-RAMP", x0, yy, x1, yy)
        # direction arrow
        cx = (x0 + x1) / 2.0
        sh.line("A-FLOR-RAMP", cx, ys, cx, ye)
        d = 900 if ye > ys else -900
        sh.line("A-FLOR-RAMP", cx, ye, cx - 300, ye - d)
        sh.line("A-FLOR-RAMP", cx, ye, cx + 300, ye - d)
    for (x0, x1, y0, y1, lvl) in landings:
        if upto_level is not None and lvl > upto_level:
            continue
        sh.rect("A-FLOR-RAMP", x0, y0, x1, y1)
        level_tag(sh, (x0 + x1) / 2.0, (y0 + y1) / 2.0, lvl)
    sh.text("A-ANNO-TEXT", "PROCESSIONAL RAMP  1:12",
            P.RAMP_X0 + 4800, P.RAMP_Y1 + 7000, H_ROOM, TA.MIDDLE_CENTER, rot=90)


# =============================================================================
# THE AUDITORIUM
# =============================================================================

def auditorium_seat_rows():
    """Exact seat grid: returns list of rows, each a list of (x, y) centres."""
    net_y0 = P.Y_A + P.WALL_ACOU / 2.0
    net_y1 = P.Y_D - P.WALL_ACOU / 2.0
    block_w = (P.AUD_BLOCK_A + P.AUD_BLOCK_B) * P.AUD_SEAT_W + P.AUD_AISLE_CENTRE
    total_w = block_w + 2 * P.AUD_AISLE_SIDE
    margin = ((net_y1 - net_y0) - total_w) / 2.0
    ya = net_y0 + margin + P.AUD_AISLE_SIDE
    rows = []
    for r in range(P.AUD_ROWS):
        x = P.AUD_FIRST_ROW_X + r * P.AUD_ROW_SPACING
        seats, y = [], ya
        for i in range(P.AUD_BLOCK_A):
            seats.append((x, y + P.AUD_SEAT_W / 2.0))
            y += P.AUD_SEAT_W
        y += P.AUD_AISLE_CENTRE
        for i in range(P.AUD_BLOCK_B):
            seats.append((x, y + P.AUD_SEAT_W / 2.0))
            y += P.AUD_SEAT_W
        rows.append(seats)
    return rows


def draw_auditorium(sh):
    rows = auditorium_seat_rows()
    total = sum(len(r) for r in rows)
    assert total == 250, "seat count must be exactly 250, got %d" % total

    sw, sd = P.AUD_SEAT_W - 50, P.AUD_SEAT_DEPTH
    for row in rows:
        for (x, y) in row:
            sh.rect("A-FURN-SEAT", x - sd / 2.0, y - sw / 2.0,
                    x + sd / 2.0, y + sw / 2.0)

    # stage
    sx0, sx1 = P.AUD_STAGE_X0, P.AUD_STAGE_X0 + P.AUD_STAGE_D
    sy0 = P.Y_A + P.WALL_ACOU / 2.0
    sy1 = P.Y_D - P.WALL_ACOU / 2.0
    sh.rect("A-FLOR-LEVL", sx0, sy0, sx1, sy1)
    sh.mtext("A-ANNO-TEXT", "STAGE\n+%.3f" % (P.AUD_STAGE_LVL / 1000.0),
             (sx0 + sx1) / 2.0, (sy0 + sy1) / 2.0, H_ROOM)

    # rake: one line per row riser
    for r in range(P.AUD_ROWS):
        x = P.AUD_FIRST_ROW_X + r * P.AUD_ROW_SPACING - P.AUD_ROW_SPACING / 2.0
        sh.line("A-FLOR-LEVL", x, sy0, x, sy1)

    sh.text("A-ANNO-TEXT", "250 SEATS  (10 ROWS x 25)",
            (P.AUD_FIRST_ROW_X + 4000), sy0 + 900, H_SMALL, TA.MIDDLE_CENTER)


# =============================================================================
# DRAWING 1 — SITE PLAN
# =============================================================================

def draw_site(sh):
    """Site plan at 1:500. Annotation is scaled by K so that it plots at the
    same physical size as the 1:100 sheets."""
    import math
    K = 3.0
    HS, HSM = H_ROOM * K, H_SMALL * K

    x0, y0 = P.SITE_X0, P.SITE_Y0
    x1, y1 = x0 + P.SITE_W, y0 + P.SITE_H
    sh.rect("C-SITE-BDRY", x0, y0, x1, y1)
    sh.text("A-ANNO-TEXT", "SITE BOUNDARY   3.000 ACRES  (12 140.52 m2)",
            x0 + 2500, y1 - 4500, HS, TA.BOTTOM_LEFT)

    # --- building footprint --------------------------------------------------
    sh.rect("A-SLAB-EDGE", P.SLAB_X0, P.SLAB_Y0, P.SLAB_X1, P.SLAB_Y1)
    sh.pattern("C-SITE-PATT",
               [(P.SLAB_X0, P.SLAB_Y0), (P.SLAB_X1, P.SLAB_Y0),
                (P.SLAB_X1, P.SLAB_Y1), (P.SLAB_X0, P.SLAB_Y1)],
               name="ANSI31", scale=600)
    sh.mtext("A-ANNO-TEXT",
             "AHMEDABAD MANAGEMENT ASSOCIATION\n"
             "2 STOREYS    BUILT-UP 4 173.60 m2",
             (P.SLAB_X0 + P.SLAB_X1) / 2.0, (P.SLAB_Y0 + P.SLAB_Y1) / 2.0, HS)

    # --- the eight neem trees, and the promenade beneath them ---------------
    ty = P.TREE_ROW_Y
    sh.rect("C-SITE-PATH", P.SLAB_X0, ty - P.PROMENADE_W / 2.0,
            P.SLAB_X1, ty + P.PROMENADE_W / 2.0)
    for i in range(P.N_TREES):
        tx = P.TREE_X0 + i * P.TREE_SPACING
        sh.circle("L-PLNT-TREE", tx, ty, P.TREE_CANOPY_R)
        sh.circle("L-PLNT-TREE", tx, ty, P.TREE_TRUNK_R)
        for k in range(12):
            a = math.radians(k * 30 + 15)
            ca, sa = math.cos(a), math.sin(a)
            sh.line("L-PLNT-TREE",
                    tx + round(P.TREE_TRUNK_R * ca),
                    ty + round(P.TREE_TRUNK_R * sa),
                    tx + round(P.TREE_CANOPY_R * ca),
                    ty + round(P.TREE_CANOPY_R * sa))
    sh.text("A-ANNO-TEXT",
            "8 No. EXISTING NEEM TREES @ %d mm CENTRES  -  "
            "PEDESTRIAN PROMENADE BENEATH" % P.TREE_SPACING,
            P.TREE_X0 - P.TREE_CANOPY_R, ty + P.TREE_CANOPY_R + 3000,
            HS, TA.BOTTOM_LEFT)

    # --- entrance forecourt on the foyer axis -------------------------------
    fx = (P.gx(P.FOYER_G0) + P.gx(P.FOYER_G1)) / 2.0
    sh.rect("C-SITE-PATH", fx - 10800, P.SLAB_Y1,
            fx + 10800, ty - P.PROMENADE_W / 2.0)
    sh.text("A-ANNO-TEXT", "ENTRANCE FORECOURT", fx, P.SLAB_Y1 + 2200,
            HSM, TA.BOTTOM_CENTER)

    # --- approach road along the north edge ---------------------------------
    ry = ty + P.TREE_CANOPY_R + 9000
    sh.line("C-SITE-PATH", x0, ry, x1, ry)
    sh.line("C-SITE-PATH", x0, ry + 7000, x1, ry + 7000)
    sh.text("A-ANNO-TEXT", "APPROACH ROAD   /   ATIRA CAMPUS",
            x0 + 6000, ry + 2200, HS, TA.BOTTOM_LEFT)

    # --- parking court, kept inside the boundary ----------------------------
    px0, px1 = P.SLAB_X1 + 8000, x1 - 6000
    py0, py1 = P.SLAB_Y0, P.SLAB_Y0 + 27000
    sh.rect("C-SITE-PATH", px0, py0, px1, py1)
    n = int((py1 - py0) // 3000)
    for i in range(1, n):
        sh.line("C-SITE-PATH", px0, py0 + i * 3000, px1, py0 + i * 3000)
    sh.text("A-ANNO-TEXT", "PARKING COURT", (px0 + px1) / 2.0, py1 + 2200,
            HSM, TA.BOTTOM_CENTER)

    # --- lawn to the south --------------------------------------------------
    ly1 = P.SLAB_Y0 - 9000
    sh.text("A-ANNO-TEXT", "LAWN", (P.SLAB_X0 + P.SLAB_X1) / 2.0,
            ly1 - 14000, HS, TA.MIDDLE_CENTER)
    for i in range(12):
        gy = ly1 - 4000 - i * 4000
        if gy < y0 + 4000:                 # never run past the boundary
            break
        sh.line("C-SITE-PATH", P.SLAB_X0 + 4000, gy, P.SLAB_X1 - 4000, gy)

    sh.dim_h(x0, x1, y0, y0 - 9000, "AMA-500")
    sh.dim_v(y0, y1, x0, x0 - 9000, "AMA-500")
    sh.dim_h(P.SLAB_X0, P.SLAB_X1, P.SLAB_Y0, P.SLAB_Y0 - 5000, "AMA-500")
    north_point(sh, x1 - 14000, y1 - 14000, 5000)
    drawing_title(sh, x0, y0 - 22000, "SITE PLAN", "SCALE 1 : 500", k=K)


# =============================================================================
# DRAWING 2 — GROUND FLOOR PLAN
# =============================================================================

def draw_ground_floor(sh):
    slab_outline(sh)
    plan_grid(sh)
    envelope(sh, "GF")
    columns(sh)

    yr0, yr1 = P.Y_ROOM_0, P.Y_ROOM_1
    yg0, yg1 = P.Y_GALL_0, P.Y_GALL_1

    # --- partitions between rooms -------------------------------------------
    # A wall shared by a full-depth room and a partial one takes the full
    # height and is pierced at the gallery so the concourse runs through.
    gal_mid = (P.Y_C + P.Y_D) / 2.0
    walls = {}
    for (g0, g1, name) in P.GF_ROOMS:
        full = (g0, g1) in P.FULL_DEPTH_GF
        ytop = yg1 if full else yr1
        t = P.WALL_EXT if full else P.WALL_INT
        for g in (g0, g1):
            if g in (1, 14):
                continue
            if g not in walls or ytop > walls[g][1]:
                walls[g] = (t, ytop)
    for g, (t, ytop) in sorted(walls.items()):
        ops = [(gal_mid, 2400)] if ytop == yg1 else []
        wall_v(sh, "A-WALL-INTR", P.gx(g), P.Y_A + P.COL_Y / 2.0,
               ytop - P.COL_Y / 2.0, t, ops)

    # --- gallery wall on gridline C, with a door to every room --------------
    for (g0, g1, name) in P.GF_ROOMS:
        if (g0, g1) in P.FULL_DEPTH_GF:
            continue
        xa = P.gx(g0) + P.WALL_INT / 2.0
        xb = P.gx(g1) - P.WALL_INT / 2.0
        dc = (xa + xb) / 2.0
        dw = 1800 if "SEMINAR" in name or "DINING" in name else 1200
        wall_h(sh, "A-WALL-INTR", P.Y_C, xa, xb, P.WALL_INT, [(dc, dw)])
        door_h(sh, dc, P.Y_C, dw, side=-1)

    # --- room names and exact net areas -------------------------------------
    for (g0, g1, name) in P.GF_ROOMS:
        if (g0, g1) in P.FULL_DEPTH_GF:
            # label the open western half of the foyer, clear of the ramp
            cx = (P.gx(g0) + P.WALL_EXT / 2.0 + P.RAMP_X0) / 2.0
            sh.mtext("A-ANNO-TEXT",
                     name + "\n%.1f m2" % net_area(g0, g1, P.Y_A, yg1),
                     cx, (P.Y_A + yg1) / 2.0, H_ROOM)
        else:
            room_label(sh, g0, g1, yr0, yr1, name, show_area=True)

    # main entrance, cut through the north glazing on the foyer axis
    ex = (P.gx(P.FOYER_G0) + P.gx(P.FOYER_G1)) / 2.0
    sh.rect("A-DOOR", ex - 1800, P.Y_D - 100, ex + 1800, P.Y_D + 100)
    door_v(sh, ex - 1800, P.Y_D + 1800, 1800, side=-1)
    door_v(sh, ex + 1800, P.Y_D + 1800, 1800, side=1)

    sh.text("A-ANNO-TEXT", "ENTRANCE CONCOURSE / GALLERY",
            P.gx(3), (yg0 + yg1) / 2.0, H_ROOM, TA.MIDDLE_CENTER)
    sh.text("A-ANNO-TEXT", "ENTRANCE CONCOURSE / GALLERY",
            (P.gx(11) + P.gx(12)) / 2.0, (yg0 + yg1) / 2.0, H_ROOM,
            TA.MIDDLE_CENTER)

    # --- cores ---------------------------------------------------------------
    stair(sh, 1400, 2600, 4000, 9200, 12, up_dir=1)
    sh.rect("A-FLOR-STRS", 4600, 2600, 7000, 5600)
    sh.line("A-FLOR-STRS", 4600, 2600, 7000, 5600)
    sh.line("A-FLOR-STRS", 7000, 2600, 4600, 5600)
    sh.text("A-ANNO-TEXT", "LIFT", 5800, 4100, H_SMALL, TA.MIDDLE_CENTER)

    stair(sh, P.gx(13) + 1400, 2600, P.gx(13) + 4000, 9200, 12, up_dir=1)

    # --- the processional ramp ----------------------------------------------
    draw_ramp(sh)

    # --- entrance steps and plinth edge -------------------------------------
    fx = (P.gx(P.FOYER_G0) + P.gx(P.FOYER_G1)) / 2.0
    for i in range(3):
        sh.line("A-FLOR-LEVL", fx - 9000, P.SLAB_Y1 + 300 * (i + 1),
                fx + 9000, P.SLAB_Y1 + 300 * (i + 1))
    level_tag(sh, fx, P.SLAB_Y1 + 1800, P.LVL_SITE)
    level_tag(sh, P.gx(3), 12000, P.LVL_GF)
    level_tag(sh, P.gx(11), 12000, P.LVL_GF)

    # --- section marks -------------------------------------------------------
    section_mark(sh, P.SLAB_X0 - 5000, SECT_AA_Y, P.SLAB_X1 + 5000, SECT_AA_Y,
                 "A")
    section_mark(sh, SECT_BB_X, P.SLAB_Y0 - 5000, SECT_BB_X, P.SLAB_Y1 + 5000,
                 "B")
    section_mark(sh, SECT_CC_X, P.SLAB_Y0 - 5000, SECT_CC_X, P.SLAB_Y1 + 5000,
                 "C", flip=True)

    plan_dims(sh)
    north_point(sh, P.SLAB_X1 + 12000, P.SLAB_Y1 - 2000)
    drawing_title(sh, P.SLAB_X0, P.SLAB_Y0 - 22000,
                  "GROUND FLOOR PLAN", "SCALE 1 : 100    LEVEL +0.900")


# =============================================================================
# DRAWING 3 — FIRST FLOOR PLAN
# =============================================================================

def draw_first_floor(sh):
    slab_outline(sh)
    plan_grid(sh)
    envelope(sh, "FF")
    columns(sh)

    yr0, yr1 = P.Y_ROOM_0, P.Y_ROOM_1
    yg1 = P.Y_GALL_1

    # --- partitions, with an explicit door schedule -------------------------
    gal_mid = (P.Y_C + P.Y_D) / 2.0
    FF_OPENINGS = {
        2:  [(17400, 1200)],                      # core 1 -> auditorium
        5:  [(5400, 1800), (17400, 1800)],        # auditorium -> its foyer
        6:  [(gal_mid, 3600)],                    # aud. foyer -> main foyer
        9:  [(gal_mid, 2400)],                    # main foyer -> library
        11: [(P.Y_B, 3600)],                      # library -> exhibition
        13: [(17400, 1200)],                      # exhibition -> core 2
    }
    walls = {}
    for (g0, g1, name) in P.FF_ROOMS:
        full = (g0, g1) in P.FULL_DEPTH_FF
        ytop = yg1 if full else yr1
        t = P.WALL_ACOU if name.startswith("AUDITORIUM\n") else (
            P.WALL_EXT if full else P.WALL_INT)
        for g in (g0, g1):
            if g in (1, 14):
                continue
            if g not in walls or ytop > walls[g][1] or t > walls[g][0]:
                walls[g] = (max(t, walls.get(g, (0, 0))[0]),
                            max(ytop, walls.get(g, (0, 0))[1]))
    for g, (t, ytop) in sorted(walls.items()):
        ops = FF_OPENINGS.get(g, [])
        wall_v(sh, "A-WALL-INTR", P.gx(g), P.Y_A + P.COL_Y / 2.0,
               ytop - P.COL_Y / 2.0, t, ops)
        for (yc, w) in ops:
            if w <= 1800:
                door_v(sh, P.gx(g), yc, w, side=1)

    # gallery wall at the two cores only
    for (g0, g1, name) in P.FF_ROOMS:
        if (g0, g1) in P.FULL_DEPTH_FF:
            continue
        xa = P.gx(g0) + P.WALL_INT / 2.0
        xb = P.gx(g1) - P.WALL_INT / 2.0
        dc = (xa + xb) / 2.0
        wall_h(sh, "A-WALL-INTR", P.Y_C, xa, xb, P.WALL_INT, [(dc, 1200)])
        door_h(sh, dc, P.Y_C, 1200, side=-1)

    for (g0, g1, name) in P.FF_ROOMS:
        ytop = yg1 if (g0, g1) in P.FULL_DEPTH_FF else yr1
        y_bot = P.Y_A if (g0, g1) in P.FULL_DEPTH_FF else yr0
        if name.startswith("AUDITORIUM\n"):
            sh.mtext("A-ANNO-TEXT",
                     "AUDITORIUM\n250 SEATS\n%.1f m2"
                     % net_area(g0, g1, P.Y_A, ytop),
                     (P.gx(g0) + P.gx(g1)) / 2.0, ytop - 2600, H_ROOM)
        elif name.startswith("FOYER VOID"):
            room_label(sh, g0, g1, y_bot, ytop, name, show_area=False)
        else:
            room_label(sh, g0, g1, y_bot, ytop, name, show_area=True)

    # --- auditorium ----------------------------------------------------------
    draw_auditorium(sh)

    # --- foyer void, ramp arrival and bridge --------------------------------
    vx0, vx1 = (P.gx(P.FOYER_G0) + P.WALL_EXT / 2.0,
                P.gx(P.FOYER_G1) - P.WALL_EXT / 2.0)
    vy0, vy1 = P.Y_A + P.WALL_EXT / 2.0, P.Y_D - P.WALL_EXT / 2.0
    # the void is only the open western half; the ramp and its landings are
    # real first-floor surface and must not be crossed by the void symbol
    vx1_open = P.RAMP_X0
    sh.rect("A-FLOR-OTLN", vx0, vy0, vx1, vy1)
    sh.line("A-FLOR-OTLN", vx0, vy0, vx1_open, vy1)
    sh.line("A-FLOR-OTLN", vx0, vy1, vx1_open, vy0)
    draw_ramp(sh)
    level_tag(sh, P.gx(9), 12000, P.LVL_FF)
    level_tag(sh, P.gx(12), 12000, P.LVL_FF)

    # --- library layout ------------------------------------------------------
    for i in range(9):
        bx = P.gx(9) + 1600 + i * 1400
        sh.rect("A-FURN", bx, 3200, bx + 600, 11600)
    sh.text("A-ANNO-TEXT", "STACKS", P.gx(10), 12600, H_SMALL,
            TA.MIDDLE_CENTER)
    for i in range(6):
        rx = P.gx(9) + 1800 + i * 1900
        sh.rect("A-FURN", rx, 14400, rx + 1800, 15600)
    sh.text("A-ANNO-TEXT", "READING", P.gx(10), 16800, H_SMALL,
            TA.MIDDLE_CENTER)

    # --- exhibition panels ---------------------------------------------------
    for i in range(7):
        px = P.gx(11) + 1800 + i * 1800
        sh.line("A-FURN", px, 5400, px, 9000)
        sh.line("A-FURN", px, 12000, px, 15600)

    # --- cores ---------------------------------------------------------------
    stair(sh, 1400, 2600, 4000, 9200, 12, up_dir=-1)
    sh.rect("A-FLOR-STRS", 4600, 2600, 7000, 5600)
    sh.line("A-FLOR-STRS", 4600, 2600, 7000, 5600)
    sh.line("A-FLOR-STRS", 7000, 2600, 4600, 5600)
    stair(sh, P.gx(13) + 1400, 2600, P.gx(13) + 4000, 9200, 12, up_dir=-1)

    plan_dims(sh)
    north_point(sh, P.SLAB_X1 + 12000, P.SLAB_Y1 - 2000)
    drawing_title(sh, P.SLAB_X0, P.SLAB_Y0 - 22000,
                  "FIRST FLOOR PLAN", "SCALE 1 : 100    LEVEL +5.400")


# =============================================================================
# DRAWING 4 — ROOF PLAN
# =============================================================================

def draw_roof(sh):
    slab_outline(sh)
    plan_grid(sh)

    # parapet
    t = P.PARAPET_T
    sh.rect("A-ROOF", P.SLAB_X0 + t, P.SLAB_Y0 + t, P.SLAB_X1 - t,
            P.SLAB_Y1 - t)

    # raised auditorium volume
    ax0, ax1 = P.gx(2) - P.COL_X / 2.0, P.gx(5) + P.COL_X / 2.0
    sh.rect("A-ROOF", ax0, P.SLAB_Y0, ax1, P.SLAB_Y1)
    sh.rect("A-ROOF", ax0 + t, P.SLAB_Y0 + t, ax1 - t, P.SLAB_Y1 - t)
    sh.mtext("A-ANNO-TEXT",
             "AUDITORIUM ROOF\n+%.3f" % (P.LVL_AUD_ROOF / 1000.0),
             (ax0 + ax1) / 2.0, (P.SLAB_Y0 + P.SLAB_Y1) / 2.0, H_ROOM)

    # expressed beam grid over the rest of the roof
    for x in P.X_GRID:
        if ax0 <= x <= ax1:
            continue
        sh.line("S-BEAM", x, P.SLAB_Y0, x, P.SLAB_Y1)
    for y in P.Y_GRID:
        sh.line("S-BEAM", ax1, y, P.SLAB_X1, y)
        sh.line("S-BEAM", P.SLAB_X0, y, ax0, y)

    # falls and rainwater outlets
    for x in P.X_GRID[5:]:
        sh.line("A-ROOF", x, P.Y_B, x, P.Y_C)
    for i, x in enumerate(P.X_GRID):
        if ax0 <= x <= ax1:
            continue
        for y in (P.SLAB_Y0 + 900, P.SLAB_Y1 - 900):
            sh.circle("A-ROOF", x, y, 180)
    sh.text("A-ANNO-TEXT",
            "RCC ROOF SLAB WITH 1:100 FALLS TO PERIMETER RAINWATER OUTLETS",
            P.gx(10), (P.Y_B + P.Y_C) / 2.0, H_ROOM, TA.MIDDLE_CENTER)
    level_tag(sh, P.gx(10), P.Y_B - 2000, P.LVL_ROOF)

    plan_dims(sh)
    north_point(sh, P.SLAB_X1 + 12000, P.SLAB_Y1 - 2000)
    drawing_title(sh, P.SLAB_X0, P.SLAB_Y0 - 22000, "ROOF PLAN",
                  "SCALE 1 : 200")


# =============================================================================
# SECTION HELPERS
# =============================================================================

def ground_and_foundation(sh, x0, x1):
    sh.line("A-SECT-GRND", x0 - 4000, P.LVL_SITE, x1 + 4000, P.LVL_SITE)
    sh.pattern("A-SECT-PATT",
               [(x0 - 4000, P.LVL_SITE), (x1 + 4000, P.LVL_SITE),
                (x1 + 4000, -P.FOUND_D - 1200), (x0 - 4000, -P.FOUND_D - 1200)],
               name="ANSI31", scale=120, angle=45)


def slab_band(sh, x0, x1, top, with_beam=True, layer="A-SECT-CUT"):
    """Slab (and the beam running along the cut) drawn as cut concrete."""
    sh.rect(layer, x0, top - P.SLAB_T, x1, top)
    sh.solid_rect("A-SECT-PATT", x0, top - P.SLAB_T, x1, top)
    if with_beam:
        b0 = top - P.SLAB_T - P.BEAM_D
        sh.rect(layer, x0, b0, x1, top - P.SLAB_T)
        sh.solid_rect("A-SECT-PATT", x0, b0, x1, top - P.SLAB_T)


def level_line(sh, x0, x1, lvl, label=True):
    sh.line("A-FLOR-LEVL", x0, lvl, x1, lvl)
    if label:
        level_tag(sh, x1 + 1200, lvl, lvl)


def vertical_dims(sh, x, levels, base_x):
    sh.dim_chain_v(levels, x, base_x)
    sh.dim_v(levels[0], levels[-1], x, base_x - 3200)


# =============================================================================
# DRAWING 5 — SECTION A-A  (longitudinal, on gridline B, looking north)
# =============================================================================

def draw_section_aa(sh):
    x0, x1 = P.SLAB_X0, P.SLAB_X1
    ground_and_foundation(sh, x0, x1)

    # plinth
    sh.rect("A-SECT-CUT", x0, P.LVL_SITE, x1, P.LVL_GF)
    sh.pattern("A-SECT-PATT",
               [(x0, P.LVL_SITE), (x1, P.LVL_SITE),
                (x1, P.LVL_GF), (x0, P.LVL_GF)], name="ANSI31", scale=90)

    # columns cut on gridline B
    for x in P.X_GRID:
        top = P.LVL_AUD_ROOF if P.gx(2) <= x <= P.gx(5) else P.LVL_ROOF
        sh.rect("S-COLS", x - P.COL_X / 2.0, -P.FOUND_D, x + P.COL_X / 2.0, top)
        sh.solid_rect("S-COLS-PATT", x - P.COL_X / 2.0, -P.FOUND_D,
                      x + P.COL_X / 2.0, top)
        sh.rect("A-SECT-CUT", x - 900, -P.FOUND_D - 400, x + 900, -P.FOUND_D)

    # First-floor slab. It stops at the foyer: the three-bay volume is open
    # from +0.900 to the roof, and the only first-floor surfaces within it are
    # the ramp flights and landings, drawn separately below.
    fx0 = P.gx(P.FOYER_G0)
    ramp_east = P.RAMP_X0 + P.RAMP_FLIGHTS * P.RAMP_WIDTH      # 55200
    slab_band(sh, x0, fx0, P.LVL_FF)
    slab_band(sh, ramp_east, x1, P.LVL_FF)

    # roof slabs, with the auditorium volume raised
    slab_band(sh, x0, P.gx(2), P.LVL_ROOF)
    slab_band(sh, P.gx(2), P.gx(5), P.LVL_AUD_ROOF)
    slab_band(sh, P.gx(5), x1, P.LVL_ROOF)

    # parapets, including the upstands where the auditorium volume steps up
    for (px, d, base, top) in (
            (x0, P.PARAPET_T, P.LVL_ROOF, P.LVL_PARAPET),
            (x1, -P.PARAPET_T, P.LVL_ROOF, P.LVL_PARAPET),
            (P.gx(2), P.PARAPET_T, P.LVL_ROOF, P.LVL_AUD_PARA),
            (P.gx(5), -P.PARAPET_T, P.LVL_ROOF, P.LVL_AUD_PARA)):
        sh.rect("A-SECT-CUT", px, base, px + d, top)
        sh.solid_rect("A-SECT-PATT", px, base, px + d, top)

    # double-height foyer void
    sh.mtext("A-ANNO-TEXT", "DOUBLE HEIGHT\nENTRANCE FOYER",
             (fx0 + P.RAMP_X0) / 2.0, P.LVL_GF + 6400, H_ROOM)
    sh.line("A-FLOR-OTLN", fx0, P.LVL_GF, fx0,
            P.LVL_ROOF - P.SLAB_T - P.BEAM_D)
    sh.line("A-FLOR-OTLN", ramp_east, P.LVL_GF, ramp_east,
            P.LVL_ROOF - P.SLAB_T - P.BEAM_D)

    # the four ramp flights, cut on gridline B at their exact local level
    flights, _ = ramp_geometry()
    for i, fl in enumerate(flights):
        lvl = ramp_level_at(fl, SECT_AA_Y)
        assert float(lvl).is_integer(), "ramp cut level must be integral"
        fx_a, fx_b = fl[0], fl[1]
        sh.rect("A-FLOR-RAMP", fx_a, lvl - 200, fx_b, lvl)
        sh.solid_rect("A-SECT-PATT", fx_a, lvl - 200, fx_b, lvl)
        sh.text("A-ANNO-SYMB", "R%d +%.3f" % (i + 1, lvl / 1000.0),
                (fx_a + fx_b) / 2.0, lvl + 420, H_LEVEL, TA.MIDDLE_CENTER)

    # auditorium: raked floor and seats seen beyond
    rake_x = P.AUD_FIRST_ROW_X
    sh.line("A-SECT-CUT", P.gx(2), P.LVL_FF, rake_x, P.LVL_FF)
    for r in range(P.AUD_ROWS):
        xa = rake_x + r * P.AUD_ROW_SPACING
        lv = P.LVL_FF + r * P.AUD_RAKE_PER_ROW
        sh.line("A-SECT-CUT", xa, lv, xa + P.AUD_ROW_SPACING, lv)
        sh.line("A-SECT-CUT", xa + P.AUD_ROW_SPACING, lv,
                xa + P.AUD_ROW_SPACING, lv + P.AUD_RAKE_PER_ROW)
        sh.rect("A-SECT-BYND", xa + 120, lv, xa + 620, lv + 450)
        sh.line("A-SECT-BYND", xa + 620, lv + 450, xa + 620, lv + 1000)
    sh.rect("A-SECT-BYND", P.AUD_STAGE_X0, P.LVL_FF,
            P.AUD_STAGE_X0 + P.AUD_STAGE_D, P.AUD_STAGE_LVL)
    sh.text("A-ANNO-TEXT", "AUDITORIUM  250 SEATS",
            (P.gx(2) + P.gx(5)) / 2.0, P.LVL_FF + 4200, H_ROOM,
            TA.MIDDLE_CENTER)
    sh.text("A-ANNO-TEXT", "STAGE +%.3f" % (P.AUD_STAGE_LVL / 1000.0),
            P.AUD_STAGE_X0 + P.AUD_STAGE_D / 2.0, P.LVL_FF + 1500,
            H_SMALL, TA.MIDDLE_CENTER)

    # room names below and above
    labels_gf = [(1, 2, "CORE 1"), (2, 4, "SEMINAR HALL 1"), (4, 5, "CLASSRM 1"),
                 (5, 6, "CLASSRM 2"), (9, 10, "BOOK SHOP"), (10, 11, "BOARD RM"),
                 (11, 13, "SEMINAR HALL 2"), (13, 14, "CORE 2")]
    for (a, b, nm) in labels_gf:
        sh.text("A-ANNO-TEXT", nm, (P.gx(a) + P.gx(b)) / 2.0,
                P.LVL_GF + 1800, H_SMALL, TA.MIDDLE_CENTER)
    labels_ff = [(5, 6, "AUD. FOYER"), (9, 11, "LIBRARY"),
                 (11, 13, "EXHIBITION SPACE"), (13, 14, "CORE 2")]
    for (a, b, nm) in labels_ff:
        sh.text("A-ANNO-TEXT", nm, (P.gx(a) + P.gx(b)) / 2.0,
                P.LVL_FF + 1800, H_SMALL, TA.MIDDLE_CENTER)

    # grid, levels, dimensions
    for x, lab in zip(P.X_GRID, P.X_LABELS):
        sh.line("A-GRID", x, -P.FOUND_D - 3000, x, P.LVL_AUD_PARA + 3000)
        grid_bubble(sh, x, P.LVL_AUD_PARA + 3700, lab)
    for lvl in (P.LVL_SITE, P.LVL_GF, P.LVL_FF, P.LVL_ROOF, P.LVL_PARAPET,
                P.LVL_AUD_ROOF, P.LVL_AUD_PARA):
        level_tag(sh, x1 + 2200, lvl, lvl)
        sh.line("A-FLOR-LEVL", x1, lvl, x1 + 2100, lvl)
    vertical_dims(sh, x0, [P.LVL_SITE, P.LVL_GF, P.LVL_FF, P.LVL_ROOF,
                           P.LVL_PARAPET], x0 - 4200)
    sh.dim_chain_h(P.X_GRID, -P.FOUND_D, -P.FOUND_D - 4200)
    drawing_title(sh, x0, -P.FOUND_D - 10500, "SECTION A-A",
                  "SCALE 1 : 100    LONGITUDINAL, ON GRIDLINE B")


# =============================================================================
# DRAWING 6 — SECTION B-B  (transverse through the foyer and ramp)
# =============================================================================

def draw_section_bb(sh):
    y0, y1 = P.SLAB_Y0, P.SLAB_Y1
    ground_and_foundation(sh, y0, y1)
    sh.rect("A-SECT-CUT", y0, P.LVL_SITE, y1, P.LVL_GF)
    sh.pattern("A-SECT-PATT", [(y0, P.LVL_SITE), (y1, P.LVL_SITE),
                               (y1, P.LVL_GF), (y0, P.LVL_GF)],
               name="ANSI31", scale=90)

    for y in P.Y_GRID:
        sh.rect("S-COLS", y - P.COL_Y / 2.0, -P.FOUND_D, y + P.COL_Y / 2.0,
                P.LVL_ROOF)
        sh.solid_rect("S-COLS-PATT", y - P.COL_Y / 2.0, -P.FOUND_D,
                      y + P.COL_Y / 2.0, P.LVL_ROOF)
        sh.rect("A-SECT-CUT", y - 1100, -P.FOUND_D - 400, y + 1100, -P.FOUND_D)

    # roof over, cantilevering 1800 each side
    slab_band(sh, y0, y1, P.LVL_ROOF)
    for (py, d) in ((y0, P.PARAPET_T), (y1, -P.PARAPET_T)):
        sh.rect("A-SECT-CUT", py, P.LVL_ROOF, py + d, P.LVL_PARAPET)
        sh.solid_rect("A-SECT-PATT", py, P.LVL_ROOF, py + d, P.LVL_PARAPET)

    # the foyer is double height: no first-floor slab in this bay
    sh.text("A-ANNO-TEXT", "DOUBLE HEIGHT ENTRANCE FOYER",
            (y0 + y1) / 2.0, P.LVL_GF + 7600, H_ROOM, TA.MIDDLE_CENTER)

    # ramp flight 3 cut in true slope, with its landings
    flights, landings = ramp_geometry()
    f3 = flights[2]
    _, _, ys, ye, ls, le = f3
    sh.pline("A-FLOR-RAMP",
             [(ys, ls), (ye, le), (ye, le - 250), (ys, ls - 250)], close=True)
    sh.solid("A-SECT-PATT",
             [(ys, ls), (ye, le), (ye, le - 250), (ys, ls - 250)])
    sh.text("A-ANNO-TEXT", "RAMP 1:12", (ys + ye) / 2.0,
            (ls + le) / 2.0 + 700, H_SMALL, TA.MIDDLE_CENTER, rot=4)
    for (lx0, lx1, ly0, ly1, lvl) in landings:
        if not (lx0 <= SECT_BB_X <= lx1):
            continue
        sh.rect("A-FLOR-RAMP", ly0, lvl - 250, ly1, lvl)
        sh.solid_rect("A-SECT-PATT", ly0, lvl - 250, ly1, lvl)
        level_tag(sh, (ly0 + ly1) / 2.0, lvl, lvl)

    # balustrade to the ramp
    sh.line("A-FLOR-RAMP", ys, ls + 1000, ye, le + 1000)

    # envelope glazing, full height both faces
    for yline in (P.Y_A, P.Y_D):
        sh.line("A-GLAZ", yline, P.LVL_GF, yline, P.LVL_ROOF - P.SLAB_T - P.BEAM_D)
        for lv in range(int(P.LVL_GF) + 1200, int(P.LVL_ROOF) - 800, 1200):
            sh.line("A-GLAZ", yline - 150, lv, yline + 150, lv)

    # south brise-soleil fins seen in section
    lv = P.LVL_GF + 1200
    while lv < P.LVL_ROOF - 900:
        sh.rect("A-LOUV", y0, lv, P.Y_A - P.COL_Y / 2.0, lv + P.LOUVRE_T)
        lv += P.LOUVRE_PITCH
    sh.text("A-ANNO-TEXT", "CONCRETE BRISE-SOLEIL", y0 - 500,
            P.LVL_GF + 5000, H_SMALL, TA.MIDDLE_RIGHT, rot=90)

    for y, lab in zip(P.Y_GRID, P.Y_LABELS):
        sh.line("A-GRID", y, -P.FOUND_D - 3000, y, P.LVL_PARAPET + 3000)
        grid_bubble(sh, y, P.LVL_PARAPET + 3700, lab)
    for lvl in (P.LVL_SITE, P.LVL_GF, P.LVL_FF, P.LVL_ROOF, P.LVL_PARAPET):
        sh.line("A-FLOR-LEVL", y1, lvl, y1 + 2100, lvl)
        level_tag(sh, y1 + 2200, lvl, lvl)
    vertical_dims(sh, y0, [P.LVL_SITE, P.LVL_GF, P.LVL_FF, P.LVL_ROOF,
                           P.LVL_PARAPET], y0 - 4200)
    sh.dim_chain_h(P.Y_GRID, -P.FOUND_D, -P.FOUND_D - 4200)
    sh.dim_h(y0, y1, -P.FOUND_D, -P.FOUND_D - 7400)
    drawing_title(sh, y0, -P.FOUND_D - 13500, "SECTION B-B",
                  "SCALE 1 : 100    THROUGH FOYER AND RAMP")


# =============================================================================
# DRAWING 7 — SECTION C-C  (transverse through the auditorium)
# =============================================================================

def draw_section_cc(sh):
    y0, y1 = P.SLAB_Y0, P.SLAB_Y1
    ground_and_foundation(sh, y0, y1)
    sh.rect("A-SECT-CUT", y0, P.LVL_SITE, y1, P.LVL_GF)
    sh.pattern("A-SECT-PATT", [(y0, P.LVL_SITE), (y1, P.LVL_SITE),
                               (y1, P.LVL_GF), (y0, P.LVL_GF)],
               name="ANSI31", scale=90)

    for y in P.Y_GRID:
        sh.rect("S-COLS", y - P.COL_Y / 2.0, -P.FOUND_D, y + P.COL_Y / 2.0,
                P.LVL_AUD_ROOF)
        sh.solid_rect("S-COLS-PATT", y - P.COL_Y / 2.0, -P.FOUND_D,
                      y + P.COL_Y / 2.0, P.LVL_AUD_ROOF)
        sh.rect("A-SECT-CUT", y - 1100, -P.FOUND_D - 400, y + 1100, -P.FOUND_D)

    slab_band(sh, y0, y1, P.LVL_FF)
    slab_band(sh, y0, y1, P.LVL_AUD_ROOF)
    for (py, d) in ((y0, P.PARAPET_T), (y1, -P.PARAPET_T)):
        sh.rect("A-SECT-CUT", py, P.LVL_AUD_ROOF, py + d, P.LVL_AUD_PARA)
        sh.solid_rect("A-SECT-PATT", py, P.LVL_AUD_ROOF, py + d, P.LVL_AUD_PARA)

    # raked auditorium floor at this cut, and the seats across the hall
    row_index = int((SECT_CC_X - P.AUD_FIRST_ROW_X) // P.AUD_ROW_SPACING)
    lvl = P.LVL_FF + max(0, row_index) * P.AUD_RAKE_PER_ROW
    sh.line("A-SECT-CUT", P.Y_A, lvl, P.Y_D, lvl)
    rows = auditorium_seat_rows()
    for (_, sy) in rows[max(0, row_index)]:
        sh.rect("A-SECT-BYND", sy - 250, lvl, sy + 250, lvl + 450)
        sh.line("A-SECT-BYND", sy - 250, lvl + 450, sy - 250, lvl + 1000)
    sh.text("A-ANNO-TEXT", "AUDITORIUM  —  ROW %d AT +%.3f"
            % (row_index + 1, lvl / 1000.0),
            (y0 + y1) / 2.0, P.LVL_FF + 4400, H_ROOM, TA.MIDDLE_CENTER)
    sh.text("A-ANNO-TEXT", "SEMINAR HALL 1", (y0 + y1) / 2.0,
            P.LVL_GF + 2000, H_ROOM, TA.MIDDLE_CENTER)

    for yline in (P.Y_A, P.Y_D):
        sh.line("A-GLAZ", yline, P.LVL_GF, yline, P.LVL_FF - P.SLAB_T - P.BEAM_D)

    for y, lab in zip(P.Y_GRID, P.Y_LABELS):
        sh.line("A-GRID", y, -P.FOUND_D - 3000, y, P.LVL_AUD_PARA + 3000)
        grid_bubble(sh, y, P.LVL_AUD_PARA + 3700, lab)
    for lv in (P.LVL_SITE, P.LVL_GF, P.LVL_FF, P.LVL_AUD_ROOF, P.LVL_AUD_PARA):
        sh.line("A-FLOR-LEVL", y1, lv, y1 + 2100, lv)
        level_tag(sh, y1 + 2200, lv, lv)
    vertical_dims(sh, y0, [P.LVL_SITE, P.LVL_GF, P.LVL_FF, P.LVL_AUD_ROOF,
                           P.LVL_AUD_PARA], y0 - 4200)
    sh.dim_chain_h(P.Y_GRID, -P.FOUND_D, -P.FOUND_D - 4200)
    drawing_title(sh, y0, -P.FOUND_D - 10500, "SECTION C-C",
                  "SCALE 1 : 100    THROUGH AUDITORIUM")


# =============================================================================
# DRAWINGS 8-11 — ELEVATIONS
# =============================================================================

def _elev_blocks(grid_xs):
    """Vertical massing blocks as (start, end, roof level, parapet level).
    The auditorium bay rises above the main roof."""
    if grid_xs is P.X_GRID:
        return [(P.SLAB_X0, P.gx(2), P.LVL_ROOF, P.LVL_PARAPET),
                (P.gx(2), P.gx(5), P.LVL_AUD_ROOF, P.LVL_AUD_PARA),
                (P.gx(5), P.SLAB_X1, P.LVL_ROOF, P.LVL_PARAPET)]
    return [(P.SLAB_Y0, P.SLAB_Y1, P.LVL_ROOF, P.LVL_PARAPET)]


def _elev_glazing(sh, grid_xs, code, lo, hi):
    """Glazed infill with mullions, in the bays the envelope schedule glazes."""
    for bay in range(1, len(grid_xs)):
        if code[bay - 1] != "G":
            continue
        a = grid_xs[bay - 1] + P.COL_X / 2.0
        b = grid_xs[bay] - P.COL_X / 2.0
        sh.rect("A-GLAZ", a, lo, b, hi)
        n = max(1, int(round((b - a) / 1800.0)))
        for i in range(1, n):
            mx = a + round(i * (b - a) / float(n))
            sh.line("A-GLAZ", mx, lo, mx, hi)
        sh.line("A-ELEV-FINE", a, lo, b, lo)      # sill / shadow line


def _elev_louvres(sh, grid_xs, code, lo, hi):
    """Brise-soleil fins, across the glazed bays only, so that the concrete
    frame still reads through the shading."""
    for bay in range(1, len(grid_xs)):
        if code[bay - 1] != "G":
            continue
        a = grid_xs[bay - 1] + P.COL_X / 2.0
        b = grid_xs[bay] - P.COL_X / 2.0
        lv = lo + P.LOUVRE_PITCH
        while lv <= hi - P.LOUVRE_PITCH / 2.0:
            sh.rect("A-LOUV", a, lv, b, lv + P.LOUVRE_T)
            lv += P.LOUVRE_PITCH


def _elev_frame(sh, grid_xs, blocks):
    """The expressed cast in-situ frame, drawn over the infill: plinth,
    spandrel bands at each floor, parapet, and every column."""
    for (a, b, roof, para) in blocks:
        sh.rect("A-ELEV", a, P.LVL_SITE, b, P.LVL_GF)                  # plinth
        sh.rect("A-ELEV", a, P.LVL_FF - P.SLAB_T - P.BEAM_D, b, P.LVL_FF)
        sh.rect("A-ELEV", a, roof - P.SLAB_T - P.BEAM_D, b, roof)
        sh.rect("A-ROOF", a, roof, b, para)                            # parapet
        sh.line("A-ELEV", a, para, b, para)
    for x in grid_xs:
        top = P.LVL_PARAPET
        for (a, b, roof, para) in blocks:
            if a <= x <= b:
                top = max(top, para)
        sh.rect("A-ELEV", x - P.COL_X / 2.0, P.LVL_SITE, x + P.COL_X / 2.0, top)


def _elev_annotate(sh, x0, x1, grid_xs, labels):
    sh.line("A-SECT-GRND", x0 - 6000, P.LVL_SITE, x1 + 6000, P.LVL_SITE)
    sh.line("A-SECT-GRND", x0 - 6000, P.LVL_SITE - 160, x1 + 6000,
            P.LVL_SITE - 160)
    for x, lab in zip(grid_xs, labels):
        sh.line("A-GRID", x, P.LVL_SITE - 3000, x, P.LVL_AUD_PARA + 3000)
        grid_bubble(sh, x, P.LVL_AUD_PARA + 3700, lab)
    levels = [P.LVL_SITE, P.LVL_GF, P.LVL_FF, P.LVL_ROOF, P.LVL_PARAPET]
    if grid_xs is P.X_GRID:
        levels += [P.LVL_AUD_ROOF, P.LVL_AUD_PARA]
    for lv in levels:
        sh.line("A-FLOR-LEVL", x1, lv, x1 + 2600, lv)
        level_tag(sh, x1 + 2700, lv, lv)
    sh.dim_chain_h(grid_xs, P.LVL_SITE, P.LVL_SITE - 4200)


def _elev_long(sh, face, title, note, louvres):
    x0, x1 = P.SLAB_X0, P.SLAB_X1
    blocks = _elev_blocks(P.X_GRID)
    gf, ff = ENVELOPE[("GF", face)], ENVELOPE[("FF", face)]
    gf_lo, gf_hi = P.LVL_GF, P.LVL_FF - P.SLAB_T - P.BEAM_D
    ff_lo = P.LVL_FF
    _elev_glazing(sh, P.X_GRID, gf, gf_lo, gf_hi)
    for (a, b, roof, para) in blocks:
        code = "".join(ff[i] if a <= P.gx(i + 1) < b else "W"
                       for i in range(P.N_BAYS_X))
        _elev_glazing(sh, P.X_GRID, code, ff_lo,
                      roof - P.SLAB_T - P.BEAM_D)
        if louvres:
            _elev_louvres(sh, P.X_GRID, code, ff_lo,
                          roof - P.SLAB_T - P.BEAM_D)
    if louvres:
        _elev_louvres(sh, P.X_GRID, gf, gf_lo, gf_hi)
    _elev_frame(sh, P.X_GRID, blocks)
    _elev_annotate(sh, x0, x1, P.X_GRID, P.X_LABELS)
    sh.dim_h(x0, x1, P.LVL_SITE, P.LVL_SITE - 7400)
    drawing_title(sh, x0, P.LVL_SITE - 13500, title, note)


def draw_elev_north(sh):
    _elev_long(sh, "N", "NORTH ELEVATION",
               "SCALE 1 : 100    FROM THE TREE PROMENADE", louvres=False)
    fx = (P.gx(P.FOYER_G0) + P.gx(P.FOYER_G1)) / 2.0
    sh.rect("A-ELEV", fx - 3600, P.LVL_SITE, fx + 3600, P.LVL_GF + 3000)
    sh.text("A-ANNO-TEXT", "MAIN ENTRANCE", fx, P.LVL_GF + 1500, H_SMALL,
            TA.MIDDLE_CENTER)
    sh.text("A-ANNO-TEXT",
            "RAISED AUDITORIUM VOLUME, ROOF AT +%.3f"
            % (P.LVL_AUD_ROOF / 1000.0),
            (P.gx(2) + P.gx(5)) / 2.0, P.LVL_AUD_PARA + 1200, H_ROOM,
            TA.BOTTOM_CENTER)


def draw_elev_south(sh):
    _elev_long(sh, "S", "SOUTH ELEVATION",
               "SCALE 1 : 100    SHADED FACE", louvres=True)
    sh.text("A-ANNO-TEXT",
            "CONCRETE BRISE-SOLEIL, %d mm FINS AT %d mm PITCH"
            % (P.LOUVRE_PROJ, P.LOUVRE_PITCH),
            P.gx(10), P.LVL_PARAPET + 1200, H_ROOM, TA.BOTTOM_CENTER)


def draw_elev_end(sh, title, note):
    y0, y1 = P.SLAB_Y0, P.SLAB_Y1
    blocks = _elev_blocks(P.Y_GRID)
    full = "G" * (len(P.Y_GRID) - 1)
    _elev_glazing(sh, P.Y_GRID, full, P.LVL_GF,
                  P.LVL_FF - P.SLAB_T - P.BEAM_D)
    _elev_glazing(sh, P.Y_GRID, full, P.LVL_FF,
                  P.LVL_ROOF - P.SLAB_T - P.BEAM_D)
    _elev_frame(sh, P.Y_GRID, blocks)
    _elev_annotate(sh, y0, y1, P.Y_GRID, P.Y_LABELS)
    sh.dim_h(y0, y1, P.LVL_SITE, P.LVL_SITE - 7400)
    drawing_title(sh, y0, P.LVL_SITE - 13500, title, note)


# =============================================================================
# NOTES PANEL — the assumptions register, written into the drawing itself
# =============================================================================

NOTES = """AHMEDABAD MANAGEMENT ASSOCIATION  —  ATIRA CAMPUS, AHMEDABAD
ARCHITECTS: HCP DESIGN, PLANNING & MANAGEMENT  (BIMAL PATEL), 1999-2001

STATUS OF THIS DRAWING SET
--------------------------------------------------------------------
THIS IS A DIMENSIONAL RECONSTRUCTION, NOT A MEASURED SURVEY.
HCP HAS NEVER PUBLISHED DIMENSIONED DRAWINGS OF THIS BUILDING. THE SET
IS BUILT ON A DOCUMENTED STRUCTURAL GRID CALIBRATED TO THE PUBLISHED
FACTS BELOW. IT IS EXACT TO THE MILLIMETRE WITHIN ITSELF; IT IS NOT
VERIFIED AGAINST THE BUILT FABRIC. DO NOT USE FOR CONSTRUCTION.

PUBLISHED FACTS REPRODUCED BY THIS MODEL      SOURCE: HCP / WORLD-ARCHITECTS
--------------------------------------------------------------------
SITE AREA                3 ACRES              MODELLED  12 140.52 m2
BUILT-UP AREA            4 180 m2             MODELLED   4 173.60 m2  (-0.15%)
STOREYS                  2                    MODELLED  2
AUDITORIUM               250 SEATS            MODELLED  250 (10 ROWS x 25)
EXISTING NEEM TREES      8                    MODELLED  8
STRUCTURE                CAST IN-SITU EXPOSED CONCRETE, LINEAR BAR
GROUND FLOOR             DOUBLE-HEIGHT FOYER, CLASSROOMS, SEMINAR HALLS,
                         BOARDROOM, BOOKSHOP
FIRST FLOOR              LIBRARY, EXHIBITION SPACE, 250-SEAT AUDITORIUM
CIRCULATION              PROCESSIONAL RAMP FROM FOYER TO FIRST FLOOR

GEOMETRY ASSUMED BY THIS RECONSTRUCTION
--------------------------------------------------------------------
LONGITUDINAL BAY         7 200 mm x 13 BAYS  =  93 600 mm
TRANSVERSE BAYS          7 200 / 7 200 / 4 200  =  18 600 mm GRID A-D
SLAB CANTILEVER          1 800 mm EACH LONG FACE
OVERALL FOOTPRINT        94 000 x 22 200 mm
FLOOR-TO-FLOOR           4 500 mm  (GF +0.900, FF +5.400, ROOF +9.900)
AUDITORIUM ROOF          +12.300   PARAPET +13.350
COLUMNS                  400 x 700 mm RCC
SLAB / BEAM              150 mm SLAB, 300 x 600 mm BEAMS
RAMP                     4 FLIGHTS x 13 500 mm AT EXACTLY 1:12
                         RISE 1 125 mm PER FLIGHT, TOTAL 4 500 mm

PRECISION
--------------------------------------------------------------------
EVERY VERTEX IN THIS FILE IS AN EXACT INTEGER NUMBER OF MILLIMETRES.
DRAWING UNITS ARE MILLIMETRES ($INSUNITS = 4). MODEL SPACE IS 1:1.

DRAWING LIST
--------------------------------------------------------------------
AMA-01   SITE PLAN                             1:500
AMA-02   GROUND FLOOR PLAN                     1:100
AMA-03   FIRST FLOOR PLAN                      1:100
AMA-04   ROOF PLAN                             1:200
AMA-05   SECTION A-A  LONGITUDINAL             1:100
AMA-06   SECTIONS B-B AND C-C  TRANSVERSE      1:100
AMA-07   NORTH AND SOUTH ELEVATIONS            1:100
AMA-08   EAST AND WEST ELEVATIONS              1:100
AMA-09   PROJECT DATA AND ASSUMPTIONS          1:100"""


def draw_notes(sh):
    lines = NOTES.split("\n")
    h, lead = 400, 700
    for i, ln in enumerate(lines):
        style = TXT_TITLE if i < 2 else TXT_NOTE
        sh.text("A-ANNO-TEXT", ln, 0, -i * lead, h, TA.MIDDLE_LEFT,
                style=style)
    w, ht = 46000, len(lines) * lead + 2400
    sh.rect("A-ANNO-TTLB", -1600, -ht + 2000, w, 1600)


# =============================================================================
# PAPER SPACE SHEETS
# =============================================================================

A0, A1 = (1189, 841), (841, 594)

# (sheet name, paper, plot scale, drawings it frames, title block heading)
SHEETS = [
    ("AMA-01 SITE PLAN",        A1,  500, ["SITE"],   "SITE PLAN"),
    ("AMA-02 GROUND FLOOR",     A0,  100, ["GF"],     "GROUND FLOOR PLAN"),
    ("AMA-03 FIRST FLOOR",      A0,  100, ["FF"],     "FIRST FLOOR PLAN"),
    ("AMA-04 ROOF PLAN",        A1,  200, ["ROOF"],   "ROOF PLAN"),
    ("AMA-05 SECTION A-A",      A0,  100, ["SEC_AA"], "SECTION A-A"),
    ("AMA-06 SECTIONS B-B C-C", A0,  100, ["SEC_BB", "SEC_CC"],
     "SECTIONS B-B AND C-C"),
    ("AMA-07 ELEVATIONS N-S",   A0,  100, ["ELEV_N", "ELEV_S"],
     "NORTH AND SOUTH ELEVATIONS"),
    ("AMA-08 ELEVATIONS E-W",   A0,  100, ["ELEV_E", "ELEV_W"],
     "EAST AND WEST ELEVATIONS"),
    ("AMA-09 PROJECT DATA",     A1,  100, ["NOTES"],
     "PROJECT DATA AND ASSUMPTIONS"),
]

TB_H = 52          # title block strip height, paper mm
MARGIN = 12


def build_sheets(doc, extents):
    """Lay out the paper-space sheets. Each viewport is centred on the true
    bounding box of the drawings it frames, and the fit is asserted, so a
    drawing can never be silently clipped by its own sheet."""
    for (name, paper, scale, keys, title) in SHEETS:
        lay = doc.layouts.new(name)
        lay.page_setup(size=paper, margins=(0, 0, 0, 0), units="mm")
        pw, ph = paper
        ps = Sheet(lay, (0, 0))

        # --- border and title block -----------------------------------------
        ps.rect("A-ANNO-TTLB", MARGIN, MARGIN, pw - MARGIN, ph - MARGIN)
        ps.rect("A-ANNO-TTLB", MARGIN, MARGIN, pw - MARGIN, MARGIN + TB_H)
        ps.line("A-ANNO-TTLB", pw - MARGIN - 250, MARGIN,
                pw - MARGIN - 250, MARGIN + TB_H)

        tx, ty = MARGIN + 6, MARGIN + TB_H - 11
        ps.text("A-ANNO-TTLB", "AHMEDABAD MANAGEMENT ASSOCIATION", tx, ty,
                6.5, TA.MIDDLE_LEFT, style=TXT_TITLE)
        for i, line in enumerate((
                "ATIRA CAMPUS, DR VIKRAM SARABHAI MARG, AHMEDABAD 380015",
                "ORIGINAL ARCHITECTS: HCP DESIGN, PLANNING & MANAGEMENT "
                "(BIMAL PATEL), 1999-2001",
                "DIMENSIONAL RECONSTRUCTION FROM PUBLISHED DATA - "
                "NOT A MEASURED SURVEY - NOT FOR CONSTRUCTION",
                "ALL DIMENSIONS IN MILLIMETRES - "
                "DO NOT SCALE OFF THE DRAWING")):
            ps.text("A-ANNO-TTLB", line, tx, ty - 9 - i * 8, 3.0, TA.MIDDLE_LEFT)

        rx = pw - MARGIN - 250 + 8
        ps.text("A-ANNO-TTLB", title, rx, ty, 5.0, TA.MIDDLE_LEFT,
                style=TXT_TITLE)
        for i, line in enumerate(("SCALE  1 : %d" % scale,
                                  "DRAWING  %s" % name.split()[0],
                                  "SHEET  %s" % paper_name(paper))):
            ps.text("A-ANNO-TTLB", line, rx, ty - 12 - i * 9, 3.5,
                    TA.MIDDLE_LEFT)

        # --- viewport, framed on what it actually contains -------------------
        vp_w = pw - 2 * MARGIN - 4
        vp_h = ph - 2 * MARGIN - TB_H - 6
        box = [1e18, 1e18, -1e18, -1e18]
        for k in keys:
            b = extents[k]
            box[0], box[1] = min(box[0], b[0]), min(box[1], b[1])
            box[2], box[3] = max(box[2], b[2]), max(box[3], b[3])
        need_w, need_h = box[2] - box[0], box[3] - box[1]
        have_w, have_h = vp_w * scale, vp_h * scale
        if need_w > have_w or need_h > have_h:
            raise AssertionError(
                "sheet %s at 1:%d cannot hold %s: needs %.0f x %.0f mm, "
                "viewport gives %.0f x %.0f mm"
                % (name, scale, "+".join(keys), need_w, need_h,
                   have_w, have_h))
        lay.add_viewport(
            center=(MARGIN + 2 + vp_w / 2.0,
                    MARGIN + TB_H + 4 + vp_h / 2.0),
            size=(vp_w, vp_h),
            view_center_point=((box[0] + box[2]) / 2.0,
                               (box[1] + box[3]) / 2.0),
            view_height=have_h,
            dxfattribs={"layer": "DEFPOINTS"})


def paper_name(paper):
    return {(1189, 841): "A0", (841, 594): "A1", (594, 420): "A2"}.get(
        paper, "%dx%d" % paper)


# =============================================================================
# MAIN
# =============================================================================

def main():
    doc = new_document()
    msp = doc.modelspace()
    O = P.ORIGINS

    extents = {}

    def place(key, fn, *args):
        """Draw one drawing and record the true bounding box of exactly the
        entities it created, so sheet composition can be verified."""
        before = len(msp)
        sh = Sheet(msp, O[key])
        fn(sh, *args)
        made = list(msp)[before:]
        box = [1e18, 1e18, -1e18, -1e18]
        for e in made:
            for pt in _entity_points(e):
                box[0], box[1] = min(box[0], pt[0]), min(box[1], pt[1])
                box[2], box[3] = max(box[2], pt[0]), max(box[3], pt[1])
        extents[key] = box
        return sh

    place("SITE", draw_site)
    place("GF", draw_ground_floor)
    place("FF", draw_first_floor)
    place("ROOF", draw_roof)
    place("SEC_AA", draw_section_aa)
    place("SEC_BB", draw_section_bb)
    place("SEC_CC", draw_section_cc)
    place("ELEV_N", draw_elev_north)
    place("ELEV_S", draw_elev_south)
    place("ELEV_E", draw_elev_end,
          "EAST ELEVATION", "SCALE 1 : 100    GRID 14")
    place("ELEV_W", draw_elev_end,
          "WEST ELEVATION", "SCALE 1 : 100    GRID 1")
    place("NOTES", draw_notes)

    build_sheets(doc, extents)

    # the default empty layouts must not ship with the drawing set; this has
    # to follow build_sheets, since a drawing must keep one paper space
    for junk in ("Layout1", "Layout2"):
        if junk in doc.layouts.names():
            doc.layouts.delete(junk)

    doc.set_modelspace_vport(height=340000, center=(46000, -80000))

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "AMA_Ahmedabad_HCP.dxf")
    doc.saveas(out)
    with open(os.path.join(os.path.dirname(out), "extents.json"), "w") as f:
        json.dump(extents, f, indent=1, sort_keys=True)
    return doc, out


if __name__ == "__main__":
    doc, out = main()
    msp = doc.modelspace()
    print("written: %s" % out)
    print("entities in model space: %d" % len(msp))
    print("layers: %d" % len(doc.layers))
    print("paper space sheets: %d"
          % len([n for n in doc.layouts.names() if n != "Model"]))
    print("layers: %s" % ", ".join(sorted(
        {e.dxf.layer for e in msp})))
