"""
Shared configuration for the SHREYAS 1:500 CNC terrain model.

Ground coordinate system used throughout:
    X -> east, Y -> north, units = millimetres at 1:1 (full size).
    Origin (0,0) = south-west corner of the model window.

All numbers below are derived in cnc/docs/verification.md, not guessed.
"""

# --- calibration -----------------------------------------------------------
# Ground millimetres per PDF point, calibrated on the basketball court that the
# source DWG draws as exactly 30000 x 18000 mm.  Verified to 0.000 % against six
# further known lengths (4500, 23500, 43543.03, 43966.94, 51500, 58881.47 mm).
MM_PER_PT = 661.630406

# --- source drawing --------------------------------------------------------
PDF_SRC = "26_08_22_SHREYAS_RASTER_WITH_CONTOURS.pdf"
DWG_SRC = "shreyasplancncrefrence.dwg"

# Map neatline corners in PDF points (used only to centre the model window).
FRAME_CENTRE_PT = (605.23100, 520.12675)

# --- model window ----------------------------------------------------------
MODEL_W_M = 600.0          # east-west   -> 1200 mm at 1:500
MODEL_H_M = 540.0          # north-south -> 1080 mm at 1:500
SCALE     = 500            # 1:500

SHEET_MM  = 1219.2         # 4 ft CNC bed (4' x 4')

# --- terrain ---------------------------------------------------------------
CONTOUR_INTERVAL_M = 1.0
LEVEL_MIN = 44             # lowest labelled contour in the data
LEVEL_MAX = 67             # highest contour (innermost loop of the SW summit)
BASE_LEVEL = 43            # datum of the base board, one interval below LEVEL_MIN

# Board thickness that makes the model true to scale vertically:
#   1.0 m / 500 = 2.0 mm
BOARD_MM = CONTOUR_INTERVAL_M * 1000.0 / SCALE     # = 2.0

# --- DEM -------------------------------------------------------------------
DEM_CELL_M   = 0.25        # 0.5 mm at 1:500
DEM_MARGIN_M = 40.0        # solve on a larger domain, then crop, to kill edge effects

# --- contour level map (validated - see docs/verification.md) --------------
COLOUR_LEVEL = {
    (205, 105,  40): 44, (211, 124, 213): 45, (100,  33, 101): 45,
    ( 41,  49, 137): 46, (  0, 255,   0): 47, (114, 116,  48): 48,
    (205,  32,  39): 49, ( 69,  84, 165): 50, ( 19, 155,  72): 51,
    (200, 201,  45): 52, (209, 156, 199): 53, (254, 204, 102): 54,
    ( 34,  52, 110): 55, (242, 113, 114): 56, (122, 175, 223): 57,
    ( 88, 186,  72): 58, (163, 158,  10): 59, (247, 171, 174): 60,
    (106, 201, 220): 61, (224, 189, 103): 62, (255,   0, 255): 63,
    (176,  42, 229): 64, ( 33, 169, 237): 65, (118,  72, 199): 66,
    (112, 215, 184): 67,
}
# black chains are the central-hill portions of the same contours
BLACK_LEVEL = {0: 56, 1: 57, 2: 58, 3: 59, 4: 60, 5: 60, 6: 61, 7: 62, 8: 63}


def window_pt():
    """Model window in PDF points -> (x0, y_top, x1, y_bot)."""
    hw = MODEL_W_M * 1000.0 / 2.0 / MM_PER_PT
    hh = MODEL_H_M * 1000.0 / 2.0 / MM_PER_PT
    cx, cy = FRAME_CENTRE_PT
    return cx - hw, cy - hh, cx + hw, cy + hh


def pt_to_ground(a):
    """Nx2 array of PDF points -> ground millimetres (X east, Y north)."""
    import numpy as np
    x0, ytop, x1, ybot = window_pt()
    a = np.asarray(a, dtype=float)
    out = np.empty_like(a)
    out[:, 0] = (a[:, 0] - x0) * MM_PER_PT
    out[:, 1] = (ybot - a[:, 1]) * MM_PER_PT
    return out
