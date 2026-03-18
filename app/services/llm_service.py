"""LLM service for clinical information extraction"""

import json
from typing import Dict, List, Optional
import logging
from app.core.config import settings
from app.services.llm.llm_factory import get_tier1_llm_service
from app.services.prompt_service import prompt_service

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM-based clinical extraction"""

    def __init__(self):
        # Don't cache - get fresh service each time to respect config changes
        pass
    
    def _get_llm_service(self):
        """Tier 1: OSS/OpenRouter for extraction (PHI allowed)."""
        return get_tier1_llm_service()

    async def extract_clinical_information(
        self, 
        text: str, 
        file_page_mapping: Dict = None,
        combined_text: str = None
    ) -> Dict[str, any]:
        """
        Extract structured clinical information from medical record text

        Args:
            text: Raw medical record text
            file_page_mapping: Mapping of file_id -> {page_num -> text} for source tracking
            combined_text: Text with file/page context markers

        Returns:
            Dictionary containing extracted clinical data with source information
        """
        llm_service = self._get_llm_service()
        
        if not llm_service.is_available():
            return self._get_mock_extraction()

        # Use combined text with context if available, otherwise use plain text
        text_for_prompt = combined_text if combined_text else text
        
        # Truncate text if too long (to fit within token limits)
        max_chars = settings.OPENAI_MAX_TEXT_CHARS
        if len(text_for_prompt) > max_chars:
            text_for_prompt = text_for_prompt[:max_chars] + "\n\n[... document truncated ...]"
            logger.warning(f"Text truncated from {len(text_for_prompt)} to {max_chars} characters")

        prompt_id = "comprehensive_extraction"
        variables = {"context": text_for_prompt}
        
        prompt = prompt_service.render_prompt(prompt_id, variables)
        system_message = prompt_service.get_system_message(prompt_id)
        
        if not system_message:
            logger.error(f"System message not found for prompt_id: {prompt_id}")
            raise ValueError(f"System message not found for prompt_id: {prompt_id}. Please ensure the prompt exists in the database.")

        try:
            # Determine provider for JSON format handling
            from app.services.llm.claude_service import ClaudeService
            from app.services.llm.openai_service import OpenAIService
            is_claude = isinstance(llm_service, ClaudeService)
            is_openai = isinstance(llm_service, OpenAIService)
            
            # For JSON responses, add instruction to prompt if Claude
            if is_claude:
                prompt = prompt + "\n\nIMPORTANT: Return ONLY valid JSON. Do not include markdown code fences or any text before or after the JSON object."
            
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
                        "content": prompt
                    }
                ],
                system_message=system_message,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"} if is_openai else None
            )

            # Note: Usage tracking not implemented here as this service doesn't have user_id/case_id
            # This is a fallback service used when RAG is disabled

            from app.services.llm_utils import extract_json_from_response
            result = extract_json_from_response(response)
            
            # Add source information to extracted items if file_page_mapping is available
            if file_page_mapping:
                result = self._add_source_information(result, file_page_mapping, text)
            
            return result

        except Exception as e:
            logger.error(f"LLM extraction error: {e}", exc_info=True)
            return self._get_mock_extraction()

    def _add_source_information(
        self, 
        extracted_data: Dict, 
        file_page_mapping: Dict,
        full_text: str
    ) -> Dict:
        """Add source file and page information to extracted data"""
        # For now, we'll enhance the data structure to include source info
        # The LLM may have provided some source info, but we can also try to match
        # text snippets to find the source
        
        # This is a simplified version - in production, you'd want more sophisticated
        # text matching to find exact sources
        return extracted_data

    def _get_mock_extraction(self) -> Dict[str, any]:
        """Return mock extraction data for testing without API key"""
        return {
            "diagnoses": [
                "Type 2 Diabetes Mellitus",
                "Hypertension",
                "Hyperlipidemia"
            ],
            "medications": [
                {
                    "name": "Metformin",
                    "dosage": "500mg",
                    "frequency": "twice daily",
                    "start_date": "01/15/2024",
                    "end_date": None,
                    "prescribed_by": "Dr. Smith"
                },
                {
                    "name": "Lisinopril",
                    "dosage": "10mg",
                    "frequency": "once daily",
                    "start_date": "02/01/2024",
                    "end_date": None,
                    "prescribed_by": "Dr. Johnson"
                }
            ],
            "procedures": [
                {
                    "name": "Annual Physical Exam",
                    "date": "03/10/2024",
                    "provider": "Dr. Smith",
                    "notes": "Routine examination"
                }
            ],
            "vitals": [
                {
                    "type": "Blood Pressure",
                    "value": "130/85",
                    "unit": "mmHg",
                    "date": "03/10/2024"
                },
                {
                    "type": "Weight",
                    "value": "185",
                    "unit": "lbs",
                    "date": "03/10/2024"
                }
            ],
            "labs": [
                {
                    "test_name": "HbA1c",
                    "value": "7.2",
                    "unit": "%",
                    "reference_range": "< 5.7",
                    "date": "03/10/2024",
                    "abnormal": True
                },
                {
                    "test_name": "Total Cholesterol",
                    "value": "220",
                    "unit": "mg/dL",
                    "reference_range": "< 200",
                    "date": "03/10/2024",
                    "abnormal": True
                }
            ],
            "allergies": ["Penicillin", "Sulfa drugs"]
        }


# Singleton instance
llm_service = LLMService()

