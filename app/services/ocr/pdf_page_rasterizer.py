"""Render a single PDF page to an image with stable dimensions for OCR and coordinate mapping."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def rasterize_pdf_page(
    pdf_path: str,
    page_number: int,
    dpi: int = 200,
) -> Tuple[Any, float, float]:
    """
    Render one PDF page to a PIL Image and return PDF page dimensions in points.

    Args:
        pdf_path: Path to PDF file (local or temp).
        page_number: 1-based page index.
        dpi: Resolution for rasterization (higher = better OCR, slower).

    Returns:
        (pil_image, page_width_pt, page_height_pt)
        - pil_image: PIL.Image (RGB).
        - page_width_pt, page_height_pt: PDF page size in points (for coordinate_mapper).
    """
    try:
        import pdf2image
    except ImportError:
        raise RuntimeError("pdf2image is required for OCR. Install with: pip install pdf2image")

    # pdf2image returns list of PIL Images; we need one page
    images = pdf2image.convert_from_path(
        pdf_path,
        first_page=page_number,
        last_page=page_number,
        dpi=dpi,
    )
    if not images:
        raise ValueError(f"Failed to rasterize page {page_number} of {pdf_path}")

    pil_image = images[0]

    # Get PDF page dimensions in points (1 point = 1/72 inch)
    # pdf2image uses dpi; page size in points = (width_px / dpi * 72, height_px / dpi * 72)
    w_px, h_px = pil_image.size
    page_width_pt = w_px * 72.0 / dpi
    page_height_pt = h_px * 72.0 / dpi

    return pil_image, page_width_pt, page_height_pt


def get_pdf_page_dimensions(pdf_path: str, page_number: int) -> Tuple[float, float]:
    """Return (page_width_pt, page_height_pt) without rasterizing (e.g. via PyPDF2/pdfplumber)."""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            if page_number < 1 or page_number > len(pdf.pages):
                return 612.0, 792.0
            page = pdf.pages[page_number - 1]
            w = page.width
            h = page.height
            return float(w), float(h)
    except Exception as e:
        logger.warning("Could not get page dimensions from pdfplumber: %s", e)
    return 612.0, 792.0
