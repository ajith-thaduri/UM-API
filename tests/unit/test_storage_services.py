import pytest
from unittest.mock import MagicMock, patch, mock_open
from fastapi import UploadFile
from app.services.local_storage_service import LocalStorageService
from pathlib import Path

@pytest.fixture
def local_storage_service():
    with patch("app.services.local_storage_service.Path.mkdir"):
        return LocalStorageService()

@pytest.mark.asyncio
async def test_local_save_case_file(local_storage_service):
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test.pdf"
    mock_file.read.return_value = b"test content"
    
    with patch("app.services.local_storage_service.open", mock_open()) as mocked_open, \
         patch("app.services.local_storage_service.Path.mkdir"):
        
        s3_key, size, filename = await local_storage_service.save_case_file(
            "case-1", mock_file, file_id="file-1", user_id="user-1"
        )
        
        assert filename == "test.pdf"
        assert size == len(b"test content")
        assert "users/user-1/cases/case-1/file-1/test.pdf" in s3_key
        mocked_open.assert_called_once()

def test_local_get_file_path(local_storage_service):
    with patch("app.services.local_storage_service.Path.mkdir"):
        path = local_storage_service._get_file_path("case-1", "file-1", "test.pdf", user_id="user-1")
        assert str(path).endswith("users/user-1/cases/case-1/file-1/test.pdf")
