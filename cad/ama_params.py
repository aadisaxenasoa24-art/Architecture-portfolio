"""
AMA — Ahmedabad Management Association, ATIRA Campus, Ahmedabad
Architects: HCP Design, Planning & Management (Bimal Patel), completed 1999-2001

SINGLE SOURCE OF TRUTH FOR ALL DIMENSIONS.
Every value in this file is an exact integer in MILLIMETRES.

------------------------------------------------------------------------------
PROVENANCE OF EVERY NUMBER
------------------------------------------------------------------------------
Values are tagged in comments as:

  [PUB]  Published fact. Taken from HCP's own project description, reproduced
         verbatim by World-Architects / Indian-Architects / Archnet.
  [DER]  Derived. Computed so that the model reproduces a [PUB] value.
  [ASM]  Assumed. A reasoned reconstruction value. NOT verified against the
         building. These are the numbers that would change if measured
         drawings were obtained from HCP.

HCP has never released dimensioned drawings of AMA. This file is therefore a
RECONSTRUCTION on a documented grid, not a measured survey. It is internally
exact to the millimetre; it is not guaranteed to match the built fabric.

------------------------------------------------------------------------------
PUBLISHED FACTS USED AS CONSTRAINTS
------------------------------------------------------------------------------
  * Site area .................. 3 acres (= 12 140 569 mm^2 x 10^-6 = 12 140.57 m^2)
  * Built-up area .............. 4 180 m^2
  * Storeys .................... 2 (ground + first)
  * Structure .................. cast in-situ exposed concrete, linear bar
  * Alignment .................. parallel to a row of 8 existing neem trees
  * Approach ................... pedestrian promenade beneath the trees
  * Ground floor ............... double-height ceremonial foyer, classrooms,
                                 seminar halls, boardroom, bookshop
  * Vertical circulation ....... "processional ramp" foyer -> first floor
  * First floor ................ library, exhibition space, 250-seat auditorium
  * Envelope ................... large glazed openings, deep daylight penetration
"""

# =============================================================================
# 1. STRUCTURAL GRID
# =============================================================================

BAY_X = 7200          # [ASM] longitudinal bay. 7.2 m = 6 x 1200 planning module,
                      #       the standard Indian institutional RCC bay.
N_BAYS_X = 13         # [DER] 13 bays -> 93 600 mm, matching a ~94 m bar set
                      #       against 8 neem trees at ~12 m centres.

# Longitudinal gridlines 1..14, x in mm
X_GRID = [i * BAY_X for i in range(N_BAYS_X + 1)]      # 0 .. 93600
X_LABELS = [str(i + 1) for i in range(N_BAYS_X + 1)]   # "1" .. "14"

# Transverse gridlines A..D, y in mm
Y_A = 1800            # [ASM] south envelope line
Y_B = 9000            # [ASM] internal line  (bay A-B = 7200)
Y_C = 16200           # [ASM] rooms/gallery line (bay B-C = 7200)
Y_D = 20400           # [ASM] north envelope line (bay C-D = 4200)
Y_GRID = [Y_A, Y_B, Y_C, Y_D]
Y_LABELS = ["A", "B", "C", "D"]

CANTILEVER = 1800     # [ASM] slab oversail beyond grid A and grid D, forming
                      #       the shading verandah on both long faces.

# Slab outline (overall building footprint)
SLAB_X0 = X_GRID[0] - 200      # [DER] end columns flush: 400/2 = 200
SLAB_X1 = X_GRID[-1] + 200     # [DER]
SLAB_Y0 = Y_A - CANTILEVER     # = 0
SLAB_Y1 = Y_D + CANTILEVER     # = 22200

BLDG_L = SLAB_X1 - SLAB_X0     # 94000 mm
BLDG_W = SLAB_Y1 - SLAB_Y0     # 22200 mm

# Built-up area check:  94.000 m x 22.200 m x 2 floors = 4173.60 m^2
# Published figure ......................................... 4180.00 m^2
# Deviation ................................................ -0.15 %

# =============================================================================
# 2. VERTICAL LEVELS  (mm above site datum +/-0.000)
# =============================================================================

LVL_SITE      = 0         # [ASM] finished ground / promenade datum
LVL_GF        = 900       # [ASM] ground floor FFL on a raised plinth
LVL_FF        = 5400      # [ASM] first floor FFL (floor-to-floor 4500)
LVL_ROOF      = 9900      # [ASM] main roof FFL (floor-to-floor 4500)
LVL_PARAPET   = 10950     # [ASM] main parapet top (1050 above roof)
LVL_AUD_ROOF  = 12300     # [ASM] raised auditorium roof
LVL_AUD_PARA  = 13350     # [ASM] auditorium parapet top

