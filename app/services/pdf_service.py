"""PDF processing and text extraction service"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import PyPDF2
import pdfplumber
import re
import logging
import tempfile
import os

from app.core.config import settings

logger = logging.getLogger(__name__)


class PDFService:
    """Service for PDF processing and text extraction"""

    def _clean_extracted_text(self, text: str) -> str:
        """
        Clean up extracted PDF text to fix common issues:
        - Merge fragmented words split by newlines
        - Fix excessive whitespace
        - Preserve intentional paragraph breaks
        """
        if not text:
            return text
        
        # Replace multiple consecutive newlines with a placeholder
        text = re.sub(r'\n{3,}', '\n\n[PARAGRAPH_BREAK]\n\n', text)
        
        # Replace single newlines that appear to be word breaks
        # (when a line ends with a lowercase letter or common word and next starts with lowercase)
        lines = text.split('\n')
        cleaned_lines = []
        
        i = 0
        while i < len(lines):
            current_line = lines[i].strip()
            
            # Skip empty lines
            if not current_line:
                cleaned_lines.append('')
                i += 1
                continue
            
            # Check if this looks like a fragmented line (single word or very short)
            # and the next line continues the sentence
            merged_line = current_line
            
            while i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                
                # Stop merging if next line is empty (paragraph break)
                if not next_line:
                    break
                
                # Stop merging if next line starts with a section header pattern
                if re.match(r'^[\d]+\.?\s|^[A-Z][A-Z\s]+:|^●|^•|^-\s', next_line):
                    break
                
                # Stop merging if current line ends with sentence-ending punctuation
                if merged_line.endswith(('.', '!', '?', ':')):
                    break
                
                # Check if lines should be merged
                # Merge if: current line is short (< 60 chars) and doesn't end with punctuation
                # or if it looks like a word was split
                should_merge = (
                    len(merged_line) < 60 and 
                    not merged_line.endswith(('.', '!', '?', ':', ';')) and
                    not re.match(r'^[A-Z][A-Z\s]+$', merged_line)  # Not an all-caps header
                )
                
                if should_merge:
                    # Add space between merged lines unless there's already punctuation
                    separator = ' ' if not merged_line.endswith(('-', '/')) else ''
                    merged_line = merged_line + separator + next_line
                    i += 1
                else:
                    break
            
            cleaned_lines.append(merged_line)
            i += 1
        
        # Rejoin lines
        text = '\n'.join(cleaned_lines)
        
        # Restore paragraph breaks
        text = text.replace('[PARAGRAPH_BREAK]', '\n')
        
        # Clean up multiple spaces
        text = re.sub(r' +', ' ', text)
        
        # Clean up multiple newlines (but keep paragraph structure)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    def extract_text_from_pdf(self, pdf_path: str) -> Dict[str, any]:
        """
        Extract text from PDF file
        
        Supports both local paths and S3 keys (starts with "cases/")

        Args:
            pdf_path: Path to PDF file (local path or S3 key)

        Returns:
            Dictionary containing extracted text and metadata
        """
        result = {
            "text": "",
            "pages": [],
            "page_count": 0,
            "extraction_method": "direct",
            "ocr_pages": [],
        }

        # Determine if we should use S3 based on global settings or path patterns
        is_s3_key = (
            settings.STORAGE_TYPE == "s3" or
            pdf_path.startswith("users/") or 
            pdf_path.startswith("cases/")
        )
        temp_file_path = None
        
        try:
            if is_s3_key:
                logger.debug(f"S3 Storage active, downloading: {pdf_path}")
                # Download from S3 to temp file
                from app.services.s3_storage_service import s3_storage_service
                pdf_content = s3_storage_service.get_file_content(pdf_path)
                logger.debug(f"Downloaded {len(pdf_content)} bytes from S3")
                
                # Save to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    tmp_file.write(pdf_content)
                    temp_file_path = tmp_file.name
                
                actual_path = temp_file_path
                logger.debug(f"Saved S3 file to temp path: {actual_path}")
            else:
                actual_path = pdf_path
                if not os.path.exists(actual_path):
                    raise FileNotFoundError(f"Local file not found: {actual_path}")
                logger.debug(f"Using local path: {actual_path}")

            with open(actual_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                result["page_count"] = len(pdf_reader.pages)

                for page_num, page in enumerate(pdf_reader.pages, start=1):
                    # Try direct text extraction
                    raw_text = page.extract_text()
                    
                    # Clean up the extracted text
                    page_text = self._clean_extracted_text(raw_text)

                    # If text is too short or empty, might be scanned/image PDF
                    if len(page_text.strip()) < 50:
                        # Mark for potential OCR
                        result["ocr_pages"].append(page_num)
                        page_text = f"[Page {page_num} may require OCR]"
                        result["extraction_method"] = "mixed"

                    result["pages"].append({
                        "page_number": page_num,
                        "text": page_text,
                        "char_count": len(page_text),
                    })

                    result["text"] += f"\n\n--- Page {page_num} ---\n\n{page_text}"

        except Exception as e:
            logger.error(f"Error extracting text from PDF {pdf_path}: {e}", exc_info=True)
            result["error"] = str(e)
            result["extraction_method"] = "failed"
        finally:
            # Clean up temp file if we created one
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {temp_file_path}: {e}")

        return result

    def extract_text_with_ocr(self, pdf_path: str) -> Dict[str, any]:
        """
        Extract text using OCR (for scanned documents)
        Note: This is a simplified version. Full implementation would use pdf2image

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dictionary containing OCR-extracted text
        """
        result = {
            "text": "",
            "pages": [],
            "page_count": 0,
            "extraction_method": "ocr",
            "ocr_confidence": "medium",
        }

        # TODO: Implement full OCR with pdf2image + pytesseract
        # For MVP, we'll use direct extraction as fallback
        return self.extract_text_from_pdf(pdf_path)

    def count_pages(self, pdf_path: str) -> int:
        """Get page count from PDF
        
        Supports both local paths and S3 keys (starts with "users/" or "cases/")
        """
        # Determine if we should use S3 based on global settings or path patterns
        is_s3_key = (
            settings.STORAGE_TYPE == "s3" or
            pdf_path.startswith("users/") or 
            pdf_path.startswith("cases/")
        )
        temp_file_path = None
        
        try:
            if is_s3_key:
                # Download from S3 to temp file
                from app.services.s3_storage_service import s3_storage_service
                pdf_content = s3_storage_service.get_file_content(pdf_path)
                
                # Save to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    tmp_file.write(pdf_content)
                    temp_file_path = tmp_file.name
                
                actual_path = temp_file_path
            else:
                actual_path = pdf_path
            
            with open(actual_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                return len(pdf_reader.pages)
        except Exception as e:
            logger.error(f"Error counting pages in {pdf_path}: {e}", exc_info=True)
            return 0
        finally:
            # Clean up temp file if we created one
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {temp_file_path}: {e}")

    def extract_metadata(self, pdf_path: str) -> Dict[str, any]:
        """Extract PDF metadata
        
        Supports both local paths and S3 keys (starts with "users/" or "cases/")
        """
        # Determine if we should use S3 based on global settings or path patterns
        is_s3_key = (
            settings.STORAGE_TYPE == "s3" or
            pdf_path.startswith("users/") or 
            pdf_path.startswith("cases/")
        )
        temp_file_path = None
        metadata = {}
        
        try:
            if is_s3_key:
                # Download from S3 to temp file
                from app.services.s3_storage_service import s3_storage_service
                pdf_content = s3_storage_service.get_file_content(pdf_path)
                
                # Save to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    tmp_file.write(pdf_content)
                    temp_file_path = tmp_file.name
                
                actual_path = temp_file_path
            else:
                actual_path = pdf_path
            
            with open(actual_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                if pdf_reader.metadata:
                    metadata = {
                        "title": pdf_reader.metadata.get("/Title", ""),
                        "author": pdf_reader.metadata.get("/Author", ""),
                        "subject": pdf_reader.metadata.get("/Subject", ""),
                        "creator": pdf_reader.metadata.get("/Creator", ""),
                    }
        except Exception:
            pass
        finally:
            # Clean up temp file if we created one
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {temp_file_path}: {e}")
        
        return metadata

    def extract_text_with_coordinates(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract text from PDF with bounding box coordinates using pdfplumber
        
        This is the preferred method for precise highlighting as it provides
        exact text positions on the page.
        
        Args:
            pdf_path: Path to PDF file (local path or S3 key)
            
        Returns:
            Dictionary containing extracted text with bbox coordinates per page
        """
        result = {
            "text": "",
            "pages": [],
            "page_count": 0,
            "extraction_method": "pdfplumber",
            "ocr_pages": [],
        }
        
        # Determine if we should use S3 based on global settings or path patterns
        is_s3_key = (
            settings.STORAGE_TYPE == "s3" or
            pdf_path.startswith("users/") or 
            pdf_path.startswith("cases/")
        )
        temp_file_path = None
        
        try:
            if is_s3_key:
                logger.debug(f"S3 Storage active, downloading: {pdf_path}")
                # Download from S3 to temp file
                from app.services.s3_storage_service import s3_storage_service
                pdf_content = s3_storage_service.get_file_content(pdf_path)
                logger.debug(f"Downloaded {len(pdf_content)} bytes from S3")
                
                # Save to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    tmp_file.write(pdf_content)
                    temp_file_path = tmp_file.name
                
                actual_path = temp_file_path
                logger.debug(f"Saved S3 file to temp path: {actual_path}")
            else:
                actual_path = pdf_path
                if not os.path.exists(actual_path):
                    raise FileNotFoundError(f"Local file not found: {actual_path}")
                logger.debug(f"Using local path: {actual_path}")
            
            with pdfplumber.open(actual_path) as pdf:
                result["page_count"] = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages, start=1):
                    # Extract text with words (which include bbox)
                    words = page.extract_words()
                    chars = page.chars  # Character-level coordinates
                    
                    # Build text from words
                    page_text = page.extract_text() or ""
                    cleaned_text = self._clean_extracted_text(page_text)
                    
                    # If text is too short, might be scanned/image PDF
                    if len(cleaned_text.strip()) < 50:
                        result["ocr_pages"].append(page_num)
                        result["extraction_method"] = "mixed"
                    
                    # Build text segments with coordinates
                    text_segments = []
                    char_pos = 0
                    
                    for word in words:
                        if word.get('text'):
                            text_segments.append({
                                "text": word['text'],
                                "bbox": {
                                    "x0": word.get('x0', 0),
                                    "y0": word.get('top', 0),  # pdfplumber uses 'top' for y0
                                    "x1": word.get('x1', 0),
                                    "y1": word.get('bottom', 0),  # pdfplumber uses 'bottom' for y1
                                },
                                "char_start": char_pos,
                                "char_end": char_pos + len(word['text'])
                            })
                            char_pos += len(word['text']) + 1  # +1 for space
                    
                    # Store character-level coordinates for precise highlighting
                    char_coordinates = []
                    for char in chars:
                        if char.get('text'):
                            char_coordinates.append({
                                "char": char['text'],
                                "bbox": {
                                    "x0": char.get('x0', 0),
                                    "y0": char.get('top', 0),
                                    "x1": char.get('x1', 0),
                                    "y1": char.get('bottom', 0),
                                }
                            })
                    
                    result["pages"].append({
                        "page_number": page_num,
                        "text": cleaned_text,
                        "char_count": len(cleaned_text),
                        "text_segments": text_segments,  # Word-level bbox
                        "char_coordinates": char_coordinates,  # Character-level bbox for precise highlighting
                    })
                    
                    result["text"] += f"\n\n--- Page {page_num} ---\n\n{cleaned_text}"
                    
        except Exception as e:
            logger.error(f"Error extracting text with coordinates from PDF {pdf_path}: {e}", exc_info=True)
            result["error"] = str(e)
            result["extraction_method"] = "failed"
            # Fallback to basic extraction
            return self.extract_text_from_pdf(pdf_path)
        finally:
            # Clean up temp file if we created one
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {temp_file_path}: {e}")
        
        return result


# Singleton instance
pdf_service = PDFService()

