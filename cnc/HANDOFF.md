# HANDOFF BRIEF — SHREYAS 1:500 CNC terrain model
_Generated 2026-08-24. Paste into a new session and say "continue from this handoff."_

## 0. Resume instruction

The user is **Aadi Saxena** (aadi.saxena.soa24@anu.edu.in), a B.Arch student. He asked for a
CNC-cuttable contour model of the SHREYAS site in Ahmedabad, built from a DWG and a PDF he
uploaded. **The work is complete and pushed** — three commits on branch
`claude/cnc-model-4x4-1500-7kzowc` of `aadisaxenasoa24-art/Architecture-portfolio`, open as
draft PR #1. Everything lives in the `cnc/` folder of that repo, and in this zip.

On resume: nothing is blocked or half-finished. If he asks for changes, edit `cnc/src/*.py`
and re-run `cd cnc/src && python3 build.py` (~2 min with cache, ~5 min with `--rebuild-dem`);
it regenerates every output and validates its own files, exiting non-zero on any failure.
Read `cnc/README.md` and `cnc/docs/verification.md` first — they carry the full reasoning.

## 1. Objective

His words, verbatim, across three requests:

1. "This is the attached dwg as well as attached pdf for reference and refer to my old context
   for cnc cutting. Make me a cnc model for 4 by 4 feet to fit the file in scale of 1:500 with
   zero errors. Take the roof out to out box in plan of al the raster building. These contours
   are 1 meter interval make me the master 3d cnc file both in 1:1 and 1:500"
2. "Show me the 3d final file"
3. "show me the rhino 3d file , with cutouts sockets made and everything properly done"

"Done" = cut-ready files a model shop can run without interpretation, plus a master 3-D model
at both scales, plus a Rhino assembly with the cutouts and sockets actually made in solids.

## 2. Current state

**Everything requested is delivered, validated and pushed.** Pipeline runs clean end to end:
0 errors, 0 warnings across cutting sheets, master 3-D files and the Rhino assembly.

| | |
|---|---|
| Scale | 1:500 |
| Model | 1200 × 1080 × 50 mm (600 × 540 m of ground) |
| Sheet | 4 ft × 4 ft = 1219.2 mm |
| Board | 2.0 mm (1 m ÷ 500) |
| Levels | 44–67 m, 24 layers + base board at 43 m = 25 boards |
| Cutting sheets | 17, 16.10 m² cut, 63.7 % utilisation, 90.2 m cut path |
| Registration | 28 dowels, 3.0 mm rod in 3.2 mm holes, 430 holes |
| Building sockets | 41 cut, 252 engrave-only |
| Buildings | 319 scheduled, 294 inside the model window |

Nothing is in progress. Nothing is untouched.

## 3. Decisions locked in

**Ground scale — 661.630406 mm per PDF point.** Neither source file states a scale. Calibrated
on the basketball court that the DWG draws as exactly `30000 × 18000` mm, then verified to
**0.000 %** against six other known lengths (4500, 23500, 43543.03, 43966.94, 51500,
58881.47 mm). Cross-checks: the court's inner rectangle works out at 28.2 × 15.0 m (a FIBA
court) and the road beside it at exactly 6.00 m.

**The lat/long graticule is nominal and ~5 % off — flagged to the user, unresolved.** Its ticks
are spaced 158.361 pt per 0.001° in *both* axes, i.e. the map was laid out in EPSG:4326 with
degrees as equal units. Under that graticule 1 pt would be 0.647 m east-west but 0.699 m
north-south. The CAD geometry is isotropic and calibrated on a real object, so **the CAD scale
is used**. Worth resolving before anyone re-georeferences the drawing.

**Contour elevations 44–67 m — recovered, not given.** The contours were traced from a PDF; the
DWG layer is literally `PDF_contours` and every polyline sits at Z=0. Recovered three ways:
(a) 85 label clusters located as filled glyph groups and matched to the contour whose line
breaks around them (32 met a strict straddle test and were read directly); (b) a colour
adjacency chain — one colour per elevation — that reproduces every read anchor; (c) the seam
between the black (central hill) and coloured (periphery) contour sets, assigned from separate
evidence, which meet at **0.00 pt** at 56, 0.19 pt at 57, 0.00 pt at 58.

