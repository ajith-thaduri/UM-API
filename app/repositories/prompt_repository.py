"""Prompt repository for database-driven prompt management"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, text
import uuid
from datetime import datetime, timezone

from app.repositories.base import BaseRepository
from app.models.prompt import Prompt
from app.models.version_history import VersionEventType
from app.repositories.version_history_repository import version_history_repository


class PromptRepository(BaseRepository[Prompt]):
    """Repository for Prompt model with generic version history integration"""

    def __init__(self):
        super().__init__(Prompt)

    def get_by_category(self, db: Session, category: str) -> List[Prompt]:
        """Get prompts by category"""
        return db.query(Prompt).filter(Prompt.category == category, Prompt.is_active == True).all()

    def normalize_text(self, text: Optional[str]) -> Optional[str]:
        """Normalize text for consistent comparison (trim, line endings)"""
        if text is None:
            return None
        # Normalize line endings to \n and trim trailing spaces from each line
        lines = [line.rstrip() for line in text.replace('\r\n', '\n').split('\n')]
        # Join and trim overall
        return '\n'.join(lines).strip()

    def update_prompt(
        self, 
        db: Session, 
        prompt_id: str, 
        template: str, 
        system_message: Optional[str], 
        user_id: str,
        change_notes: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> Optional[Prompt]:
        """
        Update a prompt and record history in the generic version_history table.
        Uses row-level locking (FOR UPDATE) to ensure atomic versioning.
        """
        # 1. Lock the prompt row for update
        prompt = db.query(Prompt).filter(Prompt.id == prompt_id).with_for_update().first()
        if not prompt:
            return None

        # 2. Normalize inputs
        norm_template = self.normalize_text(template)
        norm_system = self.normalize_text(system_message)
        
        curr_template = self.normalize_text(prompt.template)
        curr_system = self.normalize_text(prompt.system_message)

        # 3. Check if anything actually changed
        changes = {}
        if norm_template != curr_template:
            changes["template"] = {"old": prompt.template, "new": template}
        if norm_system != curr_system:
            changes["system_message"] = {"old": prompt.system_message, "new": system_message}
            
        if not changes:
            # No real changes, just return the prompt
            return prompt

        if change_notes:
            changes["change_notes"] = change_notes

        # 4. Update prompt record
        prompt.template = template
        prompt.system_message = system_message
        prompt.updated_by = user_id
        prompt.updated_at = datetime.now(timezone.utc)
        
        # 5. Prepare snapshot for history
        snapshot = {
            "id": prompt.id,
            "category": prompt.category,
            "name": prompt.name,
            "template": prompt.template,
            "system_message": prompt.system_message,
            "variables": prompt.variables
        }

        # 6. Add history entry
        version_history_repository.add_entry(
            db=db,
            table_name="prompts",
            ref_id=prompt_id,
            event_type=VersionEventType.UPDATE,
            changes=changes,
            snapshot=snapshot,
            user_id=user_id,
            request_id=request_id
        )

        db.commit()
        db.refresh(prompt)
        return prompt

    def rollback_to_version(
        self, 
        db: Session, 
        prompt_id: str, 
        version_number: int,
        user_id: str,
        request_id: Optional[str] = None
    ) -> Optional[Prompt]:
        """
        Rollback a prompt to a specific historical version.
        """
        # 1. Lock the prompt row
        prompt = db.query(Prompt).filter(Prompt.id == prompt_id).with_for_update().first()
        if not prompt:
            return None

        # 2. Fetch the target version from history
        history_entry = version_history_repository.get_version(db, "prompts", prompt_id, version_number)
        if not history_entry or not history_entry.object_snapshot:
            return None

        snapshot = history_entry.object_snapshot
        
        # 3. Record what's changing
        changes = {
            "template": {"old": prompt.template, "new": snapshot.get("template")},
            "system_message": {"old": prompt.system_message, "new": snapshot.get("system_message")},
            "rollback_to_version": version_number
        }

        # 4. Restore values from snapshot
        prompt.template = snapshot.get("template")
        prompt.system_message = snapshot.get("system_message")
        prompt.updated_by = user_id
        prompt.updated_at = datetime.now(timezone.utc)

        # 5. Add ROLLBACK history entry
        version_history_repository.add_entry(
            db=db,
            table_name="prompts",
            ref_id=prompt_id,
            event_type=VersionEventType.ROLLBACK,
            changes=changes,
            snapshot=snapshot, # New state is same as the one we rolled back to
            user_id=user_id,
            request_id=request_id
        )

        db.commit()
        db.refresh(prompt)
        return prompt

    def get_prompt_history(self, db: Session, prompt_id: str) -> List[Dict[str, Any]]:
        """Get version history for a specific prompt with user details"""
        from app.models.user import User
        
        history = version_history_repository.get_history(db, "prompts", prompt_id)
        
        # Fetch user details for all unique user IDs
        user_ids = set(h.changed_by_user_id for h in history if h.changed_by_user_id)
        users = {}
        if user_ids:
            user_records = db.query(User).filter(User.id.in_(user_ids)).all()
            users = {u.id: u for u in user_records}
        
        result = []
        for h in history:
            user = users.get(h.changed_by_user_id) if h.changed_by_user_id else None
            result.append({
                "version_number": h.version_number,
                "event_type": h.event_type,
                "created_at": h.created_at,
                "changed_by": h.changed_by_user_id,
                "changed_by_email": user.email if user else None,
                "changed_by_name": user.full_name if user and hasattr(user, 'full_name') else None,
                "changes": h.object_changes,
                "snapshot": h.object_snapshot
            })
        return result


# Singleton instance
prompt_repository = PromptRepository()
