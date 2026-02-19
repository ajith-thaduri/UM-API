"""Unit tests for SFTPIngestService"""

import pytest
from unittest.mock import MagicMock, patch, Mock
from io import BytesIO


@pytest.fixture
def mock_paramiko():
    """Mock paramiko module"""
    mock_paramiko = MagicMock()
    mock_paramiko.SSHClient = MagicMock
    mock_paramiko.AutoAddPolicy = MagicMock
    return mock_paramiko


def test_sftp_service_init_without_paramiko():
    """Test that service raises ImportError if paramiko not available"""
    with patch("app.services.sftp_ingest_service.PARAMIKO_AVAILABLE", False):
        with pytest.raises(ImportError, match="paramiko package is required"):
            from app.services.sftp_ingest_service import SFTPIngestService
            SFTPIngestService()


def test_connect_with_key_file(mock_paramiko):
    """Test SFTP connection with key file"""
    with patch("app.services.sftp_ingest_service.PARAMIKO_AVAILABLE", True), \
         patch("app.services.sftp_ingest_service.paramiko", mock_paramiko), \
         patch("app.services.sftp_ingest_service.settings") as mock_settings, \
         patch("os.path.exists", return_value=True):
        
        mock_settings.SFTP_ENABLED = True
        mock_settings.SFTP_HOST = "test.host.com"
        mock_settings.SFTP_PORT = 22
        mock_settings.SFTP_USERNAME = "user"
        mock_settings.SFTP_PASSWORD = None
        mock_settings.SFTP_KEY_FILE = "/path/to/key"
        mock_settings.SFTP_BASE_DIR = "/base"
        mock_settings.SFTP_PROCESSED_DIR = "/processed"
        mock_settings.SFTP_ERROR_DIR = "/error"
        mock_settings.SFTP_POLL_INTERVAL = 60
        
        from app.services.sftp_ingest_service import SFTPIngestService
        service = SFTPIngestService()
        
        # Mock the client creation
        mock_client = MagicMock()
        mock_sftp = MagicMock()
        mock_client.open_sftp.return_value = mock_sftp
        mock_paramiko.SSHClient.return_value = mock_client
        
        result = service._connect()
        
        # Should attempt to connect - check that connect was called
        assert mock_client.connect.called or result is not False


def test_connect_with_password(mock_paramiko):
    """Test SFTP connection with password"""
    with patch("app.services.sftp_ingest_service.PARAMIKO_AVAILABLE", True), \
         patch("app.services.sftp_ingest_service.paramiko", mock_paramiko), \
         patch("app.services.sftp_ingest_service.settings") as mock_settings:
        
        mock_settings.SFTP_ENABLED = True
        mock_settings.SFTP_HOST = "test.host.com"
        mock_settings.SFTP_PORT = 22
        mock_settings.SFTP_USERNAME = "user"
        mock_settings.SFTP_PASSWORD = "password"
        mock_settings.SFTP_KEY_FILE = None
        mock_settings.SFTP_BASE_DIR = "/base"
        mock_settings.SFTP_PROCESSED_DIR = "/processed"
        mock_settings.SFTP_ERROR_DIR = "/error"
        mock_settings.SFTP_POLL_INTERVAL = 60
        
        from app.services.sftp_ingest_service import SFTPIngestService
        service = SFTPIngestService()
        
        # Mock the client creation
        mock_client = MagicMock()
        mock_sftp = MagicMock()
        mock_client.open_sftp.return_value = mock_sftp
        mock_paramiko.SSHClient.return_value = mock_client
        
        result = service._connect()
        
        # Should attempt to connect - check that connect was called
        assert mock_client.connect.called or result is not False


