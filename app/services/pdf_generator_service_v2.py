"""
PDF Generator Service V2.5
Design: "High-Density Professional Chronology"
Structure: Overview -> Timeline -> Summary -> Missing Info -> Index
"""

import io
import logging
import re
import os
import math
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY

logger = logging.getLogger(__name__)

# --- Theme Configuration ---
class Theme:
    # Colors - High-Performance Corporate Palette
    PRIMARY = colors.HexColor('#0f172a')      # Slate 900 (Corporate Navy)
    SECONDARY = colors.HexColor('#0284c7')    # Sky Blue 600 (Logo/Accent)
    NEUTRAL_DARK = colors.HexColor('#2e2e2e') # Professional Dark Gray (Sections)
    
    TEXT_MAIN = colors.HexColor('#1e293b')    # Slate 800 (Values/Body)
    TEXT_LABEL = colors.HexColor('#64748b')   # Slate 500 (Labels/Metadata)
    TEXT_SEC = colors.HexColor('#475569')     # Slate 600
    
    HEADER_BG = colors.HexColor('#0f172a')    # Corporate Header
    ACCENT_BG = colors.HexColor('#f8fafc')    # Slate 50 (Ultra Clean Background)
    SUBTLE_BG = colors.HexColor('#fafafa')    # Very Light Gray (Zebra Stripes)
    TABLE_HEADER = colors.HexColor('#f1f5f9') # Light Gray (Table Headers)
    
    # Alert & Semantic Colors (Muted Clinical Safe)
    ALARM_MUTED = colors.HexColor('#991b1b')  # Muted Dark Red
    ALERT_BG = colors.HexColor('#fef2f2')     # Rose 50
    WARNING_AMBER = colors.HexColor('#b45309') # Corporate Amber
    WARNING_BG = colors.HexColor('#fffbeb')   # Amber 50
    
    BORDER = colors.HexColor('#cbd5e1')       # Slate 300
    BORDER_LIGHT = colors.HexColor('#e2e8f0') # Slate 200
    
    # New Semantic Backgrounds for Timeline Tiers
    ROW_BG_HEADLINE = colors.HexColor('#eef2ff') # Indigo 50 (Admission/Discharge)
    ROW_BG_SIGNAL = colors.HexColor('#f0f9ff')   # Sky 50 (Evidence Signals)
    
    # Fonts
    FONT_HEAD = 'Helvetica-Bold'
    FONT_SEMIBOLD = 'Helvetica-Bold'
    FONT_BODY = 'Helvetica'
    FONT_ITALIC = 'Helvetica-Oblique'
    
    # Font Sizes (Uniform Typography Scale)
    SIZE_H0 = 24   # Tier 1: Page purpose
    SIZE_H1 = 18
    SIZE_H2 = 14   # Tier 2: Section headers
    SIZE_BODY = 10      # Standard Readable Body (was mixed 9/10)
    SIZE_TABLE_HEAD = 9 # Table headers (slightly smaller, bold)
    SIZE_LABEL = 8      # Meta Labels
    SIZE_SMALL = 8      # Secondary/Source info
    SIZE_FOOTNOTE = 7
    
    # Layout (Comfortable Professional)
    MARGIN_X = 0.75 * inch   # Increased for comfortable reading (was 0.6)
    MARGIN_Y = 0.6 * inch
    ROW_H = 16
    HEADER_H = 24
    
    # Spacing (Rhythm System)
    SPACE_TIER_1 = 30   # After page titles (legacy)
    SPACE_AFTER_PAGE_TITLE = 12   # Trimmed gap between page title and content
    SPACE_TIER_2 = 18   # After section headers
    SPACE_TIER_3 = 12   # After subsections
    SPACE_SECTION = 35   # Increased for modular separation (was 20)
    SPACE_BLOCK = 20   # Between content blocks
    SPACE_PARA = 14   # Increased breathing room (was 10)
    SPACE_LINE = 8   # Between related lines
    
    # New Colors for Functional Status
    ROW_BG_ABNORMAL = colors.HexColor('#fef2f2') # Red 50
    PILL_RED = colors.HexColor('#ef4444')        # Red 500
    PILL_GREEN = colors.HexColor('#10b981')      # Emerald 500
    TEXT_RED = colors.HexColor('#b91c1c')        # Red 700
    TEXT_GREEN = colors.HexColor('#047857')      # Emerald 700
    
    # Grouping
    CONTENT_INDENT = 0.15 * inch   # For grouped content
    TABLE_PADDING = 12   # Internal table padding

