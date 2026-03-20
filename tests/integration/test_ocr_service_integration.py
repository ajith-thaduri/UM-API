"""
Integration test: UM-API OCR HTTP client talks to the standalone OCR service.

This starts the OCR FastAPI app via uvicorn in a subprocess (no in-process imports)
to avoid Python package name collisions (`app` exists in both UM-API and OCR repos).
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.services.ocr.ocr_service_client import ocr_process_page


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def ocr_service_base_url() -> str:
    v2_root = Path(__file__).resolve().parents[3]
    ocr_repo = v2_root / "OCR"
    port = _pick_free_port()

    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    # Keep the service light for tests.
    env.setdefault("OCR_PREPROCESS_ENABLED", "false")
    env.setdefault("OCR_LAYOUT_ENABLED", "false")

    proc = subprocess.Popen(
        ["python3", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ocr_repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    base_url = f"http://127.0.0.1:{port}"

    # Wait for service to respond on /health (200 or 503 depending on engine availability).
    deadline = time.time() + 20
    last_err: str | None = None
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=1.0)
            if r.status_code in (200, 503):
                break
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        time.sleep(0.25)
    else:
        try:
            out = (proc.stdout.read() if proc.stdout else "")[:4000]
        except Exception:  # noqa: BLE001
            out = ""
        proc.terminate()
        raise RuntimeError(f"OCR service did not become ready. last_err={last_err!r}\noutput:\n{out}")

    yield base_url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_um_api_client_can_call_ocr_service(ocr_service_base_url: str) -> None:
    img = Image.new("RGB", (64, 64), color=(255, 255, 255))
    page_text, raw_segments, page_confidence, engine_used, w_px, h_px = ocr_process_page(
        img,
        page_number=1,
        service_url=ocr_service_base_url,
        timeout_seconds=10.0,
    )

    assert w_px == 64
    assert h_px == 64
    assert isinstance(page_text, str)
    assert isinstance(raw_segments, list)
    assert isinstance(page_confidence, float)
    assert 0.0 <= page_confidence <= 1.0
    assert engine_used is None or isinstance(engine_used, str)

