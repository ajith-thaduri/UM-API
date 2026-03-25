import pytest
from unittest.mock import MagicMock, patch
from app.services.prompt_service import PromptService
from app.models.prompt import Prompt

def test_prompt_service_get_template(db):
    """Test getting prompt template."""
    service = PromptService()
    
    # Create a prompt
    prompt = Prompt(
        id="service-prompt-1",
        category="test",
        name="Service Prompt",
        template="Template with {variable}",
        variables=["variable"],
        is_active=True
    )
    db.add(prompt)
    db.commit()
    
    # Mock the _get_db to return our test db
    service._get_db = lambda: db
    service.refresh_cache()  # Clear cache to force reload
    
    template = service.get_prompt_template("service-prompt-1")
    assert template == "Template with {variable}"

def test_prompt_service_get_system_message(db):
    """Test getting system message."""
    service = PromptService()
    
    prompt = Prompt(
        id="service-prompt-2",
        category="test",
        name="Service Prompt 2",
        template="Template",
        system_message="System message",
        variables=[],
        is_active=True
    )
    db.add(prompt)
    db.commit()
    
    # Mock the _get_db to return our test db
    service._get_db = lambda: db
    service.refresh_cache()  # Clear cache to force reload
    
    system_msg = service.get_system_message("service-prompt-2")
    assert system_msg == "System message"

def test_prompt_service_render_prompt(db):
    """Test rendering prompt with variables."""
    service = PromptService()
    
    prompt = Prompt(
        id="service-prompt-3",
        category="test",
        name="Service Prompt 3",
        template="Hello {name}, you have {count} messages",
        variables=["name", "count"],
        is_active=True
    )
    db.add(prompt)
    db.commit()
    
    # Mock the _get_db to return our test db
    service._get_db = lambda: db
    service.refresh_cache()  # Clear cache to force reload
    
    rendered = service.render_prompt("service-prompt-3", {"name": "Alice", "count": "5"})
    assert "Alice" in rendered
    assert "5" in rendered

def test_prompt_service_refresh_cache(db):
    """Test cache refresh."""
    service = PromptService()
    
    # Create prompt
    prompt = Prompt(
        id="cache-prompt-1",
        category="test",
        name="Cache Prompt",
        template="Template",
        variables=[],
        is_active=True
    )
    db.add(prompt)
    db.commit()
    
    # Mock the _get_db to return our test db
    service._get_db = lambda: db
    service.refresh_cache()  # Clear cache to force reload
    
    # Should work after refresh
    template = service.get_prompt_template("cache-prompt-1")
    assert template == "Template"

def test_prompt_service_missing_prompt(db):
    """Test handling missing prompt."""
    service = PromptService()
    
    # Mock the _get_db to return our test db
    service._get_db = lambda: db
    service.refresh_cache()  # Clear cache
    
    template = service.get_prompt_template("non-existent-prompt")
    assert template is None


def test_prompt_service_refreshes_stale_cache(db):
    """Prompt cache should reload after TTL so DB prompt edits propagate to workers."""
    service = PromptService()
    service.CACHE_TTL_SECONDS = 0
    service._get_db = lambda: db

    original = MagicMock(
        id="stale-cache-prompt",
        template="Original {value}",
        system_message="Original system",
        variables=["value"],
        name="Prompt",
        category="test",
    )
    updated = MagicMock(
        id="stale-cache-prompt",
        template="Updated {value}",
        system_message="Updated system",
        variables=["value"],
        name="Prompt",
        category="test",
    )

    with patch("app.services.prompt_service.prompt_repository.get_all", side_effect=[[original], [updated]]) as mock_get_all:
        service.refresh_cache()
        assert service.get_prompt_template("stale-cache-prompt") == "Original {value}"
        assert service.get_system_message("stale-cache-prompt") == "Updated system"

    assert mock_get_all.call_count >= 2
