"""
Step 10 - the Rhino assembly.

Every board is a real closed solid: an Extrusion whose outer profile is the cut
outline and whose inner profiles are the terrain holes, the dowel holes and the
building sockets.  Rhino reads them as solids straight away - no booleans to
run, nothing to repair.

Two files come out of this:

  MASTER_ASSEMBLY_1to500.3dm   the fabrication model - 25 boards of 2 mm with
                               every cutout and socket made, the dowel rods,
                               the building blocks and the reference curves.
  MASTER_3D_1to1.3dm           the same site at full size, as reference
                               geometry: contours at true elevation, a terrain
                               mesh, footprints and out-to-out boxes.  No boards
                               or dowels - those are 1:500 fabrication features
                               and a 1 m thick "board" would be meaningless.
"""
import numpy as np
import rhino3dm as r3

import config
import assembly

# hypsometric layer colours, roughly matching the renders
LEVEL_RGB = {
    44: (60, 114, 168), 45: (68, 126, 160), 46: (79, 139, 152), 47: (92, 152, 143),
    48: (105, 160, 133), 49: (120, 168, 124), 50: (135, 175, 118), 51: (150, 181, 113),
    52: (166, 187, 112), 53: (182, 191, 114), 54: (197, 194, 120), 55: (203, 187, 121),
    56: (203, 176, 118), 57: (201, 165, 116), 58: (196, 153, 114), 59: (188, 142, 113),
    60: (179, 133, 112), 61: (172, 128, 114), 62: (170, 130, 122), 63: (176, 143, 137),
    64: (190, 163, 156), 65: (208, 186, 179), 66: (227, 210, 203), 67: (245, 241, 239),
}
BASE_RGB = (96, 96, 100)
ROD_RGB = (188, 142, 58)
BLOCK_RGB = (120, 130, 148)
REF_RGB = (110, 110, 118)


# --------------------------------------------------------------------------
# geometry helpers

def _signed_area(a):
    x, y = a[:, 0], a[:, 1]
    return 0.5 * (np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]))


def _closed(a):
    a = np.asarray(a, dtype=float)[:, :2]
    if np.hypot(*(a[-1] - a[0])) > 1e-9:
        a = np.vstack([a, a[:1]])
    return a


def _orient(a, ccw):
    a = _closed(a)
    return a if (_signed_area(a) > 0) == ccw else a[::-1]


def _curve(pts, z=0.0):
    pl = r3.Point3dList()
    for x, y in pts:
        pl.Add(float(x), float(y), float(z))
    return r3.PolylineCurve(pl)


def _curve3d(pts):
    pl = r3.Point3dList()
    for p in pts:
        pl.Add(float(p[0]), float(p[1]), float(p[2]))
    return r3.PolylineCurve(pl)


def solid(outer, holes, z0, z1):
    """Closed Extrusion from an outer ring and any number of hole rings."""
    ext = r3.Extrusion()
    if not ext.SetPathAndUp(r3.Point3d(0, 0, float(z0)),
                            r3.Point3d(0, 0, float(z1)), r3.Vector3d(0, 1, 0)):
        raise RuntimeError("SetPathAndUp failed")
    if not ext.SetOuterProfile(_curve(_orient(outer, True)), True):
        raise RuntimeError("SetOuterProfile failed")
    for h in holes:
        h = _orient(h, False)
        if len(h) < 4:
            continue
        if not ext.AddInnerProfile(_curve(h)):
            raise RuntimeError("AddInnerProfile failed")
    if not ext.IsSolid:
        raise RuntimeError("extrusion is not a closed solid")
    return ext


def _circle(cx, cy, dia, n=assembly.HOLE_SEGMENTS):
    t = np.linspace(0, 2 * np.pi, n + 1)
    return np.column_stack([cx + dia / 2 * np.cos(t), cy + dia / 2 * np.sin(t)])


# --------------------------------------------------------------------------
# layers

def _layer(model, name, rgb, parent=None):
    lay = r3.Layer()
    lay.Name = name
    lay.Color = (rgb[0], rgb[1], rgb[2], 255)
    if parent is not None:
        lay.ParentLayerId = parent
    idx = model.Layers.Add(lay)
    return model.Layers[idx].Id, idx


def _attr(layer_index):
    a = r3.ObjectAttributes()
    a.LayerIndex = layer_index
    return a


# --------------------------------------------------------------------------
# the fabrication assembly

