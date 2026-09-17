"""
Drafting infrastructure for the AMA drawing set:
layer standard, text styles, dimension styles and primitive helpers.

All model-space geometry is in MILLIMETRES at 1:1.
"""

import ezdxf
from ezdxf.enums import TextEntityAlignment as TA
from ezdxf.tools import pattern as _pattern

# Standard ACAD hatch pattern definitions, embedded so that the file renders
# identically in AutoCAD, BricsCAD, DraftSight and open-source viewers.
_PATTERNS = _pattern.load(measurement=1)

# =============================================================================
# LAYER STANDARD  (AIA / BS 1192 flavoured)
# name, ACI colour, linetype, lineweight (1/100 mm), description
# =============================================================================
LAYERS = [
    ("A-GRID",          8,   "DASHDOT",    13,  "Structural grid lines"),
    ("A-GRID-IDEN",     8,   "Continuous", 13,  "Grid bubbles and references"),
    ("S-COLS",          1,   "Continuous", 50,  "RCC columns - cut"),
    ("S-COLS-PATT",   254,   "Continuous",  9,  "Column poche"),
    ("S-BEAM",          5,   "DASHED",     18,  "Beams over - dashed"),
    ("A-WALL-EXTR",     7,   "Continuous", 50,  "External walls - cut"),
    ("A-WALL-INTR",     7,   "Continuous", 35,  "Internal partitions - cut"),
    ("A-WALL-PATT",   253,   "Continuous",  9,  "Wall poche"),
    ("A-SLAB-EDGE",     7,   "Continuous", 35,  "Slab edge / building outline"),
    ("A-GLAZ",          4,   "Continuous", 25,  "Glazing and curtain walling"),
    ("A-DOOR",          2,   "Continuous", 25,  "Doors and swings"),
    ("A-FLOR-STRS",     3,   "Continuous", 25,  "Stairs"),
    ("A-FLOR-RAMP",     3,   "Continuous", 25,  "Processional ramp"),
    ("A-FLOR-LEVL",     6,   "Continuous", 18,  "Level change / floor markers"),
    ("A-FLOR-OTLN",     9,   "DASHED",     18,  "Voids and outlines over"),
    ("A-LOUV",         30,   "Continuous", 25,  "Concrete brise-soleil"),
    ("A-ROOF",         30,   "Continuous", 35,  "Roof construction"),
    ("A-FURN",          9,   "Continuous", 13,  "Loose furniture"),
    ("A-FURN-SEAT",     9,   "Continuous", 13,  "Auditorium seating"),
    ("A-SECT-CUT",      7,   "Continuous", 70,  "Section cut line - heavy"),
    ("A-SECT-BYND",     8,   "Continuous", 13,  "Seen beyond the cut"),
    ("A-SECT-GRND",     8,   "Continuous", 50,  "Ground / earth in section"),
    ("A-SECT-PATT",   254,   "Continuous",  9,  "Earth and concrete poche"),
    ("A-ELEV",          7,   "Continuous", 25,  "Elevation lines"),
    ("A-ELEV-FINE",     8,   "Continuous", 13,  "Elevation secondary lines"),
    ("A-ANNO-DIMS",     2,   "Continuous", 13,  "Dimensions"),
    ("A-ANNO-TEXT",     7,   "Continuous", 18,  "Room names and notes"),
    ("A-ANNO-TITL",     7,   "Continuous", 35,  "Drawing titles"),
    ("A-ANNO-SYMB",     6,   "Continuous", 18,  "Section marks, north point, levels"),
    ("A-ANNO-TTLB",     7,   "Continuous", 35,  "Sheet border and title block"),
    ("C-SITE-BDRY",     6,   "PHANTOM",    50,  "Site boundary"),
    ("C-SITE-PATH",     9,   "Continuous", 18,  "Paths, promenade, roads"),
    ("C-SITE-PATT",   252,   "Continuous",  9,  "Paving hatch"),
    ("L-PLNT-TREE",     3,   "Continuous", 25,  "Existing neem trees"),
    ("DEFPOINTS",       7,   "Continuous",  0,  "Non-plotting construction"),
]

