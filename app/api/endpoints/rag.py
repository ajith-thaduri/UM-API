"""RAG API endpoints for follow-up questions and chunk retrieval"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.dependencies import get_db
from app.models.dashboard import FacetType
from app.services.main_agent import main_agent
from app.services.source_link_service import build_source_link_service
from app.services.rag_retriever import rag_retriever
from app.services.rag_orchestrator import rag_orchestrator  # Added for Phase 4
from app.repositories.chunk_repository import chunk_repository
from app.api.endpoints.auth import get_current_user
from app.models.user import User

router = APIRouter(tags=["rag"])


# Request/Response Models
class QueryRequest(BaseModel):
    """Request for a follow-up question"""
    question: str = Field(..., min_length=1, max_length=2000)
    include_dashboard_context: bool = True


class SourceReference(BaseModel):
    """Source reference in a response"""
    chunk_id: str
    vector_id: str
    file_id: str
    page_number: int
    section_type: str
    score: float
    text_preview: Optional[str] = None


class QueryResponse(BaseModel):
    """Response from a follow-up question"""
    answer: str
    sources: List[SourceReference]
    chunks_used: List[str]
    confidence: float
    suggested_actions: List[str]


class ConversationMessage(BaseModel):
    """A message in conversation history"""
    role: str
    content: str
    timestamp: str
    sources: List[dict] = []


class ConversationHistoryResponse(BaseModel):
    """Conversation history response"""
    case_id: str
    messages: List[ConversationMessage]


class RerunAgentRequest(BaseModel):
    """Request to rerun a specific agent"""
    query_refinement: Optional[str] = None


class RerunAgentResponse(BaseModel):
    """Response from rerunning an agent"""
    success: bool
    facet_type: str
    snapshot_id: str
    message: str


class ChunkResponse(BaseModel):
    """Chunk source response"""
    chunk_id: str
    vector_id: str
    case_id: str
    file_id: str
    page_number: int
    section_type: str
    text: str
    char_start: int
    char_end: int
    token_count: int


class ChunkSearchRequest(BaseModel):
    """Request to search chunks"""
    query: str = Field(..., min_length=1, max_length=500)
    section_filter: Optional[List[str]] = None
    top_k: int = Field(default=10, ge=1, le=50)


class ChunkSearchResult(BaseModel):
    """Result from chunk search"""
    chunk_id: str
    vector_id: str
    file_id: str
    page_number: int
    section_type: str
    score: float
    text: str


class ChunkSearchResponse(BaseModel):
    """Response from chunk search"""
    results: List[ChunkSearchResult]
    total: int


# Endpoints
@router.post("/dashboard/{case_id}/query", response_model=QueryResponse)
async def query_dashboard(
    case_id: str,
    request: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ask a follow-up question about a case
    
    Uses RAG to retrieve relevant chunks and answers based on
    the dashboard context and document content.
    """
    # Verify case belongs to user
    from app.repositories.case_repository import CaseRepository
    from app.db.dependencies import get_case_repository
    case_repo = get_case_repository()
    case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    try:
        response = await main_agent.answer_follow_up_question(
            db=db,
            case_id=case_id,
            question=request.question,
            include_dashboard_context=request.include_dashboard_context,
            user_id=current_user.id
        )
        
        return QueryResponse(
            answer=response.answer,
            sources=[
                SourceReference(
                    chunk_id=s.get("chunk_id", ""),
                    vector_id=s.get("vector_id", ""),
                    file_id=s.get("file_id", ""),
                    page_number=s.get("page_number", 0),
                    section_type=s.get("section_type", ""),
                    score=s.get("score", 0.0),
                    text_preview=s.get("text_preview")
                )
                for s in response.sources
            ],
            chunks_used=response.chunks_used,
            confidence=response.confidence,
            suggested_actions=response.suggested_actions
        )
        
    except Exception as e:
        err_str = str(e).lower()
        # Transient provider errors: overloaded (529), unavailable (503), rate limit (429)
        if "529" in err_str or "overloaded" in err_str or "503" in err_str or "429" in err_str or "rate" in err_str:
            raise HTTPException(
                status_code=503,
                detail="The AI service is temporarily overloaded. Please try again in a moment.",
            )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboard/{case_id}/rag_query", response_model=QueryResponse)
