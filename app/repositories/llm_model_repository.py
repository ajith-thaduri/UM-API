
from sqlalchemy.orm import Session
from app.models.llm_model import LLMModel
from typing import List, Optional
import uuid

class LLMModelRepository:
    """Repository for LLM Models"""
    
    def get_all_active(self, db: Session, provider: Optional[str] = None) -> List[LLMModel]:
        query = db.query(LLMModel).filter(LLMModel.is_active == True)
        if provider:
            query = query.filter(LLMModel.provider == provider)
        return query.order_by(LLMModel.is_custom, LLMModel.display_name).all()

    def get_by_model_id(self, db: Session, model_id: str) -> Optional[LLMModel]:
        return db.query(LLMModel).filter(LLMModel.model_id == model_id).first()
        
    def create(self, db: Session, model_id: str, display_name: str, provider: str = "openrouter", is_custom: bool = True) -> LLMModel:
        model = LLMModel(
            model_id=model_id,
            display_name=display_name,
            provider=provider,
            is_custom=is_custom,
            is_active=True
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return model

    def seed_defaults(self, db: Session):
        """Seed default Tier 1 models if table is empty"""
        if db.query(LLMModel).count() > 0:
            return

        defaults = [
            {
                "model_id": "meta-llama/llama-3.1-70b-instruct",
                "display_name": "Llama 3.1 70B (Recommended)",
                "description": "Balanced performance and cost for clinical reasoning.",
                "context_window": 128000
            },
            {
                "model_id": "meta-llama/llama-3.1-405b-instruct",
                "display_name": "Llama 3.1 405B (High Intelligence)",
                "description": "Maximum reasoning capability for complex cases.",
                "context_window": 128000
            },
            {
                "model_id": "mistralai/mistral-large-2411",
                "display_name": "Mistral Large 2 (French/Euro Optimized)",
                "description": "Excellent reasoning, alternative to Llama.",
                "context_window": 32000
            },
             {
                "model_id": "google/gemini-flash-1.5",
                "display_name": "Gemini Flash 1.5",
                "description": "High speed, large context window.",
                "context_window": 1000000
            }
        ]

        for m in defaults:
            model = LLMModel(
                provider="openrouter",
                model_id=m["model_id"],
                display_name=m["display_name"],
                description=m["description"],
                context_window=m["context_window"],
                is_custom=False
            )
            db.add(model)
        
        db.commit()
