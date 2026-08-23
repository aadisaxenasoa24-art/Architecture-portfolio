"""
Step 5 - the master 3-D files.

Two DXFs (1:1 in real millimetres, and 1:500) carrying the contour set as closed
3-D polylines at true Z, the building boxes and footprints draped on the
terrain, plus a binary STL of the terrain surface for 3-axis CAM.
"""
import struct

import ezdxf
import numpy as np

import config

LAYER_COLOUR = {  # AutoCAD colour index, roughly hypsometric
    44: 5, 45: 5, 46: 150, 47: 150, 48: 130, 49: 90, 50: 90, 51: 3, 52: 60,
    53: 50, 54: 40, 55: 40, 56: 30, 57: 30, 58: 22, 59: 22, 60: 14, 61: 14,
    62: 12, 63: 12, 64: 6, 65: 6, 66: 8, 67: 7,
}


def _sample_dem(Z, pts_mm):
    """Bilinear DEM sample, metres, for Nx2 ground-mm points."""
    cell = config.DEM_CELL_M * 1000.0
    ny, nx = Z.shape
    fx = np.clip(pts_mm[:, 0] / cell - 0.5, 0, nx - 1.001)
    fy = np.clip(pts_mm[:, 1] / cell - 0.5, 0, ny - 1.001)
    x0 = fx.astype(int); y0 = fy.astype(int)
    tx = fx - x0; ty = fy - y0
    return (Z[y0, x0] * (1 - tx) * (1 - ty) + Z[y0, x0 + 1] * tx * (1 - ty)
            + Z[y0 + 1, x0] * (1 - tx) * ty + Z[y0 + 1, x0 + 1] * tx * ty)


def write_master_dxf(path, profiles, boxes, Z, scale=1):
    """scale = 1 for 1:1, 500 for the 1:500 model."""
    k = 1.0 / scale
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4          # millimetres
    doc.header["$MEASUREMENT"] = 1
    msp = doc.modelspace()

    def layer(name, colour):
        if name not in doc.layers:
            doc.layers.add(name, color=colour)
        return name

    # --- contours as closed 3-D polylines -------------------------------
    for L in sorted(profiles):
        lay = layer(f"CONTOUR_{L}", LAYER_COLOUR.get(L, 7))
        z = L * 1000.0 * k
        for isl in profiles[L]:
            for ring in [isl["outer"]] + isl["holes"]:
                pts = [(x * k, y * k, z) for x, y in ring]
                msp.add_polyline3d(pts, dxfattribs={"layer": lay, "closed": True})

    # --- model boundary and base ----------------------------------------
    W, H = config.MODEL_W_M * 1000.0 * k, config.MODEL_H_M * 1000.0 * k
    lay = layer("MODEL_BOUNDARY", 7)
    msp.add_polyline3d([(0, 0, config.BASE_LEVEL * 1000.0 * k),
                        (W, 0, config.BASE_LEVEL * 1000.0 * k),
                        (W, H, config.BASE_LEVEL * 1000.0 * k),
                        (0, H, config.BASE_LEVEL * 1000.0 * k)],
                       dxfattribs={"layer": lay, "closed": True})

    # --- buildings, draped on the terrain --------------------------------
    kinds = [("raster", "BLDG_BOX_RASTER", 1, "BLDG_FOOTPRINT_RASTER", 12),
             ("campus", "BLDG_BOX_CAMPUS", 5, "BLDG_FOOTPRINT_CAMPUS", 8),
             ("platform", "BLDG_BOX_PLATFORM", 3, "BLDG_FOOTPRINT_PLATFORM", 94),
             ("water", None, None, "WATER", 4)]
    for kind, boxlay, boxcol, footlay, footcol in kinds:
        if boxlay:
            layer(boxlay, boxcol)
        layer(footlay, footcol)
        for e in boxes.get(kind, ()):
            for ring, lay_name in ((e.get("box_clip"), boxlay),
                                   (e.get("footprint_clip"), footlay)):
                if ring is None or lay_name is None:
                    continue
                zz = _sample_dem(Z, ring) * 1000.0 * k
                pts = [(x * k, y * k, float(z)) for (x, y), z in zip(ring, zz)]
                msp.add_polyline3d(pts, dxfattribs={"layer": lay_name, "closed": True})

    lay = layer("DATUM_BASE_TOP", 7)
    msp.add_point((0, 0, config.BASE_LEVEL * 1000.0 * k), dxfattribs={"layer": lay})

    doc.saveas(path)
    return path


