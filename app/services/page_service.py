"""Page service for creating and managing normalized pages"""

import hashlib
import logging
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.normalized_page import NormalizedPage
from app.models.page_vector import PageVector
from app.models.page_temporal_profile import PageTemporalProfile

logger = logging.getLogger(__name__)


class PageService:
    """
    Service for creating and managing normalized pages.
    
    Core responsibilities:
    - Create NormalizedPage records from PDF extraction
    - Generate page-level embeddings
    - Update page temporal profiles from entities
    - Retrieve pages for RAG operations
    """
    
    def create_pages_from_pdf(
        self,
        db: Session,
        case_id: str,
        file_id: str,
        user_id: str,
        pdf_extraction_result: Dict
    ) -> List[NormalizedPage]:
        """
        Create normalized page records from PDF extraction.
        
        Args:
            db: Database session
            case_id: Case ID
            file_id: File ID
            user_id: User ID
            pdf_extraction_result: Output from pdf_service.extract_text_with_coordinates
                Expected format: {
                    "pages": [
                        {
                            "page_number": int,
                            "text": str,
                            "text_segments": List[Dict]  # bbox coordinates
                        }
                    ]
                }
        
        Returns:
            List of created NormalizedPage objects
        """
        pages = []
        
        for page_data in pdf_extraction_result.get("pages", []):
            page_num = page_data.get("page_number")
            raw_text = page_data.get("text", "")
            text_segments = page_data.get("text_segments", [])
            
            # Generate deterministic page ID
            page_id = NormalizedPage.generate_page_id(case_id, file_id, page_num)
            
            # Compute text hash for deduplication
            text_hash = NormalizedPage.compute_text_hash(raw_text)
            
            # Create page
            page = NormalizedPage(
                page_id=page_id,
                case_id=case_id,
                file_id=file_id,
                user_id=user_id,
                page_number=page_num,
                raw_text=raw_text,
                text_hash=text_hash,
                layout_tokens=text_segments,  # Preserve bbox info
                char_count=len(raw_text)
            )
            
            pages.append(page)
        
        # Bulk create with exception handling
        try:
            db.bulk_save_objects(pages)
            db.flush()
            logger.info(f"Created {len(pages)} normalized pages for case {case_id}, file {file_id}")
        except Exception as e:
            logger.error(f"Failed to create normalized pages: {e}")
            raise
        
        return pages
    
    def generate_page_embeddings(
        self,
        db: Session,
        case_id: str,
        user_id: str
    ) -> int:
        """
        Generate embeddings for all pages in a case.
        
        Args:
            db: Database session
            case_id: Case ID
            user_id: User ID
        
        Returns:
            Number of page embeddings created
        """
        from app.services.embedding_service import embedding_service
        
        # Get all pages for case (that don't already have embeddings)
        existing_page_ids = db.query(PageVector.page_id).filter(
            PageVector.case_id == case_id
        ).all()
        existing_page_ids = {pid[0] for pid in existing_page_ids}
        
        pages = db.query(NormalizedPage).filter(
            NormalizedPage.case_id == case_id,
            ~NormalizedPage.page_id.in_(existing_page_ids)  # Skip already embedded
        ).all()
        
        if not pages:
            logger.info(f"No new pages to embed for case {case_id}")
            return 0
        
        logger.info(f"Generating embeddings for {len(pages)} pages in case {case_id}")
        
        # Generate embeddings in batch
        texts = [p.raw_text for p in pages]
        embeddings = embedding_service.generate_embeddings_batch(texts)
        
        # Create PageVector records
        page_vectors = []
        for page, embedding in zip(pages, embeddings):
            pv = PageVector(
                page_id=page.page_id,
                case_id=case_id,
                user_id=user_id,
                embedding=embedding,
                entity_count=0,  # Will be updated after entity extraction
                dated_entity_count=0
            )
            page_vectors.append(pv)
        
        # Bulk create
        try:
            db.bulk_save_objects(page_vectors)
            db.commit()
            logger.info(f"Created {len(page_vectors)} page embeddings for case {case_id}")
        except Exception as e:
            logger.error(f"Failed to create page embeddings: {e}")
            db.rollback()
            raise
        
        return len(page_vectors)
    
    def update_page_entity_counts(
        self,
        db: Session,
        page_id: str,
        entity_count: int,
        dated_entity_count: int
    ) -> None:
        """
        Update entity counts for a page after entity extraction.
        
        Args:
            db: Database session
            page_id: Page ID
            entity_count: Total number of entities on page
            dated_entity_count: Number of entities with dates on page
        """
        page_vector = db.query(PageVector).filter(
            PageVector.page_id == page_id
        ).first()
        
        if page_vector:
            page_vector.entity_count = entity_count
            page_vector.dated_entity_count = dated_entity_count
            db.commit()
    
    def update_page_temporal_profile(
        self,
        db: Session,
        page_id: str,
        earliest_date,
        latest_date,
        dated_entity_count: int
    ) -> None:
        """
        Update or create temporal profile for a page.
        
        This should be called after entity extraction to derive
        the temporal envelope from entity dates.
        
        Args:
            db: Database session
            page_id: Page ID
            earliest_date: Earliest entity date on page
            latest_date: Latest entity date on page
            dated_entity_count: Number of dated entities
        """
        profile = db.query(PageTemporalProfile).filter(
            PageTemporalProfile.page_id == page_id
        ).first()
        
        if profile:
            # Update existing
            profile.earliest_entity_date = earliest_date
            profile.latest_entity_date = latest_date
            profile.dated_entity_count = dated_entity_count
        else:
            # Create new
            profile = PageTemporalProfile(
                page_id=page_id,
                earliest_entity_date=earliest_date,
                latest_entity_date=latest_date,
                dated_entity_count=dated_entity_count
            )
            db.add(profile)
        
        db.commit()
    
    def get_pages_for_case(
        self,
        db: Session,
        case_id: str,
        file_id: Optional[str] = None
    ) -> List[NormalizedPage]:
        """
        Get all pages for a case, optionally filtered by file.
        
        Args:
            db: Database session
            case_id: Case ID
            file_id: Optional file ID filter
        
        Returns:
            List of NormalizedPage objects
        """
        query = db.query(NormalizedPage).filter(
            NormalizedPage.case_id == case_id
        )
        
        if file_id:
            query = query.filter(NormalizedPage.file_id == file_id)
        
        return query.order_by(
            NormalizedPage.file_id,
            NormalizedPage.page_number
        ).all()
    
    def get_page_by_id(
        self,
        db: Session,
        page_id: str
    ) -> Optional[NormalizedPage]:
        """Get a specific page by ID"""
        return db.query(NormalizedPage).filter(
            NormalizedPage.page_id == page_id
        ).first()


# Singleton instance
page_service = PageService()
