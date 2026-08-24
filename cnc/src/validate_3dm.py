"""
Step 11 - read the Rhino assembly back off disk and check it.

Nothing here trusts the writer: every number comes from re-opening the .3dm.
"""
import collections

import numpy as np
import rhino3dm as r3

import config
import assembly


def read(path):
    m = r3.File3dm.Read(path)
    layers = {i: m.Layers[i] for i in range(len(m.Layers))}
    names = {}
    for i, lay in layers.items():
        n, p = lay.Name, lay.ParentLayerId
        while p is not None and str(p) != "00000000-0000-0000-0000-000000000000":
            par = next((l for l in layers.values() if str(l.Id) == str(p)), None)
            if par is None:
                break
            n = par.Name + "/" + n
            p = par.ParentLayerId
        names[i] = n
    objs = []
    for ob in m.Objects:
        g = ob.Geometry
        objs.append({"geom": g, "layer": names.get(ob.Attributes.LayerIndex, "?"),
                     "type": type(g).__name__})
    return m, objs


def profiles_of(ext):
    """[(Nx2 array, ...)] - outer first, then the holes, plus (z0, z1)."""
    rings = []
    for i in range(ext.ProfileCount):
        c = ext.Profile3d(i, 0.0)
        if c is None:
            continue
        pts = np.array([[c.Point(k).X, c.Point(k).Y] for k in range(c.PointCount)])
        rings.append(pts)
    z0, z1 = ext.PathStart.Z, ext.PathEnd.Z
    return rings, (min(z0, z1), max(z0, z1))


def _centre_radius(ring):
    c = ring[:-1].mean(axis=0)
    r = np.hypot(ring[:-1, 0] - c[0], ring[:-1, 1] - c[1])
    return c, r.mean(), r.std()


