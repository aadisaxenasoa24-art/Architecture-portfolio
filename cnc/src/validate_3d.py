"""
Independent check of the master 3-D files, read back off disk.

Confirms that every contour polyline is closed, that each one sits at exactly
its own elevation, that the two scales really are a factor of 500 apart, and
that the STL covers the whole model window.
"""
import collections
import struct

import ezdxf
import numpy as np

import config


def check_master_dxf(path, scale):
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    errors = []
    counts = collections.Counter()
    z_by_layer = collections.defaultdict(set)
    pts = []
    for e in msp:
        counts[e.dxf.layer] += 1
        if e.dxftype() != "POLYLINE":
            continue
        a = np.array([(p[0], p[1], p[2]) for p in e.points()])
        pts.append(a)
        if e.dxf.layer.startswith("CONTOUR_"):
            if not e.is_closed:
                errors.append(f"{e.dxf.layer}: open contour polyline")
            z_by_layer[e.dxf.layer].add(round(float(a[0, 2]), 6))
            if abs(a[:, 2].max() - a[:, 2].min()) > 1e-6:
                errors.append(f"{e.dxf.layer}: polyline is not level")

    for lay, zs in z_by_layer.items():
        L = int(lay.split("_")[1])
        want = L * 1000.0 / scale
        if len(zs) != 1:
            errors.append(f"{lay}: {len(zs)} different Z values")
        elif abs(next(iter(zs)) - want) > 1e-6:
            errors.append(f"{lay}: Z = {next(iter(zs))}, expected {want}")

    A = np.vstack(pts)
    W = config.MODEL_W_M * 1000.0 / scale
    H = config.MODEL_H_M * 1000.0 / scale
    if abs(A[:, 0].min()) > 1e-6 or abs(A[:, 0].max() - W) > 1e-3:
        errors.append(f"X extent {A[:,0].min():.3f}..{A[:,0].max():.3f}, expected 0..{W}")
    if abs(A[:, 1].min()) > 1e-6 or abs(A[:, 1].max() - H) > 1e-3:
        errors.append(f"Y extent {A[:,1].min():.3f}..{A[:,1].max():.3f}, expected 0..{H}")
    if doc.header["$INSUNITS"] != 4:
        errors.append("units are not millimetres")

    return {"path": path, "entities": sum(counts.values()),
            "contour_layers": len(z_by_layer),
            "z_min": float(A[:, 2].min()), "z_max": float(A[:, 2].max()),
            "errors": errors}


def check_stl(path, scale):
    with open(path, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        raw = np.frombuffer(f.read(n * 50), dtype=np.uint8).reshape(n, 50)
    v = raw[:, 12:48].copy().view("<f4").reshape(n, 3, 3)
    errors = []
    W = config.MODEL_W_M * 1000.0 / scale
    H = config.MODEL_H_M * 1000.0 / scale
    if abs(v[:, :, 0].max() - W) > 0.5 / scale * 1000 or v[:, :, 0].min() < -1e-3:
        errors.append(f"STL X extent {v[:,:,0].min():.2f}..{v[:,:,0].max():.2f}, expected 0..{W}")
    if abs(v[:, :, 1].max() - H) > 0.5 / scale * 1000 or v[:, :, 1].min() < -1e-3:
        errors.append(f"STL Y extent {v[:,:,1].min():.2f}..{v[:,:,1].max():.2f}, expected 0..{H}")
    base = config.BASE_LEVEL * 1000.0 / scale
    if abs(v[:, :, 2].min() - base) > 1e-3:
        errors.append(f"STL base at {v[:,:,2].min():.3f}, expected {base}")
    return {"path": path, "triangles": n, "errors": errors}


def check_all(out_dir, verbose=True):
    import os
    errors = []
    rows = []
    for scale, tag in ((1, "1to1"), (config.SCALE, "1to500")):
        r = check_master_dxf(os.path.join(out_dir, f"MASTER_3D_{tag}.dxf"), scale)
        rows.append(r)
        errors += [f"MASTER_3D_{tag}.dxf: {e}" for e in r["errors"]]
        s = check_stl(os.path.join(out_dir, f"MASTER_TERRAIN_{tag}.stl"), scale)
        rows.append(s)
        errors += [f"MASTER_TERRAIN_{tag}.stl: {e}" for e in s["errors"]]

    # the two scales must be an exact factor of 500 apart
    a, b = rows[0], rows[2]
    if abs(a["z_min"] / config.SCALE - b["z_min"]) > 1e-6 or \
       abs(a["z_max"] / config.SCALE - b["z_max"]) > 1e-6:
        errors.append("the 1:1 and 1:500 masters are not an exact factor of 500 apart")

    if verbose:
        for r in rows:
            import os as _os
            name = _os.path.basename(r["path"])
            if "triangles" in r:
                print(f"  {name:32s} {r['triangles']:,} triangles")
            else:
                print(f"  {name:32s} {r['entities']} entities, "
                      f"{r['contour_layers']} contour layers, "
                      f"Z {r['z_min']:.3f}..{r['z_max']:.3f}")
    return errors
