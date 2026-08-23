"""
Step 2 - attach a validated elevation to every contour, then turn the contour
set into a DEM by harmonic (Laplace) interpolation with the contours held as
Dirichlet constraints.

Why a DEM rather than stitching the traced polylines directly:  the source
polylines are broken wherever a label sits in the line, several are clipped by
the map neatline, and none of them are closed.  A CNC layer has to be a closed,
non-self-intersecting profile.  Re-contouring a DEM that is pinned to the
original lines gives closed, correctly nested profiles by construction, and the
same DEM is the 3-D surface for the master model.
"""
import numpy as np

import config


def levelled_contours(chains):
    """[(level_m, polyline_pt), ...] for every contour in the drawing."""
    out = []
    for rgb, level in config.COLOUR_LEVEL.items():
        for a in chains.get(rgb, ()):
            if _length(a) > 2.0:
                out.append((level, a))
    black = chains.get((0, 0, 0), [])
    for idx, level in config.BLACK_LEVEL.items():
        out.append((level, black[idx]))
    return out


def _length(a):
    return float(np.sum(np.hypot(np.diff(a[:, 0]), np.diff(a[:, 1]))))


def _densify(a, step):
    """Resample a polyline so consecutive points are at most `step` apart."""
    out = [a[0]]
    for i in range(len(a) - 1):
        d = float(np.hypot(*(a[i + 1] - a[i])))
        n = max(1, int(np.ceil(d / step)))
        for k in range(1, n + 1):
            out.append(a[i] + (a[i + 1] - a[i]) * (k / n))
    return np.asarray(out)


def _relax(z, fixed, sweeps, omega=1.9):
    """Red-black SOR on the Laplace equation; `fixed` cells are held."""
    free = ~fixed
    for _ in range(sweeps):
        for phase in (0, 1):
            m = np.zeros_like(free)
            m[1:-1, 1:-1] = True
            idx = (np.add.outer(np.arange(z.shape[0]), np.arange(z.shape[1])) % 2) == phase
            m &= idx & free
            avg = np.empty_like(z)
            avg[1:-1, 1:-1] = 0.25 * (z[:-2, 1:-1] + z[2:, 1:-1] + z[1:-1, :-2] + z[1:-1, 2:])
            z[m] += omega * (avg[m] - z[m])
    return z


def build_dem(levelled, verbose=True):
    """
    Returns (Z, extent) where Z[row, col] is elevation in metres, row 0 = south.
    extent is (x0, x1, y0, y1) in ground millimetres of the *cropped* window.
    """
    cell = config.DEM_CELL_M * 1000.0                      # mm
    margin = config.DEM_MARGIN_M * 1000.0
    W, H = config.MODEL_W_M * 1000.0, config.MODEL_H_M * 1000.0

    gx0, gy0 = -margin, -margin
    nx = int(round((W + 2 * margin) / cell))
    ny = int(round((H + 2 * margin) / cell))

    # --- rasterise the contours as constraints ---------------------------
    zmap = np.full((ny, nx), np.nan, dtype=np.float32)
    step_pt = cell / config.MM_PER_PT * 0.5                # ~half a cell
    for level, poly in levelled:
        g = config.pt_to_ground(_densify(poly, step_pt))
        col = np.round((g[:, 0] - gx0) / cell).astype(int)
        row = np.round((g[:, 1] - gy0) / cell).astype(int)
        ok = (col >= 0) & (col < nx) & (row >= 0) & (row < ny)
        zmap[row[ok], col[ok]] = level

    # --- peak / pit enforcement -----------------------------------------
    # A closed loop with nothing inside it is a summit or a hollow.  Left alone
    # the harmonic solve makes it dead flat; nudging the middle by half an
    # interval keeps the 3-D surface honest without inventing a new contour.
    for level, seed in _extrema_seeds(levelled):
        col = int(round((seed[0] - gx0) / cell))
        row = int(round((seed[1] - gy0) / cell))
        if 0 <= col < nx and 0 <= row < ny:
            zmap[max(0, row - 1):row + 2, max(0, col - 1):col + 2] = level

    fixed = ~np.isnan(zmap)
    if verbose:
        print(f"DEM grid {nx} x {ny} @ {config.DEM_CELL_M} m   "
              f"constrained cells {fixed.sum():,} ({100*fixed.mean():.2f} %)")

    # --- progressive multigrid Laplace solve ------------------------------
    z = _solve_multigrid(zmap, fixed, verbose=verbose)

    # --- crop away the margin --------------------------------------------
    m = int(round(margin / cell))
    z = z[m:ny - m, m:nx - m]
    return z.astype(np.float32), (0.0, W, 0.0, H)


