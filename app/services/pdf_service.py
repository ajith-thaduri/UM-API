"""PDF processing and text extraction service"""

from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import json
import PyPDF2
import pdfplumber
import re
import logging
import tempfile
import os
import time

from app.core.config import settings

logger = logging.getLogger(__name__)

# #region agent log
def _debug_log(message: str, data: dict, hypothesis_id: str = ""):
    try:
        payload = {"sessionId": "4b4b91", "location": "pdf_service.py", "message": message, "data": data, "timestamp": int(time.time() * 1000)}
        if hypothesis_id:
            payload["hypothesisId"] = hypothesis_id
        with open("/Users/ajiththaduri/Desktop/V2/.cursor/debug-4b4b91.log", "a") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
# #endregion


def _run_ocr_for_page(
    actual_path: str,
    page_number: int,
    engine_hint: Optional[str] = None,
) -> Optional[Tuple[str, List[Dict], float, str, Dict[str, Any]]]:
    """
    Run OCR on one PDF page. Returns (page_text, text_segments, page_confidence, engine_used, hybrid_stats)
    or None if OCR is disabled or fails. text_segments are in PDF-space (same shape as pdfplumber).
    engine_hint: optional engine id (e.g. tesseract, ppstructure) for lab/testing.
    """
    # #region agent log
    _debug_log("OCR for page entry", {"actual_path": actual_path, "page_number": page_number, "file_exists": os.path.isfile(actual_path) if actual_path else False}, "A")
    # #endregion
    if not getattr(settings, "OCR_ENABLED", True):
        # #region agent log
        _debug_log("OCR disabled", {"page_number": page_number}, "A")
        # #endregion
        return None
    service_url = (getattr(settings, "OCR_SERVICE_URL", None) or "").strip()
    if not service_url:
        logger.debug("OCR_SERVICE_URL not set, skipping OCR for page %s", page_number)
        return None
    try:
        from app.services.ocr import rasterize_pdf_page, map_segments_to_pdf
        from app.services.ocr.ocr_service_client import ocr_process_page
    except ImportError as e:
        # #region agent log
        _debug_log("OCR import failed", {"page_number": page_number, "error": str(e)}, "A")
        # #endregion
        logger.debug("OCR package not available, skipping OCR for page %s", page_number)
        return None
    try:
        pil_image, page_width_pt, page_height_pt = rasterize_pdf_page(actual_path, page_number)
        timeout = getattr(settings, "OCR_SERVICE_TIMEOUT", 120) or 120
        _ocr_start = time.perf_counter()
        page_text, raw_segments, page_confidence, engine_used, w_px, h_px, hybrid_stats = ocr_process_page(
            pil_image, page_number, service_url, timeout_seconds=float(timeout), engine_hint=engine_hint
        )
        _ocr_elapsed_ms = (time.perf_counter() - _ocr_start) * 1000
        logger.debug(
            "OCR page: page_number=%s extraction_mode=ocr engine_used=%s processing_time_ms=%.0f",
            page_number,
            engine_used,
            _ocr_elapsed_ms,
        )
        if page_text is None or not page_text:
            # #region agent log
            _debug_log("OCR returned no text", {"page_number": page_number, "text_len": len(page_text or "")}, "A")
            # #endregion
            return None
        if w_px <= 0 or h_px <= 0:
            w_px, h_px = pil_image.size[0], pil_image.size[1]
        segments = map_segments_to_pdf(w_px, h_px, page_width_pt, page_height_pt, raw_segments)
        text_segments = [s.to_dict() for s in segments]
        # #region agent log
        _debug_log("OCR success", {"page_number": page_number, "segment_count": len(text_segments), "engine": engine_used}, "A")
        # #endregion
        return (page_text, text_segments, page_confidence, engine_used or "ocr_service", hybrid_stats)
    except Exception as e:
        # #region agent log
        _debug_log("OCR exception", {"page_number": page_number, "error": str(e)}, "A")
        # #endregion
        logger.warning("OCR failed for page %s: %s", page_number, e)
        return None


