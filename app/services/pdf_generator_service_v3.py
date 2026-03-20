"""
PDF Generator Service V3 — Professional UM Clinical Summary
Design: Executive Summary-First, Section-Driven Architecture
Engine: ReportLab Platypus with intelligent data extraction

Architecture:
- Page 1: Executive Summary (fixed anchor point)
- Remaining pages: Content-dependent sections that flow naturally
"""

import io
import logging
import os
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from collections import defaultdict

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, Image
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# THEME & STYLES (Professional Clinical)
# ═══════════════════════════════════════════════════════════════════════════════
class Theme:
    # Clinical Neutral Palette (Professional + Compliance-Safe)
    BRAND_NAVY = colors.HexColor('#3B82F6')  # Light blue header background
    BRAND_ACCENT = colors.HexColor('#2563EB')  # Darker blue accent
    TEXT_PRIMARY = colors.HexColor('#1F2933')  # Primary text
    TEXT_SECONDARY = colors.HexColor('#4B5563')  # Secondary text
    TEXT_MUTED = colors.HexColor('#6B7280')  # Muted labels
    BG_WHITE = colors.white  # Background
    BG_CARD = colors.HexColor('#F8F9FB')  # Section cards
    BORDER_LIGHT = colors.HexColor('#E3E6EA')  # Borders/dividers
    
    # Signal Colors (Muted, Dark Tones)
    ALERT_RED = colors.HexColor('#B91C1C')  # Critical/abnormal
    WARNING_AMBER = colors.HexColor('#B45309')  # Warning
    IMPROVING_GREEN = colors.HexColor('#065F46')  # Improving trends
    STABLE_GRAY = colors.HexColor('#374151')  # Stable/resolved

class LayoutStyles:
    def __init__(self):
        styles = getSampleStyleSheet()
        
        # Section headers (uppercase, navy)
        self.section_header = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=12,
            textColor=Theme.BRAND_NAVY,
            spaceBefore=20,
            spaceAfter=10,
            textTransform='uppercase'
        )
        
        # Subsection headers
        self.subsection = ParagraphStyle(
            'Subsection',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            textColor=Theme.TEXT_PRIMARY,
            spaceBefore=12,
            spaceAfter=6
        )
        
        # Body text
        self.body = ParagraphStyle(
            'Body',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=15,
            textColor=Theme.TEXT_PRIMARY,
            spaceAfter=4
        )
        
        # Bullet text
        self.bullet = ParagraphStyle(
            'Bullet',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=15,
            textColor=Theme.TEXT_PRIMARY,
            leftIndent=12,
            spaceAfter=3
        )
        
        # Small labels
        self.label = ParagraphStyle(
            'Label',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            textColor=Theme.TEXT_MUTED,
            textTransform='uppercase'
        )
        
        # Table headers
        self.table_header = ParagraphStyle(
            'TableHeader',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            textColor=Theme.TEXT_PRIMARY
        )
        
        # Values
        self.value = ParagraphStyle(
            'Value',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            textColor=Theme.TEXT_PRIMARY
        )