def write_assembly(path, profiles, boxes, dowels, sockets, Z, verbose=True):
    S = config.SCALE
    T = config.BOARD_MM
    model = r3.File3dm()
    model.Settings.ModelUnitSystem = r3.UnitSystem.Millimeters
    model.Settings.ModelAbsoluteTolerance = 0.001

    ref_id, ref_i = _layer(model, "00_REFERENCE", REF_RGB)
    bnd_id, bnd_i = _layer(model, "MODEL_BOUNDARY", (30, 30, 34), ref_id)
    con_id, con_i = _layer(model, "CONTOURS", REF_RGB, ref_id)
    sit_id, sit_i = _layer(model, "SITE_BOUNDARY", (170, 60, 170), ref_id)
    wat_id, wat_i = _layer(model, "WATER", (30, 160, 180), ref_id)
    base_id, base_i = _layer(model, "01_BASE_BOARD", BASE_RGB)
    brd_id, brd_i = _layer(model, "02_BOARDS_2mm", (140, 140, 140))
    rod_id, rod_i = _layer(model, "03_DOWEL_RODS_%.1fmm" % assembly.ROD_DIA, ROD_RGB)
    blk_id, blk_i = _layer(
        model, "04_BUILDING_BLOCKS_nominal_%.0fm" % config.BUILDING_H_NOMINAL_M, BLOCK_RGB)
    box_id, box_i = _layer(model, "05_ROOF_OUT_TO_OUT_BOXES", (40, 90, 175))

    W = config.MODEL_W_M * 1000.0 / S
    H = config.MODEL_H_M * 1000.0 / S
    zb = config.BASE_LEVEL * 1000.0 / S             # bottom of the base board

    counts = {"boards": 0, "holes": 0, "dowel_holes": 0, "sockets": 0}

    # --- base board -------------------------------------------------------
    base_holes = [_circle(d["x"], d["y"], assembly.HOLE_DIA) for d in dowels]
    counts["dowel_holes"] += len(base_holes)
    rect = np.array([(0, 0), (W, 0), (W, H), (0, H), (0, 0)], dtype=float)
    model.Objects.AddExtrusion(solid(rect, base_holes, zb, zb + T), _attr(base_i))
    counts["boards"] += 1

    # --- one sublayer and one solid set per level -------------------------
    for L in sorted(profiles):
        rgb = LEVEL_RGB.get(L, (150, 150, 150))
        _lid, li = _layer(model, "L%02d" % L, rgb, brd_id)
        z0 = L * 1000.0 / S
        dow = [d for d in dowels if L in d["levels"]]
        soc = sockets.get(L, [])
        for isl in profiles[L]:
            outer = isl["outer"][:, :2] / S
            poly_holes = [h[:, :2] / S for h in isl["holes"]]
            from shapely.geometry import Polygon, Point
            shp = Polygon(outer, poly_holes)
            if not shp.is_valid:
                shp = shp.buffer(0)
            extra = []
            for d in dow:
                if shp.contains(Point(d["x"], d["y"])):
                    extra.append(_circle(d["x"], d["y"], assembly.HOLE_DIA))
                    counts["dowel_holes"] += 1
            for s in soc:
                if shp.contains(s["poly"]):
                    extra.append(np.asarray(s["poly"].exterior.coords))
                    counts["sockets"] += 1
            counts["holes"] += len(poly_holes)
            counts["boards"] += 1
            model.Objects.AddExtrusion(
                solid(outer, poly_holes + extra, z0, z0 + T), _attr(li))

    # --- dowel rods -------------------------------------------------------
    for d in dowels:
        ztop = (d["top_level"] + 1) * 1000.0 / S
        model.Objects.AddExtrusion(
            solid(_circle(d["x"], d["y"], assembly.ROD_DIA), [], zb, ztop), _attr(rod_i))

    # --- building blocks --------------------------------------------------
    h_blk = config.BUILDING_H_NOMINAL_M * 1000.0 / S
    socket_boxes = [s["poly"] for v in sockets.values() for s in v]
    for kind in ("raster", "campus", "platform"):
        for e in boxes.get(kind, ()):
            ring = e.get("box_clip")
            if ring is None:
                continue
            g = ring[:, :2] / S
            zlo, zhi = _terrain_span(Z, ring, S)
            seated = any(sb.equals_exact(_shp(g), 1e-6) for sb in socket_boxes)
            z0 = zlo - T if seated else zlo
            model.Objects.AddExtrusion(solid(g, [], z0, zhi + h_blk), _attr(blk_i))
            model.Objects.AddCurve(_curve(_closed(g), zhi), _attr(box_i))

    # --- reference curves -------------------------------------------------
    model.Objects.AddCurve(_curve(rect, zb), _attr(bnd_i))
    for L in sorted(profiles):
        z = (L + 1) * 1000.0 / S          # the contour reads on the board's top face
        for isl in profiles[L]:
            for r in [isl["outer"]] + isl["holes"]:
                model.Objects.AddCurve(_curve(_closed(r[:, :2] / S), z), _attr(con_i))

    model.Write(path, 7)
    if verbose:
        print(f"  {counts['boards']} board solids, {counts['dowel_holes']} dowel holes, "
              f"{counts['sockets']} sockets, {counts['holes']} terrain holes, "
              f"{len(dowels)} rods")
    return path, counts


def _shp(a):
    from shapely.geometry import Polygon
    return Polygon(a)


