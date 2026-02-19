"""PDF Analyzer Service for extracting patient information during upload"""

import re
import json
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
from app.services.llm.llm_factory import get_tier1_llm_service
from app.services.llm_utils import extract_json_from_response

from app.core.config import settings
from app.services.pdf_service import pdf_service
from app.services.prompt_service import prompt_service

logger = logging.getLogger(__name__)


@dataclass
class PatientInfo:
    """Extracted patient information"""
    name: Optional[str] = None
    dob: Optional[str] = None  # MM/DD/YYYY format
    mrn: Optional[str] = None
    gender: Optional[str] = None
    encounter_date: Optional[str] = None
    provider: Optional[str] = None
    facility: Optional[str] = None
    # Case Overview Fields
    request_type: Optional[str] = None
    diagnosis: Optional[str] = None
    request_date: Optional[str] = None
    urgency: Optional[str] = None  # Routine, Expedited, or Urgent
    # Medical Relevance Fields
    is_medical: bool = True
    detected_category: str = "medical_record"
    relevance_reason: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def is_complete(self) -> bool:
        """Check if essential fields are filled"""
        return bool(self.name)
    
    def get_missing_fields(self) -> List[str]:
        """Get list of missing fields"""
        missing = []
        if not self.name:
            missing.append("patient_name")
        if not self.dob:
            missing.append("dob")
        if not self.mrn:
            missing.append("mrn")
        return missing


@dataclass
class FileAnalysis:
    """Analysis result for a single file"""
    file_name: str
    file_path: str
    page_count: int
    file_size: int  # bytes
    extraction_preview: str  # First ~500 chars
    detected_type: str  # medical_record, lab_report, imaging, discharge, etc.
    confidence: float  # 0-1


@dataclass
class AnalysisResult:
    """Complete analysis result"""
    patient_info: PatientInfo
    files: List[FileAnalysis]
    total_pages: int
    extraction_confidence: float  # Overall confidence in extracted data
    raw_text_preview: str  # Combined preview for LLM if needed
    

