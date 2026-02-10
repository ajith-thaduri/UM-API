"""Missing Information & Referential Gaps Service."""
import json
import logging
from typing import Dict, List, Optional
import uuid
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.llm.llm_factory import get_llm_service_instance
from app.services.prompt_service import prompt_service

logger = logging.getLogger(__name__)


class MissingInfoService:
    """
    Service for identifying referential gaps and potential missing information.
    
    This agent looks for clinical references in documnentation that lack corresponding 
    evidence (e.g., an MRI mentioned in a note without the actual MRI report).
    """

    def __init__(self):
        # Don't cache - get fresh service each time to respect config changes
        pass
    
    def _get_llm_service(self, db: Optional[Session] = None, user_id: Optional[str] = None):
        """Get LLM service instance (fresh each time to respect config changes)"""
        if db and user_id:
            from app.services.llm.llm_factory import get_llm_service_for_user
            return get_llm_service_for_user(db, user_id)
        return get_llm_service_instance()

    async def detect(
        self,
        clinical_data: Dict,
        timeline: List[Dict] = None,
        db: Optional[Session] = None,
        user_id: Optional[str] = None,
        case_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Detect missing information and gaps using LLM-assisted analysis.
        """
        llm_service = self._get_llm_service(db, user_id)
        
        if not llm_service.is_available():
            return self._heuristic_fallback(clinical_data)

        # Simplify data for the prompt
        meds = [m.get("name") for m in clinical_data.get("medications", [])]
        diagnoses = [d.get("name") if isinstance(d, dict) else d for d in clinical_data.get("diagnoses", [])]
        imaging = [i.get("study_type") for i in clinical_data.get("imaging", [])]
        
        variables = {
            "diagnoses": diagnoses,
            "medications": meds,
            "imaging": imaging
        }
        
        prompt_id = "gap_detection"
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
                    {
                        "role": "user",
                        "content": prompt_with_rules
                    }
                ],
                system_message=system_message,
                temperature=0.1,
                max_tokens=2000,
                response_format={"type": "json_object"} if is_openai else None
            )

            # Track usage if user_id is available
            if user_id and db:
                try:
                    from app.services.usage_tracking_service import usage_tracking_service
                    if is_claude:
                        provider_name = "claude"
                        model_name = getattr(llm_service, 'model', settings.CLAUDE_MODEL)
                    elif is_openai:
                        provider_name = "openai"
                        model_name = getattr(llm_service, 'model', settings.OPENAI_MODEL)
                    else:
                        provider_name = settings.LLM_PROVIDER.lower()
                        model_name = settings.LLM_MODEL
                    
                    usage_tracking_service.track_llm_usage(
                        db=db,
                        user_id=user_id,
                        provider=provider_name,
                        model=model_name,
                        operation_type="red_flags",
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                        case_id=case_id,
                        extra_metadata={
                            "operation": "red_flags_detection",
                            "prompt_id": prompt_id
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to track usage: {e}", exc_info=True)

            from app.services.llm_utils import extract_json_from_response
            try:
                result = extract_json_from_response(response)
            except (ValueError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to parse JSON response from LLM: {e}. Response: {response[:200] if response else 'Empty'}")
                return self._heuristic_fallback(clinical_data)
            
            gaps = []
            for item in result.get("gaps", []):
                gaps.append({
                    "id": str(uuid.uuid4()),
                    "type": "missing_info",
                    "label": item.get("title", "Potential Missing Information"),
                    "description": item.get("reason", "Referenced documentation not identified in current packet."),
                    "details": item,
                    "severity": "neutral", # Standardized to neutral as per MVP
                    "source_file": item.get("source_file"),
                    "source_page": item.get("source_page"),
                })
            return gaps

        except Exception as e:
            logger.error(f"Gap detection error: {e}", exc_info=True)
            return self._heuristic_fallback(clinical_data)

    def _heuristic_fallback(self, clinical_data: Dict) -> List[Dict]:
        """Fallback to simple heuristics if LLM is unavailable."""
        gaps = []
        for lab in clinical_data.get("labs", []) or []:
            if lab.get("abnormal"):
                gaps.append({
                    "id": str(uuid.uuid4()),
                    "type": "clinical_observation",
                    "label": f"Abnormal lab: {lab.get('test_name')}",
                    "description": "Value outside of standard reference range. May require clinical review.",
                    "details": lab,
                    "severity": "neutral"
                })
        return gaps


# Singleton instance
red_flags_service = MissingInfoService()

