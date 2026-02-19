"""
PDF layout and styling constants for UM Case Summary (fpdf2).
Single place to tune fonts, colors, spacing, and section thresholds.
"""

from fpdf.fonts import FontFace

# ----- Font sizes (pt) - single source of truth for consistency -----
BODY_FONT_SIZE = 9
EXEC_SUMMARY_FONT_SIZE = 10  # slightly larger than body (9pt) for Executive Summary content
SECTION_H1_SIZE = 14
SECTION_H2_SIZE = 11
FOOTER_FONT_SIZE = 7
# Header (page bar)
HEADER_MAIN_SIZE = 10
HEADER_MAIN_SIZE_LARGE = 14
HEADER_SUB_SIZE = 8
HEADER_SUB_SIZE_LARGE = 9
HEADER_CASE_ID_SIZE = 10
# Cover page
COVER_TITLE_SIZE = 22
COVER_SUBTITLE_SIZE = 10  # BODY_FONT_SIZE + 1
# Table of Contents (title uses SECTION_H1_SIZE)
TOC_SUBTITLE_SIZE = 8   # slightly smaller than body for secondary text
TOC_TABLE_HEADER_SIZE = 12  # section table column headers (larger for presence)
TOC_ENTRY_SIZE = 11    # section names and page numbers (bigger, easier to read)
TOC_ROW_LINE_HEIGHT_MM = 8  # row height in table (taller rows = bigger TOC)
# Narrative (markdown) headings inside Section 2
NARRATIVE_H1_SIZE = 12
NARRATIVE_H2_SIZE = 11  # same as SECTION_H2_SIZE
NARRATIVE_H3_SIZE = 10
# Section header bar (level 1) layout
SECTION_BAR_HEIGHT_MM = 10
SECTION_BAR_PADDING_MM = 8

# ----- Line height (mm) -----
BODY_LINE_HEIGHT = 7
# Table row line height (pt) for consistent wrapping in data tables
TABLE_LINE_HEIGHT_PT = 12  # ~1.33 * BODY_FONT_SIZE for readable wrapped cells
# First table (patient grid): midpoint between body (9pt) and previous emphasis (11pt bold) = 10pt regular
PATIENT_GRID_FONT_SIZE = 10
PATIENT_GRID_FONT_BOLD = False

# ----- Header -----
HEADER_HEIGHT_FIRST_MM = 18
HEADER_HEIGHT_OTHER_MM = 13
HEADER_PAD_MM = 15
HEADER_BUFFER_BELOW_MM = 4
# Header bar colors (RGB)
HEADER_BG_DARK = (15, 23, 42)
HEADER_BG_GRADIENT_LIGHT = (2, 132, 199)
HEADER_TEXT_WHITE = (255, 255, 255)
HEADER_SUBTITLE_GRAY = (148, 163, 184)

# ----- Brand (logo) blue - used only for actual section headings (Section 1-7 bars in document) -----
BRAND_BLUE = (7, 89, 133)            # darker blue (Sky 800 / #075985)

# ----- Section styling: actual section headings use blue bar + white text, left-aligned -----
SECTION_BAR_FILL = BRAND_BLUE
SECTION_BAR_TEXT = (255, 255, 255)   # white text on section bars
SECTION_TITLE_COLOR = (30, 41, 59)   # dark slate for level-2 headings and cover/grid
# Page break: start new page if less than this many mm from bottom before a section
SECTION_PAGE_BREAK_THRESHOLD_MM = 40

# ----- Executive Summary (same blue bar as other section headings) -----
EXEC_SUMMARY_HEADER_FILL = BRAND_BLUE
EXEC_SUMMARY_HEADER_TEXT = (255, 255, 255)
EXEC_SUMMARY_CALLOUT_COLOR = BRAND_BLUE  # "read first" line in brand blue on white
EXEC_SUMMARY_ACCENT_BORDER = (224, 242, 254)  # light blue left border (sky-100)

# ----- Tables (neutral gray only, no blue: gray fills + black/gray text) -----
# Table header row and subsection labels (e.g. FACILITY, PRIMARY DIAGNOSIS) are always center-aligned.
TABLE_HEADER_FILL = (240, 240, 240)
TABLE_HEADER_COLOR = (25, 25, 25)   # neutral dark gray (no navy/blue)
TABLE_ZEBRA_FILL = (248, 248, 248)
# Abnormal lab result highlight (red)
LAB_ABNORMAL_COLOR = (185, 28, 28)