async def query_rag_v2(
    case_id: str,
    request: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    [Phase 4] Intelligent RAG Query Endpoint
    
    Uses RAG Orchestrator to route between Key-Value/Entity lookup and
    Semantic Page Search based on query intent.
    """
    # Verify case
    from app.db.dependencies import get_case_repository
    case_repo = get_case_repository()
    case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
    try:
        # Use new Orchestrator
        result = await rag_orchestrator.answer_query(
            db=db,
            query=request.question,
            case_id=case_id,
            user_id=current_user.id,
            # We could fetch chat history here if needed
            chat_history=[]
        )
        
        # Map result to QueryResponse
        sources = []
        chunks_used = []
        
        for s in result.get("sources", []):
            # Adapt source format
            # New sources might be entity refs or page refs
            if "chunk_id" in s:
                chunks_used.append(s["chunk_id"])
                
            sources.append(SourceReference(
                chunk_id=s.get("chunk_id", ""),
                vector_id=s.get("vector_id", ""),
                file_id=s.get("file_id", ""),
                page_number=s.get("page_number", 0),
                section_type=s.get("type", "page"), # Map type to section_type
                score=1.0, 
                text_preview=s.get("snippet") or s.get("value")
            ))
            
        return QueryResponse(
            answer=result["answer"],
            sources=sources,
            chunks_used=chunks_used,
            confidence=0.9, # Placeholder
            suggested_actions=[f"Strategy: {result.get('strategy')}"]
        )
        
    except Exception as e:
        # Fallback to old agent if new one fails?
        # For now, just raise
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Page-Indexed RAG failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"RAG Error: {str(e)}")


@router.get("/dashboard/{case_id}/conversation", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get conversation history for a case"""
    # Verify case belongs to user
    from app.repositories.case_repository import CaseRepository
    from app.db.dependencies import get_case_repository
    case_repo = get_case_repository()
    case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    history = main_agent.get_conversation_history(db, case_id, current_user.id)
    
    return ConversationHistoryResponse(
        case_id=case_id,
        messages=[
            ConversationMessage(
                role=msg["role"],
                content=msg["content"],
                timestamp=msg["timestamp"],
                sources=msg.get("sources", [])
            )
            for msg in history
        ]
    )


@router.delete("/dashboard/{case_id}/conversation")
async def clear_conversation_history(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clear conversation history for a case"""
    # Verify case belongs to user
    from app.repositories.case_repository import CaseRepository
    from app.db.dependencies import get_case_repository
    case_repo = get_case_repository()
    case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    main_agent.clear_conversation_history(db, case_id, current_user.id)
    return {"success": True, "message": "Conversation history cleared"}


@router.post("/dashboard/{case_id}/agent/{facet_type}/rerun", response_model=RerunAgentResponse)
async def rerun_agent(
    case_id: str,
    facet_type: FacetType,
    request: RerunAgentRequest = None,
    db: Session = Depends(get_db)
):
    """
    Rerun a specific agent for a case
    
    Optionally provide query refinement to focus the agent.
    """
    try:
        result = main_agent.rerun_agent(
            db=db,
            case_id=case_id,
            facet_type=facet_type,
            query_refinement=request.query_refinement if request else None
        )
        
        return RerunAgentResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/{case_id}/source/chunk/{chunk_id}", response_model=ChunkResponse)
async def get_chunk_source(
    case_id: str,
    chunk_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get source information for a specific chunk"""
    source_service = build_source_link_service()
    chunk_data = source_service.get_chunk_source(db, chunk_id)
    
    if not chunk_data:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    # Verify chunk belongs to the case
    if chunk_data.get("case_id") != case_id:
        raise HTTPException(status_code=404, detail="Chunk not found for this case")
    
    # Track evidence click for analytics
    try:
        from app.services.analytics_service import AnalyticsService
        analytics_service = AnalyticsService()
        analytics_service.track_evidence_click(
            db=db,
            user_id=current_user.id,
            case_id=case_id,
            entity_type="chunk",
            entity_id=chunk_id,
            source_type="chunk",
            chunk_id=chunk_id
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to track evidence click for chunk source: {e}", exc_info=True)
        # Don't raise - tracking failures shouldn't break source viewing
    
    return ChunkResponse(**chunk_data)


@router.get("/dashboard/{case_id}/source/vector/{vector_id}", response_model=ChunkResponse)
async def get_chunk_by_vector_id(
    case_id: str,
    vector_id: str,
    db: Session = Depends(get_db)
):
    """Get source information for a chunk by vector ID"""
    source_service = build_source_link_service()
    chunk_data = source_service.get_chunk_by_vector_id(db, vector_id)
    
    if not chunk_data:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    # Verify chunk belongs to the case
    if chunk_data.get("case_id") != case_id:
        raise HTTPException(status_code=404, detail="Chunk not found for this case")
    
    return ChunkResponse(**chunk_data)


@router.post("/dashboard/{case_id}/chunks/search", response_model=ChunkSearchResponse)
async def search_chunks(
    case_id: str,
    request: ChunkSearchRequest,
    db: Session = Depends(get_db)
):
    """
    Search chunks within a case using semantic search
    
    Optionally filter by section type.
    """
    from app.models.document_chunk import SectionType
    
    try:
        # Convert section filter strings to SectionType enum
        section_filter = None
        if request.section_filter:
            section_filter = [SectionType(s) for s in request.section_filter]
        
        # Retrieve chunks
        chunks = rag_retriever.retrieve_for_query(
            db=db,
            query=request.query,
            case_id=case_id,
            top_k=request.top_k,
            section_filter=section_filter
        )
        
        results = [
            ChunkSearchResult(
                chunk_id=c.chunk_id,
                vector_id=c.vector_id,
                file_id=c.file_id,
                page_number=c.page_number,
                section_type=c.section_type.value,
                score=c.score,
                text=c.chunk_text
            )
            for c in chunks
        ]
        
        return ChunkSearchResponse(
            results=results,
            total=len(results)
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid section type: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/{case_id}/chunks", response_model=ChunkSearchResponse)
async def list_case_chunks(
    case_id: str,
    section_type: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    List all chunks for a case
    
    Optionally filter by section type. Supports pagination.
    """
    from app.models.document_chunk import SectionType
    
    try:
        if section_type:
            section_enum = SectionType(section_type)
            chunks = chunk_repository.get_by_section(db, case_id, section_enum)
        else:
            chunks = chunk_repository.get_by_case_id(db, case_id)
        
        # Apply pagination
        start = (page - 1) * page_size
        end = start + page_size
        paginated_chunks = chunks[start:end]
        
        results = [
            ChunkSearchResult(
                chunk_id=c.id,
                vector_id=c.vector_id,
                file_id=c.file_id,
                page_number=c.page_number,
                section_type=c.section_type.value,
                score=1.0,
                text=c.chunk_text
            )
            for c in paginated_chunks
        ]
        
        return ChunkSearchResponse(
            results=results,
            total=len(chunks)
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid section type: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/{case_id}/chunks/stats")
async def get_chunk_stats(
    case_id: str,
    db: Session = Depends(get_db)
):
    """Get chunk statistics for a case"""
    from app.models.document_chunk import SectionType
    
    total = chunk_repository.count_by_case(db, case_id)
    
    section_counts = {}
    for section_type in SectionType:
        count = chunk_repository.count_by_section(db, case_id, section_type)
        if count > 0:
            section_counts[section_type.value] = count
    
    return {
        "case_id": case_id,
        "total_chunks": total,
        "by_section": section_counts
    }

