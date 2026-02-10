"""Service for managing entity sources - industry-standard source linking."""

import uuid
import logging
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, PendingRollbackError

from app.models.entity_source import EntitySource
from app.repositories.entity_source_repository import EntitySourceRepository
from app.repositories.chunk_repository import ChunkRepository

logger = logging.getLogger(__name__)


def _is_session_broken(exc: BaseException) -> bool:
    """True if the exception leaves the DB session in an invalid state (needs rollback)."""
    if isinstance(exc, (OperationalError, PendingRollbackError)):
        return True
    msg = (getattr(exc, "message", None) or str(exc)).lower()
    return "rollback" in msg or ("connection" in msg and ("closed" in msg or "unexpectedly" in msg))


class EntitySourceService:
    """Service for creating and managing entity source attributions."""
    
    def __init__(self):
        self.entity_source_repo = EntitySourceRepository()
        self.chunk_repo = ChunkRepository()
    
    def create_entity_source(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        entity_type: str,
        entity_id: str,
        chunk_id: Optional[str] = None,
        file_id: Optional[str] = None,
        page_number: Optional[int] = None,
        bbox: Optional[Dict[str, float]] = None,
        snippet: Optional[str] = None,
        full_text: Optional[str] = None,
    ) -> EntitySource:
        """
        Create an entity source record.
        
        If chunk_id is provided, it will be used to get accurate location data.
        Otherwise, file_id and page_number must be provided.
        """
        # If chunk_id is provided, get location data from chunk
        if chunk_id:
            chunk = self.chunk_repo.get_by_id(db, chunk_id)
            if chunk:
                file_id = file_id or chunk.file_id
                page_number = page_number or chunk.page_number
                bbox = bbox or chunk.bbox
                snippet = snippet or chunk.chunk_text[:500] if chunk.chunk_text else None
                logger.debug(f"Resolved location from chunk {chunk_id}: file_id={file_id}, page={page_number}")
            else:
                logger.warning(f"Chunk {chunk_id} not found, using provided file_id/page_number")
        
        # Validate required fields
        if not file_id or page_number is None:
            raise ValueError(f"Entity source requires file_id and page_number (entity_type={entity_type}, entity_id={entity_id})")
        
        # Check if entity source already exists
        try:
            existing = self.entity_source_repo.get_by_entity(
                db, case_id, entity_type, entity_id, user_id
            )
            
            if existing:
                # Update existing record
                existing.chunk_id = chunk_id or existing.chunk_id
                existing.file_id = file_id
                existing.page_number = page_number
                existing.bbox = bbox or existing.bbox
                existing.snippet = snippet or existing.snippet
                existing.full_text = full_text or existing.full_text
                # Don't commit here - let the caller manage transactions
                db.flush()  # Flush to get ID but don't commit
                db.refresh(existing)
                logger.debug(f"Updated entity source {entity_type}:{entity_id}")
                return existing
        except Exception as e:
            error_msg = str(e)
            if "entity_sources" in error_msg.lower() or "does not exist" in error_msg.lower():
                raise ValueError(f"Entity sources table does not exist. Run migration: alembic upgrade head")
            raise
        
        # Create new record
        entity_source = EntitySource(
            id=str(uuid.uuid4()),
            case_id=case_id,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            chunk_id=chunk_id,
            file_id=file_id,
            page_number=page_number,
            bbox=bbox,
            snippet=snippet,
            full_text=full_text,
        )
        db.add(entity_source)
        # Don't commit here - let the caller manage transactions
        db.flush()  # Flush to get ID but don't commit
        db.refresh(entity_source)
        logger.debug(f"Created entity source {entity_type}:{entity_id} -> {file_id}:{page_number}")
        return entity_source
    
    def get_entity_source(
        self,
        db: Session,
        case_id: str,
        entity_type: str,
        entity_id: str,
        user_id: Optional[str] = None
    ) -> Optional[EntitySource]:
        """Get source information for an entity."""
        return self.entity_source_repo.get_by_entity(
            db, case_id, entity_type, entity_id, user_id
        )
    
    def bulk_create_entity_sources(
        self,
        db: Session,
        sources_data: List[Dict],
        case_id: str,
        user_id: str,
        commit: bool = True
    ) -> int:
        """
        Bulk create or update entity sources using production-safe pattern.
        
        Args:
            db: Database session
            sources_data: List of dicts containing source data
            case_id: Case ID
            user_id: User ID
            commit: Whether to commit the transaction (default: True)
            
        Returns:
            Number of sources processed
        """
        if not sources_data:
            return 0
            
        import logging
        logger = logging.getLogger(__name__)
        
        # 1. Pre-fetch existing sources for this case to handle "Upsert" logic in memory
        try:
            existing_sources = self.entity_source_repo.list_for_case(db, case_id, user_id)
            # Create lookup map: (entity_type, entity_id, chunk_id) -> EntitySource object
            # Using chunk_id as part of key helps distinguish duplicate mentions
            existing_map = {}
            for s in existing_sources:
                 key = (s.entity_type, s.entity_id, s.chunk_id)
                 existing_map[key] = s
                 
        except Exception as e:
            if "entity_sources" in str(e).lower() or "does not exist" in str(e).lower():
                logger.warning("Entity sources table does not exist. Skipping bulk creation.")
                return 0
            raise

        new_rows = []
        updated_count = 0
        
        for data in sources_data:
            entity_type = data.get("entity_type")
            entity_id = data.get("entity_id")
            chunk_id = data.get("chunk_id")
            
            if not entity_type or not entity_id:
                continue
                
            key = (entity_type, entity_id, chunk_id)
            
            if key in existing_map:
                # Update existing record - ORM tracks these changes automatically
                existing = existing_map[key]
                # Only update fields if they have values
                if data.get("file_id"): existing.file_id = data.get("file_id")
                if data.get("page_number"): existing.page_number = data.get("page_number")
                if data.get("bbox"): existing.bbox = data.get("bbox")
                if data.get("snippet"): existing.snippet = data.get("snippet")
                if data.get("full_text"): existing.full_text = data.get("full_text")
                updated_count += 1
            else:
                # Prepare new record dict for bulk_insert_mappings
                new_rows.append({
                    "id": str(uuid.uuid4()),
                    "case_id": case_id,
                    "user_id": user_id,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "chunk_id": chunk_id,
                    "file_id": data.get("file_id"),
                    "page_number": data.get("page_number"),
                    "bbox": data.get("bbox"),
                    "snippet": data.get("snippet"),
                    "full_text": data.get("full_text"),
                    # Add timestamps if model doesn't handle them automatically in bulk inserts
                    # usually handled by database server_default, but safer to be explicit if needed
                    # but for now relying on DB defaults for created_at
                })
        
        # Bulk save new records
        if new_rows:
            # bulk_insert_mappings is much faster than adding objects
            db.bulk_insert_mappings(EntitySource, new_rows)
        
        # Commit all changes (updates from ORM + bulk inserts)
        if commit:
            try:
                db.commit()
                logger.info(f"Bulk processed entity sources: {len(new_rows)} created, {updated_count} updated")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to commit bulk entity sources: {e}")
                raise
        else:
            # If not committing, we flush to ensure IDs are generated if needed (though bulk_insert_mappings doesn't return objs)
            # But mostly we just let the session handle it
            logger.info(f"Bulk processed entity sources (pending commit): {len(new_rows)} created, {updated_count} updated")
            if updated_count > 0:
                db.flush()
            
        return len(new_rows) + updated_count

    def create_sources_from_extraction(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        extracted_data: Dict,
        extraction_sources: List[Dict],
        file_lookup: Dict[str, str]  # file_id -> file_name
    ) -> int:
        """
        Create entity sources from extraction results using optimized bulk processing.
        
        Args:
            db: Database session
            case_id: Case ID
            user_id: User ID
            extracted_data: Extracted clinical data
            extraction_sources: Source references from RAG
            file_lookup: Mapping of file_id to file_name
            
        Returns:
            Number of entity sources created
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"[SOURCE_LINKING] Preparing entity sources from {len(extraction_sources)} extraction_sources")
        
        # Build chunk lookup from extraction_sources
        chunk_lookup = {}
        if extraction_sources:
            # Get all unique chunk_ids
            chunk_ids = [s.get("chunk_id") for s in extraction_sources if s.get("chunk_id")]
            if chunk_ids:
                # Load chunks from database to get chunk_text (Bulk fetch)
                chunks = db.query(self.chunk_repo.model).filter(
                    self.chunk_repo.model.id.in_(chunk_ids)
                ).all()
                chunk_text_map = {chunk.id: chunk.chunk_text for chunk in chunks}
                
                # Add chunk_text to sources
                for source in extraction_sources:
                    chunk_id = source.get("chunk_id")
                    if chunk_id and chunk_id in chunk_text_map:
                        source["chunk_text"] = chunk_text_map[chunk_id]
        
        for source in extraction_sources:
            chunk_id = source.get("chunk_id")
            if chunk_id:
                chunk_lookup[chunk_id] = source
        
        # Verify entity_sources table exists before processing
        try:
            # Simple check
            self.entity_source_repo.count(db, filters={"case_id": case_id})
        except Exception as e:
            error_msg = str(e)
            if "entity_sources" in error_msg.lower() or "does not exist" in error_msg.lower():
                logger.warning(f"Entity sources table does not exist. Skipping source creation.")
                return 0
            # If other error, assume table exists but query failed, likely harmless to proceed to try/catch blocks
        
        sources_to_create = []
        
        # Helper to prepare source data dictionary
        def prepare_source_data(entity_type, entity_id, item, idx, source):
            if not source:
                return None
                
            chunk_id = source.get("chunk_id")
            file_id = source.get("file_id") or (item.get("source_file") if isinstance(item, dict) else None)
            page_number = source.get("page_number") or (item.get("source_page") if isinstance(item, dict) else None)
            
            # Require valid location data
            if not (chunk_id or (file_id and page_number)):
                return None
                
            return {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "chunk_id": chunk_id,
                "file_id": file_id,
                "page_number": page_number,
                "bbox": source.get("bbox"),
                "snippet": item.get("name", "")[:200] if isinstance(item, dict) else str(item)[:200]
            }

        # 1. Medications
        for idx, med in enumerate(extracted_data.get("medications", [])):
            med_name = med.get("name", "") if isinstance(med, dict) else str(med)
            source = self._find_source_for_item(extraction_sources, "medication", idx, chunk_lookup, entity_name=med_name)
            data = prepare_source_data("medication", f"medication:{idx}", med, idx, source)
            if data:
                sources_to_create.append(data)
        
        # 2. Labs
        for idx, lab in enumerate(extracted_data.get("labs", [])):
            lab_name = lab.get("test_name", "") if isinstance(lab, dict) else str(lab)
            source = self._find_source_for_item(extraction_sources, "lab", idx, chunk_lookup, entity_name=lab_name)
            data = prepare_source_data("lab", f"lab:{idx}", lab, idx, source)
            if data:
                # Update snippet for labs
                data["snippet"] = lab.get("test_name", "")[:200] if isinstance(lab, dict) else str(lab)[:200]
                sources_to_create.append(data)
                
        # 3. Diagnoses
        for idx, dx in enumerate(extracted_data.get("diagnoses", [])):
            if isinstance(dx, dict):
                dx_name = dx.get("name", "")
                source = self._find_source_for_item(extraction_sources, "diagnosis", idx, chunk_lookup, entity_name=dx_name)
                data = prepare_source_data("diagnosis", f"diagnosis:{idx}", dx, idx, source)
                if data:
                    sources_to_create.append(data)
                    
        # 4. Vitals
        for idx, vital in enumerate(extracted_data.get("vitals", [])):
            source = self._find_source_for_item(extraction_sources, "vital", idx, chunk_lookup)
            data = prepare_source_data("vital", f"vital:{idx}", vital, idx, source)
            if data:
                # Update snippet for vitals
                snippet = f"{vital.get('type', '')}: {vital.get('value', '')}"[:200] if isinstance(vital, dict) else str(vital)[:200]
                data["snippet"] = snippet
                sources_to_create.append(data)

        # Execute bulk creation
        if sources_to_create:
            logger.info(f"[SOURCE_LINKING] Bulk creating {len(sources_to_create)} entity sources")
            return self.bulk_create_entity_sources(db, sources_to_create, case_id, user_id)
        
        return 0
    
    def _find_source_for_item(
        self,
        extraction_sources: List[Dict],
        source_type: str,
        item_index: int,
        chunk_lookup: Dict[str, Dict],
        entity_name: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Find source reference for an item by type and index.
        
        Args:
            extraction_sources: List of source references from RAG
            source_type: Type of entity (medication, lab, diagnosis, etc.)
            item_index: Index of the item in the extracted data
            chunk_lookup: Lookup dict for chunk data
            entity_name: Optional entity name for better matching
        
        Returns:
            Source dict with chunk_id, file_id, page_number, etc.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Filter sources by type
        type_sources = [s for s in extraction_sources if s.get("type") == source_type]
        
        logger.debug(f"[SOURCE_LINKING] Finding source for {source_type}:{item_index}, found {len(type_sources)} sources of this type")
        
        # Strategy 1: Try to get source at index (most common case)
        if item_index < len(type_sources):
            source = type_sources[item_index]
            # Enhance with chunk data if available
            chunk_id = source.get("chunk_id")
            if chunk_id and chunk_id in chunk_lookup:
                chunk_data = chunk_lookup[chunk_id]
                source["bbox"] = chunk_data.get("bbox")
            
            logger.debug(f"[SOURCE_LINKING] Found source at index {item_index}: chunk_id={chunk_id}, file_id={source.get('file_id')}, page={source.get('page_number')}")
            return source
        
        # Strategy 2: If entity_name provided, try to match by text similarity
        # This helps when chunks are distributed differently than entity indices
        if entity_name and type_sources:
            entity_name_lower = entity_name.lower().strip()
            best_match = None
            best_score = 0
            
            # Try to find chunk that contains entity name
            for source in type_sources:
                chunk_id = source.get("chunk_id")
                if chunk_id and chunk_id in chunk_lookup:
                    chunk_data = chunk_lookup[chunk_id]
                    # Get chunk text from repository if available
                    chunk_text = chunk_data.get("chunk_text", "").lower()
                    if entity_name_lower in chunk_text:
                        # Calculate match score (longer entity name = better match)
                        score = len(entity_name_lower)
                        if score > best_score:
                            best_score = score
                            best_match = source
            
            if best_match:
                chunk_id = best_match.get("chunk_id")
                if chunk_id and chunk_id in chunk_lookup:
                    chunk_data = chunk_lookup[chunk_id]
                    best_match["bbox"] = chunk_data.get("bbox")
                
                logger.debug(f"[SOURCE_LINKING] Found source by text match for '{entity_name}': chunk_id={chunk_id}, file_id={best_match.get('file_id')}, page={best_match.get('page_number')}")
                return best_match
        
        # Strategy 3: Fallback to first source of this type
        if type_sources:
            source = type_sources[0]
            chunk_id = source.get("chunk_id")
            if chunk_id and chunk_id in chunk_lookup:
                chunk_data = chunk_lookup[chunk_id]
                source["bbox"] = chunk_data.get("bbox")
            
            logger.debug(f"[SOURCE_LINKING] Using fallback (first source): chunk_id={chunk_id}, file_id={source.get('file_id')}, page={source.get('page_number')}")
            return source
        
        logger.warning(f"[SOURCE_LINKING] No sources found for {source_type}:{item_index}")
        return None
    
    def validate_page_number(
        self,
        db: Session,
        file_id: str,
        page_number: int,
        source_mapping: Optional[Dict] = None
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Validate that page_number exists in the PDF.
        
        Returns:
            (is_valid, max_page, error_message) tuple
        """
        if not file_id:
            return (False, None, "file_id is required for validation")
        
        if page_number is None or page_number < 1:
            return (False, None, f"Invalid page number: {page_number}")
        
        if source_mapping:
            file_page_mapping = source_mapping.get("file_page_mapping", {})
            if file_id in file_page_mapping:
                pages = file_page_mapping[file_id]
                if isinstance(pages, dict):
                    page_keys = [k for k in pages.keys() if str(k).isdigit()]
                    if page_keys:
                        max_page = max((int(k) for k in page_keys), default=0)
                        is_valid = page_number >= 1 and page_number <= max_page
                        if not is_valid:
                            return (False, max_page, f"Page {page_number} exceeds maximum page {max_page}")
                        return (True, max_page, None)
                    else:
                        return (False, None, "No valid pages found in source mapping")
                else:
                    return (False, None, "Invalid page mapping format")
            else:
                return (False, None, f"File {file_id} not found in source mapping")
        
        # If no source_mapping, log warning but assume valid (can't validate)
        logger.warning(f"Cannot validate page {page_number} for file {file_id}: no source_mapping provided")
        return (True, None, None)
    
    def create_entity_source_with_validation(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        entity_type: str,
        entity_id: str,
        chunk_id: Optional[str] = None,
        file_id: Optional[str] = None,
        page_number: Optional[int] = None,
        bbox: Optional[Dict[str, float]] = None,
        snippet: Optional[str] = None,
        full_text: Optional[str] = None,
        source_mapping: Optional[Dict] = None,
    ) -> Tuple[Optional[EntitySource], Optional[str]]:
        """
        Create entity source with page number validation.
        
        Returns:
            (entity_source, error_message) tuple
        """
        # Validate page number if file_id and page_number are provided
        if file_id and page_number is not None:
            is_valid, max_page, error_msg = self.validate_page_number(
                db, file_id, page_number, source_mapping
            )
            if not is_valid:
                logger.warning(f"Invalid page number for {entity_type}:{entity_id}: {error_msg}")
                return (None, error_msg)
        
        # Create entity source
        try:
            entity_source = self.create_entity_source(
                db=db,
                case_id=case_id,
                user_id=user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                chunk_id=chunk_id,
                file_id=file_id,
                page_number=page_number,
                bbox=bbox,
                snippet=snippet,
                full_text=full_text,
            )
            return (entity_source, None)
        except Exception as e:
            logger.error(f"Failed to create entity source for {entity_type}:{entity_id}: {e}")
            return (None, str(e))