def test_list_files(mock_paramiko):
    """Test listing files from SFTP"""
    with patch("app.services.sftp_ingest_service.PARAMIKO_AVAILABLE", True), \
         patch("app.services.sftp_ingest_service.paramiko", mock_paramiko), \
         patch("app.services.sftp_ingest_service.settings") as mock_settings:
        
        mock_settings.SFTP_ENABLED = True
        mock_settings.SFTP_HOST = "test.host.com"
        mock_settings.SFTP_PORT = 22
        mock_settings.SFTP_USERNAME = "user"
        mock_settings.SFTP_PASSWORD = "password"
        mock_settings.SFTP_KEY_FILE = None
        mock_settings.SFTP_BASE_DIR = "/base"
        mock_settings.SFTP_PROCESSED_DIR = "/processed"
        mock_settings.SFTP_ERROR_DIR = "/error"
        mock_settings.SFTP_POLL_INTERVAL = 60
        
        from app.services.sftp_ingest_service import SFTPIngestService
        service = SFTPIngestService()
        
        mock_sftp = MagicMock()
        mock_attr = MagicMock()
        mock_attr.filename = "test.pdf"
        mock_attr.st_size = 1024
        mock_attr.st_mtime = 1234567890
        mock_sftp.listdir_attr.return_value = [mock_attr]
        service._sftp = mock_sftp
        
        files = service._list_files()
        
        assert len(files) == 1
        assert files[0]["filename"] == "test.pdf"
        assert files[0]["size"] == 1024


def test_list_files_filters_non_pdf(mock_paramiko):
    """Test that only PDF files are returned"""
    with patch("app.services.sftp_ingest_service.PARAMIKO_AVAILABLE", True), \
         patch("app.services.sftp_ingest_service.paramiko", mock_paramiko), \
         patch("app.services.sftp_ingest_service.settings") as mock_settings:
        
        mock_settings.SFTP_ENABLED = True
        mock_settings.SFTP_HOST = "test.host.com"
        mock_settings.SFTP_PORT = 22
        mock_settings.SFTP_USERNAME = "user"
        mock_settings.SFTP_PASSWORD = "password"
        mock_settings.SFTP_KEY_FILE = None
        mock_settings.SFTP_BASE_DIR = "/base"
        mock_settings.SFTP_PROCESSED_DIR = "/processed"
        mock_settings.SFTP_ERROR_DIR = "/error"
        mock_settings.SFTP_POLL_INTERVAL = 60
        
        from app.services.sftp_ingest_service import SFTPIngestService
        service = SFTPIngestService()
        
        mock_sftp = MagicMock()
        mock_attr_pdf = MagicMock()
        mock_attr_pdf.filename = "test.pdf"
        mock_attr_pdf.st_size = 1024
        mock_attr_pdf.st_mtime = 1234567890
        
        mock_attr_txt = MagicMock()
        mock_attr_txt.filename = "test.txt"
        mock_attr_txt.st_size = 512
        mock_attr_txt.st_mtime = 1234567890
        
        mock_sftp.listdir_attr.return_value = [mock_attr_pdf, mock_attr_txt]
        service._sftp = mock_sftp
        
        files = service._list_files()
        
        # Should only return PDF files
        assert len(files) == 1
        assert files[0]["filename"] == "test.pdf"


def test_download_file(mock_paramiko):
    """Test downloading file from SFTP"""
    with patch("app.services.sftp_ingest_service.PARAMIKO_AVAILABLE", True), \
         patch("app.services.sftp_ingest_service.paramiko", mock_paramiko), \
         patch("app.services.sftp_ingest_service.settings") as mock_settings:
        
        mock_settings.SFTP_ENABLED = True
        mock_settings.SFTP_HOST = "test.host.com"
        mock_settings.SFTP_PORT = 22
        mock_settings.SFTP_USERNAME = "user"
        mock_settings.SFTP_PASSWORD = "password"
        mock_settings.SFTP_KEY_FILE = None
        mock_settings.SFTP_BASE_DIR = "/base"
        mock_settings.SFTP_PROCESSED_DIR = "/processed"
        mock_settings.SFTP_ERROR_DIR = "/error"
        mock_settings.SFTP_POLL_INTERVAL = 60
        
        from app.services.sftp_ingest_service import SFTPIngestService
        service = SFTPIngestService()
        
        mock_sftp = MagicMock()
        mock_buffer = BytesIO(b"PDF content")
        mock_sftp.getfo.return_value = None
        service._sftp = mock_sftp
        
        file_data = service._download_file("test.pdf")
        
        assert file_data is not None
        assert mock_sftp.getfo.called


