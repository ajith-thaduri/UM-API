"""PDF Generator Service for UM Case Summaries"""

import io
import logging
import re
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable, Image as RLImage
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO

from app.core.config import settings

logger = logging.getLogger(__name__)


class PDFGeneratorService:
    """Service for generating UM case summary PDFs"""

    def __init__(self):
        self.page_width, self.page_height = letter
        self.margin = 0.75 * inch
        self.content_width = self.page_width - (2 * self.margin)
        
        # Platform color theme - Professional Medical
        # Store both Color objects (for reportlab) and hex strings (for HTML)
        self.colors = {
            'primary': colors.HexColor('#0369a1'),      # Sky Blue - Primary
            'primary_light': colors.HexColor('#0284c7'), # Sky Blue Light
            'primary_bg': colors.HexColor('#e0f2fe'),   # Sky Blue Background
            'secondary': colors.HexColor('#0d9488'),    # Teal - Secondary
            'secondary_light': colors.HexColor('#14b8a6'), # Teal Light
            'secondary_bg': colors.HexColor('#ccfbf1'), # Teal Background
            'accent': colors.HexColor('#0891b2'),      # Cyan - Accent
            'accent_bg': colors.HexColor('#e0f7fa'),   # Cyan Background
            'text_dark': colors.HexColor('#0f172a'),    # Slate Dark
            'text_medium': colors.HexColor('#334155'),   # Slate Medium
            'text_light': colors.HexColor('#64748b'),   # Slate Light
            'border': colors.HexColor('#e2e8f0'),       # Slate Border
            'background': colors.HexColor('#f8fafc'),   # Slate Background
            'success': colors.HexColor('#059669'),       # Emerald
            'warning': colors.HexColor('#d97706'),       # Amber
            'error': colors.HexColor('#dc2626'),         # Red
        }
        # Hex strings for HTML font tags
        self.color_hex = {
            'primary': '#0369a1',
            'primary_light': '#0284c7',
            'primary_bg': '#e0f2fe',
            'secondary': '#0d9488',
            'secondary_light': '#14b8a6',
            'secondary_bg': '#ccfbf1',
            'accent': '#0891b2',
            'accent_bg': '#e0f7fa',
            'text_dark': '#0f172a',
            'text_medium': '#334155',
            'text_light': '#64748b',
            'border': '#e2e8f0',
            'background': '#f8fafc',
            'success': '#059669',
            'warning': '#d97706',
            'error': '#dc2626',
        }
        
    def generate_case_pdf(
        self,
        case,
        extraction,
        case_files: List,
        patient_dob: Optional[str] = None,
        generated_by: Optional[str] = None
    ) -> bytes:
        """
        Generate PDF for a UM case
        
        Args:
            case: Case model instance
            extraction: ClinicalExtraction model instance
            case_files: List of CaseFile instances
            patient_dob: Patient date of birth (MM/DD/YYYY format)
            generated_by: Name of user who generated the PDF
            
        Returns:
            PDF bytes
        """
        buffer = io.BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=self.margin,
            leftMargin=self.margin,
            topMargin=self.margin + 0.3 * inch,  # Extra space for header
            bottomMargin=self.margin + 0.3 * inch  # Extra space for footer
        )
        
        # Build PDF content
        story = []
        
        # Cover Page (Page 1) - Case info, disclaimer, and Section 1
        story.extend(self._create_cover_page(case, extraction, patient_dob, generated_by))
        # Add Section 1 on the same page (no page break)
        story.extend(self._create_case_overview(case, extraction))
        story.extend(self._create_section_separator())
        
        # Section 2: Clinical Summary
        story.extend(self._create_clinical_summary(extraction))
        story.extend(self._create_section_separator())
        
        # Section 3: Clinical Timeline
        story.extend(self._create_timeline(extraction, case_files))
        story.extend(self._create_section_separator())
        
        # Section 4: Vitals Per-Day Ranges
        story.extend(self._create_vitals_per_day_ranges(extraction))
        story.extend(self._create_section_separator())
        
        # Section 5: Potential Missing Info
        story.extend(self._create_potential_missing_info(extraction, case_files))
        story.extend(self._create_section_separator())
        
        # Section 6: Source Index
        story.extend(self._create_source_index(case_files, extraction))
        
        # Build PDF with header and footer - pass combined info for header
        patient_name = case.patient_name or "N/A"
        case_number = case.case_number or ""
        header_text = f"{patient_name} - {case_number}" if case_number else patient_name
        
        doc.build(
            story, 
            onFirstPage=lambda canvas, doc: self._add_header_footer(canvas, doc, header_text, is_first_page=True),
            onLaterPages=lambda canvas, doc: self._add_header_footer(canvas, doc, header_text, is_first_page=False)
        )
        
        buffer.seek(0)
        return buffer.getvalue()
    
    def _create_cover_page(self, case, extraction, patient_dob: Optional[str], generated_by: Optional[str]) -> List:
        """Create cover page with professional full-width layout"""
        story = []
        styles = getSampleStyleSheet()
        
        # Determine available width (using content_width if available, else derive from page size)
        full_width = getattr(self, 'content_width', self.page_width - 2 * self.margin)
        
        # 1. Top Brand Bar - Clean and Professional
        # We use a table to create a full-width structure
        story.append(Spacer(1, 0.2 * inch))
        
        # Check for logo
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'images', 'logo.png')
        left_cell = None
        
        brand_name_para = Paragraph("<b>Brightcone</b>", ParagraphStyle(
            'BrandName',
            parent=styles['Normal'],
            fontSize=14,
            textColor=self.colors['primary'],
            fontName='Helvetica-Bold'
        ))
        
        if os.path.exists(logo_path):
            try:
                logo_img = RLImage(logo_path)
                # Resize keeping aspect ratio
                img_width = logo_img.imageWidth
                img_height = logo_img.imageHeight
                if img_height > 0:
                    aspect = img_width / float(img_height)
                    display_height = 0.45 * inch
                    display_width = display_height * aspect
                    
                    logo_img.drawHeight = display_height
                    logo_img.drawWidth = display_width
                    
                    # Nested table for Logo + Text
                    logo_table = Table([[logo_img, brand_name_para]], colWidths=[display_width + 0.1*inch, None])
                    logo_table.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                        ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ]))
                    left_cell = logo_table
            except Exception as e:
                logger.error(f"Error loading logo: {e}")
                
        if not left_cell:
            left_cell = brand_name_para

        brand_data = [[
            left_cell,
            Paragraph("Utilization Management Platform", ParagraphStyle(
                'BrandSub',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.gray,
                alignment=TA_RIGHT,
                fontName='Helvetica'
            ))
        ]]
        
        brand_table = Table(brand_data, colWidths=[full_width * 0.6, full_width * 0.4])
        brand_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('LINEBELOW', (0, 0), (-1, -1), 1, self.colors['primary']),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(brand_table)
        story.append(Spacer(1, 0.4 * inch))
        
        # 2. Document Title
        story.append(Paragraph("UM Case Summary", ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=self.colors['text_dark'],
            spaceAfter=20,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold'
        )))
        story.append(Spacer(1, 0.2 * inch))
        
        # 3. Case Information - Full Width Grid
        # Extract request metadata
        request_type = "To be determined"
        if extraction and extraction.extracted_data and isinstance(extraction.extracted_data, dict):
            request_metadata = extraction.extracted_data.get('request_metadata', {})
            if request_metadata.get('request_type') and request_metadata.get('request_type') != 'Not specified':
                request_type = request_metadata.get('request_type')

        # Prepare data with labels and values
        # We'll use a 2-column layout (Label | Value) spanning full width
        info_data = [
            ["Case ID", str(case.id)],
            ["Case Number", str(case.case_number)],
            ["Member Name", self._clean_header_text(case.patient_name or "N/A")],
            ["Member ID", str(case.patient_id or "N/A")],
            ["Date of Birth", str(patient_dob or "Not documented")],
            ["Request Type", str(request_type)],
            ["Generated Date", datetime.now().strftime("%B %d, %Y")]
        ]
        
        # Create table data
        table_rows = []
        for label, value in info_data:
            # Label Style
            label_p = Paragraph(label, ParagraphStyle(
                'MetaLabel',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.gray,
                fontName='Helvetica-Bold'
            ))
            # Value Style
            value_p = Paragraph(value, ParagraphStyle(
                'MetaValue',
                parent=styles['Normal'],
                fontSize=11,
                textColor=colors.black,
                fontName='Helvetica'
            ))
            table_rows.append([label_p, value_p])

        # Table with professional styling
        # Width split: 30% Label, 70% Value
        info_table = Table(table_rows, colWidths=[full_width * 0.3, full_width * 0.7])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),  # Align with header
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')), # Light gray dividers
        ]))
        
        story.append(info_table)
        story.append(Spacer(1, 0.5 * inch))
        
        # 4. Disclaimer - Subtle and Integrated
        disclaimer_style = ParagraphStyle(
            'DisclaimerStyle',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.gray,
            alignment=TA_LEFT,
            fontName='Helvetica-Oblique'
        )
        story.append(Paragraph("Disclaimer: This summary is generated by AI for review purposes only. It does not constitute a final medical decision or recommendation.", disclaimer_style))
        story.append(Spacer(1, 0.4 * inch))
        
        return story
    
    def _create_case_overview(self, case, extraction) -> List:
        """Create Case Overview section"""
        story = []
        styles = getSampleStyleSheet()
        
        # Section Header - Branded with color
        header_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.white,
            backColor=self.colors['primary'],
            spaceAfter=12,
            spaceBefore=12,
            fontName='Helvetica-Bold',
            borderWidth=0,
            borderPadding=10,
            leftIndent=10,
            rightIndent=10
        )
        story.append(Paragraph("Section 1: Case Overview", header_style))
        story.append(Spacer(1, 0.15 * inch))  # Space after header before content
        
        # Content - Professional, monochrome
        content_style = ParagraphStyle(
            'ContentStyle',
            parent=styles['Normal'],
            fontSize=10,
            leading=16,
            spaceAfter=8
        )
        
        # Extract request metadata from extraction
        request_metadata = {}
        if extraction and extraction.extracted_data and isinstance(extraction.extracted_data, dict):
            request_metadata = extraction.extracted_data.get('request_metadata', {})
        
        # Request Type
        request_type = request_metadata.get('request_type', 'Not specified')
        if request_type == 'Not specified':
            request_type = 'To be determined'
        story.append(Paragraph(
            f'<b>Request Type:</b> {request_type}',
            content_style
        ))
        
        # Requested Service
        requested_service = request_metadata.get('requested_service', 'Not specified')
        if requested_service == 'Not specified':
            requested_service = 'To be determined'
        story.append(Paragraph(
            f'<b>Requested Service:</b> {requested_service}',
            content_style
        ))
        
        # Diagnosis
        diagnoses = []
        if extraction and extraction.extracted_data and isinstance(extraction.extracted_data, dict):
            extracted_diagnoses = extraction.extracted_data.get('diagnoses', [])
            for dx in extracted_diagnoses[:5]:  # First 5 diagnoses
                if isinstance(dx, str):
                    diagnoses.append(dx)
                elif isinstance(dx, dict):
                    name = dx.get('name', '')
                    if name:
                        diagnoses.append(name)
        
        diagnosis_text = ", ".join(diagnoses) if diagnoses else "Not explicitly documented"
        story.append(Paragraph(
            f'<b>Diagnosis (as documented):</b> {diagnosis_text}',
            content_style
        ))
        
        # Request Date
        request_date = request_metadata.get('request_date', 'Not specified')
        if request_date == 'Not specified':
            # Fallback to uploaded_at if request_date not available
            request_date = case.uploaded_at.strftime("%m/%d/%Y") if case.uploaded_at else "To be determined"
        story.append(Paragraph(
            f'<b>Request Date:</b> {request_date}',
            content_style
        ))
        
        # Urgency
        urgency = request_metadata.get('urgency', 'Routine')
        if urgency == 'Routine' and not request_metadata:
            # Fallback: derive from priority if no request metadata
            urgency_map = {
                'urgent': 'Expedited',
                'high': 'Expedited',
                'normal': 'Routine',
                'low': 'Routine'
            }
            urgency = urgency_map.get(
                case.priority.value.lower() if case.priority else 'normal',
                'Routine'
            )
        story.append(Paragraph(
            f'<b>Urgency:</b> {urgency}',
            content_style
        ))
        
        return story
    
    def _create_timeline(self, extraction, case_files: List) -> List:
        """Create Clinical Timeline section - Grouped by Category"""
        story = []
        styles = getSampleStyleSheet()
        
        # Section Header - Branded with color (NO EMOJI)
        header_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.white,
            backColor=self.colors['primary'],
            spaceAfter=12,
            spaceBefore=12,
            fontName='Helvetica-Bold',
            borderPadding=10,
            leftIndent=0,
            rightIndent=0
        )
        story.append(Paragraph("Section 3: Clinical Timeline", header_style))
        
        # Styles
        subheader_style = ParagraphStyle(
            'TimelineSubHeader',
            parent=styles['Heading3'],
            fontSize=12,
            textColor=self.colors['primary'],
            spaceAfter=6,
            spaceBefore=10,
            fontName='Helvetica-Bold'
        )
        
        timeline_style = ParagraphStyle(
            'TimelineStyle',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            spaceAfter=4
        )
        
        if extraction and extraction.timeline:
            timeline_events = extraction.timeline
            if isinstance(timeline_events, list):
                # Create file lookup for source references
                file_lookup = {f.id: f.file_name for f in case_files}
                
                # Process and deduplicate events
                processed_events = []
                seen_dates_descriptions = set()
                
                for event in timeline_events:
                    if not isinstance(event, dict):
                        continue
                    
                    date = event.get('date', '')
                    description = event.get('description', '').strip()
                    
                    # Skip if no date or description
                    if not date or not description:
                        continue
                        
                    # Fix unicode characters that might break rendering
                    description = description.replace('₂', '2').replace('°', ' degrees ')
                    
                    # Normalize date to YYYY-MM-DD format
                    normalized_date = self._normalize_date_for_timeline(date)
                    if not normalized_date:
                        continue
                    
                    # Remove narrative/inference language
                    clean_description = self._remove_inference_language(description)
                    
                    # Get source information
                    source_file = event.get('source_file')
                    source_page = event.get('source_page')
                    
                    if not source_file or not source_page:
                        details = event.get('details', {})
                        if isinstance(details, dict):
                            source_file = source_file or details.get('source_file')
                            source_page = source_page or details.get('source_page')
                    
                    # Handle both file_id (UUID) and file_name (string)
                    file_name = None
                    if source_file:
                        if source_file in file_lookup:
                            file_name = file_lookup[source_file]
                        else:
                            file_name = source_file
                    
                    # Skip events without source
                    if not file_name or not source_page:
                        continue
                    
                    # Create unique key for deduplication
                    dedup_key = (normalized_date, clean_description.lower())
                    if dedup_key in seen_dates_descriptions:
                        continue
                    seen_dates_descriptions.add(dedup_key)
                    
                    # Determine event type and label (NO EMOJI)
                    label = ""
                    event_type = "general"
                    desc_lower = clean_description.lower()
                    
                    if any(word in desc_lower for word in ['diagnosed', 'diagnosis', 'assessment', 'impression']):
                        label = "[Dx] "
                        event_type = "diagnosis"
                    elif any(word in desc_lower for word in ['blood pressure', 'heart rate', 'respiratory', 'temperature', 'oxygen', 'spo2', 'pulse']):
                        label = "[VS] "
                        event_type = "vital"
                    elif any(word in desc_lower for word in ['wbc', 'hemoglobin', 'creatinine', 'lab', 'test', 'culture', 'panel']):
                        label = "[Lab] "
                        event_type = "lab"
                    elif any(word in desc_lower for word in ['medication', 'drug', 'prescribed', 'administered', 'dosage']):
                        label = "[Med] "
                        event_type = "medication"
                    
                    processed_events.append({
                        'date': normalized_date,
                        'description': clean_description,
                        'source': f"{file_name}, p{source_page}",
                        'label': label,
                        'type': event_type
                    })
                
                # Sort all events chronologically first
                processed_events.sort(key=lambda x: x['date'])
                
                # Group events using a dictionary
                groups = {
                    'diagnosis': [],
                    'medication': [],
                    'lab': [],
                    'vital': [],
                    'general': []
                }
                
                for event in processed_events:
                    if event['type'] in groups:
                        groups[event['type']].append(event)
                    else:
                        groups['general'].append(event)
                
                # Define presentation order
                group_display = [
                    ('diagnosis', 'Diagnoses'),
                    ('medication', 'Medications'),
                    ('lab', 'Lab Reports'),
                    ('vital', 'Vital Signs'),
                    ('general', 'General / Other Events')
                ]
                
                has_any_content = False
                
                for group_key, group_title in group_display:
                    events = groups.get(group_key, [])
                    if not events:
                        continue
                        
                    has_any_content = True
                    
                    # Add grouping header
                    story.append(Paragraph(group_title, subheader_style))
                    
                    # Create table for this group
                    table_data = [[
                        Paragraph("<b>Date</b>", timeline_style),
                        Paragraph("<b>Event</b>", timeline_style),
                        Paragraph("<b>Source</b>", timeline_style)
                    ]]
                    
                    for event in events:
                        date_para = Paragraph(f"<b>{event['date']}</b>", timeline_style)
                        # Remove the label prefix [Dx] etc since we are in a grouped section
                        clean_desc = event['description'] # Description is already without label
                        # But wait, label was stored separately. 
                        # We don't need label anymore if grouped, cleaner look.
                        display_text = clean_desc
                        
                        # Highlight abnormal values/keywords
                        display_text = self._highlight_abnormalities(display_text)
                        
                        event_para = Paragraph(display_text, timeline_style)
                        source_para = Paragraph(f"<i>{event['source']}</i>", timeline_style)
                        table_data.append([date_para, event_para, source_para])
                    
                    # Create table with brand colors
                    timeline_table = Table(table_data, colWidths=[1.2*inch, 4.3*inch, 1.5*inch])
                    timeline_table.setStyle(TableStyle([
                        # Header
                        ('BACKGROUND', (0, 0), (-1, 0), self.colors['primary']),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                        ('ALIGN', (2, 0), (2, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 10),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                        ('TOPPADDING', (0, 0), (-1, 0), 8),
                        # Body rows
                        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 1), (-1, -1), 9),
                        ('TOPPADDING', (0, 1), (-1, -1), 6),
                        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                        ('LEFTPADDING', (0, 0), (-1, -1), 8),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                        # Grid and borders
                        ('GRID', (0, 0), (-1, -1), 0.5, self.colors['border']),
                        ('LINEBELOW', (0, 0), (-1, 0), 2, self.colors['primary']),
                        # Alternating row colors
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.colors['primary_bg']]),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ]))
                    
                    story.append(timeline_table)
                    story.append(Spacer(1, 0.15 * inch))

                if not has_any_content:
                    story.append(Paragraph("No timeline events with source references available.", timeline_style))
            else:
                story.append(Paragraph("No timeline events available.", timeline_style))
        else:
            story.append(Paragraph("No timeline events available.", timeline_style))
        
        return story
    
    def _normalize_date_for_timeline(self, date_str: str) -> Optional[str]:
        if not date_str:
            return None
        
        # Try common date formats
        date_formats = [
            '%Y-%m-%d',           # 2024-01-15
            '%m/%d/%Y',           # 01/15/2024
            '%m-%d-%Y',           # 01-15-2024
            '%Y/%m/%d',           # 2024/01/15
            '%B %d, %Y',          # January 15, 2024
            '%b %d, %Y',          # Jan 15, 2024
            '%d/%m/%Y',           # 15/01/2024
            '%m/%d/%y',           # 01/15/24
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        return None
    
    def _remove_inference_language(self, text: str) -> str:
        """Remove causal, temporal, or narrative inference language"""
        # Remove common inference phrases
        inference_patterns = [
            r'marking the beginning\s*[.,]?\s*',
            r'persisted for\s+',
            r'continued for\s+',
            r'lasting\s+',
            r'indicating\s+',
            r'suggesting\s+',
            r'consistent with\s+',
            r'likely\s+',
            r'probably\s+',
            r'appears to\s+',
            r'seems to\s+',
        ]
        
        cleaned = text
        for pattern in inference_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def _highlight_abnormalities(self, text: str) -> str:
        """Highlight abnormal values/keywords in text with red color"""
        keywords = [
            r'\bhigh\b', r'\belevated\b',
            r'\babnormal\b', r'\bcritical\b', r'\bsevere\b',
            r'\bhypertension\b', r'\bhypotension\b', r'\btachycardia\b',
            r'\bbradycardia\b', r'\bhypoxia\b', r'\bfev(?:er|rile)\b',
            r'\bsepsis\b', r'\bsepti(?:c|cemia)\b',
            r'\bfailure\b', r'\bdistress\b'
        ]
        
        # Color: Red-600 equivalent
        color = '#dc2626'
        
        for pattern in keywords:
            # use re.sub with a function to preserve case of matched text
            # Add bold and color
            text = re.sub(pattern, lambda m: f"<font color='{color}'><b>{m.group(0)}</b></font>", text, flags=re.IGNORECASE)
            
        return text
    
    def _create_clinical_summary(self, extraction) -> List:
        """Create Clinical Summary section - Structured with Diagnoses and Medications"""
        story = []
        styles = getSampleStyleSheet()
        
        # Section Header
        header_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.white,
            backColor=self.colors['primary'],
            spaceAfter=12,
            spaceBefore=12,
            fontName='Helvetica-Bold',
            borderPadding=10,
            leftIndent=0,
            rightIndent=0
        )
        story.append(Paragraph("Section 2: Clinical Summary", header_style))
        story.append(Spacer(1, 0.1 * inch))
        
        # Styles for subsections
        subheader_style = ParagraphStyle(
            'SubHeader',
            parent=styles['Heading3'],
            fontSize=12,
            textColor=self.colors['primary'],
            spaceAfter=6,
            spaceBefore=8,
            fontName='Helvetica-Bold'
        )
        
        body_style = ParagraphStyle(
            'BodyText',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            spaceAfter=6,
            alignment=TA_LEFT
        )
        
        bullet_style = ParagraphStyle(
            'BulletStyle',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            spaceAfter=4,
            leftIndent=15,
            bulletIndent=0,
            alignment=TA_LEFT
        )

        if extraction:
            # 1. Clinical Highlights (The main summary)
            story.append(Paragraph("Clinical Highlights", subheader_style))
            
            summary_text = extraction.summary if extraction.summary else ""
            if summary_text:
                # Cleaner bullet extraction logic
                bullet_points = self._extract_summary_bullets(summary_text)
                if bullet_points:
                    for bullet in bullet_points:
                        # Clean initial bullet
                        full_bullet = bullet.lstrip('•').lstrip('-').strip()
                        
                        # Filter out disclaimer boilerplate immediately
                        if "informational only" in full_bullet.lower() or "utilization management decision" in full_bullet.lower():
                            continue

                        # Split by " - " to handle multipart lines (e.g. "Name: X - Reason: Y")
                        # We use a regex to split on " - " or " – " but keep the delimiter to check context if needed? 
                        # Actually just splitting is fine.
                        segments = re.split(r'\s+[-–]\s+', full_bullet)
                        
                        for segment in segments:
                            clean_segment = segment.strip()
                            if not clean_segment:
                                continue
                            
                            # Filter out metadata segments effectively
                            # aggressive check for "Patient Name: ..." type segments
                            if any(key in clean_segment.lower() for key in ['patient name:', 'dob:', 'date of birth:', 'case id:', 'member id:', 'generated date:']):
                                 continue
                            
                            # Additional cleanup for "Patient Name: John Doe" if it slipped through w/o colon specific check
                            if clean_segment.lower().startswith('patient:') or clean_segment.lower().startswith('member:'):
                                continue

                            # Format "Key: Value" as "<b>Key:</b> Value"
                            if ':' in clean_segment:
                                parts = clean_segment.split(':', 1)
                                key = parts[0].strip()
                                val = parts[1].strip()
                                # Only bold if key is reasonable length (side heading)
                                if len(key) < 40 and not any(c in key for c in ['.', ',']):
                                    clean_segment = f"<b>{key}:</b> {val}"
                            
                            story.append(Paragraph(f"• {clean_segment}", bullet_style))
                else:
                    story.append(Paragraph("No detailed summary available.", body_style))
            else:
                story.append(Paragraph("No clinical highlights available.", body_style))
            
            # 2. Current Diagnoses (from extracted_data)
            story.append(Paragraph("Current Diagnoses", subheader_style))
            
            diagnoses = []
            if extraction.extracted_data and isinstance(extraction.extracted_data, dict):
                # Try multiple keys for diagnoses
                for key in ['diagnoses', 'diagnosis_list', 'active_diagnoses', 'current_diagnoses']:
                    if key in extraction.extracted_data:
                        d_data = extraction.extracted_data[key]
                        if isinstance(d_data, list):
                            diagnoses = d_data
                            break
                        elif isinstance(d_data, str):
                             diagnoses = [d.strip() for d in d_data.split('\n') if d.strip()]
                             break
            
            if diagnoses:
                for diag in diagnoses:
                    if isinstance(diag, dict):
                        diag_text = diag.get('name', diag.get('description', ''))
                        code = diag.get('code', '')
                        if code:
                            diag_text += f" ({code})"
                    else:
                        diag_text = str(diag)
                    
                    if diag_text:
                        story.append(Paragraph(f"• {diag_text}", bullet_style))
            else:
                 # Fallback: try to extract from summary text if not explicit
                 story.append(Paragraph("<i>Refer to clinical timeline for diagnosis details.</i>", body_style))

            # 3. Medication Summary
            story.append(Paragraph("Medication Summary", subheader_style))
            
            meds = []
            if extraction.extracted_data and isinstance(extraction.extracted_data, dict):
                # Try multiple keys for medications
                for key in ['medications', 'medication_list', 'active_medications', 'drugs']:
                    if key in extraction.extracted_data:
                        m_data = extraction.extracted_data[key]
                        if isinstance(m_data, list):
                            meds = m_data
                            break
                        elif isinstance(m_data, str):
                            meds = [m.strip() for m in m_data.split('\n') if m.strip()]
                            break

            if meds:
                for med in meds:
                    if isinstance(med, dict):
                        med_name = med.get('name', med.get('drug_name', ''))
                        dose = med.get('dosage', med.get('dose', ''))
                        freq = med.get('frequency', '')
                        med_text = f"<b>{med_name}</b>"
                        if dose: med_text += f" {dose}"
                        if freq: med_text += f", {freq}"
                    else:
                        med_text = str(med)
                    
                    if med_text:
                        story.append(Paragraph(f"• {med_text}", bullet_style))
            else:
                story.append(Paragraph("<i>No active medications strictly extracted. Verify with source documents.</i>", body_style))
                
        else:
            story.append(Paragraph("No clinical summary data available.", body_style))
        
        return story
    
    def _extract_summary_bullets(self, summary_text: str) -> List[str]:
        """Extract 5-7 plain language bullet points from summary"""
        bullets = []
        
        # Clean and split summary
        text = summary_text.strip()
        
        # Remove metadata headers and separators first
        lines = text.split('\n')
        content_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Remove separator lines (---, ===, etc.)
            if re.match(r'^[-=]{3,}$', line):
                continue
            
            # Remove metadata headers (PATIENT:, CASE NUMBER:, SUMMARY DATE:, etc.)
            if re.match(r'^(PATIENT|CASE NUMBER|SUMMARY DATE|CASE|MEMBER|DATE OF BIRTH|DOB|MRN):', line, re.IGNORECASE):
                continue
            
            # Remove lines that are just metadata (e.g., "PATIENT: John A Smith CASE NUMBER: UM-2025-BF9C")
            if re.search(r'(PATIENT|CASE NUMBER|SUMMARY DATE|CASE|MEMBER|DATE OF BIRTH|DOB|MRN):', line, re.IGNORECASE):
                # Extract only the content after metadata
                # Remove everything before and including the colon patterns
                line = re.sub(r'^.*?(?:PATIENT|CASE NUMBER|SUMMARY DATE|CASE|MEMBER|DATE OF BIRTH|DOB|MRN):\s*', '', line, flags=re.IGNORECASE)
                line = re.sub(r'\s*(?:PATIENT|CASE NUMBER|SUMMARY DATE|CASE|MEMBER|DATE OF BIRTH|DOB|MRN):\s*.*$', '', line, flags=re.IGNORECASE)
                line = line.strip()
                if not line or len(line) < 10:
                    continue
            
            # Skip headings (all caps, markdown headers, numbered sections)
            if (re.match(r'^[A-Z][A-Z\s&]+$', line) and len(line.split()) >= 2) or \
               re.match(r'^#+\s+', line) or \
               re.match(r'^\d+\.\s+[A-Z]', line) or \
               re.match(r'^\*\*(.+?)\*\*$', line) or \
               "timeline highlights" in line.lower() or \
               "key lab" in line.lower() or \
               "diagnostic findings" in line.lower():
                continue
            
            content_lines.append(line)
        
        # Join and split into sentences
        full_text = ' '.join(content_lines)
        
        # Remove remaining metadata patterns
        full_text = re.sub(r'(PATIENT|CASE NUMBER|SUMMARY DATE|CASE|MEMBER|DATE OF BIRTH|DOB|MRN):\s*[^\s]+\s*', '', full_text, flags=re.IGNORECASE)
        full_text = re.sub(r'---+', '', full_text)  # Remove separator dashes
        
        # Split into sentences
        sentences = re.split(r'[.!?]\s+', full_text)
        
        # Group related sentences into bullet points
        current_bullet = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 10:
                continue
            
            # Remove markdown formatting
            sentence = re.sub(r'\*\*(.+?)\*\*', r'\1', sentence)
            sentence = re.sub(r'<[^>]+>', '', sentence)
            
            # Remove inference language
            sentence = self._remove_inference_language(sentence)
            
            # Clean up
            sentence = self._clean_text(sentence)
            
            # Skip if too short after cleaning
            if len(sentence) < 15:
                continue
            
            # Skip if contains timeline narrative or metadata
            if any(word in sentence.lower() for word in [
                'timeline', 'chronological', 'sequence', 'progression',
                'patient:', 'case number:', 'summary date:', 'case:', 'member:'
            ]):
                continue
            
            # Skip sentences that are just metadata
            if re.search(r'^(PATIENT|CASE NUMBER|SUMMARY DATE|CASE|MEMBER):', sentence, re.IGNORECASE):
                continue
            
            current_bullet.append(sentence)
            
            # Create bullet when we have 1-2 sentences (aim for 5-7 total bullets)
            if len(current_bullet) >= 1 and len(bullets) < 7:
                bullet_text = ' '.join(current_bullet)
                if len(bullet_text) > 20:  # Minimum length
                    # Clean up the bullet text
                    bullet_text = re.sub(r'\s+', ' ', bullet_text).strip()
                    bullets.append(bullet_text[:200])  # Max length per bullet
                    current_bullet = []
        
        # Add remaining if we have less than 5
        if len(bullets) < 5 and current_bullet:
            bullet_text = ' '.join(current_bullet)
            bullet_text = re.sub(r'\s+', ' ', bullet_text).strip()
            if len(bullet_text) > 20:
                bullets.append(bullet_text[:200])
        
        return bullets[:7]  # Max 7 bullets
    
    def _neutralize_decision_language(self, text: str) -> str:
        """Replace decision/approval language with neutral documentation language"""
        replacements = {
            r'\bapproved\b': 'documented',
            r'\bdenied\b': 'not documented',
            r'\bauthorized\b': 'requested per records',
            r'\bauthorization\b': 'request',
            r'\bapproval\b': 'documentation',
            r'\bdenial\b': 'absence of documentation',
        }
        
        cleaned = text
        for pattern, replacement in replacements.items():
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        
        return cleaned
    
    def _clean_text(self, text: str) -> str:
        """Clean and escape text for PDF"""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        # Escape HTML special chars that reportlab doesn't handle
        text = text.replace('&', '&amp;')
        return text.strip()
    
    def _create_vitals_per_day_ranges(self, extraction) -> List:
        """Create Vitals Per-Day Ranges section"""
        story = []
        styles = getSampleStyleSheet()
        
        # Section Header - Branded with color (NO EMOJI)
        header_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.white,
            backColor=self.colors['primary'],
            spaceAfter=12,
            spaceBefore=12,
            fontName='Helvetica-Bold',
            borderPadding=10,
            leftIndent=0,
            rightIndent=0
        )
        story.append(Paragraph("Section 4: Vital Signs Trends", header_style))
        story.append(Spacer(1, 0.2 * inch))
        
        # Get vitals per-day ranges from extracted data
        vitals_ranges = None
        if extraction and extraction.extracted_data:
            if isinstance(extraction.extracted_data, dict):
                vitals_ranges = extraction.extracted_data.get("vitals_per_day_ranges")
        
        if not vitals_ranges or not isinstance(vitals_ranges, dict) or len(vitals_ranges) == 0:
            story.append(Paragraph("No vital signs data available.", styles['Normal']))
            return story
        
        # Enhanced table style with brand colors
        table_style = TableStyle([
            # Header with brand color
            ('BACKGROUND', (0, 0), (-1, 0), self.colors['primary']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            # Body rows
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), self.colors['text_dark']),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            # Grid and borders with brand color
            ('GRID', (0, 0), (-1, -1), 1, self.colors['border']),
            ('LINEBELOW', (0, 0), (-1, 0), 2, self.colors['primary']),
            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.colors['primary_bg']]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])
        
        # Build table data
        table_data = [["Date", "Blood Pressure\n(mmHg)", "Heart Rate\n(bpm)", "SpO2\n(%)", "Temperature\n(F)"]]
        
        # Sort by date
        def parse_date_for_sort(date_str: str) -> datetime:
            """Parse date string for sorting"""
            if not date_str:
                return datetime.min
            try:
                return datetime.strptime(date_str, "%m/%d/%Y")
            except:
                try:
                    return datetime.strptime(date_str, "%Y-%m-%d")
                except:
                    return datetime.min
        
        sorted_dates = sorted(vitals_ranges.keys(), key=parse_date_for_sort)
        
        for date_str in sorted_dates:
            day_range = vitals_ranges[date_str]
            if not isinstance(day_range, dict):
                continue
            
            # Only add row if at least one vital sign has data
            has_data = False
            bp_text = "—"
            hr_text = "—"
            spo2_text = "—"
            temp_text = "—"
            
            # Format ranges - only show if data exists
            bp_range = day_range.get("blood_pressure")
            if bp_range and bp_range != "Range not available":
                if isinstance(bp_range, dict) and bp_range.get('min') and bp_range.get('max'):
                    min_val, max_val = bp_range['min'], bp_range['max']
                    bp_text = f"{min_val} - {max_val}" if min_val != max_val else str(min_val)
                    has_data = True
                elif isinstance(bp_range, str):
                    bp_text = bp_range
                    has_data = True
            
            hr_range = day_range.get("heart_rate")
            if hr_range and hr_range != "Range not available":
                if isinstance(hr_range, dict) and hr_range.get('min') and hr_range.get('max'):
                    min_val, max_val = hr_range['min'], hr_range['max']
                    hr_text = f"{min_val} - {max_val}" if min_val != max_val else str(min_val)
                    has_data = True
                elif isinstance(hr_range, str):
                    hr_text = hr_range
                    has_data = True
            
            spo2_range = day_range.get("spO2")
            if spo2_range and spo2_range != "Range not available":
                if isinstance(spo2_range, dict) and spo2_range.get('min') and spo2_range.get('max'):
                    min_val, max_val = spo2_range['min'], spo2_range['max']
                    spo2_text = f"{min_val} - {max_val}" if min_val != max_val else str(min_val)
                    has_data = True
                elif isinstance(spo2_range, str):
                    spo2_text = spo2_range
                    has_data = True
            
            temp_range = day_range.get("temperature")
            if temp_range and temp_range != "Range not available":
                if isinstance(temp_range, dict) and temp_range.get('min') and temp_range.get('max'):
                    min_val, max_val = temp_range['min'], temp_range['max']
                    temp_text = f"{min_val} - {max_val}" if min_val != max_val else str(min_val)
                    has_data = True
                elif isinstance(temp_range, str):
                    temp_text = temp_range
                    has_data = True
            
            # Only add row if we have at least some data
            if has_data:
                table_data.append([date_str, bp_text, hr_text, spo2_text, temp_text])
        
        # Create table
        vitals_table = Table(table_data, colWidths=[
            self.content_width * 0.18,  # Date
            self.content_width * 0.22,  # BP
            self.content_width * 0.18,  # HR
            self.content_width * 0.18,  # SpO2
            self.content_width * 0.24   # Temperature
        ])
        vitals_table.setStyle(table_style)
        
        story.append(vitals_table)
        story.append(Spacer(1, 0.2 * inch))
        
        return story
    
    def _create_potential_missing_info(self, extraction, case_files: List) -> List:
        """Create Potential Missing Info section - MVP compliant tentative language"""
        story = []
        styles = getSampleStyleSheet()
        
        # Section Header - Branded with color (NO EMOJI)
        header_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.white,
            backColor=self.colors['primary'],
            spaceAfter=12,
            spaceBefore=12,
            fontName='Helvetica-Bold',
            borderPadding=10,
            leftIndent=0,
            rightIndent=0
        )
        story.append(Paragraph("Section 5: Potential Missing Info / Red Flags", header_style))
        story.append(Spacer(1, 0.2 * inch))
        
        # Items style
        item_style = ParagraphStyle(
            'ItemStyle',
            parent=styles['Normal'],
            fontSize=11,
            leading=16,
            spaceAfter=10,
            leftIndent=15,
            bulletIndent=15
        )
        
        if extraction and extraction.contradictions:
            contradictions = extraction.contradictions
            if isinstance(contradictions, list) and len(contradictions) > 0:
                # Create file lookup for source references
                file_lookup = {f.id: f.file_name for f in case_files}
                
                for item in contradictions:
                    if not isinstance(item, dict):
                        continue
                    
                    description = item.get('description', 'No description')
                    suggestion = item.get('suggestion', '')
                    
                    # Get source information if available
                    sources = item.get('sources', [])
                    source_info = ""
                    if sources and isinstance(sources, list) and len(sources) > 0:
                        first_source = sources[0]
                        if isinstance(first_source, dict):
                            source_file = first_source.get('file')
                            source_page = first_source.get('page')
                            if source_file:
                                if source_file in file_lookup:
                                    file_name = file_lookup[source_file]
                                else:
                                    file_name = source_file
                                
                                if source_page:
                                    source_info = f' <i>[Source: {file_name}, Page {source_page}]</i>'
                                else:
                                    source_info = f' <i>[Source: {file_name}]</i>'
                    
                    # Neutralize decision language
                    description = self._neutralize_decision_language(description)
                    
                    if suggestion:
                        suggestion = self._neutralize_decision_language(suggestion)
                        text = f'• {description} <i>({suggestion})</i>{source_info}'
                    else:
                        text = f'• {description} <i>(May require review)</i>{source_info}'
                    
                    story.append(Paragraph(text, item_style))
            else:
                # MVP compliant: Use tentative language
                story.append(Paragraph("No missing information noted in the reviewed documentation.", item_style))
        else:
            # MVP compliant: Use tentative language
            story.append(Paragraph("No missing information noted in the reviewed documentation.", item_style))
        
        return story
    
    def _create_source_index(self, case_files: List, extraction=None) -> List:
        """Create Source Index section - MVP compliant with specific page references"""
        story = []
        styles = getSampleStyleSheet()
        
        # Section Header - Branded with color (NO EMOJI)
        header_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.white,
            backColor=self.colors['primary'],
            spaceAfter=12,
            spaceBefore=12,
            fontName='Helvetica-Bold',
            borderPadding=10,
            leftIndent=0,
            rightIndent=0
        )
        story.append(Paragraph("Section 6: Source Index", header_style))
        story.append(Spacer(1, 0.2 * inch))
        
        # Collect referenced pages from timeline and other sources
        file_pages_map = {}  # {file_name: set of page numbers}
        file_lookup = {f.id: f.file_name for f in case_files}
        
        # Collect pages from timeline events
        if extraction and extraction.timeline:
            timeline_events = extraction.timeline
            if isinstance(timeline_events, list):
                for event in timeline_events:
                    if not isinstance(event, dict):
                        continue
                    
                    source_file = event.get('source_file')
                    source_page = event.get('source_page')
                    
                    if not source_file or not source_page:
                        details = event.get('details', {})
                        if isinstance(details, dict):
                            source_file = source_file or details.get('source_file')
                            source_page = source_page or details.get('source_page')
                    
                    if source_file and source_page:
                        file_name = file_lookup.get(source_file, source_file)
                        if file_name not in file_pages_map:
                            file_pages_map[file_name] = set()
                        # Safely parse page number (handles 'Page 5', '5', etc.)
                        try:
                            page_num = self._safe_parse_page_number(source_page)
                            if page_num is not None:
                                file_pages_map[file_name].add(page_num)
                        except (ValueError, TypeError):
                            pass
        
        # Collect pages from contradictions/red flags
        if extraction and extraction.contradictions:
            contradictions = extraction.contradictions
            if isinstance(contradictions, list):
                for item in contradictions:
                    if not isinstance(item, dict):
                        continue
                    
                    sources = item.get('sources', [])
                    if sources and isinstance(sources, list):
                        for source in sources:
                            if isinstance(source, dict):
                                source_file = source.get('file')
                                source_page = source.get('page')
                                if source_file and source_page:
                                    file_name = file_lookup.get(source_file, source_file)
                                    if file_name not in file_pages_map:
                                        file_pages_map[file_name] = set()
                                    try:
                                        page_num = self._safe_parse_page_number(source_page)
                                        if page_num is not None:
                                            file_pages_map[file_name].add(page_num)
                                    except (ValueError, TypeError):
                                        pass
        
        # Table Data - Simplified (removed timestamp column)
        table_data = [["Document Name", "Pages Referenced", "Upload Date"]]
        
        # Sort files by file_order or uploaded_at
        sorted_files = sorted(case_files, key=lambda f: f.file_order if f.file_order is not None else 0)
        
        for case_file in sorted_files:
            upload_date = case_file.uploaded_at.strftime("%Y-%m-%d") if case_file.uploaded_at else "N/A"
            
            # Get referenced pages for this file
            referenced_pages = file_pages_map.get(case_file.file_name, set())
            if referenced_pages:
                # Format pages as "1-2, 5, 7-9" style
                pages_list = sorted(referenced_pages)
                pages_str = self._format_page_range(pages_list)
            else:
                pages_str = "—"
            
            table_data.append([
                case_file.file_name,
                pages_str,
                upload_date
            ])
        
        # Create table with professional branded styling
        table = Table(table_data, colWidths=[3.5*inch, 2*inch, 1.5*inch])
        table.setStyle(TableStyle([
            # Header with brand color
            ('BACKGROUND', (0, 0), (-1, 0), self.colors['primary']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            # Body rows
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), self.colors['text_dark']),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            # Grid and borders with brand color
            ('GRID', (0, 0), (-1, -1), 1, self.colors['border']),
            ('LINEBELOW', (0, 0), (-1, 0), 2, self.colors['primary']),
            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.colors['primary_bg']]),
        ]))
        
        story.append(table)
        
        return story
    
    def _format_page_range(self, pages: List[int]) -> str:
        """Format list of page numbers as ranges (e.g., '1-2, 5, 7-9')"""
        if not pages:
            return "N/A"
        
        pages = sorted(set(pages))
        if len(pages) == 1:
            return str(pages[0])
        
        ranges = []
        start = pages[0]
        end = pages[0]
        
        for i in range(1, len(pages)):
            if pages[i] == end + 1:
                end = pages[i]
            else:
                if start == end:
                    ranges.append(str(start))
                else:
                    ranges.append(f"{start}-{end}")
                start = pages[i]
                end = pages[i]
        
        # Add last range
        if start == end:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}-{end}")
        
        return ", ".join(ranges)
    
    def _safe_parse_page_number(self, source_page) -> int:
        """
        Safely parse a page number from various formats.
        
        Handles formats like:
        - 5 (integer)
        - '5' (string integer)
        - 'Page 5' (descriptive string)
        - 'pg 5', 'p. 5', 'page: 5' (various formats)
        
        Returns:
            int: The parsed page number, or None if parsing fails
        """
        if source_page is None:
            return None
        
        # If already an int, return as-is
        if isinstance(source_page, int):
            return source_page
        
        # Convert to string for processing
        page_str = str(source_page).strip()
        
        # Try direct integer conversion first
        try:
            return int(page_str)
        except ValueError:
            pass
        
        # Try to extract number from descriptive strings like 'Page 5', 'pg 5', etc.
        import re
        match = re.search(r'\d+', page_str)
        if match:
            return int(match.group())
        
        return None
    
    def _clean_header_text(self, text: str) -> str:
        """Sanitize text for header to prevent rendering issues"""
        if not text:
            return ""
        # Replace non-breaking spaces and other invisible chars with normal space
        text = re.sub(r'[\u00a0\u200b\u202f\u2060]', ' ', text)
        # Squeeze multiple spaces
        text = re.sub(r'\s+', ' ', text)
        # Remove any non-printable chars (except specific safe ones)
        text = ''.join(c for c in text if c.isprintable())
        return text.strip()

    def _add_header_footer(self, canvas_obj: canvas.Canvas, doc: SimpleDocTemplate, header_text: str = "N/A", is_first_page: bool = False):
        """Add header and footer to every page"""
        page_num = canvas_obj.getPageNumber()
        
        # Header line - Show on all pages (monochrome)
        canvas_obj.setStrokeColor(colors.HexColor('#cccccc'))
        canvas_obj.setLineWidth(0.5)
        canvas_obj.line(
            self.margin,
            self.page_height - self.margin - 15,
            self.page_width - self.margin,
            self.page_height - self.margin - 15
        )
        
        # Patient name - Only show on pages after the first page
        if not is_first_page:
            # Header - Patient name (top right of page)
            canvas_obj.setFont("Helvetica-Bold", 9)
            canvas_obj.setFillColor(colors.black)
            
            # Clean header text to fix rendering issues
            clean_text = self._clean_header_text(header_text)
            
            text_width = canvas_obj.stringWidth(clean_text, "Helvetica-Bold", 9)
            canvas_obj.drawString(
                self.page_width - self.margin - text_width,
                self.page_height - self.margin - 10,
                clean_text
            )
        
        # Add subtle line above footer - monochrome
        canvas_obj.setStrokeColor(colors.HexColor('#cccccc'))
        canvas_obj.setLineWidth(0.5)
        canvas_obj.line(
            self.margin,
            self.margin + 5,
            self.page_width - self.margin,
            self.margin + 5
        )
        
        # Footer - Disclaimer and page number - monochrome
        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.setFillColor(colors.black)
        
        # Disclaimer text (left side)
        disclaimer_text = "Summarization only. No decisions or recommendations."
        
        canvas_obj.drawString(
            self.margin,
            self.margin - 12,
            disclaimer_text
        )
        
        # Page number (right side) - monochrome
        page_text = f"Page {page_num}"
        canvas_obj.setFillColor(colors.black)
        text_width = canvas_obj.stringWidth(page_text, "Helvetica", 7)
        canvas_obj.drawString(
            self.page_width - self.margin - text_width,
            self.margin - 12,
            page_text
        )
    
    def _create_section_separator(self) -> List:
        """Create a professional section separator"""
        story = []
        # Add spacing before separator
        story.append(Spacer(1, 0.15 * inch))
        # Add a subtle horizontal line
        separator = HRFlowable(
            width="100%",
            thickness=0.5,
            lineCap='round',
            color=colors.HexColor('#cccccc'),
            spaceBefore=0,
            spaceAfter=0.15 * inch,
            hAlign='CENTER',
            vAlign='BOTTOM',
            dash=None
        )
        story.append(separator)
        return story


# Singleton instance
pdf_generator_service = PDFGeneratorService()