def _terrain_span(Z, ring_mm_ground, scale):
    """Lowest and highest stepped board top under a footprint, in model mm."""
    cell = config.DEM_CELL_M * 1000.0
    ny, nx = Z.shape
    x = np.clip((ring_mm_ground[:, 0] / cell).astype(int), 0, nx - 1)
    y = np.clip((ring_mm_ground[:, 1] / cell).astype(int), 0, ny - 1)
    v = Z[y, x]
    lo = np.floor(v.min())
    hi = np.floor(v.max())
    return (lo + 1) * 1000.0 / scale, (hi + 1) * 1000.0 / scale


# --------------------------------------------------------------------------
# full-size reference model

def write_reference_1to1(path, profiles, boxes, Z, verbose=True):
    model = r3.File3dm()
    model.Settings.ModelUnitSystem = r3.UnitSystem.Millimeters
    model.Settings.ModelAbsoluteTolerance = 0.01

    ref_id, _ = _layer(model, "00_REFERENCE", REF_RGB)
    _b, bnd_i = _layer(model, "MODEL_BOUNDARY", (30, 30, 34), ref_id)
    _m, mesh_i = _layer(model, "01_TERRAIN_MESH", (150, 160, 140))
    _c, con_parent = _layer(model, "02_CONTOURS_1m", REF_RGB)
    con_parent_id = model.Layers[con_parent].Id
    _f, foot_i = _layer(model, "03_ROOF_FOOTPRINTS", (110, 110, 118))
    _x, box_i = _layer(model, "04_ROOF_OUT_TO_OUT_BOXES", (40, 90, 175))
    _w, wat_i = _layer(model, "05_WATER", (30, 160, 180))

    W = config.MODEL_W_M * 1000.0
    H = config.MODEL_H_M * 1000.0
    model.Objects.AddCurve(
        _curve(np.array([(0, 0), (W, 0), (W, H), (0, H), (0, 0)], float),
               config.BASE_LEVEL * 1000.0), _attr(bnd_i))

    for L in sorted(profiles):
        rgb = LEVEL_RGB.get(L, (150, 150, 150))
        _l, li = _layer(model, "L%02d" % L, rgb, con_parent_id)
        for isl in profiles[L]:
            for r in [isl["outer"]] + isl["holes"]:
                model.Objects.AddCurve(_curve(_closed(r[:, :2]), L * 1000.0), _attr(li))

    mesh = _grid_mesh(Z, step_m=2.0)
    model.Objects.AddMesh(mesh, _attr(mesh_i))

    for kind in ("raster", "campus", "platform"):
        for e in boxes.get(kind, ()):
            for ring, li in ((e.get("footprint_clip"), foot_i), (e.get("box_clip"), box_i)):
                if ring is None:
                    continue
                zz = _sample(Z, ring) * 1000.0
                model.Objects.AddCurve(
                    _curve3d(np.column_stack([ring[:, 0], ring[:, 1], zz])), _attr(li))
    for e in boxes.get("water", ()):
        ring = e.get("footprint_clip")
        if ring is not None:
            zz = _sample(Z, ring) * 1000.0
            model.Objects.AddCurve(
                _curve3d(np.column_stack([ring[:, 0], ring[:, 1], zz])), _attr(wat_i))

    model.Write(path, 7)
    if verbose:
        print(f"  terrain mesh {len(mesh.Faces)} faces, contours on {len(profiles)} layers")
    return path


def _sample(Z, pts_mm):
    cell = config.DEM_CELL_M * 1000.0
    ny, nx = Z.shape
    x = np.clip((pts_mm[:, 0] / cell).astype(int), 0, nx - 1)
    y = np.clip((pts_mm[:, 1] / cell).astype(int), 0, ny - 1)
    return Z[y, x]


def _grid_mesh(Z, step_m=2.0):
    cell = config.DEM_CELL_M
    stride = max(1, int(round(step_m / cell)))
    ri = np.unique(np.append(np.arange(0, Z.shape[0], stride), Z.shape[0] - 1))
    ci = np.unique(np.append(np.arange(0, Z.shape[1], stride), Z.shape[1] - 1))
    S = Z[np.ix_(ri, ci)]
    x = np.clip((ci * cell + cell / 2.0) * 1000.0, 0, config.MODEL_W_M * 1000.0)
    y = np.clip((ri * cell + cell / 2.0) * 1000.0, 0, config.MODEL_H_M * 1000.0)
    x[0] = y[0] = 0.0
    x[-1] = config.MODEL_W_M * 1000.0
    y[-1] = config.MODEL_H_M * 1000.0
    mesh = r3.Mesh()
    for j in range(len(y)):
        for i in range(len(x)):
            mesh.Vertices.Add(float(x[i]), float(y[j]), float(S[j, i] * 1000.0))
    nx = len(x)
    for j in range(len(y) - 1):
        for i in range(nx - 1):
            a = j * nx + i
            mesh.Faces.AddFace(a, a + 1, a + nx + 1, a + nx)
    return mesh
