#!/usr/bin/env python3
"""
Validation for the AMA drawing set.

Checks three separate things:
  1. The model reproduces every published figure it claims to.
  2. Every coordinate in the DXF is an exact integer number of millimetres.
  3. The DXF itself is structurally sound and geometrically contained.

Exit status is non-zero if any check fails.
"""
import json
import os
import sys
from collections import Counter

import ezdxf
from ezdxf.math import Vec3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ama_params as P
import ama_build as B

DXF = os.path.join(HERE, "AMA_Ahmedabad_HCP.dxf")
TOL = 1e-6
fails, warns = [], []


def check(ok, label, detail=""):
    print("  %s  %-54s %s" % ("PASS" if ok else "FAIL", label, detail))
    if not ok:
        fails.append(label)


def warn(ok, label, detail=""):
    print("  %s  %-54s %s" % ("ok  " if ok else "WARN", label, detail))
    if not ok:
        warns.append(label)


# =============================================================================
print("\n1. PUBLISHED FIGURES REPRODUCED BY THE MODEL")
print("-" * 78)

built_up = (P.BLDG_L * P.BLDG_W * 2) / 1.0e6
dev = abs(built_up - 4180.0) / 4180.0 * 100
check(dev < 1.0, "built-up area within 1% of published 4 180 m2",
      "%.2f m2  (%.2f%%)" % (built_up, -dev))

site = (P.SITE_W * P.SITE_H) / 1.0e6
acres = site / 4046.8564224
check(abs(acres - 3.0) < 0.005, "site area is 3 acres",
      "%.2f m2 = %.4f acres" % (site, acres))

seats = sum(len(r) for r in B.auditorium_seat_rows())
check(seats == 250, "auditorium seats exactly 250", "%d seats" % seats)

check(P.N_TREES == 8, "eight existing neem trees", "%d" % P.N_TREES)
check(P.LVL_FF > P.LVL_GF and P.LVL_ROOF > P.LVL_FF,
      "two storeys above the plinth",
      "+%.3f / +%.3f / +%.3f" % (P.LVL_GF / 1000, P.LVL_FF / 1000,
                                 P.LVL_ROOF / 1000))

gf = {n.split("\n")[0] for _, _, n in P.GF_ROOMS}
ff = {n.split("\n")[0] for _, _, n in P.FF_ROOMS}
need_gf = {"ENTRANCE FOYER", "CLASSROOM 1", "SEMINAR HALL 1", "BOARD ROOM",
           "BOOK SHOP"}
need_ff = {"LIBRARY", "EXHIBITION SPACE", "AUDITORIUM"}
check(need_gf <= gf, "ground floor carries the published programme",
      ", ".join(sorted(need_gf)))
check(need_ff <= ff, "first floor carries the published programme",
      ", ".join(sorted(need_ff)))

# =============================================================================
print("\n2. RAMP GEOMETRY")
print("-" * 78)

check(P.RAMP_RUN_EACH == P.RAMP_RISE_EACH * 12,
      "ramp gradient is exactly 1:12",
      "%d rise / %d run" % (P.RAMP_RISE_EACH, P.RAMP_RUN_EACH))
check(P.RAMP_RISE_EACH * P.RAMP_FLIGHTS == P.LVL_FF - P.LVL_GF,
      "four flights rise exactly floor to floor",
      "%d x %d = %d mm" % (P.RAMP_FLIGHTS, P.RAMP_RISE_EACH,
                           P.RAMP_RISE_EACH * P.RAMP_FLIGHTS))

flights, landings = B.ramp_geometry()
cuts = [B.ramp_level_at(f, B.SECT_AA_Y) for f in flights]
check(all(float(c).is_integer() for c in cuts),
      "section A-A cuts every flight at a whole millimetre",
      ", ".join("+%d" % c for c in cuts))

fx0 = min(f[0] for f in flights)
fx1 = max(max(f[1] for f in flights), max(l[1] for l in landings))
foy0 = P.gx(P.FOYER_G0) + P.WALL_EXT / 2.0
foy1 = P.gx(P.FOYER_G1) - P.WALL_EXT / 2.0
check(foy0 <= fx0 and fx1 <= foy1,
      "ramp and landings sit inside the foyer",
      "ramp %d..%d in foyer %d..%d" % (fx0, fx1, foy0, foy1))

fy0 = min(min(f[2], f[3]) for f in flights)
fy1 = max(max(f[2], f[3]) for f in flights)
check(P.Y_A + P.WALL_EXT / 2.0 <= fy0 and fy1 <= P.Y_D - P.WALL_EXT / 2.0,
      "ramp stays within the building depth",
      "%d..%d" % (fy0, fy1))

# =============================================================================
print("\n3. AUDITORIUM FITS ITS SHELL")
print("-" * 78)

rows = B.auditorium_seat_rows()
ys = [y for r in rows for (_, y) in r]
xs = [x for r in rows for (x, _) in r]
half = P.AUD_SEAT_W / 2.0
check(min(ys) - half >= P.Y_A + P.WALL_ACOU / 2.0 and
      max(ys) + half <= P.Y_D - P.WALL_ACOU / 2.0,
      "seating fits between gridlines A and D",
      "%d..%d in %d..%d" % (min(ys) - half, max(ys) + half,
                            P.Y_A + P.WALL_ACOU / 2, P.Y_D - P.WALL_ACOU / 2))
