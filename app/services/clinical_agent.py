"""Clinical agent with RAG-enhanced extraction"""

import json
import logging
import asyncio
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.llm.llm_factory import get_tier1_llm_service, get_tier1_llm_service_for_user
from app.models.document_chunk import SectionType
from app.services.rag_retriever import rag_retriever, RAGContext
from app.services.embedding_service import embedding_service
from app.db.session import SessionLocal
from app.services.prompt_service import prompt_service

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result from clinical extraction with source references"""
    data: Dict[str, Any]
    sources: List[Dict[str, Any]]
    chunks_used: List[str]  # List of chunk IDs used


class ClinicalAgent:
    """
    RAG-enhanced clinical agent for extracting medical information.
    
    Uses targeted retrieval by section type to get relevant chunks,
    then extracts structured data with source linking.
    """

    def __init__(self):
        # Don't cache - get fresh service each time to respect config changes
        pass
    
    def _scan_for_critical_fields(
        self,
        db: Session,
        case_id: str,
        extracted_data: Dict
    ) -> Dict:
        """
        Scan ALL chunks for critical fields that are commonly missed by RAG
        
        Critical fields:
        - Admission date
        - Discharge date  
        - Primary diagnosis
        - Length of stay
        
        This bypasses RAG semantic search and uses pattern matching to ensure
        critical information is not missed due to embedding/query mismatches.
        
        Args:
            db: Database session
            case_id: Case ID
            extracted_data: Current extracted data dict
            
        Returns:
            Updated extracted_data with critical fields filled in if found
        """
        import re
        from app.repositories.chunk_repository import chunk_repository
        
        # Get ALL chunks for case (bypass RAG)
        all_chunks = chunk_repository.get_by_case_id(db, case_id)
        
        # Scan for admission date if missing
        if not extracted_data.get('admission_date'):
            admission_patterns = [
                r'admitted\s+on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'admission\s+date[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'date\s+of\s+admission[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'patient\s+admitted[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            ]
            for chunk in all_chunks:
                for pattern in admission_patterns:
                    match = re.search(pattern, chunk.chunk_text, re.IGNORECASE)
                    if match:
                        extracted_data['admission_date'] = match.group(1)
                        extracted_data['admission_date_source'] = {
                            'file_id': chunk.file_id,
                            'page_number': chunk.page_number,
                            'chunk_id': chunk.id,
                            'from_critical_scan': True
                        }
                        logger.info(f"[CRITICAL_SCAN] Found admission date via full scan: {match.group(1)}")
                        break
                if extracted_data.get('admission_date'):
                    break
        
        # Scan for discharge date if missing
        if not extracted_data.get('discharge_date'):
            discharge_patterns = [
                r'discharged\s+on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'discharge\s+date[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'date\s+of\s+discharge[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'patient\s+discharged[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            ]
            for chunk in all_chunks:
                for pattern in discharge_patterns:
                    match = re.search(pattern, chunk.chunk_text, re.IGNORECASE)
                    if match:
                        extracted_data['discharge_date'] = match.group(1)
                        extracted_data['discharge_date_source'] = {
                            'file_id': chunk.file_id,
                            'page_number': chunk.page_number,
                            'chunk_id': chunk.id,
                            'from_critical_scan': True
                        }
                        logger.info(f"[CRITICAL_SCAN] Found discharge date via full scan: {match.group(1)}")
                        break
                if extracted_data.get('discharge_date'):
                    break
        
        # Scan for primary diagnosis if missing or empty
        if not extracted_data.get('diagnoses') or len(extracted_data.get('diagnoses', [])) == 0:
            primary_diag_patterns = [
                r'primary\s+diagnosis[:\s]+([^\n]+)',
                r'admitting\s+diagnosis[:\s]+([^\n]+)',
                r'principal\s+diagnosis[:\s]+([^\n]+)',
            ]
            for chunk in all_chunks:
                for pattern in primary_diag_patterns:
                    match = re.search(pattern, chunk.chunk_text, re.IGNORECASE)
                    if match:
                        diagnosis_text = match.group(1).strip()
                        if diagnosis_text and len(diagnosis_text) > 3:
                            if 'diagnoses' not in extracted_data:
                                extracted_data['diagnoses'] = []
                            extracted_data['diagnoses'].insert(0, {
                                'name': diagnosis_text,
                                'type': 'primary',
                                'source_file_id': chunk.file_id,
                                'source_page': chunk.page_number,
                                'from_critical_scan': True
                            })
                            logger.info(f"[CRITICAL_SCAN] Found primary diagnosis via full scan: {diagnosis_text[:50]}")
                            break
                if extracted_data.get('diagnoses') and len(extracted_data['diagnoses']) > 0:
                    break
        
        return extracted_data
    
    def _get_llm_service(self, db: Optional[Session] = None, user_id: Optional[str] = None):
        """Tier 1: OSS/OpenRouter for extraction (PHI allowed)."""
        if db and user_id:
            return get_tier1_llm_service_for_user(db, user_id)
        return get_tier1_llm_service()

    async def _extract_generic(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        query: str,
        prompt_id: str,
        source_type: str,
        operation_type: str,
        default_return: Dict[str, Any]
    ) -> ExtractionResult:
        """Generic extraction method to reduce duplication"""
        context = rag_retriever.build_section_context(
            db=db,
            case_id=case_id,
            user_id=user_id,
            section_types=[],  # Ignored
            query=query
        )

        if not context.chunks:
            return ExtractionResult(data=default_return, sources=[], chunks_used=[])

        prompt = prompt_service.render_prompt(prompt_id, {"context": context.formatted_context})
        result = await self._call_llm(
            prompt, 
            prompt_id=prompt_id,
            db=db, 
            user_id=user_id, 
            case_id=case_id, 
            operation_type=operation_type
        )
        
        if not result or not isinstance(result, dict):
            result = default_return

        # Ensure all keys in default_return strictly exist
        final_result = default_return.copy()
        final_result.update(result)
        
        return ExtractionResult(
            data=final_result,
            sources=self._build_sources(context, source_type),
            chunks_used=[c.chunk_id for c in context.chunks]
        )

    async def extract_all(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        fallback_text: Optional[str] = None
    ) -> ExtractionResult:
        """
        Extract all clinical information using parallel RAG-enhanced extraction calls.
        
        Args:
            db: Database session
            case_id: Case ID to extract from
            user_id: User ID for scoping
            fallback_text: Fallback text if no chunks available
            
        Returns:
            ExtractionResult with data and sources
        """
        extraction_start = time.time()
        logger.info(f"[TIMING] Starting parallelized extraction for case {case_id}")
        
        # Initialize result structure
        all_data = {
            "diagnoses": [],
            "medications": [],
            "procedures": [],
            "vitals": [],
            "labs": [],
            "allergies": [],
            "imaging": [],
            "chief_complaint": None,
            "history": [],
            "social_factors": [],
            "therapy_notes": [],
            "functional_status": []
        }
        all_sources = []
        all_chunks = []

        # 1. Prepare RAG contexts (Synchronous but fast)
        # Comprehensive context - using contextual phrases for better semantic matching
        comprehensive_query = """