class PDFGeneratorServiceV3:
    def __init__(self):
        self.styles = LayoutStyles()
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.logo_path = os.path.join(self.base_dir, 'static', 'images', 'logo.png')

    def generate_case_pdf(
        self,
        case,
        extraction,
        case_files: List,
        patient_dob: Optional[str] = None,
        generated_by: Optional[str] = None
    ) -> bytes:
        """Generate professional UM clinical summary PDF"""
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.6*inch,
            leftMargin=0.6*inch,
            topMargin=1.1*inch,
            bottomMargin=0.7*inch
        )
        
        # Extract structured data
        data = self._build_data(case, extraction, patient_dob, case_files)
        
        # Build story
        story = []
        
        # ═══════════════════════════════════════════════════════════════
        # PAGE 1: EXECUTIVE SUMMARY (Fixed Anchor)
        # ═══════════════════════════════════════════════════════════════
        executive_summary = []
        
        # Patient Snapshot
        executive_summary.append(self._create_patient_snapshot(data))
        executive_summary.append(Spacer(1, 18))
        
        # Clinical Overview
        executive_summary.append(self._create_clinical_overview(data))
        executive_summary.append(Spacer(1, 18))
        
        # Key Clinical Signals
        key_signals = self._create_key_signals(data)
        if key_signals:
            executive_summary.append(key_signals)
        
        # Keep Page 1 together, force page break after
        story.append(KeepTogether(executive_summary))
        story.append(PageBreak())
        
        # ═══════════════════════════════════════════════════════════════
        # SECTION 2: CRITICAL NOTIFICATIONS + NARRATIVE
        # ═══════════════════════════════════════════════════════════════
        
        # Critical notifications (if any)
        if data.get('critical_findings'):
            story.append(self._create_critical_notifications(data['critical_findings']))
            story.append(Spacer(1, 20))
        
        # Structured narrative
        story.append(Paragraph("CLINICAL NARRATIVE SUMMARY", self.styles.section_header))
        narrative_blocks = self._parse_narrative_blocks(data.get('summary_text', ''))
        for block_title, block_bullets in narrative_blocks:
            if block_bullets:
                story.append(Paragraph(block_title.upper(), self.styles.subsection))
                for bullet in block_bullets:
                    story.append(Paragraph(f"• {bullet}", self.styles.bullet))
                story.append(Spacer(1, 10))
        
        story.append(Spacer(1, 20))
        
        # ═══════════════════════════════════════════════════════════════
        # SECTION 3: MEDICATIONS + MILESTONES
        # ═══════════════════════════════════════════════════════════════
        
        story.append(Paragraph("MEDICATIONS", self.styles.section_header))
        if data['medications']:
            story.append(self._create_medications_table(data['medications'], data['timeline_events']))
        else:
            story.append(Paragraph("No medications documented.", self.styles.body))
        story.append(Spacer(1, 20))
        
        story.append(Paragraph("CLINICAL MILESTONES", self.styles.section_header))
        milestones = self._extract_milestones(data['timeline_events'])
        if milestones:
            for m in milestones:
                story.append(Paragraph(f"• {m['date'][:10]} – {m['description']}", self.styles.body))
        else:
            story.append(Paragraph("No key milestones identified.", self.styles.body))
        story.append(Spacer(1, 20))
        
        # ═══════════════════════════════════════════════════════════════
        # SECTION 4: LAB TRENDS + FULL LABS
        # ═══════════════════════════════════════════════════════════════
        
        story.append(Paragraph("LAB RESULTS & TRENDS", self.styles.section_header))
        
        # Key lab trends summary
        if data['labs']:
            trends_table = self._create_lab_trends_table(data['labs'])
            if trends_table:
                story.append(Paragraph("Key Lab Trends", self.styles.subsection))
                story.append(trends_table)
                story.append(Spacer(1, 14))
            
            # Full labs table
            story.append(Paragraph("All Laboratory Results", self.styles.subsection))
            story.append(self._create_labs_table(data['labs']))
        else:
            story.append(Paragraph("No laboratory results available.", self.styles.body))
        
        story.append(Spacer(1, 20))
        
        # ═══════════════════════════════════════════════════════════════
        # SECTION 5: FULL CHRONOLOGY (APPENDIX) + SOURCES
        # ═══════════════════════════════════════════════════════════════
        
        story.append(Paragraph("DETAILED CLINICAL CHRONOLOGY", self.styles.section_header))
        if data['timeline_events']:
            story.append(self._create_detailed_chronology(data['timeline_events']))
        else:
            story.append(Paragraph("No timeline events available.", self.styles.body))
        
        story.append(Spacer(1, 20))
        
        story.append(Paragraph("SOURCE DOCUMENTS", self.styles.section_header))
        for f in data['source_files'][:10]:
            story.append(Paragraph(f"• {f.file_name} ({f.page_count} pages)", self.styles.body))
        
        # Build PDF
        doc.build(story, onFirstPage=self._header_footer_page1, onLaterPages=self._header_footer_later)
        
        buffer.seek(0)
        return buffer.getvalue()

    # ═══════════════════════════════════════════════════════════════════════════
    # HEADER & FOOTER
    # ═══════════════════════════════════════════════════════════════════════════

    def _header_footer_page1(self, canvas, doc):
        """Page 1 header with colored background, logo, and styled footer"""
        canvas.saveState()
        page_w, page_h = letter
        
        # Colored header background bar
        canvas.setFillColor(Theme.BRAND_NAVY)
        canvas.rect(0, page_h - 0.9*inch, page_w, 0.9*inch, fill=True, stroke=False)
        
        # Logo (if exists) - positioned on colored background
        if os.path.exists(self.logo_path):
            try:
                # Draw logo in top-left corner on colored bar
                logo_height = 0.5 * inch
                logo_width = 0.5 * inch
                canvas.drawImage(
                    self.logo_path, 
                    0.6*inch, 
                    page_h - 0.75*inch, 
                    width=logo_width, 
                    height=logo_height,
                    preserveAspectRatio=True,
                    mask='auto'
                )
            except Exception as e:
                logger.warning(f"Failed to load logo: {e}")
        
        # Company branding beside logo
        canvas.setFont("Helvetica-Bold", 14)
        canvas.setFillColor(colors.white)
        canvas.drawString(1.2*inch, page_h - 0.5*inch, "Brightcone")
        
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(Theme.BG_CARD)
        canvas.drawString(1.2*inch, page_h - 0.7*inch, "Utilization Management")
        
        # Header text - white text on navy background
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(colors.white)
        canvas.drawString(3.2*inch, page_h - 0.55*inch, "CLINICAL CASE SUMMARY")
        
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.white)
        canvas.drawRightString(page_w - 0.6*inch, page_h - 0.4*inch, 
                              f"Generated: {datetime.now().strftime('%b %d, %Y')}")
        
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(Theme.BG_CARD)
        canvas.drawRightString(page_w - 0.6*inch, page_h - 0.6*inch, 
                              "Confidential – Professional Use")
        
        # Colored footer bar
        canvas.setFillColor(Theme.BG_CARD)
        canvas.rect(0, 0, page_w, 0.6*inch, fill=True, stroke=False)
        
        # Footer - styled page number
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(Theme.BRAND_NAVY)
        canvas.drawCentredString(page_w / 2, 0.35*inch, f"Page {canvas.getPageNumber()}")
        
        canvas.restoreState()

    def _header_footer_later(self, canvas, doc):
        """Simplified header for subsequent pages with colored bar and small logo"""
        canvas.saveState()
        page_w, page_h = letter
        
        # Colored header background bar (lighter than page 1)
        canvas.setFillColor(Theme.BG_CARD)
        canvas.rect(0, page_h - 0.75*inch, page_w, 0.75*inch, fill=True, stroke=False)
        
        # Small logo (if exists) - positioned on colored background
        if os.path.exists(self.logo_path):
            try:
                logo_height = 0.4 * inch
                logo_width = 0.4 * inch
                canvas.drawImage(
                    self.logo_path, 
                    0.6*inch, 
                    page_h - 0.65*inch, 
                    width=logo_width, 
                    height=logo_height,
                    preserveAspectRatio=True,
                    mask='auto'
                )
            except Exception as e:
                logger.warning(f"Failed to load logo on page {canvas.getPageNumber()}: {e}")
        
        # Company branding beside logo
        canvas.setFont("Helvetica-Bold", 11)
        canvas.setFillColor(Theme.BRAND_NAVY)
        canvas.drawString(1.1*inch, page_h - 0.48*inch, "Brightcone")
        
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(Theme.TEXT_SECONDARY)
        canvas.drawString(1.1*inch, page_h - 0.62*inch, "Utilization Management")
        
        # Header text - dark text on light background
        canvas.setFont("Helvetica", 10)
        canvas.setFillColor(Theme.BRAND_NAVY)
        canvas.drawString(2.8*inch, page_h - 0.5*inch, "Clinical Case Summary")
        
        # Accent line below header
        canvas.setStrokeColor(Theme.BRAND_ACCENT)
        canvas.setLineWidth(2)
        canvas.line(0, page_h - 0.75*inch, page_w, page_h - 0.75*inch)
        
        # Colored footer bar
        canvas.setFillColor(Theme.BG_CARD)
        canvas.rect(0, 0, page_w, 0.6*inch, fill=True, stroke=False)
        
        # Footer - styled page number
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(Theme.BRAND_NAVY)
        canvas.drawCentredString(page_w / 2, 0.35*inch, f"Page {canvas.getPageNumber()}")
        
        canvas.restoreState()

    # ═══════════════════════════════════════════════════════════════════════════
    # EXECUTIVE SUMMARY COMPONENTS
    # ═══════════════════════════════════════════════════════════════════════════

    def _create_patient_snapshot(self, data):
        """2-column compact patient info card"""
        def cell(label, value):
            return [Paragraph(label, self.styles.label), Paragraph(value, self.styles.value)]
        
        snapshot_data = [[
            cell("PATIENT NAME", data['patient_name']),
            cell("DOB", data['dob'])
        ], [
            cell("FACILITY", data['facility']),
            cell("MRN", data['mrn'])
        ]]
        
        t = Table(snapshot_data, colWidths=[3.5*inch, 3.5*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), Theme.BG_CARD),
            ('BOX', (0,0), (-1,-1), 0.5, Theme.BORDER_LIGHT),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        
        header = Paragraph("PATIENT SNAPSHOT", self.styles.section_header)
        return KeepTogether([header, Spacer(1, 6), t])

    def _create_clinical_overview(self, data):
        """Clinical at-a-glance with diagnosis status"""
        elements = []
        elements.append(Paragraph("CLINICAL OVERVIEW", self.styles.section_header))
        elements.append(Spacer(1, 6))
        
        # Principal diagnosis
        elements.append(Paragraph("Principal Diagnosis:", self.styles.subsection))
        elements.append(Paragraph(f"• {data['primary_diagnosis']}", self.styles.body))
        elements.append(Spacer(1, 8))
        
        # Active conditions with status
        diagnoses_with_status = data.get('diagnoses_with_status', [])
        if diagnoses_with_status and len(diagnoses_with_status) > 1:
            elements.append(Paragraph("Active Conditions:", self.styles.subsection))
            for dx in diagnoses_with_status[1:6]:  # Skip first (already shown as principal)
                status = dx.get('status', 'Active')
                elements.append(Paragraph(f"• {dx['name']} ({status})", self.styles.body))
        
        return KeepTogether(elements)

    def _create_key_signals(self, data):
        """Key clinical signals summary"""
        signals = data.get('key_signals', [])
        if not signals:
            return None
        
        elements = []
        elements.append(Paragraph("KEY CLINICAL SIGNALS", self.styles.section_header))
        elements.append(Spacer(1, 6))
        
        for signal in signals:
            elements.append(Paragraph(f"• {signal}", self.styles.body))
        
        return KeepTogether(elements)

    def _create_critical_notifications(self, findings):
        """Consolidated critical findings"""
        elements = []
        elements.append(Paragraph("CRITICAL NOTIFICATIONS", self.styles.section_header))
        elements.append(Spacer(1, 6))
        
        for finding in findings[:5]:  # Limit to top 5
            date_range = finding.get('date_range', '')
            text = f"• {finding['description']}"
            if date_range:
                text += f" ({date_range})"
            elements.append(Paragraph(text, self.styles.body))
        
        return KeepTogether(elements)

    # ═══════════════════════════════════════════════════════════════════════════
    # HELPER METHODS (Data Extraction & Transformation)
    # ═══════════════════════════════════════════════════════════════════════════

    def _extract_diagnosis_with_status(self, extraction) -> List[Dict]:
        """Parse diagnoses with Active/Chronic/Recurrent/Resolved status"""
        if not extraction:
            return []
        
        ext = extraction.extracted_data or {}
        dxs = ext.get('diagnoses', [])
        timeline = extraction.timeline or []
        
        diagnoses_with_status = []
        for dx in dxs:
            if isinstance(dx, dict):
                name = dx.get('name', '')
                # Simple heuristic: check timeline for status keywords
                status = 'Active'
                for event in timeline:
                    desc = event.get('description', '').lower()
                    if name.lower() in desc:
                        if 'resolved' in desc:
                            status = 'Resolved'
                        elif 'chronic' in desc or 'long-term' in desc:
                            status = 'Chronic'
                        elif 'recurrent' in desc or 'again' in desc:
                            status = 'Recurrent'
                
                diagnoses_with_status.append({'name': name, 'status': status})
            elif isinstance(dx, str):
                diagnoses_with_status.append({'name': dx, 'status': 'Active'})
        
        return diagnoses_with_status

    def _calculate_key_signals(self, extraction) -> List[str]:
        """Extract 4-5 critical summary metrics"""
        if not extraction:
            return []
        
        ext = extraction.extracted_data or {}
        signals = []
        
        # O2 Saturation (min)
        vitals = ext.get('vitals', [])
        o2_values = [v for v in vitals if isinstance(v, dict) and 'spo2' in v.get('type', '').lower()]
        if o2_values:
            try:
                min_o2 = min([float(v.get('value', 999)) for v in o2_values if v.get('value')])
                min_o2_date = next((v.get('date', '')[:10] for v in o2_values if float(v.get('value', 0)) == min_o2), '')
                if min_o2 < 95:
                    signals.append(f"Lowest O₂ Saturation: {min_o2:.0f}% ({min_o2_date})")
            except:
                pass
        
        # Temperature (max)
        temp_values = [v for v in vitals if isinstance(v, dict) and 'temp' in v.get('type', '').lower()]
        if temp_values:
            try:
                max_temp = max([float(v.get('value', 0)) for v in temp_values if v.get('value')])
                if max_temp > 100.4:
                    signals.append(f"Peak Temperature: {max_temp}°F")
            except:
                pass
        
        # WBC Trend
        labs = ext.get('labs', [])
        wbc_values = [l for l in labs if isinstance(l, dict) and 'wbc' in l.get('test_name', '').lower()]
        if len(wbc_values) >= 2:
            try:
                wbc_sorted = sorted(wbc_values, key=lambda x: x.get('date', ''))
                first_wbc = float(wbc_sorted[0].get('value', 0))
                last_wbc = float(wbc_sorted[-1].get('value', 0))
                if first_wbc > last_wbc:
                    signals.append(f"WBC Trend: Improving ({first_wbc:.1f} → {last_wbc:.1f})")
                elif first_wbc < last_wbc:
                    signals.append(f"WBC Trend: Worsening ({first_wbc:.1f} → {last_wbc:.1f})")
            except:
                pass
        
        # Creatinine normalization
        cr_values = [l for l in labs if isinstance(l, dict) and 'creatinine' in l.get('test_name', '').lower()]
        if len(cr_values) >= 2:
            try:
                cr_sorted = sorted(cr_values, key=lambda x: x.get('date', ''))
                last_cr = float(cr_sorted[-1].get('value', 999))
                if last_cr <= 1.3:
                    last_date = cr_sorted[-1].get('date', '')[:10]
                    signals.append(f"Renal Function: Normalized by {last_date}")
            except:
                pass
        
        return signals[:5]  # Limit to 5 signals

    def _parse_narrative_blocks(self, summary_text: str) -> List[Tuple[str, List[str]]]:
        """Split summary into Presentation/Course/Status blocks with bullet formatting"""
        if not summary_text:
            return []
        
        # Clean markdown artifacts
        clean_text = summary_text.replace('**', '').replace('##', '').replace('#', '')
        paragraphs = [p.strip() for p in clean_text.split('\n') if p.strip()]
        
        # Filter out metadata lines (like "PATIENT OVERVIEW - Patient Name:")
        paragraphs = [p for p in paragraphs if not p.startswith('- ') and ':' not in p[:30]]
        
        # Simple heuristic-based splitting
        presentation = []
        course = []
        status = []
        
        for p in paragraphs:
            p_lower = p.lower()
            # Split long paragraphs into sentences
            sentences = [s.strip() for s in p.split('. ') if s.strip()]
            
            for sent in sentences:
                sent_lower = sent.lower()
                if any(kw in sent_lower for kw in ['admitted', 'presented', 'initial', 'chief complaint', 'hypoxia', 'fever']):
                    presentation.append(sent if sent.endswith('.') else sent + '.')
                elif any(kw in sent_lower for kw in ['currently', 'stable', 'discharge', 'resolved', 'normalized']):
                    status.append(sent if sent.endswith('.') else sent + '.')
                elif any(kw in sent_lower for kw in ['treated', 'improved', 'antibiotics', 'supportive', 'labs']):
                    course.append(sent if sent.endswith('.') else sent + '.')
        
        blocks = []
        if presentation:
            blocks.append(("Presentation", presentation[:5]))  # Limit to 5 bullets
        if course:
            blocks.append(("Clinical Course", course[:5]))
        if status:
            blocks.append(("Current Status", status[:5]))
        
        # Fallback: if heuristic didn't work, create simple bullets from paragraphs
        if not blocks and paragraphs:
            bullets = [p if p.endswith('.') else p + '.' for p in paragraphs[:5]]
            blocks.append(("Summary", bullets))
        
        return blocks

    def _extract_milestones(self, timeline_events: List[Dict]) -> List[Dict]:
        """Filter timeline to 5-8 key events"""
        if not timeline_events:
            return []
        
        milestones = []
        for event in timeline_events:
            desc = event.get('description', '').lower()
            # Include diagnoses, major med changes, significant findings
            if any(kw in desc for kw in [
                'diagnosed', 'diagnosis', 'started', 'discontinued', 
                'hypoxia', 'fever', 'pneumonia', 'respiratory',
                'admitted', 'discharged', 'transferred'
            ]):
                milestones.append(event)
        
        # Limit to 8 most important
        return milestones[:8]

    def _consolidate_critical_findings(self, labs: List[Dict]) -> List[Dict]:
        """Group abnormal findings by test, show date range"""
        findings_by_test = defaultdict(list)
        
        for lab in labs:
            if lab.get('abnormal') or lab.get('critical'):
                test_name = lab.get('test_name', 'Unknown')
                date = lab.get('date', '')[:10]
                findings_by_test[test_name].append(date)
        
        consolidated = []
        for test_name, dates in findings_by_test.items():
            if dates:
                dates.sort()
                if len(dates) == 1:
                    date_range = dates[0]
                else:
                    date_range = f"{dates[0]} – {dates[-1]}"
                
                consolidated.append({
                    'description': f"Elevated {test_name}",
                    'date_range': date_range
                })
        
        return consolidated[:5]

    # ═══════════════════════════════════════════════════════════════════════════
    # TABLE CREATION METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def _create_medications_table(self, meds: List[Dict], timeline: List[Dict]):
        """Medications table with status column"""
        headers = [
            Paragraph("MEDICATION", self.styles.table_header),
            Paragraph("DOSE", self.styles.table_header),
            Paragraph("FREQUENCY", self.styles.table_header),
            Paragraph("STATUS", self.styles.table_header)
        ]
        data = [headers]
        
        for med in meds[:15]:
            name = med.get('name', 'Unknown') or 'Unknown'
            dose = med.get('dosage', '') or ''
            freq = med.get('frequency', '') or ''
            status = self._determine_med_status(med, timeline)
            
            data.append([
                Paragraph(str(name), self.styles.value),
                Paragraph(str(dose), self.styles.value),
                Paragraph(str(freq), self.styles.value),
                Paragraph(str(status), self.styles.value)
            ])
        
        t = Table(data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), Theme.BG_CARD),
            ('LINEBELOW', (0,0), (-1,0), 0.5, Theme.BORDER_LIGHT),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 6)
        ]))
        return t

    def _determine_med_status(self, med: Dict, timeline: List[Dict]) -> str:
        """Check if medication is Ongoing/Stopped"""
        med_name = med.get('name', '').lower()
        
        for event in timeline:
            desc = event.get('description', '').lower()
            if med_name in desc:
                if any(kw in desc for kw in ['stopped', 'discontinued', 'held']):
                    date = event.get('date', '')[:10]
                    return f"Stopped {date}"
        
        return "Ongoing"

    def _create_lab_trends_table(self, labs: List[Dict]):
        """Key lab trends: Peak/Latest/Trend with direction-aware logic"""
        # Define tests with direction (True = higher is better, False = lower is better)
        key_tests = {
            'wbc': {'higher_better': False, 'normal_range': (4.5, 11.0)},
            'hemoglobin': {'higher_better': True, 'normal_range': (12.0, 17.0)},
            'hgb': {'higher_better': True, 'normal_range': (12.0, 17.0)},
            'creatinine': {'higher_better': False, 'normal_range': (0.7, 1.3)}
        }
        trends = {}
        
        for test_key, test_config in key_tests.items():
            matching_labs = [l for l in labs if isinstance(l, dict) and test_key in l.get('test_name', '').lower()]
            if len(matching_labs) >= 2:
                try:
                    # Sort by date
                    sorted_labs = sorted(matching_labs, key=lambda x: x.get('date', ''))
                    values = [float(l.get('value', 0)) for l in sorted_labs if l.get('value')]
                    if values:
                        first_value = values[0]
                        latest_value = values[-1]
                        higher_better = test_config['higher_better']
                        normal_min, normal_max = test_config['normal_range']
                        
                        # Calculate distance from normal range
                        def distance_from_normal(val):
                            if val < normal_min:
                                return normal_min - val
                            elif val > normal_max:
                                return val - normal_max
                            return 0
                        
                        first_dist = distance_from_normal(first_value)
                        latest_dist = distance_from_normal(latest_value)
                        
                        # Determine trend based on direction and proximity to normal
                        if higher_better:
                            # For Hemoglobin: higher is better
                            if latest_value > first_value:
                                trend = "↑ Improving"
                                trend_color = Theme.IMPROVING_GREEN
                            elif latest_value < first_value:
                                trend = "↓ Worsening"
                                trend_color = Theme.ALERT_RED
                            else:
                                trend = "→ Stable"
                                trend_color = Theme.STABLE_GRAY
                        else:
                            # For WBC, Creatinine: lower is better
                            if latest_value < first_value:
                                trend = "↓ Improving"
                                trend_color = Theme.IMPROVING_GREEN
                            elif latest_value > first_value:
                                trend = "↑ Worsening"
                                trend_color = Theme.ALERT_RED
                            else:
                                trend = "→ Stable"
                                trend_color = Theme.STABLE_GRAY
                        
                        # Safety check: if moving closer to normal range, always "Improving"
                        if latest_dist < first_dist:
                            trend = trend.replace("Worsening", "Improving").replace("↑", "↓") if not higher_better else trend.replace("Worsening", "Improving")
                            trend_color = Theme.IMPROVING_GREEN
                        
                        trends[matching_labs[0].get('test_name', test_key)] = {
                            'peak': first_value,
                            'latest': latest_value,
                            'trend': trend,
                            'trend_color': trend_color
                        }
                except:
                    pass
        
        if not trends:
            return None
        
        headers = [
            Paragraph("TEST", self.styles.table_header),
            Paragraph("PEAK", self.styles.table_header),
            Paragraph("LATEST", self.styles.table_header),
            Paragraph("TREND", self.styles.table_header)
        ]
        data = [headers]
        
        for test_name, values in list(trends.items())[:5]:
            trend_style = ParagraphStyle('TrendValue', parent=self.styles.value, textColor=values.get('trend_color', Theme.TEXT_PRIMARY))
            data.append([
                Paragraph(test_name, self.styles.value),
                Paragraph(f"{values['peak']:.1f}", self.styles.value),
                Paragraph(f"{values['latest']:.1f}", self.styles.value),
                Paragraph(values['trend'], trend_style)
            ])
        
        t = Table(data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), Theme.BG_CARD),
            ('LINEBELOW', (0,0), (-1,0), 0.5, Theme.BORDER_LIGHT),
            ('PADDING', (0,0), (-1,-1), 6)
        ]))
        return t

    def _create_labs_table(self, labs: List[Dict]):
        """Full laboratory results table"""
        headers = [
            Paragraph("DATE", self.styles.table_header),
            Paragraph("TEST", self.styles.table_header),
            Paragraph("RESULT", self.styles.table_header),
            Paragraph("RANGE", self.styles.table_header)
        ]
        data = [headers]
        
        for lab in labs[:25]:
            date = str(lab.get('date', ''))[:10]
            test = lab.get('test_name', '')
            value = f"{lab.get('value', '')} {lab.get('unit', '')}"
            ref_range = lab.get('reference_range', '')
            
            # Highlight abnormal values
            value_style = self.styles.value
            if lab.get('abnormal') or lab.get('critical'):
                value_style = ParagraphStyle('AbnormalValue', parent=self.styles.value, textColor=Theme.ALERT_RED, fontName='Helvetica-Bold')
            
            data.append([
                Paragraph(date, self.styles.value),
                Paragraph(test, self.styles.value),
                Paragraph(value, value_style),
                Paragraph(ref_range, self.styles.value)
            ])
        
        t = Table(data, colWidths=[1.0*inch, 2.5*inch, 1.5*inch, 2.0*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), Theme.BG_CARD),
            ('LINEBELOW', (0,0), (-1,0), 0.5, Theme.BORDER_LIGHT),
            ('FONTSIZE', (0,1), (-1,-1), 9),  # Slightly smaller for dense data
            ('PADDING', (0,0), (-1,-1), 5),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, Theme.BG_CARD])  # Zebra striping
        ]))
        return t

    def _create_detailed_chronology(self, events: List[Dict]):
        """Full timeline in appendix style (smaller font)"""
        headers = [
            Paragraph("DATE", self.styles.table_header),
            Paragraph("EVENT", self.styles.table_header)
        ]
        data = [headers]
        
        for event in events[:50]:
            date = str(event.get('date', ''))[:10]
            desc = event.get('description', '')
            
            data.append([
                Paragraph(date, self.styles.value),
                Paragraph(desc, self.styles.value)
            ])
        
        t = Table(data, colWidths=[1.0*inch, 6.0*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), Theme.BG_CARD),
            ('LINEBELOW', (0,0), (-1,0), 0.5, Theme.BORDER_LIGHT),
            ('FONTSIZE', (0,1), (-1,-1), 8),  # Smaller for appendix
            ('PADDING', (0,0), (-1,-1), 4),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, Theme.BG_CARD])  # Zebra striping
        ]))
        return t

    # ═══════════════════════════════════════════════════════════════════════════
    # DATA BUILDING
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_data(self, case, extraction, dob, files) -> Dict:
        """Extract and structure all data needed for PDF"""
        data = {
            'patient_name': case.patient_name or "Unknown",
            'dob': dob or "N/A",
            'mrn': getattr(case, 'mrn', 'N/A'),
            'facility': "Not Specified",
            'primary_diagnosis': "Pending",
            'diagnoses_with_status': [],
            'key_signals': [],
            'critical_findings': [],
            'summary_text': None,
            'timeline_events': [],
            'labs': [],
            'medications': [],
            'source_files': files or []
        }
        
        if not extraction:
            return data
        
        ext = extraction.extracted_data or {}
        data['facility'] = ext.get('facility', data['facility'])
        data['summary_text'] = extraction.summary
        data['timeline_events'] = extraction.timeline or []
        data['labs'] = ext.get('labs', [])
        data['medications'] = ext.get('medications', [])
        
        # Extract diagnosis with status
        data['diagnoses_with_status'] = self._extract_diagnosis_with_status(extraction)
        if data['diagnoses_with_status']:
            data['primary_diagnosis'] = data['diagnoses_with_status'][0]['name']
        
        # Calculate key signals
        data['key_signals'] = self._calculate_key_signals(extraction)
        
        # Consolidate critical findings
        data['critical_findings'] = self._consolidate_critical_findings(data['labs'])
        
        return data

# Instance
pdf_generator_service_v3 = PDFGeneratorServiceV3()