check(max(xs) + P.AUD_SEAT_DEPTH / 2.0 <= P.gx(5) - P.WALL_ACOU / 2.0,
      "rear row clears the grid-5 wall",
      "%d <= %d" % (max(xs) + P.AUD_SEAT_DEPTH / 2,
                    P.gx(5) - P.WALL_ACOU / 2))
check(min(xs) - P.AUD_SEAT_DEPTH / 2.0 >= P.AUD_STAGE_X0 + P.AUD_STAGE_D,
      "row 1 clears the stage",
      "%d >= %d" % (min(xs) - P.AUD_SEAT_DEPTH / 2,
                    P.AUD_STAGE_X0 + P.AUD_STAGE_D))
hall = (P.gx(5) - P.gx(2)) * (P.Y_D - P.Y_A) / 1.0e6
warn(1.2 <= hall / 250 <= 2.2, "hall area per seat is reasonable",
     "%.2f m2/seat" % (hall / 250))

# =============================================================================
print("\n4. EVERY COORDINATE IS A WHOLE MILLIMETRE")
print("-" * 78)

doc = ezdxf.readfile(DXF)
msp = doc.modelspace()


def coords(e):
    t = e.dxftype()
    if t == "LINE":
        return [e.dxf.start, e.dxf.end]
    if t == "LWPOLYLINE":
        return [Vec3(p[0], p[1], 0) for p in e.get_points("xy")]
    if t in ("CIRCLE", "ARC"):
        return [e.dxf.center]
    if t == "TEXT":
        return [e.dxf.insert, e.dxf.align_point]
    if t == "POINT":
        return [e.dxf.location]
    return []


def integral(v):
    return abs(v - round(v)) < TOL


bad, seen, kinds = [], 0, Counter()
for e in msp:
    kinds[e.dxftype()] += 1
    for pt in coords(e):
        if pt is None:
            continue
        for v in (pt.x, pt.y, pt.z):
            seen += 1
            if not integral(v):
                bad.append((e.dxftype(), e.dxf.layer, v))

check(not bad, "all model-space vertices are integer mm",
      "%d ordinates checked, %d non-integer" % (seen, len(bad)))
for t, lay, v in bad[:6]:
    print("        %-14s %-16s %.6f" % (t, lay, v))

rad = [e for e in msp if e.dxftype() in ("CIRCLE", "ARC")
       and not integral(e.dxf.radius)]
check(not rad, "all radii are integer mm", "%d non-integer" % len(rad))

for name, val in (("BAY_X", P.BAY_X), ("Y_A", P.Y_A), ("Y_D", P.Y_D),
                  ("BLDG_L", P.BLDG_L), ("BLDG_W", P.BLDG_W),
                  ("LVL_FF", P.LVL_FF), ("LVL_ROOF", P.LVL_ROOF),
                  ("RAMP_RUN_EACH", P.RAMP_RUN_EACH)):
    if not isinstance(val, int):
        fails.append("parameter %s is not an integer" % name)
check(not [f for f in fails if f.startswith("parameter")],
      "all governing parameters are integers", "%d checked" % 8)

# =============================================================================
print("\n5. FILE STRUCTURE")
print("-" * 78)

check(doc.dxfversion == "AC1032", "DXF version is AC1032 (AutoCAD 2018)",
      doc.dxfversion)
check(doc.header["$INSUNITS"] == 4, "drawing units are millimetres",
      "$INSUNITS = %d" % doc.header["$INSUNITS"])
check(doc.header["$MEASUREMENT"] == 1, "metric measurement flag set")

used = Counter(e.dxf.layer for e in msp)
declared = {n for n, *_ in __import__("ama_draft").LAYERS}
check(set(used) <= set(l.dxf.name for l in doc.layers),
      "every entity sits on a declared layer",
      "%d layers in use" % len(used))
empty = sorted(declared - set(used) - {"DEFPOINTS"})
warn(not empty, "no declared layer is left empty",
     ", ".join(empty) if empty else "")

layouts = [l for l in doc.layouts if l != "Model"]
check(len(layouts) >= len(B.SHEETS),
      "paper-space sheets present", "%d layouts" % len(layouts))

# =============================================================================
print("\n6. DRAWINGS DO NOT COLLIDE IN MODEL SPACE")
print("-" * 78)

boxes = json.load(open(os.path.join(HERE, "extents.json")))

overlaps = []
keys = sorted(boxes)
for i, a in enumerate(keys):
    for b in keys[i + 1:]:
        A, Bx = boxes[a], boxes[b]
        ox = min(A[2], Bx[2]) - max(A[0], Bx[0])
        oy = min(A[3], Bx[3]) - max(A[1], Bx[1])
        if ox > 0 and oy > 0:
            overlaps.append("%s/%s (%dx%d mm)" % (a, b, ox, oy))
check(not overlaps, "no two drawings overlap",
      "; ".join(overlaps) if overlaps else "%d drawings clear" % len(boxes))

# =============================================================================
print("\n" + "=" * 78)
print("entities: %s" % ", ".join("%s %d" % (k, v)
                                 for k, v in kinds.most_common()))
print("total model-space entities: %d" % len(msp))
if fails:
    print("\nFAILED: %d check(s): %s" % (len(fails), "; ".join(fails)))
    sys.exit(1)
print("\nAll checks passed.%s"
      % (" %d warning(s)." % len(warns) if warns else ""))