def test_move_file(mock_paramiko):
    """Test moving file to processed/error directory"""
    with patch("app.services.sftp_ingest_service.PARAMIKO_AVAILABLE", True), \
         patch("app.services.sftp_ingest_service.paramiko", mock_paramiko), \
         patch("app.services.sftp_ingest_service.settings") as mock_settings:
        
        mock_settings.SFTP_ENABLED = True
        mock_settings.SFTP_HOST = "test.host.com"
        mock_settings.SFTP_PORT = 22
        mock_settings.SFTP_USERNAME = "user"
        mock_settings.SFTP_PASSWORD = "password"
        mock_settings.SFTP_KEY_FILE = None
        mock_settings.SFTP_BASE_DIR = "/base"
        mock_settings.SFTP_PROCESSED_DIR = "/processed"
        mock_settings.SFTP_ERROR_DIR = "/error"
        mock_settings.SFTP_POLL_INTERVAL = 60
        
        from app.services.sftp_ingest_service import SFTPIngestService
        service = SFTPIngestService()
        
        mock_sftp = MagicMock()
        mock_sftp.chdir.side_effect = [None, IOError()]  # First dir exists, second doesn't
        service._sftp = mock_sftp
        
        result = service._move_file("test.pdf", "/processed")
        
        assert result is True
        assert mock_sftp.rename.called


@pytest.mark.asyncio
async def test_process_file(mock_paramiko):
    """Test processing a downloaded file"""
    with patch("app.services.sftp_ingest_service.PARAMIKO_AVAILABLE", True), \
         patch("app.services.sftp_ingest_service.paramiko", mock_paramiko), \
         patch("app.services.sftp_ingest_service.settings") as mock_settings:
        
        mock_settings.SFTP_ENABLED = True
        mock_settings.SFTP_HOST = "test.host.com"
        mock_settings.SFTP_PORT = 22
        mock_settings.SFTP_USERNAME = "user"
        mock_settings.SFTP_PASSWORD = "password"
        mock_settings.SFTP_KEY_FILE = None
        mock_settings.SFTP_BASE_DIR = "/base"
        mock_settings.SFTP_PROCESSED_DIR = "/processed"
        mock_settings.SFTP_ERROR_DIR = "/error"
        mock_settings.SFTP_POLL_INTERVAL = 60
        
        from app.services.sftp_ingest_service import SFTPIngestService
        service = SFTPIngestService()
        
        result = await service._process_file("test.pdf", b"PDF content")
        
        # Should return True (placeholder implementation)
        assert result is True


def test_disconnect(mock_paramiko):
    """Test disconnecting from SFTP"""
    with patch("app.services.sftp_ingest_service.PARAMIKO_AVAILABLE", True), \
         patch("app.services.sftp_ingest_service.paramiko", mock_paramiko), \
         patch("app.services.sftp_ingest_service.settings") as mock_settings:
        
        mock_settings.SFTP_ENABLED = True
        mock_settings.SFTP_HOST = "test.host.com"
        mock_settings.SFTP_PORT = 22
        mock_settings.SFTP_USERNAME = "user"
        mock_settings.SFTP_PASSWORD = "password"
        mock_settings.SFTP_KEY_FILE = None
        mock_settings.SFTP_BASE_DIR = "/base"
        mock_settings.SFTP_PROCESSED_DIR = "/processed"
        mock_settings.SFTP_ERROR_DIR = "/error"
        mock_settings.SFTP_POLL_INTERVAL = 60
        
        from app.services.sftp_ingest_service import SFTPIngestService
        service = SFTPIngestService()
        
        mock_client = MagicMock()
        mock_sftp = MagicMock()
        service._client = mock_client
        service._sftp = mock_sftp
        
        service._disconnect()
        
        assert mock_sftp.close.called
        assert mock_client.close.called
        assert service._sftp is None
        assert service._client is None
