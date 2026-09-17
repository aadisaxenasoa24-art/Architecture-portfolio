# Ahmedabad Management Association — CAD drawing set

**Ahmedabad Management Association**, ATIRA Campus, Dr Vikram Sarabhai Marg, Ahmedabad
Original architects: **HCP Design, Planning & Management** (Bimal Patel), completed 1999–2001
World Architecture Award 2001 (education category); ar+d High Commendation 2001

---

## Read this first

**This is a dimensional reconstruction, not a measured survey.**

HCP has never publicly released dimensioned drawings of AMA. Every accessible
source — HCP's own project page, World-Architects, Indian-Architects, Archnet —
carries the same descriptive paragraph plus photographs, and no plan or section
with dimensions on it. Nothing in the public record would let anyone reproduce
the built fabric to the millimetre.

So this set does the next best thing, and says so openly:

- It reproduces **every published quantity** about the building (see the table
  below) to within 0.2%.
- It resolves everything else onto a **documented structural grid**, chosen for
  being the standard Indian institutional RCC module and consistent with the
  published description.
- Every number is tagged in `ama_params.py` as `[PUB]` published, `[DER]`
  derived, or `[ASM]` assumed, so you can see exactly which dimensions are
  evidence and which are reasoning.

What *is* exact: the file is internally perfect. Every vertex is a whole
number of millimetres, the grid is exact, the ramp gradient is exactly 1:12,
and the auditorium holds exactly 250 seats. That is verified on every build by
`validate.py`, which fails the build if it is not true.

Use it as a studio base drawing, a case-study armature or a teaching model.
Do not use it for construction, and do not present it as HCP's drawing.

---

## Published facts, and what the model does with them

| Published                          | Source        | Modelled                     | Deviation |
|------------------------------------|---------------|------------------------------|-----------|
| Built-up area 4 180 m²             | HCP           | 4 173.60 m²                  | −0.15%    |
| Site 3 acres                       | HCP           | 12 140.52 m² = 3.0000 acres  | ±0.00%    |
| 2 storeys                          | HCP           | GF +0.900, FF +5.400         | exact     |
| Auditorium 250 seats               | HCP           | 250 (10 rows × 25)           | exact     |
| 8 existing neem trees              | HCP           | 8 @ 12 000 mm centres        | exact     |
| Cast in-situ exposed concrete bar  | HCP           | RCC frame, 400 × 700 columns | —         |
| Double-height ceremonial foyer     | HCP           | 3 bays, +0.900 to roof       | —         |
| Processional ramp to first floor   | HCP           | 4 flights, exactly 1:12      | —         |
| GF: classrooms, seminar halls, boardroom, bookshop | HCP | all present      | —         |
| FF: library, exhibition, auditorium | HCP          | all present                  | —         |

---

## The file

**`AMA_Ahmedabad_HCP.dxf`** — DXF `AC1032` (AutoCAD 2018 format), millimetres,
model space at 1:1, 2 870 entities on 34 layers, 9 composed paper-space sheets.

### Why DXF and not DWG

DWG is Autodesk's closed binary format. Writing it requires either AutoCAD
itself or Open Design Alliance libraries, and this build environment's network
policy blocks every host that serves them (`opendesign.com`, `github.com` and
the GNU mirrors all return 403 or time out; `libredwg-tools` is not in the
distribution repositories). Rather than ship a DXF renamed `.dwg` — which is a
broken file that AutoCAD will refuse — the set ships as a valid DXF.

**To get a DWG, open the file in AutoCAD and `SAVEAS` → `AutoCAD 2018 Drawing
(*.dwg)`.** That is one step and lossless: AutoCAD reads DXF natively, and
layers, dimension styles, hatches and layouts all carry across. The free ODA
File Converter does the same in batch if you prefer.

### Sheets

| Sheet  | Drawing                       | Paper | Scale |
|--------|-------------------------------|-------|-------|
| AMA-01 | Site plan                     | A1    | 1:500 |
| AMA-02 | Ground floor plan             | A0    | 1:100 |
| AMA-03 | First floor plan              | A0    | 1:100 |
| AMA-04 | Roof plan                     | A1    | 1:200 |
| AMA-05 | Section A-A (longitudinal)    | A0    | 1:100 |
| AMA-06 | Sections B-B and C-C          | A0    | 1:100 |
| AMA-07 | North and south elevations    | A0    | 1:100 |
| AMA-08 | East and west elevations      | A0    | 1:100 |
| AMA-09 | Project data and assumptions  | A1    | 1:100 |

Each viewport is centred on the measured bounding box of what it frames, and
the build asserts the content fits — a drawing cannot be silently clipped.

### Layers

34 layers on an AIA/BS 1192 pattern, each with its own colour, linetype and
lineweight: `A-GRID`, `S-COLS`, `A-WALL-EXTR`, `A-WALL-INTR`, `A-GLAZ`,
`A-DOOR`, `A-FLOR-RAMP`, `A-FLOR-STRS`, `A-FURN-SEAT`, `A-LOUV`, `A-SECT-CUT`,
`A-SECT-BYND`, `A-ANNO-DIMS`, `A-ANNO-TEXT`, `C-SITE-BDRY`, `L-PLNT-TREE` and
so on. Structure, fabric, annotation and site are fully separable.

---

## The geometry

```
Grid          13 bays @ 7 200          = 93 600 mm longitudinal (gridlines 1–14)
              7 200 / 7 200 / 4 200    = 18 600 mm transverse   (gridlines A–D)
              + 1 800 cantilever each long face
Footprint     94 000 × 22 200 mm
Levels        ±0.000 site · +0.900 GF · +5.400 FF · +9.900 roof · +10.950 parapet
              auditorium volume raised: +12.300 roof · +13.350 parapet
Structure     400 × 700 columns · 150 slab · 300 × 600 beams
Ramp          4 flights × 13 500 mm at exactly 1:12, 1 125 mm rise each
Auditorium    10 rows × 25 seats = 250, 550 seat width, 950 row spacing
```

---

## Rebuilding and editing

```bash
pip install ezdxf
python3 cad/ama_build.py      # writes the DXF
python3 cad/validate.py       # 25 checks; non-zero exit if any fails
python3 cad/render_preview.py # PNG previews of every drawing
```

| File                | Purpose |
|---------------------|---------|
| `ama_params.py`     | Every dimension, with provenance. **Edit here.** |
| `ama_draft.py`      | Layer standard, text and dimension styles, primitives |
| `ama_build.py`      | The drawings and sheet composition |
| `validate.py`       | Verifies published figures, integer millimetres, file structure |
| `render_preview.py` | PNG previews |

Because the geometry is generated rather than hand-drawn, correcting it is
cheap: **if you obtain real dimensions from HCP, change the `[ASM]` values in
`ama_params.py` and re-run.** The whole set regenerates consistently, and
`validate.py` will tell you if anything no longer fits.

---

## Sources

- [HCP — Ahmedabad Management Association](https://hcp.co.in/architecture/58)
- [World-Architects — Ahmedabad Management Association](https://www.world-architects.com/en/hcpdpm-ahmedabad/project/ahmedabad-management-association)
- [Indian-Architects — HCPDPM](https://indian-architects.com/en/hcpdpm-ahmedabad/project/ahmedabad-management-association)
- [Archnet — HCP Design & Project Management](https://www.archnet.org/authorities/2132)
- [Bimal Patel — Wikipedia](https://en.wikipedia.org/wiki/Bimal_Patel_(architect))