Patient medications and prescriptions including dosage frequency and administration routes.
Laboratory test results including blood tests, chemistry panels, complete blood count.
Clinical diagnoses, assessment, and impression documented by physicians.
Procedures, surgical interventions, and treatments performed during hospitalization.
Vital signs monitoring including blood pressure, heart rate, temperature, respiratory rate, oxygen saturation.
Known allergies and adverse drug reactions.
Imaging studies and radiology reports including X-ray, CT scan, MRI, ultrasound findings.
Admission information, chief complaint, and hospital course.
"""
        context = rag_retriever.build_section_context(
            db=db,
            case_id=case_id,
            user_id=user_id,
            section_types=[],
            query=comprehensive_query,
            max_tokens=20000,
            ensure_file_diversity=True
        )

        # History context
        history_context = rag_retriever.build_section_context(
            db=db,
            case_id=case_id,
            user_id=user_id,
            section_types=[],
            query="chief complaint history of present illness past medical history past surgical history family history social history",
            max_tokens=6000
        )

        # Social factors context
        social_factors_context = rag_retriever.build_section_context(
            db=db,
            case_id=case_id,
            user_id=user_id,
            section_types=[],
            query="social work case management discharge planning housing caregiver availability cognition mental status placement barriers discharge barriers",
            max_tokens=6000
        )

        # Therapy context
        therapy_context = rag_retriever.build_section_context(
            db=db,
            case_id=case_id,
            user_id=user_id,
            section_types=[],
            query="physical therapy occupational therapy speech therapy functional status assessment mobility ambulation ADL",
            max_tokens=6000
        )

        if not context.chunks and not history_context.chunks and not social_factors_context.chunks and not therapy_context.chunks:
            logger.warning(f"No chunks found for case {case_id}, returning empty results")
            return ExtractionResult(data=all_data, sources=[], chunks_used=[])

        # 2. Prepare Prompts
        tasks = []
        
        # Task 1: Meds & Allergies
        if context.chunks:
            meds_prompt = prompt_service.render_prompt("meds_allergies_extraction", {"context": context.formatted_context})
            tasks.append(self._call_llm(meds_prompt, prompt_id="meds_allergies_extraction", db=db, user_id=user_id, case_id=case_id, operation_type="extraction_meds_allergies"))
        else:
            tasks.append(asyncio.sleep(0, result={}))

        # Task 2: Labs, Imaging, Vitals
        if context.chunks:
            labs_prompt = prompt_service.render_prompt("labs_imaging_vitals_extraction", {"context": context.formatted_context})
            tasks.append(self._call_llm(labs_prompt, prompt_id="labs_imaging_vitals_extraction", db=db, user_id=user_id, case_id=case_id, operation_type="extraction_labs_imaging"))
        else:
            tasks.append(asyncio.sleep(0, result={}))

        # Task 3: Diagnoses & Procedures
        if context.chunks:
            diag_prompt = prompt_service.render_prompt("diagnoses_procedures_extraction", {"context": context.formatted_context})
            tasks.append(self._call_llm(diag_prompt, prompt_id="diagnoses_procedures_extraction", db=db, user_id=user_id, case_id=case_id, operation_type="extraction_diagnoses_procedures"))
        else:
            tasks.append(asyncio.sleep(0, result={}))

        # Task 2: History extraction
        if history_context.chunks:
            history_prompt = prompt_service.render_prompt("history_extraction", {"context": history_context.formatted_context})
            tasks.append(self._call_llm(
                history_prompt,
                prompt_id="history_extraction",
                db=db,
                user_id=user_id,
                case_id=case_id,
                operation_type="extraction_history"
            ))
        else:
            tasks.append(asyncio.sleep(0, result={}))

        # Task 3: Social factors extraction
        if social_factors_context.chunks:
            social_factors_prompt = prompt_service.render_prompt("history_extraction", {"context": social_factors_context.formatted_context})
            tasks.append(self._call_llm(
                social_factors_prompt,
                prompt_id="history_extraction",
                db=db,
                user_id=user_id,
                case_id=case_id,
                operation_type="extraction_social_factors"
            ))
        else:
            tasks.append(asyncio.sleep(0, result={}))

        # Task 4: Therapy extraction
        if therapy_context.chunks:
            therapy_prompt = prompt_service.render_prompt("therapy_notes_extraction", {"context": therapy_context.formatted_context})
            tasks.append(self._call_llm(
                therapy_prompt,
                prompt_id="therapy_notes_extraction",
                db=db,
                user_id=user_id,
                case_id=case_id,
                operation_type="extraction_therapy"
            ))
        else:
            tasks.append(asyncio.sleep(0, result={}))

        # 3. Execute LLM calls in parallel
        llm_start = time.time()
        meds_result, labs_result, diag_result, history_result, social_factors_result, therapy_result = await asyncio.gather(*tasks)
        llm_total_time = time.time() - llm_start
        logger.info(f"[TIMING] Parallel LLM calls (6 total) completed in {llm_total_time:.2f}s for case {case_id}")

        # 4. Process Comprehensive Results
        try:
            # Process Meds & Allergies with validation
            if isinstance(meds_result, dict):
                # Validate medications
                medications = meds_result.get("medications", [])
                all_data["medications"] = self._validate_extraction_against_chunks(
                    medications, context.chunks, item_name_key="name"
                )
                
                # Validate allergies
                allergies = meds_result.get("allergies", [])
                all_data["allergies"] = self._validate_extraction_against_chunks(
                    allergies, context.chunks, item_name_key="allergen"
                )
            
            # Process Labs, Imaging, Vitals with validation
            if isinstance(labs_result, dict):
                # Validate labs
                labs = labs_result.get("labs", [])
                all_data["labs"] = self._validate_extraction_against_chunks(
                    labs, context.chunks, item_name_key="test_name"
                )
                
                # Validate imaging
                imaging = labs_result.get("imaging", [])
                all_data["imaging"] = self._validate_extraction_against_chunks(
                    imaging, context.chunks, item_name_key="study_type"
                )
                
                # Validate vitals
                vitals = labs_result.get("vitals", [])
                all_data["vitals"] = self._validate_extraction_against_chunks(
                    vitals, context.chunks, item_name_key="type"
                )
            
            # Process Diagnoses & Procedures with validation
            if isinstance(diag_result, dict):
                # Validate diagnoses
                diagnoses = diag_result.get("diagnoses", [])
                all_data["diagnoses"] = self._validate_extraction_against_chunks(
                    diagnoses, context.chunks, item_name_key="name"
                )
                
                # Validate procedures
                procedures = diag_result.get("procedures", [])
                all_data["procedures"] = self._validate_extraction_against_chunks(
                    procedures, context.chunks, item_name_key="name"
                )
            
            # Source matching for comprehensive
            source_types = ["medication", "lab", "diagnosis", "procedure", "vital", "allergy", "imaging"]
            for source_type in source_types:
                data_key = {
                    "medication": "medications", "lab": "labs", "diagnosis": "diagnoses",
                    "procedure": "procedures", "vital": "vitals", "allergy": "allergies", "imaging": "imaging"
                }.get(source_type)
                
                items = all_data.get(data_key, [])
                for item in items:
                    search_term = str(item.get("name") or item.get("test_name") or item.get("allergen") or item.get("study_type") or item.get("type", ""))
                    if not search_term or len(search_term) < 2: continue
                        
                    for chunk in context.chunks:
                        if search_term.lower() in chunk.chunk_text.lower():
                            item.update({
                                "source_file_id": chunk.file_id,
                                "source_page": chunk.page_number,
                                "bbox": chunk.bbox if hasattr(chunk, "bbox") else None
                            })
                            all_sources.append({
                                "type": source_type, "chunk_id": chunk.chunk_id, "vector_id": chunk.vector_id,
                                "file_id": chunk.file_id, "page_number": chunk.page_number,
                                "section_type": chunk.section_type.value, "score": chunk.score
                            })
                            break
            all_chunks.extend([c.chunk_id for c in context.chunks])
        except Exception as e:
            logger.error(f"Error processing comprehensive result: {e}")

        # 5. Process History Results
        try:
            if isinstance(history_result, dict):
                all_data["chief_complaint"] = history_result.get("chief_complaint")
                if "history" in history_result:
                    all_data["history"] = history_result.get("history", [])
                else:
                    all_data["history"] = history_result.get("past_medical_history", [])
                
                # Extract social factors from history if present
                if "social_factors" in history_result:
                    all_data["social_factors"] = history_result.get("social_factors", [])

            for ref in history_context.source_references:
                all_sources.append({
                    "type": "history", "chunk_id": ref["chunk_id"], "vector_id": ref["vector_id"],
                    "file_id": ref["file_id"], "page_number": ref["page_number"],
                    "section_type": ref["section_type"], "score": ref["score"]
                })
            all_chunks.extend([c.chunk_id for c in history_context.chunks])
        except Exception as e:
            logger.error(f"Error processing history result: {e}")

        # 6. Process Social Factors Results
        try:
            if isinstance(social_factors_result, dict) and "social_factors" in social_factors_result:
                extracted_factors = social_factors_result.get("social_factors", [])
                existing_factor_descriptions = {f.get("description", "") for f in all_data.get("social_factors", []) if isinstance(f, dict)}
                for factor in extracted_factors:
                    if isinstance(factor, dict) and factor.get("description", "") not in existing_factor_descriptions:
                        all_data["social_factors"].append(factor)
                        existing_factor_descriptions.add(factor.get("description", ""))
            
            for ref in social_factors_context.source_references:
                all_sources.append({
                    "type": "social_factors", "chunk_id": ref["chunk_id"], "vector_id": ref["vector_id"],
                    "file_id": ref["file_id"], "page_number": ref["page_number"],
                    "section_type": ref["section_type"], "score": ref["score"]
                })
            all_chunks.extend([c.chunk_id for c in social_factors_context.chunks])
        except Exception as e:
            logger.error(f"Error processing social factors result: {e}")

        # 7. Process Therapy Results
        try:
            if isinstance(therapy_result, dict):
                all_data["therapy_notes"] = therapy_result.get("therapy_notes", [])
                all_data["functional_status"] = therapy_result.get("functional_status", [])
            
            for ref in therapy_context.source_references:
                all_sources.append({
                    "type": "therapy", "chunk_id": ref["chunk_id"], "vector_id": ref["vector_id"],
                    "file_id": ref["file_id"], "page_number": ref["page_number"],
                    "section_type": ref["section_type"], "score": ref["score"]
                })
            all_chunks.extend([c.chunk_id for c in therapy_context.chunks])
        except Exception as e:
             logger.error(f"Error processing therapy result: {e}")

        extraction_time = time.time() - extraction_start
        logger.info(f"[TIMING] Total parallel extraction completed in {extraction_time:.2f}s for case {case_id}")
        
        # Scan for critical fields that may have been missed by RAG
        try:
            scan_start = time.time()
            all_data = self._scan_for_critical_fields(db, case_id, all_data)
            scan_time = time.time() - scan_start
            logger.info(f"[TIMING] Critical field scan completed in {scan_time:.2f}s for case {case_id}")
        except Exception as e:
            logger.error(f"[CRITICAL_SCAN] Error scanning for critical fields: {e}", exc_info=True)
            # Continue without critical scan - non-fatal
        
        # Log coverage metrics
        total_chunks = len(context.chunks) + len(history_context.chunks) + len(social_factors_context.chunks) + len(therapy_context.chunks)
        unique_chunks = len(set(all_chunks))
        
        # Get total chunks for case
        from app.repositories.chunk_repository import chunk_repository
        total_case_chunks = chunk_repository.count_by_case(db, case_id)
        
        coverage_pct = (unique_chunks / total_case_chunks * 100) if total_case_chunks > 0 else 0
        
        logger.info(f"[COVERAGE] Case {case_id}: Retrieved {unique_chunks}/{total_case_chunks} chunks ({coverage_pct:.1f}% coverage)")
        
        # Count verified vs unverified items
        verified_counts = {}
        for key in ["medications", "labs", "diagnoses", "procedures", "vitals", "allergies", "imaging"]:
            items = all_data.get(key, [])
            verified = sum(1 for item in items if item.get('is_verified', False))
            verified_counts[key] = f"{verified}/{len(items)}"
        
        logger.info(f"[VALIDATION] Verified items: {verified_counts}")
        
        # Log low confidence items
        low_confidence_items = []
        confidence_threshold = 0.5
        for key in ["medications", "labs", "diagnoses", "procedures", "vitals", "allergies", "imaging"]:
            items = all_data.get(key, [])
            for item in items:
                if item.get('confidence_score', 1.0) < confidence_threshold:
                    low_confidence_items.append({
                        'type': key,
                        'item': item.get('name') or item.get('test_name') or item.get('allergen') or str(item),
                        'confidence': item.get('confidence_score', 0.0)
                    })
        
        if low_confidence_items:
            logger.warning(f"[VALIDATION] Case {case_id} has {len(low_confidence_items)} low-confidence items")
            for lc_item in low_confidence_items[:5]:  # Log first 5
                logger.warning(f"  - {lc_item['type']}: {lc_item['item']} (confidence: {lc_item['confidence']:.2f})")
        
        return ExtractionResult(
            data=all_data,
            sources=all_sources,
            chunks_used=list(set(all_chunks))
        )

    def _validate_extraction_against_chunks(
        self,
        extracted_items: List[Dict],
        chunks: List,
        item_name_key: str = "name"
    ) -> List[Dict]:
        """
        Validate extracted items against source chunks
        
        Adds validation metadata to each item:
        - is_verified: bool (True if item text found in chunks)
        - confidence_score: float (0-1, based on chunk score and term prominence)
        - matching_chunks: List[str] (chunk_ids where item was found)
        
        Args:
            extracted_items: List of extracted items to validate
            chunks: List of RetrievedChunk objects used for extraction
            item_name_key: Key to use for searching (e.g., "name", "test_name", "allergen")
            
        Returns:
            List of validated items with added metadata
        """
        validated_items = []
        
        for item in extracted_items:
            # Get searchable text from item
            search_term = str(item.get(item_name_key) or item.get("test_name") or item.get("allergen") or item.get("study_type") or "")
            
            if not search_term or len(search_term) < 2:
                # Can't validate without search term
                item['is_verified'] = False
                item['confidence_score'] = 0.0
                item['matching_chunks'] = []
                validated_items.append(item)
                continue
            
            # Search for term in chunks
            matching_chunks = []
            best_match_score = 0.0
            
            for chunk in chunks:
                chunk_text_lower = chunk.chunk_text.lower()
                search_term_lower = search_term.lower()
                
                # Simple substring match
                if search_term_lower in chunk_text_lower:
                    matching_chunks.append(chunk.chunk_id)
                    
                    # Calculate match quality
                    # Factor 1: Chunk relevance score (from RAG)
                    # Factor 2: Search term prominence in chunk
                    term_count = chunk_text_lower.count(search_term_lower)
                    prominence = min(1.0, term_count / 10.0)  # Cap at 10 mentions
                    
                    match_score = (chunk.score * 0.7) + (prominence * 0.3)
                    best_match_score = max(best_match_score, match_score)
            
            # Set validation metadata
            item['is_verified'] = len(matching_chunks) > 0
            item['confidence_score'] = best_match_score if matching_chunks else 0.0
            item['matching_chunks'] = matching_chunks[:3]  # Top 3 chunks
            
            validated_items.append(item)
        
        return validated_items
    
    async def extract_medications(self, db: Session, case_id: str, user_id: str) -> ExtractionResult:
        """Extract medications using all available chunks (async)"""
        return await self._extract_generic(
            db, case_id, user_id, 
            query="medications prescriptions drugs dosage frequency date started",
            prompt_id="medications_extraction",
            source_type="medication",
            operation_type="extraction_medications",
            default_return={"medications": []}
        )

    async def extract_labs(self, db: Session, case_id: str, user_id: str) -> ExtractionResult:
        """Extract lab results using all available chunks (async)"""
        return await self._extract_generic(
            db, case_id, user_id, 
            query="laboratory results blood tests CBC BMP CMP values date collected",
            prompt_id="labs_extraction",
            source_type="lab",
            operation_type="extraction_labs",
            default_return={"labs": []}
        )

    async def extract_diagnoses(self, db: Session, case_id: str, user_id: str) -> ExtractionResult:
        """Extract diagnoses using all available chunks (async)"""
        return await self._extract_generic(
            db, case_id, user_id, 
            query="diagnosis impression assessment problem list ICD date diagnosed admission",
            prompt_id="diagnoses_extraction",
            source_type="diagnosis",
            operation_type="extraction_diagnoses",
            default_return={"diagnoses": []}
        )

    async def extract_procedures(self, db: Session, case_id: str, user_id: str) -> ExtractionResult:
        """Extract procedures using all available chunks (async)"""
        return await self._extract_generic(
            db, case_id, user_id, 
            query="procedures surgery operation intervention treatment date performed",
            prompt_id="procedures_extraction",
            source_type="procedure",
            operation_type="extraction_procedures",
            default_return={"procedures": []}
        )

    async def extract_vitals(self, db: Session, case_id: str, user_id: str) -> ExtractionResult:
        """Extract vital signs using all available chunks (async)"""
        return await self._extract_generic(
            db, case_id, user_id, 
            query="vital signs blood pressure heart rate temperature respiratory date time",
            prompt_id="vitals_extraction",
            source_type="vital",
            operation_type="extraction_vitals",
            default_return={"vitals": []}
        )

    async def extract_allergies(self, db: Session, case_id: str, user_id: str) -> ExtractionResult:
        """Extract allergies using all available chunks (async)"""
        return await self._extract_generic(
            db, case_id, user_id, 
            query="allergies adverse reactions drug allergy NKDA",
            prompt_id="allergies_extraction",
            source_type="allergy",
            operation_type="extraction_allergies",
            default_return={"allergies": []}
        )

    async def extract_imaging(self, db: Session, case_id: str, user_id: str) -> ExtractionResult:
        """Extract imaging results using all available chunks (async)"""
        return await self._extract_generic(
            db, case_id, user_id, 
            query="imaging radiology CT MRI X-ray ultrasound findings date performed",
            prompt_id="imaging_extraction",
            source_type="imaging",
            operation_type="extraction_imaging",
            default_return={"imaging": []}
        )

    async def extract_history(self, db: Session, case_id: str, user_id: str) -> ExtractionResult:
        """Extract chief complaint and history using all available chunks (async)"""
        return await self._extract_generic(
            db, case_id, user_id, 
            query="chief complaint history of present illness past medical history",
            prompt_id="history_extraction",
            source_type="history",
            operation_type="extraction_history",
            default_return={"chief_complaint": None, "history": []}
        )

    def _build_sources(
        self,
        context: RAGContext,
        source_type: str
    ) -> List[Dict[str, Any]]:
        """Build source reference list from context"""
        sources = []
        for ref in context.source_references:
            sources.append({
                "type": source_type,
                "chunk_id": ref["chunk_id"],
                "vector_id": ref["vector_id"],
                "file_id": ref["file_id"],
                "page_number": ref["page_number"],
                "section_type": ref["section_type"],
                "score": ref["score"]
            })
        return sources

    async def _call_llm(
        self,
        prompt: str,
        prompt_id: Optional[str] = None,
        db: Optional[Session] = None,
        user_id: Optional[str] = None,
        case_id: Optional[str] = None,
        operation_type: str = "extraction"
    ) -> Dict[str, Any]:
        """Call LLM with prompt and return parsed JSON, tracking usage (async)"""
        llm_service = self._get_llm_service(db, user_id)
        
        if not llm_service.is_available():
            logger.warning("No LLM service configured, returning empty result")
            return {}

        # Get system message from prompt service if prompt_id is provided, otherwise use default
        system_message = None
        if prompt_id:
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
            
            # Use centralized extraction instructions for BOTH providers
            # This ensures consistent behavior and prevents duplicate extraction
            prompt_with_json = prompt + EXTRACTION_RULES
            
            # Use provider-specific settings
            if is_claude:
                max_tokens = settings.CLAUDE_MAX_TOKENS
                temperature = settings.CLAUDE_TEMPERATURE
            else:
                max_tokens = settings.OPENAI_MAX_TOKENS
                temperature = settings.OPENAI_TEMPERATURE
            
            response, usage = await llm_service.chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": prompt_with_json
                    }
                ],
                system_message=system_message,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"} if not is_claude else None,
                seed=settings.LLM_SEED if not is_claude else None  # OpenAI only - for reproducibility
            )

            # Track usage if user_id is available
            if user_id and db:
                try:
                    from app.services.usage_tracking_service import usage_tracking_service
                    # Get provider and model from service
                    if is_claude:
                        provider_name = "claude"
                        model_name = getattr(llm_service, 'model', settings.CLAUDE_MODEL)
                    elif is_openai:
                        provider_name = "openai"
                        model_name = getattr(llm_service, 'model', settings.OPENAI_MODEL)
                    else:
                        # Fallback
                        provider_name = settings.LLM_PROVIDER.lower()
                        model_name = settings.LLM_MODEL
                    
                    usage_tracking_service.track_llm_usage(
                        db=db,
                        user_id=user_id,
                        provider=provider_name,
                        model=model_name,
                        operation_type=operation_type,
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                        case_id=case_id,
                        extra_metadata={
                            "operation": operation_type,
                            "prompt_id": prompt_id
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to track usage: {e}", exc_info=True)

            from app.services.llm_utils import extract_json_from_response
            result = extract_json_from_response(response)
            
            # Log extraction result for debugging
            if isinstance(result, dict):
                logger.debug(f"[EXTRACTION] LLM returned dict with keys: {list(result.keys())}")
                # Log counts for each data type
                counts = {
                    "medications": len(result.get("medications", [])),
                    "labs": len(result.get("labs", [])),
                    "diagnoses": len(result.get("diagnoses", [])),
                    "procedures": len(result.get("procedures", [])),
                    "vitals": len(result.get("vitals", [])),
                    "allergies": len(result.get("allergies", [])),
                    "imaging": len(result.get("imaging", []))
                }
                logger.debug(f"[EXTRACTION] LLM extraction counts: {counts}")
                
                # If all are empty, log a warning with sample of response
                if all(v == 0 for v in counts.values()):
                    logger.debug(f"[EXTRACTION] LLM returned empty arrays for all data types or this is a specialized extraction")
            else:
                logger.warning(f"[EXTRACTION] LLM returned non-dict result: {type(result)}")
            
            return result

        except Exception as e:
            logger.error(f"LLM extraction error: {e}", exc_info=True)
            logger.error(f"[EXTRACTION] Response that caused error (first 500 chars): {response[:500] if 'response' in locals() else 'N/A'}")
            return {}


# Singleton instance
clinical_agent = ClinicalAgent()