def _extrema_seeds(levelled):
    """
    Summits and hollows: closed loops with no other contour inside them.

    Left alone the harmonic solve makes the inside of the innermost loop dead
    flat.  Seeding the most-interior point half an interval above (summit) or
    below (hollow) keeps the 3-D surface honest.  Half an interval can never
    create a new contour line, so the cut profiles are unaffected.
    """
    from matplotlib.path import Path
    from scipy import ndimage

    closed = [(lv, p) for lv, p in levelled
              if len(p) > 8 and np.hypot(*(p[-1] - p[0])) < 2.0]
    seeds = []
    for level, poly in closed:
        path = Path(poly)
        # innermost?  no *other* contour of any kind may have a point inside
        if any(other is not poly and path.contains_points(other).any()
               for _lv, other in levelled):
            continue
        # summit or hollow?  compare with the nearest contour of another level
        best, best_lv = None, None
        c = poly.mean(axis=0)
        for lv2, other in levelled:
            if other is poly or lv2 == level:
                continue
            d = float(np.hypot(other[:, 0] - c[0], other[:, 1] - c[1]).min())
            if best is None or d < best:
                best, best_lv = d, lv2
        rising = best_lv is None or best_lv < level
        seeds.append((level + (0.5 if rising else -0.5),
                      config.pt_to_ground(_interior_point(poly)[None, :])[0]))
    return seeds


def _interior_point(poly, n=140):
    """Most-interior point of a closed polyline (max of the distance transform)."""
    from matplotlib.path import Path
    from scipy import ndimage
    x0, y0 = poly.min(axis=0)
    x1, y1 = poly.max(axis=0)
    gx = np.linspace(x0, x1, n)
    gy = np.linspace(y0, y1, n)
    GX, GY = np.meshgrid(gx, gy)
    inside = Path(poly).contains_points(np.column_stack([GX.ravel(), GY.ravel()]))
    mask = inside.reshape(GX.shape)
    if not mask.any():
        return poly.mean(axis=0)
    dt = ndimage.distance_transform_edt(mask)
    r, c = np.unravel_index(int(np.argmax(dt)), dt.shape)
    return np.array([gx[c], gy[r]])


def _solve_multigrid(zmap, fixed, verbose=True):
    """Solve coarse first, then refine - far faster than relaxing at full size."""
    ny, nx = zmap.shape
    levels = []
    cz, cf = zmap.copy(), fixed.copy()
    while min(cz.shape) > 40:
        levels.append((cz, cf))
        cz, cf = _coarsen(cz, cf)
    levels.append((cz, cf))

    z = np.where(levels[-1][1], np.nan_to_num(levels[-1][0]),
                 np.nanmean(zmap))
    z = _relax(z.astype(np.float64), levels[-1][1], 400)

    for k in range(len(levels) - 2, -1, -1):
        tz, tf = levels[k]
        z = _upsample(z, tz.shape)
        z[tf] = tz[tf]
        sweeps = 60 if k > 1 else (150 if k == 1 else 260)
        z = _relax(z, tf, sweeps)
        if verbose:
            print(f"   level {k}: {tz.shape[1]} x {tz.shape[0]}  ({sweeps} sweeps)")
    return z


def _coarsen(z, f):
    ny, nx = z.shape
    ny2, nx2 = ny // 2, nx // 2
    zz = np.full((ny2, nx2), np.nan)
    ff = np.zeros((ny2, nx2), dtype=bool)
    for dy in (0, 1):
        for dx in (0, 1):
            sub = z[dy:ny2 * 2:2, dx:nx2 * 2:2]
            m = ~np.isnan(sub) & np.isnan(zz)
            zz[m] = sub[m]
    ff = ~np.isnan(zz)
    return zz, ff


def _upsample(z, shape):
    out = np.repeat(np.repeat(z, 2, axis=0), 2, axis=1)
    return out[:shape[0], :shape[1]].copy() if out.shape >= shape else _pad(out, shape)


def _pad(a, shape):
    out = np.zeros(shape)
    out[:a.shape[0], :a.shape[1]] = a
    if a.shape[0] < shape[0]:
        out[a.shape[0]:, :] = out[a.shape[0] - 1, :]
    if a.shape[1] < shape[1]:
        out[:, a.shape[1]:] = out[:, a.shape[1] - 1][:, None]
    return out
