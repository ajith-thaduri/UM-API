"""
HTTP client for the standalone OCR service (separate repo/instance).
Calls POST /ocr/process_page and returns (page_text, raw_segments, page_confidence, engine_used, w_px, h_px).
"""

from __future__ import annotations

import io
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


def ocr_process_page(
    image: Any,
    page_number: int,
    service_url: str,
    timeout_seconds: float = 120.0,
    engine_hint: Optional[str] = None,
) -> Tuple[Optional[str], List[Dict[str, Any]], float, Optional[str], int, int, Dict[str, Any]]:
    """
    Send page image to the OCR service; return normalized result for map_segments_to_pdf.

    engine_hint: optional engine id (e.g. tesseract, ppstructure) to use for this request.

    Returns:
        (page_text, raw_segments, page_confidence, engine_used, image_width_px, image_height_px, hybrid_stats)
        or (None, [], 0.0, None, 0, 0, {}) on failure.
    """
    if not (service_url or "").strip():
        logger.debug("OCR_SERVICE_URL not set, skipping OCR")
        return None, [], 0.0, None, 0, 0, {}

    buf = _image_to_bytes(image)
    if not buf:
        return None, [], 0.0, None, 0, 0, {}

    url = f"{service_url.rstrip('/')}/ocr/process_page"
    data: Dict[str, Any] = {"page_number": page_number}
    if (engine_hint or "").strip():
        data["engine"] = (engine_hint or "").strip()
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(url, files={"page_image": ("page.jpg", buf, "image/jpeg")}, data=data)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("OCR service request failed: %s", e)
        return None, [], 0.0, None, 0, 0, {}

    if not isinstance(data, dict):
        return None, [], 0.0, None, 0, 0, {}

    page_text = data.get("page_text") or ""
    raw_segments = data.get("raw_segments") or []
    page_confidence = float(data.get("page_confidence", 0.0))
    engine_used = data.get("engine_used")
    w_px = int(data.get("image_width_px", 0)) or 1
    h_px = int(data.get("image_height_px", 0)) or 1
    hybrid_stats = data.get("hybrid_stats") or {}

    return page_text, raw_segments, page_confidence, engine_used, w_px, h_px, hybrid_stats


def _image_to_bytes(image: Any) -> Optional[bytes]:
    if image is None:
        return None
    try:
        from PIL import Image
        if hasattr(image, "save"):
            img = image
        elif hasattr(image, "read"):
            img = Image.open(image).convert("RGB")
        else:
            img = Image.fromarray(image).convert("RGB")
        buf = io.BytesIO()
        # Use JPEG instead of PNG to drastically reduce HTTP payload size over the network
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception as e:
        logger.debug("Image to bytes failed: %s", e)
        return None
