"""RAG Orchestrator Service - Page-Indexed + Entity-Grounded"""

import logging
from typing import Dict, List, Any
from sqlalchemy.orm import Session

from app.services.query_classifier import query_classifier, QueryIntent
from app.services.page_rag_retriever import page_rag_retriever, RAGContext
from app.services.llm_service import llm_service
from app.models.entity import Entity
from app.models.normalized_page import NormalizedPage

logger = logging.getLogger(__name__)


class RAGOrchestrator:
    """
    Orchestrates the RAG pipeline using intent-based routing.
    
    Routes queries to the optimal retrieval strategy:
    1. Entity-First (Deterministic SQL) for fact/entity lookups
    2. Page-First (Semantic Search) for broad queries/synthesis
    3. Hybrid for complex queries
    """
    
    async def answer_query(
        self,
        db: Session,
        query: str,
        case_id: str,
        user_id: str,
        chat_history: List[Dict] = None
    ) -> Dict:
        """
        Main entry point for answering a query.
        """
        # 1. Classify Intent
        analysis = query_classifier.classify(query)
        logger.info(f"Query Intent: {analysis.intent} (Confidence: {analysis.confidence})")
        
        context = None
        strategy_used = "general"
        
        # 2. Execute Retrieval Strategy
        if analysis.intent == QueryIntent.ENTITY_LOOKUP:
            # Try Entity-First retrieval
            context = await self._entity_first_retrieval(db, query, case_id, user_id)
            strategy_used = "entity_first"
            
        elif analysis.intent == QueryIntent.FACT_LOOKUP:
            # Hybrid: Try entity lookup first, then page search
            context = await self._entity_first_retrieval(db, query, case_id, user_id)
            if not context or not context.formatted_context:
                context = page_rag_retriever.retrieve(db, query, case_id, user_id)
                strategy_used = "hybrid_page"
            else:
                strategy_used = "hybrid_entity"
                
        else:
            # Default to Page-First retrieval
            context = page_rag_retriever.retrieve(
                db, query, case_id, user_id, top_k_pages=8
            )
            strategy_used = "page_first" # Default / Synthesis
            
        if not context:
            return {
                "answer": "I could not find relevant information to answer your question.",
                "sources": [],
                "strategy": strategy_used
            }

        # 3. Generate Answer
        # We need to construct the prompt with the retrieved context
        # This part usually lives in `llm_service` or `chat_service`.
        # Assuming we can call llm_service here or return context to caller.
        
        # For now, let's return the context so the caller can format the prompt
        # Or even better, call LLM here if `llm_service` supports raw context injection.
        
        # Let's assume we return the context + metadata, and let the caller (API endpoint)
        # handle the final generation or call LLM.
        # But `answer_query` implies returning an answer.
        
        # We'll use a placeholder for now as I need to check `llm_service` signature.
        answer = await self._generate_answer(query, context, chat_history)
        
        return {
            "answer": answer,
            "sources": context.source_references,
            "strategy": strategy_used,
            "context_used": context.formatted_context
        }

    async def _entity_first_retrieval(
        self,
        db: Session,
        query: str,
        case_id: str,
        user_id: str
    ) -> RAGContext:
        """
        Directly query the `entities` table based on keywords/regex.
        """
        # Improved logic: use `analysis.entities` if we extracted them
        # For now, simple keyword match
        query_lower = query.lower()
        
        # Determine entity type filter
        type_filter = []
        if "medication" in query_lower or "meds" in query_lower:
            type_filter.append("medication")
        if "lab" in query_lower:
            type_filter.append("lab")
        if "diagnosis" in query_lower or "condition" in query_lower:
            type_filter.append("diagnosis")
            
        if not type_filter:
            # If explicit lookup but ambiguous type, return None to fallback to semantic search
            return None
            
        # SQL Query
        entities = db.query(Entity).filter(
            Entity.case_id == case_id,
            Entity.user_id == user_id,
            Entity.entity_type.in_(type_filter)
        ).all()
        
        if not entities:
            return None
            
        # Format context
        context_parts = []
        sources = []
        
        for e in entities:
            date_str = e.entity_date.strftime('%Y-%m-%d') if e.entity_date else "Unknown Date"
            context_parts.append(f"- {e.entity_type.title()}: {e.value} ({date_str})")
            # Create loose source ref
            sources.append({
                "entity_id": e.entity_id,
                "type": e.entity_type,
                "value": e.value
            })
            
        return RAGContext(
            chunks=[],
            total_tokens=len("".join(context_parts)) // 4,
            formatted_context="\n".join(context_parts),
            source_references=sources
        )

    async def _generate_answer(
        self,
        query: str,
        context: RAGContext,
        chat_history: List[Dict] = None
    ) -> str:
        """
        Generate answer using LLM service.
        """
        from app.services.llm.llm_factory import get_llm_service_instance
        from app.core.config import settings
        
        # Construct system prompt
        system_prompt = (
            "You are an expert clinical assistant. Answer the user's question based strictly on the provided context.\n"
            "If the context does not contain the answer, state that you do not have enough information.\n"
            "Cite sources where possible (Page X)."
        )
        
        user_prompt = f"""
Context:
{context.formatted_context}

Question: {query}

Answer:
"""
        
        try:
             llm = get_llm_service_instance()
             
             # Fallback if LLM service not available
             if not llm.is_available():
                 # For testing/dev if no key
                 return "LLM service unavailable. Context found: " + context.formatted_context[:200] + "..."

             # Determine parameters based on provider (simplified)
             # Assuming standard interface supports these kwargs or ignores them
             is_openai = "openai" in str(type(llm)).lower()
             
             response, usage = await llm.chat_completion(
                 messages=[
                     {"role": "system", "content": system_prompt},
                     {"role": "user", "content": user_prompt}
                 ],
                 temperature=0.0,
                 max_tokens=1000,
                 # Only OpenAI supports json_object, but we want text here
             )
             
             # Extract content (OpenAI/Claude adapters return different structures usually, 
             # but LLMService expects a standardized response object or dict?)
             # LLMService usage regarding response content:
             # from app.services.llm_utils import extract_json_from_response
             # But here we want text.
             
             # Inspecting llm_service.py line 101: extract_json_from_response(response)
             # This suggests 'response' is an object we can extract from.
             
             # Let's try standard attribute access or dict
             if hasattr(response, 'choices'):
                 return response.choices[0].message.content
             elif hasattr(response, 'content'):
                 return response.content
             elif isinstance(response, dict):
                 return response.get('content', str(response))
             else:
                 return str(response)

        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return "I encountered an error generating the answer."


rag_orchestrator = RAGOrchestrator()