Colour → level map (in `config.COLOUR_LEVEL`), `*` = confirmed by a directly-read label:
```
44 (205,105,40)   45 (211,124,213)+(100,33,101)  46 (41,49,137)   47 (0,255,0)
48 (114,116,48)   49 (205,32,39)*                50 (69,84,165)*  51 (19,155,72)*
52 (200,201,45)*  53 (209,156,199)*              54 (254,204,102) 55 (34,52,110)
56 (242,113,114)  57 (122,175,223)               58 (88,186,72)*  59 (163,158,10)*
60 (247,171,174)* 61 (106,201,220)*              62 (224,189,103)*63 (255,0,255)
64 (176,42,229)*  65 (33,169,237)                66 (118,72,199)* 67 (112,215,184)
```
Black chains, indexed 0–8 in `config.BLACK_LEVEL`: 56, 57, 58, 59, 60, 60 (a second detached
lobe), 61, 62, 63. Level 67 is the only value with no label — the unlabelled innermost loop of
the SW summit, nested inside 66.

**Model window 600 × 540 m centred on the map frame.** The full mapped area is 632 × 542 m =
1263 mm wide at 1:500, which does not fit a 4 ft sheet. The window contains the entire site
boundary and every campus building; it trims ~16 m of far context from each side. User was told
this and did not object.

**DEM by harmonic (Laplace) interpolation**, 0.25 m grid, contours pinned as Dirichlet
constraints, solved coarse-to-fine. Sampled at all 43,647 source contour vertices: mean error
5.8 mm on the ground, p99.9 0.0428 m, max 0.2988 m, **zero vertices off by more than half a
contour interval**.

**Eight summit/hollow seeds**, each half an interval above/below the innermost closed loop, all
verified against the surrounding contour levels: 43.5 (hollow), 51.5 (hollow), 55.5, 60.5
(east lobe), 61.5, 62.5, 63.5 (central hill), 67.5 (SW summit). Half an interval can never
create a new contour, so cut profiles are unaffected — this only shapes the 3-D surface.

**Profiles sliced 1 mm below each integer level.** Slicing exactly on the level is degenerate
(the DEM is pinned to that value along the traced line, producing a speck of a loop around
every pinned cell). At a typical 1:20 slope the 1 mm offset moves the line 20 mm on the ground
= 0.04 mm at 1:500.

**Two slivers of the 61 m contour dropped** — 1.87 m² and 1.41 m² of ground (7.5 and 5.6 mm² on
the model), below what a 2 mm cutter can make.

**Dowel placement is exact, not eyeballed.** A contour stack is nested, so a point safely inside
a board is safely inside every board beneath it with at least as much clearance. Dowels are
placed top-down and each rod serves one continuous run, base board to the highest board that
holds it. 4.0 mm of material minimum at any edge; 28 mm minimum spacing. 43 of 46 cut pieces
pinned; the three that cannot take one are slivers of 72, 149 and 91 m² of ground.

**Sockets only where unambiguous.** A building socket is cut only where the whole out-to-out box
sits inside one visible terrace with 3 mm clearance and clear of every dowel by 3 mm. 41 of 293
qualify. The other 252 straddle a terrace edge and stay engrave-only. User was told 14 % is
lower than ideal but is what 1 m contours on sloping ground allow.

**No rotation-free nesting.** Parts may be rotated in 90° steps; every piece carries an engraved
north arrow, part id, level, dowel ids and the outline of the layer above, so orientation is
never in doubt.

**Building block height is an assumption, not data** — 9.0 m nominal, and the Rhino layer is
named `04_BUILDING_BLOCKS_nominal_9m` so it cannot be mistaken for survey data.

**1:1 Rhino file carries no boards or dowels.** At full size a 2 mm board is a 1 m slab and a
dowel a 1.5 m rod. `MASTER_3D_1to1.3dm` is reference geometry only. **User was offered an
×500-scaled assembly if he wants one — he has not answered.**

## 4. Active constraints & preferences

- "with zero errors" — he said it explicitly. Every generated file is read back off disk and
  validated; the build exits non-zero on failure. Keep that discipline.
- 1:500, 4 ft × 4 ft sheets, 1 m contour interval, 2.0 mm board. Not negotiable without asking.
- "roof out to out box in plan" = the overall enclosing rectangle in plan; for the L- and
  T-shaped campus blocks that is the minimum-area *oriented* bounding rectangle.
- Deliverables must be machine-ready, not just pretty: features that exist only in the 3-D model
  and not in the cutting files do not count as done.
- Assumptions must be visible in the artefact itself (layer names, captions), not buried.
- Do not overclaim in captions — a caption was corrected when it described rods the picture
  did not actually show.

## 5. Files & artifacts

