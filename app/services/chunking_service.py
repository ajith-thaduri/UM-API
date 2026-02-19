"""Medical-aware document chunking service"""

import re
import uuid
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
import tiktoken
import logging

from app.core.config import settings
from app.models.document_chunk import SectionType

logger = logging.getLogger(__name__)


@dataclass
class ChunkData:
    """Data structure for a document chunk"""
    chunk_text: str
    page_number: int
    section_type: SectionType
    char_start: int
    char_end: int
    token_count: int
    chunk_index: int
    vector_id: str
    file_id: str
    bbox: Optional[Dict[str, float]] = None  # Bounding box: {"x0": float, "y0": float, "x1": float, "y1": float}


class ChunkingService:
    """Document chunking service - simplified without section detection"""

    def __init__(self):
        self.tokenizer = tiktoken.encoding_for_model("gpt-4")
        self.chunk_size = settings.CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP  # Now token-based

    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.tokenizer.encode(text))

    def chunk_page_text(
        self,
        text: str,
        page_number: int,
        file_id: str,
        case_id: str,
        start_chunk_index: int = 0
    ) -> List[ChunkData]:
        """Chunk a single page's text - all chunks are treated as UNKNOWN type"""
        chunks = []
        
        if not text or not text.strip():
            return chunks
        
        # Split entire page into chunks without section detection
        section_chunks = self._split_into_chunks(
            text,
            page_number,
            SectionType.UNKNOWN,  # All chunks use UNKNOWN type (no section classification)
            0,  # base_char_start
            file_id,
            case_id,
            start_chunk_index
        )
        chunks.extend(section_chunks)
        
        return chunks

    def _split_into_chunks(
        self,
        text: str,
        page_number: int,
        section_type: SectionType,
        base_char_start: int,
        file_id: str,
        case_id: str,
        start_index: int
    ) -> List[ChunkData]:
        """Split text into chunks of appropriate size"""
        chunks = []
        
        token_count = self.count_tokens(text)
        
        # If text fits in one chunk, return as-is
        if token_count <= self.chunk_size:
            chunk_data = ChunkData(
                chunk_text=text.strip(),
                page_number=page_number,
                section_type=section_type,
                char_start=base_char_start,
                char_end=base_char_start + len(text),
                token_count=token_count,
                chunk_index=start_index,
                vector_id=f"{case_id}_{file_id}_{page_number}_{start_index}",
                file_id=file_id
            )
            return [chunk_data]
        
        # Split into smaller chunks
        sentences = self._split_into_sentences(text)
        current_chunk = []
        current_tokens = 0
        char_pos = 0
        chunk_start = 0
        
        for sentence in sentences:
            sentence_tokens = self.count_tokens(sentence)
            
            # If single sentence exceeds chunk size, force split
            if sentence_tokens > self.chunk_size:
                # Save current chunk first
                if current_chunk:
                    chunk_text = ' '.join(current_chunk)
                    chunks.append(ChunkData(
                        chunk_text=chunk_text.strip(),
                        page_number=page_number,
                        section_type=section_type,
                        char_start=base_char_start + chunk_start,
                        char_end=base_char_start + char_pos,
                        token_count=current_tokens,
                        chunk_index=start_index + len(chunks),
                        vector_id=f"{case_id}_{file_id}_{page_number}_{start_index + len(chunks)}",
                        file_id=file_id
                    ))
                    current_chunk = []
                    current_tokens = 0
                    chunk_start = char_pos
                
                # Force split the long sentence
                words = sentence.split()
                temp_chunk = []
                temp_tokens = 0
                
                for word in words:
                    word_tokens = self.count_tokens(word + ' ')
                    if temp_tokens + word_tokens > self.chunk_size and temp_chunk:
                        chunk_text = ' '.join(temp_chunk)
                        chunks.append(ChunkData(
                            chunk_text=chunk_text.strip(),
                            page_number=page_number,
                            section_type=section_type,
                            char_start=base_char_start + chunk_start,
                            char_end=base_char_start + chunk_start + len(chunk_text),
                            token_count=temp_tokens,
                            chunk_index=start_index + len(chunks),
                            vector_id=f"{case_id}_{file_id}_{page_number}_{start_index + len(chunks)}",
                            file_id=file_id
                        ))
                        chunk_start += len(chunk_text) + 1
                        temp_chunk = []
                        temp_tokens = 0
                    temp_chunk.append(word)
                    temp_tokens += word_tokens
                
                if temp_chunk:
                    current_chunk = temp_chunk
                    current_tokens = temp_tokens
                
                char_pos += len(sentence) + 1
                continue
            
            # Check if adding sentence exceeds chunk size
            if current_tokens + sentence_tokens > self.chunk_size and current_chunk:
                chunk_text = ' '.join(current_chunk)
                chunks.append(ChunkData(
                    chunk_text=chunk_text.strip(),
                    page_number=page_number,
                    section_type=section_type,
                    char_start=base_char_start + chunk_start,
                    char_end=base_char_start + char_pos,
                    token_count=current_tokens,
                    chunk_index=start_index + len(chunks),
                    vector_id=f"{case_id}_{file_id}_{page_number}_{start_index + len(chunks)}",
                    file_id=file_id
                ))
                
                # Start new chunk with overlap (token-based)
                overlap_sentences = self._get_overlap_sentences(current_chunk, self.chunk_overlap)
                current_chunk = overlap_sentences
                current_tokens = self.count_tokens(' '.join(current_chunk))
                # Calculate character position for overlap
                overlap_text = ' '.join(overlap_sentences)
                chunk_start = char_pos - len(overlap_text) if overlap_text else char_pos
            
            current_chunk.append(sentence)
            current_tokens += sentence_tokens
            char_pos += len(sentence) + 1
        
        # Don't forget the last chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            chunks.append(ChunkData(
                chunk_text=chunk_text.strip(),
                page_number=page_number,
                section_type=section_type,
                char_start=base_char_start + chunk_start,
                char_end=base_char_start + char_pos,
                token_count=self.count_tokens(chunk_text),
                chunk_index=start_index + len(chunks),
                vector_id=f"{case_id}_{file_id}_{page_number}_{start_index + len(chunks)}",
                file_id=file_id
            ))
        
        return chunks

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Medical-aware sentence splitting
        # Handle common abbreviations that shouldn't split
        # Protect single-letter abbreviations like B.P., U.S., etc.
        text = re.sub(r'\b([A-Z])\.', r'\1<ABBR>', text)
        
        # Handle common medical titles and abbreviations
        abbreviations = ["Dr", "Mr", "Mrs", "Ms", "St", "No", "Vs", "p.p", "p.f"]
        for abbr in abbreviations:
            text = re.sub(r'\b' + abbr + r'\.', abbr + '<ABBR>', text, flags=re.IGNORECASE)
            
        text = re.sub(r'(?<=\d)\.(?=\d)', '<DECIMAL>', text)  # Handle decimals
        
        # Split on sentence boundaries (period, exclamation, or question mark followed by space)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Restore abbreviations and decimals
        sentences = [s.replace('<ABBR>', '.').replace('<DECIMAL>', '.') for s in sentences]
        
        # Also split on newlines for medical records
        final_sentences = []
        for sentence in sentences:
            if '\n' in sentence:
                parts = [p.strip() for p in sentence.split('\n') if p.strip()]
                final_sentences.extend(parts)
            else:
                final_sentences.append(sentence)
        
        return [s for s in final_sentences if s.strip()]

    def _get_overlap_sentences(self, sentences: List[str], overlap_tokens: int) -> List[str]:
        """Get sentences for overlap from end of chunk (token-based)"""
        if not sentences:
            return []
        
        overlap = []
        token_count = 0
        
        for sentence in reversed(sentences):
            sentence_tokens = self.count_tokens(sentence)
            if token_count + sentence_tokens > overlap_tokens:
                break
            overlap.insert(0, sentence)
            token_count += sentence_tokens
        
        return overlap

    def chunk_document(
        self,
        file_page_mapping: Dict[int, str],
        file_id: str,
        case_id: str
    ) -> List[ChunkData]:
        """Chunk an entire document from page mapping"""
        all_chunks = []
        chunk_index = 0
        
        for page_number in sorted(file_page_mapping.keys()):
            page_text = file_page_mapping[page_number]
            
            page_chunks = self.chunk_page_text(
                text=page_text,
                page_number=page_number,
                file_id=file_id,
                case_id=case_id,
                start_chunk_index=chunk_index
            )
            
            all_chunks.extend(page_chunks)
            chunk_index += len(page_chunks)
        
        logger.info(f"Created {len(all_chunks)} chunks for file {file_id}")
        return all_chunks

    def chunk_page_with_bbox(
        self,
        text: str,
        text_segments: List[Dict[str, Any]],
        page_number: int,
        file_id: str,
        case_id: str,
        start_chunk_index: int = 0
    ) -> List[ChunkData]:
        """
        Chunk a page's text while preserving bbox coordinates
        
        Args:
            text: Full page text
            text_segments: List of text segments with bbox from pdfplumber
            page_number: Page number
            file_id: File ID
            case_id: Case ID
            start_chunk_index: Starting chunk index
            
        Returns:
            List of ChunkData with bbox coordinates
        """
        # First, chunk the text normally
        chunks = self.chunk_page_text(
            text=text,
            page_number=page_number,
            file_id=file_id,
            case_id=case_id,
            start_chunk_index=start_chunk_index
        )
        
        # Now map bbox coordinates to chunks
        # Build a mapping from char position to bbox
        char_to_bbox = {}
        char_pos = 0
        for segment in text_segments:
            segment_text = segment.get("text", "")
            bbox = segment.get("bbox", {})
            if bbox and segment_text:
                for i in range(len(segment_text)):
                    char_to_bbox[char_pos + i] = bbox
                char_pos += len(segment_text) + 1  # +1 for space
        
        # Assign bbox to each chunk
        for chunk in chunks:
            # Find bbox for the chunk by looking at char positions
            chunk_bboxes = []
            for char_pos in range(chunk.char_start, min(chunk.char_end, len(char_to_bbox) + chunk.char_start)):
                if char_pos in char_to_bbox:
                    chunk_bboxes.append(char_to_bbox[char_pos])
            
            if chunk_bboxes:
                # Calculate union bbox (min x0/y0, max x1/y1)
                x0 = min(bbox.get("x0", 0) for bbox in chunk_bboxes)
                y0 = min(bbox.get("y0", 0) for bbox in chunk_bboxes)
                x1 = max(bbox.get("x1", 0) for bbox in chunk_bboxes)
                y1 = max(bbox.get("y1", 0) for bbox in chunk_bboxes)
                chunk.bbox = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
            else:
                # Fallback: use first segment's bbox if available
                if text_segments:
                    first_bbox = text_segments[0].get("bbox")
                    if first_bbox:
                        chunk.bbox = first_bbox
        
        return chunks


# Singleton instance
chunking_service = ChunkingService()