class PDFAnalyzerService:
    """Service for quick PDF analysis during upload to extract patient info"""
    
    # Regex patterns for common medical record fields
    # Patterns are ordered by specificity (most specific first)
    PATTERNS = {
        "name": [
            # Highly specific: "Patient Name:" followed by 2-3 capitalized words
            r"Patient\s*Name[:\s]+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){1,2})",
            # PATIENT: followed by name
            r"PATIENT[:\s]+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){1,2})",
            # "Name:" but exclude common medical terms AND doctor titles
            r"Name[:\s]+(?!Medical|Record|Health|Hospital|Clinic|Center|Department|Service|Provider|Physician|Doctor|Facility|Date|Of|Birth|Appeared|Seems)([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){1,2})",
            # "PATIENT:" followed by colon
            r"PATIENT\s*:\s*([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){1,2})",
            # "PATIENT:" with last, first format
            r"PATIENT[:\s]+([A-Z]+,[ \t]+[A-Z]+)",
            # Title prefixes (Mr., Mrs., Ms.) - EXCLUDED Dr. to avoid doctor/patient confusion
            r"(?:Mr\.|Mrs\.|Ms\.)[ \t]+([A-Z][a-z]+[ \t]+[A-Z][a-z]+)",
        ],
        "dob": [
            r"(?:DOB|Date\s*of\s*Birth|Birth\s*Date)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"(?:DOB|Date\s*of\s*Birth)[:\s]*(\d{1,2}/\d{1,2}/\d{4})",
            r"Born[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        ],
        "mrn": [
            r"(?:MRN|Medical\s*Record\s*(?:Number|No\.?)|Patient\s*ID|Acct)[:\s#]*(\d{5,12})",
            r"(?:MRN|MR#|Patient\s*#)[:\s]*([A-Z0-9]{5,12})",
        ],
        "gender": [
            r"(?:Sex|Gender)[:\s]*(Male|Female|M|F)",
            r"\b(Male|Female)\b",
        ],
        "encounter_date": [
            r"(?:Date\s*of\s*(?:Service|Visit|Encounter)|Visit\s*Date|Service\s*Date)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"(?:Admission|Admit)\s*Date[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        ],
        "provider": [
            r"(?:Attending|Provider|Physician|Doctor)[:\s]*(?:Dr\.?\s*)?([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)",
            r"(?:Seen\s*by|Treated\s*by)[:\s]*(?:Dr\.?\s*)?([A-Z][a-z]+\s+[A-Z][a-z]+)",
            # Standalone Dr. with credentials or punctuation
            r"Dr\.\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)(?:\s*[,;]|\s+MD|\s+DO|\s+reviewed|\s+examined|\s+noted)",
            # Primary Care, Consultant, Specialist
            r"(?:Primary\s*Care|Consultant|Specialist|Referring\s*Physician)[:\s]*(?:Dr\.?\s*)?([A-Z][a-z]+\s+[A-Z][a-z]+)",
            # Physician with credentials
            r"Physician[:\s]*(?:Dr\.?\s*)?([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)(?:\s*[,;]|\s+MD|\s+DO)",
        ],
        "facility": [
            r"(?:Hospital|Facility|Clinic|Medical\s*Center)[:\s]*([A-Z][A-Za-z\s]+(?:Hospital|Medical|Center|Clinic))",
        ],
    }
    
    # Document type indicators
    DOC_TYPE_INDICATORS = {
        "discharge": ["discharge summary", "discharge instructions", "discharged"],
        "lab_report": ["laboratory", "lab results", "blood test", "urinalysis", "cbc", "cmp"],
        "imaging": ["radiology", "x-ray", "ct scan", "mri", "ultrasound", "imaging"],
        "progress_note": ["progress note", "clinic note", "follow-up", "office visit"],
        "emergency": ["emergency department", "ed visit", "er visit", "emergency room"],
        "operative": ["operative report", "surgery", "surgical", "procedure note"],
        "consultation": ["consultation", "consult note", "referral"],
        "social_work": ["social work", "social worker", "social services", "case worker", "social worker note", "social work assessment", "social work note"],
        "case_management": ["case management", "case manager", "care coordination", "care manager", "case management note", "care coordination note"],
        "discharge_planning": ["discharge planning", "discharge planner", "care planning", "discharge planning note", "care plan"],
        "physical_therapy": ["physical therapy", "pt note", "pt assessment", "physiotherapy", "rehabilitation", "rehab", "physical therapist", "pt evaluation", "pt progress note"],
        "occupational_therapy": ["occupational therapy", "ot note", "ot assessment", "occupational therapist", "ot evaluation", "ot progress note"],
        "speech_therapy": ["speech therapy", "speech language", "speech language pathology", "slt", "slp note", "slp assessment", "speech therapist", "slp evaluation", "slp progress note"],
    }

    # Non-medical document indicators (Blocklist)
    NON_MEDICAL_INDICATORS = {
        "resume": ["resume", "curriculum vitae", "experience", "education", "skills", "summary of qualifications", "work history", "objective", "employment", "professional summary"],
        "invoice": ["invoice to", "total due", "tax", "payment terms", "bank account", "billing", "amount due", "receipt"],
        "legal": ["contract", "agreement", "lawsuit", "terms and conditions", "plaintiff", "defendant", "litigation"],
    }
    
    def __init__(self):
        # Don't cache - get fresh service each time to respect config changes
        pass
    
    def _get_llm_service(self):
        """Tier 1: OSS/OpenRouter for upload analysis (PHI allowed)."""
        return get_tier1_llm_service()
    
    async def analyze_for_upload(self, file_paths: List[str]) -> AnalysisResult:
        """
        Analyze uploaded PDFs to extract patient information (async)
        
        Args:
            file_paths: List of paths to uploaded PDF files
            
        Returns:
            AnalysisResult with patient info and file metadata
        """
        files_analysis = []
        combined_text = ""
        total_pages = 0
        
        # Per-file analysis for keyword-based detection
        for file_path in file_paths:
            try:
                analysis = self._analyze_single_file(file_path)
                files_analysis.append(analysis)
                combined_text += f"\\n\\n--- {analysis.file_name} ---\\n{analysis.extraction_preview}"
                total_pages += analysis.page_count
            except Exception as e:
                logger.error(f"Error analyzing file {file_path}: {e}", exc_info=True)
                # Create a minimal analysis for failed files
                files_analysis.append(FileAnalysis(
                    file_name=Path(file_path).name,
                    file_path=file_path,
                    page_count=0,
                    file_size=0,
                    extraction_preview="[Error extracting text]",
                    detected_type="unknown",
                    confidence=0.0
                ))
        
        # Extract patient info using regex first (fast, but limited)
        patient_info = self._extract_patient_info_regex(combined_text)
        regex_confidence = self._calculate_confidence(patient_info)
        
        # Determine if we should use LLM (low confidence or missing key fields)
        # For the new Agent flow, we prefer LLM almost always to get rich case data (Diagnosis, Request Type)
        # which Regex is bad at. So we'll trigger LLM unless disabled or no text.
        llm_service = self._get_llm_service()
        if combined_text and llm_service.is_available():
            # IMPORTANT: If guardrail is enabled, analyze each file individually for LLM validation
            # This ensures we can identify which specific file is non-medical
            non_medical_file_texts = []  # Track which files are non-medical for exclusion
            if settings.ENABLE_MEDICAL_GUARDRAIL:
                # Analyze each file individually with LLM for per-file relevance check (PARALLEL)
                tasks = []
                task_indices = []
                
                for i, file_analysis in enumerate(files_analysis):
                    if file_analysis.detected_type.startswith("non_medical_"):
                        # Already flagged by keywords, skip LLM check for this file
                        non_medical_file_texts.append(file_analysis.file_name)
                        continue
                    
                    file_text = file_analysis.extraction_preview[:8000]  # Limit for LLM
                    if file_text and len(file_text) > 50:  # Only if we have meaningful text
                        tasks.append(self._extract_patient_info_llm(file_text))
                        task_indices.append(i)
                
                if tasks:
                    logger.info(f"Running guardrail checks for {len(tasks)} files in parallel...")
                    # Run all LLM calls concurrently
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for i, result in zip(task_indices, results):
                        file_analysis = files_analysis[i]
                        
                        if isinstance(result, Exception):
                            logger.warning(f"LLM guardrail check failed for {file_analysis.file_name}: {result}")
                            continue
                        
                        file_llm_info = result
                        if file_llm_info and not file_llm_info.is_medical:
                            # Update the file analysis to reflect non-medical status
                            try:
                                files_analysis[i] = FileAnalysis(
                                    file_name=file_analysis.file_name,
                                    file_path=file_analysis.file_path,
                                    page_count=file_analysis.page_count,
                                    file_size=file_analysis.file_size,
                                    extraction_preview=file_analysis.extraction_preview,
                                    detected_type=f"non_medical_{file_llm_info.detected_category.lower()}",
                                    confidence=0.95  # High confidence from LLM
                                )
                                non_medical_file_texts.append(file_analysis.file_name)
                            except Exception as e:
                                logger.error(f"Error updating file analysis for {file_analysis.file_name}: {e}")
            
            # Build combined text from ONLY medical files for patient info extraction
            medical_combined_text = ""
            for file_analysis in files_analysis:
                if not file_analysis.detected_type.startswith("non_medical_"):
                    medical_combined_text += f"\\n\\n--- {file_analysis.file_name} ---\\n{file_analysis.extraction_preview}"
            
            # Do combined LLM extraction for patient info (only from valid medical files)
            if medical_combined_text:
                llm_patient_info = await self._extract_patient_info_llm(medical_combined_text)
                if llm_patient_info:
                    # Merge LLM results with regex results (prefer non-None values, LLM wins on case data)
                    patient_info = self._merge_patient_info(patient_info, llm_patient_info)
        
        final_confidence = self._calculate_confidence(patient_info)
        
        return AnalysisResult(
            patient_info=patient_info,
            files=files_analysis,
            total_pages=total_pages,
            extraction_confidence=final_confidence,
            raw_text_preview=combined_text[:2000] if combined_text else ""
        )
    
    def _analyze_single_file(self, file_path: str) -> FileAnalysis:
        """Analyze a single PDF file"""
        path = Path(file_path)
        file_size = path.stat().st_size if path.exists() else 0
        
        # Extract text from first 2 pages for quick analysis
        extraction = pdf_service.extract_text_from_pdf(file_path)
        page_count = extraction.get("page_count", 0)
        
        # Get preview text (first 2 pages or ~1500 chars)
        preview_text = ""
        pages = extraction.get("pages", [])
        for page in pages[:2]:
            preview_text += page.get("text", "") + "\\n"
        preview_text = preview_text[:1500]
        
        # Detect document type
        doc_type, type_confidence = self._detect_document_type(preview_text)
        
        return FileAnalysis(
            file_name=path.name,
            file_path=file_path,
            page_count=page_count,
            file_size=file_size,
            extraction_preview=preview_text,
            detected_type=doc_type,
            confidence=type_confidence
        )
    
    def _detect_document_type(self, text: str) -> Tuple[str, float]:
        """Detect the type of medical document and check for non-medical indicators"""
        text_lower = text.lower()
        
        # Check non-medical blocklist first
        for non_med_type, indicators in self.NON_MEDICAL_INDICATORS.items():
            matches = sum(1 for ind in indicators if ind in text_lower)
            if matches >= 2:
                return f"non_medical_{non_med_type}", 0.95
        
        # Check medical document types
        for doc_type, indicators in self.DOC_TYPE_INDICATORS.items():
            matches = sum(1 for ind in indicators if ind in text_lower)
            if matches >= 2:
                return doc_type, 0.9
            elif matches == 1:
                return doc_type, 0.7
        
        return "medical_record", 0.5  # Default type
    
    def _extract_patient_info_regex(self, text: str) -> PatientInfo:
        """Extract patient info using regex patterns"""
        info = PatientInfo()
        
        for field, patterns in self.PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    value = match.group(1).strip()
                    # Clean and format the value
                    value = self._clean_extracted_value(field, value)
                    
                    # Additional validation for names and providers
                    if field == "name":
                        if value and self._is_valid_name(value):
                            setattr(info, field, value)
                            break
                    elif field == "provider":
                        if value and self._is_valid_provider_name(value):
                            setattr(info, field, value)
                            break
                    elif value:
                        setattr(info, field, value)
                        break
        
        return info
    
    def _is_valid_name(self, name: str) -> bool:
        """Validate that extracted value looks like a real patient name"""
        if not name or len(name) < 3:
            return False
        
        # Clean the name of common prefixes for validation
        clean_name = re.sub(r'^(?:Mr\.|Mrs\.|Ms\.|Dr\.|Mr|Mrs|Ms|Dr)\s+', '', name, flags=re.IGNORECASE)
        
        # Common medical terms that should NOT be considered names
        invalid_terms = [
            "medical", "record", "health", "hospital", "clinic", "center",
            "department", "service", "provider", "physician", "doctor", "facility",
            "patient", "information", "summary", "report", "note",
            "discharge", "admission", "visit", "encounter", "treatment", "care",
            "date", "of", "birth", "dob", "age", "gender", "sex", "mrn",
            "appeared", "seems", "stable", "condition", "arrived", "presented",
            "documented", "reported", "history", "physical", "exam", "assessment"
        ]
        
        name_lower = clean_name.lower()
        # Check if the name contains any invalid medical terms as whole words
        for term in invalid_terms:
            if re.search(r'\b' + term + r'\b', name_lower):
                return False
        
        # Must contain at least 2 words (first and last name)
        words = clean_name.split()
        if len(words) < 2:
            return False
        
        return True
    
    def _is_valid_provider_name(self, name: str) -> bool:
        """Validate that extracted value looks like a real provider/doctor name"""
        if not name or len(name) < 3:
            return False
        
        # Clean the name of common prefixes for validation
        clean_name = re.sub(r'^(?:Dr\.|Dr)\s+', '', name, flags=re.IGNORECASE)
        
        # Common non-person terms that should NOT be considered provider names
        invalid_terms = [
            "medical", "department", "service", "hospital", "clinic",
            "center", "facility", "unit", "ward", "floor", "division",
            "group", "practice", "associates", "network", "system"
        ]
        
        name_lower = clean_name.lower()
        # Check if the name contains any invalid terms as whole words
        for term in invalid_terms:
            if re.search(r'\b' + term + r'\b', name_lower):
                return False
        
        # Must contain at least 2 words (first and last name) OR be a single capitalized word with credentials
        words = clean_name.split()
        if len(words) < 1:
            return False
        
        # Allow single word if it's followed by credentials (handled in regex)
        # But prefer 2+ words for validation
        if len(words) == 1:
            # Single word names are less reliable, but allow if it looks like a name
            if not re.match(r'^[A-Z][a-z]+$', words[0]):
                return False
        
        return True
    
    def _clean_extracted_value(self, field: str, value: str) -> Optional[str]:
        """Clean and format extracted values"""
        if not value:
            return None
        
        value = value.strip()
        
        if field == "name":
            # Handle "LAST, FIRST" format
            if "," in value:
                parts = value.split(",")
                if len(parts) == 2:
                    value = f"{parts[1].strip()} {parts[0].strip()}"
            # Remove "Dr." prefix if present (shouldn't be in patient names)
            value = re.sub(r'^(?:Dr\.|Dr)\s+', '', value, flags=re.IGNORECASE)
            # Title case
            value = value.title()
        elif field == "provider":
            # Clean provider name - remove trailing credentials/punctuation
            value = re.sub(r'\s*[,;]\s*.*$', '', value)  # Remove everything after comma/semicolon
            value = re.sub(r'\s+(MD|DO|M\.D\.|D\.O\.)$', '', value, flags=re.IGNORECASE)  # Remove credentials
            value = value.strip()
            # Title case
            value = value.title()
            
        elif field == "dob":
            # Normalize date format to MM/DD/YYYY
            value = self._normalize_date(value)
            
        elif field == "gender":
            # Normalize gender
            value = value.upper()
            if value in ["M", "MALE"]:
                value = "Male"
            elif value in ["F", "FEMALE"]:
                value = "Female"
                
        elif field == "encounter_date":
            value = self._normalize_date(value)
        
        return value
    
    def _normalize_date(self, date_str: str) -> Optional[str]:
        """Normalize date to MM/DD/YYYY format"""
        if not date_str:
            return None
        
        # Try different date formats
        import re
        
        # Handle MM/DD/YYYY or MM-DD-YYYY
        match = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", date_str)
        if match:
            month, day, year = match.groups()
            # Handle 2-digit year
            if len(year) == 2:
                year = f"20{year}" if int(year) < 50 else f"19{year}"
            return f"{month.zfill(2)}/{day.zfill(2)}/{year}"
        
        return date_str
    
    async def _extract_patient_info_llm(self, text: str) -> Optional[PatientInfo]:
        """Extract patient info using LLM for better accuracy (async)"""
        llm_service = self._get_llm_service()
        if not llm_service.is_available():
            return None
        
        # Truncate text for LLM (increase context slightly for case overview)
        text = text[:8000]
        
        # Use prompt service to render the patient info extraction prompt
        prompt_id = "patient_info_extraction"
        variables = {"text": text}
        prompt = prompt_service.render_prompt(prompt_id, variables)
        system_message = prompt_service.get_system_message(prompt_id)
        
        if not system_message:
            logger.error(f"System message not found for prompt_id: {prompt_id}")
            raise ValueError(f"System message not found for prompt_id: {prompt_id}. Please ensure the prompt exists in the database.")
        
        try:
            # Determine provider for JSON format handling
            from app.services.llm.claude_service import ClaudeService
            from app.services.llm.openai_service import OpenAIService
            from app.services.llm_utils import EXTRACTION_RULES
            is_claude = isinstance(llm_service, ClaudeService)
            is_openai = isinstance(llm_service, OpenAIService)
            
            # Append centralized extraction instructions
            prompt_with_rules = prompt + EXTRACTION_RULES
            
            response, usage = await llm_service.chat_completion(
                messages=[
                    {"role": "user", "content": prompt_with_rules}
                ],
                system_message=system_message,
                temperature=0.1,
                max_tokens=800,
                response_format={"type": "json_object"} if is_openai else None
            )
            
            # Extract JSON from response
            result = extract_json_from_response(response)
            
            return PatientInfo(
                name=result.get("name"),
                dob=result.get("dob"),
                mrn=result.get("mrn"),
                gender=result.get("gender"),
                encounter_date=result.get("encounter_date"),
                provider=result.get("provider"),
                facility=result.get("facility"),
                request_type=result.get("request_type"),
                diagnosis=result.get("diagnosis"),
                request_date=result.get("request_date"),
                urgency=result.get("urgency"),
                is_medical=result.get("is_medical_record", True),
                detected_category=result.get("document_type", "medical_record"),
                relevance_reason=result.get("relevance_reason")
            )
            
        except Exception as e:
            logger.error(f"LLM patient extraction error: {e}", exc_info=True)
            return None
    
    def _merge_patient_info(self, regex_info: PatientInfo, llm_info: PatientInfo) -> PatientInfo:
        """Merge regex and LLM extraction results, preferring non-None values"""
        return PatientInfo(
            name=regex_info.name or llm_info.name,
            dob=regex_info.dob or llm_info.dob,
            mrn=regex_info.mrn or llm_info.mrn,
            gender=regex_info.gender or llm_info.gender,
            encounter_date=regex_info.encounter_date or llm_info.encounter_date,
            provider=regex_info.provider or llm_info.provider,
            facility=regex_info.facility or llm_info.facility,
            # Case fields (LLM only)
            request_type=llm_info.request_type,
            diagnosis=llm_info.diagnosis,
            request_date=llm_info.request_date,
            urgency=llm_info.urgency
        )
    
    def _calculate_confidence(self, info: PatientInfo) -> float:
        """Calculate confidence score based on extracted fields"""
        weights = {
            "name": 0.25,
            "dob": 0.15,
            "mrn": 0.15,
            "gender": 0.05,
            "encounter_date": 0.1,
            "request_type": 0.1,
            "diagnosis": 0.1,
            "request_date": 0.1
        }
        
        score = 0.0
        for field, weight in weights.items():
            if getattr(info, field):
                score += weight
        
        return round(score, 2)
    
    # Deprecated - kept for compatibility but should use analyze_for_upload
    async def extract_case_overview(self, file_paths: List[str]) -> Dict[str, Optional[str]]:
        """Deprecated: Use analyze_for_upload instead"""
        analysis = await self.analyze_for_upload(file_paths)
        return {
            "request_type": analysis.patient_info.request_type,
            "diagnosis": analysis.patient_info.diagnosis,
            "request_date": analysis.patient_info.request_date
        }


# Singleton instance
pdf_analyzer_service = PDFAnalyzerService()
