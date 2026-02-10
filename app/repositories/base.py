"""Base repository with common CRUD operations"""

from typing import Generic, TypeVar, Type, Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository providing common CRUD operations"""

    def __init__(self, model: Type[ModelType]):
        """
        Initialize repository with model class

        Args:
            model: SQLAlchemy model class
        """
        self.model = model

    def get_by_id(self, db: Session, id: str) -> Optional[ModelType]:
        """
        Get a record by ID

        Args:
            db: Database session
            id: Record ID

        Returns:
            Model instance or None if not found
        """
        return db.query(self.model).filter(self.model.id == id).first()

    def get_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        order_desc: bool = False,
    ) -> List[ModelType]:
        """
        Get all records with optional filtering and pagination

        Args:
            db: Database session
            skip: Number of records to skip
            limit: Maximum number of records to return
            filters: Dictionary of field: value filters
            order_by: Field name to order by
            order_desc: Whether to order descending

        Returns:
            List of model instances
        """
        query = db.query(self.model)

        # Apply filters
        if filters:
            for field, value in filters.items():
                if hasattr(self.model, field):
                    query = query.filter(getattr(self.model, field) == value)

        # Apply ordering
        if order_by and hasattr(self.model, order_by):
            order_field = getattr(self.model, order_by)
            if order_desc:
                query = query.order_by(order_field.desc())
            else:
                query = query.order_by(order_field)

        return query.offset(skip).limit(limit).all()

    def create(self, db: Session, obj: ModelType) -> ModelType:
        """
        Create a new record

        Args:
            db: Database session
            obj: Model instance to create

        Returns:
            Created model instance
        """
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def update(self, db: Session, obj: ModelType) -> ModelType:
        """
        Update an existing record

        Args:
            db: Database session
            obj: Model instance to update

        Returns:
            Updated model instance
        """
        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db: Session, id: str) -> bool:
        """
        Delete a record by ID

        Args:
            db: Database session
            id: Record ID

        Returns:
            True if deleted, False if not found
        """
        obj = self.get_by_id(db, id)
        if obj:
            db.delete(obj)
            db.commit()
            return True
        return False

    def count(self, db: Session, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count records matching filters

        Args:
            db: Database session
            filters: Dictionary of field: value filters

        Returns:
            Count of matching records
        """
        query = db.query(self.model)

        if filters:
            for field, value in filters.items():
                if hasattr(self.model, field):
                    query = query.filter(getattr(self.model, field) == value)

        return query.count()

    def exists(self, db: Session, id: str) -> bool:
        """
        Check if a record exists by ID

        Args:
            db: Database session
            id: Record ID

        Returns:
            True if exists, False otherwise
        """
        return self.get_by_id(db, id) is not None

