
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.api.endpoints.auth import get_current_user
from app.services.presidio_deidentification_service import presidio_deidentification_service
from app.models.privacy_vault import PrivacyVault
from app.utils.safe_logger import get_safe_logger

router = APIRouter()
safe_logger = get_safe_logger(__name__)

class AnalyzeRequest(BaseModel):
    text: str
    
class AnalyzeResponse(BaseModel):
    entities: List[Dict[str, Any]]
    redacted_text: str
    original_text_length: int

@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_text(
    request: AnalyzeRequest,
):
    """
    Test endpoint to analyze text with Presidio service.
    Returns detected entities and redacted version without saving to DB.
    """
    text = request.text
    if not text:
        return AnalyzeResponse(entities=[], redacted_text="", original_text_length=0)

    try:
        # Use the service's internal analyzer if available
        if not presidio_deidentification_service.analyzer:
             raise HTTPException(status_code=503, detail="Presidio service not available")

        # Analyze
        results = presidio_deidentification_service.analyzer.analyze(text=text, language='en')
        
        # Format entities for response
        entities = []
        for res in results:
            entities.append({
                "type": res.entity_type,
                "text": text[res.start:res.end],
                "start": res.start,
                "end": res.end,
                "score": res.score
            })
            
        # Redact (Simple generic redaction for visualization)
        # Using anonymizer engine from service
        anonymized_result = presidio_deidentification_service.anonymizer.anonymize(
            text=text,
            analyzer_results=results
        )
        
        return AnalyzeResponse(
            entities=entities,
            redacted_text=anonymized_result.text,
            original_text_length=len(text)
        )
        
    except Exception as e:
        safe_logger.error(f"Error in analyze_text endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vault/{case_id}")
def get_case_redactions(
    case_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Retrieve the stored redaction map (Privacy Vault) for a specific case.
    Shows exactly what was redacted and stored during processing.
    """
    # Find vault entry for this case
    # Note: A case might have multiple vault entries if re-processed (we take latest)
    headers = {"Cache-Control": "no-cache"}
    
    vault_entry = db.query(PrivacyVault).filter(
        PrivacyVault.case_id == case_id
    ).order_by(PrivacyVault.created_at.desc()).first()
    
    if not vault_entry:
        raise HTTPException(status_code=404, detail="No redaction history found for this case")
        
    # Return formatted map
    # token_map is Dict[token, original_value]
    # We want to show: Original Value -> Token -> Type (extracted from token)
    
    mapping = []
    if vault_entry.token_map:
        for token, original in vault_entry.token_map.items():
            # Extract type from token format [[TYPE::uuid]]
            entity_type = "UNKNOWN"
            if "::" in token:
                parts = token.replace("[[", "").replace("]]", "").split("::")
                if len(parts) >= 1:
                    entity_type = parts[0]
            
            mapping.append({
                "original": original,
                "token": token,
                "type": entity_type
            })
            
    return {
        "case_id": case_id,
        "vault_id": vault_entry.id,
        "date_shift_days": vault_entry.date_shift_days,
        "created_at": vault_entry.created_at,
        "mappings": mapping,
        "total_redactions": len(mapping)
    }


@router.get("/engine-info")
def get_engine_info():
    """
    Returns the current NER engine info and available models.
    """
    return presidio_deidentification_service.get_engine_info()


class SwitchEngineRequest(BaseModel):
    engine: str  # "spacy" or "transformers"

@router.post("/switch-engine")
def switch_engine(
    request: SwitchEngineRequest,
    current_user = Depends(get_current_user),
):
    """
    Switch the NER engine at runtime.
    Requires authentication.
    """
    result = presidio_deidentification_service.switch_ner_engine(request.engine)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to switch engine"))
    return result
