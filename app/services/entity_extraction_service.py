"""Service for extracting entities with temporal grounding"""

import logging
import uuid
import re
from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.entity import Entity
from app.models.entity_source import EntitySource
from app.models.normalized_page import NormalizedPage
from app.services.page_service import page_service

logger = logging.getLogger(__name__)


class EntityExtractionService:
    """
    Service for extracting entities and grounding them to specific pages/dates.
    
    Responsibilities:
    1. Process extracted data from ClinicalAgent
    2. Create structured Entity records with temporal anchors
    3. Create EntitySource records linked to NormalizedPages
    4. Update PageTemporalProfile based on extracted entities
    """
    
    async def process_extraction_results(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        extracted_data: Dict,
        extraction_sources: List[Dict]
    ) -> List[Entity]:
        """
        Process extraction results into structured Entities and Sources.
        
        Args:
            db: Database session
            case_id: Case ID
            user_id: User ID
            extracted_data: JSON output from ClinicalAgent
            extraction_sources: RAG source references
            
        Returns:
            List of created Entity objects
        """
        logger.info(f"Processing extraction results for case {case_id}")
        
        all_entities = []
        
        # 1. Process Medications
        meds = await self._process_medications(
            db, case_id, user_id, extracted_data.get("medications", []), extraction_sources
        )
        all_entities.extend(meds)
        
        # 2. Process Labs
        labs = await self._process_labs(
            db, case_id, user_id, extracted_data.get("labs", []), extraction_sources
        )
        all_entities.extend(labs)
        
        # 3. Process Diagnoses
        dxs = await self._process_diagnoses(
            db, case_id, user_id, extracted_data.get("diagnoses", []), extraction_sources
        )
        all_entities.extend(dxs)
        
        # 4. Update temporal profiles for pages
        # First flush to get IDs and links established
        db.flush()
        
        # Then update profiles
        self._update_page_temporal_profiles(db, all_entities)
        
        return all_entities
    
    async def _process_medications(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        medications: List[Dict],
        sources: List[Dict]
    ) -> List[Entity]:
        """Process medication entities"""
        entities = []
        
        for idx, med in enumerate(medications):
            # Handle both dict and string formats
            if isinstance(med, str):
                name = med
                med_dict = {"name": med}
            else:
                name = med.get("name", "")
                med_dict = med
                
            if not name:
                continue
                
            # Extract temporal anchor
            entity_date = self._parse_date(med_dict.get("start_date") or med_dict.get("date"))
            
            # Create Entity
            entity_id = str(uuid.uuid4())
            entity = Entity(
                entity_id=entity_id,
                case_id=case_id,
                user_id=user_id,
                entity_type="medication",
                value=name,
                normalized_value=name.strip().title(), # Simple normalization
                entity_date=entity_date,
                confidence=0.9, # Placeholder
                entity_metadata={
                    "dosage": med_dict.get("dosage"),
                    "route": med_dict.get("route"),
                    "frequency": med_dict.get("frequency"),
                    "status": med_dict.get("status")
                }
            )
            db.add(entity)
            entities.append(entity)
            
            # Find best source
            matched_source = self._find_best_source(sources, "medication", idx, name)
            if matched_source:
                self._create_entity_source(db, entity, matched_source)
                
        return entities

    async def _process_labs(
        self,
        db: Session, 
        case_id: str,
        user_id: str,
        labs: List[Dict],
        sources: List[Dict]
    ) -> List[Entity]:
        """Process lab entities"""
        entities = []
        
        for idx, lab in enumerate(labs):
            if isinstance(lab, str):
                name = lab
                lab_dict = {"test_name": lab}
            else:
                name = lab.get("test_name", "")
                lab_dict = lab
                
            if not name:
                continue
                
            entity_date = self._parse_date(lab_dict.get("date"))
            
            entity_id = str(uuid.uuid4())
            entity = Entity(
                entity_id=entity_id,
                case_id=case_id,
                user_id=user_id,
                entity_type="lab",
                value=name,
                normalized_value=name.strip().title(),
                entity_date=entity_date,
                confidence=0.9,
                entity_metadata={
                    "value": lab_dict.get("value"),
                    "unit": lab_dict.get("unit"),
                    "range": lab_dict.get("range"),
                    "flag": lab_dict.get("flag")
                }
            )
            db.add(entity)
            entities.append(entity)
            
            # Find best source
            matched_source = self._find_best_source(sources, "lab", idx, name)
            if matched_source:
                self._create_entity_source(db, entity, matched_source)
                
        return entities

    async def _process_diagnoses(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        diagnoses: List[Dict],
        sources: List[Dict]
    ) -> List[Entity]:
        """Process diagnosis entities"""
        entities = []
        
        for idx, dx in enumerate(diagnoses):
            if isinstance(dx, str):
                name = dx
                dx_dict = {"name": dx}
            else:
                name = dx.get("name", "") or dx.get("condition", "")
                dx_dict = dx
                
            if not name:
                continue
                
            entity_date = self._parse_date(dx_dict.get("date_of_diagnosis") or dx_dict.get("date"))
            
            entity_id = str(uuid.uuid4())
            entity = Entity(
                entity_id=entity_id,
                case_id=case_id,
                user_id=user_id,
                entity_type="diagnosis",
                value=name,
                normalized_value=name.strip().title(),
                entity_date=entity_date,
                confidence=0.9,
                entity_metadata={
                    "status": dx_dict.get("status"),
                    "code": dx_dict.get("code")
                }
            )
            db.add(entity)
            entities.append(entity)
            
            # Find best source
            matched_source = self._find_best_source(sources, "diagnosis", idx, name)
            if matched_source:
                self._create_entity_source(db, entity, matched_source)
        
        return entities

    def _create_entity_source(self, db: Session, entity: Entity, source_data: Dict):
        """Create EntitySource record linked to NormalizedPage"""
        file_id = source_data.get("file_id")
        page_number = source_data.get("page_number")
        
        # Skip if no valid location data
        if not file_id or page_number is None:
            return

        # Generate page_id reference
        page_id = NormalizedPage.generate_page_id(entity.case_id, file_id, page_number)
        
        # Prepare bbox
        bbox = source_data.get("bbox")
        
        source = EntitySource(
            id=str(uuid.uuid4()),
            case_id=entity.case_id,
            user_id=entity.user_id,
            entity_type=entity.entity_type,
            entity_id=entity.entity_id, 
            chunk_id=source_data.get("chunk_id"),
            file_id=file_id,
            page_number=page_number,
            page_id=page_id,  # CRITICAL: Linking to NormalizedPage
            bbox=bbox,
            snippet=source_data.get("snippet", "")[:500] if source_data.get("snippet") else None,
            created_at=datetime.utcnow()
        )
        db.add(source)

    def _find_best_source(self, sources: List[Dict], type_filter: str, idx: int, name: str) -> Optional[Dict]:
        """Heuristic to find the best source for an entity"""
        # Filter sources by type
        relevant = [s for s in sources if s.get("type") == type_filter]
        
        if not relevant:
            return None
            
        # Strategy 1: Index match (most common/reliable if ordered)
        if idx < len(relevant):
            candidate = relevant[idx]
            # Optional: Check if snippet matches name?
            return candidate
        
        return relevant[0] # Fallback to first source if index out of bounds

    def _parse_date(self, date_val: Any) -> Optional[datetime]:
        """Parse date string to datetime object"""
        if not date_val:
            return None
            
        if isinstance(date_val, datetime):
            return date_val
            
        date_str = str(date_val).strip()
        
        # Try common formats
        formats = [
            "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", 
            "%B %d, %Y", "%b %d, %Y",
            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
                
        # Handle 'YYYY' only
        if re.match(r'^\d{4}$', date_str):
            try:
                return datetime(int(date_str), 1, 1)
            except:
                pass
                
        return None

    def _update_page_temporal_profiles(self, db: Session, entities: List[Entity]):
        """Update PageTemporalProfile for all pages touched by entities"""
        # Map page_id -> list of dates
        page_date_map = {}
        
        # Iterate entities and their sources
        # Since sources might not be committed/refreshed fully, use object traversal
        for entity in entities:
            if not entity.entity_date:
                continue
                
            # Iterate through sources we just added
            # Note: back_populates might not be fully populated if not flushed/committed/refreshed
            # But the session tracks new objects.
            # Safer to inspect the session.new or iterate what we have in hand?
            # We are inside the same transaction, so relationships should work if added to session.
            pass
            
        # Re-query to be safe and update in bulk?
        # Or just update incrementally.
        
        # Optimized approach:
        # Collect (page_id, date) pairs from local entity objects
        # Because sources are linked to entity objects in memory
        pass

        # Since SQLAlchemy relationships might not be populated until flush+refresh,
        # let's assume `_create_entity_source` added them to session.
        # But `entity.sources` might be empty until refresh.
        
        # Workaround: The caller process_extraction_results flushes before calling this.
        # So we can query EntitySource joined with Entity for these entities.
        
        entity_ids = [e.entity_id for e in entities if e.entity_date]
        if not entity_ids:
            return

        # Query all sources for these entities
        results = db.query(EntitySource.page_id, Entity.entity_date).join(
            Entity, EntitySource.entity_id == Entity.entity_id
        ).filter(
            Entity.entity_id.in_(entity_ids),
            EntitySource.page_id.isnot(None)
        ).all()
        
        for page_id, date in results:
            if page_id not in page_date_map:
                page_date_map[page_id] = []
            page_date_map[page_id].append(date)
            
        # Update Profiles
        for page_id, dates in page_date_map.items():
            earliest = min(dates)
            latest = max(dates)
            count = len(dates)
            
            page_service.update_page_temporal_profile(
                db, page_id, earliest, latest, count
            )


entity_extraction_service = EntityExtractionService()
