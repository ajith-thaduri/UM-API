"""API v1 router"""

from fastapi import APIRouter
from app.api.endpoints import (
    auth,
    cases,
    extractions,
    users,
    decisions,
    annotations,
    sources,
    dashboard,
    rag,
    upload_agent,
    user_preferences,
    usage,
    wallet,
    analytics,
    prompts,
    oauth,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="", tags=["auth"])
api_router.include_router(oauth.router, prefix="", tags=["oauth"])
api_router.include_router(sources.router, prefix="", tags=["sources"])
api_router.include_router(cases.router, prefix="/cases", tags=["cases"])
api_router.include_router(extractions.router, prefix="/extractions", tags=["extractions"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(decisions.router, prefix="/cases", tags=["decisions"])
api_router.include_router(annotations.router, prefix="", tags=["annotations"])
api_router.include_router(dashboard.router, prefix="", tags=["dashboard"])
api_router.include_router(rag.router, prefix="", tags=["rag"])
api_router.include_router(upload_agent.router, prefix="", tags=["upload-agent"])
api_router.include_router(user_preferences.router, prefix="", tags=["user-preferences"])
api_router.include_router(usage.router, prefix="", tags=["usage"])
api_router.include_router(wallet.router, prefix="", tags=["wallet"])
api_router.include_router(analytics.router, prefix="", tags=["analytics"])
api_router.include_router(prompts.router, prefix="", tags=["prompts"])