All under `cnc/` in the repo and in this zip. **Branch `claude/cnc-model-4x4-1500-7kzowc`,
draft PR #1** — <https://github.com/aadisaxenasoa24-art/Architecture-portfolio/pull/1>

### Source (his uploads — carry these over, a new account will not have them)
| file | purpose |
|---|---|
| `cnc/source/26_08_22_SHREYAS_RASTER_WITH_CONTOURS.pdf` | **the authoritative source** — complete contour set + buildings, ZWCAD plot, 420 × 420 mm, layers preserved as OCGs |
| `cnc/source/shreyasplancncrefrence.dwg` | AutoCAD 2018 DWG — used only for scale calibration; its contour set is incomplete (55 black polylines, all Z=0) |
| `cnc/source/shreyasplancncrefrence_libredwg.dxf` | the DWG converted with LibreDWG WASM (`dwg2dxf-converter` on npm), kept for reference |

### Output
| file | what it is |
|---|---|
| `MASTER_ASSEMBLY_1to500.3dm` | **the fabrication model** — every board a closed Extrusion whose inner profiles are the terrain holes, dowel holes and sockets; plus 28 rods, 293 blocks, reference curves. 711 objects, 34 layers, mm |
| `MASTER_3D_1to1.3dm` | full-size reference: contours at true elevation per-metre layers, terrain mesh, footprints, boxes |
| `MASTER_3D_1to500.dxf` / `MASTER_3D_1to1.dxf` | contours as closed 3-D polylines at true Z, buildings draped. Exactly ×500 apart, checked |
| `MASTER_TERRAIN_1to500.stl` / `_1to1.stl` | terrain solid with skirt to the 43 m datum, 164,282 triangles, 2 m sampling |
| `sheets_1to500/CNC_1to500_SHEET_01..17.dxf` | the cutting sheets, origin at sheet corner |
| `CNC_NEST_4x4ft_1to500_ALL.dxf` | all 17 sheets side by side for checking |
| `CUT_LIST.csv` | 47 parts: sheet, id, level, rotation, size, area, perimeter, holes, dowel ids, sockets |
| `DOWEL_SCHEDULE.csv` | 28 rods: position, top board, boards pierced, rod length |
| `BUILDING_OUT_TO_OUT_1to500.dxf` / `_1to1.dxf` / `_SCHEDULE.csv` | 319 buildings: box, footprint, long/short side, bearing, area, centre, in-window flag |

### Docs
`README.md` (full build + assembly instructions), `docs/verification.md` (the evidence for every
recovered number), `docs/model-viewer.html` (self-contained WebGL viewer), plus preview PNGs:
`preview_model`, `preview_sheets`, `preview_3d`, `preview_assembly`, `preview_registration`,
`asm_assembled`, `asm_exploded`, `asm_detail`, `p3d_*`.

### Published artifact (his account only — a new account cannot update it)
Interactive viewer: <https://claude.ai/code/artifact/3716291a-3ba2-452a-94d6-feb3e022e4c4>
To update it from another conversation, pass that URL as `url` to the Artifact tool.

### Source code — `cnc/src/`
`config.py` (scale, window, level map, board), `extract.py` (PDF vectors, fragment re-join),
`terrain.py` (levels + DEM), `profiles.py` (slicing + manufacturability filter),
`buildings.py` (footprints, min-area boxes), `assembly.py` (dowels + sockets),
`emit3d.py` (master DXF/STL), `emit_3dm.py` (Rhino), `nest.py` (FFT raster nesting),
`emit_sheets.py`, `emit_boxes.py`, `stickfont.py` (single-stroke engraving font),
`validate.py`, `validate_3d.py`, `validate_3dm.py`, `render3d.py`, `render_3dm.py`,
`preview.py`, `make_previews_3d.py`, `make_previews_assembly.py`, `build.py` (driver).

`cnc/.cache/` is gitignored and **not in this zip** — `dem.npy`, `src.pkl`, `profiles.pkl`,
`boxes.pkl`, `assembly.pkl`, `nest.pkl`. Regenerate with `python3 build.py --rebuild-dem`.

## 6. Open threads / next steps

1. **Nothing is required.** The work is delivered. Wait for his direction.
2. **Unanswered offer:** whether he wants `MASTER_ASSEMBLY` also provided scaled ×500 (a 1:1
   version with 1 m thick "boards"). He has not replied.
3. **Unresolved, flagged to him:** the graticule/CAD scale discrepancy (~5 %). Only matters if
   the drawing is re-georeferenced.
