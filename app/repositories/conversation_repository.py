"""Repository for conversation messages"""

from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.conversation import ConversationMessage
from app.models.case import Case


def _resolve_case_version_id(db: Session, case_id: str, case_version_id: Optional[str]) -> Optional[str]:
    if case_version_id:
        return case_version_id
    case = db.query(Case).filter(Case.id == case_id).first()
    return case.live_version_id if case else None


class ConversationRepository:
    """Repository for managing conversation messages"""

    def get_conversation_history(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        limit: int = 10,
        case_version_id: Optional[str] = None,
    ) -> List[ConversationMessage]:
        vid = _resolve_case_version_id(db, case_id, case_version_id)
        q = db.query(ConversationMessage).filter(
            ConversationMessage.case_id == case_id,
            ConversationMessage.user_id == user_id,
        )
        if vid:
            q = q.filter(ConversationMessage.case_version_id == vid)
        else:
            q = q.filter(ConversationMessage.case_version_id.is_(None))
        return (
            q.order_by(ConversationMessage.created_at.asc()).limit(limit).all()
        )

    def add_message(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        role: str,
        content: str,
        sources: Optional[List[dict]] = None,
        case_version_id: Optional[str] = None,
        agent_metadata: Optional[dict] = None,
    ) -> ConversationMessage:
        vid = _resolve_case_version_id(db, case_id, case_version_id)
        message = ConversationMessage(
            case_id=case_id,
            user_id=user_id,
            role=role,
            content=content,
            sources=sources or [],
            case_version_id=vid,
            agent_metadata=agent_metadata,
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message

    def clear_conversation(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        case_version_id: Optional[str] = None,
    ) -> int:
        vid = _resolve_case_version_id(db, case_id, case_version_id)
        q = db.query(ConversationMessage).filter(
            ConversationMessage.case_id == case_id,
            ConversationMessage.user_id == user_id,
        )
        if vid:
            q = q.filter(ConversationMessage.case_version_id == vid)
        else:
            q = q.filter(ConversationMessage.case_version_id.is_(None))
        count = q.delete()
        db.commit()
        return count


# Singleton instance
conversation_repository = ConversationRepository()