def terrain_mesh(Z, step_m=2.0, scale=1, skirt=True):
    """Triangulated terrain surface (+ optional closed base) in millimetres."""
    cell = config.DEM_CELL_M
    stride = max(1, int(round(step_m / cell)))
    # always keep the last row/column so the mesh reaches the model edge
    ri = np.unique(np.append(np.arange(0, Z.shape[0], stride), Z.shape[0] - 1))
    ci = np.unique(np.append(np.arange(0, Z.shape[1], stride), Z.shape[1] - 1))
    S = Z[np.ix_(ri, ci)].astype(np.float64)
    ny, nx = S.shape
    k = 1.0 / scale
    x = (ci * cell + cell / 2.0) * 1000.0 * k
    y = (ri * cell + cell / 2.0) * 1000.0 * k
    x[0] = 0.0; y[0] = 0.0
    x[-1] = config.MODEL_W_M * 1000.0 * k
    y[-1] = config.MODEL_H_M * 1000.0 * k
    X, Y = np.meshgrid(x, y)
    ZZ = S * 1000.0 * k

    V = np.stack([X, Y, ZZ], axis=-1)
    tris = []
    a = V[:-1, :-1]; b = V[:-1, 1:]; c = V[1:, 1:]; d = V[1:, :-1]
    tris.append(np.stack([a, b, c], axis=-2).reshape(-1, 3, 3))
    tris.append(np.stack([a, c, d], axis=-2).reshape(-1, 3, 3))

    if skirt:
        z0 = config.BASE_LEVEL * 1000.0 * k
        edges = [(V[0, :], +1), (V[-1, :], -1), (V[:, 0], -1), (V[:, -1], +1)]
        for row, orient in edges:
            p0 = row[:-1]; p1 = row[1:]
            q0 = p0.copy(); q0[:, 2] = z0
            q1 = p1.copy(); q1[:, 2] = z0
            if orient > 0:
                tris.append(np.stack([p0, p1, q1], axis=-2))
                tris.append(np.stack([p0, q1, q0], axis=-2))
            else:
                tris.append(np.stack([p1, p0, q0], axis=-2))
                tris.append(np.stack([p1, q0, q1], axis=-2))
        c0 = np.array([x[0], y[0], z0]); c1 = np.array([x[-1], y[0], z0])
        c2 = np.array([x[-1], y[-1], z0]); c3 = np.array([x[0], y[-1], z0])
        tris.append(np.array([[c0, c2, c1], [c0, c3, c2]]))
    return np.vstack(tris)


def write_stl(path, tris, name=b"SHREYAS terrain"):
    n = len(tris)
    with open(path, "wb") as f:
        f.write(name.ljust(80, b" ")[:80])
        f.write(struct.pack("<I", n))
        v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
        nrm = np.cross(v1 - v0, v2 - v0)
        ln = np.linalg.norm(nrm, axis=1, keepdims=True)
        nrm = np.divide(nrm, np.where(ln == 0, 1, ln))
        buf = np.zeros((n, 12), dtype="<f4")
        buf[:, 0:3] = nrm; buf[:, 3:6] = v0; buf[:, 6:9] = v1; buf[:, 9:12] = v2
        raw = bytearray()
        b = buf.tobytes()
        for i in range(n):
            raw += b[i * 48:(i + 1) * 48] + b"\x00\x00"
        f.write(raw)
    return path