TXT_NOTE = "AMA-NOTE"
TXT_TITLE = "AMA-TITLE"

# Text heights, MODEL units (mm). Chosen so that at 1:100 they print correctly.
H_ROOM = 250        # 2.5 mm @ 1:100
H_SMALL = 180       # 1.8 mm @ 1:100
H_TITLE = 500       # 5.0 mm @ 1:100
H_GRID = 300
H_LEVEL = 200


def new_document():
    """Create the DXF document with the full AMA standard loaded."""
    doc = ezdxf.new("R2018", setup=True)

    # --- drawing units: millimetres -----------------------------------------
    doc.units = ezdxf.units.MM
    doc.header["$INSUNITS"] = 4        # 4 = millimetres
    doc.header["$MEASUREMENT"] = 1     # metric
    doc.header["$LUNITS"] = 2          # decimal
    doc.header["$LUPREC"] = 0          # whole millimetres
    doc.header["$AUNITS"] = 0
    doc.header["$AUPREC"] = 2
    doc.header["$LTSCALE"] = 50        # suits mm geometry plotted at 1:100
    doc.header["$PSLTSCALE"] = 1
    doc.header["$CELTSCALE"] = 1.0
    doc.header["$DIMASSOC"] = 2

    # --- text styles ---------------------------------------------------------
    doc.styles.add(TXT_NOTE, font="romans.shx").dxf.width = 0.85
    doc.styles.add(TXT_TITLE, font="romand.shx").dxf.width = 0.90

    # --- layers --------------------------------------------------------------
    for name, color, ltype, lw, desc in LAYERS:
        if name in doc.layers:                 # e.g. DEFPOINTS from setup=True
            lay = doc.layers.get(name)
            lay.dxf.color = color
            lay.dxf.linetype = ltype
        else:
            lay = doc.layers.add(name, color=color, linetype=ltype)
        lay.dxf.lineweight = lw
        lay.description = desc
    doc.layers.get("DEFPOINTS").dxf.plot = 0

    # --- dimension styles ----------------------------------------------------
    for scale in (50, 100, 200, 500):
        _make_dimstyle(doc, f"AMA-{scale}", scale)

    return doc


def _make_dimstyle(doc, name, scale):
    """Architectural dimension style: oblique ticks, mm, no decimals."""
    ds = doc.dimstyles.add(name)
    d = ds.dxf
    d.dimscale = scale        # everything below is in PAPER mm
    d.dimtxt = 2.5            # text height on paper
    d.dimtsz = 1.0            # oblique tick size (replaces arrowheads)
    d.dimexe = 1.25           # extension line beyond dim line
    d.dimexo = 2.0            # extension line offset from origin
    d.dimgap = 1.0
    d.dimdli = 8.0            # baseline spacing
    d.dimtad = 1              # text above the dimension line
    d.dimjust = 0
    d.dimtih = 0              # text aligned with dim line
    d.dimtoh = 0
    d.dimdec = 0              # whole millimetres
    d.dimlunit = 2            # decimal
    d.dimzin = 8              # suppress trailing zeros
    d.dimlfac = 1.0           # model units are already mm
    d.dimclrd = 8
    d.dimclre = 8
    d.dimclrt = 7
    d.dimtxsty = TXT_NOTE
    return ds


# =============================================================================
# PRIMITIVE HELPERS
# =============================================================================

