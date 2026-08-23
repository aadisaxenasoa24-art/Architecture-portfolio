#!/usr/bin/env python3
"""
Full pipeline: source PDF -> validated terrain -> master 3-D files -> nested
4 ft x 4 ft cutting sheets at 1:500.

    python3 build.py [--pdf PATH] [--out DIR] [--cache DIR]
"""
import argparse
import csv
import os
import pickle
import time

import numpy as np

import config
import extract
import terrain
import profiles as prof
import buildings as bld
import emit3d
import nest as nesting
import emit_sheets
import emit_boxes
import preview

HERE = os.path.dirname(os.path.abspath(__file__))
DEF_PDF = os.path.join(HERE, "..", "source", config.PDF_SRC)
DEF_OUT = os.path.join(HERE, "..", "output")
DEF_CACHE = os.path.join(HERE, "..", ".cache")
TOOL_MM = 2.0


def step(msg):
    print(f"\n=== {msg} " + "=" * max(0, 66 - len(msg)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=DEF_PDF)
    ap.add_argument("--out", default=DEF_OUT)
    ap.add_argument("--cache", default=DEF_CACHE)
    ap.add_argument("--tool", type=float, default=TOOL_MM)
    ap.add_argument("--rebuild-dem", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.cache, exist_ok=True)
    t0 = time.time()

    step("1  extract vector geometry from the source PDF")
    src_pkl = os.path.join(a.cache, "src.pkl")
    if os.path.exists(src_pkl) and not a.rebuild_dem:
        src = pickle.load(open(src_pkl, "rb"))
        print(f"  cached: {len(src['paths'])} paths")
    else:
        paths, chains = extract.main(a.pdf, src_pkl)
        src = {"paths": paths, "chains": chains}
    paths, chains = src["paths"], src["chains"]

    step("2  attach validated elevations to every contour")
    lev = terrain.levelled_contours(chains)
    levels = sorted({l for l, _ in lev})
    print(f"  {len(lev)} contour chains, levels {levels[0]}-{levels[-1]} m "
          f"at {config.CONTOUR_INTERVAL_M:.0f} m interval")

    step("3  interpolate the DEM")
    dem_npy = os.path.join(a.cache, "dem.npy")
    if os.path.exists(dem_npy) and not a.rebuild_dem:
        Z = np.load(dem_npy)
        print(f"  cached: {Z.shape}  {Z.min():.2f}-{Z.max():.2f} m")
    else:
        Z, _ext = terrain.build_dem(lev)
        np.save(dem_npy, Z)
    print(f"  terrain {Z.min():.2f} - {Z.max():.2f} m over "
          f"{config.MODEL_W_M:.0f} x {config.MODEL_H_M:.0f} m")

    step("4  slice the layer profiles")
    P = prof.build_all(Z)
    P, dropped = prof.filter_manufacturable(P, tool_mm=a.tool)

    step("5  building footprints and roof out-to-out boxes")
    B = bld.build_boxes(paths)
    for kind, v in B.items():
        print(f"  {kind:9s}: {len(v):4d}")

    step("6  master 3-D files")
    for scale, tag in ((1, "1to1"), (config.SCALE, "1to500")):
        p = emit3d.write_master_dxf(os.path.join(a.out, f"MASTER_3D_{tag}.dxf"),
                                    P, B, Z, scale=scale)
        print(f"  {os.path.basename(p):32s} {os.path.getsize(p)/1e6:6.2f} MB")
        tris = emit3d.terrain_mesh(Z, step_m=2.0, scale=scale)
        p = emit3d.write_stl(os.path.join(a.out, f"MASTER_TERRAIN_{tag}.stl"), tris)
        print(f"  {os.path.basename(p):32s} {os.path.getsize(p)/1e6:6.2f} MB "
              f"({len(tris):,} triangles)")

    step("7  nest the cutting sheets on 4 ft x 4 ft board")
    extra = {"SITE_BOUNDARY": [config.pt_to_ground(s) for p in paths
                               if p["layer"] == "b_COLUMN" and p["rgb"] == (0, 0, 255)
                               for s in p["subs"] if len(s) >= 2]}
    parts = [nesting.base_part(P, B)] + nesting.make_parts(P, B, extra)
    sheets = nesting.nest(parts, verbose=False)
    used = sum(it["part"]["poly"].area for sh in sheets for it in sh["items"])
    print(f"  {len(parts)} parts -> {len(sheets)} sheets, "
          f"{used/1e6:.2f} m2 cut, {100*used/(len(sheets)*config.SHEET_MM**2):.1f}% utilisation")

    sd = os.path.join(a.out, "sheets_1to500")
    os.makedirs(sd, exist_ok=True)
    for f in os.listdir(sd):
        os.remove(os.path.join(sd, f))
    for i, sh in enumerate(sheets, 1):
        emit_sheets.write_sheet(os.path.join(sd, f"CNC_1to500_SHEET_{i:02d}.dxf"),
                                sh, i, len(sheets))
    emit_sheets.write_combined(os.path.join(a.out, "CNC_NEST_4x4ft_1to500_ALL.dxf"), sheets)
    with open(os.path.join(a.out, "CUT_LIST.csv"), "w", newline="") as f:
        csv.writer(f).writerows(emit_sheets.cut_list(sheets))

    pickle.dump({"parts": parts, "sheets": sheets, "dropped": dropped},
                open(os.path.join(a.cache, "nest.pkl"), "wb"))
    pickle.dump(B, open(os.path.join(a.cache, "boxes.pkl"), "wb"))
    pickle.dump(P, open(os.path.join(a.cache, "profiles.pkl"), "wb"))

    step("8  validate the emitted sheets")
    import glob
    import validate
    import validate_3d
    rep = validate.check(glob.glob(os.path.join(sd, "*.dxf")), verbose=False)
    master_errors = validate_3d.check_all(a.out)
    rep["errors"] += master_errors
    print(f"  {len(sheets)} cutting sheets: errors {len(rep['errors']) - len(master_errors)}, "
          f"warnings {len(rep['warnings'])}")
    print(f"  master 3-D files: errors {len(master_errors)}")
    for e in rep["errors"]:
        print("   ERROR:", e)
    for w in rep["warnings"]:
        print("   WARN :", w)

    step("9  roof out-to-out boxes as a standalone deliverable")
    rows = emit_boxes.all_boxes(paths)
    for scale, tag in ((1, "1to1"), (config.SCALE, "1to500")):
        p = emit_boxes.write_dxf(os.path.join(a.out, f"BUILDING_OUT_TO_OUT_{tag}.dxf"),
                                 rows, scale=scale)
        print(f"  {os.path.basename(p):38s} {os.path.getsize(p)/1e6:6.2f} MB")
    emit_boxes.write_schedule(os.path.join(a.out, "BUILDING_OUT_TO_OUT_SCHEDULE.csv"), rows)
    print(f"  {len(rows)} buildings scheduled "
          f"({sum(1 for r in rows if r['in_window'])} inside the model window)")

    step("10  preview images")
    docs = os.path.join(HERE, "..", "docs")
    os.makedirs(docs, exist_ok=True)
    preview.sheet_contact(sd, os.path.join(docs, "preview_sheets.png"))
    preview.single_sheet(os.path.join(sd, "CNC_1to500_SHEET_01.dxf"),
                         os.path.join(docs, "preview_sheet01.png"))
    preview.single_sheet(os.path.join(sd, "CNC_1to500_SHEET_08.dxf"),
                         os.path.join(docs, "preview_sheet08.png"))
    preview.model_preview(Z, B, os.path.join(docs, "preview_model.png"))
    preview.iso_preview(Z, os.path.join(docs, "preview_iso.png"))
    print("  5 images ->", os.path.abspath(docs))

    print(f"\ndone in {time.time()-t0:.0f}s -> {os.path.abspath(a.out)}")
    return 0 if not rep["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
