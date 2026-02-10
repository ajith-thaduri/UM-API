"""Repository for conversation messages"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.conversation import ConversationMessage


class ConversationRepository:
    """Repository for managing conversation messages"""
    
    def get_conversation_history(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        limit: int = 10
    ) -> List[ConversationMessage]:
        """
        Get conversation history for a case, ordered by creation date
        
        Args:
            db: Database session
            case_id: Case ID
            user_id: User ID
            limit: Maximum number of messages to return (default: 10)
            
        Returns:
            List of ConversationMessage objects, ordered by created_at (oldest first)
        """
        return (
            db.query(ConversationMessage)
            .filter(
                ConversationMessage.case_id == case_id,
                ConversationMessage.user_id == user_id
            )
            .order_by(ConversationMessage.created_at.asc())
            .limit(limit)
            .all()
        )
    
    def add_message(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        role: str,
        content: str,
        sources: Optional[List[dict]] = None
    ) -> ConversationMessage:
        """
        Add a message to the conversation
        
        Args:
            db: Database session
            case_id: Case ID
            user_id: User ID
            role: Message role ("user" or "assistant")
            content: Message content
            sources: Optional list of source references
            
        Returns:
            Created ConversationMessage
        """
        message = ConversationMessage(
            case_id=case_id,
            user_id=user_id,
            role=role,
            content=content,
            sources=sources or []
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    
    def clear_conversation(
        self,
        db: Session,
        case_id: str,
        user_id: str
    ) -> int:
        """
        Clear all messages for a conversation
        
        Args:
            db: Database session
            case_id: Case ID
            user_id: User ID
            
        Returns:
            Number of messages deleted
        """
        count = (
            db.query(ConversationMessage)
            .filter(
                ConversationMessage.case_id == case_id,
                ConversationMessage.user_id == user_id
            )
            .delete()
        )
        db.commit()
        return count


# Singleton instance
conversation_repository = ConversationRepository()