class Sheet:
    """A translated drawing frame in model space.

    All coordinates passed to a Sheet are LOCAL to the drawing; the offset is
    added on the way out. This keeps every drawing authored from its own
    natural origin while composing the whole set in one model space.
    """

    def __init__(self, msp, origin=(0, 0)):
        self.msp = msp
        self.ox, self.oy = origin

    # -- coordinate transform -------------------------------------------------
    # Every ordinate leaving a Sheet is snapped to a whole millimetre. All
    # governing dimensions are even, so for structural geometry this is an
    # identity; it exists to stop incidental annotation maths (midpoints,
    # trigonometry, divided spacings) from introducing fractional vertices.
    def p(self, x, y):
        return (int(round(self.ox + x)), int(round(self.oy + y)))

    def pts(self, seq):
        return [(int(round(self.ox + x)), int(round(self.oy + y)))
                for x, y in seq]

    # -- linework -------------------------------------------------------------
    def line(self, layer, x1, y1, x2, y2, **kw):
        return self.msp.add_line(self.p(x1, y1), self.p(x2, y2),
                                 dxfattribs={"layer": layer, **kw})

    def pline(self, layer, points, close=False, **kw):
        return self.msp.add_lwpolyline(
            self.pts(points), close=close,
            dxfattribs={"layer": layer, **kw})

    def rect(self, layer, x0, y0, x1, y1, **kw):
        return self.pline(layer,
                          [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                          close=True, **kw)

    def circle(self, layer, cx, cy, r, **kw):
        return self.msp.add_circle(self.p(cx, cy), int(round(r)),
                                   dxfattribs={"layer": layer, **kw})

    def arc(self, layer, cx, cy, r, a0, a1, **kw):
        return self.msp.add_arc(self.p(cx, cy), int(round(r)), a0, a1,
                                dxfattribs={"layer": layer, **kw})

    # -- fills ----------------------------------------------------------------
    def solid(self, layer, points, color=None):
        h = self.msp.add_hatch(dxfattribs={"layer": layer})
        if color is not None:
            h.dxf.color = color
        h.paths.add_polyline_path(self.pts(points), is_closed=True)
        return h

    def solid_rect(self, layer, x0, y0, x1, y1, color=None):
        return self.solid(layer,
                          [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], color)

    def pattern(self, layer, points, name="ANSI31", scale=200, angle=0,
                color=None):
        h = self.msp.add_hatch(dxfattribs={"layer": layer})
        if color is not None:
            h.dxf.color = color
        defn = _PATTERNS.get(name)
        if defn is not None:
            h.set_pattern_fill(name, definition=defn, scale=scale, angle=angle)
        else:
            h.set_pattern_fill(name, scale=scale, angle=angle)
        h.paths.add_polyline_path(self.pts(points), is_closed=True)
        return h

    def pattern_rect(self, layer, x0, y0, x1, y1, **kw):
        return self.pattern(layer,
                            [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], **kw)

    # -- text -----------------------------------------------------------------
    def text(self, layer, s, x, y, h=H_ROOM, align=TA.MIDDLE_CENTER,
             rot=0, style=TXT_NOTE):
        t = self.msp.add_text(
            s, height=h,
            dxfattribs={"layer": layer, "style": style, "rotation": rot})
        t.set_placement(self.p(x, y), align=align)
        return t

    def mtext(self, layer, lines, x, y, h=H_ROOM, leading=1.6, rot=0,
              align=TA.MIDDLE_CENTER, style=TXT_NOTE):
        """Multi-line text drawn as stacked TEXT entities (maximum
        compatibility across CAD platforms)."""
        rows = lines.split("\n")
        step = h * leading
        y0 = y + (len(rows) - 1) * step / 2.0
        out = []
        for i, row in enumerate(rows):
            out.append(self.text(layer, row, x, y0 - i * step, h, align,
                                 rot, style))
        return out

    # -- dimensions -----------------------------------------------------------
    def dim_h(self, x1, x2, y, base_y, style="AMA-100", text="<>"):
        d = self.msp.add_linear_dim(
            base=self.p((x1 + x2) / 2.0, base_y),
            p1=self.p(x1, y), p2=self.p(x2, y),
            angle=0, dimstyle=style, text=text,
            dxfattribs={"layer": "A-ANNO-DIMS"})
        d.render()
        return d

    def dim_v(self, y1, y2, x, base_x, style="AMA-100", text="<>"):
        d = self.msp.add_linear_dim(
            base=self.p(base_x, (y1 + y2) / 2.0),
            p1=self.p(x, y1), p2=self.p(x, y2),
            angle=90, dimstyle=style, text=text,
            dxfattribs={"layer": "A-ANNO-DIMS"})
        d.render()
        return d

    def dim_chain_h(self, xs, y, base_y, style="AMA-100"):
        for a, b in zip(xs[:-1], xs[1:]):
            self.dim_h(a, b, y, base_y, style)

    def dim_chain_v(self, ys, x, base_x, style="AMA-100"):
        for a, b in zip(ys[:-1], ys[1:]):
            self.dim_v(a, b, x, base_x, style)


# =============================================================================
# ANNOTATION SYMBOLS
# =============================================================================

def grid_bubble(sh, x, y, label, r=700, h=H_GRID):
    sh.circle("A-GRID-IDEN", x, y, r)
    sh.text("A-GRID-IDEN", label, x, y, h, TA.MIDDLE_CENTER, style=TXT_TITLE)


def level_tag(sh, x, y, level_mm, above=True, layer="A-ANNO-SYMB"):
    """Standard levelling triangle with the level written in metres."""
    s = 220
    tri = [(x, y), (x - s, y + s if above else y - s),
           (x + s, y + s if above else y - s)]
    sh.pline(layer, tri, close=True)
    sh.solid(layer, tri)
    txt = f"+{level_mm/1000.0:.3f}" if level_mm >= 0 else f"{level_mm/1000.0:.3f}"
    ty = y + s * 2.0 if above else y - s * 2.4
    sh.text(layer, txt, x + 350, ty - s * 0.4, H_LEVEL, TA.MIDDLE_LEFT)


def north_point(sh, x, y, r=1800):
    sh.circle("A-ANNO-SYMB", x, y, r)
    sh.solid("A-ANNO-SYMB",
             [(x, y + r * 0.92), (x - r * 0.30, y - r * 0.45), (x, y - r * 0.18)])
    sh.pline("A-ANNO-SYMB",
             [(x, y + r * 0.92), (x + r * 0.30, y - r * 0.45), (x, y - r * 0.18)],
             close=True)
    sh.text("A-ANNO-SYMB", "N", x, y + r * 1.55, 400, TA.MIDDLE_CENTER,
            style=TXT_TITLE)


def drawing_title(sh, x, y, title, scale_note, underline_len=None, k=1.0):
    """k scales the annotation for drawings plotted at other than 1:100."""
    h, hs = H_TITLE * k, H_ROOM * k
    sh.text("A-ANNO-TITL", title, x, y, h, TA.BOTTOM_LEFT, style=TXT_TITLE)
    sh.text("A-ANNO-TITL", scale_note, x, y - 1.8 * hs, hs, TA.BOTTOM_LEFT)
    n = underline_len if underline_len else len(title) * h * 0.75
    sh.line("A-ANNO-TITL", x, y - 0.6 * hs, x + n, y - 0.6 * hs)


def section_mark(sh, x0, y0, x1, y1, label, flip=False, stub=5000):
    """Section reference: stub cut lines and direction flags at both ends
    only, so the mark never obscures the plan it is drawn over."""
    horizontal = abs(x1 - x0) > abs(y1 - y0)
    d = -1400 if flip else 1400
    if horizontal:
        sh.line("A-ANNO-SYMB", x0, y0, x0 + stub, y0)
        sh.line("A-ANNO-SYMB", x1 - stub, y1, x1, y1)
        sh.line("A-ANNO-SYMB", x0 + stub, y0, x0 + stub, y0 + d)
        sh.line("A-ANNO-SYMB", x1 - stub, y1, x1 - stub, y1 + d)
    else:
        sh.line("A-ANNO-SYMB", x0, y0, x0, y0 + stub)
        sh.line("A-ANNO-SYMB", x1, y1 - stub, x1, y1)
        sh.line("A-ANNO-SYMB", x0, y0 + stub, x0 + d, y0 + stub)
        sh.line("A-ANNO-SYMB", x1, y1 - stub, x1 + d, y1 - stub)
    for (px, py) in ((x0, y0), (x1, y1)):
        sh.circle("A-ANNO-SYMB", px, py, 700)
        sh.text("A-ANNO-SYMB", label, px, py, H_GRID, TA.MIDDLE_CENTER,
                style=TXT_TITLE)