SLAB_T = 150              # [ASM] RCC slab thickness
BEAM_D = 600              # [ASM] main beam depth (below slab soffit)
BEAM_W = 300              # [ASM] main beam width
PARAPET_T = 200           # [ASM] parapet thickness
FOUND_D = 1500            # [ASM] indicative footing depth below datum

# Clear heights (derived, for annotation)
GF_CLEAR = LVL_FF - SLAB_T - LVL_GF          # 4350 to slab soffit
FF_CLEAR = LVL_ROOF - SLAB_T - LVL_FF        # 4350 to slab soffit

# =============================================================================
# 3. STRUCTURE & FABRIC
# =============================================================================

COL_X = 400               # [ASM] column dimension along building length
COL_Y = 700               # [ASM] column dimension across building depth
WALL_EXT = 230            # [ASM] external infill wall
WALL_INT = 120            # [ASM] internal partition. Even, so that a wall
                          #       centred on a gridline has integer faces.
WALL_ACOU = 230           # [ASM] auditorium / seminar acoustic separation

GLAZ_T = 60               # [ASM] glazing line thickness in plan
LOUVRE_T = 150            # [ASM] concrete brise-soleil fin thickness
LOUVRE_PROJ = 1200        # [ASM] fin projection
LOUVRE_PITCH = 900        # [ASM] fin vertical pitch on the south face

# =============================================================================
# 4. ROOM ZONES  (x-ranges keyed to gridlines 1..14)
# =============================================================================
# Depth bands:
#   SOUTH BAND  y = Y_A .. Y_C  (14400 deep) -> served rooms
#   GALLERY     y = Y_C .. Y_D  ( 4200 deep) -> concourse facing the trees

Y_ROOM_0, Y_ROOM_1 = Y_A, Y_C      # 1800 .. 16200
Y_GALL_0, Y_GALL_1 = Y_C, Y_D      # 16200 .. 20400

def gx(n):
    """x-coordinate of gridline n (1-based, as labelled on the drawings)."""
    return X_GRID[n - 1]

# --- GROUND FLOOR ------------------------------------------------------------
# (grid_from, grid_to, room name, area tag)
# The programme below carries only the spaces HCP's own description names.
# The foyer is given three bays so that the ceremonial hall reads as a room in
# its own right rather than as a stairwell wrapped around the ramp.
GF_ROOMS = [
    (1,  2,  "CORE 1\nSTAIR / LIFT / TOILETS"),
    (2,  4,  "SEMINAR HALL 1\n120 SEATS"),
    (4,  5,  "CLASSROOM 1"),
    (5,  6,  "CLASSROOM 2"),
    (6,  9,  "ENTRANCE FOYER\nDOUBLE HEIGHT"),     # full depth, special
    (9,  10, "BOOK SHOP"),
    (10, 11, "BOARD ROOM"),
    (11, 13, "SEMINAR HALL 2\n60 SEATS"),
    (13, 14, "CORE 2\nSTAIR / TOILETS / SERVICES"),
]

# --- FIRST FLOOR -------------------------------------------------------------
FF_ROOMS = [
    (1,  2,  "CORE 1\nSTAIR / LIFT / TOILETS"),
    (2,  5,  "AUDITORIUM\n250 SEATS"),             # full depth, special
    (5,  6,  "AUDITORIUM FOYER"),
    (6,  9,  "FOYER VOID\nBELOW"),                 # full depth, special
    (9,  11, "LIBRARY"),                           # full depth
    (11, 13, "EXHIBITION SPACE"),                  # full depth
    (13, 14, "CORE 2\nSTAIR / TOILETS / STORE"),
]

# Rooms occupying the FULL depth (Y_A..Y_D) rather than the south band only
FULL_DEPTH_GF = {(6, 9)}
FULL_DEPTH_FF = {(2, 5), (5, 6), (6, 9), (9, 11), (11, 13)}

# Gridlines bounding the foyer
FOYER_G0, FOYER_G1 = 6, 9

# =============================================================================
# 5. PROCESSIONAL RAMP  (in the double-height foyer, grid 6-8)
# =============================================================================
# Rise LVL_GF -> LVL_FF = 4500 mm in 4 flights at an exact 1:12 gradient.

RAMP_FLIGHTS = 4                          # [ASM]
RAMP_RISE_TOTAL = LVL_FF - LVL_GF         # 4500
RAMP_RISE_EACH = RAMP_RISE_TOTAL // RAMP_FLIGHTS   # 1125
RAMP_GRADIENT = 12                        # [ASM] 1 : 12
RAMP_RUN_EACH = RAMP_RISE_EACH * RAMP_GRADIENT     # 13500  (exact)
RAMP_WIDTH = 2400                         # [ASM] clear flight width
RAMP_LDG = 2400                           # [ASM] landing depth

