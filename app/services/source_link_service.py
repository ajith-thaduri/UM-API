"""Service to resolve and register source links for facets with chunk support."""
import uuid
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
import logging

from app.models.dashboard import FacetResult, SourceLink, FacetType
from app.models.document_chunk import DocumentChunk
from app.repositories.source_link_repository import SourceLinkRepository
from app.repositories.chunk_repository import chunk_repository

logger = logging.getLogger(__name__)


class SourceLinkService:
    """Maps facet items to file/page sources and chunks for the dashboard."""

    def __init__(self, source_link_repository: SourceLinkRepository):
        self.source_link_repository = source_link_repository

    def sync_links_for_facet(
        self, db: Session, facet: FacetResult, extraction_source_mapping: Optional[Dict]
    ) -> List[SourceLink]:
        """Create normalized links from facet content when source data is available."""
        if not extraction_source_mapping:
            return []

        links: List[SourceLink] = []
        files_lookup = {}
        files = extraction_source_mapping.get("files", []) or []
        for file_info in files:
            if isinstance(file_info, dict) and file_info.get("id"):
                files_lookup[file_info["file_name"]] = file_info["id"]

        # Get extraction sources (from RAG) if available
        extraction_sources = extraction_source_mapping.get("extraction_sources", [])
        chunk_lookup = self._build_chunk_lookup(extraction_sources)

        def add_link(
            item_id: str,
            source_file: Optional[str],
            source_page: Optional[int],
            snippet: Optional[str] = None,
            chunk_id: Optional[str] = None,
        ):
            # Normalize source_page: convert invalid values to None
            if source_page is not None:
                # If it's a string like "Not specified", convert to None
                if isinstance(source_page, str):
                    if source_page.lower() in ("not specified", "none", "null", ""):
                        source_page = None
                    else:
                        # Try to convert string to integer
                        try:
                            source_page = int(source_page)
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid source_page value '{source_page}' for item {item_id}, converting to None")
                            source_page = None
                # If it's not an integer, convert to None
                elif not isinstance(source_page, int):
                    logger.warning(f"Invalid source_page type {type(source_page)} for item {item_id}, converting to None")
                    source_page = None
            
            # Normalize source_file: convert "Not specified" to None
            if source_file and isinstance(source_file, str):
                if source_file.lower() in ("not specified", "none", "null"):
                    source_file = None
            
            if not source_file and not source_page and not chunk_id:
                return
                
            file_id = files_lookup.get(source_file) if source_file else None
            page_mapping = (
                extraction_source_mapping.get("file_page_mapping", {}).get(file_id, {})
                if file_id
                else {}
            )
            page_text = ""
            if isinstance(page_mapping, dict) and source_page:
                page_text = page_mapping.get(source_page, "")

            link = SourceLink(
                id=str(uuid.uuid4()),
                case_id=facet.case_id,
                case_version_id=facet.case_version_id,
                user_id=facet.user_id,
                facet_id=facet.id,
                item_id=item_id,
                file_id=file_id,
                file_name=source_file,
                page_number=source_page,
                snippet=snippet or (page_text[:500] if page_text else None),
                full_text=page_text or None,
                chunk_id=chunk_id,
            )
            db.add(link)
            links.append(link)

        # Apply to known content shapes
        content = facet.content or {}
        if facet.facet_type == FacetType.CLINICAL:
            # Process medications
            for idx, med in enumerate(content.get("medications", []) or []):
                chunk_id = self._find_chunk_for_item(chunk_lookup, "medication", idx)
                add_link(
                    f"medication:{idx}",
                    med.get("source_file"),
                    med.get("source_page"),
                    chunk_id=chunk_id
                )
            
            # Process labs
            for idx, lab in enumerate(content.get("labs", []) or []):
                chunk_id = self._find_chunk_for_item(chunk_lookup, "lab", idx)
                add_link(
                    f"lab:{idx}",
                    lab.get("source_file"),
                    lab.get("source_page"),
                    chunk_id=chunk_id
                )
            
            # Process diagnoses
            diagnoses = content.get("diagnoses", []) or []
            for idx, dx in enumerate(diagnoses):
                if isinstance(dx, dict):
                    chunk_id = self._find_chunk_for_item(chunk_lookup, "diagnosis", idx)
                    add_link(
                        f"diagnosis:{idx}",
                        dx.get("source_file"),
                        dx.get("source_page"),
                        chunk_id=chunk_id
                    )
            
            # Process procedures
            for idx, proc in enumerate(content.get("procedures", []) or []):
                chunk_id = self._find_chunk_for_item(chunk_lookup, "procedure", idx)
                add_link(
                    f"procedure:{idx}",
                    proc.get("source_file"),
                    proc.get("source_page"),
                    chunk_id=chunk_id
                )
            
            # Process vitals
            for idx, vital in enumerate(content.get("vitals", []) or []):
                chunk_id = self._find_chunk_for_item(chunk_lookup, "vital", idx)
                add_link(
                    f"vital:{idx}",
                    vital.get("source_file"),
                    vital.get("source_page"),
                    chunk_id=chunk_id
                )
            
            # Process imaging
            for idx, img in enumerate(content.get("imaging", []) or []):
                chunk_id = self._find_chunk_for_item(chunk_lookup, "imaging", idx)
                add_link(
                    f"imaging:{idx}",
                    img.get("source_file"),
                    img.get("source_page"),
                    chunk_id=chunk_id
                )
            
            # Process allergies
            for idx, allergy in enumerate(content.get("allergies", []) or []):
                chunk_id = self._find_chunk_for_item(chunk_lookup, "allergy", idx)
                if isinstance(allergy, dict):
                    add_link(
                        f"allergy:{idx}",
                        allergy.get("source_file"),
                        allergy.get("source_page"),
                        chunk_id=chunk_id
                    )
                else:
                    add_link(f"allergy:{idx}", None, None, chunk_id=chunk_id)
                    
        elif facet.facet_type == FacetType.TIMELINE:
            for idx, item in enumerate(content or []):
                if isinstance(item, dict):
                    details = item.get("details", {})
                    add_link(
                        item.get("id", f"timeline:{idx}"),
                        details.get("source_file") if isinstance(details, dict) else None,
                        details.get("source_page") if isinstance(details, dict) else None
                    )
                    
        elif facet.facet_type == FacetType.CONTRADICTIONS:
            for contradiction in content or []:
                for source in contradiction.get("sources", []) or []:
                    add_link(
                        contradiction.get("id", ""),
                        source.get("file"),
                        source.get("page")
                    )
                    
        elif facet.facet_type == FacetType.RED_FLAGS:
            for rf in content or []:
                add_link(
                    rf.get("id", ""),
                    rf.get("source_file"),
                    rf.get("source_page")
                )

        db.commit()
        return links

    def _build_chunk_lookup(self, extraction_sources: List[Dict]) -> Dict[str, str]:
        """Build lookup from source type+index to chunk_id"""
        lookup = {}
        for source in extraction_sources:
            source_type = source.get("type", "")
            chunk_id = source.get("chunk_id")
            if source_type and chunk_id:
                # Store by type for later matching
                if source_type not in lookup:
                    lookup[source_type] = []
                lookup[source_type].append(chunk_id)
        return lookup

    def _find_chunk_for_item(
        self,
        chunk_lookup: Dict[str, List[str]],
        item_type: str,
        index: int
    ) -> Optional[str]:
        """Find the most relevant chunk for an item"""
        chunks = chunk_lookup.get(item_type, [])
        if chunks and index < len(chunks):
            return chunks[index]
        elif chunks:
            return chunks[0]  # Return first chunk if index out of range
        return None

    def get_source_for_item(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        facet_type: str,
        item_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get source information for a specific item
        
        Args:
            db: Database session
            case_id: Case ID
            user_id: User ID for scoping
            facet_type: Type of facet
            item_id: Item identifier
            
        Returns:
            Source information dict or None
        """
        # Try to find existing source link
        links = self.source_link_repository.list_for_case(db, case_id, user_id)
        link = next((l for l in links if l.item_id == item_id), None)
        
        if link:
            result = {
                "file_name": link.file_name,
                "file_id": link.file_id,
                "page": link.page_number,
                "snippet": link.snippet,
                "full_text": link.full_text,
            }
            
            # If we have a chunk_id, get chunk details including bbox
            if link.chunk_id:
                chunk = chunk_repository.get_by_id(db, link.chunk_id)
                if chunk:
                    result["chunk"] = {
                        "id": chunk.id,
                        "vector_id": chunk.vector_id,
                        "text": chunk.chunk_text,
                        "section_type": chunk.section_type.value,
                        "char_start": chunk.char_start,
                        "char_end": chunk.char_end,
                        "page_number": chunk.page_number,
                        "bbox": chunk.bbox  # Include bbox for precise highlighting
                    }
                    # Also add bbox to top level for easier access
                    if chunk.bbox:
                        result["bbox"] = chunk.bbox
            
            return result
        
        return None

    def get_chunk_source(
        self,
        db: Session,
        chunk_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get source information from a chunk
        
        Args:
            db: Database session
            chunk_id: Chunk ID
            
        Returns:
            Chunk source information
        """
        chunk = chunk_repository.get_by_id(db, chunk_id)
        if not chunk:
            return None
        
        return {
            "chunk_id": chunk.id,
            "vector_id": chunk.vector_id,
            "case_id": chunk.case_id,
            "file_id": chunk.file_id,
            "page_number": chunk.page_number,
            "section_type": chunk.section_type.value,
            "text": chunk.chunk_text,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "token_count": chunk.token_count,
            "bbox": chunk.bbox  # Include bbox for precise highlighting
        }

    def get_chunk_by_vector_id(
        self,
        db: Session,
        vector_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get chunk source by vector ID
        
        Args:
            db: Database session
            vector_id: Vector database ID (FAISS)
            
        Returns:
            Chunk source information
        """
        chunk = chunk_repository.get_by_vector_id(db, vector_id)
        if not chunk:
            return None
        
        return self.get_chunk_source(db, chunk.id)


def build_source_link_service() -> SourceLinkService:
    return SourceLinkService(SourceLinkRepository())
