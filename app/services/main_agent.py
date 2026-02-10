"""Main agent orchestrator for context-aware follow-up questions"""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.config import settings
from app.services.llm.llm_factory import get_llm_service_instance
from app.models.document_chunk import SectionType
from app.models.dashboard import FacetType
from app.services.rag_retriever import rag_retriever, RAGContext
from app.services.embedding_service import embedding_service
from app.repositories.extraction_repository import extraction_repository
from app.repositories.dashboard_snapshot_repository import DashboardSnapshotRepository
from app.repositories.facet_repository import FacetRepository
from app.services.prompt_service import prompt_service

logger = logging.getLogger(__name__)


@dataclass
class ConversationMessage:
    """A message in the conversation history"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sources: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FollowUpResponse:
    """Response from a follow-up question"""
    answer: str
    sources: List[Dict[str, Any]]
    chunks_used: List[str]
    confidence: float
    suggested_actions: List[str] = field(default_factory=list)


class MainAgent:
    """
    Context-aware main agent orchestrator for follow-up questions.
    
    Maintains conversation history and dashboard state awareness
    to answer questions about the case intelligently.
    """

    def __init__(self):
        # Conversation history is now stored in database
        # Keep in-memory as fallback cache only
        self._conversations_cache: Dict[str, List[ConversationMessage]] = {}
        from app.core.constants import MAX_HISTORY_MESSAGES
        self._max_history = MAX_HISTORY_MESSAGES
    
    def _get_llm_service(self, db: Optional[Session] = None, user_id: Optional[str] = None):
        """Get LLM service instance (fresh each time to respect config changes)"""
        if db and user_id:
            from app.services.llm.llm_factory import get_llm_service_for_user
            return get_llm_service_for_user(db, user_id)
        return get_llm_service_instance()

    async def answer_follow_up_question(
        self,
        db: Session,
        case_id: str,
        question: str,
        user_id: str,
        include_dashboard_context: bool = True
    ) -> FollowUpResponse:
        """
        Answer a follow-up question about a case using RAG and dashboard context.
        
        This method is case-scoped and grounded - it answers ONLY from uploaded case documents.
        It MUST NOT use external knowledge. If information is absent, it responds "Not documented."
        
        Args:
            db: Database session
            case_id: Case ID (ensures case-scoped responses)
            question: User's question
            user_id: User ID for scoping
            include_dashboard_context: Whether to include dashboard state in context
            
        Returns:
            FollowUpResponse with answer and sources
        """
        # Get conversation history from database
        history = self._get_conversation_history(db, case_id, user_id)
        
        # Get dashboard context if requested
        dashboard_context = ""
        if include_dashboard_context:
            dashboard_context = self._get_dashboard_context(db, case_id)
        
        # Retrieve relevant chunks using RAG
        rag_context = self._retrieve_relevant_context(db, case_id, question, user_id)
        
        # Render the prompt
        history_text = ""
        if history:
            history_parts = []
            for msg in history[-5:]:
                role = "User" if msg.role == "user" else "Assistant"
                history_parts.append(f"{role}: {msg.content}")
            history_text = "\n".join(history_parts)

        variables = {
            "question": question,
            "history_text": history_text or "No previous conversation",
            "dashboard_context": dashboard_context,
            "formatted_context": rag_context.formatted_context if rag_context else ""
        }

        if rag_context and rag_context.formatted_context:
            prompt_id = "rag_chat_with_context"
        else:
            prompt_id = "rag_chat_without_context"

        prompt = prompt_service.render_prompt(prompt_id, variables)
        
        # Get answer from LLM
        answer, confidence = await self._get_llm_response(prompt, prompt_id=prompt_id, db=db, user_id=user_id, case_id=case_id)
        
        # Extract suggested actions
        suggested_actions = self._extract_suggested_actions(answer, question)
        
        # Build sources list
        sources = self._build_sources_from_context(rag_context)
        
        # Store in conversation history
        self._add_to_history(db, case_id, user_id, "user", question)
        self._add_to_history(db, case_id, user_id, "assistant", answer, sources)
        
        return FollowUpResponse(
            answer=answer,
            sources=sources,
            chunks_used=[c.chunk_id for c in rag_context.chunks] if rag_context else [],
            confidence=confidence,
            suggested_actions=suggested_actions
        )

    def rerun_agent(
        self,
        db: Session,
        case_id: str,
        facet_type: FacetType,
        query_refinement: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Rerun a specific agent with optional query refinement
        
        Args:
            db: Database session
            case_id: Case ID
            facet_type: Which facet/agent to rerun
            query_refinement: Optional refinement for the agent
            
        Returns:
            Result from the rerun operation
        """
        # Import here to avoid circular imports
        from app.services.orchestrator_service import build_orchestrator_service
        
        orchestrator = build_orchestrator_service()
        
        # Rerun the specific facet
        snapshot = orchestrator.build_dashboard(
            db=db,
            case_id=case_id,
            facet=facet_type,
            force_reprocess=False
        )
        
        return {
            "success": True,
            "facet_type": facet_type.value,
            "snapshot_id": snapshot.id,
            "message": f"Successfully reran {facet_type.value} agent"
        }

    def get_conversation_history(self, db: Session, case_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Get conversation history for a case from database"""
        history = self._get_conversation_history(db, case_id, user_id)
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "sources": msg.sources
            }
            for msg in history
        ]

    def clear_conversation_history(self, db: Session, case_id: str, user_id: str) -> None:
        """Clear conversation history for a case from database"""
        from app.repositories.conversation_repository import conversation_repository
        conversation_repository.clear_conversation(db, case_id, user_id)
        # Also clear cache
        cache_key = f"{case_id}:{user_id}"
        if cache_key in self._conversations_cache:
            del self._conversations_cache[cache_key]

    def _get_conversation_history(self, db: Session, case_id: str, user_id: str) -> List[ConversationMessage]:
        """Get conversation history for a case from database"""
        from app.repositories.conversation_repository import conversation_repository
        from app.core.constants import MAX_HISTORY_MESSAGES
        
        # Try to get from database
        try:
            db_messages = conversation_repository.get_conversation_history(
                db=db,
                case_id=case_id,
                user_id=user_id,
                limit=MAX_HISTORY_MESSAGES
            )
            
            # Convert database messages to ConversationMessage dataclass
            history = []
            for db_msg in db_messages:
                history.append(ConversationMessage(
                    role=db_msg.role,
                    content=db_msg.content,
                    timestamp=db_msg.created_at,
                    sources=db_msg.sources or []
                ))
            
            # Update cache
            cache_key = f"{case_id}:{user_id}"
            self._conversations_cache[cache_key] = history
            
            return history
        except Exception as e:
            logger.warning(f"Failed to load conversation history from database, using cache: {e}")
            # Fallback to cache
            cache_key = f"{case_id}:{user_id}"
            return self._conversations_cache.get(cache_key, [])

    def _add_to_history(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        role: str,
        content: str,
        sources: List[Dict[str, Any]] = None
    ) -> None:
        """Add a message to conversation history in database"""
        from app.repositories.conversation_repository import conversation_repository
        
        try:
            # Save to database
            conversation_repository.add_message(
                db=db,
                case_id=case_id,
                user_id=user_id,
                role=role,
                content=content,
                sources=sources
            )
            
            # Also update cache for quick access
            cache_key = f"{case_id}:{user_id}"
            if cache_key not in self._conversations_cache:
                self._conversations_cache[cache_key] = []
            
            self._conversations_cache[cache_key].append(ConversationMessage(
                role=role,
                content=content,
                timestamp=datetime.utcnow(),
                sources=sources or []
            ))
            
            # Keep only last max_history messages in cache
            if len(self._conversations_cache[cache_key]) > self._max_history:
                self._conversations_cache[cache_key] = self._conversations_cache[cache_key][-self._max_history:]
        except Exception as e:
            logger.warning(f"Failed to save conversation to database, using cache only: {e}")
            # Fallback to cache only
            cache_key = f"{case_id}:{user_id}"
            if cache_key not in self._conversations_cache:
                self._conversations_cache[cache_key] = []
            self._conversations_cache[cache_key].append(ConversationMessage(
                role=role,
                content=content,
                timestamp=datetime.utcnow(),
                sources=sources or []
            ))
            if len(self._conversations_cache[cache_key]) > self._max_history:
                self._conversations_cache[cache_key] = self._conversations_cache[cache_key][-self._max_history:]

    def _get_dashboard_context(self, db: Session, case_id: str) -> str:
        """Get current dashboard state as context"""
        # Get extraction data
        extraction = extraction_repository.get_by_case_id(db, case_id)
        if not extraction:
            return "No clinical extraction available for this case."
        
        context_parts = []
        
        # Add extracted data summary
        extracted = extraction.extracted_data or {}
        
        # Diagnoses
        diagnoses = extracted.get('diagnoses', [])
        if diagnoses:
            dx_list = []
            for dx in diagnoses:
                if isinstance(dx, str):
                    dx_list.append(dx)
                elif isinstance(dx, dict):
                    dx_list.append(dx.get('name', ''))
            context_parts.append(f"DIAGNOSES: {', '.join(dx_list)}")
        
        # Medications count
        meds = extracted.get('medications', [])
        context_parts.append(f"MEDICATIONS: {len(meds)} documented")
        
        # Labs summary
        labs = extracted.get('labs', [])
        abnormal = len([l for l in labs if l.get('abnormal')])
        context_parts.append(f"LABS: {len(labs)} results ({abnormal} abnormal)")
        
        # Procedures
        procs = extracted.get('procedures', [])
        context_parts.append(f"PROCEDURES: {len(procs)} documented")
        
        # Allergies - handle both string and dict formats
        allergies_raw = extracted.get('allergies', [])
        allergy_names = []
        for a in allergies_raw:
            if isinstance(a, str):
                # Old format - string
                allergy_names.append(a)
            elif isinstance(a, dict):
                # New format - dictionary with 'allergen' field
                allergen = a.get('allergen', '')
                if allergen:
                    allergy_names.append(allergen)
        context_parts.append(f"ALLERGIES: {', '.join(allergy_names) if allergy_names else 'Not explicitly documented'}")
        
        # Timeline summary
        timeline = extraction.timeline or []
        context_parts.append(f"TIMELINE: {len(timeline)} events")
        
        # Contradictions
        contradictions = extraction.contradictions or []
        if contradictions:
            context_parts.append(f"CONTRADICTIONS: {len(contradictions)} detected")
        
        return "\n".join(context_parts)

    def _retrieve_relevant_context(
        self,
        db: Session,
        case_id: str,
        question: str,
        user_id: str
    ) -> Optional[RAGContext]:
        """
        Retrieve relevant chunks for the question from case documents only.
        
        This method ensures the chat is grounded in uploaded case documents by
        retrieving chunks scoped to the specific case and user.
        """
        try:
            # Get relevant chunks
            chunks = rag_retriever.retrieve_for_query(
                db=db,
                query=question,
                case_id=case_id,
                user_id=user_id,
                top_k=8
            )
            
            if not chunks:
                return None
            
            # Build context
            return rag_retriever.build_context(chunks, max_tokens=4000)
            
        except Exception as e:
            logger.warning(f"Failed to retrieve RAG context: {e}")
            return None

    async def _get_llm_response(
        self,
        prompt: str,
        prompt_id: Optional[str] = None,
        db: Optional[Session] = None,
        user_id: Optional[str] = None,
        case_id: Optional[str] = None
    ) -> tuple[str, float]:
        """Get response from LLM with usage tracking"""
        llm_service = self._get_llm_service(db, user_id)
        
        if not llm_service.is_available():
            return "I'm unable to process your question at this time. Please ensure the LLM API key is configured.", 0.0
        
        # Get system message from prompt service
        system_message = None
        if prompt_id:
            system_message = prompt_service.get_system_message(prompt_id)
            
        if not system_message:
            logger.error(f"System message not found for prompt_id: {prompt_id}")
            raise ValueError(f"System message not found for prompt_id: {prompt_id}. Please ensure the prompt exists in the database.")
        
        try:
            # Determine provider
            from app.services.llm.claude_service import ClaudeService
            from app.services.llm.openai_service import OpenAIService
            is_claude = isinstance(llm_service, ClaudeService)
            is_openai = isinstance(llm_service, OpenAIService)
            
            # Use provider-specific settings
            if is_claude:
                max_tokens = settings.CLAUDE_MAX_TOKENS
                temperature = settings.CLAUDE_TEMPERATURE
            else:
                max_tokens = settings.OPENAI_MAX_TOKENS
                temperature = settings.OPENAI_TEMPERATURE
            
            answer, usage = await llm_service.chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                system_message=system_message,
                temperature=temperature,
                max_tokens=max_tokens
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
                        operation_type="rag",
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                        case_id=case_id,
                        extra_metadata={
                            "operation": "rag_chat",
                            "prompt_id": prompt_id
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to track usage: {e}", exc_info=True)
            
            # Estimate confidence based on response characteristics
            confidence = self._estimate_confidence(answer)
            
            return answer, confidence
            
        except Exception as e:
            logger.error(f"LLM response error: {e}")
            err_str = str(e).lower()
            # Re-raise transient provider errors so the API can return 503
            if "529" in err_str or "overloaded" in err_str or "503" in err_str or "429" in err_str or "rate" in err_str:
                raise
            return f"I encountered an error processing your question: {str(e)}", 0.0

    def _estimate_confidence(self, answer: str) -> float:
        """Estimate confidence in the answer based on response characteristics"""
        confidence = 0.8  # Base confidence
        
        # Lower confidence if answer contains uncertainty markers
        uncertainty_markers = [
            "i'm not sure", "unclear", "not available", "cannot determine",
            "insufficient information", "may be", "might be", "possibly",
            "i don't have", "no information"
        ]
        
        answer_lower = answer.lower()
        for marker in uncertainty_markers:
            if marker in answer_lower:
                confidence -= 0.1
        
        # Higher confidence if answer references specific sources
        source_markers = ["page", "section", "document", "record shows", "according to"]
        for marker in source_markers:
            if marker in answer_lower:
                confidence += 0.05
        
        return max(0.1, min(1.0, confidence))

    def _extract_suggested_actions(self, answer: str, question: str) -> List[str]:
        """Extract suggested follow-up actions from the answer"""
        suggestions = []
        
        question_lower = question.lower()
        answer_lower = answer.lower()
        
        # Suggest viewing source if answer references specific pages
        if "page" in answer_lower:
            suggestions.append("View source document")
        
        # Suggest timeline review for temporal questions
        temporal_keywords = ["when", "date", "timeline", "history", "progression"]
        if any(kw in question_lower for kw in temporal_keywords):
            suggestions.append("Review clinical timeline")
        
        # Suggest medication review for drug questions
        med_keywords = ["medication", "drug", "prescription", "dose"]
        if any(kw in question_lower for kw in med_keywords):
            suggestions.append("Review medication list")
        
        # Suggest lab review for test questions
        lab_keywords = ["lab", "test", "result", "value"]
        if any(kw in question_lower for kw in lab_keywords):
            suggestions.append("Review lab results")
        
        return suggestions[:3]  # Max 3 suggestions

    def _build_sources_from_context(self, rag_context: Optional[RAGContext]) -> List[Dict[str, Any]]:
        """Build sources list from RAG context"""
        if not rag_context:
            return []
        
        sources = []
        for chunk in rag_context.chunks:
            sources.append({
                "chunk_id": chunk.chunk_id,
                "vector_id": chunk.vector_id,
                "file_id": chunk.file_id,
                "page_number": chunk.page_number,
                "section_type": chunk.section_type.value,
                "score": chunk.score,
                "text_preview": chunk.chunk_text[:200] + "..." if len(chunk.chunk_text) > 200 else chunk.chunk_text
            })
        
        return sources


# Singleton instance
main_agent = MainAgent()