def check(path, dowels, profiles, sockets, verbose=True):
    m, objs = read(path)
    errors, warnings = [], []
    S = config.SCALE
    T = config.BOARD_MM

    exts = [o for o in objs if o["type"] == "Extrusion"]
    boards = [o for o in exts if o["layer"].startswith(("01_BASE_BOARD", "02_BOARDS"))]
    rods = [o for o in exts if o["layer"].startswith("03_DOWEL")]
    blocks = [o for o in exts if o["layer"].startswith("04_BUILDING")]

    for o in exts:
        if not o["geom"].IsSolid:
            errors.append(f"{o['layer']}: extrusion is not a closed solid")

    # board thickness and elevation
    holes_by_board = {}
    for o in boards:
        rings, (z0, z1) = profiles_of(o["geom"])
        if abs((z1 - z0) - T) > 1e-6:
            errors.append(f"{o['layer']}: board is {z1-z0:.3f} mm thick, expected {T}")
        lay = o["layer"].rsplit("/", 1)[-1]
        if lay.startswith("L"):
            L = int(lay[1:])
            want = L * 1000.0 / S
            if abs(z0 - want) > 1e-6:
                errors.append(f"{o['layer']}: sits at Z {z0:.3f}, expected {want:.3f}")
        else:
            L = config.BASE_LEVEL
            if abs(z0 - config.BASE_LEVEL * 1000.0 / S) > 1e-6:
                errors.append(f"base board sits at Z {z0:.3f}")
        holes_by_board.setdefault(L, []).extend(rings[1:])

    # every dowel must have a hole in every board of its run, at the right size
    tol = 0.05
    for d in dowels:
        for L in d["levels"]:
            found = False
            for ring in holes_by_board.get(L, []):
                c, r, sd = _centre_radius(ring)
                if abs(c[0] - d["x"]) < tol and abs(c[1] - d["y"]) < tol:
                    found = True
                    if abs(r * 2 - assembly.HOLE_DIA) > 0.05 or sd > 0.02:
                        errors.append(f"{d['id']} on L{L}: hole is {r*2:.3f} mm, "
                                      f"expected {assembly.HOLE_DIA}")
                    break
            if not found:
                errors.append(f"{d['id']}: no hole in board L{L} of its run")

    # rods must span the base board up to the top face of their top board
    if len(rods) != len(dowels):
        errors.append(f"{len(rods)} rods for {len(dowels)} dowels")
    rod_by_xy = {}
    for o in rods:
        rings, (z0, z1) = profiles_of(o["geom"])
        c, r, _sd = _centre_radius(rings[0])
        rod_by_xy[(round(c[0], 3), round(c[1], 3))] = (z0, z1, r * 2)
    for d in dowels:
        k = (round(d["x"], 3), round(d["y"], 3))
        if k not in rod_by_xy:
            errors.append(f"{d['id']}: no rod")
            continue
        z0, z1, dia = rod_by_xy[k]
        wz0 = config.BASE_LEVEL * 1000.0 / S
        wz1 = (d["top_level"] + 1) * 1000.0 / S
        if abs(z0 - wz0) > 1e-6 or abs(z1 - wz1) > 1e-6:
            errors.append(f"{d['id']}: rod spans {z0:.2f}-{z1:.2f}, expected {wz0:.2f}-{wz1:.2f}")
        if abs(dia - assembly.ROD_DIA) > 0.02:
            errors.append(f"{d['id']}: rod is {dia:.2f} mm")
        if dia >= assembly.HOLE_DIA:
            errors.append(f"{d['id']}: rod {dia:.2f} does not fit hole {assembly.HOLE_DIA}")

    # sockets
    n_sock = sum(len(v) for v in sockets.values())
    sock_found = 0
    for L, v in sockets.items():
        for s in v:
            cen = np.array(s["poly"].centroid.coords[0])
            hit = any(np.hypot(*(ring[:-1].mean(axis=0) - cen)) < 0.5
                      for ring in holes_by_board.get(L, []))
            sock_found += 1 if hit else 0
            if not hit:
                errors.append(f"socket at L{L} {cen.round(1)} is not cut in the board")

    # nothing may poke out of the model box
    bb = None
    for o in objs:
        b = o["geom"].GetBoundingBox()
        lo = np.array([b.Min.X, b.Min.Y, b.Min.Z])
        hi = np.array([b.Max.X, b.Max.Y, b.Max.Z])
        bb = (lo, hi) if bb is None else (np.minimum(bb[0], lo), np.maximum(bb[1], hi))
    W = config.MODEL_W_M * 1000.0 / S
    H = config.MODEL_H_M * 1000.0 / S
    if bb[0][0] < -1e-6 or bb[0][1] < -1e-6 or bb[1][0] > W + 1e-6 or bb[1][1] > H + 1e-6:
        warnings.append(f"geometry outside the {W:.0f} x {H:.0f} mm model footprint: "
                        f"{bb[0].round(2)} to {bb[1].round(2)}")

    if verbose:
        by = collections.Counter(o["layer"] for o in objs)
        print(f"  {len(objs)} objects on {len(m.Layers)} layers, "
              f"units {m.Settings.ModelUnitSystem}")
        print(f"  {len(boards)} board solids   {len(rods)} rods   {len(blocks)} blocks")
        print(f"  every extrusion closed: {all(o['geom'].IsSolid for o in exts)}")
        print(f"  dowel holes checked: {sum(len(d['levels']) for d in dowels)}   "
              f"sockets found: {sock_found}/{n_sock}")
        print(f"  bounding box  X {bb[0][0]:.1f}..{bb[1][0]:.1f}   "
              f"Y {bb[0][1]:.1f}..{bb[1][1]:.1f}   Z {bb[0][2]:.1f}..{bb[1][2]:.1f} mm")
        print(f"  ERRORS {len(errors)}   WARNINGS {len(warnings)}")
        for e in errors[:20]:
            print("    ERROR:", e)
        for w in warnings[:10]:
            print("    WARN :", w)
    return errors, warnings
