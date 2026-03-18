import pytest
import os
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock

# Test Database setup
# In CI, DATABASE_URL should point to the test Postgres instance
@pytest.fixture(scope="session")
def db_engine():
    """Create a database engine for the entire test session."""
    from sqlalchemy import create_engine
    from app.core.config import settings
    engine = create_engine(settings.DATABASE_URL)
    yield engine
    engine.dispose()

@pytest.fixture(scope="function")
def db(db_engine) -> Generator:
    """
    Creates a new database session for a test, with a rollback at the end.
    This ensures test isolation by running each test in a transaction that is never committed.
    """
    from sqlalchemy.orm import sessionmaker
    connection = db_engine.connect()
    transaction = connection.begin()
    
    # Create a session bound to the connection
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db) -> Generator:
    """
    Provides a synchronous TestClient with the database dependency overridden.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_db
    
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture(scope="function")
async def async_client(db) -> AsyncGenerator:
    """
    Provides an asynchronous AsyncClient with the database dependency overridden.
    """
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.db.session import get_db
    
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

# Mock Fixtures
@pytest.fixture
def mock_openai(monkeypatch):
    """Mock OpenAI API calls."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    monkeypatch.setattr("openai.resources.chat.Completions.create", mock)
    return mock

@pytest.fixture
def mock_anthropic(monkeypatch):
    """Mock Anthropic API calls."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    monkeypatch.setattr("anthropic.resources.messages.Messages.create", mock)
    return mock

@pytest.fixture
def mock_llm_service(monkeypatch):
    """Mock the internal LLM service to avoid token usage."""
    from unittest.mock import AsyncMock
    mock = AsyncMock(return_value=("Mock LLM response", {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}))
    # Patch the chat_completion method on BaseLLMService
    monkeypatch.setattr("app.services.llm.base_llm_service.BaseLLMService.chat_completion", mock)
    return mock
