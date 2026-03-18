"""Integration tests for RAG API endpoints"""

import pytest
import uuid
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import status
from app.models.user import User
from app.models.case import Case, CaseStatus, Priority
from app.models.document_chunk import DocumentChunk, SectionType
from app.models.conversation import ConversationMessage


def get_auth_headers(client, email="rag@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_conversation_history(client, db):
    """Test getting conversation history"""
    headers = get_auth_headers(client, "conversationrag@example.com")
    
    user = db.query(User).filter(User.email == "conversationrag@example.com").first()
    
    case = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-001",
        patient_name="Test Patient",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    
    from app.repositories.conversation_repository import conversation_repository
    conversation_repository.add_message(db, case.id, user.id, "user", "Question 1")
    conversation_repository.add_message(db, case.id, user.id, "assistant", "Answer 1")
    db.commit()
    
    response = client.get(f"/api/v1/dashboard/{case.id}/conversation", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "messages" in data
    assert len(data["messages"]) == 2


@patch("app.api.endpoints.rag.main_agent")
def test_rerun_agent(mock_main_agent, client, db):
    """Test rerunning an agent"""
    headers = get_auth_headers(client, "rerunagent@example.com")
    
    user = db.query(User).filter(User.email == "rerunagent@example.com").first()
    
    case = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-001",
        patient_name="Test Patient",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    db.commit()
    
    # Mock main agent
    mock_main_agent.rerun_agent.return_value = {
        "success": True,
        "facet_type": "summary",
        "snapshot_id": "snap-1",
        "message": "Rerun successful"
    }
    
    query_data = {
        "query_refinement": "More specific query"
    }
    
    response = client.post(f"/api/v1/dashboard/{case.id}/agent/summary/rerun", json=query_data, headers=headers)
    assert response.status_code == status.HTTP_200_OK


def test_get_chunk(client, db):
    """Test getting chunk by ID"""
    headers = get_auth_headers(client, "getchunk@example.com")
    
    user = db.query(User).filter(User.email == "getchunk@example.com").first()
    
    case = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-001",
        patient_name="Test Patient",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    
    from app.models.case_file import CaseFile
    file = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="test.pdf",
        file_path="/path/to/test.pdf",
        file_size=1024,
        page_count=5,
        file_order=0
    )
    db.add(file)
    
    chunk = DocumentChunk(
        id=str(uuid.uuid4()),
        case_id=case.id,
        file_id=file.id,
        user_id=user.id,
        chunk_index=0,
        page_number=1,
        section_type=SectionType.MEDICATIONS,
        chunk_text="Test chunk text",
        char_start=0,
        char_end=15,
        token_count=5,
        vector_id=str(uuid.uuid4())
    )
    db.add(chunk)
    db.commit()
    
    response = client.get(f"/api/v1/dashboard/{case.id}/source/chunk/{chunk.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["chunk_id"] == chunk.id
    assert data["text"] == "Test chunk text"


@patch("app.services.rag_retriever.rag_retriever.retrieve_for_query")
def test_search_chunks(mock_search, client, db):
    """Test searching chunks"""
    headers = get_auth_headers(client, "searchchunks@example.com")
    
    user = db.query(User).filter(User.email == "searchchunks@example.com").first()
    
    case = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-001",
        patient_name="Test Patient",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    db.commit()
    
    # Mock RAG retriever response
    from app.services.rag_retriever import RAGContext
    mock_context = RAGContext(
        chunks=[],
        total_tokens=10,
        formatted_context="Test context",
        source_references=[]
    )
    mock_search.return_value = AsyncMock(return_value=mock_context)
    
    search_data = {
        "query": "test query",
        "section_filter": ["medications"],
        "top_k": 10
    }
    
    response = client.post(f"/api/v1/dashboard/{case.id}/chunks/search", json=search_data, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "results" in data