class PDFService:
    """Service for PDF processing and text extraction"""

    def _build_segments_from_chars(self, chars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Build coarse text segments from character boxes when pdfplumber.extract_words()
        returns nothing for a page that still has native text.
        """
        segments: List[Dict[str, Any]] = []
        current_chars: List[Dict[str, Any]] = []
        char_pos = 0

        def flush_current() -> None:
            nonlocal current_chars, char_pos
            if not current_chars:
                return
            text = "".join((c.get("text") or "") for c in current_chars).strip()
            if not text:
                current_chars = []
                return
            x0 = min(float(c.get("x0", 0)) for c in current_chars)
            top = min(float(c.get("top", 0)) for c in current_chars)
            x1 = max(float(c.get("x1", 0)) for c in current_chars)
            bottom = max(float(c.get("bottom", 0)) for c in current_chars)
            segments.append({
                "text": text,
                "bbox": {
                    "x0": x0,
                    "y0": top,
                    "x1": x1,
                    "y1": bottom,
                },
                "char_start": char_pos,
                "char_end": char_pos + len(text),
            })
            char_pos += len(text) + 1
            current_chars = []

        for char in chars:
            text = char.get("text") or ""
            if not text or text.isspace():
                flush_current()
                continue
            current_chars.append(char)

        flush_current()
        return segments

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

        # Use S3 only when storage is S3 and path is an S3 key (users/... or cases/...).
        # Local paths (e.g. temp files from OCR Lab) must be read from disk even when STORAGE_TYPE is s3.
        is_s3_key = (
            settings.STORAGE_TYPE == "s3"
            and (pdf_path.startswith("users/") or pdf_path.startswith("cases/"))
            and not os.path.isabs(pdf_path)
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
        is_s3_key = (
            settings.STORAGE_TYPE == "s3"
            and (pdf_path.startswith("users/") or pdf_path.startswith("cases/"))
            and not os.path.isabs(pdf_path)
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
        is_s3_key = (
            settings.STORAGE_TYPE == "s3"
            and (pdf_path.startswith("users/") or pdf_path.startswith("cases/"))
            and not os.path.isabs(pdf_path)
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

    def extract_text_with_coordinates(
        self,
        pdf_path: str,
        ocr_engine_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Extract text from PDF with bounding box coordinates using pdfplumber

        This is the preferred method for precise highlighting as it provides
        exact text positions on the page.

        Args:
            pdf_path: Path to PDF file (local path or S3 key)
            ocr_engine_hint: Optional engine id (e.g. tesseract, ppstructure) for OCR pages (e.g. from OCR Lab).

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
        
        # Use S3 only when storage is S3 and path is an S3 key (users/... or cases/...).
        # Local paths (e.g. temp files from OCR Lab) must be read from disk even when STORAGE_TYPE is s3.
        is_s3_key = (
            settings.STORAGE_TYPE == "s3"
            and (pdf_path.startswith("users/") or pdf_path.startswith("cases/"))
            and not os.path.isabs(pdf_path)
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
            # #region agent log
            try:
                _size = os.path.getsize(actual_path) if os.path.exists(actual_path) else 0
            except OSError:
                _size = 0
            _debug_log("extract_text_with_coordinates path", {"pdf_path": pdf_path, "actual_path": actual_path, "exists": os.path.exists(actual_path), "size": _size}, "D")
            # #endregion
            with pdfplumber.open(actual_path) as pdf:
                result["page_count"] = len(pdf.pages)
                page_confidences: List[float] = []
                ocr_engine_used: Optional[str] = None

                for page_num, page in enumerate(pdf.pages, start=1):
                    words = page.extract_words()
                    chars = page.chars
                    page_text = page.extract_text() or ""
                    cleaned_text = self._clean_extracted_text(page_text)
                    text_segments = []
                    char_pos = 0
                    for word in words:
                        if word.get('text'):
                            text_segments.append({
                                "text": word['text'],
                                "bbox": {
                                    "x0": word.get('x0', 0),
                                    "y0": word.get('top', 0),
                                    "x1": word.get('x1', 0),
                                    "y1": word.get('bottom', 0),
                                },
                                "char_start": char_pos,
                                "char_end": char_pos + len(word['text'])
                            })
                            char_pos += len(word['text']) + 1
                    if not text_segments and chars and len(cleaned_text.strip()) >= 50:
                        # Some PDFs expose char boxes but no word boxes; keep native extraction usable.
                        text_segments = self._build_segments_from_chars(chars)
                    # #region agent log
                    _debug_log("page native extraction", {"page_num": page_num, "n_words": len(words), "n_chars": len(chars), "len_cleaned_text": len(cleaned_text.strip()), "n_segments": len(text_segments)}, "B")
                    # #endregion
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

                    # If page needs OCR and OCR is enabled, run OCR and replace text/segments
                    if getattr(settings, "OCR_ENABLED", True):
                        try:
                            from app.services.ocr import page_needs_ocr
                            needs_ocr = page_needs_ocr(cleaned_text, text_segments)
                            # #region agent log
                            _debug_log("page_needs_ocr", {"page_num": page_num, "needs_ocr": needs_ocr}, "B")
                            # #endregion
                            if needs_ocr:
                                ocr_result = _run_ocr_for_page(actual_path, page_num, engine_hint=ocr_engine_hint)
                                # #region agent log
                                _debug_log("ocr_result for page", {"page_num": page_num, "is_none": ocr_result is None, "segment_count": len(ocr_result[1]) if ocr_result else 0}, "A")
                                # #endregion
                                if ocr_result is not None:
                                    cleaned_text, text_segments, page_conf, engine_name, hybrid_stats = ocr_result
                                    result["ocr_pages"].append(page_num)
                                    result["extraction_method"] = "mixed"
                                    page_confidences.append(page_conf)
                                    ocr_engine_used = engine_name
                                else:
                                    hybrid_stats = {}
                                    # Keep native confidence when text is present but OCR was only
                                    # attempted due to missing/weak segment extraction.
                                    if len(cleaned_text.strip()) >= 50:
                                        page_confidences.append(1.0)
                                    else:
                                        page_confidences.append(0.0)
                            else:
                                hybrid_stats = {}
                                page_confidences.append(1.0)
                        except Exception as e:
                            logger.debug("OCR check failed for page %s: %s", page_num, e)
                            hybrid_stats = {}
                            page_confidences.append(1.0)
                    else:
                        hybrid_stats = {}
                        if len(cleaned_text.strip()) < 50:
                            result["ocr_pages"].append(page_num)
                            result["extraction_method"] = "mixed"
                        page_confidences.append(1.0)

                    result["pages"].append({
                        "page_number": page_num,
                        "classification": "ocr" if page_num in result["ocr_pages"] else "native",
                        "text": cleaned_text,
                        "char_count": len(cleaned_text),
                        "text_segments": text_segments,
                        "char_coordinates": char_coordinates,
                        "hybrid_stats": hybrid_stats,
                    })
                    result["text"] += f"\n\n--- Page {page_num} ---\n\n{cleaned_text}"

                result["document_confidence"] = min(page_confidences) if page_confidences else 1.0
                if ocr_engine_used:
                    result["ocr_engine_used"] = ocr_engine_used
                # #region agent log
                _debug_log("extract done", {"document_confidence": result["document_confidence"], "ocr_pages": result.get("ocr_pages", []), "page_confidences": page_confidences}, "E")
                # #endregion
                    
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