# ----- Narrative (Section 2: Comprehensive Clinical Narrative) -----
NARRATIVE_FONT_SIZE = 10  # same as Executive Summary for section body text
NARRATIVE_HEADING_BG = "#e2e8f0"   # slate-200 for subsection headings
NARRATIVE_LINE_HEIGHT = 1.45
# Text color for tag styles (slate-800)
TAG_STYLE_COLOR = (30, 41, 59)

# ----- Placeholder / empty state -----
PLACEHOLDER_COLOR = (71, 85, 105)

# ----- Tag styles for write_html (all sizes from constants above) -----
TAG_STYLES = {
    "h1": FontFace(color=TAG_STYLE_COLOR, size_pt=NARRATIVE_H1_SIZE),
    "h2": FontFace(color=TAG_STYLE_COLOR, size_pt=NARRATIVE_H2_SIZE),
    "h3": FontFace(color=TAG_STYLE_COLOR, size_pt=NARRATIVE_H3_SIZE),
    "h4": FontFace(color=TAG_STYLE_COLOR, size_pt=BODY_FONT_SIZE),
    "h5": FontFace(color=TAG_STYLE_COLOR, size_pt=BODY_FONT_SIZE),
    "h6": FontFace(color=TAG_STYLE_COLOR, size_pt=BODY_FONT_SIZE),
    "p": FontFace(color=TAG_STYLE_COLOR, size_pt=BODY_FONT_SIZE),
    "li": FontFace(color=TAG_STYLE_COLOR, size_pt=BODY_FONT_SIZE),
    "ul": FontFace(color=TAG_STYLE_COLOR, size_pt=BODY_FONT_SIZE),
    "ol": FontFace(color=TAG_STYLE_COLOR, size_pt=BODY_FONT_SIZE),
}

TAG_STYLES_EXEC = {
    **TAG_STYLES,
    "p": FontFace(color=TAG_STYLE_COLOR, size_pt=EXEC_SUMMARY_FONT_SIZE),
    "li": FontFace(color=TAG_STYLE_COLOR, size_pt=EXEC_SUMMARY_FONT_SIZE),
    "ol": FontFace(color=TAG_STYLE_COLOR, size_pt=EXEC_SUMMARY_FONT_SIZE),
}

# Section 2 narrative: 10pt body text (same as Executive Summary)
TAG_STYLES_NARRATIVE = {
    **TAG_STYLES,
    "p": FontFace(color=TAG_STYLE_COLOR, size_pt=NARRATIVE_FONT_SIZE),
    "li": FontFace(color=TAG_STYLE_COLOR, size_pt=NARRATIVE_FONT_SIZE),
    "ul": FontFace(color=TAG_STYLE_COLOR, size_pt=NARRATIVE_FONT_SIZE),
    "ol": FontFace(color=TAG_STYLE_COLOR, size_pt=NARRATIVE_FONT_SIZE),
    "h4": FontFace(color=TAG_STYLE_COLOR, size_pt=NARRATIVE_FONT_SIZE),
    "h5": FontFace(color=TAG_STYLE_COLOR, size_pt=NARRATIVE_FONT_SIZE),
    "h6": FontFace(color=TAG_STYLE_COLOR, size_pt=NARRATIVE_FONT_SIZE),
}

# FontFace for table header row (bold, dark text, light fill)
TABLE_HEADER_STYLE = FontFace(
    emphasis="BOLD",
    color=TABLE_HEADER_COLOR,
    fill_color=TABLE_HEADER_FILL,
)
# FontFace for TOC table: header row and body rows (defined after TABLE_HEADER_*)
TOC_TABLE_HEADER_STYLE = FontFace(
    emphasis="BOLD",
    color=TABLE_HEADER_COLOR,
    fill_color=TABLE_HEADER_FILL,
    size_pt=TOC_TABLE_HEADER_SIZE,
)
TOC_ENTRY_STYLE = FontFace(color=TABLE_HEADER_COLOR, size_pt=TOC_ENTRY_SIZE)

# FontFace for abnormal lab result cell (red text)
LAB_ABNORMAL_STYLE = FontFace(color=LAB_ABNORMAL_COLOR)

# Bold label (no fill) for patient grid labels
BOLD_LABEL_STYLE = FontFace(emphasis="BOLD", color=TABLE_HEADER_COLOR)