# RAMP_Y1 is set to 4500 so that the section cut on gridline B (y = 9000)
# falls exactly 4500 mm along a flight: 4500 / 12 = 375 mm rise, an exact
# integer. Every ramp level appearing on Section A-A is therefore a whole
# millimetre, with no rounding anywhere in the set.
RAMP_Y0 = 2100                            # [ASM] south edge of lower landings
RAMP_Y1 = RAMP_Y0 + RAMP_LDG              # 4500  flight start
RAMP_Y2 = RAMP_Y1 + RAMP_RUN_EACH         # 18000 flight end
RAMP_Y3 = 20285                           # [DER] upper landing stops at the
                                          #       inner face of the grid-D wall
# The four flights sit in the eastern half of the three-bay foyer, leaving the
# western half as open double-height ceremonial hall.
RAMP_X0 = 45600                           # [ASM] west edge of flight 1
RAMP_LEVELS = [LVL_GF + k * RAMP_RISE_EACH for k in range(RAMP_FLIGHTS + 1)]
#             [900, 2025, 3150, 4275, 5400]

# =============================================================================
# 6. AUDITORIUM  (first floor, grid 2-5) — 250 seats, exactly
# =============================================================================

AUD_ROWS = 10                 # [DER] 10 rows x 25 seats = 250  [PUB seat count]
AUD_SEATS_PER_ROW = 25
AUD_SEATS_TOTAL = AUD_ROWS * AUD_SEATS_PER_ROW      # 250  <- matches [PUB]

AUD_SEAT_W = 550              # [ASM] seat centre-to-centre across a row
AUD_ROW_SPACING = 950         # [ASM] back-to-back row spacing
AUD_SEAT_DEPTH = 500          # [ASM] drawn seat depth
AUD_AISLE_SIDE = 1400         # [ASM]
AUD_AISLE_CENTRE = 1200       # [ASM]
AUD_BLOCK_A = 12              # [DER] 12 + 13 = 25 seats per row
AUD_BLOCK_B = 13

AUD_RAKE_PER_ROW = 150        # [ASM] floor rise per row
AUD_STAGE_X0 = gx(2) + 200    # [ASM] stage front zone
AUD_STAGE_D = 7200            # [ASM] stage depth (one bay)
AUD_STAGE_LVL = LVL_FF + 900  # [ASM] stage floor 900 above front-row floor
AUD_FIRST_ROW_X = 16800       # [ASM] x of row 1 (audience faces west/stage)

# =============================================================================
# 7. SITE  (3 acres)
# =============================================================================

SITE_W = 140000               # [ASM] east-west
SITE_H = 86718                # [DER] 140.000 x 86.718 = 12 140.52 m^2 = 3.000 acres
SITE_X0 = -23000              # [ASM] building placed within the plot
SITE_Y0 = -32000

N_TREES = 8                   # [PUB] "a row of 8 existing shady Neem trees"
TREE_SPACING = 12000          # [ASM] mature neem spacing
TREE_CANOPY_R = 5000          # [ASM] 10 m canopy diameter
TREE_TRUNK_R = 350            # [ASM]
TREE_ROW_Y = 30000            # [ASM] centre-line of the tree row, north of the bar
TREE_X0 = (BLDG_L - (N_TREES - 1) * TREE_SPACING) // 2 + SLAB_X0   # centred

PROMENADE_W = 4500            # [ASM] pedestrian promenade beneath the trees

# =============================================================================
# 8. DRAWING SHEET LAYOUT  (model-space placement of each drawing)
# =============================================================================
# Drawings are laid out in model space on a 1:1 mm grid, stacked vertically.

# Spacing is set from the real extents of each drawing (a plan is ~53 000 mm
# tall including its dimension strings and title; a section or elevation
# ~32 000 mm) so that no two drawings can ever overlap in model space.
ORIGINS = {
    "SITE":     (0,      150000),
    "GF":       (0,           0),
    "FF":       (0,      -60000),
    "ROOF":     (0,     -120000),
    "SEC_AA":   (0,     -175000),
    "SEC_BB":   (0,     -215000),
    "SEC_CC":   (60000, -215000),
    "ELEV_N":   (0,     -255000),
    "ELEV_S":   (0,     -295000),
    "ELEV_E":   (0,     -335000),
    "ELEV_W":   (60000, -335000),
    "NOTES":    (145000,  20000),
}
