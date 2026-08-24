# Verification record

Everything the model depends on that was *not* stated in the source files was
derived and then checked against independent evidence. This is the record.

---

## 1. Ground scale of the drawing

The PDF carries no scale bar and the DWG has no dimension entities, so the scale
had to be recovered from the geometry.

**Method.** The campus plan includes a basketball court. In the DWG
(`b_furniture_fittings`) that court's outer rectangle is a closed polyline whose
sides are exactly `30000.0` and `18000.0` drawing units — 30 m × 18 m, a court
plus run-off, drawn in millimetres at 1:1. The same rectangle in the PDF measures
45.34255 × 27.20548 points.

```
30000 / 45.34255 = 661.62994 mm per PDF point
18000 / 27.20548 = 661.63087 mm per PDF point
adopted            661.630406
```

**Independent checks.** Six further lengths that the DWG draws as round
millimetre values were predicted in PDF points and compared with the actual PDF
geometry:

| DWG length | predicted (pt) | measured (pt) | error |
|---|---|---|---|
| 4 500 mm | 6.8014 | 6.8014 | 0.000 % |
| 23 500 mm | 35.5183 | 35.5183 | 0.000 % |
| 43 543.03 mm | 65.8117 | 65.8117 | 0.000 % |
| 43 966.94 mm | 66.4524 | 66.4525 | 0.000 % |
| 51 500 mm | 77.8380 | 77.8380 | 0.000 % |
| 58 881.47 mm | 88.9945 | 88.9946 | 0.000 % |

Two more sanity checks fall out of it: the court's **inner** rectangle works out
at 28.2 × 15.0 m — a standard FIBA basketball court — and the road beside it is
exactly 6.00 m between kerb lines.

**A caveat worth knowing.** The drawing also carries a lat/long graticule
(23.013–23.017 N, 72.537–72.542 E — Ahmedabad). Its ticks are spaced
158.361 pt for 0.001° in **both** axes, which means the map was laid out in
EPSG:4326 with degrees treated as equal units. Under that graticule 1 pt would
be 0.647 m east-west but 0.699 m north-south. The CAD geometry is isotropic and
calibrated on a real object, so **the CAD scale above is the one used**; the
graticule is nominal and about 5 % off. If the drawing is ever re-georeferenced,
that is the discrepancy to resolve.

---

## 2. Contour elevations

The contour polylines carry no Z (the DWG layer is literally called
`PDF_contours` — they were traced from a PDF). Elevations were recovered and
then checked three independent ways.

**Where the data lives.** The contour set is split between a black portion over
the central hill and a coloured portion over the surrounding ground, one colour
per elevation. The two are spatially complementary — together they are one
contour set.

**Step 1 — read the labels.** The drawing's contour labels are stroked CAD text
converted to filled paths. 85 label clusters were located, and each was matched
to the contour whose line breaks around it (a pair of polyline endpoints
straddling the label, collinear with it). 32 of those matches met the strict
straddle test and were read directly.

**Step 2 — order the colours.** Every contour was densified and each sample
point matched to its nearest neighbour of a different colour, giving an
adjacency graph. The graph is a clean chain, and walking it from the anchors
reproduces every anchor exactly:

```
44 (205,105,40)   45 (211,124,213)+(100,33,101)   46 (41,49,137)   47 (0,255,0)
48 (114,116,48)   49 (205,32,39)*                 50 (69,84,165)*  51 (19,155,72)*
52 (200,201,45)*  53 (209,156,199)*               54 (254,204,102) 55 (34,52,110)
56 (242,113,114)  57 (122,175,223)                58 (88,186,72)*  59 (163,158,10)*
60 (247,171,174)* 61 (106,201,220)*               62 (224,189,103)*63 (255,0,255)
64 (176,42,229)*  65 (33,169,237)                 66 (118,72,199)* 67 (112,215,184)
```
`*` = confirmed by at least one directly-read label; 49, 52, 53, 62 by two or
three independent labels each, all agreeing.

**Step 3 — the black set, independently.** The nine black chains were labelled
by the same straddle test and read 56, 57, 58, 59, 60, 60 (a second, detached
lobe), 61, 62, 63.

**The cross-check that closes it.** The black and coloured sets were assigned
*separately*, by different evidence. Where they meet, their endpoints coincide:

| join | endpoint distance |
|---|---|
| black 56 ↔ coloured 56 | **0.00 pt** |
| black 57 ↔ coloured 57 | 0.19 pt (0.12 m) |
| black 58 ↔ coloured 58 | **0.00 pt** |

Two independently-derived assignments agreeing to zero at the seam is strong
evidence both are right. A hypsometric render of the full set
(`preview_model.png`) shows a smooth, monotonic gradient with no inversions.

Level 67 is the only value not carried by a label: it is the unlabelled
innermost loop of the south-west summit, nested inside 66.

---

## 3. Summits and hollows

