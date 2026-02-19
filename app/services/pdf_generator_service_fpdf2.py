"""
PDF Generator Service (fpdf2)
UM Case Summary PDF with Markdown support for narrative content.

Default page 1: Patient Grid (case/patient info) + Table of Contents (clickable links to sections).
Section order: (optional cover) -> Page 1: Patient Grid + TOC -> Section 1: Executive Summary
-> Section 2: Clinical Narrative -> ... -> Section 7: Source Index -> Footer.
"""

import io
import logging
import os
import re
from datetime import datetime
from typing import List, Optional, Any

from fpdf import FPDF
from fpdf.fonts import FontFace
from fpdf.enums import TableHeadingsDisplay
from markdown_it import MarkdownIt

from app.services.pdf_utils import extract_header_data, sanitize_text
from app.services.pdf_constants import (
    BODY_FONT_SIZE,
    BODY_LINE_HEIGHT,
    PATIENT_GRID_FONT_BOLD,
    PATIENT_GRID_FONT_SIZE,
    TABLE_LINE_HEIGHT_PT,
    COVER_SUBTITLE_SIZE,
    COVER_TITLE_SIZE,
    EXEC_SUMMARY_FONT_SIZE,
    FOOTER_FONT_SIZE,
    HEADER_CASE_ID_SIZE,
    HEADER_HEIGHT_FIRST_MM,
    HEADER_HEIGHT_OTHER_MM,
    HEADER_MAIN_SIZE,
    HEADER_MAIN_SIZE_LARGE,
    HEADER_SUB_SIZE,
    HEADER_SUB_SIZE_LARGE,
    HEADER_BG_DARK,
    HEADER_BG_GRADIENT_LIGHT,
    HEADER_TEXT_WHITE,
    HEADER_SUBTITLE_GRAY,
    LAB_ABNORMAL_STYLE,
    NARRATIVE_HEADING_BG,
    NARRATIVE_LINE_HEIGHT,
    PLACEHOLDER_COLOR,
    SECTION_BAR_FILL,
    SECTION_BAR_HEIGHT_MM,
    SECTION_BAR_PADDING_MM,
    SECTION_BAR_TEXT,
    SECTION_H1_SIZE,
    SECTION_H2_SIZE,
    EXEC_SUMMARY_HEADER_FILL,
    EXEC_SUMMARY_HEADER_TEXT,
    EXEC_SUMMARY_ACCENT_BORDER,
    NARRATIVE_FONT_SIZE,
    SECTION_PAGE_BREAK_THRESHOLD_MM,
    SECTION_TITLE_COLOR,
    TABLE_HEADER_STYLE,
    TABLE_ZEBRA_FILL,
    TAG_STYLES,
    TAG_STYLES_NARRATIVE,
    TOC_ENTRY_STYLE,
    TOC_ROW_LINE_HEIGHT_MM,
    TOC_SUBTITLE_SIZE,
    TOC_TABLE_HEADER_STYLE,
)

logger = logging.getLogger(__name__)

# Markdown to HTML (CommonMark + tables)
_md = MarkdownIt("commonmark", {"breaks": True, "html": True}).enable("table").enable("strikethrough")


def _wrap_narrative_headings_with_background(html: str) -> str:
    """Wrap each h1–h6 in a single-cell table with bgcolor so they render as highlighted subsections."""
    # Match headings with optional attributes and content (content: no nested <h*>, allow other inline tags)
    def repl(m):
        level, inner = m.group(1), m.group(2)
        return (
            f'<table cellpadding="3" style="width:100%"><tr><td bgcolor="{NARRATIVE_HEADING_BG}">'
            f"<h{level}>{inner}</h{level}>"
            f"</td></tr></table>"
        )

    return re.sub(r"<h([1-6])(?:\s[^>]*)?>([\s\S]*?)</h\1>", repl, html)


def _markdown_to_html(text: str) -> str:
    if not text or not text.strip():
        return ""
    return _md.render(text.strip())


def _executive_summary_to_points(text: str) -> List[str]:
    """Split executive summary into a list of point strings (no numbers). Caller renders with '1. ', '2. ', etc. and controls spacing."""
    if not text or not text.strip():
        return []
    text = re.sub(r"\n{2,}", "\n\n", text.strip())
    blocks = re.split(r"\n\s*\n", text)
    points = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        for i, ln in enumerate(lines):
            ln = re.sub(r"^[\s\-*•]\s*", "", ln)
            ln = re.sub(r"^\d+[.)]\s*", "", ln)
            lines[i] = ln
        points.append(" ".join(lines) if lines else block)
    return points


def _ensure_section_page(pdf: FPDF) -> None:
    """Start a new page if too close to bottom so sections don't start with one line."""
    if pdf.get_y() > pdf.h - pdf.b_margin - SECTION_PAGE_BREAK_THRESHOLD_MM:
        pdf.add_page()


