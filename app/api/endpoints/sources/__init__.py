"""
Sources/evidence API: contradiction, timeline, legacy source, files, entity source.

Single router is composed from sub-routers so that existing imports
`from app.api.endpoints import sources` and `sources.router` keep working.
Route order matters: more specific paths are included first.
"""

from fastapi import APIRouter

from . import contradiction, timeline, legacy_source, files, entity_source

router = APIRouter()
router.include_router(contradiction.router)
router.include_router(timeline.router)
router.include_router(legacy_source.router)
router.include_router(files.router)
router.include_router(entity_source.router)

__all__ = ["router"]
