"""Prompt service for managing and rendering prompts from the database"""

import logging
import re
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
import threading

from app.repositories.prompt_repository import prompt_repository
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

class PromptService:
    """Service for retrieving and rendering prompts with caching"""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _get_db(self):
        return SessionLocal()

    def _ensure_cache(self, db: Session):
        """Reload cache from prompts table"""
        # Note: We've simplified the caching logic to just use the latest prompts.
        # Since we no longer have a global version singleton, we refresh the cache
        # periodically or when an update occurs.
        try:
            with self._lock:
                if not self._cache:
                    logger.info("Initializing prompt cache from database")
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
        except Exception as e:
            logger.error(f"Error refreshing prompt cache: {e}")

    def get_prompt_template(self, prompt_id: str) -> Optional[str]:
        """Get the raw template for a prompt"""
        with self._get_db() as db:
            self._ensure_cache(db)
            prompt_data = self._cache.get(prompt_id)
            if not prompt_data:
                # Try fetching directly if not in cache
                p = prompt_repository.get_by_id(db, prompt_id)
                if p:
                    return p.template
            return prompt_data["template"] if prompt_data else None

    def get_system_message(self, prompt_id: str) -> Optional[str]:
        """Get the system message for a prompt"""
        with self._get_db() as db:
            self._ensure_cache(db)
            prompt_data = self._cache.get(prompt_id)
            if not prompt_data:
                # Try fetching directly if not in cache
                p = prompt_repository.get_by_id(db, prompt_id)
                if p:
                    return p.system_message
            return prompt_data["system_message"] if prompt_data else None

    def render_prompt(self, prompt_id: str, variables: Dict[str, Any]) -> str:
        """Render a prompt by replacing variables in the template"""
        with self._get_db() as db:
            self._ensure_cache(db)
            prompt_data = self._cache.get(prompt_id)
            
            if not prompt_data:
                # Try fetching directly if not in cache
                p = prompt_repository.get_by_id(db, prompt_id)
                if p:
                    prompt_data = {
                        "template": p.template,
                        "system_message": p.system_message
                    }
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

# Singleton instance
prompt_service = PromptService()