4. Possible asks he might raise: hollow/ring cutting to cut material (currently solid plateaus,
   17 sheets); more building sockets; road linework engraved on the terraces (deliberately left
   out — not requested); a section/cutaway render (one was attempted and dropped, see §8);
   PR is still a **draft** and unmerged.

## 7. Key context to preserve

- Site: SHREYAS, Ahmedabad. Graticule 23.013–23.017 N, 72.537–72.542 E.
- Terrain 43.50–67.50 m. NW hollow (innermost 44), central hill (63), east lobe (60), a small
  east hollow (52), SW summit (67).
- `MM_PER_PT = 661.630406`. `BOARD_MM = 2.0`. `BASE_LEVEL = 43`. `LEVEL_MIN/MAX = 44/67`.
- `FRAME_CENTRE_PT = (605.23100, 520.12675)`; window in PDF points
  `[151.8056, 112.0439, 1058.6564, 928.2096]`.
- Dowels: `ROD_DIA 3.0`, `HOLE_DIA 3.2`, `EDGE_CLEAR 4.0`, `MIN_SPACING 28.0`.
- Sockets: `SOCKET_CLEAR 3.0`, `SOCKET_MIN_MM 6.0`.
- DXF sheet layers: `CUT_OUTER`, `CUT_INNER`, `CUT_DOWEL_3.2`, `CUT_SOCKET_BLDG`,
  `ENGRAVE_NEXT`, `ENGRAVE_BLDG_BOX`, `ENGRAVE_BLDG_FOOTPRINT`, `ENGRAVE_SITE_BOUNDARY`,
  `ENGRAVE_TEXT`, `ENGRAVE_NORTH`, `SHEET_EDGE`, `NOTES`.
- Rhino layers: `00_REFERENCE`, `01_BASE_BOARD`, `02_BOARDS_2mm/L44…L67`,
  `03_DOWEL_RODS_3.0mm`, `04_BUILDING_BLOCKS_nominal_9m`, `05_ROOF_OUT_TO_OUT_BOXES`.
- Python deps: `ezdxf numpy scipy shapely matplotlib pymupdf pillow rhino3dm mapbox_earcut`.
  DWG→DXF via npm `dwg2dxf-converter` (LibreDWG WASM). Rhino itself is **not** installed —
  the `.3dm` is authored directly through `rhino3dm` (openNURBS), and
  `Extrusion.SetOuterProfile` + `AddInnerProfile` give closed solids with holes, no booleans.
- Playwright browser is at `/opt/pw-browsers/chromium`; pass
  `executable_path="/opt/pw-browsers/chromium"` and swiftshader flags, or the pinned version
  mismatch breaks it.

## 8. Dead ends / things tried

- **GitHub is blocked** by the agent proxy (403). Only PyPI / npm are reachable. LibreDWG could
  not be built from source; the npm WASM wrapper was the way in.
- **`apt-get install libredwg-tools`** — package not available.
- **`aspose-cad`** was installed as a DWG reader and turned out unnecessary; the npm route won.
- **Reading contour elevations from the DWG** — impossible, every polyline is Z=0.
- **Naive dowel scoring** put pins 4.8 mm from board edges; fixed by raising `EDGE_CLEAR` to
  4.0 and eligibility-filtering candidates to the deeper half of each piece.
- **First peak/pit seed logic** tested containment against closed contours only and got the
  51.5 hollow backwards; replaced with a test against all contours plus a distance-transform
  interior point.
- **Marching squares exactly on the level** produced 122 speck holes at level 49; fixed by
  slicing 1 mm below.
- **First nesting attempt** used bounding boxes (19 sheets) and had two real bugs my own
  validator caught: the sheet margin was never applied, and `binary_dilation` was clipped to the
  part's own bbox so no clearance was enforced. Rewritten as FFT raster nesting → 17 sheets.
- **GLSL `smoothstep(0, 0.1, t)`** in the viewer — GLSL ES has no int overloads; all literals
  now go through `toFixed(5)`. Caught by running the page in headless Chromium.
- **A cutaway render** was produced by clipping triangles on centroid; it came out ragged with
  no cut faces and was **deleted rather than shipped**.
- **A detail render** clipped by triangle centroid sliced through boards and looked broken;
  replaced with whole-object filters (`level_range`, `keep_over`).
- **The `rhino-illustrator` skill** was loaded as instructed but assumes Rhino 8 on Windows
  driven headlessly — not available here. Its discipline was kept ("you cannot tell whether a
  drawing is right by reading a log — render it, look at it").