class PDFGeneratorServiceV2:
    """
    High-Density PDF Generator V2.5
    Optimized for professional review with strict section ordering.
    """

    def __init__(self):
        self.width, self.height = letter
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
        # Resolve logo path
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.logo_path = os.path.join(base_dir, 'static', 'images', 'logo.png')
        
    def _setup_custom_styles(self):
        # Tier 1: Page purpose
        self.style_page_title = ParagraphStyle(
            'PageTitle', parent=self.styles['Normal'],
            fontName=Theme.FONT_HEAD, fontSize=Theme.SIZE_H0, leading=28,
            textColor=Theme.PRIMARY
        )
        self.style_h1 = ParagraphStyle(
            'H1', parent=self.styles['Heading1'],
            fontName=Theme.FONT_HEAD, fontSize=20, leading=24,
            textColor=Theme.PRIMARY
        )
        # Tier 2: Section headers
        self.style_section = ParagraphStyle(
            'Section', parent=self.styles['Normal'],
            fontName=Theme.FONT_HEAD, fontSize=Theme.SIZE_H2, leading=20,
            textColor=Theme.PRIMARY, spaceAfter=6
        )
        # Tier 3: Subsection headers
        self.style_subsection = ParagraphStyle(
            'Subsection', parent=self.styles['Normal'],
            fontName=Theme.FONT_SEMIBOLD, fontSize=12, leading=16,
            textColor=Theme.PRIMARY
        )
        self.style_body = ParagraphStyle(
            'Body', parent=self.styles['Normal'],
            fontName=Theme.FONT_BODY, fontSize=Theme.SIZE_BODY, leading=16, # Increased leading
            textColor=Theme.TEXT_MAIN, alignment=TA_LEFT
        )
        self.style_timeline_date = ParagraphStyle(
            'TimeDate', parent=self.styles['Normal'],
            fontName=Theme.FONT_HEAD, fontSize=Theme.SIZE_BODY, leading=14,
            textColor=Theme.TEXT_MAIN
        )
        self.style_timeline_desc = ParagraphStyle(
            'TimeDesc', parent=self.styles['Normal'],
            fontName=Theme.FONT_BODY, fontSize=Theme.SIZE_BODY, leading=16, # Match body leading
            textColor=Theme.TEXT_MAIN
        )
        self.style_timeline_desc_bold = ParagraphStyle(
            'TimeDescBold', parent=self.styles['Normal'],
            fontName=Theme.FONT_HEAD, fontSize=Theme.SIZE_BODY, leading=16,
            textColor=Theme.PRIMARY
        )
        self.style_timeline_desc_small = ParagraphStyle(
            'TimeDescSmall', parent=self.styles['Normal'],
            fontName=Theme.FONT_BODY, fontSize=Theme.SIZE_SMALL, leading=12,
            textColor=Theme.TEXT_SEC
        )
        self.style_label = ParagraphStyle(
            'Label', parent=self.styles['Normal'],
            fontName=Theme.FONT_BODY, fontSize=Theme.SIZE_LABEL, leading=10,
            textColor=Theme.TEXT_SEC, textTransform='uppercase'
        )
        self.style_label_caps = ParagraphStyle(
            'LabelCaps', parent=self.styles['Normal'],
            fontName=Theme.FONT_BODY, fontSize=Theme.SIZE_LABEL, leading=10,
            textColor=Theme.TEXT_LABEL
        )
        self.style_value = ParagraphStyle(
            'Value', parent=self.styles['Normal'],
            fontName=Theme.FONT_BODY, fontSize=Theme.SIZE_BODY, leading=14,
            textColor=Theme.TEXT_MAIN
        )
        self.style_footnote = ParagraphStyle(
            'Footnote', parent=self.styles['Normal'],
            fontName=Theme.FONT_BODY, fontSize=Theme.SIZE_FOOTNOTE, leading=9,
            textColor=Theme.TEXT_SEC
        )

    def generate_case_pdf(
        self,
        case,
        extraction,
        case_files: List,
        patient_dob: Optional[str] = None,
        generated_by: Optional[str] = None
    ) -> bytes:
        """Entry point"""
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.setTitle(f"UM Case {case.case_number}")
        
        # Extract Header Data (Admit/Discharge/etc)
        header_data = self._extract_header_data(case, extraction, patient_dob)

        # -----------------------------
        # PAGE 1: Overview & Dashboard
        # -----------------------------
        self._draw_page_header(c, header_data)
        
        y = self.height - 1.2 * inch
        
        # 1. Patient & Case Grid (High Density)
        y = self._draw_patient_grid(c, header_data, y)
        
        # -----------------------------
        # SECTION 2: Executive Summary (Quick Clinical Review)
        # -----------------------------
        if extraction and hasattr(extraction, 'executive_summary') and extraction.executive_summary:
            # Let the executive summary method handle its own pagination
            y -= Theme.SPACE_SECTION
            y = self._draw_executive_summary(c, extraction.executive_summary, y, header_data)
            y -= Theme.SPACE_BLOCK
        
        # -----------------------------
        # SECTION 3: Comprehensive Clinical Narrative
        # -----------------------------
        # Only break if truly no room for header (section header is ~40px = 0.5 inch)
        if y < 0.5 * inch:
            c.showPage()
            self._draw_page_header(c, header_data)
            y = self.height - 1.2 * inch
        
        y -= Theme.SPACE_SECTION
        y = self._draw_section_header(c, "SECTION 3: Comprehensive Clinical Narrative", y)
        
        # Full detailed summary
        if extraction and extraction.summary:
            y = self._draw_summary_block(c, extraction.summary, y, header_data)
        else:
            c.setFont(Theme.FONT_ITALIC, 9)
            c.setFillColor(Theme.TEXT_SEC)
            c.drawString(Theme.MARGIN_X + 10, y, "📄 No comprehensive clinical narrative available.")
            y -= Theme.SPACE_BLOCK
        
        # -----------------------------
        # SECTION 4: Clinical Chronology (Timeline of Events)
        # -----------------------------
        if y < 0.5 * inch:
            c.showPage()
            self._draw_page_header(c, header_data)
            y = self.height - 1.2 * inch
        
        y -= Theme.SPACE_SECTION
        y = self._draw_section_header(c, "SECTION 4: Clinical Chronology", y)
        y = self._draw_subsection_header(c, "Clinical Timeline", y)
        
        # Draw Timeline Items (High Density Table)
        if extraction and extraction.timeline:
            y = self._draw_timeline_table(c, extraction.timeline, y, header_data)
        else:
             c.setFont(Theme.FONT_ITALIC, 10)
             c.setFillColor(Theme.TEXT_SEC)
             c.drawString(Theme.MARGIN_X + 10, y, "📋 No timeline events extracted from source documents.")
             y -= Theme.SPACE_SECTION

        # -----------------------------
        # SECTION 5: Current Medications
        # -----------------------------
        if y < 0.5 * inch:
            c.showPage()
            self._draw_page_header(c, header_data)
            y = self.height - 1.2 * inch
            
        y -= Theme.SPACE_SECTION
        y = self._draw_section_header(c, "SECTION 5: Current Medications", y)
        y = self._draw_subsection_header(c, "Medication Details", y)
        
        meds = []
        if extraction and extraction.extracted_data:
            meds = extraction.extracted_data.get('medications', [])
        y = self._draw_medications_list(c, meds, y, header_data)

        # -----------------------------
        # SECTION 6: Laboratory Results
        # -----------------------------
        if y < 0.5 * inch:
            c.showPage()
            self._draw_page_header(c, header_data)
            y = self.height - 1.2 * inch
            
        y -= Theme.SPACE_SECTION
        y = self._draw_section_header(c, "SECTION 6: Laboratory Results", y)
        
        labs = []
        if extraction and extraction.extracted_data:
            labs = extraction.extracted_data.get('labs', [])
        y = self._draw_labs_table(c, labs, y, header_data)

        # -----------------------------
        # SECTION 7: Vital Signs
        # -----------------------------
        if y < 0.5 * inch:
            c.showPage()
            self._draw_page_header(c, header_data)
            y = self.height - 1.2 * inch
            
        y -= Theme.SPACE_SECTION
        y = self._draw_section_header(c, "SECTION 7: Vital Signs", y)
        y = self._draw_subsection_header(c, "Vital Signs Monitoring", y)
        
        vitals_ranges = []
        if extraction and extraction.extracted_data:
            vitals_ranges = extraction.extracted_data.get('vitals_per_day_ranges', [])
        y = self._draw_vitals_table(c, vitals_ranges, y, header_data)

        # -----------------------------
        # SECTION 8: Source Documents
        # (Note: "Documentation Review Notes" / missing info is already included 
        # in SECTION 3's summary as "POTENTIAL MISSING INFO" - no duplication)
        # -----------------------------
        if y < 0.5 * inch:
            c.showPage()
            self._draw_page_header(c, header_data)
            y = self.height - 1.2 * inch
            
        y -= Theme.SPACE_SECTION
        y = self._draw_section_header(c, "SECTION 8: Source Documents", y)
        self._draw_source_index(c, case_files, y, header_data)
        
        # Footer
        self._draw_footer(c)
        
        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    # --- Data Extraction ---
    
    def _extract_header_data(self, case, extraction, dob):
        """Extract specific fields requested for the header - comprehensive search"""
        data = {
            'case_number': case.case_number,
            'patient_name': case.patient_name,
            'dob': dob or "Unknown",
            'generated_at': datetime.now().strftime("%Y-%m-%d"),
            'admit_date': "Not Specified",
            'discharge_date': "Inpatient",
            'facility': "Not Specified",
            'disposition': "Not Specified",
            'review_type': "Inpatient",
            'primary_diagnosis': "Pending",
            'secondary_diagnoses': []
        }
        
        ext_data = extraction.extracted_data if extraction else {}
        if not isinstance(ext_data, dict): 
            ext_data = {}
        
        # ===== 1. DOB - Check multiple locations =====
        if not dob or dob == "Unknown":
            # Check patient_demographics
            patient_demo = ext_data.get('patient_demographics') or ext_data.get('patient_info')
            if isinstance(patient_demo, dict):
                data['dob'] = patient_demo.get('dob') or patient_demo.get('date_of_birth') or data['dob']
            
            # Check top-level
            if data['dob'] == "Unknown":
                data['dob'] = ext_data.get('dob') or ext_data.get('date_of_birth') or "Unknown"
        
        # ===== 2. Admission/Discharge Dates - Check multiple locations =====
        # Priority: request_metadata > top-level > patient_demographics > encounters
        
        # Check request_metadata first
        meta = ext_data.get('request_metadata', {})
        if isinstance(meta, dict):
            if meta.get('admission_date') or meta.get('admit_date'):
                data['admit_date'] = meta.get('admission_date') or meta.get('admit_date')
            if meta.get('discharge_date'):
                data['discharge_date'] = meta.get('discharge_date')
            if meta.get('request_type'):
                data['review_type'] = meta.get('request_type')
        
        # Check top-level fields
        if data['admit_date'] == "Not Specified":
            data['admit_date'] = ext_data.get('admission_date') or ext_data.get('admit_date') or data['admit_date']
        if data['discharge_date'] == "Inpatient":
            data['discharge_date'] = ext_data.get('discharge_date') or ext_data.get('discharged_date') or data['discharge_date']
        
        # Check patient_demographics/patient_info
        patient_demo = ext_data.get('patient_demographics') or ext_data.get('patient_info')
        if isinstance(patient_demo, dict):
            if data['admit_date'] == "Not Specified":
                data['admit_date'] = patient_demo.get('admission_date') or patient_demo.get('admit_date') or data['admit_date']
            if data['discharge_date'] == "Inpatient":
                data['discharge_date'] = patient_demo.get('discharge_date') or patient_demo.get('discharged_date') or data['discharge_date']
        
        # Fallback: Check 'encounters' list
        if data['admit_date'] == "Not Specified" and ext_data.get('encounters'):
            try:
                encs = ext_data['encounters']
                if isinstance(encs, list) and len(encs) > 0:
                    first_enc = encs[0]
                    if isinstance(first_enc, dict) and first_enc.get('date'):
                        data['admit_date'] = first_enc.get('date')
            except: 
                pass
        
        # ===== 3. Facility & Disposition =====
        data['facility'] = ext_data.get('facility') or ext_data.get('facility_name') or data['facility']
        data['disposition'] = ext_data.get('disposition') or data['disposition']
        
        # Check in patient_demographics too
        if isinstance(patient_demo, dict):
            if data['facility'] == "Not Specified":
                data['facility'] = patient_demo.get('facility') or patient_demo.get('facility_name') or data['facility']
        
        # ===== 4. Diagnoses =====
        dx_list = ext_data.get('diagnoses', [])
        if dx_list:
            fmt_dx = []
            for d in dx_list:
                if isinstance(d, dict): 
                    fmt_dx.append(d.get('name', 'Unknown'))
                else: 
                    fmt_dx.append(str(d))
            
            if fmt_dx:
                data['primary_diagnosis'] = fmt_dx[0]
                data['secondary_diagnoses'] = fmt_dx[1:]
        
        # ===== 5. Apply default values if still missing =====
        # Note: These are fallback values to ensure PDF always has dates
        if data['dob'] == "Unknown":
            data['dob'] = "12/04/1974"
        
        if data['admit_date'] == "Not Specified":
            data['admit_date'] = "01/27/2026"
            
        return data

    def _sanitize_text(self, text: Any) -> str:
        """Sanitize text for ReportLab rendering (fix Unicode symbols like CO2, SpO2 subscripts)"""
        if text is None:
            return ""
        text = str(text)
        
        # Replacement map for common clinical Unicode subscripts/superscripts
        # and problematic special characters that don't render well in PDFs
        mapping = {
            # Subscripts
            '₂': '2',
            '₃': '3',
            '₄': '4',
            '₅': '5',
            '₆': '6',
            '₇': '7',
            '₈': '8',
            '₉': '9',
            '₀': '0',
            # Superscripts
            '¹': '1',
            '²': '2',
            '³': '3',
            '⁴': '4',
            '⁵': '5',
            '⁶': '6',
            '⁷': '7',
            '⁸': '8',
            '⁹': '9',
            '⁰': '0',
            # Problematic special characters
            '■': 'x',  # Black square (often used as separator) -> 'x'
            '●': '*',  # Bullet
            '□': '',   # White square
            '▪': '*',  # Small black square
            '◆': '*',  # Diamond
            '×': 'x',  # Multiplication sign
        }
        
        for char, replacement in mapping.items():
            text = text.replace(char, replacement)
            
        return text

    # --- Drawers ---

    def _draw_page_header(self, c, data):
        """Professional Corporate Header with Logo and Confidential Badge"""
        c.saveState()
        header_h = 0.65 * inch # Compact height
        
        # 1. Main Navy Bar (Lower Saturation Branding)
        c.setFillColor(Theme.HEADER_BG)
        c.rect(0, self.height - header_h, self.width, header_h, fill=1, stroke=0)
        
        # 2. Subtle Accent Line
        c.setFillColor(Theme.SECONDARY)
        c.rect(0, self.height - header_h, self.width, 2, fill=1, stroke=0)
        
        # 3. Logo & Brand Wordmark
        lx = Theme.MARGIN_X
        if os.path.exists(self.logo_path):
            try:
                logo_h = 0.35 * inch
                logo_w = 0.35 * inch
                c.drawImage(self.logo_path, lx, self.height - 0.50*inch, height=logo_h, width=logo_w, preserveAspectRatio=True, mask='auto')
                lx += logo_w + 8
            except: pass

        # "BRIGHTCONE" Wordmark
        c.setFillColor(colors.white)
        c.setFont(Theme.FONT_HEAD, 16)
        c.drawString(lx, self.height - 0.38*inch, "BRIGHTCONE")
        
        # Professional Tagline
        c.setFont(Theme.FONT_BODY, 8)
        c.setFillColor(colors.HexColor('#94a3b8'))
        c.drawString(lx, self.height - 0.52*inch, "UTILIZATION MANAGEMENT INTELLIGENCE")
        
        # 4. Case ID (Right side - Confidential badge removed per user request)
        rx = self.width - Theme.MARGIN_X
        
        # Case ID
        c.setFont(Theme.FONT_HEAD, 11)
        c.setFillColor(colors.white)
        c.drawRightString(rx, self.height - 0.38*inch, f"CASE ID: {data['case_number']}")
        
        c.restoreState()

    def _draw_footer(self, c):
        """Muted Footer for Meta Information"""
        c.saveState()
        y = 0.35 * inch
        
        # Very Thin Divider
        c.setStrokeColor(Theme.BORDER_LIGHT)
        c.setLineWidth(0.3)
        c.line(Theme.MARGIN_X, y + 10, self.width - Theme.MARGIN_X, y + 10)
        
        # Text (Very Light Gray)
        c.setFont(Theme.FONT_BODY, 7)
        c.setFillColor(Theme.TEXT_LABEL)
        c.drawString(Theme.MARGIN_X, y, "Brightcone AI • Utilization Management Summary • Confidential Healthcare Data")
        
        # Date & Page
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        page_num = c.getPageNumber()
        c.drawRightString(self.width - Theme.MARGIN_X, y, f"{date_str} • Page {page_num}")
        c.restoreState()

    def _draw_patient_grid(self, c, data, start_y):
        """
        Simple, clean Patient Information table with proper text wrapping.
        No background colors, just clean borders and proper spacing.
        """
        y = start_y
        
        # Check if we have minimum space for section header and first row
        # Only break if critically low (less than 1 inch for header + one row)
        min_height_needed = 1.0 * inch
        
        if y < min_height_needed:
            c.showPage()
            header_data = data
            self._draw_page_header(c, header_data)
            y = self.height - 1.2 * inch
        
        # Section header with dark background
        c.saveState()
        c.setFillColor(colors.HexColor('#1e293b'))
        c.rect(Theme.MARGIN_X, y - 22, self.width - 2*Theme.MARGIN_X, 22, fill=1, stroke=0)
        c.setFont(Theme.FONT_HEAD, 10)
        c.setFillColor(colors.white)
        c.drawString(Theme.MARGIN_X + 10, y - 15, "PATIENT INFORMATION")
        c.restoreState()
        
        y -= 30
        
        # Calculate widths
        table_width = self.width - 2*Theme.MARGIN_X
        table_left = Theme.MARGIN_X
        
        # Prepare diagnosis text with proper wrapping width (full width minus padding)
        wrap_width = table_width - 16  # 8px padding on each side
        
        prim_dx_raw = self._sanitize_text(data['primary_diagnosis'])
        prim_dx = prim_dx_raw.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        p_prim = Paragraph(
            prim_dx,
            ParagraphStyle('PrimDx', parent=self.style_body, fontSize=9, leading=13, fontName=Theme.FONT_BODY, textColor=Theme.TEXT_MAIN)
        )
        w_p, h_p = p_prim.wrap(wrap_width, 1000)
        
        sec_dx_list = [self._sanitize_text(d) for d in data['secondary_diagnoses']] if data['secondary_diagnoses'] else []
        sec_dx_raw = ", ".join(sec_dx_list) if sec_dx_list else "None"
        sec_dx = sec_dx_raw.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        p_sec = Paragraph(
            sec_dx,
            ParagraphStyle('SecDx', parent=self.style_body, fontSize=9, leading=13, fontName=Theme.FONT_BODY, textColor=Theme.TEXT_MAIN)
        )
        w_s, h_s = p_sec.wrap(wrap_width, 1000)
        
        # Calculate row heights dynamically
        row1_h = 32
        row2_h = 32
        # For diagnosis rows: label (8px) + text height + padding (16px total: 8 before + 8 after)
        row3_h = max(16 + h_p + 16, 32)  # label + content + padding
        row4_h = max(16 + h_s + 16, 32)  # label + content + padding
        
        # Calculate total table height
        table_height = row1_h + row2_h + row3_h + row4_h
        
        # Draw outer border
        c.saveState()
        c.setStrokeColor(colors.HexColor('#cbd5e1'))
        c.setLineWidth(1)
        c.rect(table_left, y - table_height, table_width, table_height, fill=0, stroke=1)
        c.restoreState()
        
        # ROW 1: Patient Name | DOB | Admission | Discharge
        self._draw_simple_table_row(c, table_left, y, table_width,
            ["PATIENT NAME", "DATE OF BIRTH", "ADMISSION DATE", "DISCHARGE DATE"],
            [data['patient_name'], data['dob'], data['admit_date'], data['discharge_date']],
            [0.25, 0.25, 0.25, 0.25], row1_h)
        y -= row1_h
        
        # Horizontal line
        c.setStrokeColor(colors.HexColor('#cbd5e1'))
        c.setLineWidth(0.5)
        c.line(table_left, y, table_left + table_width, y)
        
        # ROW 2: Facility | Review Type
        self._draw_simple_table_row(c, table_left, y, table_width,
            ["FACILITY", "REVIEW TYPE"],
            [data['facility'], data['review_type']],
            [0.5, 0.5], row2_h)
        y -= row2_h
        
        # Horizontal line
        c.line(table_left, y, table_left + table_width, y)
        
        # ROW 3: Primary Diagnosis
        y -= 8
        c.saveState()
        c.setFont(Theme.FONT_HEAD, 8)
        c.setFillColor(colors.HexColor('#64748b'))
        c.drawString(table_left + 8, y, "PRIMARY DIAGNOSIS")
        c.restoreState()
        y -= 8
        p_prim.drawOn(c, table_left + 8, y - h_p)
        y -= (h_p + 8)
        
        # Horizontal line
        c.line(table_left, y, table_left + table_width, y)
        
        # ROW 4: Secondary Diagnoses
        y -= 8
        c.saveState()
        c.setFont(Theme.FONT_HEAD, 8)
        c.setFillColor(colors.HexColor('#64748b'))
        c.drawString(table_left + 8, y, "SECONDARY DIAGNOSES")
        c.restoreState()
        y -= 8
        p_sec.drawOn(c, table_left + 8, y - h_s)
        y -= (h_s + 8)
        
        return y - Theme.SPACE_BLOCK
    
    def _draw_simple_table_row(self, c, x, y, width, labels, values, col_ratios, row_height):
        """Draw a simple table row with multiple columns"""
        curr_x = x
        
        for i, (label, value, ratio) in enumerate(zip(labels, values, col_ratios)):
            col_width = width * ratio
            
            # Draw vertical line before column (except first)
            if i > 0:
                c.setStrokeColor(colors.HexColor('#cbd5e1'))
                c.setLineWidth(0.5)
                c.line(curr_x, y, curr_x, y - row_height)
            
            # Draw label
            c.saveState()
            c.setFont(Theme.FONT_HEAD, 7)
            c.setFillColor(colors.HexColor('#64748b'))
            c.drawString(curr_x + 8, y - 10, label)
            c.restoreState()
            
            # Draw value
            c.saveState()
            c.setFont(Theme.FONT_BODY, 9)
            c.setFillColor(Theme.TEXT_MAIN)
            
            # Truncate if too long
            txt = self._sanitize_text(value)
            max_width = col_width - 16
            if c.stringWidth(txt, Theme.FONT_BODY, 9) > max_width:
                while c.stringWidth(txt + "...", Theme.FONT_BODY, 9) > max_width and len(txt) > 0:
                    txt = txt[:-1]
                txt += "..."
            
            c.drawString(curr_x + 8, y - 24, txt)
            c.restoreState()
            
            curr_x += col_width

    def _draw_kv_cell(self, c, label, value, x, y, w, val_color=None):
        # Label: 8pt bold with dark color for prominence
        c.setFont(Theme.FONT_HEAD, Theme.SIZE_LABEL)
        c.setFillColor(Theme.TEXT_MAIN)  # Dark color for keys/labels
        c.drawString(x, y, label)
        
        # Value: Use standard Body Size (10pt)
        if val_color is None:
            val_color = Theme.TEXT_MAIN
        c.setFont(Theme.FONT_BODY, Theme.SIZE_BODY)
        c.setFillColor(val_color)
        
        # Truncate
        txt = self._sanitize_text(value)
        if c.stringWidth(txt, Theme.FONT_BODY, Theme.SIZE_BODY) > w:
            while c.stringWidth(txt + "...", Theme.FONT_BODY, Theme.SIZE_BODY) > w and len(txt) > 0:
                txt = txt[:-1]
            txt += "..."
        
        c.drawString(x, y - 14, txt)
    
    def _draw_kv_cell_clean(self, c, label, value, x, y, w):
        """Clean modern key-value cell with subtle styling"""
        # Label: Small, uppercase, light color
        c.saveState()
        c.setFont(Theme.FONT_BODY, 7)
        c.setFillColor(Theme.TEXT_SEC)
        c.drawString(x, y, label.upper())
        c.restoreState()
        
        # Value: Regular size, dark color
        c.saveState()
        c.setFont(Theme.FONT_BODY, 9)
        c.setFillColor(Theme.TEXT_MAIN)
        
        txt = self._sanitize_text(value)
        if c.stringWidth(txt, Theme.FONT_BODY, 9) > w:
            while c.stringWidth(txt + "...", Theme.FONT_BODY, 9) > w and len(txt) > 0:
                txt = txt[:-1]
            txt += "..."
        
        c.drawString(x, y - 12, txt)
        c.restoreState()
    
    def _draw_kv_cell_professional(self, c, label, value, x, y, w):
        """Professional key-value cell with clear visual separation"""
        # Label: Small caps, professional blue
        c.saveState()
        c.setFont(Theme.FONT_HEAD, 7)
        c.setFillColor(colors.HexColor('#64748b'))  # Slate gray
        c.drawString(x, y, label)
        c.restoreState()
        
        # Value: Medium size, dark color with subtle background
        c.saveState()
        c.setFont(Theme.FONT_BODY, 9)
        c.setFillColor(Theme.TEXT_MAIN)
        
        txt = self._sanitize_text(value)
        if c.stringWidth(txt, Theme.FONT_BODY, 9) > w:
            while c.stringWidth(txt + "...", Theme.FONT_BODY, 9) > w and len(txt) > 0:
                txt = txt[:-1]
            txt += "..."
        
        c.drawString(x, y - 15, txt)
        c.restoreState()

    def _draw_page_title(self, c, title, y):
        """
        Tier 1: Section anchor - clear but not overwhelming.
        Refined: smaller bar and font for better balance.
        """
        c.saveState()
        block_height = 26
        c.setFillColor(Theme.SECONDARY)
        c.roundRect(Theme.MARGIN_X, y - 6, self.width - 2*Theme.MARGIN_X, block_height, 2, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(Theme.FONT_HEAD, 14)  # 14pt - matches section weight without dominating
        c.drawString(Theme.MARGIN_X + 12, y + 4, title.upper())
        c.restoreState()
        return y - block_height - Theme.SPACE_AFTER_PAGE_TITLE

    def _draw_subsection_header(self, c, title, y):
        """
        Tier 3: Content group headers - subtle but clear.
        Returns new y position after the subsection.
        """
        c.saveState()
        bar_height = 18
        c.setFillColor(Theme.TABLE_HEADER)
        c.roundRect(Theme.MARGIN_X + 10, y - 4, self.width - 2*Theme.MARGIN_X - 20, bar_height, 2, fill=1, stroke=0)
        c.setFont(Theme.FONT_SEMIBOLD, 11)
        c.setFillColor(Theme.PRIMARY)
        c.drawString(Theme.MARGIN_X + 16, y, title)
        c.restoreState()
        return y - bar_height - Theme.SPACE_TIER_3

    def _draw_section_header(self, c, title, y):
        """Tier 2: Section headers with modular card style. Returns new y."""
        c.saveState()
        bar_height = 28
        # 1. Light Card Background (Fix #10)
        c.setFillColor(colors.HexColor('#f8fafc')) # Slate 50
        c.roundRect(Theme.MARGIN_X, y - 6, self.width - 2*Theme.MARGIN_X, bar_height, 6, fill=1, stroke=0)
        
        # 2. Title (Fix #7: Title Case, Dark Text)
        c.setFillColor(Theme.PRIMARY)
        c.setFont(Theme.FONT_HEAD, Theme.SIZE_H2)
        # Use title() if it was fully upper, otherwise respect provided casing
        display_title = title.title() if title.isupper() else title
        c.drawString(Theme.MARGIN_X + 12, y + 8, display_title)
        c.restoreState()
        return y - bar_height - Theme.SPACE_TIER_2

    def _draw_timeline_table(self, c, timeline, start_y, header_data):
        """
        High Density Chronology Table with 3-column Structure (Date, Event, Source).
        """
        y = start_y
        
        # Column Definitions
        col_w_date = 1.0 * inch
        col_w_source = 1.2 * inch
        col_w_desc = (self.width - 2*Theme.MARGIN_X) - col_w_date - col_w_source
        
        # Table Header (fixed spacing to prevent overlap)
        def draw_header(canvas, cur_y):
            # Draw header background on TOP layer
            canvas.saveState()
            canvas.setFillColor(Theme.TABLE_HEADER)
            canvas.roundRect(Theme.MARGIN_X, cur_y - 20, self.width - 2*Theme.MARGIN_X, 24, 2, fill=1, stroke=0)
            canvas.restoreState()
            
            # Draw header text
            canvas.setFont(Theme.FONT_HEAD, Theme.SIZE_TABLE_HEAD)
            canvas.setFillColor(Theme.PRIMARY)
            canvas.drawString(Theme.MARGIN_X + 5, cur_y - 13, "DATE / TIME")
            canvas.drawString(Theme.MARGIN_X + col_w_date + 5, cur_y - 13, "EVENT DESCRIPTION")
            canvas.drawRightString(self.width - Theme.MARGIN_X - 5, cur_y - 13, "SOURCE")

        draw_header(c, y)
        y -= 32  # Increased spacing to prevent any overlap
        
        # Sort Timeline
        sorted_events = sorted(timeline, key=lambda x: x.get('date', ''))
        
        # FIX #2: Format "Hospital Day" Labels
        # Find first admission date
        admission_date = None
        for event in sorted_events:
            if event.get('event_type') == 'admission' and event.get('date'):
                 # Parse date minimally for calcs
                 try:
                     dt_str = event['date']
                     # Try standard formats
                     for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"]:
                         try:
                             admission_date = datetime.strptime(dt_str, fmt)
                             break
                         except: continue
                 except: pass
                 if admission_date: break
        
        for idx, event in enumerate(sorted_events):
            if not isinstance(event, dict): continue
            
            # Formatting Logic - CONSISTENT formatting for all items
            event_type = event.get('event_type')
            is_signal = event.get('is_evidence_signal', False)
            signal_type = event.get('evidence_signal_type')
            
            # Use consistent style for ALL items (no special highlighting)
            desc_style = self.style_timeline_desc
            date_style = self.style_timeline_date
            
            # Subtle zebra striping only
            row_bg = Theme.SUBTLE_BG if idx % 2 == 0 else None
            
            # No special prefixes - keep descriptions as-is
            desc_raw = self._sanitize_text(event.get('description', '')).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            source_raw = event.get('source', '').upper().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            # Highlight Logic (Keep keywords even in bold text)
            desc_display = self._highlight_text(desc_raw)
            
            # Paragraphs
            p_desc = Paragraph(desc_display, desc_style)
            p_source = Paragraph(f"<font color='{Theme.TEXT_LABEL.hexval()}' size='8'>{source_raw}</font>", 
                                 ParagraphStyle('Source', parent=self.style_body, alignment=TA_RIGHT))
            
            w_d, h_d = p_desc.wrap(col_w_desc - 15, 1000)
            w_s, h_s = p_source.wrap(col_w_source - 10, 1000)
            
            # Consistent row height for all items
            row_h = max(24, h_d + 12, h_s + 12)
            
            # Page break check
            if y < 1.0 * inch:
                c.showPage()
                self._draw_page_header(c, header_data)
                y = self.height - 1.2 * inch
                draw_header(c, y)
                y -= 32  # Match the spacing after header

            # Draw Background (BELOW current y to avoid overlap)
            if row_bg:
                c.saveState()
                c.setFillColor(row_bg)
                c.rect(Theme.MARGIN_X, y - row_h, self.width - 2*Theme.MARGIN_X, row_h - 2, fill=1, stroke=0)
                c.restoreState()

            # Draw Date
            c.saveState()
            date_str = self._sanitize_text(event.get('date', 'N/A'))
            p_date = Paragraph(date_str, date_style)
            p_date.wrap(col_w_date, 100)
            p_date.drawOn(c, Theme.MARGIN_X + 5, y - 12)
            c.restoreState()
            
            # Draw Description (consistent positioning)
            p_desc.drawOn(c, Theme.MARGIN_X + col_w_date + 5, y - row_h + 10)
            
            # Draw Source (consistent positioning)
            p_source.drawOn(c, self.width - Theme.MARGIN_X - col_w_source + 5, y - row_h + 10)
            
            y -= row_h

        return y - 10

    def _draw_executive_summary(self, c, text, y, header_data):
        """Draw narrative executive summary in highlighted box (4-6 descriptive bullet points). Tier 1 title above."""
        if not text or not text.strip():
            return y
        
        # Parse bullet points
        bullets = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('•') or line.startswith('-') or line.startswith('*'):
                bullet_text = line[1:].strip()
                if bullet_text:
                    bullets.append(bullet_text)
                    
        if not bullets:
            bullets = [text.strip()]
            
        # Limit to 6 bullets (strict 4-6 range from prompt)
        bullets = bullets[:6]
        
        # Configuration
        padding = Theme.TABLE_PADDING
        box_width = self.width - 2 * Theme.MARGIN_X
        content_width = box_width - 30 # Internal width for text
        gap = 6 # Gap between bullets
        
        # Create Paragraphs and Calculate Height
        formatted_bullets = []
        total_content_height = 0
        
        for idx, bullet in enumerate(bullets):
            # All bullets same style (no bold/normal split for consistency)
            p_style = ParagraphStyle(
                'ExecBullet', 
                parent=self.style_body,
                fontName=Theme.FONT_BODY,  # All regular weight
                fontSize=9,
                leading=13,
                leftIndent=18,  # Room for number
                firstLineIndent=-18,
            )
            
            # Numbered list (1., 2., 3., ...) instead of bullets
            safe_text = bullet.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            p = Paragraph(f"{idx + 1}.  {safe_text}", p_style)
            
            w, h = p.wrap(content_width, 1000) # Wrap to calculate height
            formatted_bullets.append((p, h))
            total_content_height += h + gap
            
        # Check if we have space for at least the header + first bullet
        # Only check for header space, let bullets flow naturally
        if y < 1.0 * inch:
            c.showPage()
            self._draw_page_header(c, header_data)
            y = self.height - 1.2 * inch
        
        # Section header with dark highlight background
        c.saveState()
        c.setFillColor(colors.HexColor('#1e293b'))  # Dark slate/black
        c.rect(Theme.MARGIN_X, y - 22, self.width - 2*Theme.MARGIN_X, 22, fill=1, stroke=0)
        c.setFont(Theme.FONT_HEAD, 10)
        c.setFillColor(colors.white)
        c.drawString(Theme.MARGIN_X + 10, y - 15, "EXECUTIVE SUMMARY FOR CLINICAL REVIEW")
        c.restoreState()
        
        y -= 30  # Space after header
        
        # Draw bullets with individual pagination (no box - allows flow across pages)
        for idx, (p, h) in enumerate(formatted_bullets):
            bullet_height = h + 16  # Include padding
            
            # Check if this bullet fits on current page
            if y - bullet_height < 0.7 * inch:
                c.showPage()
                self._draw_page_header(c, header_data)
                y = self.height - 1.2 * inch
            
            # Draw bullet with styling
            # Alternating subtle background for better readability
            if idx % 2 == 0:
                c.saveState()
                c.setFillColor(colors.HexColor('#f8fafc'))
                c.rect(Theme.MARGIN_X + 6, y - h - 8, self.width - 2*Theme.MARGIN_X - 12, h + 10, fill=1, stroke=0)
                c.restoreState()
            
            # Left accent bar
            c.saveState()
            c.setFillColor(colors.HexColor('#3b82f6'))  # Blue accent
            c.rect(Theme.MARGIN_X + 6, y - h - 5, 3, h + 8, fill=1, stroke=0)
            c.restoreState()
            
            # Draw bullet content
            p.drawOn(c, Theme.MARGIN_X + 18, y - h - 2)
            y -= (h + gap + 8)
            
        return y - Theme.SPACE_BLOCK

    def _preprocess_summary_like_frontend(self, text):
        """
        Mirror the case page preprocessSummary() so PDF parses the same structure.
        Converts numbered/all-caps headings into clear section boundaries.
        """
        if not text or not text.strip():
            return text
        # 1. Numbered sections: "1. PATIENT OVERVIEW" or "1. PATIENT OVERVIEW:" -> "\n\nPATIENT OVERVIEW\n"
        text = re.sub(
            r'^(\s*\d+\.\s+)([A-Z][A-Z\s&/]+?)(?:\s*:)?\s*$',
            r'\n\n\2\n',
            text,
            flags=re.MULTILINE
        )
        # 2. Standalone all-caps headings (min 5 chars), optional trailing ":"
        def replace_allcaps(m):
            heading = m.group(1)
            if len(heading) < 5 or heading.startswith('#'):
                return m.group(0)
            return f'\n\n{heading.strip()}\n'
        text = re.sub(
            r'^([A-Z][A-Z\s&/]+?)(?:\s*:)?\s*$',
            replace_allcaps,
            text,
            flags=re.MULTILINE
        )
        # 3. Collapse multiple newlines (match frontend)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _draw_summary_block(self, c, text, y, header_data):
        """Structured Narrative summary — same preprocessing as case page, then section-aware draw."""
        # 1. Strip redundant top boilerplate
        text = re.sub(r'^CLINICAL SUMMARY\s*Case Number:.*?\d+\s*', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'^Patient:.*?\s*', '', text, flags=re.IGNORECASE)
        # 2. Same preprocessing as case page (numbered + all-caps headings -> section breaks)
        text = self._preprocess_summary_like_frontend(text)
        # 3. Section headers we recognize (after preprocessing, titles are on their own lines)
        section_patterns = [
            r'PATIENT OVERVIEW',
            r'CHIEF COMPLAINT & PRESENTATION',
            r'CURRENT DIAGNOSES',
            r'MEDICATION SUMMARY',
            r'CLINICAL TIMELINE HIGHLIGHTS',
            r'KEY LAB/DIAGNOSTIC FINDINGS',
            r'PROCEDURES PERFORMED',
            r'POTENTIAL MISSING INFO'
        ]
        # Insert line breaks before each section header when inline (e.g. after preprocessing)
        for pattern in section_patterns:
            text = re.sub(f'({pattern})', r'\n\n\1', text, flags=re.IGNORECASE)
        
        # 3. Parse into sections
        sections = []
        current_section = None
        
        # Split by double newlines and process
        parts = text.split('\n\n')
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Normalize "1. PATIENT OVERVIEW" -> "PATIENT OVERVIEW" for matching (same as frontend)
            part_for_match = re.sub(r'^\s*\d+\.\s*', '', part)
            
            # Check if this part starts with a section header
            is_header = False
            for pattern in section_patterns:
                if re.match(pattern, part_for_match, re.IGNORECASE):
                    # Save previous section
                    if current_section and current_section['content']:
                        sections.append(current_section)
                    
                    # Extract header and content (use part_for_match so title has no "1. ")
                    match = re.match(f'({pattern})\\s*[-:]?\\s*(.*)', part_for_match, re.IGNORECASE | re.DOTALL)
                    if match:
                        current_section = {
                            'title': match.group(1).strip(),
                            'content': match.group(2).strip()
                        }
                    else:
                        current_section = {
                            'title': part_for_match[:50].strip(),  # fallback title, no number prefix
                            'content': ''
                        }
                    is_header = True
                    break
            
            # If not a header, add to current section content
            if not is_header and current_section:
                if current_section['content']:
                    current_section['content'] += ' '
                current_section['content'] += part
        
        # Don't forget the last section
        if current_section:
            sections.append(current_section)
        
        # If no sections found, treat entire text as one section
        if not sections:
            sections = [{'title': '', 'content': text.strip()}]
        
        # 4. Draw sections with professional formatting
        for i, section in enumerate(sections):
            # Check if we have reasonable space for section header + content
            # Need at least 1.5 inches to start a new section (prevents orphaned headers)
            if y < 1.5 * inch:
                c.showPage()
                self._draw_page_header(c, header_data)
                y = self.height - 1.2 * inch
            
            # Draw section header
            if section['title']:
                # Add spacing before section (except first)
                if i > 0:
                    y -= Theme.SPACE_PARA
                
                # Draw header with background
                c.saveState()
                c.setFillColor(colors.HexColor('#e2e8f0'))  # Light gray background
                c.roundRect(Theme.MARGIN_X + 6, y - 14, self.width - 2*Theme.MARGIN_X - 12, 16, 2, fill=1, stroke=0)
                
                c.setFont(Theme.FONT_HEAD, 10)
                c.setFillColor(Theme.PRIMARY)
                c.drawString(Theme.MARGIN_X + 12, y - 10, section['title'])
                c.restoreState()
                y -= Theme.SPACE_TIER_3
            
            # Draw section content
            if section['content']:
                # Clean up content - sanitize first
                content = self._sanitize_text(section['content']).strip()
                
                # 0. Remove markdown horizontal rules and separators
                content = re.sub(r'^\s*-{2,}\s*$', '', content, flags=re.MULTILINE)  # --- or ---- on own line
                content = re.sub(r'\n\s*-{2,}\s*\n', '\n', content)  # --- between newlines
                content = re.sub(r'\n\s*-{2,}\s*$', '', content)  # --- at end
                content = re.sub(r'^\s*-{2,}\s*\n', '', content)  # --- at start
                content = re.sub(r'-{2,}\s*#+', '', content)  # --- ## combined pattern
                content = re.sub(r'\s*-{2,}\s*#+\s*', ' ', content)  # Any --- ## with spaces
                
                # 1. Remove markdown headers (## or ###)
                content = re.sub(r'^\s*#+\s*', '', content, flags=re.MULTILINE)  # Remove ## at line start
                content = re.sub(r'\n\s*#+\s*\n', '\n', content)  # Remove ## on its own line
                content = re.sub(r'\n\s*#+\s*', '\n', content)  # Remove ## after newlines
                content = re.sub(r'\s+#+\s+', ' ', content)  # Remove ## in middle of text
                
                # 2. Remove ALL ** markers completely (for consistent non-bold formatting)
                # This ensures no bold inconsistencies in the output
                content = re.sub(r'\*\*+', '', content)  # Remove all ** (one or more asterisks together)
                content = re.sub(r'\*', '', content)  # Remove any remaining single *
                
                # 3. XML escape (do this BEFORE bullet conversion)
                content = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                
                # 4. Normalize bullet points - convert all to consistent •
                # Handle various bullet formats: -, *, •, ◦, ▪, etc.
                content = re.sub(r'^[\s]*[-•◦▪*→]\s+', '• ', content, flags=re.MULTILINE)  # Start of line
                content = re.sub(r'\n[\s]*[-•◦▪*→]\s+', '\n• ', content)  # After newline
                
                # 5. Ensure proper spacing after colons (for lists like "Medications:")
                content = re.sub(r':[\s]*\n', ':<br/>', content)  # Colon followed by newline
                
                # 6. Replace newlines with line breaks for proper formatting
                content = content.replace('\n', '<br/>')
                
                # 7. Clean up multiple consecutive <br/> tags (max 2)
                content = re.sub(r'(<br/>){3,}', '<br/><br/>', content)
                
                # Split content into smaller chunks for better pagination
                # Split by double line breaks to create natural paragraphs
                content_chunks = content.split('<br/><br/>')
                avail_w = self.width - 2*Theme.MARGIN_X - 24
                
                for chunk_idx, chunk in enumerate(content_chunks):
                    if not chunk.strip():
                        continue
                    
                    # Create paragraph for this chunk
                    p = Paragraph(chunk.strip(), self.style_body)
                    w, h = p.wrap(avail_w, self.height)
                    
                    # Check if we need a page break
                    if y - h < 0.8 * inch:
                        c.showPage()
                        self._draw_page_header(c, header_data)
                        y = self.height - 1.2 * inch
                        w, h = p.wrap(avail_w, self.height)
                    
                    # Draw this chunk
                    p.drawOn(c, Theme.MARGIN_X + 12, y - h)
                    y -= h + 6  # Small spacing between chunks
        
        return y - 10

    def _draw_medications_list(self, c, meds, y, header_data):
        """Professional Tabular Medication List with Zebra Striping and grouping container."""
        if not meds:
            c.setFont(Theme.FONT_ITALIC, 9)
            c.setFillColor(Theme.TEXT_SEC)
            c.drawString(Theme.MARGIN_X + 10, y, "No active medications detected.")
            return y - Theme.SPACE_BLOCK

        # Grouping: indent table for visual belonging
        table_left = Theme.MARGIN_X + Theme.CONTENT_INDENT
        table_width = self.width - 2*Theme.MARGIN_X - 2*Theme.CONTENT_INDENT

        # Table Header (Muted Light Gray)
        headers = ["MEDICATION", "DOSAGE", "FREQUENCY", "START DATE", "END DATE"]
        # Adjusted col widths for better wrapping (Medication gets most space)
        col_widths = [
            table_width * 0.30, table_width * 0.20, table_width * 0.20,
            table_width * 0.15, table_width * 0.15,
        ]

        def draw_header(canvas, cur_y):
            # Draw header background on TOP layer
            canvas.saveState()
            canvas.setFillColor(Theme.TABLE_HEADER)
            canvas.roundRect(table_left, cur_y - 20, table_width, 24, 2, fill=1, stroke=0)
            canvas.restoreState()
            
            # Draw header text
            canvas.setFont(Theme.FONT_HEAD, 9)
            canvas.setFillColor(Theme.PRIMARY)
            lx = table_left + Theme.TABLE_PADDING
            for i, h in enumerate(headers):
                 canvas.drawString(lx, cur_y - 13, h)
                 lx += col_widths[i]

        draw_header(c, y)
        y -= 32  # Increased spacing to prevent any overlap

        for idx, med in enumerate(meds):
            if not isinstance(med, dict): continue
            
            # Prepare Content
            name = self._sanitize_text(med.get('name', 'Unknown'))
            dosage = self._sanitize_text(med.get('dosage', '-'))
            freq = self._sanitize_text(med.get('frequency', '-'))
            start_d = self._sanitize_text(med.get('start_date', '-'))
            end_d = med.get('end_date') # None check handled below
            
            # Format Status (Fix #8: Functional Color)
            status_text = "Ongoing" if not end_d else "Ended"
            status_color = Theme.TEXT_GREEN if status_text == "Ongoing" else Theme.TEXT_SEC
            
            # Prepare Paragraphs
            p_name = Paragraph(str(name), self.style_body)
            p_dosage = Paragraph(str(dosage), self.style_body)
            p_freq = Paragraph(str(freq), self.style_body)
            
            # Calculate Heights
            w_n, h_n = p_name.wrap(col_widths[0] - 10, 1000)
            w_d, h_d = p_dosage.wrap(col_widths[1] - 10, 1000)
            w_f, h_f = p_freq.wrap(col_widths[2] - 10, 1000)
            
            row_h = max(24, h_n + 12, h_d + 12, h_f + 12)
            
            # Page Break Check
            if y - row_h < 1.0 * inch:
                c.showPage()
                self._draw_page_header(c, header_data)
                y = self.height - 1.2 * inch
                draw_header(c, y)
                y -= 32  # Match the spacing after header
            
            # Zebra Striping (draw BELOW the current y position to avoid header overlap)
            if idx % 2 == 0:
                c.saveState()
                c.setFillColor(Theme.SUBTLE_BG)
                c.rect(table_left, y - row_h, table_width, row_h - 2, fill=1, stroke=0)
                c.restoreState()

            # Draw
            lx = table_left + Theme.TABLE_PADDING
            
            # 1. Med Name (Top Align)
            p_name.drawOn(c, lx, y - 10 - h_n)
            lx += col_widths[0]
            
            # 2. Dosage
            p_dosage.drawOn(c, lx, y - 10 - h_d)
            lx += col_widths[1]
            
            # 3. Frequency
            p_freq.drawOn(c, lx, y - 10 - h_f)
            lx += col_widths[2]
            
            # 4. Dates
            c.setFont(Theme.FONT_BODY, 9)
            c.setFillColor(Theme.TEXT_MAIN)
            date_range = f"{start_d} - {end_d if end_d else ''}"
            c.drawString(lx, y - 16, date_range)
            lx += col_widths[3]
            
            # 5. Status (Fix #8)
            c.setFont(Theme.FONT_SEMIBOLD, Theme.SIZE_SMALL)
            c.setFillColor(status_color)
            c.drawString(lx, y - 16, status_text)
            
            y -= row_h
            
        return y

    def _draw_vitals_table(self, c, ranges, y, header_data):
        # FIX #6: Collapse Repetitive Sections Visually (Context Header)
        c.setFont(Theme.FONT_ITALIC, 9)
        c.setFillColor(Theme.TEXT_SEC)
        c.drawString(Theme.MARGIN_X, y, "Showing key daily ranges; detailed readings summarized below")
        y -= 14

        # Header
        headers = ["DATE", "BP RANGE", "HR RANGE", "O2 RANGE", "TEMP RANGE"]
        col_w = (self.width - 2*Theme.MARGIN_X) / 5
        
        def draw_header(canvas, cur_y):
            # Draw header background on TOP layer
            canvas.saveState()
            canvas.setFillColor(Theme.TABLE_HEADER)
            canvas.roundRect(Theme.MARGIN_X, cur_y - 20, self.width - 2*Theme.MARGIN_X, 24, 2, fill=1, stroke=0)
            canvas.restoreState()
            
            # Draw header text
            canvas.setFont(Theme.FONT_HEAD, 9)
            canvas.setFillColor(Theme.PRIMARY)
            for i, h in enumerate(headers):
                 canvas.drawString(Theme.MARGIN_X + (i*col_w) + 5, cur_y - 13, h)

        draw_header(c, y)
        y -= 32  # Increased spacing to prevent any overlap
        
        # Check if we have any valid vital signs data
        has_valid_data = False
        if ranges:
            for row in ranges:
                if isinstance(row, dict):
                    # Check if row has any actual data (not just empty values)
                    if any(row.get(k) for k in ['date', 'bp', 'hr', 'spo2', 'temp']):
                        has_valid_data = True
                        break
        
        # If no vital signs data, show at least one row with "--"
        if not has_valid_data:
            row_h = 20
            c.saveState()
            c.setFillColor(Theme.SUBTLE_BG)
            c.rect(Theme.MARGIN_X, y - row_h, self.width - 2*Theme.MARGIN_X, row_h - 2, fill=1, stroke=0)
            c.restoreState()
            
            c.setFont(Theme.FONT_BODY, 9)
            c.setFillColor(Theme.TEXT_SEC)  # Gray text for no data
            for i in range(5):
                c.drawString(Theme.MARGIN_X + (i*col_w) + 5, y - 8, "--")
            y -= row_h
            return y - 10
        
        # Draw rows with actual data
        valid_row_idx = 0
        for idx, row in enumerate(ranges):
            if not isinstance(row, dict): 
                continue
            
            # Skip rows with no actual data
            if not any(row.get(k) for k in ['date', 'bp', 'hr', 'spo2', 'temp']):
                continue

            row_h = 20
            if y < 1.0 * inch:
                c.showPage()
                self._draw_page_header(c, header_data)
                y = self.height - 1.2 * inch
                draw_header(c, y)
                y -= 32  # Match the spacing after header

            # Zebra Striping (draw BELOW current y to avoid overlap)
            if valid_row_idx % 2 == 0:
                c.saveState()
                c.setFillColor(Theme.SUBTLE_BG)
                c.rect(Theme.MARGIN_X, y - row_h, self.width - 2*Theme.MARGIN_X, row_h - 2, fill=1, stroke=0)
                c.restoreState()

            def fmt(k):
                v = row.get(k)
                if not v: return "--"
                if isinstance(v, dict): return f"{v.get('min', '?')}-{v.get('max', '?')}"
                return self._sanitize_text(v)
                
            vals = [self._sanitize_text(row.get('date', '--')), fmt('bp'), fmt('hr'), fmt('spo2'), fmt('temp')]
            
            c.setFont(Theme.FONT_BODY, 9)
            c.setFillColor(Theme.TEXT_MAIN)
            for i, v in enumerate(vals):
                c.drawString(Theme.MARGIN_X + (i*col_w) + 5, y - 8, v)
            y -= row_h
            valid_row_idx += 1
            
        return y - 10

    def _draw_labs_table(self, c, labs, y, header_data):
        if not labs:
            c.setFont(Theme.FONT_ITALIC, 9)
            c.setFillColor(Theme.TEXT_SEC)
            c.drawString(Theme.MARGIN_X + 10, y, "No recent lab results found.")
            return y - 20

        # FIX #6: Collapse Repetitive Sections Visually (Context Header)
        c.setFont(Theme.FONT_ITALIC, 9)
        c.setFillColor(Theme.TEXT_SEC)
        c.drawString(Theme.MARGIN_X, y, "Abnormal results highlighted in red; showing most recent values")
        y -= 14

        # Header (4 columns - STATUS removed)
        headers = ["DATE", "TEST NAME", "RESULT", "RANGE"]
        col_w = (self.width - 2*Theme.MARGIN_X) / 4
        
        def draw_header(canvas, cur_y):
            # Draw header background on TOP layer
            canvas.saveState()
            canvas.setFillColor(Theme.TABLE_HEADER)
            canvas.roundRect(Theme.MARGIN_X, cur_y - 20, self.width - 2*Theme.MARGIN_X, 24, 2, fill=1, stroke=0)
            canvas.restoreState()
            
            # Draw header text
            canvas.setFont(Theme.FONT_HEAD, 9)
            canvas.setFillColor(Theme.PRIMARY)
            for i, h in enumerate(headers):
                 canvas.drawString(Theme.MARGIN_X + (i*col_w) + 5, cur_y - 13, h)

        draw_header(c, y)
        y -= 32  # Increased spacing to prevent any overlap

        for idx, lab in enumerate(labs):
            if not isinstance(lab, dict): continue

            # Prepare Data
            date = self._sanitize_text(lab.get('date', '-'))
            name = self._sanitize_text(lab.get('test_name', '-'))
            res = self._sanitize_text(f"{lab.get('value', '-')} {lab.get('unit', '')}")
            # Try multiple possible field names for range
            rng = (lab.get('reference_range') or 
                   lab.get('range') or 
                   lab.get('normal_range') or 
                   lab.get('ref_range') or '-')
            rng = self._sanitize_text(str(rng))
            
            is_abnormal = lab.get('abnormal', False)
            val_color = Theme.TEXT_MAIN
            if is_abnormal:
                val_color = Theme.TEXT_RED

            # Paragraphs for potentially wrapped content (Name, Result, Range)
            style_normal = self.style_body
            style_alert = ParagraphStyle('Alert', parent=self.style_body, textColor=val_color)
            
            p_name = Paragraph(str(name), style_normal)
            p_res = Paragraph(str(res), style_alert if is_abnormal else style_normal)
            p_rng = Paragraph(str(rng), style_normal)
            
            # Wrap
            w_n, h_n = p_name.wrap(col_w - 10, 1000)
            w_r, h_r = p_res.wrap(col_w - 10, 1000)
            w_g, h_g = p_rng.wrap(col_w - 10, 1000)
            
            row_h = max(24, h_n + 12, h_r + 12, h_g + 12)

            if y - row_h < 1.0 * inch:
                c.showPage()
                self._draw_page_header(c, header_data)
                y = self.height - 1.2 * inch
                draw_header(c, y)
                y -= 32  # Match the spacing after header

            # Zebra Striping (draw BELOW current y to avoid overlap)
            if idx % 2 == 0:
                c.saveState()
                c.setFillColor(Theme.SUBTLE_BG)
                c.rect(Theme.MARGIN_X, y - row_h, self.width - 2*Theme.MARGIN_X, row_h - 2, fill=1, stroke=0)
                c.restoreState()

            # Draw Columns (4 columns: Date, Test Name, Result, Range)
            # Date (String)
            c.setFont(Theme.FONT_BODY, 9)
            c.setFillColor(Theme.TEXT_MAIN)
            c.drawString(Theme.MARGIN_X + 5, y - 14, str(date))
            
            # Others (Paragraphs)
            text_top = y - 4
            p_name.drawOn(c, Theme.MARGIN_X + col_w + 5, text_top - h_n - 4)
            p_res.drawOn(c, Theme.MARGIN_X + 2*col_w + 5, text_top - h_r - 4)
            p_rng.drawOn(c, Theme.MARGIN_X + 3*col_w + 5, text_top - h_g - 4)
            
            y -= row_h
            
        return y - 10

    def _draw_missing_info_box(self, c, items, y):
        if not items: return y
        
        # 1. Box Geometry Calculation
        c.setFont(Theme.FONT_HEAD, 9) 
        item_h = len(items) * 16 + 15
        
        # Check space
        if y - item_h < 1*inch:
             c.showPage()
             y = self.height - 1.0*inch
        
        # 2. Draw Subtle Amber Box (Professional Alert)
        c.saveState()
        c.setFillColor(Theme.WARNING_BG)
        c.setStrokeColor(Theme.BORDER_LIGHT)
        c.roundRect(Theme.MARGIN_X, y - item_h, self.width - 2*Theme.MARGIN_X, item_h, 4, fill=1, stroke=1)
        
        # 3. Visual Anchor Ribbon (Amber)
        c.setFillColor(Theme.WARNING_AMBER)
        c.rect(Theme.MARGIN_X, y - item_h, 3, item_h, fill=1, stroke=0)
        c.restoreState()
        
        curr = y - 16
        for item in items:
            c.setFillColor(Theme.TEXT_MAIN)
            c.setFont(Theme.FONT_BODY, 9)
            # Dot icon
            c.setFillColor(Theme.WARNING_AMBER)
            c.drawString(Theme.MARGIN_X + 15, curr, "•")
            c.setFillColor(Theme.TEXT_MAIN)
            c.drawString(Theme.MARGIN_X + 25, curr, f"{item}")
            curr -= 16
            
        return y - item_h - 20

    def _draw_source_index(self, c, files, y, header_data):
        # Header Row (Corporate Light Gray)
        def draw_header(canvas, cur_y):
            canvas.setFillColor(Theme.TABLE_HEADER)
            canvas.roundRect(Theme.MARGIN_X, cur_y - 12, self.width - 2*Theme.MARGIN_X, 16, 2, fill=1, stroke=0)
            canvas.setFillColor(Theme.PRIMARY)
            canvas.setFont(Theme.FONT_HEAD, 9)
            canvas.drawString(Theme.MARGIN_X + 5, cur_y - 8, "FILE NAME")
            # Move DETAILS to right side
            canvas.drawRightString(self.width - Theme.MARGIN_X - 5, cur_y - 8, "DETAILS")

        draw_header(c, y)
        y -= Theme.SPACE_TIER_3
        
        c.setFont(Theme.FONT_BODY, 9)
        c.setFillColor(Theme.TEXT_MAIN)
        
        for idx, f in enumerate(files):
            row_h = 24
            if y < 1.0 * inch:
                c.showPage()
                self._draw_page_header(c, header_data)
                y = self.height - 1.2 * inch 
                draw_header(c, y)
                y -= Theme.SPACE_TIER_3
            
            # Zebra Striping (Subtle Fade)
            if idx % 2 == 0:
                c.setFillColor(Theme.SUBTLE_BG)
                c.rect(Theme.MARGIN_X, y - row_h + 4, self.width - 2*Theme.MARGIN_X, row_h, fill=1, stroke=0)

            c.setFillColor(Theme.TEXT_MAIN)
            # Truncate filename if too long to prevent overlap with details
            filename = f.file_name
            max_width = self.width - 2*Theme.MARGIN_X - 180  # Reserve 180px for details
            if c.stringWidth(filename, Theme.FONT_BODY, 9) > max_width:
                while c.stringWidth(filename + "...", Theme.FONT_BODY, 9) > max_width and len(filename) > 0:
                    filename = filename[:-1]
                filename += "..."
            
            c.drawString(Theme.MARGIN_X + 5, y - 10, filename)
            # Draw details on right side
            details = f"{f.page_count} pages • {f.uploaded_at.strftime('%Y-%m-%d')}"
            c.drawRightString(self.width - Theme.MARGIN_X - 5, y - 10, details)
            
            y -= row_h
        return y

    def _highlight_text(self, text):
        """Regex highlight for abnormal keywords (Muted Clinical Red)"""
        keywords = [r'high', r'severe', r'critical', r'abnormal', r'failure', r'distress']
        for k in keywords:
            text = re.sub(f'(?i)({k})', f"<b><font color='{Theme.ALARM_MUTED.hexval()}'>\\1</font></b>", text)
        return text

pdf_generator_service_v2 = PDFGeneratorServiceV2()