class CaseSummaryPDF(FPDF):
    """FPDF subclass with header/footer. Uses constants for heights and colors."""

    def __init__(self, header_data: dict, logo_path: str = ""):
        super().__init__()
        self.header_data = header_data
        self.logo_path = logo_path

    def header(self):
        """Header: logo, BRIGHTCONE, subtitle, Case ID. First page 18mm, others 13mm."""
        page_no = self.page_no()
        H = HEADER_HEIGHT_FIRST_MM if page_no == 1 else HEADER_HEIGHT_OTHER_MM
        self.t_margin = H
        pad = 15
        logo_size = min(10, max(6, H - 5))
        logo_y = max(0, (H - logo_size) / 2)
        self.set_fill_color(*HEADER_BG_DARK)
        self.rect(0, 0, self.w, H, "F")
        strip_h = 2
        n_steps = 50
        step_h = strip_h / n_steps
        for i in range(n_steps):
            t = (i + 0.5) / n_steps
            r = int(HEADER_BG_DARK[0] + (HEADER_BG_GRADIENT_LIGHT[0] - HEADER_BG_DARK[0]) * t)
            g = int(HEADER_BG_DARK[1] + (HEADER_BG_GRADIENT_LIGHT[1] - HEADER_BG_DARK[1]) * t)
            b = int(HEADER_BG_DARK[2] + (HEADER_BG_GRADIENT_LIGHT[2] - HEADER_BG_DARK[2]) * t)
            self.set_fill_color(r, g, b)
            self.rect(0, H - strip_h + i * step_h, self.w, step_h, "F")
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                self.image(self.logo_path, x=pad, y=logo_y, w=logo_size, h=logo_size)
            except Exception:
                pass
        text_x = pad + logo_size + 6
        line_h = 5 if H < 16 else 7
        gap_title_subtitle = 0.2
        text_y = max(0, 1.2)
        font_main = HEADER_MAIN_SIZE if H < 16 else HEADER_MAIN_SIZE_LARGE
        font_subtitle = HEADER_SUB_SIZE if H < 16 else HEADER_SUB_SIZE_LARGE
        self.set_text_color(*HEADER_TEXT_WHITE)
        self.set_font("Helvetica", "B", font_main)
        self.set_xy(text_x, text_y)
        self.cell(0, line_h, "BRIGHTCONE")
        self.set_font("Helvetica", "", font_subtitle)
        self.set_text_color(*HEADER_SUBTITLE_GRAY)
        self.set_xy(text_x, text_y + line_h + gap_title_subtitle)
        self.cell(0, line_h, "UTILIZATION MANAGEMENT INTELLIGENCE")
        case_id = self.header_data.get("case_number", "")
        patient_name = sanitize_text(self.header_data.get("patient_name", "") or "")
        self.set_font("Helvetica", "B", HEADER_CASE_ID_SIZE)
        self.set_text_color(*HEADER_TEXT_WHITE)
        self.set_xy(0, text_y)
        self.cell(self.w - pad, line_h, f"CASE ID: {case_id}", align="R")
        # Patient name below Case ID, right-aligned so it ends at same horizontal position
        if patient_name:
            gap = 0.8
            self.set_font("Helvetica", "", HEADER_SUB_SIZE)
            self.set_text_color(*HEADER_SUBTITLE_GRAY)
            self.set_xy(0, text_y + line_h + gap)
            self.cell(self.w - pad, line_h, patient_name, align="R")
        self.set_text_color(0, 0, 0)
        self.t_margin = H + 4
        self.set_y(H + 4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", FOOTER_FONT_SIZE)
        self.set_text_color(100, 116, 139)
        left = "Brightcone AI - Utilization Management Summary - Confidential Healthcare Data"
        gen = self.header_data.get("generated_by") or ""
        if gen:
            left += f"  |  Generated by {gen}"
        self.cell(0, 5, left, align="L")
        self.cell(0, 5, f"{datetime.now().strftime('%Y-%m-%d %H:%M')} - Page {self.page_no()}", align="R")
        self.ln(5)


class PDFGeneratorServiceFPDF2:
    """UM Case Summary PDF generator using fpdf2 (Markdown support for narrative)."""

    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.logo_path = os.path.join(base_dir, "static", "images", "logo.png")

    def generate_case_pdf(
        self,
        case,
        extraction,
        case_files: List,
        patient_dob: Optional[str] = None,
        generated_by: Optional[str] = None,
        add_cover_page: bool = False,
        add_toc: bool = True,
    ) -> bytes:
        """Generate PDF bytes for the given case, extraction, and case_files."""
        header_data = extract_header_data(case, extraction, patient_dob)
        if generated_by:
            header_data["generated_by"] = generated_by
        pdf = CaseSummaryPDF(header_data=header_data, logo_path=self.logo_path)
        pdf.set_auto_page_break(True, margin=18)
        pdf.set_margins(left=15, top=HEADER_HEIGHT_FIRST_MM + 4, right=15)
        pdf.add_page()
        # PDF metadata for document properties
        case_id = header_data.get("case_number", "")
        pdf.set_title(f"UM Case Summary - {case_id}" if case_id else "UM Case Summary")
        pdf.set_author("Brightcone")
        pdf.set_creator("Brightcone AI")
        pdf.set_font("Helvetica", size=BODY_FONT_SIZE)

        # Optional cover page
        if add_cover_page:
            self._add_cover_page(pdf, header_data)
            pdf.add_page()

        # ----- Page 1 (default): Patient grid + Table of contents -----
        self._add_patient_grid(pdf, header_data)
        toc_links = {}
        section_pages: dict = {}
        if add_toc:
            # Two-pass when TOC is enabled: pass 1 collects section page numbers, pass 2 builds PDF with TOC page nos
            toc_links = self._add_toc_page(pdf, header_data, section_pages=None)
            pdf.add_page()  # Section 1 starts on next page so page 1 = Grid + TOC only
            self._add_sections_body(
                pdf, extraction, case_files, header_data, toc_links, add_toc, section_pages_out=section_pages
            )
            # Second pass: rebuild with TOC showing page numbers
            pdf = CaseSummaryPDF(header_data=header_data, logo_path=self.logo_path)
            pdf.set_auto_page_break(True, margin=18)
            pdf.set_margins(left=15, top=HEADER_HEIGHT_FIRST_MM + 4, right=15)
            pdf.add_page()
            pdf.set_title(f"UM Case Summary - {case_id}" if case_id else "UM Case Summary")
            pdf.set_author("Brightcone")
            pdf.set_creator("Brightcone AI")
            pdf.set_font("Helvetica", size=BODY_FONT_SIZE)
            if add_cover_page:
                self._add_cover_page(pdf, header_data)
                pdf.add_page()
            self._add_patient_grid(pdf, header_data)
            toc_links = self._add_toc_page(pdf, header_data, section_pages=section_pages)
            pdf.add_page()
            self._add_sections_body(
                pdf, extraction, case_files, header_data, toc_links, add_toc, section_pages_out=None
            )
        else:
            self._add_sections_body(
                pdf, extraction, case_files, header_data, toc_links, add_toc, section_pages_out=None
            )

        out = pdf.output()
        return bytes(out) if isinstance(out, (bytearray, memoryview)) else out

    def _add_sections_body(
        self,
        pdf: FPDF,
        extraction,
        case_files: List,
        header_data: dict,
        toc_links: dict,
        add_toc: bool,
        section_pages_out: Optional[dict] = None,
    ) -> None:
        """Add Sections 1-7. When section_pages_out is provided, record page number at each section link."""
        def _record(key: str) -> None:
            if section_pages_out is not None and key in toc_links:
                section_pages_out[key] = pdf.page_no()

        # ----- Section 1: Executive Summary (highlighted so users read it first) -----
        if extraction and getattr(extraction, "executive_summary", None) and extraction.executive_summary:
            if add_toc and "exec_summary" in toc_links:
                pdf.set_link(toc_links["exec_summary"], page=pdf.page_no(), y=pdf.get_y())
                _record("exec_summary")
            self._add_executive_summary_header(pdf, "SECTION 1: Executive Summary")
            content_start_y = pdf.get_y()
            pdf.set_font("Helvetica", "", EXEC_SUMMARY_FONT_SIZE)
            points = _executive_summary_to_points(extraction.executive_summary)
            if points:
                for i, p in enumerate(points):
                    line = f"{i + 1}. {sanitize_text(p)}"
                    pdf.multi_cell(0, BODY_LINE_HEIGHT, line)
                    pdf.ln(2)
            else:
                # Fallback: render raw summary when point parsing yields nothing
                raw = sanitize_text(extraction.executive_summary.strip())
                if raw:
                    pdf.multi_cell(0, BODY_LINE_HEIGHT, raw)  # font already EXEC_SUMMARY_FONT_SIZE
            # Accent border along left edge of Executive Summary content
            content_end_y = pdf.get_y()
            pdf.set_draw_color(*EXEC_SUMMARY_ACCENT_BORDER)
            pdf.set_line_width(0.8)
            pdf.line(pdf.l_margin, content_start_y, pdf.l_margin, content_end_y)
            pdf.set_draw_color(0, 0, 0)
            pdf.set_line_width(0.2)
            pdf.ln(8)

        # ----- Section 2: Comprehensive Clinical Narrative -----
        _ensure_section_page(pdf)
        if add_toc and "narrative" in toc_links:
            pdf.set_link(toc_links["narrative"], page=pdf.page_no(), y=pdf.get_y())
            _record("narrative")
        self._add_section_header(pdf, "SECTION 2: Comprehensive Clinical Narrative", level=1)
        pdf.set_font("Helvetica", "", NARRATIVE_FONT_SIZE)
        if extraction and extraction.summary:
            cleaned = self._clean_summary_text(extraction.summary)
            raw = sanitize_text(cleaned)
            html = _markdown_to_html(raw)
            if html:
                # Remove horizontal rules (AI often adds these; we don't want them in the PDF)
                html = re.sub(r'<hr\s*/?\s*>', '', html, flags=re.IGNORECASE)
                # Add spacing after each list item (bullets/numbered) for readability
                html = html.replace("</li>", "</li><br>")  # one br = 50% of previous spacing
                # More line spacing for all normal text: inject line-height into p, ul, ol (fpdf2 honors style="line-height: N")
                for tag in ("p", "ul", "ol"):
                    html = re.sub(rf"<{tag}(\s|>)", rf'<{tag} style="line-height: {NARRATIVE_LINE_HEIGHT}"\1', html)
                # Highlight subsection headings (h1–h6) with background so they act as subsections under Section 2
                html = _wrap_narrative_headings_with_background(html)
                pdf.write_html(sanitize_text(html), tag_styles=TAG_STYLES_NARRATIVE)
        else:
            pdf.set_font("Helvetica", "I", NARRATIVE_FONT_SIZE)
            pdf.set_text_color(*PLACEHOLDER_COLOR)
            pdf.cell(0, BODY_LINE_HEIGHT, "No comprehensive clinical narrative available.", ln=True)
            pdf.set_text_color(0, 0, 0)
        pdf.ln(8)

        # ----- Section 3: Clinical Chronology -----
        _ensure_section_page(pdf)
        if add_toc and "chronology" in toc_links:
            pdf.set_link(toc_links["chronology"], page=pdf.page_no(), y=pdf.get_y())
            _record("chronology")
        self._add_section_header(pdf, "SECTION 3: Clinical Chronology", level=1)
        self._add_section_header(pdf, "Clinical Timeline", level=2)
        if extraction and extraction.timeline:
            self._add_timeline_table(pdf, extraction.timeline, header_data)
        else:
            pdf.set_font("Helvetica", "I", BODY_FONT_SIZE)
            pdf.set_text_color(*PLACEHOLDER_COLOR)
            pdf.cell(0, BODY_LINE_HEIGHT, "No timeline events extracted from source documents.", ln=True)
            pdf.set_text_color(0, 0, 0)
        pdf.ln(8)

        # ----- Section 4: Current Medications -----
        _ensure_section_page(pdf)
        if add_toc and "medications" in toc_links:
            pdf.set_link(toc_links["medications"], page=pdf.page_no(), y=pdf.get_y())
            _record("medications")
        self._add_section_header(pdf, "SECTION 4: Current Medications", level=1)
        self._add_section_header(pdf, "Medication Details", level=2)
        meds = []
        if extraction and extraction.extracted_data:
            meds = extraction.extracted_data.get("medications", [])
        self._add_medications_table(pdf, meds, header_data)
        pdf.ln(6)

        # ----- Section 5: Laboratory Results -----
        _ensure_section_page(pdf)
        if add_toc and "labs" in toc_links:
            pdf.set_link(toc_links["labs"], page=pdf.page_no(), y=pdf.get_y())
            _record("labs")
        self._add_section_header(pdf, "SECTION 5: Laboratory Results", level=1)
        labs = []
        if extraction and extraction.extracted_data:
            labs = extraction.extracted_data.get("labs", [])
        self._add_labs_table(pdf, labs, header_data)
        pdf.ln(6)

        # ----- Section 6: Vital Signs -----
        _ensure_section_page(pdf)
        if add_toc and "vitals" in toc_links:
            pdf.set_link(toc_links["vitals"], page=pdf.page_no(), y=pdf.get_y())
            _record("vitals")
        self._add_section_header(pdf, "SECTION 6: Vital Signs", level=1)
        self._add_section_header(pdf, "Vital Signs Monitoring", level=2)
        vitals_ranges = []
        raw_vitals: List[dict] = []
        if extraction and extraction.extracted_data:
            ed = extraction.extracted_data
            raw = ed.get("vitals_per_day_ranges", [])
            if isinstance(raw, dict):
                vitals_ranges = [raw[k] for k in sorted(raw.keys())]
            else:
                vitals_ranges = raw if isinstance(raw, list) else []
            raw_vitals = ed.get("vitals") or []
            if not isinstance(raw_vitals, list):
                raw_vitals = []
        self._add_vitals_table(pdf, vitals_ranges, header_data, raw_vitals=raw_vitals)
        pdf.ln(6)

        # ----- Section 7: Source Documents -----
        _ensure_section_page(pdf)
        if add_toc and "sources" in toc_links:
            pdf.set_link(toc_links["sources"], page=pdf.page_no(), y=pdf.get_y())
            _record("sources")
        self._add_section_header(pdf, "SECTION 7: Source Documents", level=1)
        self._add_source_index(pdf, case_files, header_data)

    def _clean_summary_text(self, text: str) -> str:
        """Remove boilerplate headers/metadata and horizontal rules that LLM adds to summary."""
        # Remove "CLINICAL SUMMARY" title
        text = re.sub(r'^\s*CLINICAL SUMMARY\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        # Remove "Case Number: XXX"
        text = re.sub(r'^\s*Case Number:.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        # Remove "Patient: XXX"
        text = re.sub(r'^\s*Patient:.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        # Remove "Summary Date: XXX"
        text = re.sub(r'^\s*Summary Date:.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        # Remove markdown horizontal rules (---, ***, ___) so they don't appear as lines in PDF
        text = re.sub(r'^\s*(-{3,}|\*{3,}|_{3,})\s*$', '', text, flags=re.MULTILINE)
        # Collapse multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _add_section_header(self, pdf: FPDF, title: str, level: int = 1):
        """Add actual section heading: brand blue bar, white text, left-aligned (no tab indent)."""
        if level == 1:
            pdf.ln(6)
            pdf.set_fill_color(*SECTION_BAR_FILL)
            pdf.set_text_color(*SECTION_BAR_TEXT)
            pdf.set_font("Helvetica", "B", SECTION_H1_SIZE)
            x = pdf.l_margin
            w = pdf.w - pdf.l_margin - pdf.r_margin
            y = pdf.get_y()
            pdf.set_x(x)
            pdf.rect(x, y, w, SECTION_BAR_HEIGHT_MM, "F")
            pdf.set_xy(x + 2, y + 1)  # 2mm from left edge (no tab space)
            pdf.cell(w - 2, SECTION_BAR_PADDING_MM, title, ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(4)
        else:
            pdf.set_font("Helvetica", "B", SECTION_H2_SIZE)
            pdf.set_text_color(*SECTION_TITLE_COLOR)
            pdf.cell(0, BODY_LINE_HEIGHT, title, ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)

    def _add_executive_summary_header(self, pdf: FPDF, title: str) -> None:
        """Executive Summary: same blue section bar as others, left-aligned + 'read first' callout."""
        pdf.ln(6)
        x = pdf.l_margin
        w = pdf.w - pdf.l_margin - pdf.r_margin
        y = pdf.get_y()
        pdf.set_x(x)
        pdf.set_fill_color(*EXEC_SUMMARY_HEADER_FILL)
        pdf.set_text_color(*EXEC_SUMMARY_HEADER_TEXT)
        pdf.set_font("Helvetica", "B", SECTION_H1_SIZE)
        pdf.rect(x, y, w, SECTION_BAR_HEIGHT_MM, "F")
        pdf.set_xy(x + 2, y + 1)  # 2mm from left edge (no tab space)
        pdf.cell(w - 2, SECTION_BAR_PADDING_MM, title, ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)

    def _add_cover_page(self, pdf: FPDF, data: dict) -> None:
        """Add a simple cover page: title, case ID, patient, date."""
        pdf.set_y(pdf.h / 2 - 25)
        pdf.set_font("Helvetica", "B", COVER_TITLE_SIZE)
        pdf.set_text_color(*SECTION_TITLE_COLOR)
        pdf.cell(0, SECTION_BAR_HEIGHT_MM, "UM Case Summary", align="C", ln=True)
        pdf.set_font("Helvetica", "", COVER_SUBTITLE_SIZE)
        pdf.cell(0, SECTION_BAR_PADDING_MM, f"Case ID: {data.get('case_number', '')}", align="C", ln=True)
        pdf.cell(0, 6, sanitize_text(data.get("patient_name", "")), align="C", ln=True)
        pdf.set_font("Helvetica", "", BODY_FONT_SIZE)
        pdf.set_text_color(*PLACEHOLDER_COLOR)
        pdf.cell(0, 6, data.get("generated_at", datetime.now().strftime("%Y-%m-%d")), align="C", ln=True)
        if data.get("generated_by"):
            pdf.cell(0, 6, f"Generated by {data['generated_by']}", align="C", ln=True)
        pdf.set_text_color(0, 0, 0)

    def _add_toc_page(
        self, pdf: FPDF, data: dict, section_pages: Optional[dict] = None
    ) -> dict:
        """Add Table of Contents with internal links (and optional page numbers).
        Returns dict of section_key -> link_id for set_link later.
        When section_pages is provided (key -> page_no), each entry shows the page number on the right."""
        toc_links = {
            "exec_summary": pdf.add_link(),
            "narrative": pdf.add_link(),
            "chronology": pdf.add_link(),
            "medications": pdf.add_link(),
            "labs": pdf.add_link(),
            "vitals": pdf.add_link(),
            "sources": pdf.add_link(),
        }
        # TOC title: plain heading (no blue bar)
        pdf.set_font("Helvetica", "B", SECTION_H1_SIZE)
        pdf.set_text_color(*SECTION_TITLE_COLOR)
        pdf.cell(0, SECTION_BAR_HEIGHT_MM, "Table of Contents", ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(1)
        # Subtitle: one line, then table starts higher for better position
        pdf.set_font("Helvetica", "", TOC_SUBTITLE_SIZE)
        pdf.set_text_color(*PLACEHOLDER_COLOR)
        pdf.multi_cell(0, BODY_LINE_HEIGHT - 1, "This report is generated from your case data. "
            "Click any section below to jump to that part of the document.", ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)
        entries = [
            ("Section 1: Executive Summary", "exec_summary"),
            ("Section 2: Comprehensive Clinical Narrative", "narrative"),
            ("Section 3: Clinical Chronology", "chronology"),
            ("Section 4: Current Medications", "medications"),
            ("Section 5: Laboratory Results", "labs"),
            ("Section 6: Vital Signs", "vitals"),
            ("Section 7: Source Documents", "sources"),
        ]
        # Full content width (match patient grid); three columns: Section, Name, Page
        w = pdf.w - 30
        pdf.set_x(pdf.l_margin)
        pdf.set_fill_color(*TABLE_ZEBRA_FILL)
        with pdf.table(
            width=w,
            col_widths=(0.18, 0.70, 0.12),  # Section | Name | Page
            headings_style=TOC_TABLE_HEADER_STYLE,
            cell_fill_color=TABLE_ZEBRA_FILL,
            cell_fill_mode="ROWS",
            line_height=TOC_ROW_LINE_HEIGHT_MM,
            text_align=("C", "LEFT", "C"),  # Section center; Name left; Page center
        ) as t:
            row = t.row()
            row.cell("Section", align="C")
            row.cell("Name", align="C")
            row.cell("Page", align="C")
            for title, key in entries:
                part = title.split(": ", 1)
                section_label = part[0] if part else title  # e.g. "Section 1"
                name_label = part[1] if len(part) > 1 else ""
                row = t.row()
                row.cell(section_label, link=toc_links[key], style=TOC_ENTRY_STYLE)
                row.cell(name_label, link=toc_links[key], style=TOC_ENTRY_STYLE)
                page_str = str(section_pages[key]) if section_pages and key in section_pages else "-"
                row.cell(page_str, link=toc_links[key], style=TOC_ENTRY_STYLE)
        pdf.ln(6)
        return toc_links

    def _add_patient_grid(self, pdf: FPDF, data: dict):
        """First section: patient info grid with center-aligned headers and subsection labels."""
        pdf.ln(3)  # Top spacing for first section below page header
        w = pdf.w - 30
        pdf.set_fill_color(*TABLE_ZEBRA_FILL)
        # Larger, bolder font for entire patient grid (headers + values)
        weight = "B" if PATIENT_GRID_FONT_BOLD else ""
        pdf.set_font("Helvetica", weight, PATIENT_GRID_FONT_SIZE)
        with pdf.table(
            width=w,
            col_widths=(0.25, 0.25, 0.25, 0.25),
            headings_style=TABLE_HEADER_STYLE,
            repeat_headings=TableHeadingsDisplay.ON_TOP_OF_EVERY_PAGE,
            line_height=TABLE_LINE_HEIGHT_PT,
            text_align=("C", "C", "C", "C"),  # All data center-aligned under PATIENT NAME, DOB, ADMISSION, DISCHARGE, FACILITY, REVIEW TYPE
        ) as t:
            row = t.row()
            row.cell("PATIENT NAME", align="C")
            row.cell("DATE OF BIRTH", align="C")
            row.cell("ADMISSION DATE", align="C")
            row.cell("DISCHARGE DATE", align="C")
            row = t.row()
            row.cell(sanitize_text(data.get("patient_name", "")))
            row.cell(sanitize_text(data.get("dob", "")))
            row.cell(sanitize_text(data.get("admit_date", "")))
            row.cell(sanitize_text(data.get("discharge_date", "")))
            row = t.row()
            row.cell("FACILITY", style=TABLE_HEADER_STYLE, align="C")
            row.cell("REVIEW TYPE", style=TABLE_HEADER_STYLE, align="C")
            row.cell("", colspan=2)
            row = t.row()
            row.cell(sanitize_text(data.get("facility", "")))
            row.cell(sanitize_text(data.get("review_type", "")))
            row.cell("", colspan=2)
            row = t.row()
            row.cell("PRIMARY DIAGNOSIS", colspan=4, style=TABLE_HEADER_STYLE, align="C")
            row = t.row()
            row.cell(sanitize_text(data.get("primary_diagnosis", "")), colspan=4, align="L")
            row = t.row()
            row.cell("SECONDARY DIAGNOSES", colspan=4, style=TABLE_HEADER_STYLE, align="C")
            row = t.row()
            sec = data.get("secondary_diagnoses") or []
            row.cell(sanitize_text(", ".join(sec)) if sec else "None", colspan=4, align="L")
        pdf.set_font("Helvetica", "", BODY_FONT_SIZE)  # Restore body font for TOC and rest of doc
        pdf.ln(2)
        # Visual separator before Table of Contents (keeps page 1 = Patient Grid + TOC)
        y_before = pdf.get_y()
        pdf.set_draw_color(200, 204, 210)
        pdf.line(pdf.l_margin, y_before, pdf.w - pdf.r_margin, y_before)
        pdf.ln(3)

    def _add_timeline_table(self, pdf: FPDF, timeline: List[dict], header_data: dict):
        sorted_events = sorted(timeline, key=lambda x: x.get("date", ""))
        w = pdf.w - 30
        col_w_desc = 0.55
        col_w_date = 0.22
        col_w_source = 0.23
        pdf.set_font("Helvetica", "", BODY_FONT_SIZE)
        pdf.set_fill_color(*TABLE_ZEBRA_FILL)
        with pdf.table(
            width=w,
            col_widths=(col_w_date, col_w_desc, col_w_source),
            headings_style=TABLE_HEADER_STYLE,
            cell_fill_color=TABLE_ZEBRA_FILL,
            cell_fill_mode="ROWS",
            repeat_headings=TableHeadingsDisplay.ON_TOP_OF_EVERY_PAGE,
            line_height=TABLE_LINE_HEIGHT_PT,
            text_align=("C", "LEFT", "C"),  # DATE/TIME and SOURCE center; EVENT DESCRIPTION left
        ) as t:
            row = t.row()
            row.cell("DATE / TIME", align="C")
            row.cell("EVENT DESCRIPTION", align="C")
            row.cell("SOURCE", align="C")
            for event in sorted_events:
                if not isinstance(event, dict):
                    continue
                date_str = sanitize_text(event.get("date", "N/A"))
                desc = sanitize_text(event.get("description", ""))
                source_str = (event.get("source") or "").upper()
                row = t.row()
                row.cell(date_str)
                row.cell(desc)
                row.cell(sanitize_text(source_str))

    def _add_medications_table(self, pdf: FPDF, meds: List[dict], header_data: dict):
        w = pdf.w - 30
        pdf.set_font("Helvetica", "", BODY_FONT_SIZE)  # normal weight so only first row is bold
        if not meds:
            pdf.set_font("Helvetica", "I", BODY_FONT_SIZE)
            pdf.set_text_color(*PLACEHOLDER_COLOR)
            pdf.cell(0, BODY_LINE_HEIGHT, "No active medications detected.", ln=True)
            pdf.set_text_color(0, 0, 0)
            return
        col_widths = (0.30, 0.20, 0.20, 0.15, 0.15)
        pdf.set_fill_color(*TABLE_ZEBRA_FILL)
        with pdf.table(
            width=w,
            col_widths=col_widths,
            headings_style=TABLE_HEADER_STYLE,
            cell_fill_color=TABLE_ZEBRA_FILL,
            cell_fill_mode="ROWS",
            repeat_headings=TableHeadingsDisplay.ON_TOP_OF_EVERY_PAGE,
            line_height=TABLE_LINE_HEIGHT_PT,
            text_align=("C", "C", "C", "C", "C"),  # All data center-aligned
        ) as t:
            row = t.row()
            row.cell("MEDICATION", align="C")
            row.cell("DOSAGE", align="C")
            row.cell("FREQUENCY", align="C")
            row.cell("START DATE", align="C")
            row.cell("END DATE", align="C")
            for med in meds:
                if not isinstance(med, dict):
                    continue
                name = sanitize_text(med.get("name", "Unknown"))
                dosage = sanitize_text(med.get("dosage", "-"))
                freq = sanitize_text(med.get("frequency", "-"))
                start_d = sanitize_text(med.get("start_date", "-"))
                end_d = med.get("end_date")
                end_str = sanitize_text(end_d) if end_d else ""
                row = t.row()
                row.cell(name)
                row.cell(dosage)
                row.cell(freq)
                row.cell(start_d)
                row.cell(end_str)

    def _add_labs_table(self, pdf: FPDF, labs: List[dict], header_data: dict):
        w = pdf.w - 30
        if not labs:
            pdf.set_font("Helvetica", "I", BODY_FONT_SIZE)
            pdf.set_text_color(*PLACEHOLDER_COLOR)
            pdf.cell(0, BODY_LINE_HEIGHT, "No recent lab results found.", ln=True)
            pdf.set_text_color(0, 0, 0)
            return
        pdf.set_font("Helvetica", "I", BODY_FONT_SIZE)
        pdf.set_text_color(*PLACEHOLDER_COLOR)
        pdf.cell(0, BODY_LINE_HEIGHT, "Abnormal results highlighted in red; showing most recent values", ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)
        pdf.set_font("Helvetica", "", BODY_FONT_SIZE)
        pdf.set_fill_color(*TABLE_ZEBRA_FILL)
        with pdf.table(
            width=w,
            col_widths=(0.2, 0.3, 0.25, 0.25),
            headings_style=TABLE_HEADER_STYLE,
            cell_fill_color=TABLE_ZEBRA_FILL,
            cell_fill_mode="ROWS",
            repeat_headings=TableHeadingsDisplay.ON_TOP_OF_EVERY_PAGE,
            line_height=TABLE_LINE_HEIGHT_PT,
            text_align=("C", "C", "C", "C"),  # All data center-aligned
        ) as t:
            row = t.row()
            row.cell("DATE", align="C")
            row.cell("TEST NAME", align="C")
            row.cell("RESULT", align="C")
            row.cell("RANGE", align="C")
            for lab in labs:
                if not isinstance(lab, dict):
                    continue
                date = sanitize_text(lab.get("date", "-"))
                name = sanitize_text(lab.get("test_name", "-"))
                res = sanitize_text(f"{lab.get('value', '-')} {lab.get('unit', '')}")
                rng = lab.get("reference_range") or lab.get("range") or lab.get("normal_range") or lab.get("ref_range") or "-"
                rng = sanitize_text(str(rng))
                is_abnormal = lab.get("abnormal", False)
                row = t.row()
                row.cell(date)
                row.cell(name)
                # Per-cell style so abnormal value is red without affecting other cells
                row.cell(res, style=LAB_ABNORMAL_STYLE if is_abnormal else None)
                row.cell(rng)

    def _add_vitals_table(self, pdf: FPDF, ranges: List[dict], header_data: dict, raw_vitals: Optional[List[dict]] = None):
        raw_vitals = raw_vitals or []

        def _normalize_date(d: Any) -> str:
            if not d:
                return ""
            s = str(d).strip()
            if not s:
                return ""
            try:
                for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"):
                    try:
                        return datetime.strptime(s[:10], fmt).strftime("%m/%d/%Y")
                    except ValueError:
                        continue
            except Exception:
                pass
            return s

        def _value_from_raw_vitals(row_date: str, kind: str) -> Optional[str]:
            nd = _normalize_date(row_date)
            if not nd or not raw_vitals:
                return None
            for v in raw_vitals:
                if not isinstance(v, dict):
                    continue
                vdate = v.get("date") or v.get("Date") or ""
                if _normalize_date(vdate) != nd:
                    continue
                t = (v.get("type") or "").lower()
                val = v.get("value") or v.get("value_str")
                if val is None:
                    continue
                if kind == "heart_rate" and ("heart" in t or "hr" in t or "pulse" in t):
                    return str(val).strip()
                if kind == "spO2" and ("spo2" in t or "o2 sat" in t or "oxygen" in t):
                    return str(val).strip()
                if kind == "temperature" and ("temp" in t or "temperature" in t):
                    return str(val).strip()
            return None

        w = pdf.w - 30
        pdf.set_font("Helvetica", "I", BODY_FONT_SIZE)
        pdf.set_text_color(*PLACEHOLDER_COLOR)
        pdf.cell(0, BODY_LINE_HEIGHT, "Showing key daily ranges; detailed readings summarized below", ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)
        pdf.set_font("Helvetica", "", BODY_FONT_SIZE)
        col_widths = (0.18, 0.22, 0.20, 0.20, 0.20)
        pdf.set_fill_color(*TABLE_ZEBRA_FILL)
        with pdf.table(
            width=w,
            col_widths=col_widths,
            headings_style=TABLE_HEADER_STYLE,
            cell_fill_color=TABLE_ZEBRA_FILL,
            cell_fill_mode="ROWS",
            repeat_headings=TableHeadingsDisplay.ON_TOP_OF_EVERY_PAGE,
            line_height=TABLE_LINE_HEIGHT_PT,
            text_align=("C", "C", "C", "C", "C"),  # All columns center-aligned including Date
        ) as t:
            row = t.row()
            row.cell("DATE", align="C")
            row.cell("BP RANGE", align="C")
            row.cell("HR RANGE", align="C")
            row.cell("O2 RANGE", align="C")
            row.cell("TEMP RANGE", align="C")
            if not ranges:
                row = t.row()
                for _ in range(5):
                    row.cell("--")
            else:
                for row_data in ranges:
                    if not isinstance(row_data, dict):
                        continue
                    _vital_keys = ["date", "blood_pressure", "blood pressure", "heart_rate", "heart rate", "spO2", "spo2", "temperature", "temp"]
                    if not any(row_data.get(k) for k in _vital_keys):
                        continue
                    date = sanitize_text(row_data.get("date", "--"))

                    def get_vital(row: dict, *keys: str):
                        for k in keys:
                            if k in row and row[k] is not None:
                                return row[k]
                        return None

                    def fmt(*keys: str):
                        v = get_vital(row_data, *keys)
                        if v is None or v == "":
                            return "--"
                        if isinstance(v, dict):
                            mn, mx = v.get("min"), v.get("max")
                            if mn is not None and mx is not None:
                                return f"{mn}-{mx}" if mn != mx else str(mn)
                            if mn is not None:
                                return str(mn)
                            if mx is not None:
                                return str(mx)
                            return "--"
                        s = str(v).strip()
                        if s and s.lower() != "range not available":
                            return sanitize_text(s)
                        return None  # caller will use fallback

                    def cell_val(*keys: str, raw_kind: Optional[str] = None):
                        out = fmt(*keys)
                        if out is not None:
                            return out
                        if raw_kind and date:
                            fallback = _value_from_raw_vitals(date, raw_kind)
                            if fallback:
                                return sanitize_text(fallback)
                        return "N/A"

                    row = t.row()
                    row.cell(str(date).strip())
                    row.cell(str(fmt("blood_pressure", "blood pressure") or "N/A").strip())
                    row.cell(str(cell_val("heart_rate", "heart rate", "heartRate", raw_kind="heart_rate")).strip())
                    row.cell(str(cell_val("spO2", "spo2", raw_kind="spO2")).strip())
                    row.cell(str(cell_val("temperature", "temp", raw_kind="temperature")).strip())

    def _add_source_index(self, pdf: FPDF, case_files: List, header_data: dict):
        w = pdf.w - 30
        pdf.set_font("Helvetica", "", BODY_FONT_SIZE)
        pdf.set_fill_color(*TABLE_ZEBRA_FILL)
        with pdf.table(
            width=w,
            col_widths=(0.7, 0.3),
            headings_style=TABLE_HEADER_STYLE,
            cell_fill_color=TABLE_ZEBRA_FILL,
            cell_fill_mode="ROWS",
            repeat_headings=TableHeadingsDisplay.ON_TOP_OF_EVERY_PAGE,
            line_height=TABLE_LINE_HEIGHT_PT,
            text_align=("L", "C"),  # FILE NAME values left; DETAILS center
        ) as t:
            row = t.row()
            row.cell("FILE NAME", align="C")
            row.cell("DETAILS", align="C")
            for f in case_files:
                name = getattr(f, "file_name", str(f))[:80]
                pages = getattr(f, "page_count", None)
                up = getattr(f, "uploaded_at", None)
                if up and hasattr(up, "strftime"):
                    date_str = up.strftime("%Y-%m-%d")
                else:
                    date_str = str(up) if up else ""
                details = f"{pages or '?'} pages - {date_str}"
                row = t.row()
                row.cell(sanitize_text(name))
                row.cell(details)


pdf_generator_service_fpdf2 = PDFGeneratorServiceFPDF2()
