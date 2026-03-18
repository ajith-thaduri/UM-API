from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.upload_session import UploadSession
from app.repositories.base import BaseRepository

class UploadSessionRepository(BaseRepository[UploadSession]):
    def __init__(self):
        super().__init__(UploadSession)

    def get_by_id(self, db: Session, id: str) -> Optional[UploadSession]:
        return db.query(UploadSession).filter(UploadSession.id == id).first()

    def get_by_user(self, db: Session, user_id: str) -> List[UploadSession]:
        return db.query(UploadSession).filter(UploadSession.user_id == user_id).all()
    
    def delete_by_id(self, db: Session, id: str) -> bool:
        session = self.get_by_id(db, id)
        if session:
            db.delete(session)
            db.commit()
            return True
        return False
