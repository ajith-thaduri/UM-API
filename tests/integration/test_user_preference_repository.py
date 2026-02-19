import pytest
from app.repositories.user_preference_repository import UserPreferenceRepository
from app.models.user_preference import UserPreference
from app.models.user import User

def test_user_preference_repository_get_by_user_id(db):
    """Test getting user preference by user ID."""
    repo = UserPreferenceRepository()
    
    user = User(
        id="pref-repo-user-1",
        email="prefrepo1@example.com",
        name="Pref Repo User",
        is_active=True
    )
    preference = UserPreference(
        id="pref-1",
        user_id=user.id,
        llm_provider="openai",
        llm_model="gpt-4o"
    )
    db.add(user)
    db.add(preference)
    db.commit()
    
    found = repo.get_by_user_id(db, user.id)
    assert found is not None
    assert found.llm_provider == "openai"

def test_user_preference_repository_upsert_create(db):
    """Test upsert creating new preference."""
    repo = UserPreferenceRepository()
    
    user = User(
        id="upsert-create-user-1",
        email="upsertcreate1@example.com",
        name="Upsert Create User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    preference = repo.upsert(db, user.id, "claude", "claude-sonnet-4-5")
    assert preference is not None
    assert preference.llm_provider == "claude"
    assert preference.llm_model == "claude-sonnet-4-5"

def test_user_preference_repository_upsert_update(db):
    """Test upsert updating existing preference."""
    repo = UserPreferenceRepository()
    
    user = User(
        id="upsert-update-user-1",
        email="upsertupdate1@example.com",
        name="Upsert Update User",
        is_active=True
    )
    preference = UserPreference(
        id="pref-update-1",
        user_id=user.id,
        llm_provider="openai",
        llm_model="gpt-3.5-turbo"
    )
    db.add(user)
    db.add(preference)
    db.commit()
    
    # Update preference
    updated = repo.upsert(db, user.id, "openai", "gpt-4o")
    assert updated.llm_model == "gpt-4o"
