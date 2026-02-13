"""Query Intent Classification Service"""

import logging
from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    """
    RAG Query Intent Types
    """
    FACT_LOOKUP = "fact_lookup"       # Specific data point (e.g. "What was the BP on 5/12?")
    ENTITY_LOOKUP = "entity_lookup"   # Information about specific entity (e.g. "List all medications")
    TIMELINE = "timeline"             # Chronological sequence (e.g. "What happened after the fall?")
    SYNTHESIS = "synthesis"           # Summarization/Reasoning (e.g. "Is the treatment appropriate?")
    GENERAL = "general"               # Fallback


class QueryAnalysis(BaseModel):
    intent: QueryIntent
    entities: List[str] = []
    temporal_constraints: Optional[str] = None
    confidence: float = 0.0


class QueryClassifier:
    """
    Classifies user queries to determine the optimal RAG strategy.
    """
    
    def classify(self, query: str) -> QueryAnalysis:
        """
        Classify the query intent.
        
        Optimization:
        1. Try regex/heuristic first (fastest)
        2. Fallback to LLM classification (slower but more accurate)
        """
        # 1. Heuristic check
        heuristic = self._heuristic_classify(query)
        if heuristic and heuristic.confidence > 0.8:
            return heuristic
            
        # 2. LLM Classification (Placeholder - real implementation would call LLM)
        # For MVP, we stick to heuristics or simple keyword matching to avoid latency
        return heuristic or QueryAnalysis(intent=QueryIntent.GENERAL, confidence=0.5)

    def _heuristic_classify(self, query: str) -> Optional[QueryAnalysis]:
        """Simple heuristic classification"""
        query_lower = query.lower()
        
        # Timeline
        if any(w in query_lower for w in ["timeline", "chronology", "sequence", "history of", "when did"]):
            return QueryAnalysis(intent=QueryIntent.TIMELINE, confidence=0.9)
            
        # Entity Lookup
        if any(w in query_lower for w in ["list all", "what medications", "show labs", "diagnoses", "meds"]):
            return QueryAnalysis(intent=QueryIntent.ENTITY_LOOKUP, confidence=0.85)
            
        # Fact Lookup (Specific dates usually imply fact lookup)
        import re
        if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', query) or " on " in query_lower:
             return QueryAnalysis(intent=QueryIntent.FACT_LOOKUP, confidence=0.8)
             
        # Synthesis
        if any(w in query_lower for w in ["summarize", "explain", "why", "opinion", "conclusion"]):
            return QueryAnalysis(intent=QueryIntent.SYNTHESIS, confidence=0.8)
            
        return QueryAnalysis(intent=QueryIntent.GENERAL, confidence=0.5)


query_classifier = QueryClassifier()
