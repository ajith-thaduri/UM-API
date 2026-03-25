"""Prompt service for managing and rendering prompts from the database"""

import threading
import time
import logging
import re
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from app.repositories.prompt_repository import prompt_repository
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

class PromptService:
    """Service for retrieving and rendering prompts with caching"""

    CACHE_TTL_SECONDS = 60.0

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._last_refresh_at = 0.0

    def _get_db(self):
        return SessionLocal()

    def _ensure_cache(self, db: Session):
        """Reload cache from prompts table"""
        # Note: We've simplified the caching logic to just use the latest prompts.
        # Since we no longer have a global version singleton, we refresh the cache
        # periodically or when an update occurs.
        try:
            with self._lock:
                now = time.monotonic()
                should_reload = (
                    not self._cache
                    or (now - self._last_refresh_at) >= self.CACHE_TTL_SECONDS
                )
                if should_reload:
                    logger.info("Refreshing prompt cache from database")
                    all_prompts = prompt_repository.get_all(db, filters={"is_active": True})
                    new_cache = {}
                    for p in all_prompts:
                        new_cache[p.id] = {
                            "template": p.template,
                            "system_message": p.system_message,
                            "variables": p.variables,
                            "name": p.name,
                            "category": p.category
                        }
                    self._cache = new_cache
                    self._last_refresh_at = now
        except Exception as e:
            logger.error(f"Error refreshing prompt cache: {e}")

    def _merge_into_cache(self, prompt_id: str, row) -> Dict[str, Any]:
        """Store a row from DB into the in-memory cache (e.g. prompt added after process start)."""
        data = {
            "template": row.template,
            "system_message": row.system_message,
            "variables": row.variables,
            "name": row.name,
            "category": row.category,
        }
        with self._lock:
            self._cache[prompt_id] = data
            self._last_refresh_at = time.monotonic()
        return data

    def get_prompt_template(self, prompt_id: str) -> Optional[str]:
        """Get the raw template for a prompt"""
        with self._get_db() as db:
            self._ensure_cache(db)
            prompt_data = self._cache.get(prompt_id)
            if not prompt_data:
                p = prompt_repository.get_by_id(db, prompt_id)
                if p:
                    prompt_data = self._merge_into_cache(prompt_id, p)
                else:
                    return None
            return prompt_data["template"]

    def get_system_message(self, prompt_id: str) -> Optional[str]:
        """Get the system message for a prompt"""
        with self._get_db() as db:
            self._ensure_cache(db)
            prompt_data = self._cache.get(prompt_id)
            if not prompt_data:
                p = prompt_repository.get_by_id(db, prompt_id)
                if p:
                    prompt_data = self._merge_into_cache(prompt_id, p)
                else:
                    return None
            return prompt_data["system_message"]

    def render_prompt(self, prompt_id: str, variables: Dict[str, Any]) -> str:
        """Render a prompt by replacing variables in the template"""
        with self._get_db() as db:
            self._ensure_cache(db)
            prompt_data = self._cache.get(prompt_id)

            if not prompt_data:
                p = prompt_repository.get_by_id(db, prompt_id)
                if p:
                    prompt_data = self._merge_into_cache(prompt_id, p)
                else:
                    logger.error(f"Prompt {prompt_id} not found in database or cache")
                    raise ValueError(f"Prompt {prompt_id} not found")

            template = prompt_data["template"]
            
            try:
                def replace_var(match):
                    var_name = match.group(1)
                    if var_name in variables:
                        val = variables[var_name]
                        return str(val) if val is not None else ""
                    return match.group(0)
                
                rendered = re.sub(r'\{([a-zA-Z0-9_]+)\}', replace_var, template)
                return rendered
            except Exception as e:
                logger.error(f"Error rendering prompt {prompt_id}: {e}")
                raise e

    def refresh_cache(self):
        """Force a cache refresh"""
        with self._lock:
            self._cache = {} # Clear cache to trigger reload on next access
            self._last_refresh_at = 0.0

# Singleton instance
prompt_service = PromptService()