A closed contour with nothing inside it is a summit or a hollow. Harmonic
interpolation would leave it dead flat, so the most-interior point of each such
loop (maximum of a distance transform, so it is genuinely inside even for
crescent shapes) is seeded half an interval above or below. Half an interval can
never create a new contour line, so the cut profiles are untouched — this only
affects the 3-D surface.

All eight were checked against the surrounding contour levels:

| seed | contours outward | reading |
|---|---|---|
| 43.5 | 44 → 45 → 46 → 47 | hollow ✓ |
| 51.5 | 52 → 53 → 54 | hollow ✓ |
| 55.5 | 55 → 54 → 53 | summit ✓ |
| 60.5 | 60 → 59 → 58 | summit ✓ (east lobe) |
| 61.5 | 61 → 60 → 59 → 58 | summit ✓ |
| 62.5 | 62 → 61 → 60 | summit ✓ |
| 63.5 | 63 → 62 | summit ✓ (central hill) |
| 67.5 | 67 → 66 → 65 → 64 | summit ✓ |

---

## 4. DEM fidelity

The DEM is a harmonic (Laplace) solve on a 2720 × 2480 grid at 0.25 m, with the
traced contours pinned as Dirichlet constraints, solved coarse-to-fine and then
cropped back to the model window.

Sampling the finished DEM at **every one of the 43 647 source contour vertices**
inside the window:

```
mean |dz|   0.0058 m      (5.8 mm on the ground, 0.012 mm at 1:500)
p99.9       0.0428 m
max         0.2988 m
vertices off by more than half a contour interval:  0
```

So the cut profiles sit on the traced lines, not near them.

---

## 5. Manufacturability

Profiles are sliced with marching squares 1 mm below each integer level. (Slicing
exactly *on* the level is degenerate, because the DEM is pinned to exactly that
value along the traced line, and it produces a speck of a loop around every
pinned cell. At a typical 1:20 slope the 1 mm offset moves the line 20 mm on the
ground — 0.04 mm at 1:500.)

Every island and hole is then eroded by half the tool diameter (2 mm at 1:500).
Two slivers of the 61 m contour do not survive and are dropped:

| dropped | ground area | on the model |
|---|---|---|
| island at 61 m | 1.87 m² | 7.5 mm² |
| island at 61 m | 1.41 m² | 5.6 mm² |

Nothing else in the model is below the tool size.

---

## 6. Output check

`src/validate.py` reads the emitted DXFs back off disk — it does not trust the
in-memory model — and checks every sheet for: open cut polylines, degenerate
polylines, self-intersecting rings, geometry outside the sheet margin,
overlapping parts, insufficient clearance between parts, holes that do not sit
inside exactly one profile, and profiles below tool size.

```
17 sheets   0 errors   0 warnings
minimum clearance between parts on a sheet: 10.1 mm (target 5 mm)
```

---

## 7. Registration and sockets

**Why the dowel runs are provably right.** A contour stack is nested: the region
at or above level *L* is a subset of the region at or above *L−1*. So a point
that sits inside a board with clearance *c* sits inside every board beneath it
with clearance at least *c*. Placement therefore only has to be checked at the
top of a run, and dowels are chosen top-down so a rod placed for a summit board
is reused free by everything below it.

```
28 dowels, 3.0 mm rod in 3.2 mm holes, 4.0 mm of material minimum at any edge
holes per board: 2 to 28        430 holes in total
46 cut pieces: 43 pinned, 3 too small to take a dowel
```

The three unpinned pieces are slivers of 72, 149 and 91 m² of ground (289, 596
and 365 mm² on the model). They are located by the outline engraved on the board
below them.

**Sockets.** A building socket is cut only where the whole out-to-out box sits
inside one visible terrace with 3 mm clearance and clear of every dowel by 3 mm.
41 of 293 boxes qualify; the rest straddle a terrace edge, where a socket would
be ambiguous, and stay engrave-only.

## 8. The Rhino assembly, checked

`src/validate_3dm.py` reopens `MASTER_ASSEMBLY_1to500.3dm` and checks it against
the plan — not against the writer's own variables:

- every Extrusion reports `IsSolid`
- every board is exactly 2.000 mm thick and sits at its own elevation
- **every one of the 430 dowel holes is present, in the right board of the run,
  at 3.2 mm** (a hole missing from any board in a run is an error)
- all 41 sockets are cut in the board the plan assigns them to
- each of the 28 rods is 3.0 mm, fits its 3.2 mm hole, and spans the base board
  to the top face of its top board
- nothing lies outside the 1200 × 1080 mm footprint

```
711 objects on 34 layers, units Millimeters
47 board solids   28 rods   293 blocks
every extrusion closed: True
bounding box  X 0.0..1200.0   Y 0.0..1080.0   Z 86.0..154.0 mm
ERRORS 0   WARNINGS 0
```

The assembly views in `docs/` are tessellated from the .3dm itself — outer
profile, hole profiles and path — so a feature missing from the file would be
missing from the picture.
