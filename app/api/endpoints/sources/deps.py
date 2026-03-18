"""Dependencies for source/evidence endpoints."""

from app.repositories.entity_source_repository import EntitySourceRepository
from app.services.entity_source_service import EntitySourceService


def get_entity_source_repository() -> EntitySourceRepository:
    """Dependency for EntitySourceRepository."""
    return EntitySourceRepository()


def get_entity_source_service() -> EntitySourceService:
    """Dependency for EntitySourceService."""
    return EntitySourceService()
